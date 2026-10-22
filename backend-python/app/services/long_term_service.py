"""QVM rankings use stored observations; browsing never downloads financial data."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.analysis.long_term import MODEL_VERSION, compute_long_term
from app.db.base import DB_SCAN_CONCURRENCY
from app.db.repository import QuoteRepository
from app.markets import get_market, market_of
from app.models import GpwCompany, StooqDailyQuote
from app.models.long_term import LongTermRankingResponse
from app.services.ranking_service import CONTEXT_HISTORY_DAYS


def long_term_cache_key(market: str) -> str:
    return f"long-term:{market}:{MODEL_VERSION}"


async def build_long_term_ranking(
    companies: list[GpwCompany],
    market: str,
    repo: QuoteRepository | None,
    *,
    now: datetime | None = None,
) -> LongTermRankingResponse:
    """Use completed sessions and observed fundamentals for a single market.

    Observation time is distinct from each stock's latest price session.
    Read failures propagate: a partial peer universe would silently change ranks.
    """
    current = now or datetime.now(UTC)
    exchange = get_market(market)
    if exchange is None:
        raise ValueError(f"Unknown market: {market}")
    scope = [c for c in companies if market_of(c.ticker).id == market]
    if repo is None:
        return LongTermRankingResponse(market=market, db_enabled=False)
    fundamentals = await repo.get_long_term_inputs([c.ticker for c in scope])
    fundamentals = {
        ticker: observation for ticker, observation in fundamentals.items()
        if observation["observed_at"] <= current
    }
    semaphore = asyncio.Semaphore(DB_SCAN_CONCURRENCY)
    from_date = current.date() - timedelta(days=CONTEXT_HISTORY_DAYS)

    async def load(company: GpwCompany) -> tuple[str, list[StooqDailyQuote]]:
        exchange = market_of(company.ticker)
        async with semaphore:
            bars = await repo.get_quotes(company.ticker, from_date, current.date())
        return company.ticker, [q for q in bars if exchange.session_is_final(q.date, current)]

    quotes = dict(await asyncio.gather(*(load(company) for company in scope)))
    items = compute_long_term(scope, quotes, fundamentals, as_of=exchange.local_date(current))
    items.sort(key=lambda item: (item.score is None, -(item.score or 0), item.ticker))
    latest = max((q.date for bars in quotes.values() for q in bars), default=None)
    return LongTermRankingResponse(
        market=market, as_of=latest, db_enabled=True, items=items,
        total_count=len(items), scored_count=sum(item.score is not None for item in items),
    )
