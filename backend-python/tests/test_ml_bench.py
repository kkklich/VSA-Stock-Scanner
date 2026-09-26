"""The bench reproduces the app's own back-test gate (plan §6.6)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.analysis.methods import get_method
from app.db.repository import InMemoryQuoteRepository
from app.ml.bench import coverage, random_filter_bar, reproduce_gate
from app.ml.dataset import StockInput
from app.models import GpwCompany
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.method_backtest_service import compute_method_backtest
from tests.ml_synthetic import random_walk_bars


class _NoNetwork:
    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        raise StooqAccessError("offline")


@pytest.mark.asyncio
@pytest.mark.parametrize("method_id", ["vsa4", "breakout"])
@pytest.mark.parametrize("horizon", [10, 30])
async def test_bench_matches_the_gate(method_id, horizon):
    stocks = [
        StockInput(f"s{i}", "gpw", "PLN", None, random_walk_bars(520, seed=40 + i, vol=0.03))
        for i in range(6)
    ]
    today = max(b.date for s in stocks for b in s.bars) + timedelta(days=1)
    repo = InMemoryQuoteRepository()
    for s in stocks:
        await repo.upsert_quotes(s.ticker, list(s.bars))
    companies = [GpwCompany(ticker=s.ticker, name=s.ticker) for s in stocks]

    app = await compute_method_backtest(
        get_method(method_id), companies, _NoNetwork(), TTLCache(), 60,
        repo=repo, today=today, forward_sessions=horizon,
    )
    bench = reproduce_gate(stocks, method_id, (10, 30), today)[horizon]
    assert bench.evaluated == app.evaluated_count
    assert bench.wins == app.win_count
    if app.evaluated_count:
        assert bench.avg_excess_pp == pytest.approx(app.avg_excess_return_pct, abs=0.01)


def test_random_filter_bar_is_above_its_mean():
    import pandas as pd

    labels = pd.Series([1.0] * 55 + [0.0] * 45)
    bar = random_filter_bar(labels, (0.4,))
    mean, p95 = bar[0.4]
    assert mean == pytest.approx(0.55, abs=0.01) and p95 > mean


def test_coverage_counts_market_days():
    stocks = [
        StockInput(f"s{i}", "gpw", "PLN", None, random_walk_bars(30, start=date(2024, 1, 1)))
        for i in range(21)
    ]
    (c,) = coverage(stocks)
    assert c.companies == 21 and c.days_with_market == 30
    assert c.first_full_day == c.first_date
