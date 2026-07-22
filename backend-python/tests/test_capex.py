"""Tests for the capex screen (summary math, screen assembly, endpoint)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import (
    get_gpw_company_service,
    get_quote_repository,
    history_cache,
    ranking_cache,
)
from app.main import app
from app.models import CashflowPeriod, FinancialMetrics, GpwCompany
from app.routers.stocks import _load_ticker_capex
from app.services.cache import TTLCache
from app.services.capex_service import build_capex_screen, summarize_capex
from app.services.yahoo_finance_client import (
    YahooFinanceClient,
    _frame_value,
    _periods_from_frame,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quarter(period_end: str, capex: int | None, ocf: int | None = None) -> CashflowPeriod:
    return CashflowPeriod(
        period_end=period_end,
        period_type="quarterly",
        capex=capex,
        operating_cash_flow=ocf,
        currency="PLN",
    )


def _year(period_end: str, capex: int | None, ocf: int | None = None) -> CashflowPeriod:
    return CashflowPeriod(
        period_end=period_end,
        period_type="annual",
        capex=capex,
        operating_cash_flow=ocf,
        currency="PLN",
    )


def _four_quarters(capex: int = 25, ocf: int | None = None) -> list[CashflowPeriod]:
    """Four quarters ending 2026-03-31, each spending ``capex``."""
    return [
        _quarter(end, capex, ocf)
        for end in ("2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30")
    ]


def _company(ticker: str = "tst", name: str = "Test SA", sector: str | None = "Banks"):
    return GpwCompany(ticker=ticker, name=name, sector=sector)


class _FakeCompanyService:
    def __init__(self, companies: list[GpwCompany]) -> None:
        self._companies = companies

    def get_companies(self) -> list[GpwCompany]:
        return self._companies


@pytest.fixture(autouse=True)
def _clear_caches_and_overrides():
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()


# ── summarize_capex ───────────────────────────────────────────────────────────


class TestSummarizeCapex:
    def test_no_data_gives_empty_summary(self) -> None:
        s = summarize_capex([])
        assert s.capex is None
        assert s.basis is None
        assert s.capex_to_revenue_pct is None

    def test_ttm_is_the_sum_of_four_quarters(self) -> None:
        s = summarize_capex(_four_quarters(capex=25))
        assert s.capex_ttm == 100
        assert s.capex == 100
        assert s.basis == "ttm"

    def test_partial_year_is_not_summed(self) -> None:
        # Three quarters would understate a year of spending by a quarter —
        # better no number than a confidently wrong one.
        s = summarize_capex(_four_quarters()[:3])
        assert s.capex_ttm is None

    def test_missing_figure_in_one_quarter_blocks_the_sum(self) -> None:
        quarters = _four_quarters()
        quarters[1] = _quarter(quarters[1].period_end, None)
        s = summarize_capex(quarters)
        assert s.capex_ttm is None

    def test_falls_back_to_the_latest_full_year(self) -> None:
        s = summarize_capex([_year("2025-12-31", 400), _year("2024-12-31", 300)])
        assert s.basis == "annual"
        assert s.capex == 400
        assert s.capex_annual == 400
        assert s.annual_period_end == "2025-12-31"

    def test_ttm_wins_over_annual_when_both_exist(self) -> None:
        s = summarize_capex([*_four_quarters(capex=25), _year("2025-12-31", 400)])
        assert s.basis == "ttm"
        assert s.capex == 100
        # The annual figures stay available for the year-on-year comparison.
        assert s.capex_annual == 400

    def test_year_on_year_growth_uses_annual_figures(self) -> None:
        s = summarize_capex([_year("2025-12-31", 150), _year("2024-12-31", 100)])
        assert s.capex_growth_yoy_pct == 50.0

    def test_growth_needs_two_years(self) -> None:
        assert summarize_capex([_year("2025-12-31", 150)]).capex_growth_yoy_pct is None

    def test_zero_previous_year_does_not_divide_by_zero(self) -> None:
        s = summarize_capex([_year("2025-12-31", 150), _year("2024-12-31", 0)])
        assert s.capex_growth_yoy_pct is None

    def test_ratios_are_percentages_of_revenue_and_cash_flow(self) -> None:
        s = summarize_capex(_four_quarters(capex=25, ocf=50), ttm_revenue=1_000)
        # 100 of capex against 1,000 revenue and 200 of operating cash flow.
        assert s.capex_to_revenue_pct == 10.0
        assert s.capex_to_ocf_pct == 50.0

    def test_ratio_is_blank_without_revenue(self) -> None:
        assert summarize_capex(_four_quarters()).capex_to_revenue_pct is None

    def test_negative_cash_flow_gives_no_ratio(self) -> None:
        # A loss-making year has no meaningful "share of cash flow spent".
        s = summarize_capex(_four_quarters(capex=25, ocf=-50))
        assert s.capex_to_ocf_pct is None

    def test_currency_travels_with_the_figures(self) -> None:
        periods = [
            CashflowPeriod(
                period_end="2025-12-31",
                period_type="annual",
                capex=500,
                currency="EUR",
            )
        ]
        assert summarize_capex(periods).currency == "EUR"


# ── build_capex_screen ────────────────────────────────────────────────────────


class TestBuildCapexScreen:
    def test_every_company_gets_a_row_even_without_data(self) -> None:
        screen = build_capex_screen(
            [_company("aaa"), _company("bbb")],
            cashflow={"aaa": _four_quarters(capex=25)},
            revenue={},
        )
        assert screen.total_count == 2
        assert screen.with_data_count == 1
        # The company with no data keeps its identity and blank figures — it is
        # "not reported", not "invested nothing".
        blank = next(i for i in screen.items if i.ticker == "BBB")
        assert blank.capex is None

    def test_biggest_investor_first_and_blanks_last(self) -> None:
        screen = build_capex_screen(
            [_company("aaa"), _company("bbb"), _company("ccc")],
            cashflow={
                "aaa": [_year("2025-12-31", 100)],
                "ccc": [_year("2025-12-31", 900)],
            },
            revenue={},
        )
        assert [i.ticker for i in screen.items] == ["CCC", "AAA", "BBB"]

    def test_as_of_is_the_newest_reported_period(self) -> None:
        screen = build_capex_screen(
            [_company("aaa")],
            cashflow={"aaa": [_year("2025-12-31", 100), _quarter("2026-03-31", 30)]},
            revenue={},
        )
        assert screen.as_of == "2026-03-31"

    def test_revenue_is_matched_by_ticker(self) -> None:
        screen = build_capex_screen(
            [_company("aaa")],
            cashflow={"aaa": _four_quarters(capex=25)},
            revenue={"aaa": 1_000},
        )
        assert screen.items[0].capex_to_revenue_pct == 10.0


# ── Yahoo cash-flow frame parsing ─────────────────────────────────────────────


class TestPeriodsFromFrame:
    """The frame layout is Yahoo's: rows = statement lines, columns = periods."""

    @staticmethod
    def _frame(rows: dict[str, list[float]], periods: list[str]):
        """Build a Yahoo-shaped cash-flow frame: {row label: [value per period]}."""
        pd = pytest.importorskip("pandas")
        return pd.DataFrame(
            list(rows.values()),
            index=list(rows),
            columns=[pd.Timestamp(p) for p in periods],
        )

    def test_capex_is_stored_as_positive_money_spent(self) -> None:
        frame = self._frame(
            {"Capital Expenditure": [-1_400.0], "Operating Cash Flow": [5_000.0]},
            ["2025-12-31"],
        )
        periods = _periods_from_frame(frame, "annual", "PLN", 5)
        assert len(periods) == 1
        assert periods[0].capex == 1_400
        assert periods[0].operating_cash_flow == 5_000
        assert periods[0].period_end == "2025-12-31"

    def test_falls_back_to_purchase_of_ppe(self) -> None:
        frame = self._frame({"Purchase Of PPE": [-250.0]}, ["2025-12-31"])
        periods = _periods_from_frame(frame, "annual", "PLN", 5)
        assert periods[0].capex == 250

    def test_empty_cell_is_skipped_not_read_as_zero(self) -> None:
        # Yahoo commonly lists the row and leaves the newest period blank.
        frame = self._frame(
            {"Capital Expenditure": [float("nan"), -800.0]},
            ["2025-12-31", "2024-12-31"],
        )
        periods = _periods_from_frame(frame, "annual", "PLN", 5)
        assert [p.period_end for p in periods] == ["2024-12-31"]
        assert periods[0].capex == 800

    def test_no_capex_row_yields_nothing(self) -> None:
        frame = self._frame({"Operating Cash Flow": [5_000.0]}, ["2025-12-31"])
        assert _periods_from_frame(frame, "annual", "PLN", 5) == []

    def test_empty_frame_is_handled(self) -> None:
        assert _periods_from_frame(None, "annual", "PLN", 5) == []

    def test_frame_value_reads_a_row_via_the_prebuilt_label_map(self) -> None:
        # The label map is built once per frame and handed in, so the lookup
        # stays a pure function of (frame, column, row names, labels).
        frame = self._frame({"Capital Expenditure": [-1_400.0]}, ["2025-12-31"])
        labels = {str(idx): idx for idx in frame.index}
        column = frame.columns[0]
        assert _frame_value(frame, column, ("Capital Expenditure",), labels) == -1_400
        assert _frame_value(frame, column, ("Nope",), labels) is None


# ── GET /api/stocks/capex ─────────────────────────────────────────────────────


def _seed(repo: InMemoryQuoteRepository) -> InMemoryQuoteRepository:
    """Fill a repository with two companies that have capex, one without."""
    asyncio.run(repo.upsert_cashflow("aaa", _four_quarters(capex=25, ocf=50)))
    asyncio.run(repo.upsert_cashflow("bbb", [_year("2025-12-31", 900)]))
    asyncio.run(
        repo.upsert_fundamentals("aaa", FinancialMetrics(total_revenue=1_000))
    )
    return repo


def _seed_repo() -> InMemoryQuoteRepository:
    """Two companies with capex, one without."""
    return _seed(InMemoryQuoteRepository())


class _FlakyRepo(InMemoryQuoteRepository):
    """Fails the first whole-table cash-flow read, then behaves normally."""

    def __init__(self, failures: int = 1) -> None:
        super().__init__()
        self.failures = failures

    async def get_all_cashflow(self):  # type: ignore[override]
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("database unavailable")
        return await super().get_all_cashflow()


def _client(repo: InMemoryQuoteRepository | None) -> TestClient:
    companies = [
        _company("aaa", "Alpha SA", "Banks"),
        _company("bbb", "Beta SA", "Energy"),
        _company("ccc", "Gamma SA", "Energy"),
    ]
    app.dependency_overrides[get_gpw_company_service] = lambda: _FakeCompanyService(
        companies
    )
    app.dependency_overrides[get_quote_repository] = lambda: repo
    return TestClient(app)


class TestCapexEndpoint:
    def test_returns_companies_with_data_biggest_first(self) -> None:
        with _client(_seed_repo()) as client:
            body = client.get("/api/stocks/capex").json()
        assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA"]
        assert body["totalCount"] == 2
        assert body["withDataCount"] == 2
        assert body["scannedCount"] == 3

    def test_with_data_false_keeps_companies_without_figures(self) -> None:
        with _client(_seed_repo()) as client:
            body = client.get("/api/stocks/capex?withData=false").json()
        assert body["totalCount"] == 3
        blank = next(i for i in body["items"] if i["ticker"] == "CCC")
        assert blank["capex"] is None
        assert blank["basis"] is None

    def test_row_carries_the_computed_ratios(self) -> None:
        with _client(_seed_repo()) as client:
            body = client.get("/api/stocks/capex?q=alpha").json()
        row = body["items"][0]
        assert row["ticker"] == "AAA"
        assert row["capex"] == 100
        assert row["basis"] == "ttm"
        assert row["capexToRevenuePct"] == 10.0
        assert row["capexToOcfPct"] == 50.0
        assert row["currency"] == "PLN"

    def test_foreign_currency_rows_are_hidden_by_default(self) -> None:
        # A forint or euro amount would top a zloty-sorted list on unit size
        # alone (580bn HUF is far less money than 30bn PLN), so the default
        # view is the comparable set: the zloty reporters.
        repo = _seed_repo()
        asyncio.run(
            repo.upsert_cashflow(
                "ccc",
                [
                    CashflowPeriod(
                        period_end="2025-12-31",
                        period_type="annual",
                        capex=580_000_000_000,
                        currency="HUF",
                    )
                ],
            )
        )
        with _client(repo) as client:
            default = client.get("/api/stocks/capex").json()
            everything = client.get("/api/stocks/capex?currency=all").json()

        assert "CCC" not in [i["ticker"] for i in default["items"]]
        assert [i["ticker"] for i in everything["items"]][0] == "CCC"

    def test_currency_filter_keeps_rows_that_have_no_amount(self) -> None:
        # A company with no reported capex has no amount to compare, so the
        # currency filter must not silently swallow it when the user has
        # asked to see the blank rows.
        with _client(_seed_repo()) as client:
            body = client.get("/api/stocks/capex?withData=false").json()
        assert "CCC" in [i["ticker"] for i in body["items"]]

    def test_sector_filter(self) -> None:
        with _client(_seed_repo()) as client:
            body = client.get("/api/stocks/capex?sector=Energy").json()
        assert [i["ticker"] for i in body["items"]] == ["BBB"]

    def test_sorting_and_pagination(self) -> None:
        with _client(_seed_repo()) as client:
            body = client.get(
                "/api/stocks/capex?sortBy=capex&sortDir=asc&pageSize=1"
            ).json()
        assert [i["ticker"] for i in body["items"]] == ["AAA"]
        # totalCount reflects all matching rows, not the page.
        assert body["totalCount"] == 2

    def test_unknown_sort_column_is_rejected(self) -> None:
        with _client(_seed_repo()) as client:
            resp = client.get("/api/stocks/capex?sortBy=__class__")
        assert resp.status_code == 400

    def test_without_a_database_the_screen_is_empty_not_an_error(self) -> None:
        # The figures only ever arrive through the ingest job, so there is
        # nothing to fall back to — but the page must still render.
        with _client(None) as client:
            body = client.get("/api/stocks/capex").json()
        assert body["items"] == []
        assert body["totalCount"] == 0
        assert body["scannedCount"] == 3

    def test_failed_db_read_is_not_cached_as_an_empty_screen(self) -> None:
        # A momentary database failure must not be remembered as "this app has
        # no investment data": that message sends the user to a Refresh button
        # which cannot fix it, and would stick for the whole cache lifetime.
        repo = _seed(_FlakyRepo())
        with _client(repo) as client:
            first = client.get("/api/stocks/capex")
            second = client.get("/api/stocks/capex")

        assert first.status_code == 503
        assert second.status_code == 200
        assert [i["ticker"] for i in second.json()["items"]] == ["BBB", "AAA"]

    def test_padded_all_sentinel_is_still_recognised(self) -> None:
        # "?currency= all " must lift the filter, not search for a currency
        # literally called "ALL" and return nothing.
        with _client(_seed_repo()) as client:
            body = client.get("/api/stocks/capex?currency=%20all%20").json()
        assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA"]

    def test_padded_sector_is_matched(self) -> None:
        with _client(_seed_repo()) as client:
            body = client.get("/api/stocks/capex?sector=%20Energy%20").json()
        assert [i["ticker"] for i in body["items"]] == ["BBB"]


# ── Per-ticker capex on the stock page (live fetch + negative caching) ────────


class _CountingYahoo(YahooFinanceClient):
    """Counts live cash-flow fetches and returns a canned answer."""

    def __init__(self, periods: list[CashflowPeriod] | None = None) -> None:
        self.periods = periods or []
        self.calls = 0

    async def get_cashflow_periods(self, ticker: str) -> list[CashflowPeriod]:
        self.calls += 1
        return list(self.periods)


class TestLoadTickerCapex:
    def test_missing_data_is_fetched_once_not_on_every_page_view(self) -> None:
        # Yahoo has no cash-flow statement for roughly one company in twenty.
        # Nothing gets persisted for those, so without a remembered "nothing to
        # find" marker every view of the stock page repeats two network round
        # trips to learn the same thing.
        yahoo = _CountingYahoo(periods=[])
        cache: TTLCache = TTLCache()

        async def load() -> None:
            for _ in range(3):
                assert (
                    await _load_ticker_capex(
                        "aaa", repo=None, stooq=yahoo, cache=cache, ttm_revenue=None
                    )
                    is None
                )

        asyncio.run(load())
        assert yahoo.calls == 1

    def test_a_company_with_data_is_still_fetched_and_summarised(self) -> None:
        yahoo = _CountingYahoo(periods=[_year("2025-12-31", 900)])
        cache: TTLCache = TTLCache()
        summary = asyncio.run(
            _load_ticker_capex(
                "bbb", repo=None, stooq=yahoo, cache=cache, ttm_revenue=None
            )
        )
        assert yahoo.calls == 1
        assert summary is not None
        assert summary.capex == 900
        assert summary.basis == "annual"

    def test_stored_data_short_circuits_the_live_fetch(self) -> None:
        repo = _seed(InMemoryQuoteRepository())
        yahoo = _CountingYahoo(periods=[])
        cache: TTLCache = TTLCache()
        summary = asyncio.run(
            _load_ticker_capex(
                "bbb", repo=repo, stooq=yahoo, cache=cache, ttm_revenue=None
            )
        )
        assert yahoo.calls == 0
        assert summary is not None
        assert summary.capex == 900
