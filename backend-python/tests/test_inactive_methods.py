"""Inactive methods must neither run nor leak into live application results."""
import asyncio
from datetime import date, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.analysis import runtime_vsa, vsa
from app.analysis.analytics_summary import build_analytics_summary
from app.analysis.methods import all_methods, get_method, method_ids
from app.analysis.methods.vsa3 import Vsa3
from app.analysis.methods.vsa_glinicki import VsaGlinicki
from app.analysis.methods.vsa_method import VsaMethod
from app.analysis.weekly import compute_weekly_view
from app.dependencies import get_stooq_client, history_cache, ranking_cache
from app.main import app
from app.models import GpwCompany, MethodResultModel, StooqDailyQuote
from app.routers.stocks import _query_ranking, _with_combined_score
from app.services.cache import TTLCache
from app.services.ranking_service import compute_ranking
from app.services.refresh_service import RefreshService, build_rating_points

ACTIVE = {"vsa4", "minervini", "breakout", "weinstein", "pocket_pivot"}
INACTIVE = {"vsa", "vsa3", "glinicki"}


def quotes():
    return [StooqDailyQuote(
        date=date.today()-timedelta(days=329-i), open=100+i/10,
        high=102+i/10, low=98+i/10, close=101+i/10, volume=1_000_000,
    ) for i in range(330)]


class Client:
    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return quotes()


def test_only_active_methods_are_advertised_and_resolvable():
    assert set(method_ids()) >= ACTIVE
    assert {m.id for m in all_methods()} >= ACTIVE
    assert not INACTIVE.intersection(method_ids())
    assert all(get_method(m) is None for m in INACTIVE)
    assert get_method("vsa4") is not None


def test_legacy_runtime_short_circuits_before_detector_weekly_and_snapshots(monkeypatch):
    detector = Mock(side_effect=AssertionError("Classic detector must not run"))
    monkeypatch.setattr(vsa, "detect_signals", detector)
    assert runtime_vsa.detect_signals(quotes()) == []
    assert not compute_weekly_view(quotes()).available
    assert build_rating_points(quotes()) == []
    detector.assert_not_called()


def test_ranking_and_consensus_never_evaluate_archived_methods(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Archived method executed"))
    for cls in (Vsa3, VsaGlinicki, VsaMethod):
        monkeypatch.setattr(cls, "evaluate", forbidden)
        monkeypatch.setattr(cls, "signals", forbidden)
    monkeypatch.setattr(vsa, "detect_signals", forbidden)
    monkeypatch.setattr("app.analysis.analytics_summary.analyze_stock", forbidden)
    monkeypatch.setattr("app.analysis.analytics_summary.compute_trust_score", forbidden)
    monkeypatch.setattr("app.services.ranking_service.analyze_stock", forbidden)
    rows = asyncio.run(compute_ranking(
        [GpwCompany(ticker="test", name="Test")], Client(), TTLCache(), 60,
    ))
    assert len(rows) == 1
    assert set(rows[0].method_results) >= ACTIVE
    assert not INACTIVE.intersection(rows[0].method_results)
    assert rows[0].weekly_rating is None
    assert rows[0].ai_confidence == 0
    # A saved classic-only filter must not empty an otherwise valid ranking.
    assert len(_query_ranking(
        rows, q=None, min_rating=95, signal="Strong Buy", tickers=None,
        sort=[("current_rating", True)], weekly_confirms=True,
    )) == 1
    stale = rows[0].model_copy(update={"method_results": {
        "vsa": MethodResultModel(method_id="vsa", score=100),
        "vsa4": MethodResultModel(method_id="vsa4", score=35),
    }})
    assert _with_combined_score(stale, None).combined_score == 35
    repo = Mock()
    refresh = RefreshService([], Client(), TTLCache(), TTLCache(), repo=repo)
    assert asyncio.run(refresh._snapshot_ratings(rows, date.today())) == 0
    repo.get_rating_history.assert_not_called()
    repo.upsert_rating_snapshots.assert_not_called()
    summary = build_analytics_summary(ticker="test", name="Test", quotes=quotes(), signals=[])
    assert {s.key for s in summary.sources} >= ACTIVE
    assert not (INACTIVE | {"aiInsight", "trustScore"}).intersection(s.key for s in summary.sources)
    forbidden.assert_not_called()


def test_archived_http_paths_return_404_without_fetching_and_v4_chart_survives():
    fetch = Mock(side_effect=AssertionError("Archived endpoints must not fetch"))
    app.dependency_overrides[get_stooq_client] = lambda: fetch
    history_cache.clear()
    ranking_cache.clear()
    try:
        with TestClient(app) as client:
            catalogue = {m["id"] for m in client.get("/api/stocks/methods").json()}
            assert catalogue >= ACTIVE
            assert not INACTIVE.intersection(catalogue)
            paths = [f"/api/stocks/methods/{m}/backtest" for m in INACTIVE]
            paths += ["/api/stocks/scanner/stats"]
            paths += [f"/api/stocks/kgh/{suffix}" for suffix in
                      ("rating-history", "ai-analysis", "trust-score")]
            for path in paths:
                assert client.get(path).status_code == 404, path
            fetch.get_daily_history.assert_not_called()
            app.dependency_overrides[get_stooq_client] = lambda: Client()
            response = client.get("/api/stocks/kgh/signals")
            assert response.status_code == 200
            payload = response.json()
            assert payload["vsaSignals"] == []
            assert {m["methodId"] for m in payload["methodSignals"]} == catalogue
    finally:
        app.dependency_overrides.pop(get_stooq_client, None)
        history_cache.clear()
        ranking_cache.clear()
