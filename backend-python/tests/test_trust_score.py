"""Tests for the VSA trust-score engine and its endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.analysis.trust_score import (
    ENGINE_VERSION,
    HORIZON_SESSIONS,
    compute_trust_score,
)
from app.analysis.vsa import SignalName, SignalType, VsaSignal
from app.dependencies import get_stooq_client, history_cache, ranking_cache
from app.main import app
from app.models import StooqDailyQuote

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(d: date, close: float, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close - 1)),
        high=Decimal(str(close + 2)),
        low=Decimal(str(close - 2)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(closes: list[float]) -> list[StooqDailyQuote]:
    start = date(2026, 1, 2)
    return [_quote(start + timedelta(days=i), c) for i, c in enumerate(closes)]


def _signal(
    quotes: list[StooqDailyQuote],
    idx: int,
    name: SignalName = SignalName.SOS,
    type_: SignalType = SignalType.BULLISH,
) -> VsaSignal:
    return VsaSignal(date=quotes[idx].date, signal_name=name, type=type_, strength=1.0)


class _FakeStooqClient:
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        self._quotes = quotes

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._quotes


# ── Engine unit tests ─────────────────────────────────────────────────────────


class TestComputeTrustScore:
    def test_good_buy_entries_score_above_neutral(self) -> None:
        # Mostly flat with two rallies, each starting right on a Strong Buy
        # signal — the signals clearly beat the flat baseline.
        closes = (
            [100.0] * 20
            + [100.0 + i * 1.0 for i in range(1, 13)]  # rally 1 (bars 20..31)
            + [112.0] * 20
            + [112.0 + i * 1.0 for i in range(1, 13)]  # rally 2 (bars 52..63)
            + [124.0] * 20
        )
        quotes = _series(closes)
        signals = [_signal(quotes, 19), _signal(quotes, 51)]

        result = compute_trust_score(
            ticker="kgh", name="KGHM", quotes=quotes, signals=signals
        )

        assert result.engine == ENGINE_VERSION
        assert result.as_of == quotes[-1].date
        assert result.evaluated_count == 2
        assert result.good_count == 2
        assert result.buy_evaluated == 2 and result.buy_good == 2
        assert result.score is not None and result.score > 55
        assert all(e.good_entry for e in result.events)

    def test_bad_buy_entries_score_below_neutral(self) -> None:
        # Strong Buy signals fire right before slumps in an otherwise flat series.
        closes = (
            [100.0] * 20
            + [100.0 - i * 1.0 for i in range(1, 13)]  # slump (bars 20..31)
            + [88.0] * 20
            + [88.0 - i * 1.0 for i in range(1, 13)]  # slump 2 (bars 52..63)
            + [76.0] * 20
        )
        quotes = _series(closes)
        signals = [_signal(quotes, 19), _signal(quotes, 51)]

        result = compute_trust_score(
            ticker="kgh", name=None, quotes=quotes, signals=signals
        )

        assert result.evaluated_count == 2
        assert result.good_count == 0
        assert result.score is not None and result.score < 45
        assert result.grade == "low"

    def test_strong_sell_before_fall_is_good_entry(self) -> None:
        closes = [100.0] * 20 + [100.0 - i * 1.5 for i in range(1, 13)] + [82.0] * 10
        quotes = _series(closes)
        signals = [
            _signal(quotes, 19, name=SignalName.SOW, type_=SignalType.BEARISH)
        ]

        result = compute_trust_score(
            ticker="pkn", name=None, quotes=quotes, signals=signals
        )

        assert result.evaluated_count == 1
        assert result.sell_evaluated == 1 and result.sell_good == 1
        assert result.events[0].verdict == "Strong Sell"
        assert result.events[0].good_entry is True

    def test_non_strong_verdicts_are_ignored(self) -> None:
        # Successful Test → "Buy", No Demand → "Sell": neither is back-tested.
        closes = [100.0 + i * 0.2 for i in range(60)]
        quotes = _series(closes)
        signals = [
            _signal(quotes, 20, name=SignalName.SUCCESSFUL_TEST),
            _signal(quotes, 30, name=SignalName.NO_DEMAND, type_=SignalType.BEARISH),
        ]

        result = compute_trust_score(
            ticker="pko", name=None, quotes=quotes, signals=signals
        )

        assert result.evaluated_count == 0
        assert result.score is None
        assert result.grade == "insufficient"
        assert "no track record" in result.summary.casefold()

    def test_fresh_signal_not_evaluated(self) -> None:
        closes = [100.0] * 40
        quotes = _series(closes)
        # Fires within the forward horizon of the last bar — too fresh to judge.
        signals = [_signal(quotes, len(quotes) - HORIZON_SESSIONS + 1)]

        result = compute_trust_score(
            ticker="cdr", name=None, quotes=quotes, signals=signals
        )

        assert result.evaluated_count == 0
        assert result.fresh_count == 1
        assert result.score is None
        assert result.grade == "insufficient"

    def test_single_lucky_signal_stays_moderate(self) -> None:
        # Shrinkage: one good signal must not produce an extreme score.
        closes = [100.0] * 20 + [100.0 + i * 2.0 for i in range(1, 13)] + [124.0] * 10
        quotes = _series(closes)
        signals = [_signal(quotes, 19)]

        result = compute_trust_score(
            ticker="kgh", name=None, quotes=quotes, signals=signals
        )

        assert result.evaluated_count == 1
        assert result.good_count == 1
        assert result.score is not None and 50 < result.score <= 70

    def test_deterministic(self) -> None:
        closes = [100.0 + (i % 7) for i in range(80)]
        quotes = _series(closes)
        signals = [_signal(quotes, 25), _signal(quotes, 50)]
        kwargs = dict(ticker="cdr", name="CD Projekt", quotes=quotes, signals=signals)

        assert compute_trust_score(**kwargs) == compute_trust_score(**kwargs)


# ── Endpoint tests ────────────────────────────────────────────────────────────


class TestTrustScoreEndpoint:
    def setup_method(self) -> None:
        history_cache.clear()
        ranking_cache.clear()
        app.dependency_overrides.clear()

    def teardown_method(self) -> None:
        history_cache.clear()
        ranking_cache.clear()
        app.dependency_overrides.clear()

    def test_returns_trust_score_payload(self) -> None:
        quotes = _series([100.0 + i * 0.3 for i in range(60)])
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(quotes)

        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/trust-score")

        assert resp.status_code == 200
        body = resp.json()
        for field in (
            "ticker", "asOf", "score", "grade", "horizonSessions",
            "evaluatedCount", "goodCount", "freshCount",
            "buyEvaluated", "buyGood", "sellEvaluated", "sellGood",
            "baselineReturnPct", "avgExcessReturnPct",
            "summary", "events", "engine",
        ):
            assert field in body, f"Missing field: {field}"
        assert body["ticker"] == "KGH"
        assert body["engine"] == ENGINE_VERSION
        assert body["horizonSessions"] == HORIZON_SESSIONS

    def test_invalid_ticker_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/bad!ticker/trust-score")
        assert resp.status_code == 400

    def test_no_history_is_404(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient([])
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/trust-score")
        assert resp.status_code == 404

    def test_respects_settings_parameter(self) -> None:
        quotes = _series([100.0 + i * 0.3 for i in range(60)])
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(quotes)

        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/kgh/trust-score",
                params={"settings": '{"spring": {"enabled": false}}'},
            )
        assert resp.status_code == 200

    def test_malformed_settings_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/kgh/trust-score", params={"settings": "not json"}
            )
        assert resp.status_code == 400
