"""Observation initialization resumes per company and market after partial writes."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from app.db.repository import InMemoryQuoteRepository
from app.jobs import daily_ingest
from app.jobs.daily_ingest import IngestService
from app.models import CashflowPeriod, FinancialMetrics, GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache


class _Thursday(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 22, 18, tzinfo=UTC).astimezone(tz)


class _Provider:
    def __init__(self):
        self.financial_calls = []

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return [StooqDailyQuote(
            date=date(2026, 10, 21), open=Decimal(100), high=Decimal(100),
            low=Decimal(100), close=Decimal(100), volume=100_000,
        )]

    async def get_fundamentals(self, ticker):
        self.financial_calls.append(ticker)
        return FinancialMetrics(pe_ratio=12, financial_currency="PLN")

    async def get_quarterly_reports(self, ticker):
        return []

    async def get_cashflow_periods(self, ticker):
        return []


def _service(repo, provider=None):
    return IngestService(
        companies=[GpwCompany(ticker=t, name=t) for t in ("aaa", "bbb", "ccc.us")],
        stooq=provider or _Provider(), repo=repo,
        history_cache=TTLCache(), ranking_cache=TTLCache(),
    )


async def test_one_archived_company_does_not_skip_remaining_market_members(monkeypatch):
    monkeypatch.setattr(daily_ingest, "datetime", _Thursday)
    repo = InMemoryQuoteRepository()
    await repo.upsert_fundamentals("aaa", FinancialMetrics(pe_ratio=10))
    await repo.upsert_cashflow("aaa", [CashflowPeriod(
        period_end="2025-12-31", period_type="annual", capex=100, currency="PLN",
    )])
    provider = _Provider()
    service = _service(repo, provider)
    monkeypatch.setattr(service, "_fetch_company_insiders", AsyncMock(return_value=0))
    before = await repo.get_financial_history("aaa")

    stats = await service.run(markets=["gpw"])

    assert stats.fundamentals_run
    assert provider.financial_calls == ["bbb"]
    assert await repo.get_financial_history("aaa") == before
    assert len(await repo.get_financial_history("bbb")) == 1
    assert await repo.get_financial_history("ccc.us") == []

    # Unavailable optional statements must not turn every weekday into a full
    # fundamentals fetch. A real initial observation is sufficient here.
    second = await service.run(markets=["gpw"])
    assert not second.fundamentals_run
    assert provider.financial_calls == ["bbb"]


async def _snapshot(repo, ticker, market):
    await repo.append_long_term_snapshots(
        [{"ticker": ticker, "market": market, "asOf": "2026-10-21"}],
        datetime(2026, 10, 22, 12, tzinfo=UTC), "qvm-v1",
    )


async def test_restart_resumes_only_markets_with_missing_observations():
    repo = InMemoryQuoteRepository()
    service = _service(repo)
    for ticker in ("aaa", "bbb", "ccc.us"):
        await repo.upsert_fundamentals(ticker, FinancialMetrics(pe_ratio=10))
    await _snapshot(repo, "aaa", "gpw")

    # A first refresh interrupted after GPW still needs the US snapshot.
    assert await service.observation_bootstrap_markets() == ["us"]
    await _snapshot(repo, "ccc.us", "us")
    assert await service.observation_bootstrap_markets() == []

    # Having scores everywhere does not prove financial history is complete.
    repo._financial_observations = [
        row for row in repo._financial_observations if row["ticker"] != "bbb"
    ]
    assert await service.observation_bootstrap_markets() == ["gpw"]
