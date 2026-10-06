"""Phase 0 bench report for the AI layer — plan §6.5 / §6.6 / §20.

Runs the honest test bench on the stored bars (never downloads anything) and
writes ``<reports>/<date>-phase0-bench.md`` (``agent/ml/reports`` on a PC,
``~/stockpilot/ml/reports`` on the server). It reads the datasets the dataset
step wrote, and streams the stored bars **one stock at a time** for the rest —
it never holds a whole market's history, so it fits beside the live site:

1. **Data coverage** — how much history each market really holds.
2. **Look-ahead check** — features recomputed on histories cut off at random
   days must not change.
3. **Gate reproduction** — the bench re-measures VSA V4 and Weinstein through
   its own code and must match the app's back-test gate.
4. **Unfiltered baselines** — what each method scores on L1 / L2 / L3, per
   year, and how high a *random* filter already scores by chance.

On the server (after ``bash deploy/ml-run.sh dataset``)::

    bash deploy/ml-run.sh bench

On a PC, from ``backend-python/`` with PostgreSQL running (after the dataset
step)::

    .venv/Scripts/python.exe -m scripts.ml_report
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from datetime import date, timedelta

from app.analysis.methods import get_method
from app.analysis.vsa4.adapter import tick_size
from app.config import settings
from app.db.base import build_engine, build_session_factory
from app.db.repository import PostgresQuoteRepository
from app.ml import AGENT_ML_DIR, ML_DATA_DIR
from app.ml.bench import (
    GATE_WINDOW_DAYS,
    CoverageCounter,
    GateNumbers,
    leak_check,
    random_filter_bar,
    reproduce_gate,
    summarise_method,
)
from app.ml.data_access import parse_markets, peak_memory_mb, stream_stock_inputs
from app.ml.dataset import HORIZONS, JOB1_METHODS, PRIMARY_METHODS, read_datasets
from app.ml.report import fmt_num, fmt_pct, fmt_pp, md_table
from app.ml.trials import ensure_register, trial_count
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.gpw_company_service import GpwCompanyService
from app.services.method_backtest_service import compute_method_backtest

# Tolerances for "the bench reproduces the gate" (design choices §4, plan §15).
_TOL_WIN_RATE_PP = 0.3
_TOL_EDGE_PP = 0.2


def _gate_cell(nums: GateNumbers) -> str:
    return f"{nums.evaluated} · {nums.win_rate_pct}% · {fmt_pp(nums.avg_excess_pp)}"


class _NoNetwork:
    """Stands in for the data client: the report must never download."""

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        raise StooqAccessError("ml_report reads the database only")


async def _gate_numbers(method_id: str, horizon: int, today: date) -> GateNumbers:
    """The app's own gate, run in-process on the database (GPW, as the endpoint)."""
    companies = GpwCompanyService().get_companies("gpw")
    engine = build_engine(settings.database_url)
    try:
        repo = PostgresQuoteRepository(build_session_factory(engine))
        stats = await compute_method_backtest(
            get_method(method_id),
            companies,
            _NoNetwork(),  # type: ignore[arg-type]
            TTLCache(),
            3600,
            repo=repo,
            today=today,
            forward_sessions=horizon,
        )
    finally:
        await engine.dispose()
    return GateNumbers(
        stats.evaluated_count, stats.win_count, stats.win_rate_pct, stats.avg_excess_return_pct
    )



#: The only dataset columns this report reads. The rest of a back-filled table
#: is hundreds of MB the server's memory cap cannot spare.
_JOB1_READ = [
    "method",
    "date",
    *(
        f"{name}_{n}"
        for n in HORIZONS
        for name in ("l1_y", "l1_excess", "l2_y", "l2_excess", "l3_r")
    ),
]
_JOB2_READ = [f"l1_y_{n}" for n in HORIZONS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 0 bench report (AI layer).")
    parser.add_argument("--markets", default="gpw", help="gpw (default), a list, or all")
    parser.add_argument("--leak-samples", type=int, default=50, help="random days to check")
    parser.add_argument("--event-samples", type=int, default=100,
                        help="signal/marker days to check (where look-ahead hides)")
    parser.add_argument("--skip-gate", action="store_true", help="skip the gate reproduction")
    args = parser.parse_args(argv)
    if not settings.database_url:
        print("No database configured (STOCKPILOT_DATABASE_URL).", file=sys.stderr)
        return 2

    started = time.perf_counter()
    today = date.today()
    markets = parse_markets(args.markets)
    try:
        job1, _ = read_datasets(ML_DATA_DIR, markets, 1, columns=_JOB1_READ)
        job2, _ = read_datasets(ML_DATA_DIR, markets, 2, columns=_JOB2_READ)
    except FileNotFoundError as exc:
        print(f"{exc} (bash deploy/ml-run.sh dataset on the server).", file=sys.stderr)
        return 1
    counter = CoverageCounter()
    for stock in stream_stock_inputs(markets):
        counter.add(stock)
    print(f"Counted {len(counter.bar_counts)} companies.", flush=True)
    lines: list[str] = []
    add = lines.append

    add(f"# AI layer — Phase 0 bench report, {today}")
    add("")
    add("*Written by `backend-python/scripts/ml_report.py`. Plan: "
        "`agent/AI-ALGORITHMS-PLAN.md` §6 and §15 (Phase 0); fixed rules: "
        "`agent/ml/DESIGN-CHOICES.md`. **No model has been trained** — this is the "
        "bench every later model is judged on, and the baselines it must beat.*")
    add("")

    # 1. Coverage ────────────────────────────────────────────────────────────
    cov = counter.result()
    add("## 1. Data coverage")
    add("")
    add(md_table(
        ["Market", "Companies", "Bars", "Oldest bar", "Median company starts",
         "Days with ≥ 20 stocks", "First such day"],
        [[c.market, c.companies, f"{c.bars:,}", c.first_date, c.median_first_date,
          f"{c.days_with_market:,}", c.first_full_day] for c in cov],
    ))
    add("")
    add("\"Days with ≥ 20 stocks\" is where the market regime and the L1 "
        "\"beat the market\" label exist at all (design choices §3). Before that "
        "day the database holds only the few companies whose stock pages were "
        "opened, which is not a market.")
    add("")

    # 2. Leak check ─────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    rng = random.Random(20260925)
    eligible = sorted(t for t, n in counter.bar_counts.items() if n >= 300)
    chosen = rng.sample(eligible, min(40, len(eligible)))
    sample = list(stream_stock_inputs(markets, tickers=chosen))
    checked, counts, examples = leak_check(
        sample, args.leak_samples, event_samples=args.event_samples, event_stocks=len(sample)
    )
    add("## 2. Look-ahead check")
    add("")
    verdict = "**PASS** — no feature changed" if not counts else "**FAIL**"
    add(f"{checked} (stock, day) rows — {args.leak_samples} random days plus up to "
        f"{args.event_samples} days on which a signal, firing or marker happens — were "
        f"recomputed on histories cut off at that day, comparing all per-stock "
        f"features: {verdict}. ({time.perf_counter() - t0:.0f} s)")
    if counts:
        add("")
        add(md_table(["Feature", "Rows that changed"], counts.most_common()))
        add("")
        add("Examples: " + "; ".join(examples))
    add("")
    print("Leak check:", "pass" if not counts else dict(counts))

    # 3. Gate reproduction ──────────────────────────────────────────────────
    add("## 3. Does the bench reproduce the app's back-test gate?")
    add("")
    since = today - timedelta(days=GATE_WINDOW_DAYS)

    def gpw_window():
        return stream_stock_inputs(["gpw"], since=since)

    if args.skip_gate or "gpw" not in markets:
        add("*Skipped.*")
    else:
        rows = []
        all_ok = True
        bench_last = {}
        for method_id in PRIMARY_METHODS:
            bench_all = reproduce_gate(gpw_window(), method_id, HORIZONS, today)
            if method_id == "vsa4":
                bench_last = bench_all
            for n in HORIZONS:
                app_nums = asyncio.run(_gate_numbers(method_id, n, today))
                bench = bench_all[n]
                edge_gap = abs((app_nums.avg_excess_pp or 0) - (bench.avg_excess_pp or 0))
                ok = (
                    app_nums.evaluated == bench.evaluated
                    and app_nums.win_rate_pct is not None
                    and bench.win_rate_pct is not None
                    and abs(app_nums.win_rate_pct - bench.win_rate_pct) <= _TOL_WIN_RATE_PP
                    and edge_gap <= _TOL_EDGE_PP
                )
                all_ok &= ok
                rows.append([method_id, n, _gate_cell(app_nums), _gate_cell(bench),
                             "✓" if ok else "✗"])
                verdict = "ok" if ok else "MISMATCH"
                print(f"Gate {method_id} {n}: app {app_nums} bench {bench} {verdict}")
        add(md_table(["Method", "Sessions", "App's gate (judged · hit rate · edge)",
                      "Bench", "Match"], rows))
        add("")
        add(("**PASS**" if all_ok else "**FAIL**")
            + f" — tolerance ±{_TOL_WIN_RATE_PP} pp hit rate, ±{_TOL_EDGE_PP} pp edge, "
              "identical count. Same window as the gate (last 1,460 days, GPW).")
        add("")

        # The gate reads VSA V4's whole history with today's price tolerance.
        crossing = total_gpw = 0
        for s in gpw_window():
            total_gpw += 1
            crossing += len({tick_size(float(b.close)) for b in s.bars}) > 1
        pit = reproduce_gate(gpw_window(), "vsa4", HORIZONS, today, vsa4_tick="point_in_time")
        add("### VSA V4 read point-in-time")
        add("")
        add("VSA V4 sizes its price tolerance from the **last** close it is given "
            "(0.01 at 10 zł or more, 0.001 from 1 zł, 0.0001 below). The gate reads "
            "four years of history with *today's* tolerance, so for a stock whose "
            "price has since crossed 10 zł or 1 zł the past is read with a figure "
            f"taken from a later price. **{crossing} of {total_gpw}** GPW companies "
            "crossed a level in the gate's window. The bench reads each day with that "
            "day's own tolerance (`features.vsa4_rows`), which is what the program "
            "would have said on the day:")
        add("")
        add(md_table(
            ["Sessions", "Gate as the app reads it", "Read point-in-time", "Difference"],
            [[n, _gate_cell(bench_last[n]), _gate_cell(pit[n]),
              f"{pit[n].evaluated - bench_last[n].evaluated:+d} firings"]
             for n in HORIZONS],
        ))
        add("")
        add("The AI layer's datasets use the point-in-time reading. Changing the app's "
            "own gate is outside Phase 0; it is recorded as a finding.")
    add("")

    # 4. Baselines ──────────────────────────────────────────────────────────
    print(f"Datasets: job1 {len(job1):,} rows, job2 {len(job2):,} rows.", flush=True)

    add("## 4. The unfiltered methods — the baseline every AI filter must beat")
    add("")
    add("**L1** = beat the stock's own market over *N* sessions, entering at the "
        "next open (the training label). **L2** = the app's gate frame. **L3** = "
        "the trade: 2×ATR stop, 3R target, *N*-session limit, costs 0.25% a side. "
        "Every firing in the stored history, all years.")
    add("")
    summary_rows = []
    summaries = {}
    for method_id in JOB1_METHODS:
        for n in HORIZONS:
            s = summarise_method(job1, method_id, n)
            summaries[(method_id, n)] = s
            ci = f"95% {fmt_pct(s.l1_ci[0])}–{fmt_pct(s.l1_ci[1])}"
            expectancy = fmt_num(s.l3_expectancy_r, signed=True)
            summary_rows.append([
                method_id, n, s.firings,
                f"{fmt_pct(s.l1_precision)} (n {s.l1_n}; {ci})",
                fmt_pp(s.l1_avg_excess_pct),
                f"{fmt_pct(s.l2_precision)} (n {s.l2_n})",
                fmt_pp(s.l2_avg_excess_pp),
                f"{fmt_pct(s.l3_win_rate)} · {expectancy} R (n {s.l3_n})",
            ])
    add(md_table(["Method", "Sessions", "Firings", "L1 precision", "L1 edge",
                  "L2 precision", "L2 edge", "L3 wins · expectancy"], summary_rows))
    add("")

    add("### How high does a random filter score?")
    add("")
    add("A filter that keeps a share of the signals **at random** changes the "
        "measured hit rate by chance alone. The 95th percentile below is the bar an "
        "AI filter keeping that share must clear before it means anything "
        "(L1, 30 sessions for VSA V4 and 10 for Weinstein — each one's gate-passing horizon).")
    add("")
    bar_rows = []
    for method_id, n in (("vsa4", 30), ("vsa4", 10), ("weinstein", 10)):
        rows_m = job1.loc[job1["method"] == method_id] if not job1.empty else job1
        if rows_m.empty:
            continue
        bar = random_filter_bar(rows_m[f"l1_y_{n}"])
        for rate, (mean, p95) in bar.items():
            bar_rows.append([method_id, n, f"{rate:.0%}", fmt_pct(mean), fmt_pct(p95),
                             fmt_pp((p95 - mean) * 100)])
    add(md_table(["Method", "Sessions", "Keep", "Random filter, mean",
                  "Random filter, 95th pct", "Luck alone adds"], bar_rows))
    add("")

    add("### Per year (L1 precision, primary methods)")
    add("")
    year_rows = []
    for method_id in PRIMARY_METHODS:
        for n in HORIZONS:
            for year, count, prec in summaries[(method_id, n)].by_year:
                if count:  # years before the market had 20 stocks have no L1 label
                    year_rows.append([method_id, n, year, count, fmt_pct(prec)])
    add(md_table(["Method", "Sessions", "Year", "Judged", "L1 precision"], year_rows))
    add("")

    add("### Job 2 sanity check")
    add("")
    for n in HORIZONS:
        y = job2[f"l1_y_{n}"].dropna()
        add(f"- {n} sessions: {len(y):,} stock-days; share beating their market "
            f"{fmt_pct(float(y.mean()) if len(y) else None)} — by construction "
            "close to 50%, a check that the label is built right.")
    add("")

    # 5. Verdict ────────────────────────────────────────────────────────────
    ensure_register()
    add("## 5. What this means")
    add("")
    add(f"- Trials recorded so far: **{trial_count()}** (no model has been tried yet).")
    add("- Until the history back-fill (decision D2) is approved, every result is a "
        "**pilot**: most companies hold under two years of bars, so a real gain of a "
        "few points cannot be told from luck (compare section 4's random-filter bar).")
    add("")
    peak = peak_memory_mb()
    add(f"*Built in {time.perf_counter() - started:.0f} s"
        + (f"; peak memory {peak:.0f} MB.*" if peak else ".*"))

    out_dir = AGENT_ML_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{today}-phase0-bench.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
