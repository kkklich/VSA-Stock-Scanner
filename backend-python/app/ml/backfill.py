"""The one-time history back-fill for training — plan §16, owner decision D2.

Extends a ticker's stored history back as far as the data provider reaches,
**without ever mixing two price scales**. The same rule as the nightly
ingest's corporate-action repair (``daily_ingest._check_and_repair``):

* the fresh download is compared with the stored bars it overlaps
  (``detect_adjustment``);
* if they agree, only the **older** bars are written — nothing already stored
  is touched;
* if they disagree (a split or dividend restated the stock since it was
  stored), the whole fresh series replaces the stored one **only when it
  reaches at least as far back** — otherwise nothing is written, because
  ``upsert_quotes`` never deletes and a short rebuild would leave the oldest
  bars on the old scale.

Only ``scripts/ml_backfill_history.py`` calls this, by hand, on the owner's
PC. The running app never does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.analysis.corporate_actions import detect_adjustment
from app.models import StooqDailyQuote

logger = logging.getLogger(__name__)

#: How far back to ask. The provider answers from the listing date onwards.
BACKFILL_FROM = date(1995, 1, 1)

#: Statuses after which a ticker counts as done (a re-run skips it).
DONE_STATUSES = frozenset({"extended", "unchanged", "rebuilt", "new"})


class _Client(Protocol):
    async def get_daily_history(
        self, ticker: str, from_date: date | None = None, to_date: date | None = None
    ) -> list[StooqDailyQuote]: ...


class _Repo(Protocol):
    async def get_quote_date_range(self, ticker: str) -> tuple[date, date] | None: ...

    async def get_quotes(
        self, ticker: str, from_date: date | None = None, to_date: date | None = None
    ) -> list[StooqDailyQuote]: ...

    async def upsert_quotes(self, ticker: str, quotes: list[StooqDailyQuote]) -> None: ...

    async def resync_rating_snapshot_closes(self, ticker: str) -> int: ...


@dataclass(frozen=True)
class BackfillResult:
    """What happened to one ticker.

    ``status``: ``new`` (nothing was stored; the whole series written),
    ``extended`` (older bars added), ``unchanged`` (the provider has nothing
    older), ``rebuilt`` (a corporate action: the full series replaced the
    stored one), ``refused`` (a corporate action, but the download does not
    reach back far enough to replace everything safely — nothing written),
    ``empty`` (the provider returned nothing), ``failed`` (the download raised).
    """

    ticker: str
    status: str
    stored_first: date | None
    fetched_first: date | None
    written: int
    detail: str = ""


async def backfill_ticker(
    ticker: str,
    client: _Client,
    repo: _Repo,
    *,
    start: date = BACKFILL_FROM,
) -> BackfillResult:
    """Extend one ticker's stored history back to ``start`` (or its listing)."""
    span = await repo.get_quote_date_range(ticker)
    stored_first = span[0] if span else None
    try:
        fetched = await client.get_daily_history(ticker, from_date=start)
    except Exception as exc:  # noqa: BLE001 — reported per ticker, never fatal
        return BackfillResult(ticker, "failed", stored_first, None, 0, str(exc))
    if not fetched:
        return BackfillResult(ticker, "empty", stored_first, None, 0)
    fetched = sorted(fetched, key=lambda q: q.date)
    fetched_first = fetched[0].date

    if span is None:
        await repo.upsert_quotes(ticker, fetched)
        return BackfillResult(ticker, "new", None, fetched_first, len(fetched))

    stored = await repo.get_quotes(ticker, span[0], None)
    check = detect_adjustment(stored, fetched)
    if check.adjusted:
        if fetched_first > span[0]:
            return BackfillResult(
                ticker,
                "refused",
                stored_first,
                fetched_first,
                0,
                f"restated ({check.reason}) but the download starts {fetched_first}, "
                f"after the first stored bar {span[0]} — writing would splice two scales",
            )
        await repo.upsert_quotes(ticker, fetched)
        try:
            await repo.resync_rating_snapshot_closes(ticker)
        except Exception:  # noqa: BLE001 — the bars matter; the chart price can wait
            logger.warning("Back-fill: could not re-scale %s rating snapshots.", ticker)
        return BackfillResult(
            ticker, "rebuilt", stored_first, fetched_first, len(fetched), str(check.reason)
        )

    older = [q for q in fetched if q.date < span[0]]
    if not older:
        return BackfillResult(ticker, "unchanged", stored_first, fetched_first, 0)
    await repo.upsert_quotes(ticker, older)
    return BackfillResult(ticker, "extended", stored_first, fetched_first, len(older))
