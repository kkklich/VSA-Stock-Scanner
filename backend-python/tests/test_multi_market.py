"""Multi-market plumbing beyond the registry itself.

Pinned here:

* the company service loads one file per market, skips bad entries, and only
  reveals companies from markets this deployment has switched on;
* the stock endpoints accept a suffixed ticker for a tracked company on an
  enabled market, and refuse everything else — a visitor must not be able to
  make the server download (and store) an arbitrary symbol;
* the scans judge every stock against the złoty floors in its own currency.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import (
    get_gpw_company_service,
    get_stooq_client,
    history_cache,
    ranking_cache,
)
from app.main import app
from app.models import GpwCompany, StooqDailyQuote
from app.routers.stocks import _backfill_attempted
from app.services.cache import TTLCache
from app.services.gpw_company_service import GpwCompanyService
from app.services.heatmap_service import compute_heatmap
from app.services.ranking_service import compute_ranking
from app.services.refresh_service import build_rating_points
from app.services.volume_surge_service import compute_volume_surge

_DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"

_APPLE = {
    "ticker": "aapl.us",
    "name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "country": "United States",
    "exchange": "NASDAQ",
    "currency": "USD",
    "marketCap": 4_857_818_775_552,
    "employees": 150_000,
    "website": "https://www.apple.com",
    "description": "Designs phones.",
    "indices": ["ndx", "sp500"],
}


def _write_market(markets_dir: Path, market_id: str, companies: list) -> None:
    markets_dir.mkdir(parents=True, exist_ok=True)
    payload = {"market": market_id, "generatedAt": "2026-09-16", "companies": companies}
    (markets_dir / f"{market_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _service(markets_dir: Path) -> GpwCompanyService:
    """The real GPW seed files plus a scratch directory of market files."""
    return GpwCompanyService(
        companies_file=_DATA_DIR / "gpw-companies.json",
        details_file=_DATA_DIR / "company-details.json",
        markets_dir=markets_dir,
    )


@pytest.fixture
def us_market(tmp_path: Path) -> GpwCompanyService:
    _write_market(tmp_path, "us", [_APPLE])
    return _service(tmp_path)


# ── Company service ───────────────────────────────────────────────────────────


class TestCompanyService:
    def test_the_default_list_is_still_the_gpw(self, us_market: GpwCompanyService) -> None:
        companies = us_market.get_companies()
        assert len(companies) == len(GpwCompanyService().get_companies())
        assert {c.market for c in companies} == {"gpw"}
        kgh = next(c for c in companies if c.ticker == "kgh")
        assert (kgh.exchange, kgh.currency) == ("GPW", "PLN")

    def test_a_market_file_is_loaded_with_every_field(
        self, us_market: GpwCompanyService
    ) -> None:
        [apple] = us_market.get_companies("us")
        assert apple.ticker == "aapl.us"
        assert apple.market == "us"
        assert apple.exchange == "NASDAQ"
        assert apple.currency == "USD"
        assert apple.indices == ("ndx", "sp500")
        assert apple.market_cap == 4_857_818_775_552
        assert apple.description == "Designs phones."

    def test_bad_entries_are_skipped_one_by_one(self, tmp_path: Path) -> None:
        _write_market(
            tmp_path,
            "us",
            [
                _APPLE,
                {**_APPLE, "ticker": "AAPL.US"},  # duplicate once normalised
                {**_APPLE, "ticker": "sap.de"},  # belongs to another market
                {**_APPLE, "ticker": "!!!"},  # not a ticker
                {**_APPLE, "ticker": "msft.us", "employees": "many"},  # malformed
                {**_APPLE, "ticker": "nvda.us", "name": "NVIDIA"},
            ],
        )
        tickers = [c.ticker for c in _service(tmp_path).get_companies("us")]
        assert tickers == ["aapl.us", "nvda.us"]

    def test_a_missing_file_is_an_empty_market(self, tmp_path: Path) -> None:
        assert _service(tmp_path).get_companies("de") == []

    def test_a_broken_file_costs_that_market_only(self, tmp_path: Path) -> None:
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "uk.json").write_text("{ not json", encoding="utf-8")
        service = _service(tmp_path)
        assert service.get_companies("uk") == []
        assert len(service.get_companies()) > 0

    def test_an_unknown_market_has_no_companies(self, us_market: GpwCompanyService) -> None:
        assert us_market.get_companies("xx") == []

    def test_a_switched_off_market_stays_invisible(
        self, us_market: GpwCompanyService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "markets", "gpw")
        assert us_market.find("AAPL.US") is None
        assert [c.market for c in us_market.enabled_companies()].count("us") == 0

    def test_a_switched_on_market_is_found(
        self, us_market: GpwCompanyService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "markets", "us")
        apple = us_market.find(" AAPL.US ")
        assert apple is not None and apple.name == "Apple Inc."
        assert [c.market for c in us_market.enabled_companies()].count("us") == 1

    def test_gpw_lookups_are_unchanged(self, us_market: GpwCompanyService) -> None:
        assert us_market.find("KGH").ticker == "kgh"
        # Yahoo's spelling of a GPW ticker is the same company.
        assert us_market.find("kgh.wa").ticker == "kgh"
        assert us_market.find("nosuch") is None
        assert us_market.find("") is None


# ── Endpoints: which tickers are served ───────────────────────────────────────


def _bars(n: int = 40, close: float = 100.0, volume: int = 200_000) -> list[StooqDailyQuote]:
    start = date.today() - timedelta(days=n - 1)
    return [
        StooqDailyQuote(
            date=start + timedelta(days=i),
            open=Decimal(str(close)),
            high=Decimal(str(close + 1)),
            low=Decimal(str(close - 1)),
            close=Decimal(str(close)),
            volume=volume,
        )
        for i in range(n)
    ]


class _RecordingClient:
    """Serves canned bars and remembers which tickers were asked for."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.asked.append(ticker)
        return _bars()


@pytest.fixture
def api(us_market: GpwCompanyService):
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()
    client = _RecordingClient()
    app.dependency_overrides[get_gpw_company_service] = lambda: us_market
    app.dependency_overrides[get_stooq_client] = lambda: client
    with TestClient(app) as http:
        yield http, client
    app.dependency_overrides.clear()
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()


class TestEndpointTickers:
    def test_a_tracked_stock_on_an_enabled_market_is_served(
        self, api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        http, client = api
        monkeypatch.setattr(settings, "markets", "us")
        resp = http.get("/api/stocks/AAPL.US/signals")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "AAPL.US"
        assert body["name"] == "Apple Inc."
        assert client.asked == ["aapl.us"]

    def test_a_switched_off_market_answers_404_without_a_download(
        self, api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        http, client = api
        monkeypatch.setattr(settings, "markets", "gpw")
        resp = http.get("/api/stocks/aapl.us/signals")
        assert resp.status_code == 404
        assert client.asked == []

    def test_an_untracked_foreign_symbol_answers_404_without_a_download(
        self, api, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # e.g. a crypto pair or any other symbol Yahoo would happily serve.
        http, client = api
        monkeypatch.setattr(settings, "markets", "all")
        for path in (
            "/api/stocks/btc-usd.us/history",
            "/api/stocks/msft.us/ai-analysis",
            "/api/stocks/sap.de/volume",
        ):
            assert http.get(path).status_code == 404, path
        assert client.asked == []

    @pytest.mark.parametrize(
        "path",
        [
            "/api/stocks/foo.xx/signals",
            "/api/stocks/abc-def/history",
            "/api/stocks/kgh./trust-score",
        ],
    )
    def test_malformed_tickers_answer_400(self, api, path: str) -> None:
        http, client = api
        assert http.get(path).status_code == 400
        assert client.asked == []

    def test_gpw_tickers_behave_as_before(self, api) -> None:
        http, client = api
        resp = http.get("/api/stocks/KGH/history")
        assert resp.status_code == 200
        assert resp.json()["ticker"] == "KGH"
        # Yahoo's own spelling resolves to the same stock.
        resp = http.get("/api/stocks/kgh.wa/signals")
        assert resp.status_code == 200
        assert resp.json()["ticker"] == "KGH"
        assert set(client.asked) == {"kgh"}


# ── Floors in the scans ───────────────────────────────────────────────────────


class _PerTicker:
    def __init__(self, by_ticker: dict[str, list[StooqDailyQuote]]) -> None:
        self._by_ticker = by_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._by_ticker.get(ticker, [])


def _company(
    ticker: str, market_cap: int | None = None, currency: str | None = None
) -> GpwCompany:
    return GpwCompany(
        ticker=ticker, name=ticker.upper(), market_cap=market_cap, currency=currency
    )


def _rank(companies: list[GpwCompany], bars: dict[str, list[StooqDailyQuote]]) -> set[str]:
    rows = asyncio.run(
        compute_ranking(
            companies=companies,
            stooq=_PerTicker(bars),
            history_cache=TTLCache(),
            history_cache_ttl=60,
        )
    )
    return {r.ticker for r in rows}


class TestFloorsFollowTheCurrency:
    def test_thirty_thousand_dollars_a_day_is_liquid(self) -> None:
        # Median turnover 30,000 in the stock's currency: ~114k PLN for a US
        # stock (ranked), 30k PLN for a GPW one (too thin).
        thin = _bars(close=10.0, volume=3_000)
        ranked = _rank(
            [_company("aaa.us"), _company("aaa")],
            {"aaa.us": thin, "aaa": thin},
        )
        assert ranked == {"AAA.US"}

    def test_pence_are_divided_before_judging(self) -> None:
        # 500p × 3,000 shares = £15,000 ≈ 76k PLN — too thin despite the
        # raw 1,500,000; 5,000 shares = £25,000 ≈ 128k PLN is enough.
        ranked = _rank(
            [_company("thin.l"), _company("fine.l")],
            {
                "thin.l": _bars(close=500.0, volume=3_000),
                "fine.l": _bars(close=500.0, volume=5_000),
            },
        )
        assert ranked == {"FINE.L"}

    def test_a_london_line_quoted_in_dollars_is_judged_in_dollars(self) -> None:
        # Compass Group trades in USD on the LSE. 30 × 1,000 = 30,000 USD
        # (~114k PLN) is liquid; read as pence it would be £300 and dropped.
        bars = _bars(close=30.0, volume=1_000)
        ranked = _rank(
            [_company("cpg.l", currency="USD"), _company("pence.l")],
            {"cpg.l": bars, "pence.l": bars},
        )
        assert ranked == {"CPG.L"}

    def test_market_caps_are_converted_too(self) -> None:
        # 30M in the market's currency: ~114M PLN in dollars, 30M PLN in złoty.
        bars = _bars()
        ranked = _rank(
            [_company("big.us", 30_000_000), _company("small", 30_000_000)],
            {"big.us": bars, "small": bars},
        )
        assert ranked == {"BIG.US"}

    def test_the_other_scans_apply_the_same_rule(self) -> None:
        thin = _bars(close=10.0, volume=3_000)
        companies = [_company("aaa.us"), _company("aaa")]
        bars = {"aaa.us": thin, "aaa": thin}

        heatmap = asyncio.run(
            compute_heatmap(
                companies=companies,
                stooq=_PerTicker(bars),
                history_cache=TTLCache(),
                history_cache_ttl=60,
            )
        )
        assert {i.ticker for i in heatmap.items} == {"AAA.US"}

        surge = asyncio.run(
            compute_volume_surge(
                companies=companies,
                stooq=_PerTicker(bars),
                history_cache=TTLCache(),
                history_cache_ttl=60,
                min_ratio=1.0,
            )
        )
        assert surge.scanned_count == 1

    def test_rating_snapshots_use_the_stocks_own_currency(self) -> None:
        thin = _bars(close=10.0, volume=3_000)
        assert build_rating_points(thin) == []
        assert build_rating_points(thin, currency="PLN") == []
        assert len(build_rating_points(thin, currency="USD")) == len(thin)
        assert build_rating_points(_bars(close=500.0, volume=3_000), currency="GBp") == []


# ── Market-scoped screens ─────────────────────────────────────────────────────


class _TwoMarkets:
    """One GPW and two US companies, with the lookups the endpoints use."""

    def __init__(self) -> None:
        self._by_market = {
            "gpw": [GpwCompany(ticker="aaa", name="AAA", sector="Banks", market="gpw")],
            "us": [
                GpwCompany(
                    ticker="bbb.us",
                    name="BBB Inc.",
                    sector="Technology",
                    market="us",
                    exchange="NASDAQ",
                    currency="USD",
                    description="A long description nobody lists.",
                ),
                GpwCompany(ticker="ccc.us", name="CCC Corp.", market="us", currency="USD"),
            ],
        }

    def get_companies(self, market: str = "gpw") -> list[GpwCompany]:
        return self._by_market.get(market, [])

    def enabled_companies(self) -> list[GpwCompany]:
        return [c for companies in self._by_market.values() for c in companies]

    def find(self, ticker: str) -> GpwCompany | None:
        wanted = ticker.strip().casefold()
        return next((c for c in self.enabled_companies() if c.ticker == wanted), None)


@pytest.fixture
def two_markets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "markets", "gpw,us")
    history_cache.clear()
    ranking_cache.clear()
    client = _RecordingClient()
    app.dependency_overrides[get_gpw_company_service] = lambda: _TwoMarkets()
    app.dependency_overrides[get_stooq_client] = lambda: client
    with TestClient(app) as http:
        yield http, client
    app.dependency_overrides.clear()
    history_cache.clear()
    ranking_cache.clear()


class TestMarketCatalogue:
    def test_only_served_markets_are_listed_with_their_counts(self, two_markets) -> None:
        http, _ = two_markets
        body = http.get("/api/stocks/markets").json()
        assert [m["id"] for m in body] == ["gpw", "us"]
        us = body[1]
        assert us["companyCount"] == 2
        assert us["currency"] == "USD"
        assert us["tickerSuffix"] == ".us"
        assert us["refreshRun"] == "us"
        assert [i["name"] for i in us["indices"]] == ["S&P 500", "NASDAQ-100"]
        assert body[0]["tickerSuffix"] == ""

    def test_the_default_deployment_lists_the_gpw_alone(self) -> None:
        with TestClient(app) as http:
            body = http.get("/api/stocks/markets").json()
        assert [m["id"] for m in body] == ["gpw"]
        assert body[0]["companyCount"] == len(GpwCompanyService().get_companies())


class TestCompanyList:
    def test_one_market_or_all(self, two_markets) -> None:
        http, _ = two_markets
        assert [c["ticker"] for c in http.get("/api/stocks").json()] == ["aaa"]
        assert [c["ticker"] for c in http.get("/api/stocks?market=us").json()] == [
            "bbb.us",
            "ccc.us",
        ]
        assert len(http.get("/api/stocks?market=all").json()) == 3

    def test_descriptions_are_left_out_of_the_list(self, two_markets) -> None:
        http, _ = two_markets
        [bbb, _] = http.get("/api/stocks?market=us").json()
        assert "description" not in bbb
        assert bbb["market"] == "us"
        assert bbb["exchange"] == "NASDAQ"

    def test_a_market_that_is_not_served_is_a_400(self) -> None:
        with TestClient(app) as http:
            resp = http.get("/api/stocks?market=us")
        assert resp.status_code == 400
        assert "gpw" in resp.json()["detail"]


class TestRankingPerMarket:
    def test_default_is_the_gpw(self, two_markets) -> None:
        http, client = two_markets
        rows = http.get("/api/stocks/ranking").json()
        assert [r["ticker"] for r in rows] == ["AAA"]
        assert rows[0]["market"] == "gpw"
        assert rows[0]["currency"] == "PLN"
        assert set(client.asked) == {"aaa"}

    def test_one_foreign_market(self, two_markets) -> None:
        http, client = two_markets
        rows = http.get("/api/stocks/ranking?market=us").json()
        assert {r["ticker"] for r in rows} == {"BBB.US", "CCC.US"}
        assert {r["currency"] for r in rows} == {"USD"}
        assert set(client.asked) == {"bbb.us", "ccc.us"}

    def test_all_markets_side_by_side_with_one_total(self, two_markets) -> None:
        http, _ = two_markets
        resp = http.get("/api/stocks/ranking?market=all&pageSize=2")
        assert resp.headers["X-Total-Count"] == "3"
        assert len(resp.json()) == 2

    def test_each_market_is_cached_on_its_own(self, two_markets) -> None:
        http, _ = two_markets
        http.get("/api/stocks/ranking?market=us")
        assert ranking_cache.get("ranking:us:full") is not None
        assert ranking_cache.get("ranking:gpw:full") is None

    def test_favorites_across_markets(self, two_markets) -> None:
        http, _ = two_markets
        rows = http.get("/api/stocks/ranking?market=all&tickers=aaa,ccc.us").json()
        assert {r["ticker"] for r in rows} == {"AAA", "CCC.US"}

    def test_unknown_or_unserved_market_is_a_400(self, two_markets) -> None:
        http, _ = two_markets
        assert http.get("/api/stocks/ranking?market=xx").status_code == 400
        assert http.get("/api/stocks/ranking?market=uk").status_code == 400


class TestSingleMarketScreens:
    def test_heatmap_takes_one_market(self, two_markets) -> None:
        http, _ = two_markets
        body = http.get("/api/stocks/heatmap?market=us").json()
        assert {i["ticker"] for i in body["items"]} == {"BBB.US", "CCC.US"}
        assert {i["currency"] for i in body["items"]} == {"USD"}
        assert http.get("/api/stocks/heatmap?market=all").status_code == 400

    def test_backtest_takes_one_market(self, two_markets) -> None:
        http, client = two_markets
        body = http.get("/api/stocks/methods/vsa/backtest?market=us").json()
        assert body["market"] == "us"
        assert set(client.asked) == {"bbb.us", "ccc.us"}
        assert http.get("/api/stocks/methods/vsa/backtest?market=all").status_code == 400

    def test_capex_takes_one_market(self, two_markets) -> None:
        http, _ = two_markets
        assert http.get("/api/stocks/capex?market=us").status_code == 200
        assert http.get("/api/stocks/capex?market=all").status_code == 400


class TestPooledScreens:
    def test_volume_surge_puts_markets_side_by_side(self, two_markets) -> None:
        http, _ = two_markets
        us = http.get("/api/stocks/volume-surge?market=us&minRatio=1").json()
        both = http.get("/api/stocks/volume-surge?market=all&minRatio=1").json()
        gpw = http.get("/api/stocks/volume-surge?minRatio=1").json()
        assert both["scannedCount"] == us["scannedCount"] + gpw["scannedCount"]
        assert both["totalCount"] == us["totalCount"] + gpw["totalCount"]
        assert {i["market"] for i in both["items"]} <= {"gpw", "us"}

    def test_scanner_stats_can_pool_every_market(self, two_markets) -> None:
        http, client = two_markets
        assert http.get("/api/stocks/scanner/stats?market=all").status_code == 200
        assert set(client.asked) == {"aaa", "bbb.us", "ccc.us"}
        assert ranking_cache.get("scanner:stats:all") is not None


class TestStockPageIdentity:
    def test_signals_carry_market_currency_and_venue(self, two_markets) -> None:
        http, _ = two_markets
        body = http.get("/api/stocks/bbb.us/signals").json()
        assert (body["market"], body["currency"], body["exchange"]) == (
            "us",
            "USD",
            "NASDAQ",
        )
        gpw = http.get("/api/stocks/aaa/signals").json()
        assert (gpw["market"], gpw["currency"], gpw["exchange"]) == ("gpw", "PLN", "GPW")

    def test_rating_history_says_what_its_prices_are_in(self, two_markets) -> None:
        http, _ = two_markets
        body = http.get("/api/stocks/bbb.us/rating-history").json()
        assert body["currency"] == "USD"
        assert body["source"] == "computed"

    def test_ai_insight_quotes_price_levels_in_the_stocks_currency(self, two_markets) -> None:
        http, _ = two_markets
        body = http.get("/api/stocks/bbb.us/ai-analysis").json()
        levels = [o for o in body["keyObservations"] if o.startswith("Nearest support")]
        assert levels and "USD" in levels[0] and "PLN" not in levels[0]
