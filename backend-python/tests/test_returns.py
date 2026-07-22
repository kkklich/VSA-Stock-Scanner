"""Tests for trailing price returns and the trailing-twelve-month aggregates.

The contract these pin: a horizon is reported only when the stored history
genuinely reaches back that far. Reporting a "5Y" return computed against a
bar from 18 months ago would be worse than reporting nothing, so the staleness
guard (a baseline may be at most twice the horizon old) gets its own tests.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.analysis.returns import baseline_close, compute_price_returns, pct_change
from app.models import QuarterlyReport, StooqDailyQuote
from app.routers.stocks import _ttm_sum

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(d: date, close: float) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=100_000,
    )


def _report(period_end: str, revenue: int | None, income: int | None) -> QuarterlyReport:
    return QuarterlyReport(
        period_end=period_end, total_revenue=revenue, net_income=income
    )


# ── Primitives ────────────────────────────────────────────────────────────────


class TestPrimitives:
    def test_pct_change(self) -> None:
        assert pct_change(110.0, 100.0) == 10.0
        assert pct_change(90.0, 100.0) == -10.0

    def test_pct_change_guards_zero_baseline(self) -> None:
        # A zero/negative baseline would divide by zero — report nothing.
        assert pct_change(100.0, 0.0) is None

    def test_baseline_close_picks_newest_bar_at_or_before_cutoff(self) -> None:
        quotes = [
            _quote(date(2026, 1, 10), 100.0),
            _quote(date(2026, 1, 20), 200.0),
            _quote(date(2026, 1, 30), 300.0),
        ]
        got = baseline_close(quotes, date(2026, 1, 25), date(2026, 1, 1))
        assert got == 200.0

    def test_baseline_close_rejects_bar_older_than_floor(self) -> None:
        quotes = [_quote(date(2020, 1, 1), 100.0)]
        assert baseline_close(quotes, date(2026, 1, 25), date(2026, 1, 1)) is None


# ── compute_price_returns ─────────────────────────────────────────────────────


class TestComputePriceReturns:
    def test_one_year_return_from_known_series(self) -> None:
        end = date(2026, 6, 30)
        quotes = [
            _quote(end - timedelta(days=365), 100.0),
            _quote(end - timedelta(days=30), 130.0),
            _quote(end, 150.0),
        ]
        r = compute_price_returns(quotes)
        assert r.y1_pct == 50.0  # 100 → 150
        assert r.max_pct == 50.0  # oldest stored bar is the same one
        assert r.max_from_date == end - timedelta(days=365)

    def test_horizons_beyond_history_are_none(self) -> None:
        # ~1 year of history: 1Y resolves, 3Y and 5Y must not be invented.
        end = date(2026, 6, 30)
        quotes = [
            _quote(end - timedelta(days=365), 100.0),
            _quote(end, 120.0),
        ]
        r = compute_price_returns(quotes)
        assert r.y1_pct == 20.0
        assert r.y3_pct is None
        assert r.y5_pct is None

    def test_stale_baseline_is_rejected(self) -> None:
        # The only old bar is ~3 years back — more than twice the 1-year
        # horizon, so a "1Y" return must NOT be computed against it.
        end = date(2026, 6, 30)
        quotes = [
            _quote(end - timedelta(days=1100), 100.0),
            _quote(end, 200.0),
        ]
        r = compute_price_returns(quotes)
        assert r.y1_pct is None
        # MAX always uses the oldest bar, however old it is.
        assert r.max_pct == 100.0

    def test_ytd_uses_last_close_of_previous_year(self) -> None:
        quotes = [
            _quote(date(2025, 12, 30), 100.0),  # last close of 2025
            _quote(date(2026, 3, 1), 110.0),
            _quote(date(2026, 6, 30), 125.0),
        ]
        r = compute_price_returns(quotes)
        assert r.ytd_pct == 25.0

    def test_ytd_none_when_history_starts_this_year(self) -> None:
        # Listed in February 2026 — there is no 2025 close to measure from.
        quotes = [
            _quote(date(2026, 2, 2), 100.0),
            _quote(date(2026, 6, 30), 125.0),
        ]
        assert compute_price_returns(quotes).ytd_pct is None

    def test_single_bar_returns_empty(self) -> None:
        r = compute_price_returns([_quote(date(2026, 6, 30), 100.0)])
        assert r.y1_pct is None
        assert r.max_pct is None

    def test_empty_returns_empty(self) -> None:
        assert compute_price_returns([]).max_pct is None


# ── Trailing twelve months ────────────────────────────────────────────────────


class TestTtmSum:
    def test_sums_last_four_quarters(self) -> None:
        reports = [
            _report("2026-03-31", 40, 4),
            _report("2025-12-31", 30, 3),
            _report("2025-09-30", 20, 2),
            _report("2025-06-30", 10, 1),
        ]
        assert _ttm_sum(reports, "total_revenue") == 100
        assert _ttm_sum(reports, "net_income") == 10

    def test_uses_only_the_four_newest_quarters(self) -> None:
        reports = [
            _report("2026-03-31", 40, 4),
            _report("2025-12-31", 30, 3),
            _report("2025-09-30", 20, 2),
            _report("2025-06-30", 10, 1),
            _report("2025-03-31", 999, 999),  # older — must be ignored
        ]
        assert _ttm_sum(reports, "total_revenue") == 100

    def test_sorts_regardless_of_input_order(self) -> None:
        # Oldest-first input must give the same answer as newest-first.
        reports = [
            _report("2025-03-31", 999, 999),
            _report("2025-06-30", 10, 1),
            _report("2025-09-30", 20, 2),
            _report("2025-12-31", 30, 3),
            _report("2026-03-31", 40, 4),
        ]
        assert _ttm_sum(reports, "total_revenue") == 100

    def test_fewer_than_four_quarters_is_none(self) -> None:
        reports = [_report("2026-03-31", 40, 4), _report("2025-12-31", 30, 3)]
        assert _ttm_sum(reports, "total_revenue") is None

    def test_missing_figure_makes_the_sum_none(self) -> None:
        # A partial sum would understate a full year — report nothing instead.
        reports = [
            _report("2026-03-31", 40, 4),
            _report("2025-12-31", None, 3),
            _report("2025-09-30", 20, 2),
            _report("2025-06-30", 10, 1),
        ]
        assert _ttm_sum(reports, "total_revenue") is None
        assert _ttm_sum(reports, "net_income") == 10
