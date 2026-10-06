"""Phase 1 of the AI layer: the logistic-regression pilot (plan §15).

Reads the datasets ``scripts/ml_build_dataset.py`` wrote (never the network),
walks forward year by year with the rules frozen in
``agent/ml/DESIGN-CHOICES.md`` §6, **records every variant in the trial
register**, and writes ``agent/ml/reports/<date>-phase1-logistic.md``.

On the server (decision D6, after ``bash deploy/ml-run.sh dataset``)::

    bash deploy/ml-run.sh train

On a PC, from ``backend-python/`` (after ``ml_build_dataset``)::

    .venv/Scripts/python.exe -m scripts.ml_train

Every run on real data is recorded — there is no unrecorded mode. A run is a
measurement, and a variant tried and forgotten still counts against the one
that is finally reported (plan §6.4).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date

import numpy as np

from app.ml import AGENT_ML_DIR, ML_DATA_DIR
from app.ml.data_access import parse_markets, peak_memory_mb
from app.ml.dataset import HORIZONS, PRIMARY_METHODS, read_datasets
from app.ml.phase1 import (
    C_GRID,
    FREEZE_DATE,
    Run,
    coefficient_review,
    input_columns,
    kept_trade_sharpe,
    monthly_returns,
    run_hand_rule,
    run_job1,
    run_job2,
    summarise_filter,
    summarise_score,
)
from app.ml.report import fmt_num, fmt_pct, md_table
from app.ml.trials import TRIALS_FILE, append_trial, trial_count
from app.ml.validation import deflated_sharpe_probability, holdout_start, pbo_cscv

# Module-level so the end-to-end test can point them at a temporary folder.
DATA_DIR = ML_DATA_DIR
REPORTS_DIR = AGENT_ML_DIR / "reports"
TRIALS_PATH = TRIALS_FILE


def _backfilled() -> str | None:
    """The date of the latest history back-fill report, or None when none ran."""
    reports = sorted(DATA_DIR.glob("backfill-report-*.json"))
    return reports[-1].stem.removeprefix("backfill-report-") if reports else None


def _load(markets: list[str], job: int):
    # Only the columns a run reads: the rest of a back-filled table is memory
    # the server's cap cannot spare.
    frame, metas = read_datasets(DATA_DIR, markets, job, columns=input_columns(job))
    sha = "+".join(m.get("sha256", "?")[:12] for m in metas)
    return frame, {"sha256": sha}


def _gain_cell(s) -> str:
    if s.gain_pp is None:
        return "—"
    ci = f" (95% {s.gain_ci[0]:+.1f} … {s.gain_ci[1]:+.1f})" if s.gain_ci else ""
    return f"{s.gain_pp:+.2f} pp{ci}"


def _filter_row(label: str, s) -> list[str]:
    return [
        label,
        str(s.rows),
        f"{s.kept} ({fmt_pct(s.keep_rate, 0)})",
        f"{fmt_pct(s.kept_precision)} ({fmt_pct(s.kept_ci[0])}–{fmt_pct(s.kept_ci[1])})",
        fmt_pct(s.random_p95),
        "**yes**" if s.beats_random else "no",
        _gain_cell(s),
        f"{fmt_num(s.r_unfiltered, signed=True)} → {fmt_num(s.r_kept, signed=True)}",
        fmt_num(s.auc, 3),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 1: logistic-regression pilot.")
    parser.add_argument("--markets", default="gpw", help="gpw (default), a list, or all")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    markets = parse_markets(args.markets)
    try:
        job1, meta1 = _load(markets, 1)
        job2, meta2 = _load(markets, 2)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    holdout = holdout_start(FREEZE_DATE)
    print(f"Job 1: {len(job1):,} firings; Job 2: {len(job2):,} stock-days; "
          f"holdout from {holdout} (untouched).")

    # ── Run every variant ────────────────────────────────────────────────
    job1_runs: dict[int, list[Run]] = {}
    shuffled: dict[int, Run] = {}
    job2_runs: dict[int, list[Run]] = {}
    for n in HORIZONS:
        runs = [run_hand_rule(job1, n, holdout_from=holdout)]
        for c in C_GRID:
            runs.append(run_job1(job1, n, c, holdout_from=holdout))
            print(f"  job 1, {n} sessions, C={c}: done")
        job1_runs[n] = runs
        shuffled[n] = run_job1(job1, n, 0.1, holdout_from=holdout, shuffle_labels=True)
        job2_runs[n] = []
        for c in C_GRID:
            job2_runs[n].append(run_job2(job2, n, c, holdout_from=holdout))
            print(f"  job 2, {n} sessions, C={c}: done")

    years = sorted({f.test_year for runs in job1_runs.values() for r in runs for f in r.folds})
    folds_label = ",".join(str(y) for y in years)
    backfill = _backfilled()
    scope = f"back-filled {backfill}" if backfill else "pilot (no back-fill)"
    notes = f"{scope}; dataset {meta1.get('sha256', '?')[:12]}"

    # ── The trials (recorded only after the report is written) ──────────
    trial_rows: list[dict] = []
    job1_summary: dict[tuple[int, str], object] = {}
    for n, runs in job1_runs.items():
        for run in runs:
            s = summarise_filter(run.oos)
            job1_summary[(n, run.name)] = s
            trial_rows.append({
                "phase": 1, "job": 1, "horizon": n, "label": "L1",
                "model": "hand-rule" if run.c is None else "logistic",
                "params": "weekly_agree=+1 & rs_pct>=0.5" if run.c is None else f"C={run.c}",
                "feature_set": "v1", "markets": ",".join(markets), "folds": folds_label,
                "oos_precision_gain_pp": None if s.gain_pp is None else round(s.gain_pp, 3),
                "oos_expectancy_r": None if s.r_kept is None else round(s.r_kept, 4),
                "auc": None if np.isnan(s.auc) else round(s.auc, 4),
                "keep_rate": None if s.keep_rate is None else round(s.keep_rate, 3),
                "notes": notes,
            })
    job2_summary: dict[tuple[int, float], object] = {}
    for n, runs in job2_runs.items():
        for run in runs:
            s = summarise_score(run.oos)
            job2_summary[(n, run.c)] = s
            trial_rows.append({
                "phase": 1, "job": 2, "horizon": n, "label": "L1", "model": "logistic",
                "params": f"C={run.c}", "feature_set": "v1", "markets": ",".join(markets),
                "folds": folds_label, "auc": round(s.auc, 4), "brier": round(s.brier, 4),
                "notes": f"{scope}; dataset {meta2.get('sha256', '?')[:12]}",
            })
    # This run's trials count too — the hurdle includes them.
    total_trials = trial_count(TRIALS_PATH) + len(trial_rows)

    # ── Overfitting statistics per horizon ──────────────────────────────
    overfit_rows = []
    for n, runs in job1_runs.items():
        stats = [(run.name, *kept_trade_sharpe(run.oos)) for run in runs]
        sharpes = [s[1] for s in stats if np.isfinite(s[1])]
        best = max(stats, key=lambda s: s[1] if np.isfinite(s[1]) else -np.inf)
        var = float(np.var(sharpes)) if len(sharpes) > 1 else 0.0
        dsr = deflated_sharpe_probability(best[1], best[2], total_trials, var,
                                          skew=best[3], kurtosis=best[4])
        matrix = monthly_returns(runs)
        blocks = min(16, matrix.shape[0] - matrix.shape[0] % 2)
        pbo = pbo_cscv(matrix, n_blocks=blocks)[0] if blocks >= 4 else float("nan")
        overfit_rows.append([n, best[0], fmt_num(best[1], 3), best[2],
                             fmt_num(dsr, 2), fmt_num(pbo, 2), matrix.shape[0]])

    # ── The report ──────────────────────────────────────────────────────
    lines: list[str] = []
    add = lines.append
    add(f"# AI layer — Phase 1 pilot: logistic regression, {date.today()}")
    add("")
    if backfill:
        data_note = (f"The stored history was back-filled (latest back-fill report {backfill}); "
                     f"test years {folds_label}.")
    else:
        data_note = ("**Pilot**: the history back-fill (decision D2) has not run, so the "
                     f"test years ({folds_label}) are thin and, before 2025, drawn from the "
                     "few companies whose pages were opened.")
    add("*Written by `backend-python/scripts/ml_train.py`. Rules frozen before the "
        f"first fit: `agent/ml/DESIGN-CHOICES.md` §6. {data_note} The holdout "
        f"(from {holdout}) was not touched.*")
    add("")

    add("## 1. In plain words")
    add("")
    for n in HORIZONS:
        beating = [name for (h, name), s in job1_summary.items() if h == n and s.beats_random
                   and name != "hand rule"]
        base = job1_summary[(n, "hand rule")]
        add(f"- **Signal filter, {n} sessions:** unfiltered, "
            f"{fmt_pct(base.unfiltered_precision)} of the {base.rows} VSA V4 / Weinstein "
            f"firings in the test years beat their market. "
            + (f"{len(beating)} of {len(C_GRID)} model variants kept a share that did better "
               "than a random filter's 95th percentile"
               if beating else "No model variant beat what a random filter reaches by luck")
            + ".")
    for n in HORIZONS:
        best2 = max((job2_summary[(n, c)] for c in C_GRID), key=lambda s: s.auc)
        add(f"- **Learned score, {n} sessions:** best AUC {best2.auc:.3f} "
            f"(95% {best2.auc_ci[0]:.3f}–{best2.auc_ci[1]:.3f}) against "
            f"{best2.auc_vsa_rating:.3f} for the VSA rating alone and "
            f"{best2.auc_rs_pct:.3f} for relative strength alone (0.5 = a coin).")
    shuffled_auc = {n: summarise_filter(shuffled[n].oos).auc for n in HORIZONS}
    add("- **Sanity check:** trained on shuffled labels, the filter scored AUC "
        + " and ".join(f"{shuffled_auc[n]:.3f} at {n} sessions" for n in HORIZONS)
        + " — close to 0.5 is the pass.")
    add(f"- **Trials recorded so far: {total_trials}.** Every number below is corrected "
        "for that count where it matters (section 5).")
    add("")

    add("## 2. Job 1 — the signal filter")
    add("")
    add("Out of sample: each test year is scored by a model fitted on the years before "
        "it, with the cut chosen on the last training year. \"Beats random\" = the kept "
        "firings' hit rate is above the 95th percentile of 2,000 random filters keeping "
        "the same share.")
    add("")
    for n in HORIZONS:
        add(f"### {n} sessions")
        add("")
        rows = [_filter_row(run.name, job1_summary[(n, run.name)]) for run in job1_runs[n]]
        rows.append(_filter_row("sanity: shuffled labels", summarise_filter(shuffled[n].oos)))
        add(md_table(["Variant", "Judged", "Kept", "Hit rate of kept (95%)",
                      "Random 95th pct", "Beats random", "Gain vs all",
                      "L3 R: all → kept", "AUC"], rows))
        add("")
        per_method = []
        for method in PRIMARY_METHODS:
            for run in job1_runs[n][1:]:
                s = summarise_filter(run.oos, [method])
                if s.rows:
                    per_method.append([method, run.name, s.rows,
                                       fmt_pct(s.unfiltered_precision),
                                       f"{fmt_pct(s.kept_precision)} "
                                       f"({fmt_pct(s.keep_rate, 0)} kept)",
                                       "yes" if s.beats_random else "no", fmt_num(s.auc, 3)])
        add(md_table(["Method", "Variant", "Judged", "Unfiltered", "Kept", "Beats random", "AUC"],
                     per_method))
        add("")
        fold_rows = [[f.test_year, f.fit_rows, f.inner_rows, f.test_rows,
                      fmt_pct(f.keep_rate, 0) if f.keep_rate else "—", f.how or f.skipped]
                     for f in job1_runs[n][2].folds]
        add(f"Folds (C={job1_runs[n][2].c}):")
        add("")
        add(md_table(["Test year", "Fit rows", "Inner rows", "Test firings", "Keep",
                      "Cut chosen by"], fold_rows))
        add("")

    add("## 3. Job 2 — the learned score")
    add("")
    job2_rows = []
    for n in HORIZONS:
        for c in C_GRID:
            s = job2_summary[(n, c)]
            job2_rows.append([n, f"C={c}", f"{s.rows:,}",
                              f"{s.auc:.3f} ({s.auc_ci[0]:.3f}–{s.auc_ci[1]:.3f})",
                              f"{s.brier:.4f}", f"{fmt_pct(s.top10)} vs {fmt_pct(s.base_rate)}",
                              f"{s.auc_vsa_rating:.3f}", f"{s.auc_rs_pct:.3f}"])
    add(md_table(["Sessions", "Variant", "Test stock-days", "AUC (95%)", "Brier",
                  "Top 10% beat market vs all", "AUC: VSA rating", "AUC: RS"], job2_rows))
    add("")

    add("## 4. Coefficient review (C=0.1, 30 sessions)")
    add("")
    add("Mean standardised weight across the test folds, how many folds agree on its "
        "sign, and whether it points the way the source material expects. A ✗ is "
        "checked as a possible data bug before it is read as a finding.")
    add("")
    reviewed = (("Job 1 — the filter", job1_runs[30][2]), ("Job 2 — the score", job2_runs[30][1]))
    for title, run in reviewed:
        add(f"### {title}")
        add("")
        add(md_table(["Feature", "Weight", "Folds agreeing", "Theory", "Expected because"],
                     [[f, f"{w:+.3f}", fmt_pct(a, 0), v, why]
                      for f, w, a, v, why in coefficient_review(run)]))
        add("")

    add("## 5. Corrected for how much was tried")
    add("")
    add(md_table(["Sessions", "Best Job-1 variant (per-trade Sharpe)", "Sharpe", "Trades",
                  "Deflated-Sharpe probability", "PBO", "Months"], overfit_rows))
    add("")
    add(f"The Deflated Sharpe probability uses the whole register ({total_trials} trials). "
        "Read it carefully: it asks whether the best variant's kept trades earn **more "
        "than zero** after correcting for how many variants were tried — not whether the "
        "filter beat the unfiltered firings, which already earn what section 2's \"L3 R: "
        "all\" column shows. PBO compares the Job-1 variants month by month: above 0.5 "
        "means that picking the variant that looked best in one half of the months tends "
        "to pick a worse one in the other half. With only four variants it is a weak "
        "test, reported for completeness.")
    add("")
    peak = peak_memory_mb()
    add(f"*Built in {time.perf_counter() - started:.0f} s"
        + (f"; peak memory {peak:.0f} MB.*" if peak else ".*"))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{date.today()}-phase1-logistic.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Recorded last: a run that crashed above has recorded nothing.
    for row in trial_rows:
        append_trial(row, TRIALS_PATH)
    print(f"Wrote {out}; trials in register: {trial_count(TRIALS_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
