"""Generic GPW back-test gate for the pluggable trading methods.

A trading method may *look* sensible and still not have worked on the Warsaw
exchange. Before a method's score is trusted to rank real money, this service
proves it on stored GPW history — reusing the exact frame the VSA scanner
back-test (`scanner_service.py`) and the trust score already use:

  * For each stock, take the method's own firing history (`method.signals`).
  * Judge every *long* firing old enough to have forward data: its return over
    the next ``forward_sessions`` sessions versus the stock's **own median
    forward move over the same horizon** (the baseline a random-day entry would
    have earned). Beating that baseline — not zero — is what "the setup has
    skill" means; otherwise the number just measures market drift.
  * Aggregate across the universe into a win rate, an average baseline-excess
    return (the edge), a reward/risk ratio and a pass/fail **gate verdict**.

Because it drives off the generic ``TradingMethod.signals`` contract, the same
gate judges *every* method (VSA's bullish structures, the Minervini template,
Volume Breakout, and any method added later) with no per-method code.

The gate is deliberately honest: it needs a minimum sample before it will grade
at all (few lucky firings must not read as "proven"), and a method that does not
clear its own baseline is reported as failing, not massaged into a pass.

Unlike the ranking/scanner (which analyse a 120-day slice), the back-test hands
each method its **full stored window** — trend/breakout methods need hundreds of
bars before they can fire even once — so it fetches a multi-year history and
keeps it in a cache of its own.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from app.analysis.methods.base import TradingMethod
from app.analysis.vsa import VsaConfig
from app.db.repository import QuoteRepository
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.stooq_client import StooqClient

logger = logging.getLogger(__name__)

# Forward horizon judged after each firing — identical to the VSA scanner stats
# and the trust score, so the three back-tests are directly comparable.
DEFAULT_FORWARD_SESSIONS = 10
# Fetch as much stored history as the DB holds, up to ~4 years, so a method has
# enough run-up to fire many times. Its own cache key (below), separate from the
# ranking's ~380-day window.
_BACKTEST_HISTORY_DAYS = 1460
_MAX_CONCURRENT = 4
# Below this many judged firings the result is "insufficient", not a grade — a
# handful of lucky signals must never read as a proven edge (same spirit as the
# trust score's ≥ 8 gate, scaled up because this pools the whole universe).
_MIN_SAMPLES = 30

ENGINE_VERSION = "method-backtest-1"


@dataclass(frozen=True)
class MethodBacktestStats:
    """Aggregated back-test of one trading method across the GPW universe."""

    method_id: str
    name: str
    as_of: date | None
    forward_sessions: int
    scanned_count: int
    signal_count: int
    evaluated_count: int
    win_count: int
    win_rate_pct: float | None
    avg_forward_return_pct: float | None
    baseline_return_pct: float | None
    avg_excess_return_pct: float | None
    reward_risk: float | None
    passes: bool | None
    grade: str
    summary: str
    engine: str = ENGINE_VERSION


@dataclass
class _Acc:
    """Running accumulator over judged firings (not exported)."""

    scanned: int = 0
    signals: int = 0
    evaluated: int = 0
    wins: int = 0
    forward_sum: float = 0.0
    baseline_sum: float = 0.0
    excess_sum: float = 0.0
    win_mag_sum: float = 0.0
    win_mag_n: int = 0
    loss_mag_sum: float = 0.0
    loss_mag_n: int = 0
    last_dates: list[date] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.last_dates = []


def judge_stock(
    bars: Sequence[StooqDailyQuote],
    signal_dates: Sequence[date],
    forward_sessions: int,
    bullish: bool,
) -> list[tuple[float, float, float, bool]] | None:
    """Judge one stock's firings; return ``(pct, baseline, excess, success)`` rows.

    ``pct`` is the forward return over ``forward_sessions`` sessions after the
    firing bar; ``baseline`` is the stock's median forward move over the same
    horizon; ``excess = pct - baseline`` (positive = beat the baseline the long
    way); ``success`` is whether it beat the baseline in the trade's direction.
    Returns ``None`` when the stock cannot be judged (too little forward data).
    Pure — no I/O — so it is unit-testable.
    """
    bars_sorted = sorted(bars, key=lambda q: q.date)
    dates = [q.date for q in bars_sorted]
    closes = [float(q.close) for q in bars_sorted]
    n = len(closes)
    if n <= forward_sessions:
        return None

    forward_returns = [
        (closes[i + forward_sessions] - closes[i]) / closes[i] * 100
        for i in range(n - forward_sessions)
        if closes[i] > 0
    ]
    if not forward_returns:
        return None
    baseline = median(forward_returns)

    index_of = {d: i for i, d in enumerate(dates)}
    out: list[tuple[float, float, float, bool]] = []
    for sig_date in signal_dates:
        idx = index_of.get(sig_date)
        if idx is None or idx + forward_sessions >= n:
            continue  # unknown bar, or not enough forward data yet
        entry = closes[idx]
        if entry <= 0:
            continue
        pct = (closes[idx + forward_sessions] - entry) / entry * 100
        success = pct > baseline if bullish else pct < baseline
        # Rows carry the baseline-excess (pct - baseline); the caller derives the
        # win/loss magnitude as |excess|, the same frame the win/loss test uses.
        out.append((pct, baseline, pct - baseline, success))
    return out


def _grade(
    evaluated: int, win_rate: float, avg_excess: float, rr: float | None
) -> tuple[bool | None, str, str]:
    """Map aggregates to (passes, grade, plain-language summary)."""
    if evaluated < _MIN_SAMPLES:
        return (
            None,
            "insufficient",
            (
                f"Only {evaluated} historical firing(s) old enough to judge — "
                f"fewer than the {_MIN_SAMPLES} needed to grade this method on "
                "GPW. Not enough evidence yet; the score should be treated as "
                "unproven."
            ),
        )
    passes = win_rate > 50.0 and avg_excess > 0.0
    strong = win_rate >= 55.0 and avg_excess >= 1.0 and (rr is None or rr >= 1.2)
    if strong:
        grade = "strong"
    elif passes:
        grade = "pass"
    else:
        grade = "fail"

    edge = f"{avg_excess:+.2f} pp vs each stock's own baseline"
    if passes:
        summary = (
            f"Passes the GPW gate: over {evaluated} historical firings the setup "
            f"beat the stock's own baseline {win_rate:.0f}% of the time, an "
            f"average edge of {edge}. Treat the score as evidence-backed on GPW "
            "(past performance is not a guarantee)."
        )
    else:
        summary = (
            f"Fails the GPW gate: over {evaluated} historical firings it beat the "
            f"baseline only {win_rate:.0f}% of the time (edge {edge}). On this "
            "universe the setup did not add a real edge, so its score should not "
            "yet guide real money."
        )
    return passes, grade, summary


async def compute_method_backtest(
    method: TradingMethod,
    companies: list[GpwCompany],
    stooq: StooqClient,
    history_cache: TTLCache,
    history_cache_ttl: int,
    repo: QuoteRepository | None = None,
    today: date | None = None,
    config: VsaConfig | None = None,
    forward_sessions: int = DEFAULT_FORWARD_SESSIONS,
) -> MethodBacktestStats:
    """Back-test one method across the tracked universe on stored GPW history."""
    if today is None:
        today = date.today()

    from_date = today - timedelta(days=_BACKTEST_HISTORY_DAYS)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    bullish = method.direction != "Bearish"
    acc = _Acc()

    async def fetch_quotes(ticker: str) -> list[StooqDailyQuote]:
        # Own cache key (longer window than the ranking's) — the back-test needs
        # the full run-up, not the 120-day slice the ranking analyses.
        cache_key = f"backtest-history:{ticker}:{from_date}"
        cached: list[StooqDailyQuote] | None = history_cache.get(cache_key)
        if cached is not None:
            return cached
        rows: list[StooqDailyQuote] = []
        if repo is not None:
            rows = await repo.get_quotes(ticker, from_date)
        if not rows:
            async with semaphore:
                try:
                    rows = await stooq.get_daily_history(ticker, from_date=from_date)
                except Exception as exc:  # noqa: BLE001 — includes StooqAccessError
                    logger.debug("Backtest: skip %s — %s", ticker, exc)
                    rows = []
                if repo is not None and rows:
                    try:
                        await repo.upsert_quotes(ticker, rows)
                    except Exception:
                        logger.exception("Backtest: DB write failed for %s.", ticker)
        history_cache.set(cache_key, rows or [], history_cache_ttl)
        return rows or []

    async def process(company: GpwCompany) -> None:
        bars = await fetch_quotes(company.ticker)
        if len(bars) <= forward_sessions:
            return
        try:
            raw = method.signals(bars, config)
        except Exception:  # noqa: BLE001 — one bad stock must not sink the gate
            logger.exception("Backtest: %s signals failed for %s.", method.id, company.ticker)
            return
        # Long-only gate: judge only the bullish entries (VSA also emits bearish
        # structures, which are not long trades).
        sig_dates = sorted({s.date for s in raw if s.type != "Bearish"})

        acc.scanned += 1
        acc.last_dates.append(max(b.date for b in bars))
        if not sig_dates:
            return
        acc.signals += len(sig_dates)

        judged = judge_stock(bars, sig_dates, forward_sessions, bullish)
        if not judged:
            return
        for pct, base, excess, success in judged:
            acc.evaluated += 1
            acc.forward_sum += pct
            acc.baseline_sum += base
            acc.excess_sum += excess
            magnitude = abs(excess)
            if success:
                acc.wins += 1
                acc.win_mag_sum += magnitude
                acc.win_mag_n += 1
            else:
                acc.loss_mag_sum += magnitude
                acc.loss_mag_n += 1

    results = await asyncio.gather(
        *(process(c) for c in companies), return_exceptions=True
    )
    for company, result in zip(companies, results, strict=True):
        if isinstance(result, BaseException):
            logger.error("Backtest: skipping %s: %s", company.ticker, result)

    as_of = max(acc.last_dates, default=None)
    if acc.evaluated == 0:
        _, grade, summary = _grade(0, 0.0, 0.0, None)
        return MethodBacktestStats(
            method_id=method.id,
            name=method.name,
            as_of=as_of,
            forward_sessions=forward_sessions,
            scanned_count=acc.scanned,
            signal_count=acc.signals,
            evaluated_count=0,
            win_count=0,
            win_rate_pct=None,
            avg_forward_return_pct=None,
            baseline_return_pct=None,
            avg_excess_return_pct=None,
            reward_risk=None,
            passes=None,
            grade=grade,
            summary=summary,
        )

    win_rate = acc.wins / acc.evaluated * 100
    avg_forward = acc.forward_sum / acc.evaluated
    avg_baseline = acc.baseline_sum / acc.evaluated
    avg_excess = acc.excess_sum / acc.evaluated
    avg_win = acc.win_mag_sum / acc.win_mag_n if acc.win_mag_n else 0.0
    avg_loss = acc.loss_mag_sum / acc.loss_mag_n if acc.loss_mag_n else 0.0
    if avg_loss > 0:
        rr: float | None = round(avg_win / avg_loss, 2)
    elif acc.win_mag_n:
        rr = None  # wins but no losses → undefined, not the worst score
    else:
        rr = 0.0

    passes, grade, summary = _grade(acc.evaluated, win_rate, avg_excess, rr)

    return MethodBacktestStats(
        method_id=method.id,
        name=method.name,
        as_of=as_of,
        forward_sessions=forward_sessions,
        scanned_count=acc.scanned,
        signal_count=acc.signals,
        evaluated_count=acc.evaluated,
        win_count=acc.wins,
        win_rate_pct=round(win_rate, 1),
        avg_forward_return_pct=round(avg_forward, 2),
        baseline_return_pct=round(avg_baseline, 2),
        avg_excess_return_pct=round(avg_excess, 2),
        reward_risk=rr,
        passes=passes,
        grade=grade,
        summary=summary,
    )
