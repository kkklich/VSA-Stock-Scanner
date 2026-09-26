"""Assembling the AI layer's datasets — plan §19.1, design choices §1–§3.

``build_panel`` → one row per stock per session: every per-stock feature
(``features``), every label (``labels``), then the cross-sectional half that
needs a whole market at once — percentiles within the market on that day, the
market regime, and L1's "beat the market" comparison.

From the panel:

* ``job2_rows`` — the stock-day panel sampled every 5th session (Job 2, the
  learned Combined score, roadmap #29);
* ``job1_rows`` — one row per firing of the pool's trading methods (Job 1,
  the signal filter), with the firing-specific features (group H).

``write_dataset`` saves a frame as compressed CSV beside a metadata file that
records exactly what went in.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from app.analysis.vsa import VsaConfig
from app.markets import to_pln_or_none
from app.ml import FEATURES_VERSION
from app.ml.features import (
    LABEL_COLUMN,
    METHOD_FEATURE_IDS,
    STOCK_FEATURE_COLUMNS,
    bars_frame,
    sessions_since,
    stock_features,
)
from app.ml.labels import (
    forward_open_to_close,
    gate_baseline_pct,
    gate_forward_pct,
    triple_barrier,
)
from app.models import StooqDailyQuote

HORIZONS: tuple[int, ...] = (10, 30)
#: The methods the filter is built for (design choices §2, D1 proposal).
PRIMARY_METHODS: tuple[str, ...] = ("vsa4", "weinstein")
#: Every method whose firings become Job-1 training rows.
JOB1_METHODS: tuple[str, ...] = ("vsa4", "weinstein", "glinicki", "breakout")
#: A market with fewer stocks trading that day has no regime and no L1 median.
MIN_STOCKS_PER_DAY = 20
JOB2_EVERY = 5

CROSS_SECTIONAL_COLUMNS = ["turnover_pct", "rs_pct", "mom_12_1_pct"]
REGIME_COLUMNS = [
    "reg_mkt_ret20",
    "reg_mkt_ret60",
    "reg_mkt_vol20",
    "reg_breadth50",
    "reg_breadth200",
    "reg_hl_net",
    "reg_dispersion",
    "reg_vsa_net",
]
#: Numeric model inputs shared by both jobs.
FEATURE_COLUMNS: list[str] = [*STOCK_FEATURE_COLUMNS, *CROSS_SECTIONAL_COLUMNS, *REGIME_COLUMNS]
CATEGORICAL_COLUMNS = ["sector", "market"]
#: Group H — only meaningful on a firing row.
FIRING_COLUMNS = ["h_prior_firings60", "h_since_prev", "h_confluence"]
JOB1_FEATURE_COLUMNS: list[str] = [*FEATURE_COLUMNS, *FIRING_COLUMNS]
JOB1_CATEGORICAL_COLUMNS = [*CATEGORICAL_COLUMNS, "method", "setup"]


@dataclass(frozen=True)
class StockInput:
    """One company's stored bars and the metadata the dataset needs."""

    ticker: str
    market: str
    currency: str | None
    sector: str | None
    bars: Sequence[StooqDailyQuote]


def label_columns(horizons: Sequence[int] = HORIZONS) -> list[str]:
    """Every label column a panel carries, for the horizons it was built with."""
    cols: list[str] = []
    for n in horizons:
        cols += [
            f"fwd_r_{n}",
            f"fwd_end_{n}",
            f"l1_excess_{n}",
            f"l1_y_{n}",
            f"l2_pct_{n}",
            f"l2_base_{n}",
            f"l2_excess_{n}",
            f"l2_y_{n}",
            f"l3_r_{n}",
            f"l3_exit_{n}",
            f"l3_y_{n}",
        ]
    return cols


# ── Per stock ─────────────────────────────────────────────────────────────────


def stock_frame(
    stock: StockInput,
    horizons: Sequence[int] = HORIZONS,
    config: VsaConfig | None = None,
) -> pd.DataFrame:
    """Features, the stock's half of every label, and the firing helpers."""
    frame = stock_features(stock.bars, config)
    if frame.empty:
        return frame
    bars = bars_frame(stock.bars)  # same dates, same order as ``frame``
    rows = len(frame)
    head = pd.DataFrame(
        {
            "ticker": stock.ticker,
            "market": stock.market,
            "sector": stock.sector or "Unknown",
            "position": np.arange(rows),
        },
        index=frame.index,
    )
    # New columns are collected here and joined once (see features.py).
    extra: dict[str, object] = {}
    rate = to_pln_or_none(1.0, stock.currency)
    extra["turnover_pln"] = frame["turnover_med20"] * rate if rate else np.nan

    fired_any = np.zeros(rows, dtype=bool)
    for mid in JOB1_METHODS:
        fired_any |= frame[f"fire_{mid}"].to_numpy() > 0
    atr = frame["atr14"].to_numpy()
    closes = bars["close"].to_numpy()

    for n in horizons:
        fwd = forward_open_to_close(bars, n)
        extra[f"fwd_r_{n}"] = fwd["fwd_r"].to_numpy()
        extra[f"fwd_end_{n}"] = fwd["fwd_end"].to_numpy()

        pct = gate_forward_pct(closes, n)
        base = gate_baseline_pct(closes, n)
        excess = pct - (np.nan if base is None else base)
        extra[f"l2_pct_{n}"] = pct
        extra[f"l2_base_{n}"] = np.nan if base is None else base
        extra[f"l2_excess_{n}"] = excess
        extra[f"l2_y_{n}"] = np.where(np.isfinite(excess), (excess > 0).astype(float), np.nan)

        l3 = np.full(rows, np.nan)
        exits = [""] * rows
        for t in np.flatnonzero(fired_any):
            outcome = triple_barrier(bars, int(t), n, float(atr[t]))
            if outcome is not None:
                l3[t] = outcome.r_net
                exits[t] = outcome.exit_reason
        extra[f"l3_r_{n}"] = l3
        extra[f"l3_exit_{n}"] = exits
        extra[f"l3_y_{n}"] = np.where(np.isfinite(l3), (l3 > 0).astype(float), np.nan)

    # Group H helpers, per method (``job1_rows`` picks the firing method's).
    recent = sum(frame[f"m_{mid}_fired5"].fillna(0.0) for mid in METHOD_FEATURE_IDS)
    extra["h_recent_methods5"] = recent + (frame["vsa_bull_since"] <= 4).astype(float)
    for mid in JOB1_METHODS:
        fire = frame[f"fire_{mid}"]
        extra[f"h_prior60_{mid}"] = fire.shift(1).rolling(60, min_periods=1).sum().fillna(0.0)
        extra[f"h_since_{mid}"] = sessions_since(fire.to_numpy() > 0, 250, exclusive=True)
    return pd.concat([head, frame, pd.DataFrame(extra, index=frame.index)], axis=1)


# ── Across the market ─────────────────────────────────────────────────────────


def add_cross_sectional(panel: pd.DataFrame, horizons: Sequence[int] = HORIZONS) -> pd.DataFrame:
    """Percentiles within a market-day, the market regime, and L1's comparison.

    Everything here compares stocks **on the same day**, so it uses nothing a
    trader at that day's close could not have known.
    """
    keys = ["market", "date"]
    grouped = panel.groupby(keys, sort=False)
    panel["turnover_pct"] = grouped["turnover_pln"].rank(pct=True)
    panel["rs_pct"] = grouped["rs_raw"].rank(pct=True)
    panel["mom_12_1_pct"] = grouped["mom_12_1_raw"].rank(pct=True)

    regime = (
        grouped.agg(
            reg_stocks=("ret1", "count"),
            ew_ret=("ret1", "mean"),
            reg_breadth50=("above_ma50", "mean"),
            reg_breadth200=("above_ma200", "mean"),
            new_high=("new_52w_high", "mean"),
            new_low=("new_52w_low", "mean"),
            reg_dispersion=("ret20", "std"),
            bull=("vsa_bull_today", "mean"),
            bear=("vsa_bear_today", "mean"),
        )
        .reset_index()
        .sort_values(keys)
    )
    regime["reg_hl_net"] = regime["new_high"] - regime["new_low"]
    regime["reg_vsa_net"] = regime["bull"] - regime["bear"]
    thin = regime["reg_stocks"] < MIN_STOCKS_PER_DAY
    daily = [
        "ew_ret",
        "reg_breadth50",
        "reg_breadth200",
        "reg_hl_net",
        "reg_dispersion",
        "reg_vsa_net",
    ]
    regime.loc[thin, daily] = np.nan

    parts = []
    for _, market in regime.groupby("market", sort=False):
        market = market.copy()
        log_ret = np.log1p(market["ew_ret"])
        market["reg_mkt_ret20"] = log_ret.rolling(20).sum()
        market["reg_mkt_ret60"] = log_ret.rolling(60).sum()
        market["reg_mkt_vol20"] = market["ew_ret"].rolling(20).std()
        parts.append(market)
    regime = pd.concat(parts, ignore_index=True) if parts else regime
    panel = panel.merge(regime[[*keys, "reg_stocks", *REGIME_COLUMNS]], on=keys, how="left")

    for n in horizons:
        col = f"fwd_r_{n}"
        valid = panel[col].notna()
        counts = panel.loc[valid].groupby(keys)[col].transform("count")
        medians = panel.loc[valid].groupby(keys)[col].transform("median")
        enough = counts >= MIN_STOCKS_PER_DAY
        excess = pd.Series(np.nan, index=panel.index)
        excess.loc[enough[enough].index] = (panel.loc[valid, col] - medians)[enough]
        panel[f"l1_excess_{n}"] = excess
        panel[f"l1_y_{n}"] = np.where(excess.notna(), (excess > 0).astype(float), np.nan)
    return panel


def build_panel(
    stocks: Sequence[StockInput],
    horizons: Sequence[int] = HORIZONS,
    config: VsaConfig | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> pd.DataFrame:
    """Every stock's frame, joined, with the cross-sectional half added."""
    frames = []
    for i, stock in enumerate(stocks, start=1):
        frame = stock_frame(stock, horizons, config)
        if not frame.empty:
            frames.append(frame)
        if progress is not None:
            progress(i, len(stocks), stock.ticker)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    return add_cross_sectional(panel, horizons)


# ── The two jobs' rows ────────────────────────────────────────────────────────


def job2_rows(
    panel: pd.DataFrame,
    horizons: Sequence[int] = HORIZONS,
    every: int = JOB2_EVERY,
    offset: int = 0,
) -> pd.DataFrame:
    """Every ``every``-th session of each stock that has at least one L1 label."""
    has_label = np.zeros(len(panel), dtype=bool)
    for n in horizons:
        has_label |= panel[f"l1_y_{n}"].notna().to_numpy()
    keep = (panel["position"].to_numpy() % every == offset) & has_label
    return panel.loc[keep].reset_index(drop=True)


def job1_rows(panel: pd.DataFrame, methods: Sequence[str] = JOB1_METHODS) -> pd.DataFrame:
    """One row per firing of each method, with its firing-specific features."""
    parts = []
    for mid in methods:
        col = f"fire_{mid}"
        if col not in panel:
            continue
        rows = panel.loc[panel[col] > 0].copy()
        if rows.empty:
            continue
        rows["method"] = mid
        if mid == "vsa4":  # VSA V4 names its setup; the others have one
            rows["setup"] = rows[LABEL_COLUMN].where(rows[LABEL_COLUMN] != "", mid)
        else:
            rows["setup"] = mid
        rows["h_prior_firings60"] = rows[f"h_prior60_{mid}"]
        rows["h_since_prev"] = rows[f"h_since_{mid}"]
        # Other methods active within 5 sessions: the total minus this one.
        rows["h_confluence"] = rows["h_recent_methods5"] - 1.0
        parts.append(rows)
    if not parts:
        return pd.DataFrame()
    joined = pd.concat(parts, ignore_index=True)
    return joined.sort_values(["date", "ticker", "method"]).reset_index(drop=True)


# ── Saving ────────────────────────────────────────────────────────────────────


def write_dataset(frame: pd.DataFrame, path: Path, meta: dict | None = None) -> dict:
    """Write ``frame`` as ``<path>`` (gzip CSV) plus ``<path>.meta.json``.

    The metadata records the features version, the row and column counts, the
    date span and the file's SHA-256, so a model card can name the exact data
    it was trained on.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    dates = frame["date"] if "date" in frame and not frame.empty else pd.Series([], dtype=object)
    info = {
        "file": path.name,
        "featuresVersion": FEATURES_VERSION,
        "builtAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "firstDate": str(min(dates)) if len(dates) else None,
        "lastDate": str(max(dates)) if len(dates) else None,
        "sha256": digest,
        **(meta or {}),
    }
    Path(f"{path}.meta.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
    return info


def as_dates(values: Sequence[object]) -> list[date]:
    """Coerce a column read back from CSV (strings) or built in memory to dates."""
    out: list[date] = []
    for v in values:
        if isinstance(v, date):
            out.append(v)
        else:
            out.append(date.fromisoformat(str(v)[:10]))
    return out
