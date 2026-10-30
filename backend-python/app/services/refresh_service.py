"""Data-refresh pipeline: Yahoo ingest → VSA ranking → daily rating snapshots.

``RefreshService`` is the single entry point for refreshing the application's
data. It runs in exactly three situations:

  * the nightly APScheduler jobs — one per group of markets: the GPW and the
    European exchanges at 18:00 Europe/Warsaw, the US at 17:15 New York time
    (``app.markets.refresh_runs``), each refreshing only its own markets;
  * the user pressing the **Refresh** button in the UI
    (``POST /api/stocks/refresh``), which refreshes every served market; and
  * the start-up check, for markets whose stored data is missing or behind.

Outside these two triggers no Yahoo Finance calls are made for data that is
already in the database — the API serves everything from PostgreSQL and the
in-process caches.

One full run:

  1. Ingest fresh EOD bars from Yahoo Finance into PostgreSQL
     (skipped when the app runs without a database — caches are just cleared
     so the ranking recomputes from a fresh live fetch).
  2. Recompute each refreshed market's VSA ranking with the DEFAULT engine
     settings and warm the ranking cache, so the first page load after a
     refresh is instant.
  3. Persist one rating snapshot per (ticker, day) to ``rating_snapshots``.
     Backfill missing dates using each date's own preceding analysis window.
     Routine refreshes preserve existing ratings and verdicts.
  4. Today's live prices for whichever refreshed markets are trading right
     now (``app/services/live_prices.py``) — what makes the Refresh button,
     pressed during a session, show today's prices at once instead of at the
     next hourly run. A nightly run finds every one of its markets closed, so
     for it this step does nothing.

The service also tracks its own status (idle/running, last refresh time,
last error) for the ``GET /api/stocks/refresh/status`` endpoint, and records
every run in the **action log** (``app/services/action_log.py``) as
``job.refresh`` / ``job.ingest`` entries — started, finished or failed, with
what the run actually did. A background job is accepted with a 202 long before
it succeeds or fails, so its HTTP status says nothing about the outcome; those
entries are what make a nightly run that quietly fetched nothing visible.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.analysis.method_status import is_method_active
from app.analysis.runtime_vsa import detect_signals
from app.analysis.statistics import median_turnover
from app.analysis.vsa import compute_rating, verdict_from_signals
from app.config import settings
from app.db.repository import QuoteRepository
from app.jobs.daily_ingest import IngestService, IngestStats, markets_in
from app.markets import GPW, below_liquidity_floor, market_of, quote_currency
from app.models import (
    GpwCompany,
    RatingPoint,
    RefreshStatusResponse,
    StockRankingItem,
    StooqDailyQuote,
)
from app.services.action_log import (
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
    OUTCOME_SKIPPED,
    OUTCOME_STARTED,
    ActionLogService,
)
from app.services.cache import TTLCache
from app.services.live_prices import LivePriceService
from app.services.long_term_service import build_long_term_ranking, long_term_cache_key
from app.services.market_cache import invalidate_markets
from app.services.ranking_service import (
    CONTEXT_HISTORY_DAYS,
    compute_ranking,
    ranking_cache_key,
)
from app.services.stooq_client import StooqClient
from app.services.yahoo_finance_client import YahooFinanceClient

logger = logging.getLogger(__name__)

_WARSAW = ZoneInfo("Europe/Warsaw")

# Mirror ranking_service: how far back the ranking (and thus the snapshot
# backfill) looks. Snapshots are written for every trading day in this window.
RATING_LOOKBACK_DAYS = 120
_HISTORY_DAYS = RATING_LOOKBACK_DAYS
# A stock needs this many bars before its historical ratings mean anything.
_MIN_BARS = 25

# Share of the tracked universe that has to error before the download step is
# reported as FAILED. See `ingest_outcome` for why it is not zero.
_INGEST_FAILURE_SHARE = 0.10


def failed_ingest_markets(stats: IngestStats) -> list[str]:
    return [
        market for market, counts in stats.by_market.items()
        if counts.companies and (
            counts.fetched == 0 or counts.failed > counts.companies * _INGEST_FAILURE_SHARE
        )
    ]


def ingest_outcome(stats: IngestStats) -> str:
    """Did the download step work? — the verdict its log entry carries.

    Not "did anything fail", which is what this used to ask. One flaky Yahoo
    response out of ~290 is an ordinary night; calling the whole download
    FAILED for it makes ``GET /api/admin/logs/summary`` — the one screen meant
    to surface a genuinely broken run — cry wolf most nights, and a warning
    nobody believes is worse than no warning at all.

    Apply these rules to EACH requested market, as well as the aggregate, so
    a larger market's successes cannot hide a complete smaller-market outage:

      * **nothing was fetched** — every ticker errored or was skipped, which
        is what a dead network, a wrong symbol list or an unreachable database
        looks like; or
      * **more than one ticker in ten errored** (``_INGEST_FAILURE_SHARE``) —
        past that the failures stop looking like provider noise and start
        looking systemic.

    Anything less is ``finished``, and no information is lost: the exact
    counters (fetched / skipped / failed / barsWritten) ride in the entry's
    ``detail`` either way, so a run with a handful of casualties is still
    fully readable — it is just not shouted about.
    """
    if failed_ingest_markets(stats):
        return OUTCOME_FAILED
    if stats.companies == 0:
        # Nothing was asked for, so nothing failing is not a failure.
        return OUTCOME_FINISHED
    if stats.fetched == 0:
        return OUTCOME_FAILED
    if stats.failed > stats.companies * _INGEST_FAILURE_SHARE:
        return OUTCOME_FAILED
    return OUTCOME_FINISHED


class RefreshService:
    """Orchestrates a full data refresh and reports its status."""

    def __init__(
        self,
        companies: list[GpwCompany],
        stooq: StooqClient | YahooFinanceClient,
        history_cache: TTLCache,
        ranking_cache: TTLCache,
        repo: QuoteRepository | None = None,
        ingest: IngestService | None = None,
        action_log: ActionLogService | None = None,
        live: LivePriceService | None = None,
    ) -> None:
        self._companies = companies
        # Quote currency per ticker, for the liquidity floor of the rating
        # snapshots (a London line may be quoted in pence or in dollars).
        self._currencies = {c.ticker.casefold(): quote_currency(c) for c in companies}
        self._stooq = stooq
        self._history_cache = history_cache
        self._ranking_cache = ranking_cache
        self._repo = repo
        self._ingest = ingest
        # Optional: the pipeline works without it, so tests and any other
        # caller can build a RefreshService without wiring up a log.
        self._action_log = action_log
        # Optional too: the hourly live prices, refreshed as the last step of
        # a run for any of its markets trading right now.
        self._live = live
        self._running = asyncio.Lock()
        # Id of the HTTP request that started the run in progress, if any.
        self._run_request_id: str | None = None
        self._task: asyncio.Task | None = None

        # Status, exposed via GET /api/stocks/refresh/status.
        self.last_started_at: datetime | None = None
        self.last_refresh_at: datetime | None = None
        self.last_error: str | None = None
        # The markets of the run in progress, or of the last one — which is
        # also the run ``last_error`` belongs to (it is reset on every start).
        # The health check needs it: with two nightly runs, "a refresh is
        # running" or "it failed" is only news for the run covering them.
        self.run_markets: list[str] = []
        self.stocks_ranked: int | None = None
        # How many stocks got rating snapshots written on the last run — kept
        # so the run's log entry can report it.
        self.snapshots_written: int | None = None
        self.long_term_snapshots_written: int | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running.locked()

    def status(self) -> RefreshStatusResponse:
        """Current pipeline status for the /refresh endpoints."""
        return RefreshStatusResponse(
            state="running" if self.is_running else "idle",
            last_started_at=(
                self.last_started_at.isoformat() if self.last_started_at else None
            ),
            last_refresh_at=(
                self.last_refresh_at.isoformat() if self.last_refresh_at else None
            ),
            last_error=self.last_error,
            stocks_ranked=self.stocks_ranked,
            db_enabled=self._repo is not None,
        )

    def start(
        self,
        full: bool = False,
        trigger: str = "manual",
        request_id: str | None = None,
        markets: list[str] | None = None,
        full_markets: list[str] | None = None,
    ) -> bool:
        """Kick off a refresh in the background.

        ``trigger`` says who asked — ``manual`` (the Refresh button),
        ``bootstrap`` (missing data on startup) or ``nightly`` (a scheduled
        run). It is recorded, so the log can tell an owner-initiated run from
        an automatic one. ``request_id`` carries the id of the HTTP call that
        pressed the button, so the request entry and the job entries it set
        off share one id in the action log. ``markets`` limits the run (default:
        every served market); ``full_markets`` get the full history download.

        Returns ``True`` if a new run was started, ``False`` when one is
        already in progress (the in-flight run is left alone).
        """
        if self.is_running:
            self._log_job(
                "job.refresh",
                OUTCOME_SKIPPED,
                detail={"trigger": trigger, "reason": "already running"},
                request_id=request_id,
            )
            return False
        self._task = asyncio.create_task(
            self.run(
                full=full,
                trigger=trigger,
                request_id=request_id,
                markets=markets,
                full_markets=full_markets,
            ),
            name="data_refresh",
        )
        return True

    async def run(
        self,
        full: bool = False,
        trigger: str = "nightly",
        request_id: str | None = None,
        markets: list[str] | None = None,
        full_markets: list[str] | None = None,
    ) -> None:
        """Execute the full pipeline; safe to call from the scheduler.

        The scheduler calls this directly, so ``nightly`` is the default
        trigger — ``start()`` passes its own.
        """
        if self._running.locked():
            logger.warning("Refresh already running — skipping duplicate trigger.")
            self._log_job(
                "job.refresh",
                OUTCOME_SKIPPED,
                detail={"trigger": trigger, "reason": "already running"},
                request_id=request_id,
            )
            return
        async with self._running:
            self.last_started_at = datetime.now(tz=UTC)
            self.last_error = None
            self.stocks_ranked = None
            self.snapshots_written = None
            self.long_term_snapshots_written = None
            started = time.perf_counter()
            scope = self._scope(markets)
            self.run_markets = scope
            full_ids = [m for m in (full_markets or []) if m in scope]
            # Held for the duration of the run so the ingest step's own entry
            # carries the same id as the refresh that contains it.
            self._run_request_id = request_id
            self._log_job(
                "job.refresh",
                OUTCOME_STARTED,
                detail={
                    "trigger": trigger,
                    "full": full,
                    "markets": scope,
                    "fullMarkets": full_ids,
                },
                request_id=request_id,
            )
            try:
                await self._do_run(full=full, scope=scope, full_markets=full_ids)
                live_prices = await self._refresh_live(scope, trigger)
                self.last_refresh_at = datetime.now(tz=UTC)
                self._log_job(
                    "job.refresh",
                    OUTCOME_FINISHED,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    detail={
                        "trigger": trigger,
                        "full": full,
                        "markets": scope,
                        "fullMarkets": full_ids,
                        "stocksRanked": self.stocks_ranked,
                        "snapshotsWritten": self.snapshots_written,
                        "longTermSnapshotsWritten": self.long_term_snapshots_written,
                        "dbEnabled": self._repo is not None,
                        "livePrices": live_prices,
                    },
                    request_id=request_id,
                )
            except Exception as exc:  # noqa: BLE001 — background job must not crash the app
                self.last_error = str(exc)
                logger.exception("Data refresh failed.")
                self._log_job(
                    "job.refresh",
                    OUTCOME_FAILED,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    detail={
                        "trigger": trigger,
                        "full": full,
                        "markets": scope,
                        "error": f"{type(exc).__name__}: {exc}"[:500],
                    },
                    request_id=request_id,
                )

    async def _refresh_live(self, scope: list[str], trigger: str) -> int | None:
        """Step 4: today's live prices for the run's markets that are trading.

        Returns how many stocks got a price, or ``None`` when there is no live
        service or it had nothing to do. Never raises: the live prices have
        their own log entry (``job.live``), and a failure there must not turn
        a refresh whose ingest and ranking worked into a failed one.
        """
        if self._live is None:
            return None
        try:
            stats = await self._live.run(markets=scope, trigger=f"refresh:{trigger}")
        except Exception:  # noqa: BLE001
            logger.exception("Refresh: the live-price step failed.")
            return None
        if stats is None or not stats.markets:
            return None
        return stats.updated + stats.not_traded

    def _log_job(
        self,
        action: str,
        outcome: str,
        *,
        duration_ms: float | None = None,
        detail: dict | None = None,
        request_id: str | None = None,
    ) -> None:
        """Record one pipeline event, if an action log was wired in.

        ``request_id`` defaults to the id of the run in progress, so a step
        logged from inside the pipeline (the ingest) is tied to the refresh
        that contains it and, in turn, to the button press that started it.
        """
        if self._action_log is None:
            return
        self._action_log.log_job(
            action,
            outcome,
            duration_ms=duration_ms,
            detail=detail,
            request_id=request_id or self._run_request_id,
        )

    # ── Pipeline body ─────────────────────────────────────────────────────────

    def _scope(self, markets: list[str] | None) -> list[str]:
        """The market ids a run covers, in display order."""
        present = markets_in(self._companies)
        if markets is None:
            return present
        wanted = set(markets)
        return [m for m in present if m in wanted]

    async def _do_run(
        self, full: bool, scope: list[str], full_markets: list[str]
    ) -> None:
        today = datetime.now(_WARSAW).date()

        # 1. Fresh bars from Yahoo Finance.
        if self._ingest is not None:
            # Persists to PostgreSQL and clears the refreshed markets' caches.
            stats = await self._ingest.run(
                full=full, markets=scope, full_markets=full_markets
            )
            if stats is not None:
                outcome = ingest_outcome(stats)
                self._log_job(
                    "job.ingest",
                    outcome,
                    duration_ms=stats.duration_ms,
                    detail=stats.as_detail(),
                )
                if outcome == OUTCOME_FAILED:
                    # A recorded ingest failure must also fail the containing
                    # refresh. Ranking stale/partial data cannot turn it into
                    # success or advance the last successful refresh time.
                    failed_markets = failed_ingest_markets(stats)
                    affected = [stats.by_market[m] for m in failed_markets] or [stats]
                    summary = "; ".join(
                        f"{market}: fetched {counts.fetched} of {counts.companies} companies; "
                        f"{counts.failed} failed, {counts.skipped} skipped"
                        for market, counts in zip(
                            failed_markets or [', '.join(scope)], affected, strict=True
                        )
                    )
                    raise RuntimeError(
                        f"Ingest failed for {summary}. "
                        "See the ingest log for affected tickers."
                    )
            else:
                self._log_job(
                    "job.ingest",
                    OUTCOME_SKIPPED,
                    detail={"reason": "already running"},
                )
                raise RuntimeError(
                    "Refresh incomplete: ingest is already running in another job."
                )
        else:
            # No DB: just drop the refreshed markets' caches so the ranking
            # below live-fetches.
            invalidate_markets(
                scope, (self._history_cache, "history"), (self._ranking_cache, "ranking")
            )

        # 2. Recompute each market's ranking with DEFAULT settings and pre-warm
        #    the cache (the same key the /ranking endpoint uses for the default
        #    config). One market at a time: each ranking is computed within its
        #    own market, and this keeps the work — and the memory — bounded.
        ranking: list[StockRankingItem] = []
        for market_id in scope:
            rows = await compute_ranking(
                companies=[
                    c for c in self._companies if market_of(c.ticker).id == market_id
                ],
                stooq=self._stooq,
                history_cache=self._history_cache,
                history_cache_ttl=settings.history_cache_seconds,
                repo=self._repo,
                today=today,
            )
            self._ranking_cache.set(
                ranking_cache_key(market_id), rows, settings.history_cache_seconds
            )
            logger.info("Refresh: %s ranking recomputed (%d stocks).", market_id, len(rows))
            ranking.extend(rows)
        self.stocks_ranked = len(ranking)

        # 3. Persist rating snapshots so the rating's evolution can be charted.
        if self._repo is not None:
            self.snapshots_written = await self._snapshot_ratings(ranking, today)
        else:
            self.snapshots_written = None
            logger.info("Refresh: no database configured — rating history not stored.")

        # Capture QVM as observed now. Never backfill past sessions using
        # today's financial data; repeated refreshes append revisions.
        self.long_term_snapshots_written = await self._snapshot_long_term(scope)

    async def _snapshot_long_term(self, scope: list[str]) -> int | None:
        if self._repo is None:
            return None
        written = 0
        for market_id in scope:
            now = datetime.now(UTC)
            result = await build_long_term_ranking(
                self._companies, market_id, self._repo, now=now,
            )
            items = [item.model_dump(mode="json", by_alias=True)
                     for item in result.items if item.as_of is not None]
            await self._repo.append_long_term_snapshots(items, now, result.model_version)
            written += len(items)
            self._ranking_cache.set(long_term_cache_key(market_id), result, 600)
        logger.info("Refresh: %d long-term observations stored.", written)
        return written

    async def _snapshot_ratings(
        self, ranking: list[StockRankingItem], today: date
    ) -> int:
        # Skip the legacy backfill entirely, including per-stock history reads.
        if not is_method_active("vsa"):
            return 0
        assert self._repo is not None
        from_date = today - timedelta(days=_HISTORY_DAYS)
        context_from = today - timedelta(days=CONTEXT_HISTORY_DAYS)
        written = 0
        failures: list[str] = []

        for item in ranking:
            ticker = item.ticker.lower()
            try:
                quotes = await self._load_quotes(ticker, from_date, context_from)
                currency = self._currencies.get(ticker) or market_of(ticker).currency
                existing = await self._repo.get_rating_history(ticker, from_date, today)
                saved_dates = {point.date for point in existing}
                missing_dates = {
                    q.date for q in quotes
                    if from_date <= q.date <= today and q.date not in saved_dates
                }
                if not missing_dates:
                    continue
                points = await asyncio.to_thread(
                    build_rating_points, quotes, currency, snapshot_dates=missing_dates,
                )
                if points:
                    await self._repo.upsert_rating_snapshots(ticker, points)
                    written += 1
            except Exception:
                logger.exception("Failed to snapshot ratings for %s.", ticker)
                failures.append(ticker)

        logger.info(
            "Refresh: rating snapshots stored for %d/%d ranked stocks.",
            written,
            len(ranking),
        )
        self.snapshots_written = written
        if failures:
            raise RuntimeError(
                f"Rating snapshots incomplete: {len(failures)} of {len(ranking)} "
                f"stocks failed ({', '.join(failures[:10])}). "
                f"Snapshots written for {written} stocks; retry the refresh."
            )
        return written

    async def _load_quotes(
        self, ticker: str, from_date: date, context_from: date
    ) -> list[StooqDailyQuote]:
        """Reuse the history the ranking step just loaded (cache → DB).

        Include a full analysis window BEFORE the first output date. Otherwise
        a later refresh loses the context that produced an earlier rating.
        """
        cache_key = f"history:{ticker}:{context_from}:None"
        quotes: list[StooqDailyQuote] | None = self._history_cache.get(cache_key)
        history_from = from_date - timedelta(days=RATING_LOOKBACK_DAYS)
        if quotes is not None:
            return [q for q in quotes if q.date >= history_from]
        if self._repo is not None:
            return await self._repo.get_quotes(ticker, history_from)
        return []

    async def run_insider_refresh(self) -> None:
        """Scheduled daily at 12:00 (Europe/Warsaw): refresh insider transactions."""
        self._history_cache.invalidate(
            lambda k: k.startswith("insider-checked:") or k.startswith("insider-miss:")
        )
        if self._ingest is None:
            return
        if self._action_log is not None:
            self._action_log.log_job(
                "job.insider_refresh",
                OUTCOME_STARTED,
                detail={"schedule": "12:00 Europe/Warsaw"},
            )
        try:
            detail = await self._ingest.run_insider_refresh()
            if self._action_log is not None:
                self._action_log.log_job(
                    "job.insider_refresh",
                    OUTCOME_FINISHED,
                    detail=detail,
                )
        except Exception as exc:
            logger.exception("Scheduled 12:00 insider refresh failed.")
            if self._action_log is not None:
                self._action_log.log_job(
                    "job.insider_refresh",
                    OUTCOME_FAILED,
                    detail={"error": str(exc)},
                )


def build_rating_points(
    quotes: list[StooqDailyQuote], currency: str = GPW.currency,
    *, snapshot_dates: set[date] | None = None,
) -> list[RatingPoint]:
    """Compute one rating snapshot per trading day from an OHLCV series.

    Each output date uses its own preceding 120 calendar days, DEFAULT VSA
    settings and liquidity check, matching a ranking run on that date. Callers
    must supply this preceding context as well as the desired output dates.
    ``snapshot_dates`` limits output without discarding the warm-up bars.

    ``currency`` is the stock's quote currency — the liquidity floor is
    judged in it (złoty unless said otherwise).
    """
    # Retain the historical rating builder, but do not run the archived classic
    # engine or write neutral placeholder snapshots during refresh/backfill.
    if not is_method_active("vsa"):
        return []
    if len(quotes) < _MIN_BARS:
        return []
    ordered = sorted(quotes, key=lambda q: q.date)
    points: list[RatingPoint] = []
    start = 0
    for index, q in enumerate(ordered):
        day = q.date
        if snapshot_dates is not None and day not in snapshot_dates:
            continue
        window_from = day - timedelta(days=RATING_LOOKBACK_DAYS)
        while ordered[start].date < window_from:
            start += 1
        window = ordered[start:index + 1]
        if len(window) < _MIN_BARS or below_liquidity_floor(median_turnover(window), currency):
            continue
        signals = detect_signals(window)
        verdict, _ = verdict_from_signals(signals, day)
        points.append(
            RatingPoint(
                date=day,
                rating=compute_rating(signals, day),
                verdict=verdict,
                close=float(q.close),
            )
        )
    return points
