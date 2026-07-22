"""Price-return arithmetic shared by the heatmap and the fundamentals card.

Two primitives (``pct_change``, ``baseline_close``) and one aggregate
(``compute_price_returns``). All of it is pure — a chronological list of bars
in, percentages out — so it is trivially unit-testable and does no I/O.

The rule that matters: a horizon is reported only when the stored history
actually reaches back far enough. A baseline bar may be at most **twice** the
horizon old, so a gappy or recently listed series yields ``None`` instead of a
change quietly mislabelled as "1Y". "MAX" is the exception — it always uses
the oldest stored bar, and reports that bar's date so the UI can say *since
when*.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models import PriceReturns, StooqDailyQuote


def pct_change(last_close: float, baseline: float) -> float | None:
    """Percentage change from ``baseline`` to ``last_close`` (2 decimals)."""
    if baseline <= 0:
        return None
    return round((last_close - baseline) / baseline * 100, 2)


def baseline_close(
    quotes: list[StooqDailyQuote], cutoff: date, oldest: date
) -> float | None:
    """Close of the newest bar dated within ``[oldest, cutoff]`` (else None).

    The ``oldest`` floor keeps gappy histories honest: without it a "1M"
    change could silently be computed against a bar from many months ago.
    """
    for q in reversed(quotes):
        if q.date <= cutoff:
            return float(q.close) if q.date >= oldest else None
    return None


def _horizon_change(
    quotes: list[StooqDailyQuote], last_close: float, last_day: date, days: int
) -> float | None:
    """Change over ``days`` calendar days back from the last bar."""
    base = baseline_close(
        quotes[:-1], last_day - timedelta(days=days), last_day - timedelta(days=days * 2)
    )
    return pct_change(last_close, base) if base else None


def compute_price_returns(quotes: list[StooqDailyQuote]) -> PriceReturns:
    """Trailing price returns (YTD / 1Y / 3Y / 5Y / MAX) for a bar list.

    ``quotes`` must be chronological (oldest first). Every field is ``None``
    when the history does not reach back far enough — except ``max_pct`` /
    ``max_from_date``, which describe the full stored history and are present
    whenever there are at least two bars.

    These are pure **price** returns: they ignore dividends, so for a high-
    yielding stock the true total return is higher than the number shown.
    """
    if len(quotes) < 2:
        return PriceReturns()

    last = quotes[-1]
    last_close = float(last.close)
    last_day = last.date

    # Year to date: the last close of the PREVIOUS year is the baseline, so
    # the figure means "how much this stock has moved so far this year".
    # Allowed to be up to ~2 weeks stale (year-end holidays close the GPW).
    ytd_base = baseline_close(
        quotes[:-1], date(last_day.year, 1, 1), date(last_day.year - 1, 12, 15)
    )

    return PriceReturns(
        ytd_pct=pct_change(last_close, ytd_base) if ytd_base else None,
        y1_pct=_horizon_change(quotes, last_close, last_day, 365),
        y3_pct=_horizon_change(quotes, last_close, last_day, 365 * 3),
        y5_pct=_horizon_change(quotes, last_close, last_day, 365 * 5),
        max_pct=pct_change(last_close, float(quotes[0].close)),
        max_from_date=quotes[0].date,
    )
