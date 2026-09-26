"""Market overview: breadth and the biggest rating movers.

Builds the data behind ``GET /api/stocks/market-overview`` — the top-down read
of the Dashboard ("is the market leaning bullish or bearish today, and which
stocks changed their mind the most?").

It is a single pass over ranking rows that already exist: every row carries the
verdict, the rating and its day-over-day change, the price change and the
52-week flags, so nothing new is downloaded, stored or computed per stock, and
the overview can never disagree with the list beneath it. ``ratingChange`` is
the rating *after* the newest session minus the rating *before* it, both on the
same settings, which is exactly what a "biggest movers" list needs.

Breadth is a count and nothing more. It is deliberately not blended into a
single "market score": a verdict split says how many stocks lean each way, and
whether that is early or late in a move is not something a tally can know.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.models import MarketBreadth, MarketOverviewResponse, RatingMover, StockRankingItem

# How many stocks each movers list holds.
DEFAULT_MOVERS = 5

_BULLISH = ("Strong Buy", "Buy")
_BEARISH = ("Sell", "Strong Sell")


def compute_breadth(rows: Sequence[StockRankingItem]) -> MarketBreadth:
    """Tally the ranked stocks: verdicts, price breadth, rating momentum."""
    total = len(rows)
    if total == 0:
        return MarketBreadth()

    counts = {"Strong Buy": 0, "Buy": 0, "Hold": 0, "Sell": 0, "Strong Sell": 0}
    for row in rows:
        # An unexpected verdict string still counts toward ``total`` but lands
        # in no bucket, rather than raising in the middle of a request.
        if row.last_signal in counts:
            counts[row.last_signal] += 1

    bullish = sum(counts[v] for v in _BULLISH)
    bearish = sum(counts[v] for v in _BEARISH)
    return MarketBreadth(
        total=total,
        strong_buy=counts["Strong Buy"],
        buy=counts["Buy"],
        hold=counts["Hold"],
        sell=counts["Sell"],
        strong_sell=counts["Strong Sell"],
        bullish_pct=round(100 * bullish / total, 1),
        bearish_pct=round(100 * bearish / total, 1),
        average_rating=round(sum(r.current_rating for r in rows) / total, 1),
        advancers=sum(1 for r in rows if r.price_change_pct > 0),
        decliners=sum(1 for r in rows if r.price_change_pct < 0),
        unchanged=sum(1 for r in rows if r.price_change_pct == 0),
        rating_up=sum(1 for r in rows if r.rating_change > 0),
        rating_down=sum(1 for r in rows if r.rating_change < 0),
        new_52w_highs=sum(1 for r in rows if r.is_new_52w_high),
        new_52w_lows=sum(1 for r in rows if r.is_new_52w_low),
    )


def _mover(row: StockRankingItem) -> RatingMover:
    return RatingMover(
        ticker=row.ticker,
        name=row.name,
        market=row.market,
        currency=row.currency,
        last_session=row.last_session,
        last_price=row.last_price,
        price_change_pct=row.price_change_pct,
        previous_rating=row.current_rating - row.rating_change,
        current_rating=row.current_rating,
        rating_change=row.rating_change,
        last_signal=row.last_signal,
    )


def top_movers(
    rows: Sequence[StockRankingItem], *, limit: int = DEFAULT_MOVERS
) -> tuple[list[RatingMover], list[RatingMover]]:
    """The stocks whose rating rose most and fell most: ``(up, down)``.

    Only stocks that actually moved are listed. Equal moves are ordered by the
    resulting rating (the better-rated stock first among risers, the worse-rated
    first among fallers) and then by ticker, so the answer never depends on the
    order the rows arrived in.
    """
    risers = sorted(
        (r for r in rows if r.rating_change > 0),
        key=lambda r: (-r.rating_change, -r.current_rating, r.ticker),
    )
    fallers = sorted(
        (r for r in rows if r.rating_change < 0),
        key=lambda r: (r.rating_change, r.current_rating, r.ticker),
    )
    return [_mover(r) for r in risers[:limit]], [_mover(r) for r in fallers[:limit]]


def build_market_overview(
    rows: Sequence[StockRankingItem], *, market: str, limit: int = DEFAULT_MOVERS
) -> MarketOverviewResponse:
    """The breadth tally and both movers lists for one market's ranking rows."""
    up, down = top_movers(rows, limit=limit)
    sessions = [r.last_session for r in rows if r.last_session is not None]
    return MarketOverviewResponse(
        as_of=max(sessions) if sessions else None,
        market=market,
        breadth=compute_breadth(rows),
        movers_up=up,
        movers_down=down,
    )
