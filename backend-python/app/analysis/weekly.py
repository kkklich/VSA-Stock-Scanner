"""Multi-timeframe (weekly) VSA analysis.

VSA analysts confirm a daily signal by checking that the weekly chart tells the
same story — strength on the daily that also shows on the weekly is far more
trustworthy than strength the higher timeframe contradicts (Master the Markets
stresses reading a signal against the larger background). This module resamples
a stock's stored daily bars into weekly candles and runs the *same* VSA engine
on them, then reports whether the weekly verdict confirms, conflicts with, or is
neutral toward the daily one.

No new data source is needed: the weekly bars are aggregated from the daily
OHLCV the app already stores.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from app.analysis.vsa import (
    VsaConfig,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.models import StooqDailyQuote

# Minimum number of weekly bars before a weekly reading is trusted. The VSA
# engine needs a full rolling context (default lookback 20) plus a warm-up
# buffer, so ~25 weekly bars is the floor; 30 (≈ seven months of trading) leaves
# a little scanning room beyond that. Below this the stock is a recent listing —
# or the DB has too little history — and no weekly badge is shown rather than a
# misleading "neutral" read from three weekly candles. The ranking fetches well
# over a year per ticker (CONTEXT_HISTORY_DAYS), so an established stock clears
# this comfortably.
_MIN_WEEKLY_BARS = 30

# The most weekly bars the weekly read looks at: one year of weekly candles,
# the higher-timeframe background a VSA trader actually reads.
#
# Pinned here rather than "however many the caller happened to fetch", because
# the caller's fetch window exists for unrelated reasons (the 52-week context,
# the relative-strength rank) and has already been widened once. Without this
# cap, widening it again would silently move every weekly rating in the app —
# a fetch-window tweak must not be able to change what the weekly chart says.
_MAX_WEEKLY_BARS = 52

# Half-life used when decaying weekly signals into a rating and a verdict.
#
# The VSA engine's default is 30 CALENDAR DAYS, and that number was chosen for
# daily bars — roughly a month of trading, about 21 sessions of memory. But the
# decay is applied to whatever bars it is handed, and on weekly candles 30
# calendar days is only 4.3 *bars*. Measured on this app's own data, a weekly
# Strong Buy kept 85% of its weight after one week, 27% after eight (by which
# point the badge had already faded to "Hold") and 1.5% after twenty-six. The
# weekly view was therefore looking back no further than the daily one and
# almost always answering "neutral" — the exact opposite of what a
# higher-timeframe confirmation is for, and the reason 105 of 126 ranked stocks
# came back neutral when the feature shipped.
#
# Multiplying by 7 states the intent directly: one WEEK of weekly bars now
# decays like one DAY of daily bars. The weekly read remembers ~30 weekly bars
# (about seven months) instead of a month and a half.
#
# ``verdict_from_signals`` must be given the SAME value as ``compute_rating``
# (its own docstring says so): both read the one decayed net score, and passing
# a custom half-life to only one of them is how a "rating 90 with a Sell badge"
# contradiction gets born.
_WEEKLY_HALF_LIFE_DAYS = 30 * 7  # 210 calendar days = 30 weekly bars

# Friday, in Python's Monday-is-0 weekday numbering: the last session of a
# normal GPW week.
_FRIDAY = 4

# Verdict → direction, shared with the agreement logic below.
_BULLISH_VERDICTS = frozenset({"Strong Buy", "Buy"})
_BEARISH_VERDICTS = frozenset({"Strong Sell", "Sell"})


@dataclass(frozen=True)
class WeeklyView:
    """The weekly-timeframe VSA read of one stock.

    ``available`` is False when the stored history is too short to form enough
    weekly bars to analyse; ``rating``/``verdict`` are then None.
    """

    available: bool
    rating: int | None = None
    verdict: str | None = None
    # How many weekly bars the daily history resampled to (diagnostic).
    weekly_bars: int = 0


def resample_weekly(bars: Sequence[StooqDailyQuote]) -> list[StooqDailyQuote]:
    """Aggregate chronological daily OHLCV bars into weekly candles.

    Bars are grouped by ISO (year, week) — Monday-to-Sunday weeks, so a week
    that straddles a year boundary stays one bar. Each weekly candle takes the
    week's first open, the max high, the min low, the last close, the summed
    volume, and is dated to the week's last trading session. The most recent
    week may be partial (the week still in progress); that is the correct
    "forming" weekly bar and is kept.

    The input need not be pre-sorted — it is sorted by date defensively — but
    Decimal/int types are preserved so the result feeds the VSA engine exactly
    like real daily bars.
    """
    if not bars:
        return []

    ordered = sorted(bars, key=lambda b: b.date)
    groups: dict[tuple[int, int], list[StooqDailyQuote]] = {}
    order: list[tuple[int, int]] = []
    for b in ordered:
        iso = b.date.isocalendar()
        key = (iso.year, iso.week)
        bucket = groups.get(key)
        if bucket is None:
            groups[key] = [b]
            order.append(key)
        else:
            bucket.append(b)

    weekly: list[StooqDailyQuote] = []
    for key in order:
        week = groups[key]  # chronological within the week (input was sorted)
        weekly.append(
            StooqDailyQuote(
                date=week[-1].date,
                open=week[0].open,
                high=max(q.high for q in week),
                low=min(q.low for q in week),
                close=week[-1].close,
                volume=sum(q.volume for q in week),
            )
        )
    return weekly


def trailing_week_is_complete(daily: Sequence[StooqDailyQuote]) -> bool:
    """Has the last ISO week in ``daily`` finished trading?

    Answered from the daily bars themselves rather than from the clock, because
    the clock does not know about holidays, and a wrong guess here is expensive
    (see ``compute_weekly_view``). Two independent cues, and either one is
    enough to call the week finished:

      * its last session is a **Friday** — the week is over by definition; or
      * it already holds **as many sessions as this stock's typical week** —
        which covers a Friday holiday (a Monday-to-Thursday week that really is
        complete) and stocks so thinly traded that their normal week is three
        sessions long.

    Only when *neither* holds is the week still forming. Requiring both (i.e.
    "Friday AND a full session count") would throw away every genuinely complete
    holiday-shortened week, and the artefact this guards against is a bar that
    is small *relative to the stock's own weekly norm* — which is exactly what
    the session-count cue measures.

    A series with only one week in it has nothing to compare against, so it is
    treated as forming.
    """
    if not daily:
        return False

    ordered = sorted(daily, key=lambda b: b.date)
    sessions_per_week: OrderedDict[tuple[int, int], int] = OrderedDict()
    for bar in ordered:
        iso = bar.date.isocalendar()
        key = (iso.year, iso.week)
        sessions_per_week[key] = sessions_per_week.get(key, 0) + 1

    # Friday (or later, defensively — a weekend print would still end the week).
    if ordered[-1].date.weekday() >= _FRIDAY:
        return True

    keys = list(sessions_per_week)
    earlier = keys[:-1]
    if not earlier:
        return False
    typical = median(sessions_per_week[k] for k in earlier)
    return sessions_per_week[keys[-1]] >= typical


def compute_weekly_view(
    quotes: Sequence[StooqDailyQuote],
    config: VsaConfig | None = None,
) -> WeeklyView:
    """Run the VSA engine on the weekly resampling of ``quotes``.

    Uses the same ``config`` (the user's Scanner settings) as the daily scan, so
    the higher timeframe is judged by identical rules — the lookback of 20 simply
    becomes 20 *weeks*. The rating and verdict are keyed to the last weekly bar's
    date (no wall-clock decay), mirroring the daily path.

    Two things separate this from a plain ``resample_weekly`` + ``detect_signals``:

    **The forming week is dropped.** ``resample_weekly`` keeps the week still in
    progress, which is right for a chart — the user wants to see today — and
    wrong for detection. A part-built weekly bar has a fraction of a real week's
    volume and range (measured on a Monday: 0.20× the 20-week average volume,
    0.16× the average spread), and "volume below 0.7× average" plus "spread
    below 0.7× average" are the *hard gates* on No Demand and the Successful
    Test. Left in, that bar manufactures those two signals out of nothing but
    its own incompleteness — and since the nightly job runs at 18:00 on
    weekdays, four runs in five would analyse one.

    **The window is capped** at ``_MAX_WEEKLY_BARS``, so the weekly read depends
    only on this module, not on how much history the caller happened to fetch.
    """
    weekly = resample_weekly(quotes)

    # Drop the trailing bar while its week is still being built.
    if weekly and not trailing_week_is_complete(quotes):
        weekly = weekly[:-1]

    # One year of weekly candles; older ones would carry decayed weight anyway
    # and only make the answer depend on the caller's fetch window.
    weekly = weekly[-_MAX_WEEKLY_BARS:]

    # ``weekly_bars`` reports what was actually ANALYSED, so a caller reading it
    # is not told about a bar the verdict never saw.
    if len(weekly) < _MIN_WEEKLY_BARS:
        return WeeklyView(available=False, weekly_bars=len(weekly))

    signals = detect_signals(weekly, config)
    as_of = weekly[-1].date
    rating = compute_rating(signals, as_of, _WEEKLY_HALF_LIFE_DAYS)
    verdict, _ = verdict_from_signals(signals, as_of, _WEEKLY_HALF_LIFE_DAYS)
    return WeeklyView(
        available=True, rating=rating, verdict=verdict, weekly_bars=len(weekly)
    )


def _direction(verdict: str) -> int:
    """+1 bullish, -1 bearish, 0 neutral (Hold / unknown)."""
    if verdict in _BULLISH_VERDICTS:
        return 1
    if verdict in _BEARISH_VERDICTS:
        return -1
    return 0


def weekly_agreement(daily_verdict: str, weekly_verdict: str) -> str:
    """How the weekly verdict relates to the daily one.

    ``"confirms"`` when both lean the same non-neutral way (both bullish or both
    bearish — the case a VSA trader wants to see before acting), ``"conflicts"``
    when they lean opposite ways, and ``"neutral"`` when either side is Hold (the
    higher timeframe neither backs nor contradicts the daily call).
    """
    d = _direction(daily_verdict)
    w = _direction(weekly_verdict)
    if d != 0 and w != 0:
        return "confirms" if d == w else "conflicts"
    return "neutral"
