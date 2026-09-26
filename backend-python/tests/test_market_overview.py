"""Tests for the market overview: breadth tally, rating movers and the endpoint."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.routers.stocks as stocks_router
from app.dependencies import get_stooq_client, history_cache, ranking_cache
from app.main import app
from app.models import StockRankingItem
from app.services.market_overview import build_market_overview, compute_breadth, top_movers
from tests.test_api import _FakeStooqClient, _rich_quotes


def _row(
    ticker: str,
    *,
    verdict: str = "Hold",
    rating: int = 50,
    change: int = 0,
    price_change: float = 0.0,
    new_high: bool = False,
    new_low: bool = False,
    session: date | None = date(2026, 9, 24),
    market: str = "gpw",
) -> StockRankingItem:
    return StockRankingItem(
        ticker=ticker,
        name=f"{ticker.upper()} SA",
        market=market,
        last_session=session,
        last_price=10.0,
        price_change_pct=price_change,
        current_rating=rating,
        rating_change=change,
        last_signal=verdict,
        days_since_signal=1,
        sparkline=[10.0],
        volume=1000,
        is_new_52w_high=new_high,
        is_new_52w_low=new_low,
    )


@pytest.fixture(autouse=True)
def _clean():
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()


class TestBreadth:
    def test_empty_universe_is_all_zero(self) -> None:
        breadth = compute_breadth([])
        assert breadth.total == 0
        assert breadth.average_rating is None
        assert breadth.bullish_pct == 0.0

    def test_verdict_split_and_shares(self) -> None:
        rows = [
            _row("a", verdict="Strong Buy", rating=90),
            _row("b", verdict="Buy", rating=70),
            _row("c", verdict="Buy", rating=68),
            _row("d", verdict="Hold", rating=50),
            _row("e", verdict="Sell", rating=30),
            _row("f", verdict="Strong Sell", rating=10),
            _row("g", verdict="Hold", rating=50),
            _row("h", verdict="Hold", rating=50),
        ]
        b = compute_breadth(rows)
        assert (b.strong_buy, b.buy, b.hold, b.sell, b.strong_sell) == (1, 2, 3, 1, 1)
        assert b.total == 8
        # The five buckets partition the universe.
        assert b.strong_buy + b.buy + b.hold + b.sell + b.strong_sell == b.total
        assert b.bullish_pct == 37.5
        assert b.bearish_pct == 25.0
        assert b.average_rating == pytest.approx(52.2, abs=0.05)

    def test_price_breadth_and_rating_momentum(self) -> None:
        rows = [
            _row("a", price_change=1.2, change=5),
            _row("b", price_change=0.4, change=-3),
            _row("c", price_change=-2.0, change=0),
            _row("d", price_change=0.0, change=2),
        ]
        b = compute_breadth(rows)
        assert (b.advancers, b.decliners, b.unchanged) == (2, 1, 1)
        assert (b.rating_up, b.rating_down) == (2, 1)

    def test_counts_fresh_52_week_extremes(self) -> None:
        rows = [
            _row("a", new_high=True),
            _row("b", new_high=True),
            _row("c", new_low=True),
            _row("d"),
        ]
        b = compute_breadth(rows)
        assert (b.new_52w_highs, b.new_52w_lows) == (2, 1)

    def test_unknown_verdict_counts_in_total_but_no_bucket(self) -> None:
        b = compute_breadth([_row("a", verdict="Buy"), _row("b", verdict="???")])
        assert b.total == 2
        assert b.buy == 1
        assert b.strong_buy + b.buy + b.hold + b.sell + b.strong_sell == 1


class TestMovers:
    def test_ordered_by_size_of_move_and_only_real_moves(self) -> None:
        rows = [
            _row("a", change=4, rating=60),
            _row("b", change=12, rating=80),
            _row("c", change=0, rating=99),
            _row("d", change=-9, rating=20),
            _row("e", change=-2, rating=40),
            _row("f", change=7, rating=55),
        ]
        up, down = top_movers(rows, limit=5)
        assert [m.ticker for m in up] == ["b", "f", "a"]
        assert [m.ticker for m in down] == ["d", "e"]

    def test_limit_applies_to_each_list(self) -> None:
        rows = [_row(f"u{i}", change=i + 1) for i in range(8)] + [
            _row(f"d{i}", change=-(i + 1)) for i in range(8)
        ]
        up, down = top_movers(rows, limit=3)
        assert [m.rating_change for m in up] == [8, 7, 6]
        assert [m.rating_change for m in down] == [-8, -7, -6]

    def test_previous_rating_is_rating_before_the_move(self) -> None:
        up, down = top_movers([_row("a", rating=72, change=9), _row("b", rating=18, change=-6)])
        assert (up[0].previous_rating, up[0].current_rating) == (63, 72)
        assert (down[0].previous_rating, down[0].current_rating) == (24, 18)

    def test_ties_do_not_depend_on_input_order(self) -> None:
        rows = [
            _row("zzz", change=5, rating=70),
            _row("aaa", change=5, rating=70),
            _row("mid", change=5, rating=85),
        ]
        forward = [m.ticker for m in top_movers(rows)[0]]
        backward = [m.ticker for m in top_movers(list(reversed(rows)))[0]]
        # Same move → the better-rated stock first, then by ticker.
        assert forward == backward == ["mid", "aaa", "zzz"]

    def test_nothing_moved_gives_empty_lists(self) -> None:
        up, down = top_movers([_row("a"), _row("b")])
        assert up == [] and down == []


class TestBuildOverview:
    def test_as_of_is_the_newest_session(self) -> None:
        rows = [
            _row("a", session=date(2026, 9, 23)),
            _row("b", session=date(2026, 9, 24)),
            _row("c", session=None),
        ]
        overview = build_market_overview(rows, market="all")
        assert overview.as_of == date(2026, 9, 24)
        assert overview.market == "all"

    def test_empty_input(self) -> None:
        overview = build_market_overview([], market="gpw")
        assert overview.as_of is None
        assert overview.breadth.total == 0
        assert overview.movers_up == [] and overview.movers_down == []


class TestEndpoint:
    def test_serialises_camel_case_with_all_sections(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_rich_quotes()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/market-overview")
            ranked = client.get("/api/stocks/ranking?pageSize=500").json()
        assert resp.status_code == 200
        body = resp.json()
        assert body["market"] == "gpw"
        assert set(body) == {"asOf", "market", "breadth", "moversUp", "moversDown"}
        for key in (
            "total", "strongBuy", "buy", "hold", "sell", "strongSell", "bullishPct",
            "bearishPct", "averageRating", "advancers", "decliners", "unchanged",
            "ratingUp", "ratingDown", "new52wHighs", "new52wLows",
        ):
            assert key in body["breadth"], key
        # The overview describes exactly the list the Dashboard shows.
        assert body["breadth"]["total"] == len(ranked)

    def test_limit_is_bounded(self) -> None:
        with TestClient(app) as client:
            assert client.get("/api/stocks/market-overview?limit=0").status_code == 422
            assert client.get("/api/stocks/market-overview?limit=26").status_code == 422

    def test_unknown_market_is_a_400(self) -> None:
        with TestClient(app) as client:
            resp = client.get("/api/stocks/market-overview?market=mars")
        assert resp.status_code == 400

    def test_reads_the_same_cached_rows_as_the_ranking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rows = [
            _row("a", verdict="Strong Buy", rating=91, change=14),
            _row("b", verdict="Sell", rating=25, change=-11),
        ]

        async def fake_ranking(scope, *args, **kwargs):
            return rows

        monkeypatch.setattr(stocks_router, "_market_ranking", fake_ranking)
        with TestClient(app) as client:
            body = client.get("/api/stocks/market-overview?limit=1").json()
        assert body["breadth"]["strongBuy"] == 1 and body["breadth"]["sell"] == 1
        assert [m["ticker"] for m in body["moversUp"]] == ["a"]
        assert [m["ticker"] for m in body["moversDown"]] == ["b"]
        assert body["moversUp"][0]["previousRating"] == 77
