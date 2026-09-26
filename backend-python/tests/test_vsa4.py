"""VSA V4: the owner's VSA program as a trading method and a trade simulation.

The program's own behaviour is pinned by its own tests
(``tests/test_vsa4_program.py``). These cover what the app adds around it:
the bar adapter, the method's score ladder / chart markers / slicing, the
simulation payload, and the endpoint — using the program's own 45-bar sample
(``tests/data_vsa4_sample.py``), which walks one complete long sequence.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.analysis.methods import get_method, method_ids
from app.analysis.methods.base import NEVER_FIRED
from app.analysis.methods.vsa4 import _EVAL_BARS, _WARMUP_BARS
from app.analysis.vsa4.adapter import (
    SIGNAL_LABELS,
    analyze_quotes,
    config_for,
    sequence_state,
    setup_label,
    simulate,
    tick_size,
    to_engine_bars,
)
from app.analysis.vsa4.engine import SIGNAL_NAMES, analyze
from app.dependencies import get_stooq_client, history_cache, ranking_cache
from app.main import app
from app.models import StooqDailyQuote
from app.routers.stocks import _backfill_attempted
from app.services.trade_simulation_service import build_trade_simulation
from tests.data_vsa4_sample import (
    DEMO_CLOSED_TRADES,
    DEMO_ENTRY_BAR,
    DEMO_ENTRY_PRICE,
    DEMO_EXIT_BAR,
    DEMO_EXIT_REASON,
    DEMO_FINAL_EQUITY,
    DEMO_LONG_SETUPS,
    DEMO_SHORT_SETUPS,
    DEMO_SIGNAL_BAR,
    DEMO_SIGNAL_NAME,
    DEMO_STOP_LOSS,
    SAMPLE_BARS,
)

_START = date(2025, 1, 1)
# Twenty flat, quiet bars in front of the sample: the method needs 40 bars
# before it evaluates at all, and these raise no signal of their own (constant
# volume is never "pink", a flat bar is never a pivot), so the sample's
# sequence lands on bars 45-47 of the padded series instead of 25-27.
_PAD = 20
_PAD_BARS = [(120.1, 120.6, 119.6, 120.1, 100)] * _PAD


def _quotes(rows, start: date = _START) -> list[StooqDailyQuote]:
    return [
        StooqDailyQuote(
            date=start + timedelta(days=i),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(lo)),
            close=Decimal(str(c)),
            volume=v,
        )
        for i, (o, h, lo, c, v) in enumerate(rows)
    ]


def _sample() -> list[StooqDailyQuote]:
    return _quotes(SAMPLE_BARS)


def _padded() -> list[StooqDailyQuote]:
    return _quotes(_PAD_BARS + list(SAMPLE_BARS))


def _mirrored_padded() -> list[StooqDailyQuote]:
    """The padded sample flipped upside down (p -> 250 - p).

    Every strength detector has a weakness twin, so the Selling Climax becomes
    a Buying Climax, the No Supply a No Demand and the confirmation a down bar:
    the same sequence on the short side.
    """
    k = 250.0
    rows = _PAD_BARS + list(SAMPLE_BARS)
    return _quotes([(k - o, k - lo, k - h, k - c, v) for o, h, lo, c, v in rows])


def _random_walk(n: int = 700, seed: int = 917) -> list[StooqDailyQuote]:
    """The program's own verify_independent.py walk, extended. Prices stay >= 10,
    so the tick bucket never changes along it."""
    rng = random.Random(seed)
    rows = []
    close = 100.0
    for _ in range(n):
        o = close + rng.uniform(-0.5, 0.5)
        close = max(10, o + rng.uniform(-2, 2))
        h = max(o, close) + rng.uniform(0.05, 1.8)
        lo = min(o, close) - rng.uniform(0.05, 1.8)
        volume = rng.randrange(10, 900)
        rows.append((round(o, 4), round(h, 4), round(lo, 4), round(close, 4), volume))
    return _quotes(rows)


def _method():
    m = get_method("vsa4")
    assert m is not None
    return m


# ── Adapter ───────────────────────────────────────────────────────────────────


class TestAdapter:
    def test_tick_size_shrinks_with_price(self) -> None:
        assert tick_size(150.0) == 0.01
        assert tick_size(10.0) == 0.01
        assert tick_size(4.2) == 0.001
        assert tick_size(0.35) == 0.0001

    def test_config_takes_the_tick_from_the_last_close(self) -> None:
        bars, _ = to_engine_bars(_quotes([(0.5, 0.52, 0.49, 0.51, 10), (12, 12.5, 11.8, 12.2, 10)]))
        assert config_for(bars).min_tick == 0.01
        assert config_for(bars[:1]).min_tick == 0.0001
        # Overrides reach the program's config; its other defaults stay.
        cfg = config_for(bars, commission_bps=20.0)
        assert cfg.commission_bps == 20.0 and cfg.reward_risk == 3.0

    def test_repairs_what_the_program_would_reject(self) -> None:
        d = date(2026, 1, 5)
        quotes = [
            StooqDailyQuote(date=d + timedelta(days=1), open=Decimal("10"), high=Decimal("10.5"),
                            low=Decimal("9.9"), close=Decimal("10.6"), volume=5),  # close > high
            StooqDailyQuote(date=d, open=Decimal("10"), high=Decimal("10"), low=Decimal("10"),
                            close=Decimal("10"), volume=1),
            StooqDailyQuote(date=d, open=Decimal("10"), high=Decimal("11"), low=Decimal("9"),
                            close=Decimal("10.5"), volume=7),  # same date: the last one wins
            StooqDailyQuote(date=d + timedelta(days=2), open=Decimal("0"), high=Decimal("0"),
                            low=Decimal("0"), close=Decimal("0"), volume=0),  # halted, zeros
        ]
        bars, dates = to_engine_bars(quotes)
        assert dates == [d, d + timedelta(days=1)]
        assert bars[0].volume == 7 and bars[0].high == 11
        assert bars[1].high == 10.6  # widened to contain the close
        # ...and the program accepts the result instead of raising VSAError.
        assert len(analyze(bars, config_for(bars))) == 2

    def test_every_signal_has_a_display_name(self) -> None:
        assert set(SIGNAL_LABELS) == set(SIGNAL_NAMES)

    def test_reads_the_reported_sequence_state(self) -> None:
        _, dates, rows = analyze_quotes(_sample())
        # Bar 25: the Selling Climax; bar 26: No Supply after it; bar 27: confirmed.
        s25, s26 = sequence_state(rows[25]), sequence_state(rows[26])
        assert s25.long_background is not None
        assert s25.long_background.primary == "selling_climax"
        assert s25.long_background.on == dates[25]
        assert s25.long_pending is None
        assert s26.long_pending is not None
        pending = (s26.long_pending.primary, s26.long_pending.secondary)
        assert pending == ("selling_climax", "no_supply")
        assert s26.long_pending.on == dates[26]
        assert rows[27]["long_setup_confirmation"]
        assert setup_label(rows[27]) == "Selling Climax → No Supply"
        # Once confirmed, nothing is pending any more.
        assert sequence_state(rows[27]).long_pending is None


# ── The program, run exactly as shipped ──────────────────────────────────────


class TestProgramAsShipped:
    def test_simulation_reproduces_the_packaged_demo_result(self) -> None:
        # The package's demo_results were produced with the program's own
        # defaults (1 bp costs, both sides). Same inputs through the app's
        # adapter must give the same account to the last digit.
        run = simulate(_sample(), sides="both", commission_bps=1.0, slippage_bps=1.0)
        assert run is not None
        assert run.summary["final_equity"] == pytest.approx(DEMO_FINAL_EQUITY, abs=1e-9)
        assert run.summary["closed_trades"] == DEMO_CLOSED_TRADES
        assert sum(r["long_setup_confirmation"] for r in run.rows) == DEMO_LONG_SETUPS
        assert sum(r["short_setup_confirmation"] for r in run.rows) == DEMO_SHORT_SETUPS
        (trade,) = run.trades
        assert trade["entry_bar_index"] == DEMO_ENTRY_BAR
        assert trade["exit_bar_index"] == DEMO_EXIT_BAR
        assert trade["exit_reason"] == DEMO_EXIT_REASON
        assert trade["signal_name"] == DEMO_SIGNAL_NAME
        assert trade["signal_timestamp"] == run.bars[DEMO_SIGNAL_BAR].timestamp
        assert trade["entry_price"] == pytest.approx(DEMO_ENTRY_PRICE, abs=1e-9)
        assert trade["stop_loss"] == pytest.approx(DEMO_STOP_LOSS, abs=1e-9)

    def test_long_only_ignores_short_setups_but_still_counts_them(self) -> None:
        both = simulate(_mirrored_padded(), sides="both")
        long_only = simulate(_mirrored_padded(), sides="long")
        assert both is not None and long_only is not None
        assert [t["direction"] for t in both.trades] == ["short"]
        assert long_only.trades == []
        # The analysis itself is untouched by the choice.
        assert sum(r["short_setup_confirmation"] for r in long_only.rows) == 1

    def test_stock_costs_are_the_default(self) -> None:
        run = simulate(_sample())
        assert run is not None
        assert run.config.commission_bps == 20.0
        assert run.config.slippage_bps == 5.0
        assert run.sides == "long"


# ── The method ───────────────────────────────────────────────────────────────


class TestRegistration:
    def test_registered_after_v3_and_long_only(self) -> None:
        ids = method_ids()
        assert "vsa4" in ids
        # order: ... vsa3 (60) < vsa4 (65) < weinstein (70)
        assert ids.index("vsa3") < ids.index("vsa4") < ids.index("weinstein")
        m = _method()
        assert m.name == "VSA V4"
        assert m.direction == "Bullish"
        assert m.name and m.description and m.source and m.source_url
        assert m.source != get_method("vsa3").source


class TestScoreLadder:
    """The padded sample walks the long sequence one stage per bar."""

    @pytest.mark.parametrize(
        ("sample_bar", "score", "fired", "detail_part"),
        [
            (24, 35, False, "No sequence"),
            (25, 50, False, "Strength: Selling Climax"),
            (26, 65, False, "Selling Climax → No Supply, awaiting confirmation"),
            (27, 100, True, "Selling Climax → No Supply confirmed, stop 109.45"),
            (28, 85, False, "trade live"),
            (32, 85, False, "trade live"),
            # Bar 33: the demo trade's target was hit by a gap, so it is no
            # longer live; the newer Two Bar Reversal is the background.
            (33, 50, False, "Strength: Two Bar Reversal"),
        ],
    )
    def test_stage(self, sample_bar: int, score: int, fired: bool, detail_part: str) -> None:
        result = _method().evaluate(_padded()[: _PAD + sample_bar + 1])
        assert result.available
        assert result.score == score
        assert result.fired is fired
        assert detail_part in (result.detail or "")

    def test_days_since_counts_calendar_days_from_the_confirmation(self) -> None:
        result = _method().evaluate(_padded()[: _PAD + 31 + 1])
        assert result.days_since == 4

    def test_weakness_scores_below_nothing_in_play(self) -> None:
        mirrored = _mirrored_padded()
        fired = _method().evaluate(mirrored[: _PAD + 27 + 1])
        assert fired.score == 0 and fired.fired is False
        assert "Weakness: Buying Climax → No Demand confirmed" in (fired.detail or "")
        # The long entry never fired, so days_since stays "never".
        assert fired.days_since == NEVER_FIRED
        pending = _method().evaluate(mirrored[: _PAD + 26 + 1])
        assert pending.score == 10


class TestChartMarkers:
    def test_confirmed_setup_is_a_bullish_marker(self) -> None:
        quotes = _sample()
        (marker,) = _method().signals(quotes)
        assert marker.type == "Bullish"
        assert marker.date == quotes[27].date
        assert marker.label == "Selling Climax → No Supply"

    def test_short_setup_is_a_bearish_marker(self) -> None:
        quotes = _mirrored_padded()
        (marker,) = _method().signals(quotes)
        assert marker.type == "Bearish"
        assert marker.date == quotes[_PAD + 27].date
        assert marker.label == "Buying Climax → No Demand"

    def test_the_test_awaiting_confirmation_is_a_watch_marker(self) -> None:
        quotes = _padded()[: _PAD + 26 + 1]
        markers = _method().signals(quotes)
        assert [(m.type, m.date) for m in markers] == [("Watch", quotes[-1].date)]
        assert "awaiting confirmation" in markers[0].label
        # One bar later it is confirmed: the Watch gives way to the entry.
        later = _method().signals(_padded()[: _PAD + 27 + 1])
        assert [m.type for m in later] == ["Bullish"]


class TestSlicing:
    """``evaluate`` reads only its last ``_EVAL_BARS``; that must not change
    anything it reports."""

    def test_bars_past_the_warmup_match_the_whole_history(self) -> None:
        quotes = _random_walk()
        bars, _ = to_engine_bars(quotes)
        cfg = config_for(bars)
        full = analyze(bars, cfg)
        for end in range(_EVAL_BARS, len(bars) + 1, 23):
            part = analyze(bars[end - _EVAL_BARS : end], cfg)
            for j in range(_WARMUP_BARS, _EVAL_BARS):
                assert part[j] == full[end - _EVAL_BARS + j], (end, j)

    def test_evaluate_agrees_with_the_markers_on_every_prefix(self) -> None:
        quotes = _random_walk()
        long_dates = {s.date for s in _method().signals(quotes) if s.type == "Bullish"}
        assert len(long_dates) >= 5  # the walk really exercises the setup
        fired_on = set()
        for k in range(60, len(quotes) + 1):
            if _method().evaluate(quotes[:k]).fired:
                fired_on.add(quotes[k - 1].date)
        assert fired_on == long_dates

    def test_never_raises_on_short_or_broken_history(self) -> None:
        m = _method()
        assert m.evaluate([]).available is False
        assert m.evaluate(_sample()[:39]).available is False
        assert m.signals(_sample()[:10]) == []
        zeros = _quotes([(0, 0, 0, 0, 0)] * 80)
        assert m.evaluate(zeros).available is False
        assert m.signals(zeros) == []


# ── Simulation payload ───────────────────────────────────────────────────────


class TestSimulationPayload:
    def test_payload_describes_the_trade(self) -> None:
        result = build_trade_simulation("kgh", _sample(), currency="PLN")
        assert result is not None
        assert result.ticker == "KGH" and result.currency == "PLN"
        assert result.bar_count == len(SAMPLE_BARS)
        assert result.sides == "long"
        assert (result.commission_pct, result.slippage_pct) == (0.2, 0.05)
        assert result.risk_pct == 1.0 and result.reward_risk == 3.0
        assert result.closed_trades == 1 and result.open_trades == 0
        assert result.long_setups == 1 and result.short_setups == 0
        (trade,) = result.trades
        assert trade.setup == "Selling Climax → No Supply"
        assert trade.signal_date == _sample()[27].date
        assert trade.entry_date == _sample()[28].date
        # Stock-like slippage lifts the entry, and with it the 3R target, a
        # little above bar 33's open: the demo's gap fill becomes an intraday
        # one. Same bar, same outcome.
        assert trade.exit_reason == "take_profit"
        assert trade.exit_date == _sample()[DEMO_EXIT_BAR].date
        assert trade.net_r is not None and trade.net_r > 2.5
        assert trade.return_pct is not None and trade.return_pct > 0
        assert result.win_rate_pct == 100.0
        assert result.avg_r == pytest.approx(trade.net_r)
        assert result.profit_factor is None  # no losses: undefined, not infinite
        assert result.equity[-1].date == _sample()[-1].date
        assert result.buy_hold_return_pct is not None

    def test_equity_curve_is_thinned_but_keeps_the_last_session(self) -> None:
        result = build_trade_simulation("kgh", _random_walk(), currency="PLN")
        assert result is not None
        assert len(result.equity) <= 300 + 1
        assert result.equity[-1].date == _random_walk()[-1].date

    def test_no_bars_is_none(self) -> None:
        assert build_trade_simulation("kgh", [], currency="PLN") is None


# ── Endpoint ─────────────────────────────────────────────────────────────────


class _FakeClient:
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        self._quotes = quotes

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._quotes


def _recent_sample() -> list[StooqDailyQuote]:
    """The sample dated to end today, inside the endpoint's 5-year window."""
    return _quotes(SAMPLE_BARS, start=date.today() - timedelta(days=len(SAMPLE_BARS) - 1))


@pytest.fixture(autouse=True)
def _isolated():
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()
    app.dependency_overrides.clear()


class TestTradeSimulationEndpoint:
    def test_returns_the_simulation(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeClient(_recent_sample())
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/trade-simulation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "KGH"
        assert body["methodId"] == "vsa4"
        assert body["currency"] == "PLN"
        assert body["sides"] == "long"
        assert body["closedTrades"] == 1
        assert body["trades"][0]["setup"] == "Selling Climax → No Supply"
        assert body["trades"][0]["exitReason"] == "take_profit"  # stock costs, see above
        assert "closed_trades" not in body  # camelCase for the frontend

    def test_parameters_reach_the_program(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeClient(_recent_sample())
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/kgh/trade-simulation?sides=both&commissionBps=1&slippageBps=1"
            ).json()
        assert body["sides"] == "both"
        assert body["commissionPct"] == 0.01
        assert body["finalEquity"] == pytest.approx(DEMO_FINAL_EQUITY, abs=1e-6)

    @pytest.mark.parametrize(
        "query", ["sides=short", "commissionBps=-1", "slippageBps=500"]
    )
    def test_rejects_bad_parameters(self, query: str) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeClient(_recent_sample())
        with TestClient(app) as client:
            resp = client.get(f"/api/stocks/kgh/trade-simulation?{query}")
        assert resp.status_code == 422

    def test_no_history_is_404(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeClient([])
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/trade-simulation")
        assert resp.status_code == 404

    def test_rejects_invalid_ticker(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/" + "a" * 21 + "/trade-simulation")
        assert resp.status_code == 400

    def test_method_is_in_the_catalogue(self) -> None:
        with TestClient(app) as client:
            ids = [m["id"] for m in client.get("/api/stocks/methods").json()]
        assert "vsa4" in ids
