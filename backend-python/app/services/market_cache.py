"""Dropping the cached data of some markets only.

The nightly runs refresh markets separately (Europe and the GPW at 18:00
Warsaw, the US at 17:15 New York), so a run must only throw away what was
built from the markets it refreshed. Clearing everything at 23:15 would make
the next GPW visitor pay for a full recomputation of data that did not change.

This module is the one place that knows how the two process caches name their
entries (``app/dependencies.py``):

* **history cache** — per-ticker data, the ticker being the second part of the
  key: ``history:{ticker}:…``, ``backtest-history:{ticker}:…``,
  ``intraday:{ticker}:…``, ``capex-miss:{ticker}`` — or the third for
  ``resp:history:{ticker}:…``;
* **ranking cache** — whole screens, the market scope being the second part —
  ``ranking:{market}:…``, ``heatmap:{market}…``, ``volume-surge:{market}:…``,
  ``method-backtest:{market}:…``, ``capex:{market}:…`` — or the third for
  ``scanner:stats:{market}…``. A scope of ``all`` pools every market, so any
  refresh invalidates it.

A key this module cannot read is dropped: keeping a stale entry costs a wrong
answer, dropping a good one only costs a recomputation.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.markets import enabled_markets, market_of, normalize_ticker
from app.services.cache import TTLCache

_ALL_SCOPE = "all"


def history_key_ticker(key: str) -> str | None:
    """The ticker a history-cache key belongs to, or ``None`` if unreadable."""
    parts = key.split(":")
    index = 2 if parts[0] == "resp" else 1
    if len(parts) <= index:
        return None
    return normalize_ticker(parts[index])


def ranking_key_scope(key: str) -> str | None:
    """The market scope of a ranking-cache key (``gpw``, ``all``…), or ``None``."""
    parts = key.split(":")
    index = 2 if parts[0] == "scanner" else 1
    return parts[index] if len(parts) > index else None


def invalidate_markets(
    market_ids: Iterable[str],
    *caches: tuple[TTLCache, str],
) -> None:
    """Drop what the given markets' data fed, from each ``(cache, kind)``.

    ``kind`` is ``"history"`` or ``"ranking"``. When the markets cover every
    market this deployment serves, the caches are simply cleared.
    """
    refreshed = set(market_ids)
    everything = refreshed >= {m.id for m in enabled_markets()}

    def history_match(key: str) -> bool:
        ticker = history_key_ticker(key)
        return ticker is None or market_of(ticker).id in refreshed

    def ranking_match(key: str) -> bool:
        scope = ranking_key_scope(key)
        return scope is None or scope == _ALL_SCOPE or scope in refreshed

    for cache, kind in caches:
        if everything:
            cache.clear()
        elif kind == "history":
            cache.invalidate(history_match)
        elif kind == "ranking":
            cache.invalidate(ranking_match)
        else:
            raise ValueError(f"Unknown cache kind {kind!r}.")
