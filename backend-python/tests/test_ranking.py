"""Tests for the ranking service's 52-week context and its analysis window.

Three contracts are pinned here:

* ``compute_52w_context`` reports the last close vs. the 52-week high/low and
  flags a bar that sets a new extreme, over a window anchored to the last bar
  (bars older than 52 weeks are ignored);
* it refuses to answer at all when the stored bars do not span a real year —
  a three-month high must never be published as a "new 52-week high";
* the longer fetch window the 52-week context needs must NOT change ratings —
  every VSA metric still runs on the 120-day analysis slice.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.ranking_service import (
    _MIN_52W_COVERAGE_DAYS,
    compute_52w_context,
    compute_ranking,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(
    d: date,
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    volume: int = 200_000,
) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(high if high is not None else close + 1)),
        low=Decimal(str(low if low is not None else close - 1)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(closes: list[float], end: date | None = None) -> list[StooqDailyQuote]:
    """One bar per close, ending at ``end`` (default today)."""
    if end is None:
        end = date.today()
    days = len(closes)
    return [_quote(end - timedelta(days=days - 1 - i), closes[i]) for i in range(days)]


# How far back the oldest bar of a "long enough" series sits. Anything from
# _MIN_52W_COVERAGE_DAYS up to 365 counts as a real 52 weeks of coverage.
_COVERED_SPAN = 360


def _anchor(end: date, high: float, low: float) -> StooqDailyQuote:
    """One old bar that gives a short series a genuine 52 weeks of coverage.

    Its high/low sit inside the range the test cares about, so it never
    becomes the window's extreme — it only proves the history is long enough.
    """
    return _quote(end - timedelta(days=_COVERED_SPAN), close=(high + low) / 2,
                  high=high, low=low)


class _PerTickerStooqClient:
    def __init__(self, by_ticker: dict[str, list[StooqDailyQuote]]) -> None:
        self._by_ticker = by_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        # Honour from_date so the test can prove the analysis slice is used.
        rows = self._by_ticker.get(ticker, [])
        if from_date is not None:
            rows = [q for q in rows if q.date >= from_date]
        return rows


# ── compute_52w_context ───────────────────────────────────────────────────────


class TestCompute52wContext:
    def test_distances_from_known_high_and_low(self) -> None:
        # High 120, low 80, last close 100 → −16.67% from high, +25% from low.
        end = date.today()
        quotes = [
            _anchor(end, high=110, low=85),
            _quote(end - timedelta(days=3), close=90, high=120, low=88),
            _quote(end - timedelta(days=2), close=85, high=95, low=80),
            _quote(end - timedelta(days=1), close=95, high=98, low=90),
            _quote(end, close=100, high=101, low=99),
        ]
        dist_high, dist_low, new_high, new_low = compute_52w_context(quotes)
        assert dist_high == round((100 - 120) / 120 * 100, 2)  # -16.67
        assert dist_low == round((100 - 80) / 80 * 100, 2)  # 25.0
        assert new_high is False
        assert new_low is False

    def test_new_high_flag_when_last_bar_beats_all_prior(self) -> None:
        end = date.today()
        quotes = [
            _anchor(end, high=105, low=95),
            _quote(end - timedelta(days=2), close=100, high=105, low=95),
            _quote(end - timedelta(days=1), close=101, high=106, low=96),
            _quote(end, close=110, high=115, low=100),  # new high
        ]
        dist_high, _, new_high, new_low = compute_52w_context(quotes)
        assert new_high is True
        assert new_low is False
        # Closed at 110 vs its own intraday high 115 → slightly below the high.
        assert dist_high == round((110 - 115) / 115 * 100, 2)

    def test_new_low_flag_when_last_bar_undercuts_all_prior(self) -> None:
        end = date.today()
        quotes = [
            _anchor(end, high=105, low=95),
            _quote(end - timedelta(days=2), close=100, high=105, low=95),
            _quote(end - timedelta(days=1), close=99, high=104, low=94),
            _quote(end, close=90, high=95, low=85),  # new low
        ]
        _, dist_low, new_high, new_low = compute_52w_context(quotes)
        assert new_low is True
        assert new_high is False
        assert dist_low == round((90 - 85) / 85 * 100, 2)

    def test_bars_older_than_52_weeks_are_ignored(self) -> None:
        # A 130 high 400 days ago must NOT define the 52-week high.
        end = date.today()
        quotes = [
            _quote(end - timedelta(days=400), close=125, high=130, low=120),
            _anchor(end, high=105, low=95),
            _quote(end - timedelta(days=10), close=100, high=105, low=95),
            _quote(end, close=100, high=101, low=99),
        ]
        dist_high, _, _, _ = compute_52w_context(quotes)
        # Window high is 105 (the in-window bars), not the stale 130.
        assert dist_high == round((100 - 105) / 105 * 100, 2)

    def test_single_bar_has_no_context(self) -> None:
        # One bar cannot cover 52 weeks, so there is no 52-week answer to give.
        quotes = [_quote(date.today(), close=100, high=102, low=98)]
        assert compute_52w_context(quotes) == (None, None, False, False)

    def test_empty_returns_none(self) -> None:
        assert compute_52w_context([]) == (None, None, False, False)


# ── The window must actually span 52 weeks ────────────────────────────────────


class TestCoverageRequirement:
    """A "52-week high" claimed from four months of data is simply wrong.

    Short histories happen constantly: a recent listing, a ticker the DB has
    only just started collecting, a series with a long gap. In every case the
    honest answer is "unknown", not a quarterly extreme with a yearly label.
    """

    @staticmethod
    def _rising_series(days: int) -> list[StooqDailyQuote]:
        """One bar per day ending today; the last bar is the highest."""
        end = date.today()
        return [
            _quote(end - timedelta(days=days - 1 - i), close=100.0 + i)
            for i in range(days)
        ]

    def test_full_year_of_history_reports_context_and_flags(self) -> None:
        quotes = self._rising_series(365)
        dist_high, dist_low, new_high, new_low = compute_52w_context(quotes)
        assert dist_high is not None
        assert dist_low is not None
        # The series only rises, so the newest bar is a genuine 52-week high.
        assert new_high is True
        assert new_low is False

    def test_four_months_of_history_reports_nothing(self) -> None:
        # The last bar IS the highest of what is stored — but four months is
        # not a year, so it must not be advertised as a 52-week high.
        quotes = self._rising_series(120)
        assert compute_52w_context(quotes) == (None, None, False, False)

    def test_just_enough_coverage_is_accepted(self) -> None:
        end = date.today()
        quotes = [
            _quote(end - timedelta(days=_MIN_52W_COVERAGE_DAYS), close=100),
            _quote(end, close=110),
        ]
        dist_high, _, _, _ = compute_52w_context(quotes)
        assert dist_high is not None

    def test_one_day_short_of_coverage_is_rejected(self) -> None:
        end = date.today()
        quotes = [
            _quote(end - timedelta(days=_MIN_52W_COVERAGE_DAYS - 1), close=100),
            _quote(end, close=110),
        ]
        assert compute_52w_context(quotes) == (None, None, False, False)


# ── Analysis window is unaffected by the longer fetch window ──────────────────


class TestAnalysisWindowUnchanged:
    def test_old_bars_do_not_change_the_rating(self) -> None:
        # Two runs on the same recent 120 days: one with a year of extra older
        # bars prepended, one without. Ratings/verdicts must be identical —
        # the extra bars only feed the 52-week context.
        company = GpwCompany(
            ticker="kgh", name="KGHM", sector="Basic Materials", market_cap=None
        )
        recent = _series([100.0 + (i % 5) for i in range(60)])
        # Long enough that the combined series covers a real 52 weeks (so the
        # long run resolves a 52-week context at all).
        older = _series(
            [90.0] * 280, end=recent[0].date - timedelta(days=1)
        )
        with_history = older + recent

        async def run(quotes: list[StooqDailyQuote]):
            client = _PerTickerStooqClient({"kgh": quotes})
            return await compute_ranking(
                companies=[company],
                stooq=client,
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )

        short = asyncio.run(run(recent))
        long = asyncio.run(run(with_history))
        assert len(short) == 1
        assert len(long) == 1
        assert short[0].current_rating == long[0].current_rating
        assert short[0].last_signal == long[0].last_signal
        # The long run resolves a 52-week context; the short one (60 bars, so
        # ~two months of history) honestly reports "unknown".
        assert long[0].dist_from_52w_high_pct is not None
        assert short[0].dist_from_52w_high_pct is None

    def test_context_fields_present_on_ranking_items(self) -> None:
        company = GpwCompany(
            ticker="kgh", name="KGHM", sector="Basic Materials", market_cap=None
        )
        # A full year of bars — anything shorter has no 52-week context.
        quotes = _series([100.0 + (i % 7) for i in range(340)])
        client = _PerTickerStooqClient({"kgh": quotes})
        result = asyncio.run(
            compute_ranking(
                companies=[company],
                stooq=client,
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )
        )
        item = result[0]
        assert item.dist_from_52w_high_pct is not None
        assert item.dist_from_52w_high_pct <= 0
        assert item.dist_from_52w_low_pct is not None
        assert item.dist_from_52w_low_pct >= 0
