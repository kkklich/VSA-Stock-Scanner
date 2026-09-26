"""Causal, deliberately heuristic VSA feature and signal engine (stdlib only).

[StockPilot] Vendored from the owner's "VSA - kompendium i program Python"
package (python/engine.py, SHA-256 16a7a08f...1f2c69, supplied 2026-09-24).
The detection and sequence logic is unchanged. The only edits, each marked
``[StockPilot]``, are this note and a few lines in
``add_confirmation_and_setup_events`` that REPORT the sequence state the
function already keeps (which strength/weakness is in the background, which
test is awaiting confirmation, which primary a confirmed setup came from) as
extra row fields. They read state; they never change a flag, a level or a
confirmation. See ``app/analysis/vsa4/__init__.py``.
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable


class VSAError(ValueError):
    """Invalid market data or configuration."""


@dataclass(frozen=True)
class Bar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Config:
    baseline_window: int = 20
    atr_window: int = 14
    trend_window: int = 20
    structure_window: int = 12
    test_window: int = 40
    sequence_window: int = 30
    confirmation_window: int = 3
    pivot_left_bars: int = 2
    pivot_right_bars: int = 2
    max_pivot_gap: int = 40
    min_tick: float = 0.01
    risk_fraction: float = 0.01
    max_notional_fraction: float = 1.0
    initial_capital: float = 10000.0
    reward_risk: float = 3.0
    commission_bps: float = 1.0
    slippage_bps: float = 1.0
    stop_buffer_atr: float = 0.05
    high_volume_ratio: float = 1.5
    extreme_volume_ratio: float = 2.25
    narrow_spread_ratio: float = 0.75
    wide_spread_ratio: float = 1.30
    low_volume_ratio: float = 0.80
    test_volume_ratio: float = 0.65
    close_high_threshold: float = 0.70
    close_low_threshold: float = 0.30
    long_wick_body_ratio: float = 1.8
    test_level_atr_tolerance: float = 0.60
    close_positions_at_end: bool = False

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Config":
        allowed = {item.name for item in fields(cls)}
        unknown = set(data) - allowed
        if unknown:
            raise VSAError(f"Nieznane pola konfiguracji: {', '.join(sorted(unknown))}")
        try:
            config = cls(**data)
        except (TypeError, ValueError) as exc:
            raise VSAError(f"Niepoprawna konfiguracja: {exc}") from exc
        config.validate()
        return config

    @classmethod
    def from_json(cls, path: str | Path) -> "Config":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VSAError(f"Nie można odczytać konfiguracji {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise VSAError("Konfiguracja JSON musi być obiektem.")
        return cls.from_mapping(data)

    def validate(self) -> None:
        for name in (
            "baseline_window", "atr_window", "trend_window", "structure_window",
            "test_window", "sequence_window", "confirmation_window",
            "max_pivot_gap",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise VSAError(f"{name} musi być dodatnią liczbą całkowitą.")
        for name in ("pivot_left_bars", "pivot_right_bars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise VSAError(f"{name} musi być liczbą całkowitą >= 1.")
        positive = (
            "min_tick", "max_notional_fraction", "initial_capital", "reward_risk",
            "high_volume_ratio", "extreme_volume_ratio", "narrow_spread_ratio",
            "wide_spread_ratio", "test_volume_ratio", "long_wick_body_ratio",
            "test_level_atr_tolerance", "low_volume_ratio",
        )
        for name in positive:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise VSAError(f"{name} musi być skończoną liczbą > 0.")
        for name in ("close_high_threshold", "close_low_threshold"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise VSAError(f"{name} musi być skończoną liczbą.")
        for name in (
            "risk_fraction", "commission_bps", "slippage_bps", "stop_buffer_atr",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise VSAError(f"{name} musi być skończoną liczbą >= 0.")
        if not 0 < self.risk_fraction < 1:
            raise VSAError("risk_fraction musi być większe od 0 i mniejsze niż 1.")
        if self.commission_bps >= 10000 or self.slippage_bps >= 10000:
            raise VSAError("commission_bps i slippage_bps muszą być mniejsze niż 10000.")
        if self.close_high_threshold <= self.close_low_threshold or not (
            0 <= self.close_low_threshold < 0.5 < self.close_high_threshold <= 1
        ):
            raise VSAError("Progi położenia zamknięcia muszą obejmować środek zakresu.")
        if self.extreme_volume_ratio < self.high_volume_ratio:
            raise VSAError("extreme_volume_ratio nie może być niższy niż high_volume_ratio.")
        if self.test_volume_ratio >= 1 or self.low_volume_ratio >= 1:
            raise VSAError("Progi wolumenu test_volume_ratio i low_volume_ratio muszą być < 1.")
        if self.narrow_spread_ratio >= self.wide_spread_ratio:
            raise VSAError("narrow_spread_ratio musi być mniejszy od wide_spread_ratio.")
        if not isinstance(self.close_positions_at_end, bool):
            raise VSAError("close_positions_at_end musi mieć wartość true albo false.")


SIGNAL_NAMES = (
    "bag_holding", "selling_climax", "stopping_volume", "shakeout",
    "strength_two_bar_reversal", "no_supply", "test",
    "end_of_rising_market", "buying_climax", "supply_coming_in",
    "trap_upmove", "no_demand", "no_result_from_effort",
    "weakness_two_bar_reversal", "upthrust", "wfo_bullish", "wfo_bearish",
)

STRENGTH_SIGNALS = {
    "bag_holding", "selling_climax", "stopping_volume", "shakeout",
    "strength_two_bar_reversal", "wfo_bullish",
}
WEAKNESS_SIGNALS = {
    "end_of_rising_market", "buying_climax", "supply_coming_in", "trap_upmove",
    "no_result_from_effort", "weakness_two_bar_reversal", "upthrust", "wfo_bearish",
}
LONG_TEST_SIGNALS = {"no_supply", "test"}
SHORT_TEST_SIGNALS = {"no_demand"}


def _finite_float(value: str, field_name: str, line: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VSAError(f"Wiersz {line}: pole {field_name!r} nie jest liczbą: {value!r}.") from exc
    if not math.isfinite(number):
        raise VSAError(f"Wiersz {line}: pole {field_name!r} musi być skończone.")
    return number


def _parse_timestamp(value: str, line: int) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise VSAError(f"Wiersz {line}: timestamp musi być datą ISO-8601: {value!r}.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_ohlcv_csv(path: str | Path) -> list[Bar]:
    """Read and validate strict, nonempty timestamp-sorted OHLCV CSV."""
    try:
        handle = Path(path).open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise VSAError(f"Nie można otworzyć CSV {path}: {exc}") from exc
    with handle:
        return load_ohlcv_stream(handle)


def load_ohlcv_text(text: str) -> list[Bar]:
    """In-memory CSV parser for tests and small integrations."""
    return load_ohlcv_stream(io.StringIO(text))


def load_ohlcv_stream(handle: Any) -> list[Bar]:
    bars: list[Bar] = []
    previous_time: datetime | None = None
    reader = csv.DictReader(handle)
    if not reader.fieldnames:
        raise VSAError("CSV jest pusty albo nie ma nagłówka.")
    normalized = [name.strip().lower() if name else "" for name in reader.fieldnames]
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if len(normalized) != len(set(normalized)):
        raise VSAError("Nagłówek CSV zawiera powtórzone nazwy kolumn.")
    missing = required - set(normalized)
    if missing:
        raise VSAError(f"Brak wymaganych kolumn CSV: {', '.join(sorted(missing))}.")
    mapping = dict(zip(normalized, reader.fieldnames))
    for line, raw in enumerate(reader, start=2):
        if None in raw or any(raw.get(mapping[key]) is None for key in required):
            raise VSAError(f"Wiersz {line}: liczba pól nie odpowiada nagłówkowi.")
        timestamp_raw = (raw.get(mapping["timestamp"]) or "").strip()
        if not timestamp_raw:
            raise VSAError(f"Wiersz {line}: timestamp nie może być pusty.")
        stamp = _parse_timestamp(timestamp_raw, line)
        if previous_time is not None and stamp <= previous_time:
            raise VSAError(f"Wiersz {line}: timestampy muszą rosnąć ściśle.")
        previous_time = stamp
        values = {
            name: _finite_float(raw.get(mapping[name], ""), name, line)
            for name in ("open", "high", "low", "close", "volume")
        }
        for name in ("open", "high", "low", "close"):
            if values[name] <= 0:
                raise VSAError(f"Wiersz {line}: cena {name} musi być > 0.")
        if values["volume"] < 0:
            raise VSAError(f"Wiersz {line}: volume nie może być ujemny.")
        if values["high"] < max(values["open"], values["close"]):
            raise VSAError(f"Wiersz {line}: high musi być >= open i close.")
        if values["low"] > min(values["open"], values["close"]):
            raise VSAError(f"Wiersz {line}: low musi być <= open i close.")
        if values["high"] < values["low"]:
            raise VSAError(f"Wiersz {line}: high musi być >= low.")
        bars.append(Bar(timestamp=stamp.isoformat().replace("+00:00", "Z"), **values))
    if not bars:
        raise VSAError("CSV musi zawierać co najmniej jeden bar OHLCV.")
    return bars


def _mean(values: Iterable[float]) -> float | None:
    items = list(values)
    return fmean(items) if items else None


def build_features(bars: list[Bar], config: Config) -> list[dict[str, Any]]:
    """Create causal features; normalization baselines exclude the current bar."""
    result: list[dict[str, Any]] = []
    true_ranges: list[float] = []
    bodies: list[float] = []
    for i, bar in enumerate(bars):
        spread = bar.high - bar.low
        body = abs(bar.close - bar.open)
        upper_wick = bar.high - max(bar.open, bar.close)
        lower_wick = min(bar.open, bar.close) - bar.low
        prev_close = bars[i - 1].close if i else None
        prior_start = max(0, i - config.baseline_window)
        prior = bars[prior_start:i]
        prior_vol_mean = _mean(item.volume for item in prior)
        prior_spread_mean = _mean(item.high - item.low for item in prior)
        prior_body_median = median(bodies[prior_start:i]) if i > prior_start else None
        volume_ratio = bar.volume / prior_vol_mean if prior_vol_mean and prior_vol_mean > 0 else None
        spread_ratio = spread / prior_spread_mean if prior_spread_mean and prior_spread_mean > 0 else None
        body_ratio = body / prior_body_median if prior_body_median and prior_body_median > 0 else None
        close_position = (bar.close - bar.low) / spread if spread > 0 else None
        pink = (
            i >= 2 and bar.volume > 0 and bars[i - 1].volume > 0 and bars[i - 2].volume > 0
            and bar.volume < bars[i - 1].volume and bar.volume < bars[i - 2].volume
        )
        tr = spread if prev_close is None else max(
            spread, abs(bar.high - prev_close), abs(bar.low - prev_close)
        )
        true_ranges.append(tr)
        atr = fmean(true_ranges[max(0, i - config.atr_window + 1): i + 1])
        # Context uses only current/past closes. It is descriptive, never a future label.
        trend = "unknown"
        if i > config.trend_window:
            # Exclude the current (potential reversal) bar from prior-trend context.
            movement = bars[i - 1].close - bars[i - 1 - config.trend_window].close
            threshold = max(config.min_tick, atr * 0.25)
            trend = "up" if movement > threshold else "down" if movement < -threshold else "sideways"
        background = "unavailable"
        if prior:
            prior_low = min(item.low for item in prior[-config.structure_window:])
            prior_high = max(item.high for item in prior[-config.structure_window:])
            tolerance = max(config.min_tick, atr * 0.75)
            if bar.close <= prior_low + tolerance:
                background = "near_support"
            elif bar.close >= prior_high - tolerance:
                background = "near_resistance"
            else:
                background = "middle_of_recent_range"
        up_bar = prev_close is not None and bar.close > prev_close
        down_bar = prev_close is not None and bar.close < prev_close
        row: dict[str, Any] = {
            "timestamp": bar.timestamp,
            "open": bar.open, "high": bar.high, "low": bar.low,
            "close": bar.close, "volume": bar.volume,
            "spread": spread, "body": body,
            "upper_wick": upper_wick, "lower_wick": lower_wick,
            "close_position": close_position,
            "true_range": tr, "atr": atr,
            "prior_volume_mean": prior_vol_mean,
            "volume_ratio": volume_ratio,
            "prior_spread_mean": prior_spread_mean,
            "spread_ratio": spread_ratio,
            "prior_body_median": prior_body_median,
            "body_ratio": body_ratio,
            "up_bar": up_bar, "down_bar": down_bar,
            "pink_volume": pink,
            "zero_range": spread == 0, "zero_volume": bar.volume == 0,
            "warmup_ready": i >= config.baseline_window and i >= config.atr_window - 1,
            "trend_context": trend, "background": background,
            "volume_class": (
                "unavailable" if volume_ratio is None else
                "extreme" if volume_ratio >= config.extreme_volume_ratio else
                "high" if volume_ratio >= config.high_volume_ratio else
                "low" if volume_ratio <= config.low_volume_ratio else "ordinary"
            ),
            "spread_class": (
                "unavailable" if spread_ratio is None else
                "narrow" if spread_ratio <= config.narrow_spread_ratio else
                "wide" if spread_ratio >= config.wide_spread_ratio else "ordinary"
            ),
        }
        result.append(row)
        bodies.append(body)
    return result


def _valid_signal_bar(row: dict[str, Any]) -> bool:
    return not row["zero_range"] and not row["zero_volume"]


def _wick_ratio(wick: float, body: float, config: Config) -> float:
    return wick / max(body, config.min_tick)


def detect_candidates(
    bars: list[Bar], features: list[dict[str, Any]], config: Config
) -> tuple[list[dict[str, bool]], list[list[str]], list[list[str]]]:
    """Return current-bar candidate flags, reasons and delayed WFO pivot timestamps."""
    flags: list[dict[str, bool]] = []
    reasons: list[list[str]] = []
    pivot_stamps: list[list[str]] = []
    confirmed_high_pivots: list[int] = []
    confirmed_low_pivots: list[int] = []
    index_by_timestamp = {item.timestamp: idx for idx, item in enumerate(bars)}

    for i, (bar, row) in enumerate(zip(bars, features)):
        active = {name: False for name in SIGNAL_NAMES}
        why: list[str] = []
        pivot_stamps_at_bar: list[str] = []
        valid = _valid_signal_bar(row) and row["warmup_ready"]
        vol_ratio = row["volume_ratio"]
        spread_ratio = row["spread_ratio"]
        high_vol = vol_ratio is not None and vol_ratio >= config.high_volume_ratio
        extreme_vol = vol_ratio is not None and vol_ratio >= config.extreme_volume_ratio
        wide = spread_ratio is not None and spread_ratio >= config.wide_spread_ratio
        narrow = spread_ratio is not None and spread_ratio <= config.narrow_spread_ratio
        cp = row["close_position"]
        body = row["body"]
        upper = row["upper_wick"]
        lower = row["lower_wick"]
        candle_up = bar.close > bar.open
        candle_down = bar.close < bar.open
        prior = bars[max(0, i - config.structure_window):i]
        prior_high = max((item.high for item in prior), default=None)
        prior_low = min((item.low for item in prior), default=None)
        trend = row["trend_context"]

        def mark(name: str, explanation: str) -> None:
            active[name] = True
            why.append(f"{name}: {explanation}")

        if valid and row["pink_volume"] and row["down_bar"] and narrow:
            mark("no_supply", "down bar, pink volume < two preceding bars, narrow spread")
        if valid and row["pink_volume"] and row["up_bar"] and narrow:
            mark("no_demand", "up bar, pink volume < two preceding bars, narrow spread")

        # The course requires prior demand/accumulation, a low-volume revisit,
        # medium/narrow spread and a lower wick. Pink volume is not required.
        if valid and row["close"] > bar.low and spread_ratio is not None and spread_ratio < config.wide_spread_ratio and lower >= row["spread"] * 0.15:
            for strength_i in range(max(0, i - config.test_window), i):
                for strength_name in STRENGTH_SIGNALS:
                    if not flags[strength_i][strength_name]:
                        continue
                    # Stopping Volume is a two-bar signal; its preceding down bar is
                    # the high-volume test-zone reference, not a later red candle.
                    if strength_name == "wfo_bullish" and pivot_stamps[strength_i]:
                        ref_i = index_by_timestamp.get(pivot_stamps[strength_i][-1], strength_i)
                    else:
                        ref_i = strength_i - 1 if strength_name == "stopping_volume" else strength_i
                    if ref_i < 0:
                        continue
                    ref, refbar = features[ref_i], bars[ref_i]
                    if (
                        (ref["down_bar"] or strength_name == "wfo_bullish") and ref["volume_ratio"] is not None
                        and ref["volume_ratio"] >= config.high_volume_ratio
                        and abs(bar.low - refbar.low) <= max(config.min_tick, row["atr"] * config.test_level_atr_tolerance)
                        and bar.volume < refbar.volume * config.test_volume_ratio
                        and row["volume_ratio"] is not None
                        and row["volume_ratio"] <= config.low_volume_ratio
                    ):
                        mark("test", f"retest of prior {strength_name} demand-zone low from {refbar.timestamp}; low volume, medium/narrow spread and lower wick; pink not required")
                        break
                if active["test"]:
                    break

        # The transcript describes Bag Holding as a narrow, high-volume bar in a decline;
        # candle direction can vary. This follows lesson 8 audio, not the simplified map.
        if valid and trend == "down" and narrow and extreme_vol and cp is not None and 0.30 <= cp <= 0.70:
            mark("bag_holding", "declining prior background, narrow spread, ultra-high volume, middle close; candle colour unrestricted")

        prior_volumes = [item.volume for item in bars[max(0, i - config.baseline_window):i]]
        record_volume = bool(prior_volumes) and bar.volume >= max(prior_volumes)
        if valid and trend == "down" and row["down_bar"] and wide and high_vol and record_volume and cp is not None:
            if 0.30 <= cp <= 0.70 and lower > 0:
                mark("selling_climax", "wide down bar, middle close, lower wick, high and trailing-record volume")

        if valid and i >= 2 and trend == "down":
            prev = bars[i - 1]
            prev_ratio = features[i - 1]["volume_ratio"]
            if features[i - 1]["down_bar"] and row["up_bar"] and cp is not None and cp >= config.close_high_threshold and prev_ratio is not None and prev_ratio >= config.high_volume_ratio:
                mark("stopping_volume", "high-volume down bar followed by an up bar closing high in its own range")

        if valid and prior_low is not None and prior_high is not None:
            if (
                bar.low < prior_low - config.min_tick
                and bar.close > prior_low and cp is not None and cp >= config.close_high_threshold
                and high_vol and wide
            ):
                mark("shakeout", "wide high-volume bar swept a recent low and closed in its upper third; candle colour unrestricted")

        if valid and i >= 2 and trend == "down":
            prev = bars[i - 1]
            prev_body = abs(prev.close - prev.open)
            if (
                features[i - 1]["down_bar"] and row["up_bar"] and prev_body > 0
                and body >= prev_body * 0.65
                and bar.close >= prev.open - max(config.min_tick, row["atr"] * 0.05)
                and bar.volume >= prev.volume
            ):
                mark("strength_two_bar_reversal", "down candle followed by up candle closing near or above prior open; V2>=V1")

        if valid and trend == "up" and row["up_bar"] and narrow and extreme_vol and cp is not None and 0.30 <= cp <= 0.70:
            mark("end_of_rising_market", "after a rise: narrow up bar, ultra-high volume and middle close")

        if valid and trend == "up" and row["up_bar"] and wide and high_vol and record_volume and cp is not None:
            if 0.30 <= cp <= 0.70 and upper > 0:
                mark("buying_climax", "wide up bar, middle close, upper wick, high and trailing-record volume")

        prior_window_vol = [item.volume for item in bars[max(0, i - config.structure_window):i]]
        if valid and trend == "up" and row["up_bar"] and upper > 0 and high_vol:
            if prior_window_vol and bar.volume < max(prior_window_vol):
                mark("supply_coming_in", "up bar with upper wick and increased, but non-record, volume")

        if valid and trend != "unknown" and prior_high is not None:
            if (
                bar.high > prior_high + config.min_tick and cp is not None and cp <= config.close_low_threshold
                and wide and high_vol
            ):
                mark("trap_upmove", "upward trap attempt rejected with low close, wide spread and increased volume")

        if valid and trend == "up" and wide and high_vol and cp is not None:
            if _wick_ratio(upper, body, config) >= 1.0 and cp <= config.close_low_threshold:
                mark("no_result_from_effort", "wide high-volume bar, long upper wick and close near low")

        if valid and i >= 2 and trend == "up":
            prev = bars[i - 1]
            prev_body = abs(prev.close - prev.open)
            if (
                features[i - 1]["up_bar"] and row["down_bar"] and prev_body > 0
                and body >= prev_body * 0.65
                and bar.close <= prev.open + max(config.min_tick, row["atr"] * 0.05)
                and bar.volume >= prev.volume
            ):
                mark("weakness_two_bar_reversal", "up candle followed by down candle closing near or below prior open; V2>=V1")

        if valid and trend == "up" and prior_high is not None:
            if (
                bar.high > prior_high + config.min_tick and bar.close < prior_high
                and _wick_ratio(upper, body, config) >= config.long_wick_body_ratio
                and cp is not None and cp <= config.close_low_threshold
            ):
                subtype = "high-volume supply" if high_vol else "not-high-volume variant"
                mark("upthrust", f"new high rejected below prior resistance with long upper wick; {subtype}")

        # Symmetric local pivots are emitted only when all right-side bars have closed.
        pivot_index = i - config.pivot_right_bars
        if pivot_index >= config.pivot_left_bars:
            start = pivot_index - config.pivot_left_bars
            end = pivot_index + config.pivot_right_bars
            window = bars[start:end + 1]
            pivot = bars[pivot_index]
            left_bars = bars[start:pivot_index]
            right_bars = bars[pivot_index + 1:end + 1]
            is_high = all(pivot.high > item.high for item in left_bars) and all(pivot.high >= item.high for item in right_bars)
            is_low = all(pivot.low < item.low for item in left_bars) and all(pivot.low <= item.low for item in right_bars)
            if is_high:
                prev_pivot = next((p for p in reversed(confirmed_high_pivots) if pivot_index - p <= config.max_pivot_gap), None)
                confirmed_high_pivots.append(pivot_index)
                if prev_pivot is not None:
                    between_max = max((bars[j].volume for j in range(prev_pivot + 1, pivot_index)), default=0.0)
                    v1, v2 = bars[prev_pivot].volume, pivot.volume
                    if (
                        pivot.high >= bars[prev_pivot].high + config.min_tick
                        and v1 > v2 > between_max
                        and features[prev_pivot]["warmup_ready"]
                        and features[prev_pivot]["volume_ratio"] is not None
                        and features[prev_pivot]["volume_ratio"] >= config.high_volume_ratio
                        and features[pivot_index]["warmup_ready"]
                        and bars[prev_pivot].volume > 0 and pivot.volume > 0
                    ):
                        active["wfo_bearish"] = True
                        pivot_stamps_at_bar.append(pivot.timestamp)
                        why.append(
                            f"wfo_bearish: confirmed higher high at {pivot.timestamp}; pivot volumes V1>V2>max(intervening)"
                        )
            if is_low:
                prev_pivot = next((p for p in reversed(confirmed_low_pivots) if pivot_index - p <= config.max_pivot_gap), None)
                confirmed_low_pivots.append(pivot_index)
                if prev_pivot is not None:
                    between_max = max((bars[j].volume for j in range(prev_pivot + 1, pivot_index)), default=0.0)
                    v1, v2 = bars[prev_pivot].volume, pivot.volume
                    if (
                        pivot.low <= bars[prev_pivot].low - config.min_tick
                        and v1 > v2 > between_max
                        and features[prev_pivot]["warmup_ready"]
                        and features[prev_pivot]["volume_ratio"] is not None
                        and features[prev_pivot]["volume_ratio"] >= config.high_volume_ratio
                        and features[pivot_index]["warmup_ready"]
                        and bars[prev_pivot].volume > 0 and pivot.volume > 0
                    ):
                        active["wfo_bullish"] = True
                        pivot_stamps_at_bar.append(pivot.timestamp)
                        why.append(
                            f"wfo_bullish: confirmed lower low at {pivot.timestamp}; pivot volumes V1>V2>max(intervening)"
                        )
        flags.append(active)
        reasons.append(why)
        pivot_stamps.append(pivot_stamps_at_bar)
    return flags, reasons, pivot_stamps


def add_confirmation_and_setup_events(
    bars: list[Bar], features: list[dict[str, Any]], flags: list[dict[str, bool]],
    reasons: list[list[str]], pivot_stamps: list[list[str]], config: Config,
) -> list[dict[str, Any]]:
    """Create confirmation events only on the bar where they become observable."""
    rows: list[dict[str, Any]] = []
    pending_signals: list[tuple[int, str, str, float]] = []
    pending_long: dict[str, Any] | None = None
    pending_short: dict[str, Any] | None = None
    last_strength: int | None = None
    last_weakness: int | None = None
    index_by_timestamp = {item.timestamp: idx for idx, item in enumerate(bars)}

    def primary_level(name: str, index: int, direction: str) -> float:
        if name == "wfo_bullish" and pivot_stamps[index]:
            pivot_index = index_by_timestamp.get(pivot_stamps[index][-1])
            if pivot_index is not None:
                return bars[pivot_index].low
        if name == "wfo_bearish" and pivot_stamps[index]:
            pivot_index = index_by_timestamp.get(pivot_stamps[index][0])
            if pivot_index is not None:
                return bars[pivot_index].high
        if name in {"stopping_volume", "strength_two_bar_reversal"} and direction == "long" and index > 0:
            return min(bars[index - 1].low, bars[index].low)
        if name == "weakness_two_bar_reversal" and direction == "short" and index > 0:
            return max(bars[index - 1].high, bars[index].high)
        return bars[index].low if direction == "long" else bars[index].high

    last_strength_level: float | None = None
    last_weakness_level: float | None = None
    # [StockPilot] Names of the current background legs, kept beside their
    # indices only so the rows can report them (see the end of the loop).
    last_strength_name: str | None = None
    last_weakness_name: str | None = None

    for i, (bar, feat, candidates) in enumerate(zip(bars, features, flags)):
        # Clear stale background legs before a later test is allowed to reuse them.
        if last_strength is not None and last_strength_level is not None:
            if bar.low < last_strength_level - config.min_tick or any(candidates[name] for name in WEAKNESS_SIGNALS):
                last_strength = None
                last_strength_level = None
        if last_weakness is not None and last_weakness_level is not None:
            if bar.high > last_weakness_level + config.min_tick or any(candidates[name] for name in STRENGTH_SIGNALS):
                last_weakness = None
                last_weakness_level = None

        confirmed_bull: list[str] = []
        confirmed_bear: list[str] = []
        still_pending: list[tuple[int, str, str, float]] = []
        for source_index, name, direction, invalid_level in pending_signals:
            age = i - source_index
            if age <= 0:
                still_pending.append((source_index, name, direction, invalid_level))
                continue
            invalidated = (
                (direction == "long" and bar.low < invalid_level - config.min_tick)
                or (direction == "short" and bar.high > invalid_level + config.min_tick)
                or (direction == "long" and any(candidates[s] for s in WEAKNESS_SIGNALS))
                or (direction == "short" and any(candidates[s] for s in STRENGTH_SIGNALS))
            )
            if invalidated or age > config.confirmation_window:
                continue
            source = bars[source_index]
            if direction == "long" and _valid_signal_bar(feat) and feat["up_bar"] and bar.close > source.close:
                confirmed_bull.append(f"{name}@{source.timestamp}")
            elif direction == "short" and _valid_signal_bar(feat) and feat["down_bar"] and bar.close < source.close:
                confirmed_bear.append(f"{name}@{source.timestamp}")
            else:
                still_pending.append((source_index, name, direction, invalid_level))
        pending_signals = still_pending

        # A setup confirmation uses a close breakout after a prior strength/weakness
        # and a later test/no-supply/no-demand. It is never backdated to either signal.
        long_confirm = False
        short_confirm = False
        long_setup_name = ""
        short_setup_name = ""
        setup_primary_name = ""  # [StockPilot] reported only
        long_stop: float | None = None
        short_stop: float | None = None
        if pending_long is not None:
            age = i - pending_long["secondary_index"]
            invalidated = bar.low < pending_long["stop"] - config.min_tick or any(candidates[name] for name in WEAKNESS_SIGNALS)
            if invalidated or age > config.confirmation_window:
                pending_long = None
            elif age > 0 and feat["up_bar"] and bar.close > pending_long["secondary_high"] and bar.volume > pending_long["secondary_volume"]:
                long_confirm = True
                long_setup_name = pending_long["secondary_name"]
                setup_primary_name = pending_long["primary_name"]  # [StockPilot]
                long_stop = pending_long["stop"] - feat["atr"] * config.stop_buffer_atr
                pending_long = None
        if pending_short is not None:
            age = i - pending_short["secondary_index"]
            invalidated = bar.high > pending_short["stop"] + config.min_tick or any(candidates[name] for name in STRENGTH_SIGNALS)
            if invalidated or age > config.confirmation_window:
                pending_short = None
            elif age > 0 and feat["down_bar"] and bar.close < pending_short["secondary_low"] and bar.volume > pending_short["secondary_volume"]:
                short_confirm = True
                short_setup_name = pending_short["secondary_name"]
                if not long_confirm:  # [StockPilot] same precedence as setup_reference_signal
                    setup_primary_name = pending_short["primary_name"]
                short_stop = pending_short["stop"] + feat["atr"] * config.stop_buffer_atr
                pending_short = None

        row: dict[str, Any] = dict(feat)
        for name in SIGNAL_NAMES:
            row[f"candidate_{name}"] = candidates[name]
        row["candidate_signals"] = ";".join(name for name in SIGNAL_NAMES if candidates[name])
        row["candidate_reasons"] = " | ".join(reasons[i])
        row["wfo_pivot_timestamp"] = ";".join(pivot_stamps[i])
        row["wfo_detection_timestamp"] = bar.timestamp if pivot_stamps[i] else ""
        row["price_confirmed_bullish_signals"] = ";".join(confirmed_bull)
        row["price_confirmed_bearish_signals"] = ";".join(confirmed_bear)
        row["long_setup_confirmation"] = long_confirm
        row["short_setup_confirmation"] = short_confirm
        row["setup_reference_signal"] = long_setup_name or short_setup_name
        row["setup_primary_signal"] = setup_primary_name  # [StockPilot]
        row["setup_stop_level"] = long_stop if long_confirm else short_stop if short_confirm else None
        row["entry_status"] = ""
        rows.append(row)

        # Consume signal candidates only after prior confirmations have been checked.
        for name in SIGNAL_NAMES:
            if candidates[name]:
                if name in STRENGTH_SIGNALS or name in LONG_TEST_SIGNALS:
                    pending_signals.append((i, name, "long", primary_level(name, i, "long")))
                elif name in WEAKNESS_SIGNALS or name in SHORT_TEST_SIGNALS:
                    pending_signals.append((i, name, "short", primary_level(name, i, "short")))

        # Secondary sequence elements must follow (strictly later than) the first leg.
        primary_strength_before = last_strength
        primary_weakness_before = last_weakness
        if any(candidates[name] for name in LONG_TEST_SIGNALS) and primary_strength_before is not None:
            if i - primary_strength_before <= config.sequence_window:
                secondary = "no_supply" if candidates["no_supply"] else "test"
                stop_levels = [bars[j].low for j in range(primary_strength_before, i + 1)]
                # Keep the full structural primary level; for a two-bar reversal
                # its first bar can define the true swing low.
                if last_strength_level is not None:
                    stop_levels.append(last_strength_level)
                if flags[primary_strength_before]["wfo_bullish"] and pivot_stamps[primary_strength_before]:
                    pivot_i = index_by_timestamp.get(pivot_stamps[primary_strength_before][-1])
                    if pivot_i is not None:
                        stop_levels.append(bars[pivot_i].low)
                stop = min(stop_levels)
                pending_long = {
                    "secondary_index": i, "secondary_name": secondary,
                    "secondary_high": bar.high, "secondary_volume": bar.volume,
                    "stop": stop,
                    "primary_name": last_strength_name or "",  # [StockPilot] reported only
                }
        if any(candidates[name] for name in SHORT_TEST_SIGNALS) and primary_weakness_before is not None:
            if i - primary_weakness_before <= config.sequence_window:
                stop_levels = [bars[j].high for j in range(primary_weakness_before, i + 1)]
                # The first candle of a two-bar weakness pattern may define the
                # structural high used for the stop.
                if last_weakness_level is not None:
                    stop_levels.append(last_weakness_level)
                if flags[primary_weakness_before]["wfo_bearish"] and pivot_stamps[primary_weakness_before]:
                    pivot_i = index_by_timestamp.get(pivot_stamps[primary_weakness_before][0])
                    if pivot_i is not None:
                        stop_levels.append(bars[pivot_i].high)
                stop = max(stop_levels)
                pending_short = {
                    "secondary_index": i, "secondary_name": "no_demand",
                    "secondary_low": bar.low, "secondary_volume": bar.volume,
                    "stop": stop,
                    "primary_name": last_weakness_name or "",  # [StockPilot] reported only
                }
        if any(candidates[name] for name in STRENGTH_SIGNALS):
            last_strength = i
            selected = next(name for name in SIGNAL_NAMES if candidates[name] and name in STRENGTH_SIGNALS)
            last_strength_level = primary_level(selected, i, "long")
            last_strength_name = selected  # [StockPilot]
        if any(candidates[name] for name in WEAKNESS_SIGNALS):
            last_weakness = i
            selected = next(name for name in SIGNAL_NAMES if candidates[name] and name in WEAKNESS_SIGNALS)
            last_weakness_level = primary_level(selected, i, "short")
            last_weakness_name = selected  # [StockPilot]

        # [StockPilot] Report the sequence state as it stands after this bar's
        # close, in the same "name@timestamp" form the confirmation columns use.
        # A background leg is reported only while a test could still use it (the
        # sequence_window check above); a pending test only while the next bar
        # could still confirm it (the confirmation_window check above). Nothing
        # here feeds back into the logic.
        row["long_background"] = (
            f"{last_strength_name}@{bars[last_strength].timestamp}"
            if last_strength is not None and i - last_strength <= config.sequence_window
            else ""
        )
        row["short_background"] = (
            f"{last_weakness_name}@{bars[last_weakness].timestamp}"
            if last_weakness is not None and i - last_weakness <= config.sequence_window
            else ""
        )
        row["long_setup_pending"] = (
            f"{pending_long['primary_name']}>{pending_long['secondary_name']}"
            f"@{bars[pending_long['secondary_index']].timestamp}"
            if pending_long is not None
            and i - pending_long["secondary_index"] < config.confirmation_window
            else ""
        )
        row["short_setup_pending"] = (
            f"{pending_short['primary_name']}>{pending_short['secondary_name']}"
            f"@{bars[pending_short['secondary_index']].timestamp}"
            if pending_short is not None
            and i - pending_short["secondary_index"] < config.confirmation_window
            else ""
        )
    return rows


def _validate_bar_sequence(bars: list[Bar]) -> None:
    if not bars:
        raise VSAError("Potrzebny jest co najmniej jeden bar OHLCV.")
    previous: datetime | None = None
    for i, bar in enumerate(bars, start=1):
        stamp = _parse_timestamp(bar.timestamp, i + 1)
        if previous is not None and stamp <= previous:
            raise VSAError(f"Bar {i}: timestampy muszą rosnąć ściśle.")
        previous = stamp
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise VSAError(f"Bar {i}: ceny i wolumen muszą być liczbami skończonymi.")
        if min(bar.open, bar.high, bar.low, bar.close) <= 0 or bar.volume < 0:
            raise VSAError(f"Bar {i}: ceny muszą być > 0, wolumen >= 0.")
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.high < bar.low:
            raise VSAError(f"Bar {i}: niespójny zakres OHLC.")


def analyze(bars: list[Bar], config: Config) -> list[dict[str, Any]]:
    config.validate()
    _validate_bar_sequence(bars)
    features = build_features(bars, config)
    candidates, reasons, pivot_stamps = detect_candidates(bars, features, config)
    return add_confirmation_and_setup_events(bars, features, candidates, reasons, pivot_stamps, config)


def config_as_dict(config: Config) -> dict[str, Any]:
    return asdict(config)
