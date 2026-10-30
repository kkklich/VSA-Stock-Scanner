"""Portfolios are available only to their authenticated owner."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.db.models import UserRow
from app.db.user_repository import UserRepository
from app.dependencies import get_live_prices, get_user_repository, gpw_company_service
from app.markets import market_of, quote_currency
from app.models.portfolio import AddTransaction, CreatePortfolio, UpdatePortfolio
from app.routers.auth import get_current_user
from app.services.portfolio import PortfolioError, valuation

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])
Owner = Annotated[UserRow, Depends(get_current_user)]
Repository = Annotated[UserRepository, Depends(get_user_repository)]


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
        for c in gpw_company_service.enabled_companies()
    ]


@router.get("")
async def portfolios(user: Owner, repo: Repository, response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    rows = await repo.portfolios.list(user.id)
    tickers = {t["ticker"] for row in rows for t in row["transactions"]}
    quotes = await repo.portfolios.quotes(tickers)
    live = get_live_prices()
    for ticker in tickers:
        quote = quotes.get(ticker)
        if quote:
            quote["source"] = "close"
        current = live.get(ticker) if live else None
        if current and (quote is None or current.session_date > quote["date"]):
            quote = {
                "price": Decimal(str(current.price)),
                "date": current.session_date,
                "asOf": current.as_of,
                "source": "intraday",
            }
            quotes[ticker] = quote
        if quote:
            company = gpw_company_service.find(ticker)
            quote["currency"] = quote_currency(company) if company else market_of(ticker).currency
            quote["ageDays"] = max(0, (market_of(ticker).local_date() - quote["date"]).days)
            if not quote["price"].is_finite() or quote["price"] <= 0:
                quotes.pop(ticker)
    return {
        "items": [
            {**row, **valuation(row["transactions"], quotes, row["costMethod"])} for row in rows
        ],
        "valuedAt": datetime.now(UTC),
    }


@router.post("", status_code=201)
async def create(payload: CreatePortfolio, user: Owner, repo: Repository, response: Response):
    return await execute(response, repo.portfolios.change(user.id, "create", payload=payload))


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
    company = gpw_company_service.find(payload.ticker)
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
