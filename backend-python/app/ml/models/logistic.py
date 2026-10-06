"""L2-penalised logistic regression and its preprocessing — plan §19.3, Phase 1.

Written in plain numpy on purpose: Phase 1 adds **no library** to the project
(decision D3 is left for Phase 2's trees). A logistic regression is small
enough to fit exactly with Newton's method, and its weights can be read —
each one says how much a measurement moves the odds, which is what the
coefficient review in the Phase-1 report checks against VSA theory.

``Preprocessor`` is fitted on **training rows only** (medians, category
levels, means and spreads), then applied unchanged to later rows — fitting it
on everything would leak the test period's scale into training.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_OTHER = "__other__"


@dataclass
class Preprocessor:
    """Numeric + categorical columns → one standardised matrix.

    * numeric: a gap is filled with the training median, and a column that had
      any gap gains a 0/1 "was missing" flag;
    * categorical: one-hot over the ``max_levels`` most common training values,
      everything else (including values never seen in training) in one
      "other" column;
    * then every column is z-scored with the training mean and spread, and a
      column constant in training is dropped.
    """

    numeric: Sequence[str]
    categorical: Sequence[str] = ()
    max_levels: dict[str, int] = field(default_factory=dict)
    default_levels: int = 11

    medians_: dict[str, float] = field(default_factory=dict, init=False)
    flagged_: list[str] = field(default_factory=list, init=False)
    levels_: dict[str, list[str]] = field(default_factory=dict, init=False)
    means_: np.ndarray | None = field(default=None, init=False)
    stds_: np.ndarray | None = field(default=None, init=False)
    keep_: np.ndarray | None = field(default=None, init=False)
    names_: list[str] = field(default_factory=list, init=False)

    def fit(self, df: pd.DataFrame, rows: np.ndarray | None = None) -> Preprocessor:
        """Learn the statistics from ``df`` — only its ``rows`` (positions), if given.

        Passing ``rows`` rather than ``df.iloc[rows]`` saves copying every
        column of a training fold just to read the ones used here.
        """
        self.medians_ = {}
        self.flagged_ = []
        for col in self.numeric:
            values = _numeric(df, col, rows)
            finite = values[np.isfinite(values)]
            if len(finite) == 0:
                continue  # never observed in training: nothing to learn from
            self.medians_[col] = float(np.median(finite))
            if not np.isfinite(values).all():
                self.flagged_.append(col)
        self.levels_ = {}
        for col in self.categorical:
            counts = _column(df, col, rows).astype(str).value_counts()
            limit = self.max_levels.get(col, self.default_levels)
            self.levels_[col] = [*counts.index[:limit].tolist(), _OTHER]
        names = self._names()
        # One column at a time: fitting never holds the whole matrix, nor the
        # same-sized scratch copy numpy makes to measure a spread. Together
        # those were a training run's memory peak on a capped server.
        means = np.empty(len(names))
        stds = np.empty(len(names))
        for j, values in enumerate(self._columns(df, rows)):
            means[j] = values.mean()
            stds[j] = values.std()
        self.keep_ = stds > 1e-12
        self.means_ = means[self.keep_]
        self.stds_ = stds[self.keep_]
        self.names_ = [n for n, k in zip(names, self.keep_, strict=True) if k]
        return self

    def transform(self, df: pd.DataFrame, rows: np.ndarray | None = None) -> np.ndarray:
        """The standardised matrix for ``df`` (its ``rows`` only, if given)."""
        if self.keep_ is None:
            raise RuntimeError("Preprocessor.transform called before fit.")
        # Only the kept columns are built, then standardised in place: the same
        # numbers as ``(raw[:, keep] - means) / stds`` with one matrix in memory
        # instead of three.
        out = self._assemble(df, rows, self.keep_)
        out -= self.means_
        out /= self.stds_
        return out

    @property
    def feature_names(self) -> list[str]:
        return list(self.names_)

    def _names(self) -> list[str]:
        names: list[str] = []
        for col in self.medians_:
            names.append(col)
            if col in self.flagged_:
                names.append(f"{col}__missing")
        for col, levels in self.levels_.items():
            names += [f"{col}={level}" for level in levels]
        return names

    def _columns(self, df: pd.DataFrame, rows: np.ndarray | None) -> Iterator[np.ndarray]:
        """Every column before scaling, in ``_names`` order, one at a time."""
        for col, median in self.medians_.items():
            values = _numeric(df, col, rows)
            missing = ~np.isfinite(values)
            yield np.where(missing, median, values)
            if col in self.flagged_:
                yield missing.astype(float)
        for col, levels in self.levels_.items():
            values = _column(df, col, rows).astype(str).to_numpy()
            known = set(levels[:-1])
            mapped = np.where(np.isin(values, list(known)), values, _OTHER)
            for level in levels:
                yield (mapped == level).astype(float)

    def _assemble(
        self, df: pd.DataFrame, rows: np.ndarray | None, keep: np.ndarray
    ) -> np.ndarray:
        """The ``keep`` columns, in ``_names`` order, filled into one matrix."""
        matrix = np.empty((len(df) if rows is None else len(rows), int(keep.sum())))
        slot = 0
        for index, values in enumerate(self._columns(df, rows)):
            if keep[index]:
                matrix[:, slot] = values
                slot += 1
        return matrix


def _column(df: pd.DataFrame, col: str, rows: np.ndarray | None) -> pd.Series:
    return df[col] if rows is None else df[col].iloc[rows]


def _numeric(df: pd.DataFrame, col: str, rows: np.ndarray | None) -> np.ndarray:
    return pd.to_numeric(_column(df, col, rows), errors="coerce").to_numpy(dtype=float)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35.0, 35.0)))


#: Rows per block when summing the curvature: a few MB of scratch memory.
_HESSIAN_BLOCK = 4096


def _hessian(x: np.ndarray, curvature: np.ndarray) -> np.ndarray:
    """``[1 x]ᵀ · diag(curvature) · [1 x]``, one block of rows at a time.

    Written out in one go it needs the matrix twice more — once with the
    intercept's column of ones glued on, once weighted — and on a server with a
    memory cap that is the difference between a training run that finishes and
    one that is stopped.
    """
    n, k = x.shape
    h = np.zeros((k + 1, k + 1))
    h[0, 0] = curvature.sum()
    cross = x.T @ curvature
    h[0, 1:] = cross
    h[1:, 0] = cross
    for start in range(0, n, _HESSIAN_BLOCK):
        block = x[start : start + _HESSIAN_BLOCK]
        h[1:, 1:] += (block.T * curvature[start : start + _HESSIAN_BLOCK]) @ block
    return h


@dataclass
class LogisticRegression:
    """Logistic regression with an L2 penalty of ``1/c`` (intercept free).

    Fitted by Newton's method on the penalised log-likelihood, which is
    strictly convex, so the answer is unique and the same on every run — no
    random start, no seed.
    """

    c: float = 0.1
    max_iter: int = 100
    tol: float = 1e-8

    coef_: np.ndarray | None = field(default=None, init=False)
    intercept_: float = field(default=0.0, init=False)
    n_iter_: int = field(default=0, init=False)

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ) -> LogisticRegression:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        n, k = x.shape
        weight = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        penalty = np.full(k + 1, 1.0 / self.c)
        penalty[0] = 0.0
        w = np.zeros(k + 1)
        # Start the intercept at the weighted base rate: fewer Newton steps.
        base = np.clip(np.average(y, weights=weight), 1e-6, 1 - 1e-6)
        w[0] = np.log(base / (1 - base))
        # The intercept is kept beside ``x`` rather than glued on as a column of
        # ones, which would copy the whole matrix (see ``_hessian``).
        for it in range(1, self.max_iter + 1):
            p = _sigmoid(x @ w[1:] + w[0])
            residual = weight * (p - y)
            grad = np.concatenate(([residual.sum()], x.T @ residual)) + penalty * w
            hessian = _hessian(x, weight * p * (1 - p))
            hessian[np.diag_indices_from(hessian)] += penalty
            hessian[0, 0] += 1e-10  # keeps the intercept solvable on one-class data
            try:
                step = np.linalg.solve(hessian, grad)
            except np.linalg.LinAlgError:
                step = np.linalg.lstsq(hessian, grad, rcond=None)[0]
            w -= step
            self.n_iter_ = it
            if np.max(np.abs(step)) < self.tol:
                break
        self.intercept_ = float(w[0])
        self.coef_ = w[1:]
        return self

    def decision_function(self, x: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise RuntimeError("LogisticRegression used before fit.")
        return np.asarray(x, dtype=float) @ self.coef_ + self.intercept_

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        """P(y = 1) for each row."""
        return _sigmoid(self.decision_function(x))
