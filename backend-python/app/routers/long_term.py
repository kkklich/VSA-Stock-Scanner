"""Long-term ranking and append-only observation history, all read-only routes."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.repository import QuoteRepository
from app.dependencies import get_gpw_company_service, get_quote_repository, get_ranking_cache
from app.models.long_term import (
    FinancialHistoryResponse,
    LongTermHistoryResponse,
    LongTermRankingResponse,
)
from app.routers.stocks import _market_companies, _resolve_markets, _resolve_ticker
from app.services.cache import LockRegistry, TTLCache
from app.services.gpw_company_service import GpwCompanyService
from app.services.long_term_service import build_long_term_ranking, long_term_cache_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stocks", tags=["long-term"])
_locks = LockRegistry()


@router.get("/long-term", response_model=LongTermRankingResponse)
async def get_long_term_ranking(
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    cache: Annotated[TTLCache, Depends(get_ranking_cache)],
    market: str = "gpw",
) -> LongTermRankingResponse:
    markets = _resolve_markets(market, allow_all=False)
    market_id = markets[0].id
    key = long_term_cache_key(market_id)
    if repo is None:
        return LongTermRankingResponse(market=market_id, db_enabled=False)
    async with _locks.get(key):
        if (cached := cache.get(key)) is not None:
            return cached
        generation = cache.generation
        try:
            result = await build_long_term_ranking(
                _market_companies(companies, markets), market_id, repo,
            )
        except Exception as exc:
            logger.exception("Long-term ranking could not read stored data.")
            raise HTTPException(503, "Long-term ranking data is temporarily unavailable.") from exc
        if generation == cache.generation:
            cache.set(key, result, 600)
        return result


def _tracked_ticker(ticker: str, companies: GpwCompanyService) -> str:
    normalized = _resolve_ticker(ticker, companies)
    if companies.find(normalized) is None:
        raise HTTPException(404, "This company is not tracked.")
    return normalized


@router.get("/{ticker}/long-term-history", response_model=LongTermHistoryResponse)
async def get_long_term_history(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    limit: Annotated[int, Query(ge=1, le=365)] = 100,
) -> LongTermHistoryResponse:
    normalized = _tracked_ticker(ticker, companies)
    try:
        items = await repo.get_long_term_history(normalized, limit) if repo else []
    except Exception as exc:
        logger.exception("Could not read long-term history for %s.", normalized)
        raise HTTPException(503, "Long-term history is temporarily unavailable.") from exc
    return LongTermHistoryResponse(ticker=normalized, db_enabled=repo is not None, items=items)


@router.get("/{ticker}/financial-history", response_model=FinancialHistoryResponse)
async def get_financial_history(
    ticker: str,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)],
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)],
    limit: Annotated[int, Query(ge=1, le=365)] = 50,
) -> FinancialHistoryResponse:
    normalized = _tracked_ticker(ticker, companies)
    try:
        items = await repo.get_financial_history(normalized, limit) if repo else []
    except Exception as exc:
        logger.exception("Could not read financial history for %s.", normalized)
        raise HTTPException(503, "Financial history is temporarily unavailable.") from exc
    return FinancialHistoryResponse(ticker=normalized, db_enabled=repo is not None, items=items)
