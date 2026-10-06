"""Phase 1 — the logistic-regression pilot (plan §15, design choices §6).

Two questions, answered out of sample, one calendar year at a time:

* **Job 1 — the signal filter.** Among VSA V4's and Weinstein's firings, can a
  model trained on earlier years pick the ones that beat their market? The
  filter keeps the firings scored above a cut chosen on the last training
  year; it is judged against the same firings unfiltered, a random filter
  with the same keep-rate, and one simple hand rule.
* **Job 2 — the learned score.** On every 5th session of every stock, does
  the model's probability rank stocks better than the VSA rating or relative
  strength alone?

Everything is fitted on the fold's training rows only — the preprocessing,
the model, the threshold. The test year is scored once and never looked at
while choosing anything. ``tests/test_ml_phase1.py`` pins that on synthetic
data with a planted signal and with pure noise.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.ml.dataset import (
    FEATURE_COLUMNS,
    HORIZONS,
    JOB1_FEATURE_COLUMNS,
    PRIMARY_METHODS,
    as_dates,
)
from app.ml.metrics import brier, roc_auc, top_fraction_precision
from app.ml.models.logistic import LogisticRegression, Preprocessor
from app.ml.theory import EXPECTED_SIGNS, verdict
from app.ml.validation import (
    random_filter_precisions,
    walk_forward_folds,
    week_block_bootstrap,
    wilson_interval,
)

FREEZE_DATE = date(2026, 9, 26)
C_GRID: tuple[float, ...] = (0.01, 0.1, 1.0)
KEEP_GRID: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
MIN_KEPT_INNER = 20
DEFAULT_KEEP = 0.5
MAX_METHOD_SHARE = 0.5
MIN_FIT_ROWS = 50
SHUFFLE_SEED = 20260926
_LEVELS = {"sector": 11, "setup": 10, "method": 10, "market": 10}


# ── Data ──────────────────────────────────────────────────────────────────────


#: What the runs read besides the model's inputs, which stay in ``frame``.
_CARRIED = ("ticker", "method", "weekly_agree", "rs_pct", "vsa_rating")
_CATEGORICAL = {1: ["market", "sector", "method", "setup"], 2: ["market", "sector"]}


def input_columns(job: int, horizons: Sequence[int] = HORIZONS) -> list[str]:
    """Every column a Phase-1 run of ``job`` reads; ``ml_train`` loads only these."""
    features = JOB1_FEATURE_COLUMNS if job == 1 else FEATURE_COLUMNS
    labels = [f"{name}_{n}" for n in horizons for name in ("l1_y", "l3_r", "fwd_end")]
    wanted = [*features, *_CATEGORICAL[job], *_CARRIED, "date", *labels]
    return list(dict.fromkeys(wanted))


def prepare(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """The rows with an L1 label at ``horizon``: real dates and label ends, the
    columns the runs read, and ``_pos`` — each row's position in ``frame``.

    The model's inputs are not copied here: the scaler reads them from
    ``frame`` by position. A copy of every labelled row — every column — was a
    quarter of what training held on a back-filled GPW history.
    """
    pos = np.flatnonzero(frame[f"l1_y_{horizon}"].notna().to_numpy())
    kept = [c for c in (*_CARRIED, f"l1_y_{horizon}", f"l3_r_{horizon}") if c in frame]
    data = pd.DataFrame({c: frame[c].to_numpy()[pos] for c in kept})
    data["date"] = as_dates(frame["date"].to_numpy()[pos])
    data["label_end"] = as_dates(frame[f"fwd_end_{horizon}"].to_numpy()[pos])
    data["_pos"] = pos
    return data


def method_weights(methods: Sequence[str], cap: float = MAX_METHOD_SHARE) -> np.ndarray:
    """Sample weights so no single method carries more than ``cap`` of the total."""
    methods = np.asarray(methods, dtype=str)
    weights = np.ones(len(methods))
    counts = Counter(methods.tolist())
    total = len(methods)
    if len(counts) < 2:
        return weights
    for method, n in counts.items():
        if n / total > cap:
            others = total - n
            weights[methods == method] = cap / (1 - cap) * others / n
    return weights


def choose_keep_rate(
    scores: np.ndarray, r_net: np.ndarray, primary: np.ndarray
) -> tuple[float, float, str]:
    """(keep-rate, probability cut, how) chosen on the inner year.

    The keep-rate with the best mean L3 R among the kept primary firings,
    needing at least ``MIN_KEPT_INNER`` of them; otherwise the default 50%.
    """
    s = np.asarray(scores, dtype=float)[primary]
    r = np.asarray(r_net, dtype=float)[primary]
    if len(s) == 0:
        return DEFAULT_KEEP, 0.5, "default (no inner firings)"
    best: tuple[float, float, float] | None = None  # (mean R, keep, cut)
    for keep in KEEP_GRID:
        cut = float(np.quantile(s, 1 - keep)) if keep < 1 else float(s.min())
        kept = (s >= cut) & np.isfinite(r)
        if kept.sum() < MIN_KEPT_INNER:
            continue
        mean_r = float(r[kept].mean())
        if best is None or mean_r > best[0] or (mean_r == best[0] and keep > best[1]):
            best = (mean_r, keep, cut)
    if best is None:
        cut = float(np.quantile(s, 1 - DEFAULT_KEEP))
        return DEFAULT_KEEP, cut, "default (too few inner firings)"
    return best[1], best[2], "best inner-year R"


def _job1_preprocessor() -> Preprocessor:
    return Preprocessor(
        numeric=JOB1_FEATURE_COLUMNS,
        categorical=["market", "sector", "method", "setup"],
        max_levels=_LEVELS,
    )


def _job2_preprocessor() -> Preprocessor:
    return Preprocessor(
        numeric=FEATURE_COLUMNS, categorical=["market", "sector"], max_levels=_LEVELS
    )


# ── Job 1: the signal filter ──────────────────────────────────────────────────


@dataclass
class FoldNote:
    test_year: int
    fit_rows: int
    inner_rows: int
    test_rows: int
    keep_rate: float | None = None
    cut: float | None = None
    how: str = ""
    skipped: str = ""


@dataclass
class Run:
    """One variant's out-of-sample record across every test year."""

    name: str
    job: int
    horizon: int
    c: float | None
    oos: pd.DataFrame
    folds: list[FoldNote] = field(default_factory=list)
    coefs: pd.DataFrame = field(default_factory=pd.DataFrame)


def run_job1(
    frame: pd.DataFrame,
    horizon: int,
    c: float,
    *,
    holdout_from: date,
    primary: Sequence[str] = PRIMARY_METHODS,
    shuffle_labels: bool = False,
) -> Run:
    """Walk forward through the years: fit, choose the cut, score the test year."""
    data = prepare(frame, horizon)
    folds = walk_forward_folds(data["date"], data["label_end"], holdout_from=holdout_from)
    y = data[f"l1_y_{horizon}"].to_numpy(dtype=float)
    r_net = data[f"l3_r_{horizon}"].to_numpy(dtype=float)
    methods = data["method"].astype(str).to_numpy()
    is_primary = np.isin(methods, list(primary))
    pos = data["_pos"].to_numpy()
    rng = np.random.default_rng(SHUFFLE_SEED)

    parts, notes, coefs = [], [], {}
    for fold in folds:
        test_idx = fold.test_idx[is_primary[fold.test_idx]]
        note = FoldNote(fold.test_year, len(fold.fit_idx), len(fold.inner_idx), len(test_idx))
        notes.append(note)
        y_fit = y[fold.fit_idx]
        if len(fold.fit_idx) < MIN_FIT_ROWS or len(set(y_fit.tolist())) < 2:
            note.skipped = "too little training data"
            continue
        if not len(test_idx):
            note.skipped = "no test firings"
            continue
        if shuffle_labels:
            y_fit = rng.permutation(y_fit)
        # Rows are passed by position: copying a fold's rows (every column)
        # for each step is what a server's memory cap cannot afford.
        pre = _job1_preprocessor().fit(frame, pos[fold.fit_idx])
        model = LogisticRegression(c=c).fit(
            pre.transform(frame, pos[fold.fit_idx]), y_fit, method_weights(methods[fold.fit_idx])
        )
        if len(fold.inner_idx):
            inner_scores = model.predict_proba(pre.transform(frame, pos[fold.inner_idx]))
            keep, cut, how = choose_keep_rate(
                inner_scores, r_net[fold.inner_idx], is_primary[fold.inner_idx]
            )
        else:
            keep, cut, how = DEFAULT_KEEP, 0.5, "default (no inner year)"
        note.keep_rate, note.cut, note.how = keep, cut, how
        scores = model.predict_proba(pre.transform(frame, pos[test_idx]))
        parts.append(_oos_frame(data, test_idx, y, r_net, scores, scores >= cut, fold.test_year))
        coefs[fold.test_year] = pd.Series(model.coef_, index=pre.feature_names)

    name = f"logistic C={c}" + (" (shuffled labels)" if shuffle_labels else "")
    return Run(name, 1, horizon, c, _concat(parts), notes, pd.DataFrame(coefs))


def run_hand_rule(frame: pd.DataFrame, horizon: int, *, holdout_from: date,
                  primary: Sequence[str] = PRIMARY_METHODS) -> Run:
    """The baseline rule: weekly read confirms and relative strength in the top half."""
    data = prepare(frame, horizon)
    folds = walk_forward_folds(data["date"], data["label_end"], holdout_from=holdout_from)
    y = data[f"l1_y_{horizon}"].to_numpy(dtype=float)
    r_net = data[f"l3_r_{horizon}"].to_numpy(dtype=float)
    is_primary = np.isin(data["method"].astype(str).to_numpy(), list(primary))
    rule = ((data["weekly_agree"] == 1) & (data["rs_pct"] >= 0.5)).to_numpy()
    parts, notes = [], []
    for fold in folds:
        test_idx = fold.test_idx[is_primary[fold.test_idx]]
        notes.append(FoldNote(fold.test_year, 0, 0, len(test_idx), how="fixed rule"))
        if len(test_idx) and len(fold.fit_idx) >= MIN_FIT_ROWS:
            kept = rule[test_idx]
            parts.append(
                _oos_frame(data, test_idx, y, r_net, kept.astype(float), kept, fold.test_year)
            )
    return Run("hand rule", 1, horizon, None, _concat(parts), notes)


def _oos_frame(data, idx, y, r_net, scores, kept, year) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": data["date"].to_numpy()[idx],
            "ticker": data["ticker"].to_numpy()[idx],
            "method": data["method"].to_numpy()[idx] if "method" in data else "",
            "y": y[idx],
            "r": r_net[idx],
            "score": scores,
            "kept": np.asarray(kept, dtype=bool),
            "test_year": year,
        }
    )


def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
    columns = ["date", "ticker", "method", "y", "r", "score", "kept", "test_year"]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)


# ── Job 2: the learned score ──────────────────────────────────────────────────


def run_job2(frame: pd.DataFrame, horizon: int, c: float, *, holdout_from: date) -> Run:
    """Walk forward on the stock-day panel; keep each test row's probability."""
    data = prepare(frame, horizon)
    folds = walk_forward_folds(data["date"], data["label_end"], holdout_from=holdout_from)
    y = data[f"l1_y_{horizon}"].to_numpy(dtype=float)
    pos = data["_pos"].to_numpy()
    parts, notes, coefs = [], [], {}
    for fold in folds:
        note = FoldNote(fold.test_year, len(fold.fit_idx), 0, len(fold.test_idx))
        notes.append(note)
        if len(fold.fit_idx) < MIN_FIT_ROWS or len(set(y[fold.fit_idx].tolist())) < 2:
            note.skipped = "too little training data"
            continue
        pre = _job2_preprocessor().fit(frame, pos[fold.fit_idx])
        model = LogisticRegression(c=c).fit(
            pre.transform(frame, pos[fold.fit_idx]), y[fold.fit_idx]
        )
        idx = fold.test_idx
        parts.append(
            pd.DataFrame(
                {
                    "date": data["date"].to_numpy()[idx],
                    "y": y[idx],
                    "score": model.predict_proba(pre.transform(frame, pos[idx])),
                    "vsa_rating": data["vsa_rating"].to_numpy(dtype=float)[idx],
                    "rs_pct": data["rs_pct"].to_numpy(dtype=float)[idx],
                    "test_year": fold.test_year,
                }
            )
        )
        coefs[fold.test_year] = pd.Series(model.coef_, index=pre.feature_names)
    oos = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return Run(f"logistic C={c}", 2, horizon, c, oos, notes, pd.DataFrame(coefs))


# ── Summaries ─────────────────────────────────────────────────────────────────


@dataclass
class FilterSummary:
    rows: int
    unfiltered_precision: float | None
    kept: int
    keep_rate: float | None
    kept_precision: float | None
    kept_ci: tuple[float, float]
    random_p95: float | None
    gain_pp: float | None
    gain_ci: tuple[float, float] | None
    r_unfiltered: float | None
    r_kept: float | None
    auc: float
    beats_random: bool


def _mean(values: np.ndarray) -> float | None:
    values = values[np.isfinite(values)]
    return float(values.mean()) if len(values) else None


def summarise_filter(oos: pd.DataFrame, methods: Sequence[str] | None = None) -> FilterSummary:
    """How the kept firings compare with all of them, with a random filter and luck."""
    rows = oos if methods is None else oos.loc[oos["method"].isin(list(methods))]
    y = rows["y"].to_numpy(dtype=float)
    kept = rows["kept"].to_numpy(dtype=bool)
    r = rows["r"].to_numpy(dtype=float)
    n, k = len(y), int(kept.sum())
    if n == 0:
        return FilterSummary(0, None, 0, None, None, (0.0, 1.0), None, None, None,
                             None, None, float("nan"), False)
    keep_rate = k / n
    kept_prec = float(y[kept].mean()) if k else None
    random_p95 = None
    if 0 < k < n:
        draws = random_filter_precisions(y, keep_rate)
        random_p95 = float(np.quantile(draws, 0.95))
    gain = (kept_prec - float(y.mean())) * 100 if kept_prec is not None else None
    gain_ci = None
    if k and k < n:
        encoded = y + 2 * kept

        def diff(values: np.ndarray, weights: np.ndarray) -> float:
            yy, kk = values % 2, values >= 2
            w_all, w_kept = weights.sum(), weights[kk].sum()
            if w_all == 0 or w_kept == 0:
                return float("nan")
            kept_rate = np.sum(yy[kk] * weights[kk]) / w_kept
            return float((kept_rate - np.sum(yy * weights) / w_all) * 100)

        _, lo, hi = week_block_bootstrap(list(rows["date"]), encoded, diff, n_boot=1000)
        gain_ci = (lo, hi)
    return FilterSummary(
        rows=n,
        unfiltered_precision=float(y.mean()),
        kept=k,
        keep_rate=keep_rate,
        kept_precision=kept_prec,
        kept_ci=wilson_interval(int(y[kept].sum()), k),
        random_p95=random_p95,
        gain_pp=gain,
        gain_ci=gain_ci,
        r_unfiltered=_mean(r),
        r_kept=_mean(r[kept]),
        auc=roc_auc(y, rows["score"].to_numpy(dtype=float)),
        beats_random=bool(
            kept_prec is not None and random_p95 is not None and kept_prec > random_p95
        ),
    )


@dataclass
class ScoreSummary:
    rows: int
    auc: float
    auc_ci: tuple[float, float]
    brier: float
    top10: float
    base_rate: float
    auc_vsa_rating: float
    auc_rs_pct: float


def summarise_score(oos: pd.DataFrame) -> ScoreSummary:
    """Job 2: ranking quality against the VSA rating and relative strength."""
    y = oos["y"].to_numpy(dtype=float)
    score = oos["score"].to_numpy(dtype=float)
    encoded = np.column_stack([y, score])

    def auc_of(values: np.ndarray, weights: np.ndarray) -> float:
        # Resampled weeks enter as repeated rows (weights are draw counts).
        reps = weights.astype(int)
        return roc_auc(np.repeat(values[:, 0], reps), np.repeat(values[:, 1], reps))

    est, lo, hi = week_block_bootstrap(list(oos["date"]), encoded, auc_of, n_boot=300)
    return ScoreSummary(
        rows=len(y),
        auc=est,
        auc_ci=(lo, hi),
        brier=brier(y, score),
        top10=top_fraction_precision(y, score, 0.1),
        base_rate=float(y.mean()) if len(y) else float("nan"),
        auc_vsa_rating=roc_auc(y, oos["vsa_rating"].to_numpy(dtype=float)),
        auc_rs_pct=roc_auc(y, oos["rs_pct"].to_numpy(dtype=float)),
    )


def coefficient_review(run: Run, top: int = 20) -> list[tuple[str, float, float, str, str]]:
    """(feature, mean weight, share of folds with that sign, theory verdict, why).

    The ``top`` largest weights, plus every feature theory has a view on.
    """
    if run.coefs.empty:
        return []
    mean = run.coefs.mean(axis=1, skipna=True)
    signs = np.sign(run.coefs)
    same_sign = signs.eq(np.sign(mean), axis=0) & run.coefs.notna()
    agree = same_sign.sum(axis=1) / run.coefs.notna().sum(axis=1)
    order = mean.abs().sort_values(ascending=False)
    chosen = list(order.index[:top]) + [f for f in EXPECTED_SIGNS if f in mean.index]
    seen, out = set(), []
    for feature in chosen:
        if feature in seen:
            continue
        seen.add(feature)
        why = EXPECTED_SIGNS.get(feature, (0, ""))[1]
        out.append((feature, float(mean[feature]), float(agree[feature]),
                    verdict(feature, float(mean[feature])), why))
    return out


def kept_trade_sharpe(oos: pd.DataFrame) -> tuple[float, int, float, float]:
    """Per-trade Sharpe, trade count, skew and (ordinary) kurtosis of kept L3 R."""
    r = oos.loc[oos["kept"], "r"].to_numpy(dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3 or r.std() == 0:
        return float("nan"), len(r), 0.0, 3.0
    z = (r - r.mean()) / r.std()
    return float(r.mean() / r.std()), len(r), float(np.mean(z**3)), float(np.mean(z**4))


def monthly_returns(runs: Sequence[Run]) -> np.ndarray:
    """Months × variants: mean L3 R of each variant's kept firings (0 if none)."""
    frames = []
    for run in runs:
        kept = run.oos.loc[run.oos["kept"] & np.isfinite(run.oos["r"].astype(float))]
        months = pd.to_datetime(pd.Series(kept["date"])).dt.to_period("M")
        frames.append(kept.groupby(months.to_numpy())["r"].mean().rename(run.name))
    if not frames:
        return np.zeros((0, 0))
    table = pd.concat(frames, axis=1).sort_index().fillna(0.0)
    return table.to_numpy(dtype=float)


def is_finite(value: float | None) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))
