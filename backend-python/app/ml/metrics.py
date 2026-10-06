"""Scoring a probabilistic prediction — the numbers a Phase-1+ report quotes."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _clean(y: np.ndarray, score: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float)
    score = np.asarray(score, dtype=float)
    ok = np.isfinite(y) & np.isfinite(score)
    return y[ok], score[ok]


def roc_auc(y: np.ndarray, score: np.ndarray) -> float:
    """Probability that a random success scores above a random failure.

    Mann–Whitney form with average ranks, so ties count half. 0.5 is a coin;
    ``NaN`` when one of the two classes is absent.
    """
    y, score = _clean(y, score)
    pos = int((y == 1).sum())
    neg = int((y == 0).sum())
    if pos == 0 or neg == 0:
        return float("nan")
    ranks = pd.Series(score).rank(method="average").to_numpy()
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    """Mean squared error of the probabilities (0.25 for a constant 50%)."""
    y, p = _clean(y, p)
    return float(np.mean((p - y) ** 2)) if len(y) else float("nan")


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    y, p = _clean(y, p)
    if not len(y):
        return float("nan")
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def top_fraction_precision(y: np.ndarray, score: np.ndarray, fraction: float = 0.1) -> float:
    """Share of successes among the ``fraction`` highest-scored rows."""
    y, score = _clean(y, score)
    if not len(y):
        return float("nan")
    count = max(1, int(round(fraction * len(y))))
    top = np.argsort(-score, kind="stable")[:count]
    return float(y[top].mean())


def reliability(
    y: np.ndarray, p: np.ndarray, bins: int = 10
) -> list[tuple[float, float, int, float, float]]:
    """(low, high, rows, mean predicted, share observed) per probability band.

    A calibrated model has the last two columns close together — "of the cases
    called 55–65%, about 60% succeeded".
    """
    y, p = _clean(y, p)
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        inside = (p >= lo) & ((p < hi) | (hi == 1.0))
        if inside.any():
            rows.append((float(lo), float(hi), int(inside.sum()),
                         float(p[inside].mean()), float(y[inside].mean())))
    return rows
