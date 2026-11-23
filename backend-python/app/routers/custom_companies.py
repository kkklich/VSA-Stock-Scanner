"""Signed-in users can extend the shared stock catalogue."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from app.db.models import UserRow
from app.dependencies import gpw_company_service, history_cache, ranking_cache, yahoo_client
from app.markets import enabled_markets, get_market, market_of, normalize_ticker, ticker_for
from app.models import GpwCompany
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/custom-stocks", tags=["stocks"])
_add_lock = asyncio.Lock()


class AddStock(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    ticker: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=1, max_length=100)
    market: str = Field(min_length=1, max_length=8)


def fail(status: int, code: str):
    return HTTPException(status, detail={"code": code, "message": code})


@router.post("", response_model=GpwCompany, status_code=201)
async def add_stock(
    payload: AddStock,
    user: Annotated[UserRow, Depends(get_current_user)],
    x_expected_user_id: Annotated[int | None, Header()] = None,
):
    if x_expected_user_id is not None and x_expected_user_id != user.id:
        raise fail(409, "account_changed")
    repo = gpw_company_service.custom_repository
    if repo is None:
        raise fail(503, "storage_unavailable")
    market = get_market(payload.market)
    if market is None or market not in enabled_markets():
        raise fail(422, "unsupported_market")
    # Accept either the exchange symbol or an already suffixed app ticker.
    normalized = normalize_ticker(payload.ticker)
    if normalized and "." in normalized and market_of(normalized).id != market.id:
        raise fail(422, "invalid_ticker")
    ticker = (normalized if normalized and market_of(normalized).id == market.id
              else ticker_for(payload.ticker, market))
    if ticker is None or market_of(ticker).id != market.id:
        raise fail(422, "invalid_ticker")
    async with _add_lock:
        if gpw_company_service.find(ticker):
            raise fail(409, "stock_exists")
        try:
            quotes = await asyncio.wait_for(yahoo_client.get_daily_history(
                ticker, from_date=datetime.now(UTC).date() - timedelta(days=5 * 366),
            ), timeout=45)
        except Exception as exc:
            raise fail(502, "price_check_failed") from exc
        if not quotes:
            raise fail(422, "no_price_history")
        company = GpwCompany(
            ticker=ticker, name=payload.name, country=payload.country,
            market=market.id, exchange=market.exchange, currency=market.currency,
        )
        try:
            await repo.add(company, user.id, quotes)
        except IntegrityError as exc:
            raise fail(409, "stock_exists") from exc
        gpw_company_service.add_company(company)
        history_cache.clear()
        ranking_cache.clear()
        return company
