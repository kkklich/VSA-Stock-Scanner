"""Today's prices while an exchange is open — downloaded every hour.

Every analysis in the app runs on FINISHED sessions. A daily bar for a session
still trading carries a fraction of the day's volume, and unusually low volume
is exactly what VSA reads as a signal (No Demand, the Test), so the ingest
refuses such a bar (``Market.session_is_final``) and the day's final bar is
stored by the evening run. The price of the finished analysis is therefore
yesterday's close all day: at 14:00 the dashboard used to show nothing of the
session in progress.

This service adds the session in progress WITHOUT touching the analysis. At
every full hour (``STOCKPILOT_LIVE_PRICES_INTERVAL_MINUTES``) it asks, for each
served market that is trading at that moment (``Market.session_in_progress``),
for every tracked stock's session so far — today's price, range and volume —
and keeps the answers in memory. The endpoints lay them over what they already
serve (``overlay_row``, ``overlay_tile``):

* the ranking rows, the heatmap tiles and the stock page show today's price and
  today's change so far, and carry a ``live`` object saying what it is and when
  it is from;
* every rating, signal, method score and chart marker stays exactly what the
  finished sessions give. Nothing half-finished is written to the database.
  When the evening run stores the day's final bar, the finished data covers
  that session and the live price is simply no longer attached.

In memory on purpose: the API runs as one process (the scheduler and every
cache already assume so), a live price is worthless once the day's final bar is
stored, and a restart during market hours is followed by an immediate download
(``app/main.py``), so there is nothing worth persisting.

Every run is recorded in the action log as ``job.live`` — started, then
finished or failed with what it did — like the nightly jobs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol

from app.analysis.returns import pct_change
from app.markets import MARKETS, get_market, market_of
from app.models import GpwCompany, HeatmapItem, LivePrice, StockRankingItem
from app.services.action_log import (
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
    OUTCOME_SKIPPED,
    OUTCOME_STARTED,
    ActionLogService,
)
from app.services.yahoo_finance_client import SessionQuote

logger = logging.getLogger(__name__)

#: The scheduler's id for the recurring job, and its action-log name.
JOB_ID = "live_prices"
ACTION = "job.live"

# Downloads in flight at once. The Yahoo client lets five through for the whole
# process; keeping this run to three leaves two for the people using the app
# while it works — a stock page opened at 14:00 must not queue behind three
# hundred background downloads.
_MAX_CONCURRENT = 3

# A market's largest companies are asked first. When not one of them has a bar
# for today, the exchange is not trading today (a public holiday — the app keeps
# no holiday calendar) or not yet (the first minutes, while Yahoo's ~15-minute
# delay on European quotes has nothing to show), and the other few hundred
# downloads are skipped until the next run. The biggest names trade from the
# opening minutes of every session, so silence from all of them is no accident.
_PROBES = 3

# A run that lost more than this share of its stocks is reported as failed —
# the same line the nightly ingest draws (``refresh_service.ingest_outcome``).
_FAILURE_SHARE = 0.10
# How many failing tickers a run names in its log entry; the rest are counted.
_MAX_REPORTED_FAILURES = 20

# Cadences that divide an hour, so every run lands on the same minutes of every
# hour ("at every full hour", "at :00 and :30").
_VALID_INTERVALS = (5, 10, 15, 20, 30, 60)
_DEFAULT_INTERVAL = 60


class SessionQuoteSource(Protocol):
    """Where session quotes come from — the Yahoo client, or a test's fake."""

    async def get_session_quote(self, ticker: str) -> SessionQuote: ...


def cron_minutes(interval: int) -> str:
    """The cron ``minute`` field for a cadence in minutes ("0", "*/30" …).

    A cadence that does not divide an hour would drift across the hours
    (a 45-minute one fires at :00, :45, then :30 of the next hour …), which no
    reader of "updated every 45 minutes" expects; it falls back to hourly.
    """
    if interval not in _VALID_INTERVALS:
        logger.warning(
            "STOCKPILOT_LIVE_PRICES_INTERVAL_MINUTES=%s does not divide an hour "
            "(use one of %s) — live prices run every %d minutes instead.",
            interval,
            ", ".join(str(v) for v in _VALID_INTERVALS),
            _DEFAULT_INTERVAL,
        )
        interval = _DEFAULT_INTERVAL
    return "0" if interval == 60 else f"*/{interval}"


def live_price_from(quote: SessionQuote, fetched_at: datetime) -> LivePrice | None:
    """The live price a session download describes, or ``None``.

    Only ever called for a market whose largest stocks DID trade today (see
    ``_PROBES``), so a stock with no bar for today has simply not traded yet:
    its price today is still the previous close, its change 0.00% and its
    volume zero. Saying so beats leaving the row on yesterday's figures —
    sorted by change, a stock that has not traded since yesterday's +8% would
    otherwise sit among today's biggest movers. ``None`` when there is not even
    a previous close to state it from.
    """
    as_of = quote.last_trade_at or fetched_at
    previous = quote.previous_close
    bar = quote.bar
    if bar is None:
        if previous is None:
            return None
        return LivePrice(
            session_date=quote.today,
            price=previous,
            open=previous,
            high=previous,
            low=previous,
            volume=0,
            previous_close=previous,
            change_pct=0.0,
            as_of=as_of,
            fetched_at=fetched_at,
        )
    return LivePrice(
        session_date=quote.today,
        price=bar.close,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        volume=bar.volume,
        previous_close=previous,
        change_pct=pct_change(bar.close, previous) if previous else None,
        as_of=as_of,
        fetched_at=fetched_at,
    )


def _supersedes(live: LivePrice | None, last_session: date | None) -> bool:
    """Is ``live`` a session newer than the finished data it would sit on?

    A payload whose session is unknown is left alone: attaching today's price
    to data of an unknown day would be a guess presented as a fact.
    """
    return (
        live is not None
        and last_session is not None
        and live.session_date > last_session
    )


def overlay_row(row: StockRankingItem, live: LivePrice | None) -> StockRankingItem:
    """A ranking row showing today's price, when ``live`` is newer than it.

    The price, the change and the sparkline's last point become today's; the
    rating, the signal, the methods and ``last_session`` stay the finished
    session's. Returns a copy — the cached row is shared by every request.
    """
    if not _supersedes(live, row.last_session):
        return row
    assert live is not None  # narrowed by _supersedes
    update: dict[str, object] = {"live": live, "last_price": live.price}
    if live.change_pct is not None:
        update["price_change_pct"] = live.change_pct
    if row.sparkline:
        # Same length as before: the oldest close makes way for today's price.
        update["sparkline"] = [*row.sparkline[1:], live.price]
    return row.model_copy(update=update)


def overlay_tile(item: HeatmapItem, live: LivePrice | None) -> HeatmapItem:
    """A heatmap tile measured from today's price, when ``live`` is newer.

    Each change is restated from the same reference close the finished tile
    used (kept on the tile, never serialised), so 1M/1Y/MAX stay the same
    horizons, only now ending at today's price. 1D is today's change so far.
    """
    if not _supersedes(live, item.last_session):
        return item
    assert live is not None  # narrowed by _supersedes
    price = live.price

    def restated(baseline: float | None) -> float | None:
        return pct_change(price, baseline) if baseline else None

    change_1d = (
        live.change_pct
        if live.change_pct is not None
        else pct_change(price, item.last_price)
    )
    return item.model_copy(
        update={
            "live": live,
            "last_price": price,
            "change_1d": change_1d,
            "change_1m": restated(item.baseline_1m),
            "change_1y": restated(item.baseline_1y),
            "change_max": restated(item.baseline_max),
        }
    )


@dataclass(slots=True)
class LiveRunStats:
    """What one live-price run did — the raw material of its log entry."""

    trigger: str
    # Markets trading by the clock when the run started.
    markets: list[str] = field(default_factory=list)
    # Of those, markets whose largest stocks had no bar for today: a holiday,
    # or the first minutes of the session. Skipped until the next run.
    quiet_markets: list[str] = field(default_factory=list)
    # Stocks the run asked about (on the markets it did not skip).
    companies: int = 0
    # Stocks with a bar for today — a real price from today's session.
    updated: int = 0
    # Stocks that have not traded yet today: shown at the previous close, 0%.
    not_traded: int = 0
    # Stocks whose download failed; they keep their last live price, if any.
    failed: int = 0
    duration_ms: float = 0.0
    failures: list[str] = field(default_factory=list)

    def as_detail(self) -> dict:
        """The JSON-friendly form stored in an action-log entry."""
        return {
            "trigger": self.trigger,
            "markets": list(self.markets),
            "quietMarkets": list(self.quiet_markets),
            "companies": self.companies,
            "updated": self.updated,
            "notTraded": self.not_traded,
            "failed": self.failed,
            "failures": self.failures[:_MAX_REPORTED_FAILURES],
        }


def run_outcome(stats: LiveRunStats) -> str:
    """Did the run work? — ``finished`` or ``failed`` (see ``ingest_outcome``).

    A handful of failing downloads out of hundreds is provider noise and is
    only counted; the run is failed when it produced no price at all, or when
    more than one stock in ten could not be downloaded.
    """
    if stats.companies == 0:
        return OUTCOME_FINISHED
    if stats.updated + stats.not_traded == 0:
        return OUTCOME_FAILED
    if stats.failed > stats.companies * _FAILURE_SHARE:
        return OUTCOME_FAILED
    return OUTCOME_FINISHED


class LivePriceService:
    """Downloads and keeps today's prices for the markets that are trading."""

    def __init__(
        self,
        companies: Sequence[GpwCompany],
        client: SessionQuoteSource,
        action_log: ActionLogService | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        max_concurrent: int = _MAX_CONCURRENT,
    ) -> None:
        self._companies = list(companies)
        self._client = client
        # Optional, like everywhere in the pipeline: tests build the service
        # without a log.
        self._action_log = action_log
        # The current moment — injectable so tests can stand mid-session.
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._max_concurrent = max(1, max_concurrent)
        # Latest live price per ticker (lower-case).
        self._prices: dict[str, LivePrice] = {}
        # When each market's prices were last downloaded.
        self._market_fetched: dict[str, datetime] = {}
        self._running = asyncio.Lock()
        self._task: asyncio.Task | None = None
        #: When the last run that produced a price finished downloading.
        self.last_update_at: datetime | None = None

    # ── Reading ───────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running.locked()

    def get(self, ticker: str) -> LivePrice | None:
        """Today's live price for a ticker, or ``None``.

        A price from an earlier day is never returned: once the date has turned
        on the exchange's calendar it describes a session that is over, whose
        final bar the evening run stores.
        """
        key = ticker.strip().casefold()
        entry = self._prices.get(key)
        if entry is None:
            return None
        try:
            market = market_of(key)
        except ValueError:
            return None
        if entry.session_date != market.local_date(self._clock()):
            return None
        return entry

    def overlay_rows(self, rows: list[StockRankingItem]) -> list[StockRankingItem]:
        """Ranking rows with today's prices laid over them (see ``overlay_row``)."""
        if not self._prices:
            return rows
        return [overlay_row(row, self.get(row.ticker)) for row in rows]

    def overlay_tiles(self, items: list[HeatmapItem]) -> list[HeatmapItem]:
        """Heatmap tiles with today's prices laid over them (see ``overlay_tile``)."""
        if not self._prices:
            return items
        return [overlay_tile(item, self.get(item.ticker)) for item in items]

    def market_times(self) -> dict[str, datetime]:
        """When each market's live prices were downloaded — today's runs only."""
        now = self._clock()
        times: dict[str, datetime] = {}
        for market in MARKETS:
            at = self._market_fetched.get(market.id)
            if at is not None and market.local_date(at) == market.local_date(now):
                times[market.id] = at
        return times

    def due_markets(self, markets: Sequence[str] | None = None) -> list[str]:
        """The markets (of ``markets``, default all tracked) trading right now."""
        now = self._clock()
        present = {market_of(c.ticker).id for c in self._companies}
        wanted = set(markets) if markets is not None else present
        return [
            m.id
            for m in MARKETS
            if m.id in present and m.id in wanted and m.session_in_progress(now)
        ]

    # ── Running ───────────────────────────────────────────────────────────────

    def start(self, markets: Sequence[str] | None = None, trigger: str = "manual") -> bool:
        """Run in the background; ``False`` when a run is already going."""
        if self.is_running:
            return False
        self._task = asyncio.create_task(
            self.run(markets=markets, trigger=trigger), name="live_prices"
        )
        return True

    async def run_scheduled(self) -> None:
        """The scheduler's entry point: every served market trading right now."""
        await self.run(trigger="scheduled")

    async def run(
        self, markets: Sequence[str] | None = None, trigger: str = "scheduled"
    ) -> LiveRunStats | None:
        """Download today's prices for the markets trading now.

        Returns what the run did, or ``None`` when another run was already in
        progress. With no market trading — nights, weekends, or a refresh of
        markets that have closed — it returns at once without a log entry: the
        job fires every hour of the day, and "nothing to do at 03:00" is not
        news.
        """
        due = self.due_markets(markets)
        if not due:
            return LiveRunStats(trigger=trigger)
        if self._running.locked():
            logger.info("Live prices: a run is already in progress — skipping.")
            self._log(OUTCOME_SKIPPED, detail={"trigger": trigger, "reason": "already running"})
            return None
        async with self._running:
            return await self._do_run(due, trigger)

    async def _do_run(self, due: list[str], trigger: str) -> LiveRunStats:
        started = time.perf_counter()
        stats = LiveRunStats(trigger=trigger, markets=list(due))
        self._log(OUTCOME_STARTED, detail={"trigger": trigger, "markets": list(due)})
        try:
            semaphore = asyncio.Semaphore(self._max_concurrent)
            for market_id in due:
                await self._run_market(market_id, semaphore, stats)
        except Exception as exc:  # noqa: BLE001 — a background job must not crash the app
            stats.duration_ms = (time.perf_counter() - started) * 1000.0
            logger.exception("Live prices: the run failed.")
            self._log(
                OUTCOME_FAILED,
                duration_ms=stats.duration_ms,
                detail={**stats.as_detail(), "error": f"{type(exc).__name__}: {exc}"[:500]},
            )
            return stats

        stats.duration_ms = (time.perf_counter() - started) * 1000.0
        outcome = run_outcome(stats)
        self._log(outcome, duration_ms=stats.duration_ms, detail=stats.as_detail())
        log = logger.warning if outcome == OUTCOME_FAILED else logger.info
        log(
            "Live prices (%s): %d updated, %d not traded yet today, %d failed%s — %.1f s.",
            ", ".join(due),
            stats.updated,
            stats.not_traded,
            stats.failed,
            f"; not trading yet: {', '.join(stats.quiet_markets)}" if stats.quiet_markets else "",
            stats.duration_ms / 1000.0,
        )
        return stats

    async def _run_market(
        self, market_id: str, semaphore: asyncio.Semaphore, stats: LiveRunStats
    ) -> None:
        market = get_market(market_id)
        assert market is not None  # ids come from the registry
        companies = [c for c in self._companies if market_of(c.ticker).id == market_id]
        if not companies:
            return
        fetched_at = self._clock()
        today = market.local_date(fetched_at)

        async def download(
            company: GpwCompany,
        ) -> tuple[GpwCompany, SessionQuote | None, Exception | None]:
            async with semaphore:
                try:
                    return company, await self._client.get_session_quote(company.ticker), None
                except Exception as exc:  # noqa: BLE001 — counted, never fatal
                    return company, None, exc

        # Largest first (unknown caps last), so the probes are the names that
        # trade from the opening minutes.
        ordered = sorted(companies, key=lambda c: -(c.market_cap or 0))
        probes, rest = ordered[:_PROBES], ordered[_PROBES:]
        results = list(await asyncio.gather(*(download(c) for c in probes)))
        answered = [quote for _, quote, error in results if error is None and quote]

        if not answered:
            # Every probe failed: the provider is not answering. Asking about
            # the rest would only queue a few hundred more failures (each
            # possibly a timeout) — try again at the next run instead.
            stats.companies += len(companies)
            stats.failed += len(companies)
            stats.failures.extend(c.ticker for c in companies)
            logger.warning(
                "Live prices: no answer for %s's largest stocks (%s) — skipping "
                "the market until the next run.",
                market_id,
                "; ".join(f"{c.ticker}: {e}" for c, _, e in results)[:300],
            )
            return
        if not any(quote.bar is not None for quote in answered):
            stats.quiet_markets.append(market_id)
            logger.info(
                "Live prices: %s's largest stocks have no bar for %s yet (a holiday, "
                "or the first minutes of the session) — skipped this run.",
                market_id,
                today,
            )
            return

        stats.companies += len(companies)
        results.extend(await asyncio.gather(*(download(c) for c in rest)))

        # What was downloaded for an earlier day is spent; drop it rather than
        # keep it until the same stock is next downloaded successfully.
        for ticker in [t for t, p in self._prices.items() if p.session_date != today]:
            if market_of(ticker).id == market_id:
                del self._prices[ticker]

        for company, quote, error in results:
            if error is not None or quote is None:
                stats.failed += 1
                stats.failures.append(company.ticker)
                logger.debug("Live price for %s failed: %s", company.ticker, error)
                continue
            entry = live_price_from(quote, fetched_at)
            if entry is None:
                stats.failed += 1
                stats.failures.append(company.ticker)
                continue
            self._prices[company.ticker.casefold()] = entry
            if quote.bar is None:
                stats.not_traded += 1
            else:
                stats.updated += 1

        self._market_fetched[market_id] = fetched_at
        self.last_update_at = fetched_at

    def _log(
        self,
        outcome: str,
        *,
        duration_ms: float | None = None,
        detail: dict | None = None,
    ) -> None:
        if self._action_log is None:
            return
        self._action_log.log_job(ACTION, outcome, duration_ms=duration_ms, detail=detail)
