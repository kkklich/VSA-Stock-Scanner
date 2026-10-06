"""Point-in-time features for the AI layer — plan §17, design choices §3.

``stock_features(bars)`` turns one stock's daily bars into a frame with one row
per session. **Every value in row *t* is computed from bars dated ≤ *t*
only** — that is the whole point of the module, and it is checked rather than
assumed: ``validation.truncation_check`` recomputes rows on histories cut off
at *t* and requires identical values (``tests/test_ml_features.py`` on
synthetic series, ``scripts/ml_report.py`` on stored ones).

What is here is the per-stock half of the catalogue. The cross-sectional half
— percentiles within a market on a day, and the market regime — needs every
stock of the market at once and lives in ``dataset.py``.

Every feature is scale-free (a ratio, a share, volatility units or a flag), so
a złoty stock and a pence stock read the same way. Missing is ``NaN``, never 0.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from datetime import date

import numpy as np
import pandas as pd

from app.analysis.methods import get_method
from app.analysis.phase import Phase, add_phase_columns, classify_row
from app.analysis.vsa import SignalName, SignalType, VsaConfig, detect_signals
from app.analysis.vsa4.adapter import (
    config_for,
    sequence_state,
    setup_label,
    tick_size,
    to_engine_bars,
)
from app.analysis.vsa4.engine import analyze
from app.analysis.weekly import resample_weekly
from app.models import StooqDailyQuote

logger = logging.getLogger(__name__)

# ── Constants (each tied to the app definition it mirrors) ────────────────────

_ATR_BARS = 14
# The ranking detects VSA signals on a 120-calendar-day slice and rates them
# with a 30-day half-life (ranking_service._HISTORY_DAYS, vsa.compute_rating).
_RATING_WINDOW_DAYS = 120
_RATING_HALF_LIFE_DAYS = 30
# vsa._VERDICT_STRONG_NET / _VERDICT_LEAN_NET — the verdict badge's boundaries.
_VERDICT_STRONG_NET = 1.2
_VERDICT_LEAN_NET = 0.45
# vsa._TREND_LOOKBACK / _TREND_BAND — the engine's background-trend proxy.
_TREND_LOOKBACK = 30
_TREND_BAND = 0.03
# weekly._MAX_WEEKLY_BARS / _MIN_WEEKLY_BARS / _WEEKLY_HALF_LIFE_DAYS.
_WEEKLY_WINDOW = 52
_MIN_WEEKLY_BARS = 30
_WEEKLY_HALF_LIFE_DAYS = 210
# ranking_service: the 52-week window and the coverage it must really span.
_WEEK52_WINDOW = "366D"  # (t − 366 days, t] = [t − 365, t] for whole days
_MIN_52W_COVERAGE_DAYS = 330
# ranking_service._RS_OFFSETS / _RS_WEIGHTS — IBD-style blended performance.
_RS_OFFSETS = (63, 126, 189, 252)
_RS_WEIGHTS = (0.4, 0.2, 0.2, 0.2)
# volume_surge_service defaults: 3 recent sessions vs the 20 before them.
_RVOL_RECENT = 3
_RVOL_BASELINE = 20
# methods/vsa4._MIN_BARS — below this VSA V4 does not evaluate at all.
_VSA4_MIN_BARS = 40
# Caps for "sessions since" counters — "long ago" is one value, not a trend.
_SINCE_CAP_SIGNAL = 60
_SINCE_CAP_METHOD = 250

#: The trading methods whose firing history becomes features (group D). VSA's
#: own signals are group C; every other registered method is here.
METHOD_FEATURE_IDS: tuple[str, ...] = (
    "minervini",
    "breakout",
    "glinicki",
    "vsa3",
    "vsa4",
    "weinstein",
)

_SIGNAL_SLUGS: dict[SignalName, str] = {
    SignalName.SPRING: "spring",
    SignalName.SUCCESSFUL_TEST: "test",
    SignalName.SOS: "sos",
    SignalName.UPTHRUST: "upthrust",
    SignalName.NO_DEMAND: "nodemand",
    SignalName.SOW: "sow",
}

# ── Column catalogue ──────────────────────────────────────────────────────────

_GROUP_A = [
    "spread_rel20",
    "close_pos",
    "vol_rel20",
    "vol_rel_med20",
    "vol_pct60",
    "vol_new_max20",
    "gap_atr",
    "body_pos",
    "up_bar",
    "vol_trend5",
]
_GROUP_B = [
    "ret1_vol",
    "ret5_vol",
    "ret10_vol",
    "ret20_vol",
    "ret60_vol",
    "dist_ma20_atr",
    "dist_ma50_atr",
    "dist_ma200_atr",
    "ma50_slope10",
    "ma200_slope20",
    "dd_60",
    "atr_pct",
    "range_contraction",
    "up_share20",
]
_GROUP_C = [
    *(f"vsa_{slug}5" for slug in _SIGNAL_SLUGS.values()),
    "vsa_net",
    "vsa_rating",
    "vsa_verdict",
    "trend_ctx",
    *(f"phase_{p.value}" for p in Phase),
    "vsa_bull_since",
]
_GROUP_D = [
    *(
        f"m_{mid}_{suffix}"
        for mid in METHOD_FEATURE_IDS
        for suffix in ("fired1", "fired5", "fired20", "since")
    ),
    "m_vsa4_bear5",
    "m_vsa3_watch5",
    "m_vsa4_watch5",
]
_GROUP_E = [
    "dist_52w_high",
    "dist_52w_low",
    "new_52w_high",
    "new_52w_low",
    "weekly_rating",
    "weekly_agree",
    "rvol_3_20",
    "rvol_last",
    "rvol_days_above",
]
_GROUP_F = ["zero_vol_60"]

#: Per-stock numeric model inputs produced by ``stock_features``.
STOCK_FEATURE_COLUMNS: list[str] = [
    *_GROUP_A,
    *_GROUP_B,
    *_GROUP_C,
    *_GROUP_D,
    *_GROUP_E,
    *_GROUP_F,
]

#: Helper columns: inputs to the cross-sectional features, the regime and the
#: labels. Not model inputs themselves (``turnover_med20`` is in the stock's own
#: currency, ``rs_raw`` in percent — both become percentiles in ``dataset``).
AUX_COLUMNS: list[str] = [
    "atr14",
    "turnover_med20",
    "rs_raw",
    "mom_12_1_raw",
    "ret1",
    "ret20",
    "above_ma50",
    "above_ma200",
    "vsa_bull_today",
    "vsa_bear_today",
    *(f"fire_{mid}" for mid in METHOD_FEATURE_IDS),
]

#: String column: VSA V4's setup label on the bars where it fired.
LABEL_COLUMN = "label_vsa4"


# ── Small helpers ─────────────────────────────────────────────────────────────


def ordered_bars(bars: Sequence[StooqDailyQuote]) -> list[StooqDailyQuote]:
    """Chronological, one bar per date (the last one wins on a duplicate)."""
    by_date: dict[date, StooqDailyQuote] = {}
    for b in bars:
        by_date[b.date] = b
    return [by_date[d] for d in sorted(by_date)]


def bars_frame(bars: Sequence[StooqDailyQuote]) -> pd.DataFrame:
    """The bars as a float frame: date, open, high, low, close, volume."""
    ordered = ordered_bars(bars)
    return pd.DataFrame(
        {
            "date": [b.date for b in ordered],
            "open": np.array([float(b.open) for b in ordered], dtype=float),
            "high": np.array([float(b.high) for b in ordered], dtype=float),
            "low": np.array([float(b.low) for b in ordered], dtype=float),
            "close": np.array([float(b.close) for b in ordered], dtype=float),
            "volume": np.array([float(b.volume) for b in ordered], dtype=float),
        }
    )


def _ratio(num: pd.Series | np.ndarray, den: pd.Series | np.ndarray) -> np.ndarray:
    """num / den, with NaN wherever the denominator is missing or not positive."""
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    out = np.full(num.shape, np.nan)
    ok = np.isfinite(den) & (den > 0) & np.isfinite(num)
    out[ok] = num[ok] / den[ok]
    return out


def _flag(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """A 0/1 float array that is NaN where the inputs were not available."""
    out = np.asarray(values, dtype=float)
    return np.where(valid, out, np.nan)


def sessions_since(event: np.ndarray, cap: int, *, exclusive: bool = False) -> np.ndarray:
    """Sessions since the latest event at or before each row, capped at ``cap``.

    ``exclusive=True`` looks only at rows *before* each row (the previous
    firing, not today's). A row with no earlier event reads ``cap``.
    """
    ev = np.asarray(event, dtype=bool)
    n = len(ev)
    if n == 0:
        return np.zeros(0)
    pos = np.arange(n)
    last = np.maximum.accumulate(np.where(ev, pos, -1))
    if exclusive:
        last = np.concatenate(([-1], last[:-1]))
    dist = np.where(last >= 0, pos - last, cap)
    return np.minimum(dist, cap).astype(float)


def _recent(event: np.ndarray, window: int) -> np.ndarray:
    """1 when the event happened on this row or one of the ``window - 1`` before."""
    s = pd.Series(np.asarray(event, dtype=float))
    return s.rolling(window, min_periods=1).max().to_numpy()


def _decayed_net(
    row_days: np.ndarray,
    sig_days: np.ndarray,
    sig_weights: np.ndarray,
    half_life: float,
    window_days: float | None = None,
    window_start: np.ndarray | None = None,
) -> np.ndarray:
    """Σ weight · exp(−λ · days_ago) over signals no later than each row.

    Mirrors ``vsa._net_score``. ``window_days`` keeps only signals at most that
    many days old; ``window_start`` (per row) keeps only signals on or after it.
    """
    net = np.zeros(len(row_days))
    if len(sig_days) == 0 or len(row_days) == 0:
        return net
    lam = math.log(2) / half_life
    step = 2000  # bounds the rows × signals matrix
    for start in range(0, len(row_days), step):
        stop = min(start + step, len(row_days))
        ago = row_days[start:stop, None] - sig_days[None, :]
        mask = ago >= 0
        if window_days is not None:
            mask &= ago <= window_days
        if window_start is not None:
            mask &= sig_days[None, :] >= window_start[start:stop, None]
        weight = np.where(mask, np.exp(-lam * np.clip(ago, 0.0, None)), 0.0)
        net[start:stop] = (weight * sig_weights[None, :]).sum(axis=1)
    return net


def _rating_from_net(net: np.ndarray) -> np.ndarray:
    """``vsa.compute_rating``'s mapping: 50 + 50·tanh(net / 2), clipped 0–100."""
    return np.clip(np.round(50.0 + 50.0 * np.tanh(net / 2.0)), 0, 100)


def _verdict_from_net(net: np.ndarray) -> np.ndarray:
    """Strong Buy +2 … Hold 0 … Strong Sell −2, as ``vsa.verdict_from_signals``."""
    return np.select(
        [
            net >= _VERDICT_STRONG_NET,
            net >= _VERDICT_LEAN_NET,
            net <= -_VERDICT_STRONG_NET,
            net <= -_VERDICT_LEAN_NET,
        ],
        [2.0, 1.0, -2.0, -1.0],
        default=0.0,
    )


# ── The builder ───────────────────────────────────────────────────────────────


def stock_features(
    bars: Sequence[StooqDailyQuote],
    config: VsaConfig | None = None,
    method_ids: Sequence[str] = METHOD_FEATURE_IDS,
    *,
    vsa4_tick: str = "point_in_time",
) -> pd.DataFrame:
    """One row per session: ``date``, the per-stock features and the helpers.

    Never raises on short or odd input — a feature that cannot be computed yet
    is ``NaN``. A method whose ``signals()`` raises leaves its columns ``NaN``
    and is logged, so one faulty method cannot sink a dataset build.

    ``vsa4_tick="last_close"`` reads VSA V4 the way the app's back-test gate
    does (see ``vsa4_rows``); only the gate reproduction uses it.
    """
    ordered = ordered_bars(bars)
    columns = ["date", *STOCK_FEATURE_COLUMNS, *AUX_COLUMNS, LABEL_COLUMN]
    if not ordered:
        return pd.DataFrame(columns=columns)

    df = bars_frame(ordered)
    # Columns are collected in a dict and turned into a frame once: assigning
    # ~130 columns one by one into a DataFrame fragments it badly.
    out: dict[str, object] = {"date": df["date"]}
    _price_volume(df, out)
    _vsa_engine(ordered, df, out, config)
    _methods(ordered, df, out, config, method_ids, vsa4_tick)
    _weekly(ordered, df, out, config)

    numeric = [c for c in columns if c not in ("date", LABEL_COLUMN)]
    for col in numeric:
        out.setdefault(col, np.full(len(df), np.nan))
    out.setdefault(LABEL_COLUMN, [""] * len(df))
    frame = pd.DataFrame({c: out[c] for c in columns})
    frame[numeric] = frame[numeric].replace([np.inf, -np.inf], np.nan).astype(float)
    return frame


def _price_volume(df: pd.DataFrame, out: dict[str, object]) -> None:
    """Groups A, B, the 52-week part of E, RVOL, F06 and the regime helpers."""
    o, h, low, c, v = (df[k] for k in ("open", "high", "low", "close", "volume"))
    prev_c = c.shift(1)
    spread = h - low

    # Wilder's ATR: exponential with alpha 1/14, from the first bar onward.
    tr = pd.concat([spread, (h - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / _ATR_BARS, adjust=False, min_periods=_ATR_BARS).mean()
    out["atr14"] = atr

    # ── A: the bar itself, against the bars before it ──────────────────────
    out["spread_rel20"] = _ratio(spread, spread.shift(1).rolling(20).mean())
    out["close_pos"] = np.where(spread > 0, _ratio(c - low, spread), 0.5)
    out["vol_rel20"] = _ratio(v, v.shift(1).rolling(20).mean())
    out["vol_rel_med20"] = _ratio(v, v.shift(1).rolling(20).median())

    vals = v.to_numpy()
    pct60 = np.full(len(vals), np.nan)
    if len(vals) > 60:
        windows = np.lib.stride_tricks.sliding_window_view(vals[:-1], 60)
        pct60[60:] = (windows < vals[60:, None]).mean(axis=1)
    out["vol_pct60"] = pct60

    prior_max20 = v.shift(1).rolling(20).max()
    out["vol_new_max20"] = _flag(v > prior_max20, prior_max20.notna().to_numpy())
    out["gap_atr"] = _ratio(o - prev_c, atr)
    out["body_pos"] = np.where(spread > 0, _ratio(c - o, spread), 0.0)
    up = c > prev_c
    out["up_bar"] = _flag(up, prev_c.notna().to_numpy())
    out["vol_trend5"] = _ratio(v.rolling(5).mean(), v.shift(5).rolling(20).mean())

    # ── B: the recent path ──────────────────────────────────────────────────
    log_ret = np.log(c / prev_c)
    sigma20 = log_ret.rolling(20).std()
    for k in (1, 5, 10, 20, 60):
        out[f"ret{k}_vol"] = np.log(c / c.shift(k)) / (sigma20 * math.sqrt(k)).where(sigma20 > 0)
    out["mom_12_1_raw"] = np.log(c.shift(21) / c.shift(252))
    sma = {k: c.rolling(k).mean() for k in (20, 50, 200)}
    for k, ma in sma.items():
        out[f"dist_ma{k}_atr"] = (c - ma) / atr.where(atr > 0)
    out["ma50_slope10"] = sma[50] / sma[50].shift(10) - 1
    out["ma200_slope20"] = sma[200] / sma[200].shift(20) - 1
    out["dd_60"] = c / h.rolling(60).max() - 1
    out["atr_pct"] = atr / c.where(c > 0)
    out["range_contraction"] = _ratio(tr.rolling(5).mean(), tr.rolling(50).mean())
    out["up_share20"] = pd.Series(np.where(prev_c.notna(), up, np.nan)).rolling(20).mean()

    # ── E: 52-week context (the ranking's definition, per row) ─────────────
    ts = pd.DatetimeIndex(pd.to_datetime(df["date"]))
    day = np.array([d.toordinal() for d in df["date"]], dtype=float)
    hs = pd.Series(h.to_numpy(), index=ts)
    ls = pd.Series(low.to_numpy(), index=ts)
    high_w = hs.rolling(_WEEK52_WINDOW).max().to_numpy()
    low_w = ls.rolling(_WEEK52_WINDOW).min().to_numpy()
    prior_high = hs.rolling(_WEEK52_WINDOW, closed="neither").max().to_numpy()
    prior_low = ls.rolling(_WEEK52_WINDOW, closed="neither").min().to_numpy()
    first = pd.Series(day, index=ts).rolling(_WEEK52_WINDOW).min().to_numpy()
    covered = (day - first) >= _MIN_52W_COVERAGE_DAYS
    cv = c.to_numpy()
    out["dist_52w_high"] = np.where(covered, _ratio(cv, high_w) - 1, np.nan)
    out["dist_52w_low"] = np.where(covered, _ratio(cv, low_w) - 1, np.nan)
    with np.errstate(invalid="ignore"):
        new_high = h.to_numpy() > prior_high
        new_low = low.to_numpy() < prior_low
    out["new_52w_high"] = np.where(covered, new_high.astype(float), np.nan)
    out["new_52w_low"] = np.where(covered, new_low.astype(float), np.nan)

    # Relative-strength raw score (percentiled across the market in dataset).
    rs = pd.Series(0.0, index=c.index)
    for off, weight in zip(_RS_OFFSETS, _RS_WEIGHTS, strict=True):
        rs = rs + weight * (c / c.shift(off).where(c.shift(off) > 0) - 1.0) * 100.0
    out["rs_raw"] = rs

    # RVOL, as compute_surge_metrics was when these features were frozen: 3
    # recent sessions vs the MEAN of the 20 before them. The scanner moved to
    # a median baseline on 2026-09-26; this stays as frozen (DESIGN-CHOICES).
    base = v.shift(_RVOL_RECENT).rolling(_RVOL_BASELINE).mean()
    out["rvol_3_20"] = _ratio(v.rolling(_RVOL_RECENT).mean(), base)
    out["rvol_last"] = _ratio(v, base)
    above = sum((v.shift(j) > base).astype(float) for j in range(_RVOL_RECENT))
    out["rvol_days_above"] = np.where(base > 0, above, np.nan)

    out["zero_vol_60"] = (v == 0).astype(float).rolling(60).sum()

    # Regime and cross-sectional helpers.
    out["turnover_med20"] = (c * v).rolling(20).median()
    out["ret1"] = c / prev_c.where(prev_c > 0) - 1
    out["ret20"] = c / c.shift(20).where(c.shift(20) > 0) - 1
    out["above_ma50"] = _flag(c > sma[50], sma[50].notna().to_numpy())
    out["above_ma200"] = _flag(c > sma[200], sma[200].notna().to_numpy())


def _vsa_engine(
    ordered: list[StooqDailyQuote],
    df: pd.DataFrame,
    out: dict[str, object],
    config: VsaConfig | None,
) -> None:
    """Group C: the app's VSA engine and phase classifier, read per session."""
    n = len(ordered)
    pos_of = {b.date: i for i, b in enumerate(ordered)}
    signals = detect_signals(ordered, config)

    per_name = {name: np.zeros(n) for name in SignalName}
    bull_today = np.zeros(n)
    bear_today = np.zeros(n)
    sig_days: list[float] = []
    sig_weights: list[float] = []
    for s in signals:
        i = pos_of.get(s.date)
        if i is None:
            continue
        per_name[s.signal_name][i] = 1.0
        bullish = s.type == SignalType.BULLISH
        (bull_today if bullish else bear_today)[i] = 1.0
        sig_days.append(float(s.date.toordinal()))
        sig_weights.append(s.strength if bullish else -s.strength)

    for name, slug in _SIGNAL_SLUGS.items():
        out[f"vsa_{slug}5"] = _recent(per_name[name], 5)
    out["vsa_bull_today"] = bull_today
    out["vsa_bear_today"] = bear_today

    row_days = np.array([b.date.toordinal() for b in ordered], dtype=float)
    net = _decayed_net(
        row_days,
        np.array(sig_days),
        np.array(sig_weights),
        _RATING_HALF_LIFE_DAYS,
        window_days=_RATING_WINDOW_DAYS,
    )
    out["vsa_net"] = net
    out["vsa_rating"] = _rating_from_net(net)
    out["vsa_verdict"] = _verdict_from_net(net)
    out["vsa_bull_since"] = sessions_since(bull_today > 0, _SINCE_CAP_SIGNAL)

    # The engine's background proxy: the previous close against the average
    # close of the 30 sessions before it, ±3%.
    c = df["close"]
    ma = c.rolling(_TREND_LOOKBACK).mean().shift(1)
    ref = c.shift(1)
    out["trend_ctx"] = np.select(
        [ref >= ma * (1 + _TREND_BAND), ref <= ma * (1 - _TREND_BAND)], [1.0, -1.0], 0.0
    )

    # Phase (accumulation / mark-up / …), the same classifier the engine can use.
    frame = df[["high", "low", "close", "volume"]].copy()
    spread = frame["high"] - frame["low"]
    frame["close_pos"] = ((frame["close"] - frame["low"]) / spread).where(spread > 0)
    add_phase_columns(frame)
    phases = [classify_row(row) for row in frame.to_dict("records")]
    for phase in Phase:
        out[f"phase_{phase.value}"] = np.array([1.0 if p == phase else 0.0 for p in phases])


def vsa4_rows(
    ordered: list[StooqDailyQuote], tick: str = "point_in_time"
) -> tuple[list[date], list[dict]] | None:
    """VSA V4's per-bar analysis rows, each as the program saw that day.

    The program sizes its price tolerance (``min_tick``) from the **last**
    close it is given (``adapter.config_for``). Read over a whole history, a
    stock that has since crossed 10 zł or 1 zł is therefore analysed in the
    past with a tolerance taken from a later price — the history depends on
    the future. ``tick="point_in_time"`` runs the unchanged program once per
    tolerance the stock's closes ever called for and takes each day's row from
    the run matching that day's own close: exactly what the program would have
    said with the data ending on that day. ``tick="last_close"`` is the app's
    own reading (``VsaV4Method.signals``), kept so the bench can reproduce the
    back-test gate. ``None`` below the method's 40-bar minimum.
    """
    bars, dates = to_engine_bars(ordered)
    if len(bars) < _VSA4_MIN_BARS:
        return None
    if tick == "last_close":
        return dates, analyze(bars, config_for(bars))
    needed = [tick_size(b.close) for b in bars]
    runs = {t: analyze(bars, config_for(bars, min_tick=t)) for t in set(needed)}
    return dates, [runs[t][i] for i, t in enumerate(needed)]


def _vsa4_marks(
    ordered: list[StooqDailyQuote], pos_of: dict[date, int], n: int, tick: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """VSA V4's firings, weakness firings and waiting state, per session.

    The chart's "Watch" marker means "awaiting confirmation *right now*" and
    is only ever drawn on the last bar it is given — as a history it would
    exist only where the data happens to end. The per-bar sequence state
    (``long_setup_pending``) is the same fact read honestly on every day.
    """
    bull, bear, pending = np.zeros(n), np.zeros(n), np.zeros(n)
    labels = [""] * n
    analysed = vsa4_rows(ordered, tick)
    if analysed is None:
        return bull, bear, pending, labels
    for d, row in zip(*analysed, strict=True):
        i = pos_of.get(d)
        if i is None:
            continue
        if row["long_setup_confirmation"]:
            bull[i] = 1.0
            labels[i] = setup_label(row)
        elif row["short_setup_confirmation"]:
            bear[i] = 1.0
        if sequence_state(row).long_pending is not None:
            pending[i] = 1.0
    return bull, bear, pending, labels


def _methods(
    ordered: list[StooqDailyQuote],
    df: pd.DataFrame,
    out: dict[str, object],
    config: VsaConfig | None,
    method_ids: Sequence[str],
    vsa4_tick: str,
) -> None:
    """Group D: every other trading method's firing history, per session."""
    n = len(ordered)
    pos_of = {b.date: i for i, b in enumerate(ordered)}
    labels = [""] * n
    for mid in method_ids:
        method = get_method(mid)
        if method is None:
            continue
        if mid == "vsa4" and method.__class__.__module__ == "app.analysis.methods.vsa4":
            # The real VSA V4: read its rows directly (see ``vsa4_rows``).
            bull, bear, watch, labels = _vsa4_marks(ordered, pos_of, n, vsa4_tick)
        else:
            try:
                marks = method.signals(ordered, config)
            except Exception:  # noqa: BLE001 — one faulty method must not sink a build
                logger.exception("ML features: %s.signals failed; its columns stay empty.", mid)
                continue
            bull = np.zeros(n)
            bear = np.zeros(n)
            watch = np.zeros(n)
            for m in marks:
                i = pos_of.get(m.date)
                if i is None:
                    continue
                if m.type == "Bullish":
                    bull[i] = 1.0
                    if mid == "vsa4":
                        labels[i] = m.label
                elif m.type == "Bearish":
                    bear[i] = 1.0
                elif m.type == "Watch":
                    watch[i] = 1.0
        out[f"fire_{mid}"] = bull
        out[f"m_{mid}_fired1"] = bull
        out[f"m_{mid}_fired5"] = _recent(bull, 5)
        out[f"m_{mid}_fired20"] = _recent(bull, 20)
        out[f"m_{mid}_since"] = sessions_since(bull > 0, _SINCE_CAP_METHOD)
        if mid == "vsa4":
            out["m_vsa4_bear5"] = _recent(bear, 5)
        if mid in ("vsa3", "vsa4"):
            out[f"m_{mid}_watch5"] = _recent(watch, 5)
    out[LABEL_COLUMN] = labels


def _weekly(
    ordered: list[StooqDailyQuote],
    df: pd.DataFrame,
    out: dict[str, object],
    config: VsaConfig | None,
) -> None:
    """E06 / E07: the weekly VSA read as of each session (design choices §3).

    Only completed weeks are used: every ISO week before the row's own week,
    plus the row's own week when the row is a Friday (a week ends on Friday).
    One detection over the whole weekly history, then the rating as of the
    last completed week over a 52-week window with the app's weekly half-life.
    """
    n = len(ordered)
    weekly = resample_weekly(ordered)
    rating_col = np.full(n, np.nan)
    agree_col = np.full(n, np.nan)
    if len(weekly) >= _MIN_WEEKLY_BARS:
        week_index = {}
        for k, wb in enumerate(weekly):
            iso = wb.date.isocalendar()
            week_index[(iso.year, iso.week)] = k
        w_days = np.array([wb.date.toordinal() for wb in weekly], dtype=float)
        signals = detect_signals(weekly, config)
        sig_days = np.array([float(s.date.toordinal()) for s in signals])
        sig_w = np.array(
            [s.strength if s.type == SignalType.BULLISH else -s.strength for s in signals]
        )
        starts = np.array([w_days[max(0, k - _WEEKLY_WINDOW + 1)] for k in range(len(weekly))])
        w_net = _decayed_net(w_days, sig_days, sig_w, _WEEKLY_HALF_LIFE_DAYS, window_start=starts)
        w_rating = _rating_from_net(w_net)
        w_verdict = _verdict_from_net(w_net)
        # compute_weekly_view needs 30 weekly bars in its (capped) window.
        enough = np.arange(1, len(weekly) + 1) >= _MIN_WEEKLY_BARS

        daily_verdict = np.asarray(out["vsa_verdict"], dtype=float)
        for i, b in enumerate(ordered):
            iso = b.date.isocalendar()
            k = week_index[(iso.year, iso.week)]
            available = k if b.date.weekday() >= 4 else k - 1
            if available < 0 or not enough[available]:
                continue
            rating_col[i] = w_rating[available]
            d = np.sign(daily_verdict[i])
            w = np.sign(w_verdict[available])
            agree_col[i] = 0.0 if d == 0 or w == 0 else (1.0 if d == w else -1.0)
    out["weekly_rating"] = rating_col
    out["weekly_agree"] = agree_col
