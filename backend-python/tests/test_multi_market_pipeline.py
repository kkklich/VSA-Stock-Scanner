"""The data pipeline once several markets are served.

Pinned here:

* caches are dropped per market — a US run at 23:15 leaves the GPW alone;
* the ingest touches only the markets it was asked for, gives a market new to
  the database the full download, and the start-up check tells "new", "behind"
  and "current" apart on each market's own clock;
* the refresh pipeline ranks and pre-warms each refreshed market separately;
* one scheduled job per group of markets, each on its own clock;
* the health check judges each run and each market, so US stocks waiting for
  their run are not "stale";
* Yahoo's rate limit is waited out rather than costing the ticker its night;
* the heatmap's MAX change comes from the oldest stored close.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.db.health_repository import MarketStoredStats, StoredDataStats
from app.db.repository import InMemoryQuoteRepository
from app.jobs.daily_ingest import IngestService, build_scheduler, markets_in
from app.markets import GPW, US, refresh_runs
from app.models import GpwCompany, StooqDailyQuote
from app.services import yahoo_finance_client
from app.services.action_log import OUTCOME_FAILED, OUTCOME_FINISHED
from app.services.cache import TTLCache
from app.services.heatmap_service import compute_heatmap
from app.services.market_cache import (
    history_key_ticker,
    invalidate_markets,
    ranking_key_scope,
)
from app.services.refresh_service import RefreshService
from app.services.system_health import (
    JobRecord,
    combine_ingest,
    evaluate_data,
    evaluate_ingest,
    job_covers,
    last_scheduled_run,
)

_WARSAW = ZoneInfo("Europe/Warsaw")


def _bar(day: date, close: float = 100.0, volume: int = 200_000) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=day,
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(n: int = 40, end: date | None = None) -> list[StooqDailyQuote]:
    end = end or date.today()
    return [_bar(end - timedelta(days=n - 1 - i)) for i in range(n)]


_GPW_CO = GpwCompany(ticker="aaa", name="AAA")
_US_CO = GpwCompany(ticker="bbb.us", name="BBB", market="us", currency="USD")
_UK_CO = GpwCompany(ticker="ccc.l", name="CCC", market="uk")


@pytest.fixture
def all_markets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "markets", "all")


# ── Caches ────────────────────────────────────────────────────────────────────


class TestInvalidate:
    def test_matching_keys_go_and_the_generation_moves(self) -> None:
        cache: TTLCache = TTLCache()
        cache.set("keep", 1, 60)
        cache.set("drop:1", 2, 60)
        before = cache.generation
        assert cache.invalidate(lambda k: k.startswith("drop")) == 1
        assert cache.get("keep") == 1
        assert cache.get("drop:1") is None
        assert cache.generation == before + 1

    def test_a_computation_from_before_is_not_written_back(self) -> None:
        cache: TTLCache = TTLCache()
        generation = cache.generation
        cache.invalidate(lambda _k: False)
        assert cache.set_if_generation("x", 1, 60, generation) is False


class TestKeyParsing:
    @pytest.mark.parametrize(
        ("key", "ticker"),
        [
            ("history:aapl.us:2025-01-01:None", "aapl.us"),
            ("history:kgh:2025-01-01:None", "kgh"),
            ("resp:history:sap.de:None:None", "sap.de"),
            ("backtest-history:hsba.l:2022-09-01", "hsba.l"),
            ("intraday:mc.pa:30m:60", "mc.pa"),
            ("capex-miss:asml.as", "asml.as"),
            ("garbage", None),
        ],
    )
    def test_history_keys(self, key: str, ticker: str | None) -> None:
        assert history_key_ticker(key) == ticker

    @pytest.mark.parametrize(
        ("key", "scope"),
        [
            ("ranking:us:full", "us"),
            ("ranking:gpw:full:abc123", "gpw"),
            ("heatmap:uk:abc123", "uk"),
            ("heatmap:de", "de"),
            ("volume-surge:all:3:20:1.5", "all"),
            ("scanner:stats:fr", "fr"),
            ("method-backtest:nl:vsa:10", "nl"),
            ("capex:gpw:full", "gpw"),
            ("oddity", None),
        ],
    )
    def test_ranking_keys(self, key: str, scope: str | None) -> None:
        assert ranking_key_scope(key) == scope


class TestInvalidateMarkets:
    def _caches(self) -> tuple[TTLCache, TTLCache]:
        history: TTLCache = TTLCache()
        ranking: TTLCache = TTLCache()
        for key in ("history:kgh:x:None", "history:aapl.us:x:None", "resp:history:msft.us:a:b"):
            history.set(key, [1], 60)
        for key in ("ranking:gpw:full", "ranking:us:full", "scanner:stats:all", "heatmap:us"):
            ranking.set(key, [1], 60)
        return history, ranking

    def test_a_us_run_leaves_the_gpw_alone(self, all_markets: None) -> None:
        history, ranking = self._caches()
        invalidate_markets(["us"], (history, "history"), (ranking, "ranking"))
        assert history.get("history:kgh:x:None") is not None
        assert history.get("history:aapl.us:x:None") is None
        assert history.get("resp:history:msft.us:a:b") is None
        assert ranking.get("ranking:gpw:full") is not None
        assert ranking.get("ranking:us:full") is None
        assert ranking.get("heatmap:us") is None
        # A pooled screen includes the refreshed market, so it goes too.
        assert ranking.get("scanner:stats:all") is None

    def test_every_served_market_is_a_plain_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "markets", "gpw")
        history, ranking = self._caches()
        invalidate_markets(["gpw"], (history, "history"), (ranking, "ranking"))
        assert len(history) == 0
        assert len(ranking) == 0

    def test_an_unknown_kind_is_a_programming_error(self, all_markets: None) -> None:
        with pytest.raises(ValueError):
            invalidate_markets(["us"], (TTLCache(), "weird"))


# ── Ingest ────────────────────────────────────────────────────────────────────


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date | None]] = []

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.calls.append((ticker, from_date))
        return _series(3)


def _ingest(repo: InMemoryQuoteRepository | None = None, history=None, ranking=None):
    client = _Recorder()
    svc = IngestService(
        companies=[_GPW_CO, _US_CO, _UK_CO],
        stooq=client,
        repo=repo or InMemoryQuoteRepository(),
        history_cache=history or TTLCache(),
        ranking_cache=ranking or TTLCache(),
    )
    return svc, client


class TestIngestScope:
    def test_markets_in_follows_display_order(self) -> None:
        assert markets_in([_UK_CO, _US_CO, _GPW_CO]) == ["gpw", "us", "uk"]

    def test_only_the_requested_markets_are_downloaded(self, all_markets: None) -> None:
        svc, client = _ingest()
        stats = asyncio.run(svc.run(markets=["us"]))
        assert [t for t, _ in client.calls] == ["bbb.us"]
        assert stats.markets == ["us"]
        assert stats.companies == 1
        assert stats.as_detail()["markets"] == ["us"]

    def test_a_new_market_gets_the_full_window_the_others_a_top_up(
        self, all_markets: None
    ) -> None:
        svc, client = _ingest()
        asyncio.run(svc.run(markets=["gpw", "us"], full_markets=["us"]))
        windows = dict(client.calls)
        today = datetime.now(_WARSAW).date()
        assert (today - windows["bbb.us"]).days == 400
        assert (today - windows["aaa"]).days == 5

    def test_the_run_drops_only_its_own_markets_caches(self, all_markets: None) -> None:
        history: TTLCache = TTLCache()
        ranking: TTLCache = TTLCache()
        history.set("history:aaa:x:None", [1], 60)
        history.set("history:bbb.us:x:None", [1], 60)
        ranking.set("ranking:gpw:full", [1], 60)
        ranking.set("ranking:us:full", [1], 60)
        svc, _ = _ingest(history=history, ranking=ranking)
        asyncio.run(svc.run(markets=["us"]))
        assert history.get("history:aaa:x:None") is not None
        assert history.get("history:bbb.us:x:None") is None
        assert ranking.get("ranking:gpw:full") is not None
        assert ranking.get("ranking:us:full") is None


class _FundamentalsRecorder(_Recorder):
    def __init__(self) -> None:
        super().__init__()
        self.fundamentals: list[str] = []

    async def get_fundamentals(self, ticker):
        self.fundamentals.append(ticker)
        raise RuntimeError("not needed for this test")


class TestFundamentalsScope:
    def _run(self, monkeypatch: pytest.MonkeyPatch, weekday_date: date, **run_kwargs):
        from app.jobs import daily_ingest

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001 — mirrors datetime.now
                return datetime.combine(weekday_date, datetime.min.time(), tzinfo=tz)

        monkeypatch.setattr(daily_ingest, "datetime", _Clock)
        client = _FundamentalsRecorder()
        svc = IngestService(
            companies=[_GPW_CO, _US_CO, _UK_CO],
            stooq=client,
            repo=InMemoryQuoteRepository(),
            history_cache=TTLCache(),
            ranking_cache=TTLCache(),
        )

        async def nothing_missing() -> bool:
            return False

        monkeypatch.setattr(svc, "_fundamentals_missing", nothing_missing)
        asyncio.run(svc.run(**run_kwargs))
        return client

    def test_a_new_market_fetches_only_its_own_fundamentals(
        self, all_markets: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tuesday = date(2026, 9, 15)
        client = self._run(
            monkeypatch, tuesday, markets=["gpw", "us"], full_markets=["us"]
        )
        assert client.fundamentals == ["bbb.us"]

    def test_an_ordinary_weekday_fetches_none(
        self, all_markets: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = self._run(monkeypatch, date(2026, 9, 15), markets=["gpw", "us"])
        assert client.fundamentals == []

    def test_monday_fetches_every_company_in_the_run(
        self, all_markets: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monday = date(2026, 9, 14)
        client = self._run(monkeypatch, monday, markets=["gpw", "us"])
        assert sorted(client.fundamentals) == ["aaa", "bbb.us"]


class TestBootstrapPlan:
    # Wednesday 16 Sep 2026, 20:00 Warsaw = 14:00 New York: Europe has closed
    # for the day, the US is still trading.
    NOW = datetime(2026, 9, 16, 18, 0, tzinfo=UTC)

    def _repo(self, newest: dict[str, date]) -> InMemoryQuoteRepository:
        repo = InMemoryQuoteRepository()
        for ticker, day in newest.items():
            asyncio.run(repo.upsert_quotes(ticker, [_bar(day)]))
        return repo

    def _plan(self, newest: dict[str, date]):
        svc, _ = _ingest(self._repo(newest))
        return asyncio.run(svc.bootstrap_plan(now=self.NOW))

    def test_an_empty_database_needs_everything(self, all_markets: None) -> None:
        plan = self._plan({})
        assert plan.full == ["gpw", "us", "uk"]
        assert plan.markets == ["gpw", "us", "uk"]

    def test_current_everywhere_needs_nothing(self, all_markets: None) -> None:
        # Europe has today's bar; the US has yesterday's — its session today
        # has not finished, so that is current.
        plan = self._plan(
            {"aaa": date(2026, 9, 16), "ccc.l": date(2026, 9, 16), "bbb.us": date(2026, 9, 15)}
        )
        assert not plan.needed

    def test_a_missed_european_run_is_a_top_up_not_a_full_download(
        self, all_markets: None
    ) -> None:
        plan = self._plan(
            {"aaa": date(2026, 9, 15), "ccc.l": date(2026, 9, 16), "bbb.us": date(2026, 9, 15)}
        )
        assert plan.full == []
        assert plan.catch_up == ["gpw"]

    def test_a_newly_served_market_gets_the_full_download(self, all_markets: None) -> None:
        plan = self._plan({"aaa": date(2026, 9, 16), "ccc.l": date(2026, 9, 16)})
        assert plan.full == ["us"]
        assert plan.catch_up == []

    def test_a_restart_before_the_close_needs_nothing(self, all_markets: None) -> None:
        # 10:00 Warsaw on the 16th: the newest finished session is the 15th.
        svc, _ = _ingest(
            self._repo(
                {"aaa": date(2026, 9, 15), "ccc.l": date(2026, 9, 15), "bbb.us": date(2026, 9, 15)}
            )
        )
        plan = asyncio.run(svc.bootstrap_plan(now=datetime(2026, 9, 16, 8, 0, tzinfo=UTC)))
        assert not plan.needed


class TestLatestFinalSession:
    def test_weekends_step_back_to_friday(self) -> None:
        saturday = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        assert GPW.latest_final_session(saturday) == date(2026, 9, 18)

    def test_before_the_close_it_is_the_previous_weekday(self) -> None:
        monday_morning = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
        assert GPW.latest_final_session(monday_morning) == date(2026, 9, 11)

    def test_each_market_on_its_own_clock(self) -> None:
        evening = datetime(2026, 9, 16, 18, 0, tzinfo=UTC)  # 20:00 Warsaw
        assert GPW.latest_final_session(evening) == date(2026, 9, 16)
        assert US.latest_final_session(evening) == date(2026, 9, 15)


# ── Refresh pipeline ──────────────────────────────────────────────────────────


class _SeriesClient:
    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return _series(40)


class TestRefreshPerMarket:
    def test_a_market_run_ranks_and_warms_only_that_market(self, all_markets: None) -> None:
        ranking: TTLCache = TTLCache()
        svc = RefreshService(
            companies=[_GPW_CO, _US_CO, _UK_CO],
            stooq=_SeriesClient(),
            history_cache=TTLCache(),
            ranking_cache=ranking,
        )
        asyncio.run(svc.run(markets=["us"]))
        assert svc.last_error is None
        assert svc.stocks_ranked == 1
        assert [r.ticker for r in ranking.get("ranking:us:full")] == ["BBB.US"]
        assert ranking.get("ranking:gpw:full") is None

    def test_the_button_refreshes_every_market(self, all_markets: None) -> None:
        ranking: TTLCache = TTLCache()
        svc = RefreshService(
            companies=[_GPW_CO, _US_CO],
            stooq=_SeriesClient(),
            history_cache=TTLCache(),
            ranking_cache=ranking,
        )
        asyncio.run(svc.run(trigger="manual"))
        assert svc.stocks_ranked == 2
        assert ranking.get("ranking:gpw:full") is not None
        assert ranking.get("ranking:us:full") is not None

    def test_snapshots_use_each_stocks_currency(self, all_markets: None) -> None:
        # 10 × 3,000 = 30,000 a day: liquid in dollars, too thin in złoty.
        class _Thin:
            async def get_daily_history(self, ticker, from_date=None, to_date=None):
                return [_bar(b.date, close=10.0, volume=3_000) for b in _series(40)]

        repo = InMemoryQuoteRepository()
        svc = RefreshService(
            companies=[_GPW_CO, _US_CO],
            stooq=_Thin(),
            history_cache=TTLCache(),
            ranking_cache=TTLCache(),
            repo=repo,
        )
        asyncio.run(svc.run())
        assert svc.snapshots_written == 1
        assert asyncio.run(repo.get_rating_history("bbb.us", date(2000, 1, 1)))


# ── Schedules ─────────────────────────────────────────────────────────────────


class TestRefreshRuns:
    def test_the_default_deployment_has_the_one_european_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "markets", "gpw")
        [run] = refresh_runs()
        assert (run.id, run.job_id, run.market_ids) == ("europe", "daily_ingest", ("gpw",))
        assert run.schedule == "18:00 Europe/Warsaw"

    def test_serving_the_us_adds_a_new_york_run(self, all_markets: None) -> None:
        europe, us = refresh_runs()
        assert europe.market_ids == ("gpw", "de", "fr", "nl", "uk")
        assert (us.id, us.job_id, us.market_ids) == ("us", "daily_ingest_us", ("us",))
        assert us.schedule == "17:15 America/New_York"

    def test_each_run_is_its_own_job_on_its_own_clock(self, all_markets: None) -> None:
        class _Refresh:
            async def run(self, **_kwargs) -> None:
                return None

        scheduler = build_scheduler(_Refresh(), runs=refresh_runs())
        europe = scheduler.get_job("daily_ingest")
        us = scheduler.get_job("daily_ingest_us")
        assert str(europe.trigger.timezone) == "Europe/Warsaw"
        assert str(us.trigger.timezone) == "America/New_York"
        assert us.kwargs == {"markets": ["us"]}
        assert europe.kwargs == {"markets": ["gpw", "de", "fr", "nl", "uk"]}

    def test_the_old_single_job_still_covers_everything(self) -> None:
        class _Refresh:
            async def run(self, **_kwargs) -> None:
                return None

        job = build_scheduler(_Refresh(), hour=18, minute=0).get_job("daily_ingest")
        assert job.kwargs == {"markets": None}


# ── Health ────────────────────────────────────────────────────────────────────


def _job(action: str, when: datetime, outcome: str = OUTCOME_FINISHED, **detail) -> JobRecord:
    return JobRecord(action=action, outcome=outcome, started_at=when, detail=detail or None)


class TestIngestHealthPerRun:
    NOW = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)  # Thursday noon, Warsaw

    def test_scheduled_time_on_new_yorks_clock(self) -> None:
        due = last_scheduled_run(self.NOW, 17, 15, "America/New_York")
        assert due.isoformat() == "2026-09-16T17:15:00-04:00"

    def test_legacy_entries_count_for_the_gpw_run_only(self) -> None:
        old = _job("job.refresh", self.NOW)
        assert job_covers(old, ["gpw", "de"], legacy=True)
        assert not job_covers(old, ["us"], legacy=False)
        tagged = _job("job.refresh", self.NOW, markets=["us"])
        assert job_covers(tagged, ["us"], legacy=False)
        assert not job_covers(tagged, ["gpw"], legacy=True)

    def _run(self, jobs, run_id, hour, minute, zone, markets):
        return evaluate_ingest(
            jobs,
            now=self.NOW,
            running=False,
            scheduler_active=True,
            next_run_at=None,
            hour=hour,
            minute=minute,
            timezone=zone,
            run_id=run_id,
            markets=markets,
        )

    def test_a_missed_us_run_shows_even_when_europe_ran(self) -> None:
        europe_ran = _job(
            "job.refresh", datetime(2026, 9, 16, 16, 5, tzinfo=UTC), markets=["gpw"]
        )
        europe = self._run([europe_ran], "europe", 18, 0, "Europe/Warsaw", ["gpw"])
        us = self._run([], "us", 17, 15, "America/New_York", ["us"])
        combined = combine_ingest([europe, us])
        assert europe.status == "ok"
        assert us.status == "never"
        assert combined.status == "never"
        assert [r.run_id for r in combined.runs] == ["europe", "us"]
        assert combined.schedule == "18:00 Europe/Warsaw; 17:15 America/New_York"
        assert combined.summary.startswith("EUROPE: ")

    def test_a_failed_run_is_the_headline(self) -> None:
        failed = _job(
            "job.refresh",
            datetime(2026, 9, 16, 21, 20, tzinfo=UTC),
            outcome=OUTCOME_FAILED,
            markets=["us"],
            error="boom",
        )
        ok = _job("job.refresh", datetime(2026, 9, 16, 16, 5, tzinfo=UTC), markets=["gpw"])
        combined = combine_ingest(
            [
                self._run([ok], "europe", 18, 0, "Europe/Warsaw", ["gpw"]),
                self._run([failed], "us", 17, 15, "America/New_York", ["us"]),
            ]
        )
        assert combined.status == "failed"

    def test_one_run_is_reported_as_it_always_was(self) -> None:
        only = self._run([], "europe", 18, 0, "Europe/Warsaw", ["gpw"])
        assert combine_ingest([only]) is only
        assert only.runs == []


class _BusyRefresh:
    """A refresh service stand-in, mid-run on some markets."""

    def __init__(self, run_markets: list[str], last_error: str | None = None) -> None:
        self.is_running = True
        self.run_markets = run_markets
        self.last_error = last_error


class TestHealthEndpointPerRun:
    """The running flag and the error belong to the run that covers them."""

    def _runs(self, refresh: _BusyRefresh) -> dict[str, dict]:
        from fastapi.testclient import TestClient

        from app.dependencies import get_refresh_service
        from app.main import app

        with TestClient(app) as client:
            app.dependency_overrides[get_refresh_service] = lambda: refresh
            try:
                body = client.get("/api/admin/health").json()
            finally:
                app.dependency_overrides.pop(get_refresh_service, None)
        return {run["runId"]: run for run in body["ingest"]["runs"]}

    def test_a_us_run_in_progress_is_not_shown_on_the_european_row(
        self, all_markets: None
    ) -> None:
        runs = self._runs(_BusyRefresh(["us"], last_error="US download failed"))

        assert runs["us"]["status"] == "running"
        assert runs["europe"]["status"] != "running"
        assert runs["europe"]["lastError"] is None

    def test_the_button_covers_every_run(self, all_markets: None) -> None:
        runs = self._runs(_BusyRefresh(["gpw", "us", "de", "fr", "nl", "uk"]))

        assert {run["status"] for run in runs.values()} == {"running"}

    def test_an_unknown_scope_still_counts_everywhere(self, all_markets: None) -> None:
        runs = self._runs(_BusyRefresh([]))

        assert {run["status"] for run in runs.values()} == {"running"}


def _market(market: str, newest: date | None, tracked: int, current: int) -> MarketStoredStats:
    return MarketStoredStats(
        market=market,
        latest_bar_date=newest,
        tickers_tracked=tracked,
        tickers_with_data=current if newest else 0,
        tickers_current=current,
    )


def _stats(*markets: MarketStoredStats) -> StoredDataStats:
    newest = max((m.latest_bar_date for m in markets if m.latest_bar_date), default=None)
    current = sum(m.tickers_current for m in markets)
    return StoredDataStats(
        latest_bar_date=newest,
        earliest_bar_date=date(2025, 1, 2),
        tickers_with_data=current,
        tickers_current=current,
        tickers_behind=0,
        bar_count=10_000,
        latest_snapshot_date=newest,
        markets=list(markets),
    )


class TestDataHealthPerMarket:
    TODAY = date(2026, 9, 16)

    def _evaluate(self, stats: StoredDataStats, running: bool = False):
        tracked = sum(m.tickers_tracked for m in stats.markets)
        return evaluate_data(
            stats,
            tickers_tracked=tracked,
            db_enabled=True,
            today=self.TODAY,
            refresh_running=running,
        )

    def test_us_a_session_behind_the_gpw_is_not_stale(self) -> None:
        """At 20:00 Warsaw the US run has not happened yet — nothing is wrong."""
        health = self._evaluate(
            _stats(
                _market("gpw", self.TODAY, 288, 285),
                _market("us", self.TODAY - timedelta(days=1), 518, 518),
            )
        )
        assert health.status == "ok"
        assert [m.status for m in health.markets] == ["ok", "ok"]
        assert health.tickers_current == 803

    def test_a_market_left_half_done_is_named(self) -> None:
        health = self._evaluate(
            _stats(_market("gpw", self.TODAY, 288, 288), _market("us", self.TODAY, 518, 100))
        )
        assert health.status == "stale"
        assert health.summary.startswith("US: 100 of 518")

    def test_a_market_with_nothing_stored_says_so(self) -> None:
        health = self._evaluate(
            _stats(_market("gpw", self.TODAY, 288, 288), _market("uk", None, 100, 0))
        )
        assert health.status == "empty"
        assert "UK: no stored data yet." in health.summary

    def test_partial_coverage_during_a_run_is_updating(self) -> None:
        health = self._evaluate(
            _stats(_market("gpw", self.TODAY, 288, 288), _market("us", self.TODAY, 518, 50)),
            running=True,
        )
        assert health.status == "updating"

    def test_a_single_market_keeps_the_original_wording(self) -> None:
        health = self._evaluate(_stats(_market("gpw", self.TODAY, 288, 288)))
        assert health.summary == f"288 of 288 companies are current as of {self.TODAY}."
        assert [m.market for m in health.markets] == ["gpw"]


# ── Yahoo rate limits ─────────────────────────────────────────────────────────


class TestRateLimitRetry:
    def test_a_rate_limit_is_waited_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        waits: list[float] = []
        monkeypatch.setattr(yahoo_finance_client, "_sleep", waits.append)
        attempts = {"n": 0}

        def call() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("Too Many Requests. Rate limited. Try after a while.")
            return "bars"

        assert yahoo_finance_client._with_rate_limit_retry(call, "AAPL") == "bars"
        assert waits == list(yahoo_finance_client._RATE_LIMIT_WAITS_SECONDS)

    def test_other_errors_are_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(yahoo_finance_client, "_sleep", lambda _s: None)
        calls = {"n": 0}

        def call() -> str:
            calls["n"] += 1
            raise ValueError("bad symbol")

        with pytest.raises(ValueError):
            yahoo_finance_client._with_rate_limit_retry(call, "AAPL")
        assert calls["n"] == 1

    def test_a_limit_that_does_not_lift_is_raised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(yahoo_finance_client, "_sleep", lambda _s: None)

        class YFRateLimitError(Exception):
            pass

        def call() -> str:
            raise YFRateLimitError("slow down")

        with pytest.raises(YFRateLimitError):
            yahoo_finance_client._with_rate_limit_retry(call, "AAPL")


# ── Heatmap MAX from the oldest stored close ──────────────────────────────────


class TestHeatmapMax:
    def test_max_reaches_past_the_fetch_window(self) -> None:
        repo = InMemoryQuoteRepository()
        recent = _series(40)
        # Five years ago the stock stood at 50; the window only sees 100s.
        old = _bar(date.today() - timedelta(days=5 * 365), close=50.0)
        asyncio.run(repo.upsert_quotes("aaa", [old, *recent]))
        firsts = asyncio.run(repo.get_first_closes(["aaa", "nothing"]))
        assert firsts == {"aaa": (old.date, Decimal("50.0"))}

        result = asyncio.run(
            compute_heatmap(
                companies=[_GPW_CO],
                stooq=_SeriesClient(),
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=repo,
            )
        )
        [tile] = result.items
        assert tile.change_max == 100.0

    def test_without_a_database_max_is_the_window(self) -> None:
        result = asyncio.run(
            compute_heatmap(
                companies=[_GPW_CO],
                stooq=_SeriesClient(),
                history_cache=TTLCache(),
                history_cache_ttl=60,
            )
        )
        assert result.items[0].change_max == 0.0

    def test_heatmap_and_ranking_share_one_history(self) -> None:
        history: TTLCache = TTLCache()
        asyncio.run(
            compute_heatmap(
                companies=[_GPW_CO],
                stooq=_SeriesClient(),
                history_cache=history,
                history_cache_ttl=60,
            )
        )
        from app.services.ranking_service import CONTEXT_HISTORY_DAYS

        key = f"history:aaa:{date.today() - timedelta(days=CONTEXT_HISTORY_DAYS)}:None"
        assert history.get(key) is not None


# ── Fundamentals know their reporting currency ────────────────────────────────


class TestFinancialCurrency:
    def test_yahoo_financial_currency_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import yfinance

        class _Ticker:
            def __init__(self, _symbol: str) -> None:
                self.info = {"marketCap": 259_000_000_000, "financialCurrency": "USD"}

        monkeypatch.setattr(yfinance, "Ticker", _Ticker)
        metrics = asyncio.run(yahoo_finance_client.YahooFinanceClient().get_fundamentals("hsba.l"))
        assert metrics.financial_currency == "USD"
        assert metrics.market_cap == 259_000_000_000
