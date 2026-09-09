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

from app.analysis.vsa import compute_rating, detect_signals, verdict_from_signals
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import NEGATIVE_CACHE_SECONDS, TTLCache
from app.services.exceptions import StooqAccessError
from app.services.ranking_service import (
    _HISTORY_DAYS,
    _MIN_52W_COVERAGE_DAYS,
    _RS_OFFSETS,
    CONTEXT_HISTORY_DAYS,
    _relative_strength_raw,
    compute_52w_context,
    compute_ranking,
)
from app.services.scanner_service import compute_scanner_stats
from app.services.volume_surge_service import compute_volume_surge

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

    def test_weekly_fields_present_on_long_history(self) -> None:
        # ~48 weeks of daily bars resample to enough weekly candles for the
        # multi-timeframe read to be available.
        company = GpwCompany(
            ticker="kgh", name="KGHM", sector="Basic Materials", market_cap=None
        )
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
        assert item.weekly_rating is not None
        assert 0 <= item.weekly_rating <= 100
        assert item.weekly_signal is not None
        assert item.weekly_agreement in {"confirms", "conflicts", "neutral"}

    def test_weekly_fields_none_on_short_history(self) -> None:
        # ~9 weeks of daily bars is below the weekly-analysis floor, so the
        # multi-timeframe fields are honestly blank rather than a shaky read.
        company = GpwCompany(
            ticker="kgh", name="KGHM", sector="Basic Materials", market_cap=None
        )
        quotes = _series([100.0 + (i % 5) for i in range(60)])
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
        assert item.weekly_rating is None
        assert item.weekly_signal is None
        assert item.weekly_agreement is None


# ── The fetch window vs. the relative-strength rank ───────────────────────────
#
# ``CONTEXT_HISTORY_DAYS`` is a CALENDAR figure; everything that reads it
# downstream counts SESSIONS. The gap between the two is where this section
# lives.
#
# The window used to be 380 days, sized purely for the 52-week high/low context
# (365 days plus a fortnight of slack). But Minervini's rule 8 needs a blended
# 3/6/9/12-month return, whose longest offset is 252 *sessions*, and Minervini
# itself refuses to evaluate below 252 bars. GPW trades ~250 sessions a year, so
# 380 calendar days is only ~262-273 sessions — single-digit-to-twenty bars of
# margin — and a stock that misses the odd session (an exchange holiday, a thin
# listing, a gap in what the DB stored) fell under the line, silently lost its
# RS rank, and was scored on 7 rules while its neighbours were scored on 8.
#
# Rule 8 being applied to some rows and not others is worse than not applying it
# at all: the ranking's Minervini column then compares two different scales.

# A stock that trades most weekdays but not all: roughly one weekday in twelve
# is missing, which is about what exchange holidays plus a thinly traded listing
# produce. Nothing exotic — this is an ordinary GPW small cap.
_THIN_SKIP_EVERY = 12
# The window as it was before the widening, for the before/after comparison.
_OLD_CONTEXT_HISTORY_DAYS = 380


def _thin_session_dates(span_days: int, end: date | None = None) -> list[date]:
    """Weekday dates over ``span_days``, dropping every twelfth one."""
    if end is None:
        end = date.today()
    out: list[date] = []
    weekday_no = 0
    for offset in range(span_days, -1, -1):
        d = end - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        weekday_no += 1
        if weekday_no % _THIN_SKIP_EVERY == 0:
            continue
        out.append(d)
    return out


def _thin_series(
    span_days: int, end: date | None = None, start_price: float = 40.0
) -> list[StooqDailyQuote]:
    """A thinly traded but steadily rising stock over ``span_days`` calendar days."""
    dates = _thin_session_dates(span_days, end)
    return [
        _quote(d, close=start_price + i * 0.2 + (i % 5) * 0.05)
        for i, d in enumerate(dates)
    ]


def _within(quotes: list[StooqDailyQuote], days: int) -> list[StooqDailyQuote]:
    """The bars a fetch window of ``days`` calendar days would have returned."""
    cutoff = date.today() - timedelta(days=days)
    return [q for q in quotes if q.date >= cutoff]


class TestFetchWindowCoversTheRelativeStrengthRank:
    def test_the_old_window_starved_a_thinly_traded_stock_of_its_rs_rank(self) -> None:
        # The regression, stated in the units that actually matter: sessions.
        quotes = _thin_series(700)
        old_window = _within(quotes, _OLD_CONTEXT_HISTORY_DAYS)

        assert len(old_window) <= max(_RS_OFFSETS)
        assert _relative_strength_raw(old_window) is None

    def test_the_current_window_gives_the_same_stock_an_rs_rank(self) -> None:
        quotes = _thin_series(700)
        current_window = _within(quotes, CONTEXT_HISTORY_DAYS)

        assert _relative_strength_raw(current_window) is not None

    def test_the_window_keeps_real_margin_over_the_longest_rs_offset(self) -> None:
        # Not "just enough" — enough that no realistic amount of gappiness eats
        # through it, which is precisely what 380 days did not have.
        sessions = len(_within(_thin_series(700), CONTEXT_HISTORY_DAYS))
        assert sessions >= max(_RS_OFFSETS) + 50

    def test_the_window_still_covers_the_52_week_context_it_was_sized_for(self) -> None:
        # Widening for one reader must not shorten it for the other.
        assert CONTEXT_HISTORY_DAYS >= _MIN_52W_COVERAGE_DAYS
        assert CONTEXT_HISTORY_DAYS > 365

    def test_minervini_is_scored_on_all_eight_rules_in_the_ranking(self) -> None:
        # End to end: a cross-sectional rank needs a universe, so two companies.
        companies = [
            GpwCompany(ticker="aaa", name="Alpha SA", sector="Industry",
                       market_cap=None),
            GpwCompany(ticker="bbb", name="Beta SA", sector="Industry",
                       market_cap=None),
        ]
        client = _PerTickerStooqClient(
            {
                "aaa": _thin_series(700, start_price=40.0),
                "bbb": _thin_series(700, start_price=25.0),
            }
        )
        result = asyncio.run(
            compute_ranking(
                companies=companies,
                stooq=client,
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )
        )

        assert len(result) == 2
        for item in result:
            minervini = item.method_results["minervini"]
            assert minervini.available is True
            # "/8 rules" is the ranking path (rule 8 applied); "/7 structural"
            # is the fallback for a stock with no universe-wide rank.
            assert minervini.detail.endswith("/8 rules"), minervini.detail


# ── The wider fetch must not move a single rating ─────────────────────────────


class TestWiderFetchChangesNoRating:
    """The invariant the widening rests on.

    Every VSA metric runs on the 120-day analysis slice; the 52-week context is
    measured back from the last bar; and the weekly read is capped at 52 weekly
    candles inside ``app/analysis/weekly.py``. So bars that only the WIDER
    window can see — the 380-to-520-day band — feed the relative-strength rank
    and nothing else.
    """

    @staticmethod
    def _rank_one(quotes: list[StooqDailyQuote]):
        company = GpwCompany(
            ticker="kgh", name="KGHM", sector="Basic Materials", market_cap=None
        )
        result = asyncio.run(
            compute_ranking(
                companies=[company],
                stooq=_PerTickerStooqClient({"kgh": quotes}),
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=None,
            )
        )
        assert len(result) == 1
        return result[0]

    def test_rating_matches_the_120_day_slice_computed_directly(self) -> None:
        # Not "the two runs agree with each other" but "the run agrees with the
        # engine run on the slice alone" — the strongest form of the claim.
        quotes = _thin_series(700)
        item = self._rank_one(quotes)

        analysis_from = date.today() - timedelta(days=_HISTORY_DAYS)
        recent = [q for q in quotes if q.date >= analysis_from]
        expected_signals = detect_signals(recent)
        expected_rating = compute_rating(expected_signals, recent[-1].date)
        expected_verdict, expected_days = verdict_from_signals(
            expected_signals, recent[-1].date
        )

        assert item.current_rating == expected_rating
        assert item.last_signal == expected_verdict
        assert item.days_since_signal == expected_days

    def test_bars_only_the_wider_window_can_see_change_nothing_visible(self) -> None:
        # Same stock, two histories that are identical inside 380 days and
        # differ only in the band the widening newly reaches.
        full = _thin_series(700)
        as_the_old_window_saw_it = _within(full, _OLD_CONTEXT_HISTORY_DAYS)

        narrow = self._rank_one(as_the_old_window_saw_it)
        wide = self._rank_one(full)

        assert wide.current_rating == narrow.current_rating
        assert wide.rating_change == narrow.rating_change
        assert wide.last_signal == narrow.last_signal
        assert wide.days_since_signal == narrow.days_since_signal
        assert wide.last_price == narrow.last_price
        assert wide.price_change_pct == narrow.price_change_pct
        assert wide.volume == narrow.volume
        # The 52-week context is measured back from the last bar, so the extra
        # bars fall outside it.
        assert wide.dist_from_52w_high_pct == narrow.dist_from_52w_high_pct
        assert wide.dist_from_52w_low_pct == narrow.dist_from_52w_low_pct
        assert wide.is_new_52w_high == narrow.is_new_52w_high
        assert wide.is_new_52w_low == narrow.is_new_52w_low
        # The weekly read is capped at 52 weekly candles inside weekly.py, so a
        # longer fetch cannot reach it either.
        assert wide.weekly_rating == narrow.weekly_rating
        assert wide.weekly_signal == narrow.weekly_signal


# ── The 52-week context is anchored to the stock, not to the fetch ────────────


class TestContextAnchoringUnderTheWiderWindow:
    """More old bars now reach ``compute_52w_context``, so its bounds matter more."""

    def test_a_spike_older_than_52_weeks_never_becomes_the_52_week_high(self) -> None:
        # 450 days ago is inside the 520-day fetch and outside the 52-week
        # window. Before the widening this bar was never even fetched, so the
        # window bound was doing no work; now it is the only thing standing
        # between a year-and-a-half-old spike and the screener's "% from high".
        end = date.today()
        quotes = [
            _quote(end - timedelta(days=450), close=180, high=200, low=170),
            _quote(end - timedelta(days=_COVERED_SPAN), close=100, high=105, low=95),
            _quote(end - timedelta(days=10), close=100, high=105, low=95),
            _quote(end, close=100, high=101, low=99),
        ]
        dist_high, _, _, _ = compute_52w_context(quotes)
        assert dist_high == round((100 - 105) / 105 * 100, 2)

    def test_the_window_moves_with_the_last_session_not_with_today(self) -> None:
        # A stock whose last print is a month old: its 52-week window ends
        # there, so a bar 380 days before TODAY is only 350 days before its last
        # session and is therefore still inside the window.
        last_session = date.today() - timedelta(days=30)
        quotes = [
            _quote(last_session - timedelta(days=350), close=100, high=140, low=95),
            _quote(last_session - timedelta(days=200), close=100, high=105, low=95),
            _quote(last_session, close=100, high=101, low=99),
        ]
        dist_high, _, _, _ = compute_52w_context(quotes)
        # 140 counts: it is within 52 weeks of the LAST BAR.
        assert dist_high == round((100 - 140) / 140 * 100, 2)

    def test_a_long_fetch_of_a_short_listing_still_reports_nothing(self) -> None:
        # The coverage rule is about what the bars SPAN, not how many days were
        # asked for: a company listed four months ago has no 52-week anything,
        # however wide the fetch window is.
        quotes = _thin_series(120)
        assert compute_52w_context(quotes) == (None, None, False, False)


# ── One cached history, shared by all three full-universe scans ───────────────


class _CountingPerTickerClient(_PerTickerStooqClient):
    """Records every live fetch, and the from_date each scan asked for."""

    def __init__(self, by_ticker: dict[str, list[StooqDailyQuote]]) -> None:
        super().__init__(by_ticker)
        self.calls: list[tuple[str, date | None]] = []

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.calls.append((ticker, from_date))
        return await super().get_daily_history(ticker, from_date, to_date)


class TestSharedHistoryCache:
    """Ranking, volume-surge and scanner-stats must reuse ONE cached history.

    The cache key embeds the ``from_date`` each derives from
    ``CONTEXT_HISTORY_DAYS``. If any of them ever computed its window
    differently the keys would stop matching, every scan would re-download the
    whole universe, and nothing would look broken — just three times the load on
    Yahoo and the database.
    """

    _COMPANY = GpwCompany(
        ticker="kgh", name="KGHM", sector="Basic Materials", market_cap=None
    )

    def test_three_scans_fetch_each_ticker_once_between_them(self) -> None:
        client = _CountingPerTickerClient({"kgh": _thin_series(700)})
        shared = TTLCache()

        async def run_all() -> None:
            await compute_ranking(
                companies=[self._COMPANY], stooq=client, history_cache=shared,
                history_cache_ttl=600, repo=None,
            )
            await compute_volume_surge(
                companies=[self._COMPANY], stooq=client, history_cache=shared,
                history_cache_ttl=600, repo=None,
            )
            await compute_scanner_stats(
                companies=[self._COMPANY], stooq=client, history_cache=shared,
                history_cache_ttl=600, repo=None,
            )

        asyncio.run(run_all())

        fetched = [c for c in client.calls if c[0] == "kgh"]
        assert len(fetched) == 1, (
            "the three scans no longer share one cached history — "
            f"{len(fetched)} fetches for one ticker"
        )

    def test_all_three_ask_for_the_same_window(self) -> None:
        # The cache key is built from this date, so agreeing on it IS the
        # sharing. Each scan runs with its own cache so every one really fetches.
        client = _CountingPerTickerClient({"kgh": _thin_series(700)})

        async def run_all() -> None:
            await compute_ranking(
                companies=[self._COMPANY], stooq=client, history_cache=TTLCache(),
                history_cache_ttl=600, repo=None,
            )
            await compute_volume_surge(
                companies=[self._COMPANY], stooq=client, history_cache=TTLCache(),
                history_cache_ttl=600, repo=None,
            )
            await compute_scanner_stats(
                companies=[self._COMPANY], stooq=client, history_cache=TTLCache(),
                history_cache_ttl=600, repo=None,
            )

        asyncio.run(run_all())

        windows = {from_date for _, from_date in client.calls}
        assert len(windows) == 1
        assert windows == {date.today() - timedelta(days=CONTEXT_HISTORY_DAYS)}

    def test_the_shared_entry_is_stored_under_the_documented_key(self) -> None:
        client = _CountingPerTickerClient({"kgh": _thin_series(700)})
        shared = TTLCache()
        asyncio.run(
            compute_ranking(
                companies=[self._COMPANY], stooq=client, history_cache=shared,
                history_cache_ttl=600, repo=None,
            )
        )
        from_date = date.today() - timedelta(days=CONTEXT_HISTORY_DAYS)
        assert shared.get(f"history:kgh:{from_date}:None") is not None


# ── A ticker the provider cannot serve is not re-asked every scan ─────────────


class _DeadTickerClient(_CountingPerTickerClient):
    """Answers normally, except for tickers the provider has no data for."""

    def __init__(
        self, by_ticker: dict[str, list[StooqDailyQuote]], dead: set[str]
    ) -> None:
        super().__init__(by_ticker)
        self._dead = dead

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.calls.append((ticker, from_date))
        if ticker in self._dead:
            raise StooqAccessError(
                f"Yahoo Finance returned no data for '{ticker.upper()}.WA'."
            )
        return await _PerTickerStooqClient.get_daily_history(
            self, ticker, from_date, to_date
        )


class TestDeadTickerNegativeCache:
    """A listing the data provider cannot serve must be asked about ONCE.

    GPW listings get renamed, merged and withdrawn a few times a year, and
    Yahoo simply 404s the old symbol from then on. Without a negative cache
    every scan re-requests each dead ticker and logs an error for it, so a run
    that handled the situation perfectly prints a wall of errors and pays a
    failed round-trip per dead listing — every time anyone loads the dashboard.

    The remembered failure is deliberately capped by the caller's own TTL
    (``min(history_cache_ttl, NEGATIVE_CACHE_SECONDS)``): a passing provider
    hiccup must not be able to hide a healthy stock for a whole trading day.
    """

    _LIVE = GpwCompany(
        ticker="kgh", name="KGHM", sector="Basic Materials", market_cap=None
    )
    _DEAD = GpwCompany(
        ticker="ccc", name="Renamed away", sector="Consumer Cyclical", market_cap=None
    )

    def _client(self) -> _DeadTickerClient:
        return _DeadTickerClient({"kgh": _thin_series(700)}, dead={"ccc"})

    async def _rank(self, client, cache, ttl):
        return await compute_ranking(
            companies=[self._LIVE, self._DEAD],
            stooq=client,
            history_cache=cache,
            history_cache_ttl=ttl,
            repo=None,
        )

    def test_dead_ticker_is_fetched_once_across_repeated_scans(self) -> None:
        client = self._client()
        shared = TTLCache()

        async def run_twice():
            first = await self._rank(client, shared, 600)
            second = await self._rank(client, shared, 600)
            return first, second

        first, second = asyncio.run(run_twice())

        dead_calls = [t for t, _ in client.calls if t == "ccc"]
        assert dead_calls == ["ccc"], "the dead ticker was re-requested"
        # And the rest of the market is unaffected by its neighbour's failure.
        assert [i.ticker for i in first] == ["KGH"]
        assert [i.ticker for i in second] == ["KGH"]

    def test_remembered_failure_never_outlives_the_configured_ttl(self) -> None:
        # With a zero-second history TTL the negative entry must expire at
        # once too — proving the failure is capped by the caller's TTL rather
        # than pinned open for NEGATIVE_CACHE_SECONDS.
        client = self._client()
        shared = TTLCache()

        def dead_calls() -> int:
            return len([t for t, _ in client.calls if t == "ccc"])

        async def run_twice() -> tuple[int, int]:
            await self._rank(client, shared, 0)
            after_first = dead_calls()
            await self._rank(client, shared, 0)
            return after_first, dead_calls()

        after_first, after_second = asyncio.run(run_twice())

        assert after_first >= 1
        assert after_second > after_first, "the failure outlived the configured TTL"

    def test_negative_window_is_shorter_than_the_daily_history_ttl(self) -> None:
        # A full-day negative TTL would keep a stock that failed once out of
        # the ranking until the next nightly refresh.
        assert NEGATIVE_CACHE_SECONDS < 24 * 60 * 60
