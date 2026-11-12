"""Portfolios are available only to their authenticated owner."""

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from hmac import compare_digest, digest
from typing import Annotated
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db.models import UserRow
from app.db.user_repository import UserRepository
from app.dependencies import get_live_prices, get_user_repository, gpw_company_service
from app.markets import market_of, quote_currency
from app.models.portfolio import AddTransaction, CreatePortfolio, UpdatePortfolio
from app.routers.auth import get_current_user
from app.services.auth import jwt_secret
from app.services.portfolio import WARSAW, PortfolioError, valuation, xtb_checkpoint
from app.services.portfolio_instruments import find_portfolio_instrument, list_portfolio_instruments
from app.services.portfolio_summary import SUMMARY_DAYS, portfolio_summary
from app.services.xtb_daily_statement import parse_xtb_daily_statement
from app.services.xtb_import import MAX_FILE_BYTES, parse_xtb, prepare_import
from app.services.xtb_wallet_import import parse_xtb_wallets

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])
AuthenticatedOwner = Annotated[UserRow, Depends(get_current_user)]
Repository = Annotated[UserRepository, Depends(get_user_repository)]


def require_expected_owner(user: UserRow, expected: int | None) -> UserRow:
    if expected is not None and expected != user.id:
        raise HTTPException(409, detail={"code": "account_changed", "message": "account_changed"})
    return user


async def portfolio_owner(
    user: AuthenticatedOwner,
    x_expected_user_id: Annotated[int | None, Header(gt=0)] = None,
) -> UserRow:
    return require_expected_owner(user, x_expected_user_id)


async def wallet_import_owner(
    user: AuthenticatedOwner, x_expected_user_id: Annotated[int, Header(gt=0)]
) -> UserRow:
    return require_expected_owner(user, x_expected_user_id)


Owner = Annotated[UserRow, Depends(portfolio_owner)]
WalletImportOwner = Annotated[UserRow, Depends(wallet_import_owner)]


async def execute(response, operation):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await operation
    except PortfolioError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.code}) from exc


@router.get("/instruments")
async def instruments(user: Owner, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    return [
        {"ticker": c.ticker, "name": c.name, "market": c.market, "currency": quote_currency(c)}
        for c in list_portfolio_instruments(gpw_company_service)
    ]


@router.get("")
async def portfolios(user: Owner, repo: Repository, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    now = datetime.now(UTC)
    today = now.astimezone(WARSAW).date()
    rows = await repo.portfolios.list(user.id)
    tickers = {t["ticker"] for row in rows for t in row["transactions"]}
    tickers.update(
        change["ticker"]
        for row in rows
        if row["reconciliation"]
        for change in row["reconciliation"]["changes"]
    )
    history = await repo.portfolios.quote_history(
        tickers, today - timedelta(days=SUMMARY_DAYS), today
    )
    quotes = {}
    live = get_live_prices()
    for ticker in tickers:
        market = market_of(ticker)
        company = find_portfolio_instrument(ticker, gpw_company_service)
        currency = quote_currency(company) if company else market.currency
        observations = history.get(ticker, [])
        for observation in observations:
            observation["currency"] = currency
        quote = {**observations[-1], "source": "close"} if observations else None
        current = live.get(ticker) if live else None
        if (
            current
            and current.session_date <= today
            and (quote is None or current.session_date > quote["date"])
        ):
            price = Decimal(str(current.price))
            if price.is_finite() and price > 0:
                quote = {
                    "price": price,
                    "date": current.session_date,
                    "asOf": current.as_of,
                    "source": "intraday",
                    "currency": currency,
                }
        if quote:
            quote["ageDays"] = max(0, (market.local_date(now) - quote["date"]).days)
            quotes[ticker] = quote
    items = [
        {
            **{key: value for key, value in row.items() if key != "ledger"},
            **valuation(row["ledger"], quotes, row["costMethod"]),
        }
        for row in rows
    ]
    return {
        "items": items,
        "summary": await portfolio_summary(rows, items, history, today),
        "valuedAt": now,
    }


@router.post("", status_code=201)
async def create(payload: CreatePortfolio, user: Owner, repo: Repository, response: Response):
    return await execute(response, repo.portfolios.change(user.id, "create", payload=payload))


async def read_import_file(request: Request) -> bytes:
    # Raw bounded uploads avoid buffering an arbitrarily large multipart request.
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_FILE_BYTES:
            raise PortfolioError("import_file_too_large", 413)
    return bytes(data)


async def import_file(request: Request, filename: str):
    data = await read_import_file(request)
    return await run_in_threadpool(parse_xtb, data, filename, gpw_company_service)


@router.post("/imports/xtb/automation")
async def import_xtb_automation(
    request: Request,
    repo: Annotated[UserRepository | None, Depends(get_user_repository)],
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
    x_import_filename: Annotated[str | None, Header()] = None,
):
    token = settings.xtb_automation_token.get_secret_value()
    owner = settings.xtb_automation_user_id
    portfolio = settings.xtb_automation_portfolio_id
    if len(token) < 32 or owner is None or portfolio is None:
        raise HTTPException(404, detail={"code": "not_found"})
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(
            401, detail={"code": "invalid_automation_token"}, headers={"WWW-Authenticate": "Bearer"}
        )
    if repo is None:
        raise HTTPException(503, detail={"code": "database_unavailable"})

    async def commit():
        try:
            filename = unquote(x_import_filename or "", errors="strict")
        except UnicodeDecodeError as exc:
            raise PortfolioError("import_invalid_filename", 422) from exc
        if (
            not 1 <= len(filename) <= 200
            or not filename.isprintable()
            or any(separator in filename for separator in ("/", "\\"))
        ):
            raise PortfolioError("import_invalid_filename", 422)
        if filename.lower().endswith(".pdf"):
            password = settings.xtb_statement_password.get_secret_value()
            if not password:
                raise PortfolioError("import_statement_password_unconfigured", 503)
            data = await read_import_file(request)
            parsed = await run_in_threadpool(
                parse_xtb_daily_statement, data, password, gpw_company_service
            )
            ignored_sales = parsed.ignored
        else:
            parsed = await import_file(request, filename)
            # Keep invalid rows so an ambiguous or unsupported execution stops the import.
            purchases = [
                row for row in parsed.rows if row.get("transaction", {}).get("side") != "sell"
            ]
            ignored_sales = len(parsed.rows) - len(purchases)
            parsed = replace(parsed, rows=purchases)
        result = await repo.portfolios.change(
            owner,
            "automated_import",
            portfolio_id=str(portfolio),
            parsed=parsed,
        )
        return {
            **result,
            "ignoredSales": ignored_sales,
            "warnings": parsed.warnings,
        }

    return await execute(response, commit())


async def read_wallet_import(request: Request, filename: str, owner: int):
    data = await read_import_file(request)
    report_digest = sha256(data).hexdigest()
    wallets = await run_in_threadpool(parse_xtb_wallets, data, filename, gpw_company_service)
    manifest = [{**wallet, "parsed": asdict(wallet["parsed"])} for wallet in wallets]
    payload = json.dumps([owner, report_digest, manifest], sort_keys=True, separators=(",", ":"))
    # Authorize the exact report interpretation that was previewed. Re-parsing
    # must not make a previously accepted trade silently eligible to skip.
    token = digest(jwt_secret().encode(), b"xtb-wallet-preview:v1\0" + payload.encode(), "sha256")
    return wallets, report_digest, token.hex()


@router.post("/imports/xtb/wallets/preview")
async def preview_xtb_wallets(
    request: Request,
    user: WalletImportOwner,
    repo: Repository,
    response: Response,
    filename: Annotated[str, Query(min_length=1, max_length=200)],
):
    async def preview():
        wallets, report_digest, token = await read_wallet_import(request, filename, user.id)
        result = await repo.portfolios.preview_wallets(user.id, wallets, report_digest)
        return {**result, "previewToken": token}

    return await execute(response, preview())


@router.post("/imports/xtb/wallets")
async def import_xtb_wallets(
    request: Request,
    user: WalletImportOwner,
    repo: Repository,
    response: Response,
    filename: Annotated[str, Query(min_length=1, max_length=200)],
    x_xtb_preview: Annotated[str, Header(pattern=r"^[0-9a-f]{64}$")],
    allow_partial: bool = False,
):
    async def commit():
        wallets, report_digest, token = await read_wallet_import(request, filename, user.id)
        if not compare_digest(token, x_xtb_preview):
            raise PortfolioError("import_preview_changed")
        return await repo.portfolios.import_wallets(user.id, wallets, report_digest, allow_partial)

    return await execute(response, commit())


@router.post("/{portfolio_id}/imports/xtb/preview")
async def preview_xtb(
    portfolio_id: UUID,
    request: Request,
    user: Owner,
    repo: Repository,
    response: Response,
    filename: Annotated[str, Query(min_length=1, max_length=200)],
):
    async def preview():
        portfolio = await repo.portfolios.get(user.id, str(portfolio_id))
        parsed = await import_file(request, filename)
        plan = prepare_import(
            parsed,
            portfolio["transactions"],
            portfolio["costMethod"],
            checkpoint=xtb_checkpoint(portfolio["ledger"]),
        )
        return {
            key: value
            for key, value in {**plan, "version": portfolio["version"]}.items()
            if key not in {"additions", "ledger"}
        }

    return await execute(response, preview())


@router.post("/{portfolio_id}/imports/xtb")
async def import_xtb(
    portfolio_id: UUID,
    request: Request,
    user: Owner,
    repo: Repository,
    response: Response,
    filename: Annotated[str, Query(min_length=1, max_length=200)],
    version: Annotated[int, Query(ge=1)],
    allow_partial: bool = False,
):
    async def commit():
        await repo.portfolios.get(user.id, str(portfolio_id))
        parsed = await import_file(request, filename)
        return await repo.portfolios.change(
            user.id,
            "import",
            portfolio_id=str(portfolio_id),
            version=version,
            parsed=parsed,
            allow_partial=allow_partial,
        )

    return await execute(response, commit())


@router.patch("/{portfolio_id}")
async def update(
    portfolio_id: UUID, payload: UpdatePortfolio, user: Owner, repo: Repository, response: Response
):
    return await execute(
        response,
        repo.portfolios.change(
            user.id,
            "update",
            portfolio_id=str(portfolio_id),
            payload=payload,
        ),
    )


@router.post("/{portfolio_id}/transactions", status_code=201)
async def add(
    portfolio_id: UUID, payload: AddTransaction, user: Owner, repo: Repository, response: Response
):
    company = find_portfolio_instrument(payload.ticker, gpw_company_service)
    if company is None:
        raise HTTPException(422, detail={"code": "unknown_ticker"})
    if quote_currency(company) != payload.currency:
        raise HTTPException(422, detail={"code": "currency_mismatch"})
    return await execute(
        response,
        repo.portfolios.change(
            user.id,
            "add",
            portfolio_id=str(portfolio_id),
            payload=payload,
        ),
    )


@router.delete("/{portfolio_id}/transactions/{transaction_id}")
async def remove(
    portfolio_id: UUID,
    transaction_id: UUID,
    user: Owner,
    repo: Repository,
    response: Response,
    version: Annotated[int, Query(ge=1)],
):
    return await execute(
        response,
        repo.portfolios.change(
            user.id,
            "remove",
            portfolio_id=str(portfolio_id),
            transaction_id=str(transaction_id),
            version=version,
        ),
    )


@router.delete("/{portfolio_id}")
async def delete(
    portfolio_id: UUID,
    user: Owner,
    repo: Repository,
    response: Response,
    version: Annotated[int, Query(ge=1)],
):
    return await execute(
        response,
        repo.portfolios.change(
            user.id,
            "delete",
            portfolio_id=str(portfolio_id),
            version=version,
        ),
    )
