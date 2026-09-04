"""Ranking computation service.

Builds the VSA ranking for all tracked GPW companies.

Data source priority:
  1. In-memory ``history_cache`` (fastest, ~ms).
  2. ``QuoteRepository`` (PostgreSQL, ~ms if warm).
  3. stooq.pl live fetch (slow, ~30 s for 30 tickers; also persists result).

When ``repo`` is ``None`` (DB not configured), the service falls directly to
the stooq live fetch — identical to the pre-DB behaviour.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import date, timedelta

from app.analysis.ai_insight import analyze_stock
from app.analysis.methods import MethodResult, all_methods
from app.analysis.methods.vsa_method import vsa_result_from_signals
from app.analysis.statistics import median_volume_pln
from app.analysis.vsa import (
    VsaConfig,
    VsaSignal,
    compute_rating,
    detect_signals,
    verdict_from_signals,
)
from app.analysis.weekly import compute_weekly_view, weekly_agreement
from app.db.repository import QuoteRepository
from app.models import GpwCompany, MethodResultModel, StockRankingItem, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

# VSA analysis window (calendar days). Ratings, signals, liquidity and every
# other per-stock metric except the 52-week context are computed on this slice,
# so results are identical to the pre-52w engine.
_HISTORY_DAYS = 120
# Fetch window (calendar days): 52 weeks for the high/low context plus two
# weeks of slack, because the 52-week window is anchored to the stock's last
# SESSION date, which can trail today by a few days. Shared with the
# volume-surge and scanner-stats services so all three reuse one cached
# per-ticker history (the cache key embeds the from_date derived from this).
CONTEXT_HISTORY_DAYS = 380
# The 52-week window itself, anchored to the last bar.
_WEEK52_DAYS = 365
# Minimum span the stored bars must actually cover before a "52-week" figure is
# reported. Without it a recently listed stock — or one whose history the DB
# has only just started collecting — would have its 3-month high published as a
# "new 52-week high", which the /filters screener then offers as a filter. 330
# days (~47 weeks) leaves room for a listing that started just under a year ago
# and for the gaps a thin GPW series can have, while still being a real year.
_MIN_52W_COVERAGE_DAYS = 330
_MIN_MEDIAN_VOLUME_PLN = 100_000.0
_MIN_MARKET_CAP_PLN = 100_000_000
_MAX_CONCURRENT = 4
_SPARKLINE_BARS = 10
# Recency pre-filter: exclude suspended/stale listings, whose last bar keeps
# falling further behind the rest of the market while their rating (keyed to
# their own last session) stays frozen. A ticker is dropped when its last bar
# is more than this many calendar days older than the newest session across
# the whole scan — dataset-global, not wall-clock, so cached results stay
# deterministic; 10 days tolerates holidays and long weekends.
_MAX_SESSION_LAG_DAYS = 10


# ── Cross-sectional relative strength (Minervini's rule 8) ────────────────────
# IBD-style blended trailing performance: the most recent quarter double-
# weighted, then the three quarters before it. Sessions, not calendar days.
# Requires a full ~12-month history so every stock is ranked on the same
# horizons; a stock with less (which is also below Minervini's own 52-week
# minimum) gets no RS rank and Minervini falls back to its 7 structural rules.
_RS_OFFSETS = (63, 126, 189, 252)  # ~3 / 6 / 9 / 12 months
_RS_WEIGHTS = (0.4, 0.2, 0.2, 0.2)


def _relative_strength_raw(quotes: Sequence[StooqDailyQuote]) -> float | None:
    """The stock's raw blended trailing return (percent), or None if too short."""
    closes = [float(q.close) for q in quotes]
    n = len(closes)
    if n <= max(_RS_OFFSETS):
        return None
    last = closes[-1]
    if last <= 0:
        return None
    perf = 0.0
    for off, weight in zip(_RS_OFFSETS, _RS_WEIGHTS, strict=True):
        past = closes[-1 - off]
        if past <= 0:
            return None
        perf += weight * (last / past - 1.0) * 100.0
    return perf


def _percentile_ranks(raw: dict[str, float]) -> dict[str, float]:
    """Rank raw RS values into 0-100 percentiles across the universe.

    Lowest raw -> 0, highest -> 100 (ordinal, ties broken by ticker for
    determinism). Needs at least two stocks; with fewer, a cross-sectional rank
    is meaningless, so every ticker gets none (Minervini uses the 7 structural
    rules).
    """
    if len(raw) < 2:
        return {}
    ordered = sorted(raw.items(), key=lambda kv: (kv[1], kv[0]))
    m = len(ordered)
    return {ticker: i / (m - 1) * 100.0 for i, (ticker, _) in enumerate(ordered)}


def _to_method_model(method_id: str, result: MethodResult) -> MethodResultModel:
    """Convert a framework ``MethodResult`` dataclass into the API model."""
    return MethodResultModel(
        method_id=method_id,
        score=result.score,
        days_since=result.days_since,
        fired=result.fired,
        detail=result.detail,
        available=result.available,
    )


def _evaluate_methods(
    quotes: list[StooqDailyQuote],
    config: VsaConfig | None,
    *,
    vsa_signals: Sequence[VsaSignal],
    vsa_rating: int,
    vsa_verdict: str,
    as_of: date,
    rs_rank: float | None = None,
) -> dict[str, MethodResultModel]:
    """Run every registered trading method against one stock's bars.

    VSA reuses the signals/rating the ranking already computed for the row, so
    its column equals the Rating/Signal columns exactly and no VSA work is
    repeated. Every other method evaluates on the full fetched window, receiving
    the stock's cross-sectional ``rs_rank`` (used only by methods with a
    relative-strength rule, e.g. Minervini's rule 8). A method that raises is
    skipped (recorded as unavailable) so one bad rule can never break the
    ranking.
    """
    results: dict[str, MethodResultModel] = {}
    for method in all_methods():
        if method.id == "vsa":
            results["vsa"] = _to_method_model(
                "vsa",
                vsa_result_from_signals(vsa_signals, vsa_rating, vsa_verdict, as_of),
            )
            continue
        try:
            results[method.id] = _to_method_model(
                method.id, method.evaluate(quotes, config, rs_rank=rs_rank)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Method %s failed on a stock; marking unavailable.",
                             method.id)
            results[method.id] = MethodResultModel(
                method_id=method.id, score=0, available=False
            )
    return results


def compute_52w_context(
    quotes: list[StooqDailyQuote],
) -> tuple[float | None, float | None, bool, bool]:
    """52-week high/low context for a chronological bar list.

    Returns ``(dist_from_high_pct, dist_from_low_pct, new_high, new_low)``:
    the last close vs. the highest high / lowest low of the 52 weeks ending
    at the last bar (inclusive, so the "distance from high" is never
    positive), plus flags saying whether the last bar itself set a new
    52-week extreme (its intraday high/low beat every earlier bar in the
    window).

    The window has to be a real year: when the stored bars span less than
    ``_MIN_52W_COVERAGE_DAYS`` the answer is "unknown" — all ``None``/``False``
    — rather than a 52-week claim made from three months of data. Reporting a
    short window would turn a quarterly high into a "new 52-week high" on the
    screener, which is a plain falsehood to the reader.
    """
    if not quotes:
        return None, None, False, False
    last = quotes[-1]
    window_from = last.date - timedelta(days=_WEEK52_DAYS)
    window = [q for q in quotes if q.date >= window_from]
    # window is non-empty (it always contains `last`); window[0] is its oldest
    # bar, because callers pass chronologically sorted history.
    if window[0].date > last.date - timedelta(days=_MIN_52W_COVERAGE_DAYS):
        return None, None, False, False
    high = max(float(q.high) for q in window)
    low = min(float(q.low) for q in window)
    last_close = float(last.close)
    dist_high = round((last_close - high) / high * 100, 2) if high > 0 else None
    dist_low = round((last_close - low) / low * 100, 2) if low > 0 else None
    prior = window[:-1]
    new_high = bool(prior) and float(last.high) > max(float(q.high) for q in prior)
    new_low = bool(prior) and float(last.low) < min(float(q.low) for q in prior)
    return dist_high, dist_low, new_high, new_low


async def compute_ranking(
    companies: list[GpwCompany],
    stooq: StooqClient,
    history_cache: TTLCache,
    history_cache_ttl: int,
    repo: QuoteRepository | None = None,
    today: date | None = None,
    config: VsaConfig | None = None,
) -> list[StockRankingItem]:
    """Fetch history for all companies, run VSA analysis, apply pre-filters, rank.

    Args:
        companies:          All tracked GPW companies.
        stooq:              stooq.pl client (fallback data source).
        history_cache:      In-memory TTL cache for per-ticker OHLCV lists.
        history_cache_ttl:  Seconds before cache entries expire.
        repo:               Persistent quote repository; ``None`` = no DB.
        today:              Override "today" (used in tests).
        config:             VSA detection settings; ``None`` = defaults.
    """
    if today is None:
        today = date.today()

    from_date = today - timedelta(days=CONTEXT_HISTORY_DAYS)
    analysis_from = today - timedelta(days=_HISTORY_DAYS)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote] | None:
        """Return quotes from cache → repo → stooq, in that priority order."""
        cache_key = f"history:{ticker}:{from_date}:None"
        quotes: list[StooqDailyQuote] | None = history_cache.get(cache_key)
        if quotes is not None:
            return quotes

        # Try the DB.
        if repo is not None:
            quotes = await repo.get_quotes(ticker, from_date)
            if quotes:
                history_cache.set(cache_key, quotes, history_cache_ttl)
                return quotes

        # Fall back to stooq.pl.
        async with semaphore:
            try:
                quotes = await stooq.get_daily_history(ticker, from_date=from_date)
            except StooqAccessError as exc:
                logger.warning("Skipping %s: stooq error: %s", ticker, exc)
                return None
            except Exception as exc:  # noqa: BLE001
                logger.error("Skipping %s: unexpected error: %s", ticker, exc)
                return None

            # Persist inside the semaphore so at most _MAX_CONCURRENT DB writes
            # are in flight simultaneously (prevents connection pool exhaustion).
            if repo is not None and quotes:
                try:
                    await repo.upsert_quotes(ticker, quotes)
                except Exception:
                    logger.exception("Failed to persist %s quotes to DB.", ticker)

        history_cache.set(cache_key, quotes or [], history_cache_ttl)
        return quotes or []

    async def fetch_and_analyse(
        company: GpwCompany,
        rs_rank: float | None,
    ) -> tuple[StockRankingItem, date] | None:
        """Analyse one company; returns (item, its last session date) or None."""
        # Capitalisation floor (blueprint §5): market cap must exceed 100M PLN.
        # Applied only when the value is known, so missing metadata never
        # silently hides a company from the ranking.
        if company.market_cap is not None and company.market_cap < _MIN_MARKET_CAP_PLN:
            logger.debug("Skipping %s: market cap below floor.", company.ticker)
            return None

        quotes = await fetch_quotes(company.ticker)
        # Everything below except the 52-week context runs on the 120-day
        # analysis slice, so the longer fetch window (CONTEXT_HISTORY_DAYS)
        # never changes ratings, signals or the pre-filters.
        recent = [q for q in quotes or [] if q.date >= analysis_from]
        if len(recent) < 25:
            logger.debug("Skipping %s: insufficient history (%d bars).",
                         company.ticker, len(recent))
            return None

        # Guard the analysis + model construction: a single company with
        # malformed data must never 500 the whole ranking — skip it instead.
        try:
            if median_volume_pln(recent) < _MIN_MEDIAN_VOLUME_PLN:
                logger.debug("Skipping %s: below liquidity threshold.", company.ticker)
                return None

            signals = detect_signals(recent, config)

            # Ratings are keyed to the last SESSION date, not the wall-clock
            # date: identical data must yield identical ratings whether the
            # ranking runs on Friday evening or Sunday (no weekend decay).
            last_bar_date = recent[-1].date
            rating_today = compute_rating(signals, last_bar_date)

            # ratingChange = how the newest session changed the rating: the
            # rating as of the last bar minus the rating as it stood after
            # the previous bar (excluding any signal fired on the last bar).
            if len(recent) >= 2:
                prev_bar_date = recent[-2].date
                prior_signals = [s for s in signals if s.date < last_bar_date]
                rating_change = rating_today - compute_rating(
                    prior_signals, prev_bar_date
                )
            else:
                rating_change = 0

            verdict, days_since = verdict_from_signals(signals, last_bar_date)

            # Multi-timeframe check: run the same VSA engine on the weekly
            # resampling of the full fetched window (not the 120-day slice —
            # weekly VSA needs ~30 weekly bars of context). "confirms" when the
            # weekly verdict leans the same way as the daily one.
            weekly = compute_weekly_view(quotes or [], config)
            weekly_agree = (
                weekly_agreement(verdict, weekly.verdict)
                if weekly.available and weekly.verdict is not None
                else None
            )

            # Local AI-insight second opinion — reuses the quotes/signals/rating
            # already computed above (no extra I/O). We only surface its
            # confidence here; the full narrative lives on the detail endpoint.
            ai = analyze_stock(
                ticker=company.ticker,
                name=company.name,
                quotes=recent,
                signals=signals,
                rating=rating_today,
            )

            last_close = float(recent[-1].close)
            prev_close = float(recent[-2].close) if len(recent) >= 2 else last_close
            price_change_pct = (
                round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0
            )

            sparkline = [float(q.close) for q in recent[-_SPARKLINE_BARS:]]

            # 52-week context is the one metric that uses the full fetched
            # window. `recent` is a suffix of `quotes` (same last bar), so
            # the window is anchored to the same session as the rating.
            dist_high, dist_low, new_high, new_low = compute_52w_context(quotes)

            # Every registered trading method's read of this stock. VSA reuses
            # the values just computed; other methods see the full window.
            method_results = _evaluate_methods(
                quotes or [],
                config,
                vsa_signals=signals,
                vsa_rating=rating_today,
                vsa_verdict=verdict,
                as_of=last_bar_date,
                rs_rank=rs_rank,
            )

            med_vol_list = sorted(q.volume for q in recent[-20:])
            n = len(med_vol_list)
            median_vol_shares = int(
                (med_vol_list[n // 2 - 1] + med_vol_list[n // 2]) / 2
                if n % 2 == 0
                else med_vol_list[n // 2]
            )

            item = StockRankingItem(
                ticker=company.ticker.upper(),
                name=company.name,
                sector=company.sector,
                last_price=last_close,
                price_change_pct=price_change_pct,
                current_rating=rating_today,
                rating_change=rating_change,
                last_signal=verdict,
                days_since_signal=days_since,
                sparkline=sparkline,
                volume=median_vol_shares,
                ai_confidence=ai.confidence,
                dist_from_52w_high_pct=dist_high,
                dist_from_52w_low_pct=dist_low,
                is_new_52w_high=new_high,
                is_new_52w_low=new_low,
                method_results=method_results,
                weekly_rating=weekly.rating,
                weekly_signal=weekly.verdict,
                weekly_agreement=weekly_agree,
            )
            return item, last_bar_date
        except Exception:  # noqa: BLE001
            logger.exception("Skipping %s: analysis failed.", company.ticker)
            return None

    # Relative-strength pre-pass (Minervini's rule 8): compute each stock's raw
    # blended trailing return, then rank those into 0-100 percentiles across the
    # scanned universe. This warms the per-ticker history cache, so the main
    # analysis pass below reads the SAME quotes back from cache — no extra
    # network or DB fetch. Stocks below the market-cap floor or without a full
    # ~12-month history get no rank (Minervini then uses its structural rules).
    async def rs_raw_for(company: GpwCompany) -> tuple[str, float | None]:
        if company.market_cap is not None and company.market_cap < _MIN_MARKET_CAP_PLN:
            return company.ticker, None
        quotes = await fetch_quotes(company.ticker)
        return company.ticker, _relative_strength_raw(quotes or [])

    rs_pairs = await asyncio.gather(
        *(rs_raw_for(c) for c in companies), return_exceptions=True
    )
    rs_raw: dict[str, float] = {}
    for res in rs_pairs:
        if isinstance(res, BaseException):
            continue  # a fetch failure here just means "no RS rank" for that stock
        ticker, raw = res
        if raw is not None:
            rs_raw[ticker] = raw
    rs_rank_by_ticker = _percentile_ranks(rs_raw)

    # return_exceptions=True so one failed task can never abort the whole gather.
    results = await asyncio.gather(
        *(
            fetch_and_analyse(c, rs_rank_by_ticker.get(c.ticker))
            for c in companies
        ),
        return_exceptions=True,
    )
    # An exception that escaped fetch_and_analyse's guard (e.g. the DB dying
    # mid-scan) must be logged, or a broken run would look like an empty market.
    for company, result in zip(companies, results, strict=True):
        if isinstance(result, BaseException):
            logger.error("Ranking: skipping %s: %s", company.ticker, result)
    pairs = [r for r in results if isinstance(r, tuple)]

    # Recency pre-filter (see _MAX_SESSION_LAG_DAYS): a ticker whose last bar
    # lags the newest session in this run by more than the tolerance has
    # stopped trading — drop it instead of ranking its frozen rating.
    latest_session = max((d for _, d in pairs), default=None)
    ranking = [
        item
        for item, last_bar in pairs
        if latest_session is None
        or (latest_session - last_bar).days <= _MAX_SESSION_LAG_DAYS
    ]
    ranking.sort(key=lambda r: r.current_rating, reverse=True)
    return ranking
