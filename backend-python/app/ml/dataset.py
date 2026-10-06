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
from collections.abc import Callable, Iterable, Sequence
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
    out = pd.concat([head, frame, pd.DataFrame(extra, index=frame.index)], axis=1)
    # Measurements are kept as 4-byte floats — seven significant digits is far
    # more than a percentile, a ratio or a z-score needs, and it halves what a
    # market's history costs in memory on the server. The labels (what the
    # models learn and are judged on) keep full precision, and so do the
    # figures ranked across stocks each day.
    narrow = [
        c for c in out.columns
        if out[c].dtype == np.float64
        and not c.startswith(_FULL_PRECISION_PREFIXES)
        and c not in _RANKED_COLUMNS
    ]
    out[narrow] = out[narrow].astype(np.float32)
    return out


#: Column prefixes kept as 8-byte floats: every label and its inputs.
_FULL_PRECISION_PREFIXES = ("fwd_r_", "l1_", "l2_", "l3_")
#: Kept as 8-byte floats too: what ``market_day_tables`` ranks across stocks.
#: Rounded to four bytes, two stocks a hair apart would tie and share a
#: percentile (it happened to 3 of 28,410 GPW rows before this rule).
_RANKED_COLUMNS = frozenset({"turnover_pln", "rs_raw", "mom_12_1_raw"})


# ── Across the market ─────────────────────────────────────────────────────────


#: What the cross-sectional half needs from **every** stock-session. The rest of
#: a row is needed only on the rows the two jobs keep — that split is what lets
#: ``build_datasets`` hold a market's history in a fraction of the memory.
_SLIM_COLUMNS = [
    "ticker",
    "market",
    "date",
    "turnover_pln",
    "rs_raw",
    "mom_12_1_raw",
    "ret1",
    "above_ma50",
    "above_ma200",
    "new_52w_high",
    "new_52w_low",
    "ret20",
    "vsa_bull_today",
    "vsa_bear_today",
]


def slim_columns(horizons: Sequence[int] = HORIZONS) -> list[str]:
    return [*_SLIM_COLUMNS, *(f"fwd_r_{n}" for n in horizons)]


@dataclass(frozen=True)
class MarketDayTables:
    """The cross-sectional facts, keyed so they can be joined onto any rows."""

    percentiles: pd.DataFrame  # ticker, date → turnover / RS / momentum percentile
    regime: pd.DataFrame  # market, date → the market's mood that day
    l1: pd.DataFrame  # market, date → each horizon's median return and count


def market_day_tables(slim: pd.DataFrame, horizons: Sequence[int] = HORIZONS) -> MarketDayTables:
    """Percentiles within a market-day, the market regime, and L1's medians.

    Everything here compares stocks **on the same day**, so it uses nothing a
    trader at that day's close could not have known.
    """
    keys = ["market", "date"]
    grouped = slim.groupby(keys, sort=False)
    percentiles = slim[["ticker", "date"]].copy()
    percentiles["turnover_pct"] = grouped["turnover_pln"].rank(pct=True)
    percentiles["rs_pct"] = grouped["rs_raw"].rank(pct=True)
    percentiles["mom_12_1_pct"] = grouped["mom_12_1_raw"].rank(pct=True)

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

    l1 = None
    for n in horizons:
        col = f"fwd_r_{n}"
        # median and count both skip missing values, so no filtered copy of
        # every stock-session is needed; a day with none counts 0, which
        # ``attach_cross_sectional`` treats exactly like a day not listed.
        stats = (
            grouped[col]
            .agg(["median", "count"])
            .rename(columns={"median": f"_l1_median_{n}", "count": f"_l1_count_{n}"})
            .reset_index()
        )
        l1 = stats if l1 is None else l1.merge(stats, on=keys, how="outer")
    if l1 is None:
        l1 = regime[keys].copy()
    return MarketDayTables(
        percentiles=percentiles,
        regime=regime[[*keys, "reg_stocks", *REGIME_COLUMNS]],
        l1=l1,
    )


def attach_cross_sectional(
    frame: pd.DataFrame, tables: MarketDayTables, horizons: Sequence[int] = HORIZONS
) -> pd.DataFrame:
    """Add the market-day facts to ``frame`` **in place** and compute L1; returns it.

    Looked up by index rather than merged: a merge copies the whole frame once
    per join, and on the server the frame is most of the memory a build uses.
    """
    by_stock_day = pd.MultiIndex.from_arrays([frame["ticker"], frame["date"]])
    by_market_day = pd.MultiIndex.from_arrays([frame["market"], frame["date"]])
    percentiles = tables.percentiles.set_index(["ticker", "date"]).reindex(by_stock_day)
    for col in percentiles.columns:
        frame[col] = percentiles[col].to_numpy()
    regime = tables.regime.set_index(["market", "date"]).reindex(by_market_day)
    for col in regime.columns:
        frame[col] = regime[col].to_numpy()
    l1 = tables.l1.set_index(["market", "date"]).reindex(by_market_day)
    for n in horizons:
        fwd = frame[f"fwd_r_{n}"].to_numpy(dtype=float)
        median = (
            l1[f"_l1_median_{n}"].to_numpy(dtype=float)
            if f"_l1_median_{n}" in l1
            else np.full(len(frame), np.nan)
        )
        count = (
            l1[f"_l1_count_{n}"].fillna(0).to_numpy()
            if f"_l1_count_{n}" in l1
            else np.zeros(len(frame))
        )
        ok = np.isfinite(fwd) & (count >= MIN_STOCKS_PER_DAY)
        excess = np.where(ok, fwd - median, np.nan)
        frame[f"l1_excess_{n}"] = excess
        frame[f"l1_y_{n}"] = np.where(ok, (excess > 0).astype(float), np.nan)
    return frame


def add_cross_sectional(panel: pd.DataFrame, horizons: Sequence[int] = HORIZONS) -> pd.DataFrame:
    """The whole-panel form: compute the market-day facts and attach them."""
    tables = market_day_tables(panel[slim_columns(horizons)], horizons)
    return attach_cross_sectional(panel, tables, horizons)


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


def build_datasets(
    stocks: Iterable[StockInput],
    horizons: Sequence[int] = HORIZONS,
    config: VsaConfig | None = None,
    progress: Callable[[int, str], None] | None = None,
    every: int = JOB2_EVERY,
    offset: int = 0,
    job1_methods: Sequence[str] = JOB1_METHODS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(Job-1 rows, Job-2 rows), built **one stock at a time** — the server path.

    ``build_panel`` holds every column of every stock-session at once: 280 MB
    for today's GPW history, about 1 GB after a ten-year back-fill, on top of
    the bars themselves. Here each stock's frame lives only while it is being
    read: every session keeps just the handful of columns the cross-sectional
    half needs, and only the rows the two jobs keep (every ``every``-th
    session, plus every firing) keep all of theirs. ``stocks`` can therefore be
    a generator that loads one stock at a time
    (``data_access.stream_stock_inputs``). The result is identical to
    ``job1_rows(build_panel(...))`` / ``job2_rows(build_panel(...))`` —
    ``tests/test_ml_dataset.py`` pins that.
    """
    slim_cols = slim_columns(horizons)
    slims: list[pd.DataFrame] = []
    kept: list[pd.DataFrame] = []
    for i, stock in enumerate(stocks, start=1):
        frame = stock_frame(stock, horizons, config)
        if progress is not None:
            progress(i, stock.ticker)
        if frame.empty:
            continue
        slims.append(frame[slim_cols])
        fired = np.zeros(len(frame), dtype=bool)
        for mid in job1_methods:
            fired |= frame[f"fire_{mid}"].to_numpy() > 0
        keep = (frame["position"].to_numpy() % every == offset) | fired
        kept.append(frame.loc[keep])
    if not kept:
        return pd.DataFrame(), pd.DataFrame()
    # Each list is emptied the moment it has been joined, so the per-stock
    # pieces and the joined frame never sit in memory together while the
    # next (itself memory-hungry) step runs.
    slim = pd.concat(slims, ignore_index=True)
    slims.clear()
    tables = market_day_tables(slim, horizons)
    del slim
    rows = pd.concat(kept, ignore_index=True)
    kept.clear()
    attach_cross_sectional(rows, tables, horizons)
    del tables
    return job1_rows(rows, job1_methods), job2_rows(rows, horizons, every, offset)


# ── The two jobs' rows ────────────────────────────────────────────────────────


def _renumbered(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` with a fresh 0…n-1 index, set in place.

    ``reset_index(drop=True)`` would copy every column once more (pandas
    without copy-on-write), and a market's kept rows are most of what a build
    holds; setting the index copies nothing.
    """
    frame.index = pd.RangeIndex(len(frame))
    return frame


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
    return _renumbered(panel.loc[keep])


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
    return _renumbered(joined.sort_values(["date", "ticker", "method"]))


# ── Saving ────────────────────────────────────────────────────────────────────


def write_dataset(frame: pd.DataFrame, path: Path, meta: dict | None = None) -> dict:
    """Write ``frame`` as ``<path>`` (gzip CSV) plus ``<path>.meta.json``.

    The metadata records the features version, the row and column counts, the
    date span and the file's SHA-256, so a model card can name the exact data
    it was trained on.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the target and renamed into place: a job stopped mid-write
    # (by hand, or by the server's memory cap) never leaves a cut-off file for
    # the next job to trip over.
    partial = path.with_name(f"{path.name}.partial")
    frame.to_csv(partial, index=False, compression="gzip")
    digest = hashlib.sha256()
    with partial.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    partial.replace(path)
    dates = frame["date"] if "date" in frame and not frame.empty else pd.Series([], dtype=object)
    info = {
        "file": path.name,
        "featuresVersion": FEATURES_VERSION,
        "builtAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "firstDate": str(min(dates)) if len(dates) else None,
        "lastDate": str(max(dates)) if len(dates) else None,
        "sha256": digest.hexdigest(),
        **(meta or {}),
    }
    Path(f"{path}.meta.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
    return info


def read_datasets(
    directory: Path, markets: Sequence[str], job: int, columns: Iterable[str] | None = None
) -> tuple[pd.DataFrame, list[dict]]:
    """Read ``job<job>-<market>.csv.gz`` for each market, joined, plus their metadata.

    Raises ``FileNotFoundError`` naming the first missing file — the dataset
    step (``scripts/ml_build_dataset.py``) has to have run for those markets.
    ``columns``, when given, keeps only those (a name a file lacks is skipped):
    a reader that needs a third of a table should not hold all of it.
    """
    frames, metas = [], []
    for market in markets:
        path = directory / f"job{job}-{market}.csv.gz"
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing — build the datasets first.")
        frames.append(_read_dataset(path, columns))
        meta_path = Path(f"{path}.meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        metas.append(meta)
    frames = [f for f in frames if not f.empty]
    if len(frames) == 1:
        return frames[0], metas  # ``concat`` would copy it once more for nothing
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), metas


#: The columns a dataset file holds as text; every other column is a number.
_TEXT_COLUMNS = frozenset({"ticker", "market", "sector", "date", LABEL_COLUMN, "method", "setup"})
_TEXT_PREFIXES = ("fwd_end_", "l3_exit_")
#: Rows parsed at a time by ``_read_dataset``.
_READ_ROWS = 20_000


def _text_dtypes(columns: Iterable[str]) -> dict[str, str]:
    return {
        c: "object" for c in columns if c in _TEXT_COLUMNS or c.startswith(_TEXT_PREFIXES)
    }


def _read_dataset(path: Path, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """One dataset file, parsed ``_READ_ROWS`` at a time.

    Parsed in one go, a file needed about three times the finished table's
    memory for a moment (750 MB for a ten-year GPW Job 2 of 216 MB); in pieces
    it needs about twice. The text columns are named so no piece can guess a
    column's type differently from the rest.
    """
    try:
        header = pd.read_csv(path, compression="gzip", nrows=0).columns
    except pd.errors.EmptyDataError:
        return pd.DataFrame()  # a job with no rows for this market
    if columns is not None:
        wanted = set(columns)
        header = pd.Index([c for c in header if c in wanted])
    with pd.read_csv(
        path,
        compression="gzip",
        usecols=None if columns is None else list(header),
        dtype=_text_dtypes(header),
        chunksize=_READ_ROWS,
    ) as reader:
        pieces = list(reader)
    if not pieces:
        return pd.DataFrame(columns=header)
    return pieces[0] if len(pieces) == 1 else pd.concat(pieces, ignore_index=True)


def as_dates(values: Sequence[object]) -> list[date]:
    """Coerce a column read back from CSV (strings) or built in memory to dates."""
    out: list[date] = []
    for v in values:
        if isinstance(v, date):
            out.append(v)
        else:
            out.append(date.fromisoformat(str(v)[:10]))
    return out
