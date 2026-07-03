"""Tests for IngestService and InMemoryQuoteRepository."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.db.repository import InMemoryQuoteRepository
from app.jobs.daily_ingest import IngestService
from app.models import GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError

# ── Shared helpers ────────────────────────────────────────────────────────────


def _company(ticker: str = "kgh") -> GpwCompany:
    return GpwCompany(ticker=ticker, name=ticker.upper(), sector="Test")


def _quote(d: str, close: float = 100.0, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=date.fromisoformat(d),
        open=Decimal(str(close - 1)),
        high=Decimal(str(close + 2)),
        low=Decimal(str(close - 2)),
        close=Decimal(str(close)),
        volume=volume,
    )


class _FakeStooq:
    """Fake stooq client that returns canned quotes or raises on demand."""

    def __init__(self, quotes: list[StooqDailyQuote] | None = None, fail: bool = False) -> None:
        self.calls: list[str] = []
        self._quotes = quotes or []
        self._fail = fail

    async def get_daily_history(self, ticker: str, from_date=None, to_date=None):
        self.calls.append(ticker)
        if self._fail:
            raise StooqAccessError("Simulated failure")
        return self._quotes


# ── InMemoryQuoteRepository ───────────────────────────────────────────────────


class TestInMemoryQuoteRepository:
    def test_empty_repo_returns_no_quotes(self) -> None:
        repo = InMemoryQuoteRepository()
        result = asyncio.run(repo.get_quotes("kgh", date(2026, 1, 1)))
        assert result == []

    def test_upsert_and_retrieve_quotes(self) -> None:
        repo = InMemoryQuoteRepository()
        quotes = [_quote("2026-06-25"), _quote("2026-06-26")]
        asyncio.run(repo.upsert_quotes("kgh", quotes))

        result = asyncio.run(repo.get_quotes("kgh", date(2026, 6, 25)))
        assert len(result) == 2
        assert result[0].date == date(2026, 6, 25)
        assert result[1].date == date(2026, 6, 26)

    def test_from_date_filters_older_bars(self) -> None:
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", [
            _quote("2026-06-20"),
            _quote("2026-06-25"),
            _quote("2026-06-30"),
        ]))
        result = asyncio.run(repo.get_quotes("kgh", date(2026, 6, 25)))
        assert len(result) == 2
        assert all(q.date >= date(2026, 6, 25) for q in result)

    def test_to_date_filters_newer_bars(self) -> None:
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", [
            _quote("2026-06-20"),
            _quote("2026-06-25"),
            _quote("2026-06-30"),
        ]))
        result = asyncio.run(repo.get_quotes("kgh", date(2026, 6, 1), date(2026, 6, 25)))
        assert len(result) == 2
        assert all(q.date <= date(2026, 6, 25) for q in result)

    def test_upsert_is_idempotent(self) -> None:
        repo = InMemoryQuoteRepository()
        q = _quote("2026-06-25", close=100.0)
        asyncio.run(repo.upsert_quotes("kgh", [q]))
        asyncio.run(repo.upsert_quotes("kgh", [q]))  # duplicate
        result = asyncio.run(repo.get_quotes("kgh", date(2026, 6, 25)))
        assert len(result) == 1

    def test_has_today_data_false_when_empty(self) -> None:
        repo = InMemoryQuoteRepository()
        today = date.today()
        assert asyncio.run(repo.has_today_data("kgh", as_of=today)) is False

    def test_has_today_data_true_after_upsert(self) -> None:
        repo = InMemoryQuoteRepository()
        today = date.today()
        asyncio.run(repo.upsert_quotes("kgh", [_quote(today.isoformat())]))
        assert asyncio.run(repo.has_today_data("kgh", as_of=today)) is True

    def test_quotes_sorted_by_date(self) -> None:
        repo = InMemoryQuoteRepository()
        # Insert in reverse order.
        asyncio.run(repo.upsert_quotes("kgh", [
            _quote("2026-06-30"),
            _quote("2026-06-20"),
            _quote("2026-06-25"),
        ]))
        result = asyncio.run(repo.get_quotes("kgh", date(2026, 6, 1)))
        dates = [q.date for q in result]
        assert dates == sorted(dates)

    def test_upsert_companies_and_retrieve(self) -> None:
        repo = InMemoryQuoteRepository()
        companies = [_company("kgh"), _company("pko")]
        asyncio.run(repo.upsert_companies(companies))
        assert len(repo._companies) == 2

    def test_upsert_companies_updates_existing(self) -> None:
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_companies([GpwCompany(ticker="kgh", name="Old", sector=None)]))
        asyncio.run(repo.upsert_companies([GpwCompany(ticker="kgh", name="New", sector="Mining")]))
        assert len(repo._companies) == 1
        assert repo._companies[0].name == "New"

    def test_tickers_are_isolated(self) -> None:
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", [_quote("2026-06-25")]))
        asyncio.run(repo.upsert_quotes("pko", [_quote("2026-06-25", close=50.0)]))

        kgh = asyncio.run(repo.get_quotes("kgh", date(2026, 6, 1)))
        pko = asyncio.run(repo.get_quotes("pko", date(2026, 6, 1)))
        assert kgh[0].close != pko[0].close


# ── IngestService ─────────────────────────────────────────────────────────────


class TestIngestService:
    def _make_service(
        self,
        companies: list[GpwCompany] | None = None,
        stooq: _FakeStooq | None = None,
        repo: InMemoryQuoteRepository | None = None,
    ) -> tuple[IngestService, _FakeStooq, InMemoryQuoteRepository, TTLCache, TTLCache]:
        companies = companies or [_company("kgh")]
        stooq = stooq or _FakeStooq(quotes=[_quote("2026-06-25")])
        repo = repo or InMemoryQuoteRepository()
        h_cache: TTLCache = TTLCache()
        r_cache: TTLCache = TTLCache()
        svc = IngestService(
            companies=companies,
            stooq=stooq,
            repo=repo,
            history_cache=h_cache,
            ranking_cache=r_cache,
        )
        return svc, stooq, repo, h_cache, r_cache

    def test_run_fetches_all_companies(self) -> None:
        companies = [_company("kgh"), _company("pko"), _company("pkn")]
        fake = _FakeStooq(quotes=[_quote("2026-06-25")])
        svc, _, _, _, _ = self._make_service(companies=companies, stooq=fake)
        asyncio.run(svc.run())
        assert set(fake.calls) == {"kgh", "pko", "pkn"}

    def test_run_persists_quotes_to_repo(self) -> None:
        quotes = [_quote("2026-06-25"), _quote("2026-06-26")]
        svc, _, repo, _, _ = self._make_service(stooq=_FakeStooq(quotes=quotes))
        asyncio.run(svc.run())
        stored = asyncio.run(repo.get_quotes("kgh", date(2026, 6, 1)))
        assert len(stored) == 2

    def test_run_clears_history_cache(self) -> None:
        svc, _, _, h_cache, _ = self._make_service()
        h_cache.set("history:kgh:2026-01-01:None", [_quote("2026-06-25")], 3600)
        asyncio.run(svc.run())
        assert h_cache.get("history:kgh:2026-01-01:None") is None

    def test_run_clears_ranking_cache(self) -> None:
        svc, _, _, _, r_cache = self._make_service()
        r_cache.set("ranking:full", [object()], 3600)
        asyncio.run(svc.run())
        assert r_cache.get("ranking:full") is None

    def test_run_skips_failed_ticker_continues_others(self) -> None:
        """A failure on one ticker must not abort ingestion of others."""
        fail_ticker = "kgh"
        ok_ticker = "pko"
        companies = [_company(fail_ticker), _company(ok_ticker)]

        class _PartialFail(_FakeStooq):
            async def get_daily_history(self, ticker, from_date=None, to_date=None):
                self.calls.append(ticker)
                if ticker == fail_ticker:
                    raise StooqAccessError("Simulated failure")
                return [_quote("2026-06-25")]

        fake = _PartialFail()
        svc, _, repo, _, _ = self._make_service(companies=companies, stooq=fake)
        asyncio.run(svc.run())

        kgh_stored = asyncio.run(repo.get_quotes(fail_ticker, date(2026, 6, 1)))
        pko_stored = asyncio.run(repo.get_quotes(ok_ticker, date(2026, 6, 1)))
        assert kgh_stored == []
        assert len(pko_stored) == 1

    def test_needs_bootstrap_true_when_no_data(self) -> None:
        svc, _, _, _, _ = self._make_service()
        assert asyncio.run(svc.needs_bootstrap()) is True

    def test_needs_bootstrap_false_after_todays_ingest(self) -> None:
        repo = InMemoryQuoteRepository()
        today = date.today()
        asyncio.run(repo.upsert_quotes("kgh", [_quote(today.isoformat())]))
        svc, _, _, _, _ = self._make_service(repo=repo)
        assert asyncio.run(svc.needs_bootstrap()) is False

    def test_full_ingest_requests_more_history(self) -> None:
        """Verify the ``full`` flag causes a different ``from_date`` in the request."""
        from_dates_seen: list[date] = []

        class _RecordingStooq(_FakeStooq):
            async def get_daily_history(self, ticker, from_date=None, to_date=None):
                from_dates_seen.append(from_date)
                return []

        svc, _, _, _, _ = self._make_service(stooq=_RecordingStooq())
        asyncio.run(svc.run(full=True))

        assert from_dates_seen, "No calls made"
        # full ingest: 400 days back; incremental: 5 days back
        expected_from = date.today() - timedelta(days=400)
        assert from_dates_seen[0] == expected_from
