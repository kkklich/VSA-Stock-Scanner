"""Market-data endpoints backed by stooq.pl.

Mirrors the .NET ``StocksController``: the tracked GPW company list and
per-ticker end-of-day price history. Routes live under ``/api/stocks``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    get_gpw_company_service,
    get_history_cache,
    get_stooq_client,
)
from app.config import settings
from app.models import GpwCompany, StockHistoryResponse
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.gpw_company_service import GpwCompanyService
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("", response_model=list[GpwCompany], summary="Tracked GPW companies")
async def get_companies(
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
) -> list[GpwCompany]:
    """Return the list of GPW companies the scanner tracks."""
    return companies.get_companies()


@router.get(
    "/{ticker}/history",
    response_model=StockHistoryResponse,
    summary="End-of-day OHLCV history for a ticker",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid ticker or date range"},
        status.HTTP_502_BAD_GATEWAY: {"description": "stooq.pl unavailable"},
    },
)
async def get_history(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    stooq: Annotated[StooqClient, Depends(get_stooq_client)],
    cache: Annotated[TTLCache[StockHistoryResponse], Depends(get_history_cache)],
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
) -> StockHistoryResponse:
    """Return a ticker's end-of-day OHLCV history from stooq.pl (cached 6h)."""
    if not ticker or not ticker.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A ticker is required.")

    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "'from' must not be later than 'to'.")

    normalized_ticker = ticker.strip().casefold()
    cache_key = f"history:{normalized_ticker}:{from_}:{to}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        company = companies.find(normalized_ticker)
        quotes = await stooq.get_daily_history(normalized_ticker, from_, to)
    except StooqAccessError as ex:
        logger.warning("stooq.pl access failed for ticker %s: %s", normalized_ticker, ex)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream data provider (stooq.pl) unavailable: {ex}",
        ) from ex

    response = StockHistoryResponse(
        ticker=normalized_ticker.upper(),
        name=company.name if company else None,
        quotes=quotes,
    )

    cache.set(cache_key, response, settings.history_cache_seconds)
    return response
