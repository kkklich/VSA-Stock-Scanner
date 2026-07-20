"""Tests for the scanner back-test statistics (``compute_scanner_stats``).

The signal detector is monkeypatched so each test controls exactly which
signals fire; the OHLCV series is engineered so the stock's baseline (the
median 10-session forward return) and the probed signals' forward returns are
known values. That pins the two contracts the Scanner page relies on:

* a "win" means beating the stock's OWN baseline in the signal's direction,
  not merely moving away from zero;
* winner/loser magnitudes live in the same baseline-excess frame as the
  classification, so reward/risk never mixes the two.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest

import app.services.scanner_service as scanner_service
from app.analysis.vsa import SignalName, SignalType, VsaSignal
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.scanner_service import compute_scanner_stats

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(d: date, close: float, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(round(close * 1.02, 2))),
        low=Decimal(str(round(close * 0.98, 2))),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(closes: list[float], end: date | None = None) -> list[StooqDailyQuote]:
    """One daily bar per close, ending at ``end`` (default today)."""
    if end is None:
        end = date.today()
    days = len(closes)
    return [
        _quote(end - timedelta(days=days - 1 - i), closes[i]) for i in range(days)
    ]


def _probe_closes() -> list[float]:
    """30 closes whose baseline (median 10-session forward return) is +4%.

    Two probe windows deviate from it: bar 5 → +2% (positive, but BELOW the
    baseline) and bar 6 → +10% (above it). All other windows return ~+4%.
    """
    first = [100.0] * 10
    second = [104.0] * 10
    second[5] = 102.0  # bar 15: forward target of bar 5 → +2%
    second[6] = 110.0  # bar 16: forward target of bar 6 → +10%
    third = [round(c * 1.04, 2) for c in second]  # keeps decade-2 windows at +4%
    return first + second + third


class _FakeStooqClient:
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        self._quotes = quotes

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._quotes


def _run_stats(
    quotes: list[StooqDailyQuote],
    signals: list[VsaSignal],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, scanner_service.SignalEffStats]:
    """Run the back-test over one company with canned signals; key by name."""
    monkeypatch.setattr(
        scanner_service, "detect_signals", lambda bars, config=None: list(signals)
    )
    stats = asyncio.run(
        compute_scanner_stats(
            companies=[
                GpwCompany(ticker="tst", name="Test SA", sector=None, market_cap=None)
            ],
            stooq=_FakeStooqClient(quotes),
            history_cache=TTLCache(),
            history_cache_ttl=60,
        )
    )
    return {s.signal: s for s in stats}


def _signal(
    quotes: list[StooqDailyQuote],
    idx: int,
    name: SignalName = SignalName.SOS,
    type_: SignalType = SignalType.BULLISH,
) -> VsaSignal:
    return VsaSignal(date=quotes[idx].date, signal_name=name, type=type_, strength=1.0)


# ── compute_scanner_stats ─────────────────────────────────────────────────────


class TestComputeScannerStats:
    def test_bullish_win_must_beat_the_baseline(self, monkeypatch) -> None:
        # Forward return +2% is positive but BELOW the stock's +4% baseline
        # drift: under the old vs-zero rule this was a "win"; baseline-
        # relative it is a loss (a random-day entry would have done better).
        quotes = _series(_probe_closes())
        stats = _run_stats(quotes, [_signal(quotes, 5)], monkeypatch)

        row = stats["Sign of Strength"]
        assert row.count == 1
        assert row.success_pct == 0.0
        # One loss, zero wins: reward/risk is a defined (and worst) 0.0.
        assert row.reward_risk == 0.0

    def test_bearish_win_is_baseline_relative(self, monkeypatch) -> None:
        # The same +2% window is a WIN for a bearish signal: the stock rose
        # less than its own +4% drift, so the short beat the baseline even
        # though the price went up.
        quotes = _series(_probe_closes())
        stats = _run_stats(
            quotes,
            [_signal(quotes, 5, name=SignalName.SOW, type_=SignalType.BEARISH)],
            monkeypatch,
        )

        row = stats["Sign of Weakness"]
        assert row.count == 1
        assert row.success_pct == 100.0
        # Wins but no losses: the ratio is undefined — None, not 0.
        assert row.reward_risk is None

    def test_magnitudes_measured_as_baseline_excess(self, monkeypatch) -> None:
        # Two bullish probes vs the +4% baseline: bar 6 wins by 6pp (10−4)
        # and bar 5 loses by 2pp (|2−4|) → reward/risk 3.0. Absolute
        # magnitudes (10%/2%) would report 5.0 — a different frame from the
        # classification, which is exactly the bug this pins.
        quotes = _series(_probe_closes())
        stats = _run_stats(
            quotes, [_signal(quotes, 5), _signal(quotes, 6)], monkeypatch
        )

        row = stats["Sign of Strength"]
        assert row.count == 2
        assert row.success_pct == 50.0
        assert row.reward_risk == pytest.approx(3.0, abs=0.01)

    def test_reward_risk_none_when_nothing_evaluable(self, monkeypatch) -> None:
        # No judged occurrences at all — whether no signal fired or the only
        # one is too fresh to have forward data — leaves the ratio undefined.
        quotes = _series(_probe_closes())

        stats = _run_stats(quotes, [], monkeypatch)
        assert all(row.count == 0 for row in stats.values())
        assert all(row.reward_risk is None for row in stats.values())

        fresh_only = [_signal(quotes, len(quotes) - 1)]
        stats = _run_stats(quotes, fresh_only, monkeypatch)
        row = stats["Sign of Strength"]
        assert row.count == 0
        assert row.reward_risk is None
        assert row.active_count == 1  # still reported as the latest signal
