"""Honest validation for the AI layer — plan §6, design choices §4.

Everything a model result must survive before anyone believes it:

* ``walk_forward_folds`` — split by calendar year, train only on the past,
  purge labels that reach into the test year, embargo the sessions before it,
  and never touch the locked holdout.
* ``random_filter_precisions`` — what a filter that throws signals away *at
  random* scores. An AI filter has to beat this, not just "no filter".
* ``week_block_bootstrap`` — a confidence interval that resamples whole
  weeks, because signals fired on the same days are not independent.
* ``deflated_sharpe_probability`` / ``pbo_cscv`` — corrections for how many
  variants were tried (Bailey & López de Prado 2014; Bailey et al. 2017).
* ``truncation_check`` — proves a feature builder never looks ahead, by
  recomputing rows on histories cut off at that row.

Pure functions, no I/O; ``tests/test_ml_validation.py`` pins each one.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist

import numpy as np
import pandas as pd

from app.models import StooqDailyQuote

#: 30 sessions (the longer horizon) expressed in calendar days.
EMBARGO_DAYS = 45
MIN_TRAIN_YEARS = 3
BOOTSTRAP_SEED = 20260925
_EULER_GAMMA = 0.5772156649015329
_NORMAL = NormalDist()


# ── Walk-forward splits ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fold:
    """One walk-forward step: fit on the past, check on one calendar year.

    ``fit_idx`` and ``inner_idx`` split the training rows for early stopping,
    calibration and the threshold (the inner year is the last calendar year
    before the test year); ``train_idx`` is their union.
    """

    test_year: int
    train_idx: np.ndarray
    fit_idx: np.ndarray
    inner_idx: np.ndarray
    test_idx: np.ndarray


def holdout_start(freeze: date, days: int = 365) -> date:
    """The first day of the locked holdout: the last ``days`` before the freeze."""
    return freeze - timedelta(days=days)


def walk_forward_folds(
    dates: Sequence[date],
    label_end: Sequence[date | None],
    *,
    holdout_from: date | None = None,
    min_train_years: int = MIN_TRAIN_YEARS,
    embargo_days: int = EMBARGO_DAYS,
) -> list[Fold]:
    """Expanding-window folds, one per test calendar year.

    A row enters training only when its label window ends before the test year
    starts (**purge**) and it is dated at least ``embargo_days`` before it
    (**embargo**). Test rows are the test year's rows whose labels are complete
    and end before the holdout. Rows on or after ``holdout_from`` are never in
    any fold — the holdout is opened once, separately.
    """
    d = pd.to_datetime(pd.Series(list(dates)))
    end = pd.to_datetime(pd.Series(list(label_end)))
    has_label = end.notna().to_numpy()
    cutoff = pd.Timestamp(holdout_from) if holdout_from else None
    before_holdout = np.ones(len(d), dtype=bool)
    if cutoff is not None:
        before_holdout = (d < cutoff).to_numpy() & (end.isna() | (end < cutoff)).to_numpy()

    usable = has_label & before_holdout
    if not usable.any():
        return []
    years = d.dt.year.to_numpy()
    first_year = int(years[usable].min())
    last_year = int(years[usable].max())

    folds: list[Fold] = []
    for test_year in range(first_year + min_train_years, last_year + 1):
        start = pd.Timestamp(date(test_year, 1, 1))
        inner_start = pd.Timestamp(date(test_year - 1, 1, 1))
        test_mask = usable & (years == test_year)
        if not test_mask.any():
            continue
        train_mask = (
            usable
            & (d < start - pd.Timedelta(days=embargo_days)).to_numpy()
            & (end < start).to_numpy()
        )
        if not train_mask.any():
            continue
        inner_mask = train_mask & (d >= inner_start).to_numpy()
        fit_mask = (
            train_mask
            & (d < inner_start - pd.Timedelta(days=embargo_days)).to_numpy()
            & (end < inner_start).to_numpy()
        )
        folds.append(
            Fold(
                test_year=test_year,
                train_idx=np.flatnonzero(train_mask),
                fit_idx=np.flatnonzero(fit_mask),
                inner_idx=np.flatnonzero(inner_mask),
                test_idx=np.flatnonzero(test_mask),
            )
        )
    return folds


# ── Precision, the random filter, the bootstrap ───────────────────────────────


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a hit rate; (0, 1) when there is nothing to judge."""
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def random_filter_precisions(
    labels: np.ndarray,
    keep_rate: float,
    *,
    draws: int = 2000,
    seed: int = BOOTSTRAP_SEED,
) -> np.ndarray:
    """Precision of ``draws`` random filters that keep ``keep_rate`` of the signals.

    Its spread is the bar an AI filter must clear: keeping 40% of signals at
    random already moves the measured hit rate around by chance, and a real
    filter has to beat that noise, not merely beat "no filter".
    """
    y = np.asarray(labels, dtype=float)
    y = y[np.isfinite(y)]
    n = len(y)
    keep = max(1, int(round(keep_rate * n))) if n else 0
    if keep == 0:
        return np.zeros(0)
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    for i in range(draws):
        out[i] = y[rng.choice(n, size=keep, replace=False)].mean()
    return out


def week_block_bootstrap(
    dates: Sequence[date],
    values: np.ndarray,
    statistic: Callable[[np.ndarray, np.ndarray], float],
    *,
    n_boot: int = 2000,
    seed: int = BOOTSTRAP_SEED,
    level: float = 0.95,
) -> tuple[float, float, float]:
    """(estimate, low, high) of ``statistic`` with whole ISO weeks resampled.

    ``statistic(values, weights)`` receives the rows and how many times each
    was drawn, so any weighted mean or difference of means can be bootstrapped
    without copying rows around.
    """
    vals = np.asarray(values, dtype=float)
    weeks = np.array([f"{d.isocalendar().year}-{d.isocalendar().week}" for d in dates])
    unique, inverse = np.unique(weeks, return_inverse=True)
    estimate = statistic(vals, np.ones(len(vals)))
    if len(unique) < 2:
        return estimate, estimate, estimate
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        drawn = np.bincount(rng.integers(0, len(unique), len(unique)), minlength=len(unique))
        stats[b] = statistic(vals, drawn[inverse].astype(float))
    alpha = (1 - level) / 2
    return estimate, float(np.nanquantile(stats, alpha)), float(np.nanquantile(stats, 1 - alpha))


# ── Corrections for how many things were tried ────────────────────────────────


def expected_max_sharpe(n_trials: int, var_sharpe: float) -> float:
    """The Sharpe ratio the best of ``n_trials`` pure-noise strategies would show.

    Bailey & López de Prado (2014), eq. for SR₀ — the hurdle the Deflated
    Sharpe Ratio measures against. One trial has no selection, so the hurdle is 0.
    """
    if n_trials <= 1 or var_sharpe <= 0:
        return 0.0
    n = float(n_trials)
    return math.sqrt(var_sharpe) * (
        (1 - _EULER_GAMMA) * _NORMAL.inv_cdf(1 - 1 / n)
        + _EULER_GAMMA * _NORMAL.inv_cdf(1 - 1 / (n * math.e))
    )


def deflated_sharpe_probability(
    sharpe: float,
    n_obs: int,
    n_trials: int,
    var_sharpe: float,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Probability that the true Sharpe ratio beats the best-of-N-noise hurdle.

    ``sharpe`` is per period (not annualised), ``n_obs`` the number of periods,
    ``var_sharpe`` the variance of the Sharpe ratios across the trials,
    ``kurtosis`` the ordinary (not excess) kurtosis of the returns.
    """
    if n_obs < 2:
        return float("nan")
    hurdle = expected_max_sharpe(n_trials, var_sharpe)
    denom = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe * sharpe
    if denom <= 0:
        return float("nan")
    z = (sharpe - hurdle) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return _NORMAL.cdf(z)


def pbo_cscv(performance: np.ndarray, n_blocks: int = 16) -> tuple[float, np.ndarray]:
    """Probability of Backtest Overfitting by combinatorially symmetric CV.

    ``performance`` is periods × trials (e.g. weekly returns of each variant).
    The periods are cut into ``n_blocks`` blocks; for every way of choosing
    half of them as "in sample", the variant that looks best in sample is
    ranked out of sample. PBO is the share of splits in which it lands in the
    bottom half. Returns ``(pbo, logits)``; ~0.5 means "choosing the best did
    nothing", near 0 means the in-sample winner genuinely keeps winning.
    """
    m = np.asarray(performance, dtype=float)
    periods, trials = m.shape
    if trials < 2 or n_blocks < 2 or n_blocks % 2 or periods < n_blocks:
        return float("nan"), np.zeros(0)
    usable = periods - periods % n_blocks
    blocks = m[:usable].reshape(n_blocks, usable // n_blocks, trials)
    sums = blocks.sum(axis=1)
    squares = (blocks**2).sum(axis=1)
    per_block = usable // n_blocks
    total_sum = sums.sum(axis=0)
    total_sq = squares.sum(axis=0)

    def sharpe(s: np.ndarray, q: np.ndarray, count: int) -> np.ndarray:
        mean = s / count
        var = np.maximum(q / count - mean**2, 1e-18)
        return mean / np.sqrt(var)

    logits = []
    for chosen in itertools.combinations(range(n_blocks), n_blocks // 2):
        idx = list(chosen)
        is_s, is_q = sums[idx].sum(axis=0), squares[idx].sum(axis=0)
        count = per_block * len(idx)
        is_perf = sharpe(is_s, is_q, count)
        oos_perf = sharpe(total_sum - is_s, total_sq - is_q, usable - count)
        best = int(np.argmax(is_perf))
        below = np.sum(oos_perf < oos_perf[best])
        ties = np.sum(oos_perf == oos_perf[best]) - 1
        rank = 1 + below + 0.5 * ties
        omega = rank / (trials + 1)
        logits.append(math.log(omega / (1 - omega)))
    arr = np.array(logits)
    return float(np.mean(arr <= 0)), arr


# ── No look-ahead, checked ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Mismatch:
    """A feature whose value at a row changed when the future was removed."""

    position: int
    date: date
    column: str
    full: float
    truncated: float


def truncation_check(
    bars: Sequence[StooqDailyQuote],
    positions: Sequence[int],
    builder: Callable[[Sequence[StooqDailyQuote]], pd.DataFrame],
    columns: Sequence[str],
    *,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> list[Mismatch]:
    """Recompute rows on histories cut off at each position; report differences.

    A point-in-time builder gives row *t* the same value whether or not the
    bars after *t* exist. Any difference is look-ahead (or non-determinism)
    and is returned — an empty list is the pass.
    """
    ordered = sorted(bars, key=lambda b: b.date)
    full = builder(ordered)
    problems: list[Mismatch] = []
    for pos in positions:
        if pos < 0 or pos >= len(ordered):
            continue
        part = builder(ordered[: pos + 1])
        for col in columns:
            a = float(full[col].iloc[pos])
            b = float(part[col].iloc[pos])
            if math.isnan(a) and math.isnan(b):
                continue
            if math.isnan(a) != math.isnan(b) or not math.isclose(a, b, rel_tol=rtol, abs_tol=atol):
                problems.append(Mismatch(pos, ordered[pos].date, col, a, b))
    return problems
