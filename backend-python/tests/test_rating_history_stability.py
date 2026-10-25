"""Historical ratings retain their date's context across refreshes and chart ranges."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.analysis.methods.vsa_method import VsaMethod
from app.db.repository import InMemoryQuoteRepository
from app.models import GpwCompany, RatingPoint, StockRankingItem, StooqDailyQuote
from app.routers.stocks import get_rating_history
from app.services.cache import TTLCache
from app.services.gpw_company_service import GpwCompanyService
from app.services.ranking_service import CONTEXT_HISTORY_DAYS
from app.services.refresh_service import RefreshService, build_rating_points
from tests.data_alr_2026 import ALR_BARS


def _bars():
    return [
        StooqDailyQuote(
            date=date.fromisoformat(day), open=Decimal(str(op)), high=Decimal(str(high)),
            low=Decimal(str(low)), close=Decimal(str(close)), volume=volume,
        )
        for day, op, high, low, close, volume in ALR_BARS
    ]


def _points_as_of(today):
    first = today - timedelta(days=120)
    bars = [q for q in _bars() if first - timedelta(days=120) <= q.date <= today]
    return {
        p.date: p for p in build_rating_points(
            bars, snapshot_dates={q.date for q in bars if q.date >= first},
        )
    }


def test_overlapping_refresh_windows_keep_identical_historical_ratings():
    august = _points_as_of(date(2026, 8, 3))
    september = _points_as_of(date(2026, 9, 22))
    overlap = august.keys() & september.keys()
    assert date(2026, 6, 12) in overlap
    assert len(overlap) > 30
    assert {d: august[d] for d in overlap} == {d: september[d] for d in overlap}


@pytest.mark.parametrize("day", [date(2026, 6, 12), date(2026, 9, 22)])
def test_snapshot_matches_standalone_daily_vsa_read(day):
    bars = _bars()
    point, = build_rating_points(bars, snapshot_dates={day})
    expected = VsaMethod().evaluate([q for q in bars if q.date <= day])
    assert point.rating == expected.score
    assert point.verdict == expected.detail


def test_future_liquidity_does_not_change_earlier_history():
    bars = _bars()
    first = bars[:60]
    # A later collapse in volume must not suppress previously liquid sessions.
    future = [q.model_copy(update={"volume": 1}) for q in bars[60:]]
    before = build_rating_points(first)
    after = build_rating_points(first + future)
    assert before
    assert [p for p in after if p.date <= first[-1].date] == before


def _ranking_item():
    return StockRankingItem(
        ticker="ALR", name="Alior", last_price=100, price_change_pct=0,
        current_rating=50, rating_change=0, last_signal="Hold", days_since_signal=999,
        sparkline=[], volume=200_000,
    )


@pytest.mark.parametrize("warm_cache", [False, True])
async def test_refresh_preserves_saved_points_and_backfills_with_context(warm_cache):
    repo = InMemoryQuoteRepository()
    bars = _bars()
    await repo.upsert_quotes("alr", bars)
    saved = RatingPoint(date=date(2026, 6, 12), rating=37, verdict="Sell", close=123)
    await repo.upsert_rating_snapshots("alr", [saved])
    history_cache = TTLCache()
    service = RefreshService(
        companies=[GpwCompany(ticker="alr", name="Alior")],
        stooq=AsyncMock(), history_cache=history_cache, ranking_cache=TTLCache(), repo=repo,
    )
    for today in (date(2026, 8, 3), date(2026, 9, 22)):
        if warm_cache:
            key = f"history:alr:{today - timedelta(days=CONTEXT_HISTORY_DAYS)}:None"
            history_cache.set(key, bars, 60)
        assert await service._snapshot_ratings([_ranking_item()], today) == 1
        points = {p.date: p for p in await repo.get_rating_history("alr", date(2026, 1, 1))}
        assert points[saved.date] == saved
        assert max(points) <= today
        expected = _points_as_of(today)
        assert all(points[d] == p for d, p in expected.items() if d != saved.date)
    assert await service._snapshot_ratings([_ranking_item()], today) == 0


async def test_failed_snapshot_read_cannot_overwrite_saved_history():
    repo = InMemoryQuoteRepository()
    await repo.upsert_quotes("alr", _bars())
    repo.get_rating_history = AsyncMock(side_effect=RuntimeError("database unavailable"))
    repo.upsert_rating_snapshots = AsyncMock()
    service = RefreshService(
        companies=[GpwCompany(ticker="alr", name="Alior")],
        stooq=AsyncMock(), history_cache=TTLCache(), ranking_cache=TTLCache(), repo=repo,
    )
    with pytest.raises(RuntimeError, match="Rating snapshots incomplete"):
        await service._snapshot_ratings([_ranking_item()], date(2026, 9, 22))
    repo.upsert_rating_snapshots.assert_not_awaited()


async def test_computed_chart_rating_is_independent_of_display_range():
    bars = _bars()

    async def fetch(ticker, from_date=None, to_date=None):
        return [q for q in bars if from_date <= q.date <= to_date]

    provider = AsyncMock()
    provider.get_daily_history.side_effect = fetch
    responses = []
    for first in (date(2026, 6, 1), date(2026, 8, 1)):
        result = await get_rating_history(
            ticker="alr", companies=GpwCompanyService(), stooq=provider,
            cache=TTLCache(), repo=None, from_date=first, to_date=date(2026, 9, 22),
        )
        responses.append({p.date: p for p in result.points})
        assert all(p.date >= first for p in result.points)
        assert provider.get_daily_history.call_args.args[1] == (
            first - timedelta(days=120)
        )
    assert responses[1]
    assert all(responses[0][day] == point for day, point in responses[1].items())
