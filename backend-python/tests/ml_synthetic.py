"""Synthetic bars for the AI-layer tests (``tests/test_ml_*.py``)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from app.models import StooqDailyQuote


def bar(d: date, o: float, h: float, lo: float, c: float, v: int = 1_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(round(o, 4))),
        high=Decimal(str(round(h, 4))),
        low=Decimal(str(round(lo, 4))),
        close=Decimal(str(round(c, 4))),
        volume=v,
    )


def weekdays(start: date, count: int) -> list[date]:
    """``count`` consecutive Monday–Friday dates from ``start``."""
    out: list[date] = []
    d = start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def random_walk_bars(
    count: int,
    *,
    seed: int = 1,
    start: date = date(2020, 1, 6),
    price: float = 50.0,
    drift: float = 0.0003,
    vol: float = 0.02,
) -> list[StooqDailyQuote]:
    """A plausible daily series: log-normal closes, ranges and volume spikes."""
    rng = np.random.default_rng(seed)
    out: list[StooqDailyQuote] = []
    close = price
    for d in weekdays(start, count):
        ret = rng.normal(drift, vol)
        open_ = close * (1 + rng.normal(0, vol / 4))
        close = max(0.5, close * float(np.exp(ret)))
        high = max(open_, close) * (1 + abs(rng.normal(0, vol / 2)))
        low = min(open_, close) * (1 - abs(rng.normal(0, vol / 2)))
        volume = int(rng.lognormal(10, 0.5) * (3 if rng.random() < 0.05 else 1))
        out.append(bar(d, open_, high, low, close, volume))
    return out
