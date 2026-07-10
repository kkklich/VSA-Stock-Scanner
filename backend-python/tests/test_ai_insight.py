"""Tests for the built-in AI insight engine and its endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.analysis.ai_insight import ENGINE_VERSION, analyze_stock
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


def _series(closes: list[float], volumes: list[int] | None = None) -> list[StooqDailyQuote]:
    start = date(2026, 1, 2)
    vols = volumes or [200_000] * len(closes)
    return [
        _quote(start + timedelta(days=i), c, v)
        for i, (c, v) in enumerate(zip(closes, vols, strict=True))
    ]


class _FakeStooqClient:
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        self._quotes = quotes

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._quotes


# ── Engine unit tests ─────────────────────────────────────────────────────────


class TestAnalyzeStock:
    def test_confirms_bullish_signal_with_follow_through(self) -> None:
        # Flat, then a signal, then a clear rally: the signal must be confirmed.
        closes = [100.0] * 30 + [100.0 + i * 1.5 for i in range(1, 11)]
        quotes = _series(closes)
        signal = VsaSignal(
            date=quotes[29].date,
            signal_name=SignalName.SPRING,
            type=SignalType.BULLISH,
            strength=0.9,
        )

        result = analyze_stock(
            ticker="kgh", name="KGHM", quotes=quotes, signals=[signal], rating=70
        )

        assert result.engine == ENGINE_VERSION
        assert result.as_of == quotes[-1].date
        assert result.signal_assessments[0].agreement == "confirm"
        assert result.verdict in ("Buy", "Strong Buy")

    def test_rejects_bullish_signal_when_price_falls(self) -> None:
        closes = [100.0] * 30 + [100.0 - i * 1.5 for i in range(1, 11)]
        quotes = _series(closes)
        signal = VsaSignal(
            date=quotes[29].date,
            signal_name=SignalName.SOS,
            type=SignalType.BULLISH,
            strength=1.0,
        )

        result = analyze_stock(
            ticker="kgh", name=None, quotes=quotes, signals=[signal], rating=50
        )

        assert result.signal_assessments[0].agreement == "reject"

    def test_fresh_signal_is_uncertain(self) -> None:
        closes = [100.0] * 30
        quotes = _series(closes)
        signal = VsaSignal(
            date=quotes[-1].date,
            signal_name=SignalName.NO_DEMAND,
            type=SignalType.BEARISH,
            strength=0.6,
        )

        result = analyze_stock(
            ticker="pkn", name=None, quotes=quotes, signals=[signal], rating=50
        )

        assert result.signal_assessments[0].agreement == "uncertain"
        assert "too fresh" in result.signal_assessments[0].comment.casefold()

    def test_no_signals_still_produces_analysis(self) -> None:
        quotes = _series([100.0 + i * 0.5 for i in range(40)])

        result = analyze_stock(
            ticker="pko", name="PKO BP", quotes=quotes, signals=[], rating=50
        )

        assert result.signal_assessments == []
        assert result.verdict in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")
        assert 0 <= result.confidence <= 100
        assert result.summary
        assert result.key_observations

    def test_deterministic(self) -> None:
        quotes = _series([100.0 + (i % 7) for i in range(60)])
        signal = VsaSignal(
            date=quotes[40].date,
            signal_name=SignalName.UPTHRUST,
            type=SignalType.BEARISH,
            strength=0.85,
        )
        kwargs = dict(
            ticker="cdr", name="CD Projekt", quotes=quotes, signals=[signal], rating=44
        )

        assert analyze_stock(**kwargs) == analyze_stock(**kwargs)


# ── Endpoint tests ────────────────────────────────────────────────────────────


class TestAiAnalysisEndpoint:
    def setup_method(self) -> None:
        history_cache.clear()
        ranking_cache.clear()
        app.dependency_overrides.clear()

    def teardown_method(self) -> None:
        history_cache.clear()
        ranking_cache.clear()
        app.dependency_overrides.clear()

    def test_returns_analysis_payload(self) -> None:
        quotes = _series([100.0 + i * 0.3 for i in range(60)])
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(quotes)

        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/ai-analysis")

        assert resp.status_code == 200
        body = resp.json()
        for field in (
            "ticker", "asOf", "verdict", "confidence",
            "summary", "signalAssessments", "keyObservations", "engine",
        ):
            assert field in body, f"Missing field: {field}"
        assert body["ticker"] == "KGH"
        assert body["engine"] == ENGINE_VERSION

    def test_invalid_ticker_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/bad!ticker/ai-analysis")
        assert resp.status_code == 400

    def test_no_history_is_404(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient([])
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/ai-analysis")
        assert resp.status_code == 404

    def test_respects_settings_parameter(self) -> None:
        quotes = _series([100.0 + i * 0.3 for i in range(60)])
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(quotes)

        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/kgh/ai-analysis",
                params={"settings": '{"spring": {"enabled": false}}'},
            )
        assert resp.status_code == 200

    def test_malformed_settings_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/kgh/ai-analysis", params={"settings": "not json"}
            )
        assert resp.status_code == 400
