"""Tests for the volume-surge scanner (RVOL math) and endpoint."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository, merge_report_dates
from app.dependencies import (
    get_gpw_company_service,
    get_stooq_client,
    history_cache,
    ranking_cache,
)
from app.main import app
from app.models import FinancialMetrics, GpwCompany, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError
from app.services.volume_surge_service import (
    compute_surge_context,
    compute_surge_metrics,
    compute_volume_surge,
    report_in_window,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _quote(d: date, close: float, volume: int) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(round(close * 1.02, 2))),
        low=Decimal(str(round(close * 0.98, 2))),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(
    volumes: list[int],
    closes: list[float] | None = None,
    end: date | None = None,
) -> list[StooqDailyQuote]:
    """One daily bar per volume entry, ending at ``end`` (default today)."""
    if end is None:
        end = date.today()
    if closes is None:
        closes = [100.0] * len(volumes)
    days = len(volumes)
    return [
        _quote(end - timedelta(days=days - 1 - i), closes[i], volumes[i])
        for i in range(days)
    ]


def _surge_series(days: int = 60, base_vol: int = 100_000, spike: int = 300_000):
    """Flat 100k-share volume with the last 3 sessions spiking to 300k."""
    volumes = [base_vol] * (days - 3) + [spike] * 3
    return _series(volumes)


def _company(
    ticker: str = "tst",
    name: str = "Test SA",
    sector: str | None = "Banks",
    market_cap: int | None = 500_000_000,
) -> GpwCompany:
    return GpwCompany(ticker=ticker, name=name, sector=sector, market_cap=market_cap)


class _FakeStooqClient:
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        self._quotes = quotes

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._quotes


class _PerTickerStooqClient:
    """Fake client returning a different series per ticker."""

    def __init__(self, by_ticker: dict[str, list[StooqDailyQuote]]) -> None:
        self._by_ticker = by_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._by_ticker.get(ticker, [])


class _FlakyStooqClient(_FakeStooqClient):
    """Fake client that fails for one specific ticker."""

    def __init__(self, quotes: list[StooqDailyQuote], bad_ticker: str) -> None:
        super().__init__(quotes)
        self._bad_ticker = bad_ticker

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        if ticker == self._bad_ticker:
            raise StooqAccessError("stooq unavailable")
        return self._quotes


class _CountingStooqClient(_FakeStooqClient):
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        super().__init__(quotes)
        self.calls = 0

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.calls += 1
        return self._quotes


class _FakeCompanyService:
    def __init__(self, companies: list[GpwCompany]) -> None:
        self._companies = companies

    def get_companies(self, market: str = "gpw") -> list[GpwCompany]:
        return self._companies if market == "gpw" else []


@pytest.fixture(autouse=True)
def _clear_caches_and_overrides():
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()


# ── compute_surge_metrics ─────────────────────────────────────────────────────


class TestComputeSurgeMetrics:
    def test_flat_volume_has_ratio_one(self) -> None:
        m = compute_surge_metrics(_series([100_000] * 30))
        assert m is not None
        assert m.volume_ratio == 1.0
        assert m.last_day_ratio == 1.0
        assert m.days_above_baseline == 0

    def test_three_day_spike_triples_the_ratio(self) -> None:
        m = compute_surge_metrics(_surge_series())
        assert m is not None
        assert m.volume_ratio == 3.0
        assert m.last_day_ratio == 3.0
        assert m.days_above_baseline == 3
        assert m.recent_avg_volume == 300_000
        assert m.baseline_avg_volume == 100_000

    def test_single_spike_day_dilutes_multi_day_ratio(self) -> None:
        # Only the last day spikes: recent avg = (100k+100k+400k)/3 = 200k.
        volumes = [100_000] * 29 + [400_000]
        m = compute_surge_metrics(_series(volumes))
        assert m is not None
        assert m.volume_ratio == 2.0
        assert m.last_day_ratio == 4.0
        assert m.days_above_baseline == 1

    def test_baseline_excludes_recent_window(self) -> None:
        # The spike must not inflate its own baseline: with 20 baseline
        # sessions all at 100k, the ratio is exactly 3.0 regardless of how
        # large the recent volumes are.
        volumes = [100_000] * 23 + [300_000] * 3
        m = compute_surge_metrics(_series(volumes), recent_days=3, baseline_days=20)
        assert m is not None
        assert m.baseline_avg_volume == 100_000
        assert m.volume_ratio == 3.0

    def test_price_change_measured_over_recent_window(self) -> None:
        # Bars older than the entry bar sit at 90, so an off-by-one that
        # anchors the change on anything but the close immediately before the
        # window would not produce +10 %.
        # Close before the window = 100, last close = 110 → +10 %.
        closes = [90.0] * 26 + [100.0, 104.0, 108.0, 110.0]
        m = compute_surge_metrics(_series([100_000] * 30, closes=closes))
        assert m is not None
        assert m.price_change_pct == 10.0

    def test_history_exactly_window_length(self) -> None:
        # 23 bars = recent 3 + baseline 20 exactly: still scorable, and the
        # entry close is the last baseline bar (no IndexError at the boundary).
        volumes = [100_000] * 20 + [300_000] * 3
        closes = [100.0] * 20 + [104.0, 108.0, 110.0]
        m = compute_surge_metrics(_series(volumes, closes=closes))
        assert m is not None
        assert m.volume_ratio == 3.0
        assert m.price_change_pct == 10.0

    def test_insufficient_history_returns_none(self) -> None:
        assert compute_surge_metrics(_series([100_000] * 10)) is None

    def test_zero_baseline_volume_returns_none(self) -> None:
        # A stock suspended during the whole baseline window can't be scored.
        volumes = [0] * 27 + [50_000] * 3
        assert compute_surge_metrics(_series(volumes)) is None

    def test_custom_windows(self) -> None:
        # recent=2, baseline=10: last two sessions at 500k vs 100k baseline.
        volumes = [100_000] * 10 + [500_000] * 2
        m = compute_surge_metrics(_series(volumes), recent_days=2, baseline_days=10)
        assert m is not None
        assert m.volume_ratio == 5.0

    def test_one_huge_baseline_day_does_not_hide_a_surge(self) -> None:
        # The reason the baseline is a median: one report day at 20× inside
        # the reference period lifted its MEAN to 195k, so a genuine doubling
        # read as 1.03× — "normal" — for the next four weeks. The median is
        # the typical session, 100k, and the doubling reads as 2×.
        volumes = [100_000] * 10 + [2_000_000] + [100_000] * 9 + [200_000] * 3
        m = compute_surge_metrics(_series(volumes))
        assert m is not None
        assert m.baseline_avg_volume == 100_000
        assert m.volume_ratio == 2.0
        assert m.last_day_ratio == 2.0
        assert m.days_above_baseline == 3

    def test_a_typical_session_reads_one(self) -> None:
        # A skewed but ordinary baseline: most sessions quiet, a few busy.
        # Measured against the mean (155k) a typical 100k session read 0.65×;
        # against the median it reads 1.0×, as the page says "normal" does.
        volumes = [100_000] * 15 + [320_000] * 5 + [100_000] * 3
        m = compute_surge_metrics(_series(volumes))
        assert m is not None
        assert m.volume_ratio == 1.0

    def test_even_baseline_takes_the_middle_pair(self) -> None:
        # 20 baseline sessions: the median is the mean of the 10th and 11th.
        volumes = [100_000] * 10 + [200_000] * 10 + [450_000] * 3
        m = compute_surge_metrics(_series(volumes))
        assert m is not None
        assert m.baseline_avg_volume == 150_000
        assert m.volume_ratio == 3.0

    def test_mostly_halted_baseline_returns_none(self) -> None:
        # More than half the reference sessions untraded: the typical session
        # is zero, and a ratio against zero means nothing.
        volumes = [0] * 11 + [100_000] * 9 + [300_000] * 3
        assert compute_surge_metrics(_series(volumes)) is None


# ── compute_surge_context ─────────────────────────────────────────────────────


def _bar(
    d: date, low: float, high: float, close: float, volume: int
) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _context_series(
    window: list[tuple[float, float, float, int]],
    baseline_days: int = 20,
) -> list[StooqDailyQuote]:
    """``baseline_days`` bars ranging 99–101 closing 100 on 100k, then ``window``.

    Each window entry is (low, high, close, volume).
    """
    start = date(2026, 1, 1)
    bars = [
        _bar(start + timedelta(days=i), 99.0, 101.0, 100.0, 100_000)
        for i in range(baseline_days)
    ]
    for j, (low, high, close, volume) in enumerate(window):
        bars.append(_bar(start + timedelta(days=baseline_days + j), low, high, close, volume))
    return bars


class TestComputeSurgeContext:
    def test_peak_session_is_read_in_vsa_terms(self) -> None:
        # The middle session carried the surge: 5× volume on a 6-point range
        # (3× the baseline's 2-point average), closing near its high, up 4%.
        bars = _context_series(
            [
                (99.0, 101.0, 100.0, 150_000),
                (98.0, 104.0, 104.0 - 0.6, 500_000),
                (102.0, 104.0, 103.0, 200_000),
            ]
        )
        c = compute_surge_context(bars)
        assert c is not None
        assert c.surge_start == bars[-3].date
        assert c.peak_date == bars[-2].date
        assert c.peak_volume_ratio == 5.0
        assert c.peak_change_pct == 3.4
        assert c.peak_spread_ratio == 3.0
        assert c.peak_close_position == 0.9
        assert c.breaks_high is True
        assert c.breaks_low is True

    def test_down_bar_closing_on_its_low(self) -> None:
        bars = _context_series(
            [
                (99.0, 101.0, 100.0, 100_000),
                (99.0, 101.0, 100.0, 100_000),
                (95.0, 100.0, 95.0, 400_000),
            ]
        )
        c = compute_surge_context(bars)
        assert c is not None
        assert c.peak_date == bars[-1].date
        assert c.peak_change_pct == -5.0
        assert c.peak_close_position == 0.0
        assert c.breaks_high is False
        assert c.breaks_low is True

    def test_surge_inside_the_range_breaks_nothing(self) -> None:
        bars = _context_series([(99.5, 100.5, 100.0, 300_000)] * 3)
        c = compute_surge_context(bars)
        assert c is not None
        assert c.breaks_high is False
        assert c.breaks_low is False
        assert c.peak_spread_ratio == 0.5

    def test_tie_goes_to_the_latest_session(self) -> None:
        bars = _context_series([(99.0, 101.0, 100.0, 300_000)] * 3)
        c = compute_surge_context(bars)
        assert c is not None
        assert c.peak_date == bars[-1].date

    def test_zero_range_peak_has_no_close_position(self) -> None:
        bars = _context_series(
            [(99.0, 101.0, 100.0, 100_000)] * 2 + [(100.0, 100.0, 100.0, 400_000)]
        )
        c = compute_surge_context(bars)
        assert c is not None
        assert c.peak_close_position is None
        assert c.peak_spread_ratio == 0.0

    def test_frozen_baseline_has_no_spread_ratio(self) -> None:
        # A baseline without any range (a suspension that still printed
        # volume) gives no reference to call a spread wide or narrow against.
        start = date(2026, 1, 1)
        bars = [
            _bar(start + timedelta(days=i), 100.0, 100.0, 100.0, 100_000)
            for i in range(20)
        ] + [
            _bar(start + timedelta(days=20 + j), 99.0, 103.0, 102.0, 300_000)
            for j in range(3)
        ]
        c = compute_surge_context(bars)
        assert c is not None
        assert c.peak_spread_ratio is None

    def test_same_none_cases_as_the_metrics(self) -> None:
        assert compute_surge_context(_series([100_000] * 10)) is None
        assert compute_surge_context(_series([0] * 27 + [50_000] * 3)) is None
        assert compute_surge_context(_series([100_000] * 30), recent_days=0) is None


# ── report_in_window ──────────────────────────────────────────────────────────


class TestReportInWindow:
    # Sessions Mon 14 – Fri 18 September 2026; the surge window is the last
    # three (Wed–Fri), so the session before it is Tuesday the 15th.
    BARS = [
        _quote(date(2026, 9, d), 100.0, 100_000) for d in (14, 15, 16, 17, 18)
    ]

    def test_report_inside_the_window(self) -> None:
        assert report_in_window([date(2026, 9, 17)], self.BARS) == date(2026, 9, 17)

    def test_report_after_the_close_before_the_window(self) -> None:
        # Published Tuesday evening, traded Wednesday — the window's first day.
        assert report_in_window([date(2026, 9, 15)], self.BARS) == date(2026, 9, 15)

    def test_older_report_is_not_the_surge(self) -> None:
        assert report_in_window([date(2026, 9, 14)], self.BARS) is None

    def test_report_after_the_last_session_has_not_traded(self) -> None:
        assert report_in_window([date(2026, 9, 21)], self.BARS) is None

    def test_latest_of_several_and_none_ignored(self) -> None:
        dates = [None, date(2026, 9, 16), date(2026, 9, 18), date(2026, 8, 1)]
        assert report_in_window(dates, self.BARS) == date(2026, 9, 18)

    def test_window_follows_recent_days(self) -> None:
        # One-day window: only Thursday (the session before) and Friday count.
        assert report_in_window([date(2026, 9, 16)], self.BARS, 1) is None
        assert report_in_window([date(2026, 9, 17)], self.BARS, 1) == date(2026, 9, 17)

    def test_nothing_known(self) -> None:
        assert report_in_window([], self.BARS) is None
        assert report_in_window([date(2026, 9, 17)], []) is None


# ── Report dates through the scan ─────────────────────────────────────────────


class _NoReportsRepo(InMemoryQuoteRepository):
    async def get_report_dates(self, tickers):
        raise RuntimeError("fundamentals table unreadable")


class TestScanReportFlag:
    def _scan(self, repo: InMemoryQuoteRepository) -> object:
        return asyncio.run(
            compute_volume_surge(
                companies=[_company()],
                stooq=_FakeStooqClient(_surge_series()),
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=repo,
            )
        )

    def test_report_in_the_window_is_flagged(self) -> None:
        repo = InMemoryQuoteRepository()
        asyncio.run(
            repo.upsert_fundamentals(
                "tst",
                FinancialMetrics(
                    last_report_date=date.today() - timedelta(days=90),
                    next_report_date=date.today() - timedelta(days=1),
                ),
            )
        )
        resp = self._scan(repo)
        assert [i.report_date for i in resp.items] == [date.today() - timedelta(days=1)]

    def test_no_stored_report_leaves_it_empty(self) -> None:
        resp = self._scan(InMemoryQuoteRepository())
        assert len(resp.items) == 1
        assert resp.items[0].report_date is None

    def test_unreadable_report_dates_do_not_break_the_scan(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR, logger="app.services.volume_surge_service"):
            resp = self._scan(_NoReportsRepo())
        assert len(resp.items) == 1
        assert resp.items[0].report_date is None
        assert any("report dates" in r.getMessage() for r in caplog.records)


class TestReportDatesMerge:
    """A weekly fetch merges into the stored report dates, never overwrites."""

    TODAY = date(2026, 11, 23)  # the Monday after KGHM's Wednesday report

    def test_a_passed_next_date_becomes_the_last_one(self) -> None:
        # KGHM-style info names only the upcoming report. Stored on the
        # previous Monday: next = Wed 18.11. This Monday's fetch says
        # next = March, nothing about the past — the Wednesday must survive,
        # because its surge is what the scan shows this evening.
        assert merge_report_dates(
            date(2026, 8, 20), date(2026, 11, 18), None, date(2027, 3, 12), self.TODAY
        ) == (date(2026, 11, 18), date(2027, 3, 12))

    def test_a_fetch_without_dates_keeps_what_is_known(self) -> None:
        assert merge_report_dates(
            date(2026, 8, 13), date(2026, 12, 1), None, None, self.TODAY
        ) == (date(2026, 8, 13), date(2026, 12, 1))

    def test_a_new_date_replaces_an_upcoming_estimate(self) -> None:
        # The estimate 01.12 is still ahead, so it is replaced, not kept.
        assert merge_report_dates(
            date(2026, 8, 13), date(2026, 12, 1), None, date(2026, 12, 3), self.TODAY
        ) == (date(2026, 8, 13), date(2026, 12, 3))

    def test_the_latest_past_date_wins(self) -> None:
        assert merge_report_dates(
            date(2026, 8, 13), date(2026, 11, 5), date(2026, 11, 20), None, self.TODAY
        ) == (date(2026, 11, 20), None)

    def test_first_fetch(self) -> None:
        assert merge_report_dates(None, None, None, None, self.TODAY) == (None, None)

    def test_in_memory_repository_uses_the_same_rule(self) -> None:
        today = date.today()
        repo = InMemoryQuoteRepository()
        asyncio.run(
            repo.upsert_fundamentals(
                "kgh",
                FinancialMetrics(
                    last_report_date=today - timedelta(days=90),
                    next_report_date=today - timedelta(days=2),
                ),
            )
        )
        asyncio.run(
            repo.upsert_fundamentals(
                "kgh", FinancialMetrics(next_report_date=today + timedelta(days=90))
            )
        )
        assert asyncio.run(repo.get_report_dates(["kgh", "pko"])) == {
            "kgh": [today - timedelta(days=2), today + timedelta(days=90)]
        }


# ── GET /api/stocks/volume-surge ──────────────────────────────────────────────


class TestGetVolumeSurge:
    def test_surging_stock_returned_with_expected_fields(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_surge_series()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/volume-surge")
        assert resp.status_code == 200
        body = resp.json()
        assert body["asOf"] == date.today().isoformat()
        assert body["recentDays"] == 3
        assert body["baselineDays"] == 20
        assert body["minRatio"] == 1.5
        assert body["scannedCount"] == 1
        assert len(body["items"]) == 1

        item = body["items"][0]
        for field in (
            "ticker", "name", "sector", "lastPrice",
            "recentAvgVolume", "baselineAvgVolume",
            "volumeRatio", "lastDayRatio", "daysAboveBaseline",
            "priceChangePct", "currentRating", "lastSignal",
            "daysSinceSignal", "signalInWindow", "surgeStart",
            "peakDate", "peakVolumeRatio", "peakChangePct",
            "peakSpreadRatio", "peakClosePosition",
            "breaksHigh", "breaksLow", "reportDate",
        ):
            assert field in item, f"missing field: {field}"
        assert item["ticker"] == "TST"
        assert item["volumeRatio"] == 3.0
        assert 0 <= item["currentRating"] <= 100
        # _surge_series: three identical 300k sessions ending today.
        assert item["surgeStart"] == (date.today() - timedelta(days=2)).isoformat()
        assert item["peakDate"] == date.today().isoformat()
        assert item["peakVolumeRatio"] == 3.0
        assert item["peakClosePosition"] == 0.5
        assert item["breaksHigh"] is False
        assert item["reportDate"] is None
        assert isinstance(item["daysSinceSignal"], int)

    def test_normal_volume_stock_excluded_but_counted(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_series([200_000] * 60)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert body["items"] == []
        assert body["scannedCount"] == 1

    def test_items_sorted_by_ratio_descending(self) -> None:
        strong = [100_000] * 57 + [500_000] * 3   # ratio 5.0
        mild = [100_000] * 57 + [200_000] * 3     # ratio 2.0
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company("aaa", "A SA"), _company("bbb", "B SA")])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            {"aaa": _series(mild), "bbb": _series(strong)}
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA"]
        ratios = [i["volumeRatio"] for i in body["items"]]
        assert ratios == sorted(ratios, reverse=True)

    def test_min_ratio_parameter_filters(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_surge_series()  # ratio 3.0
        )
        with TestClient(app) as client:
            below = client.get("/api/stocks/volume-surge", params={"minRatio": 4.0})
            above = client.get("/api/stocks/volume-surge", params={"minRatio": 2.0})
        assert below.json()["items"] == []
        assert len(above.json()["items"]) == 1

    def test_window_parameters_change_the_result(self) -> None:
        # Volume has been elevated for 10 sessions; with recentDays=1 vs a
        # baseline that still catches the pre-surge sessions the ratio drops.
        volumes = [100_000] * 50 + [300_000] * 10
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_series(volumes)
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/volume-surge",
                params={"recentDays": 10, "baselineDays": 30},
            )
        body = resp.json()
        assert body["recentDays"] == 10
        assert body["baselineDays"] == 30
        assert len(body["items"]) == 1
        assert body["items"][0]["volumeRatio"] == 3.0
        assert body["items"][0]["daysAboveBaseline"] == 10

    def test_invalid_parameters_rejected(self) -> None:
        with TestClient(app) as client:
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"recentDays": 0}
                ).status_code
                == 422
            )
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"baselineDays": 5}
                ).status_code
                == 422
            )
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"minRatio": 0.5}
                ).status_code
                == 422
            )
            assert (
                client.get(
                    "/api/stocks/volume-surge", params={"settings": "{not json"}
                ).status_code
                == 400
            )

    def test_illiquid_stock_excluded(self) -> None:
        # 100 shares/day at 100 PLN = 10,000 PLN median turnover < 100k floor.
        volumes = [100] * 57 + [300] * 3
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_series(volumes)
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert body["items"] == []
        assert body["scannedCount"] == 0

    def test_listing_lagging_the_market_excluded(self) -> None:
        # A suspended stock's last "surge" is months-old news: when its last
        # bar lags the newest session across the scanned tickers by 15 days,
        # the recency pre-filter must drop it even though its own RVOL ratio
        # clears the screen.
        volumes = [100_000] * 57 + [300_000] * 3
        fresh = _series(volumes)
        stale = _series(volumes, end=date.today() - timedelta(days=15))
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [_company("frs", "Fresh SA"), _company("stl", "Stale SA")]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            {"frs": fresh, "stl": stale}
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert [i["ticker"] for i in body["items"]] == ["FRS"]
        assert body["totalCount"] == 1
        assert body["asOf"] == date.today().isoformat()

    def test_market_cap_below_floor_excluded(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [
                    _company("big", market_cap=500_000_000),
                    _company("sml", market_cap=50_000_000),
                ]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_surge_series()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/volume-surge").json()
        assert [i["ticker"] for i in body["items"]] == ["BIG"]

    def test_sorting_and_pagination(self) -> None:
        # Three surging stocks with distinct ratios (5.0 / 3.0 / 2.0) and
        # distinct price moves so both sort orders are observable.
        def series(spike: int, last_close: float) -> list[StooqDailyQuote]:
            volumes = [100_000] * 57 + [spike] * 3
            closes = [100.0] * 59 + [last_close]
            return _series(volumes, closes=closes)

        by_ticker = {
            "aaa": series(300_000, 104.0),  # ratio 3.0, +4 %
            "bbb": series(500_000, 98.0),   # ratio 5.0, -2 %
            "ccc": series(200_000, 110.0),  # ratio 2.0, +10 %
        }
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [_company(t, f"{t.upper()} SA") for t in by_ticker]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            by_ticker
        )
        with TestClient(app) as client:
            # Default: volumeRatio descending, one page with all rows.
            body = client.get("/api/stocks/volume-surge").json()
            assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA", "CCC"]
            assert body["totalCount"] == 3

            # Sort by price move ascending.
            body = client.get(
                "/api/stocks/volume-surge",
                params={"sortBy": "priceChangePct", "sortDir": "asc"},
            ).json()
            assert [i["ticker"] for i in body["items"]] == ["BBB", "AAA", "CCC"]

            # Sort by ticker ascending.
            body = client.get(
                "/api/stocks/volume-surge",
                params={"sortBy": "ticker", "sortDir": "asc"},
            ).json()
            assert [i["ticker"] for i in body["items"]] == ["AAA", "BBB", "CCC"]

            # Pagination: 2 rows per page → page 1 has 2, page 2 has 1;
            # totalCount always reports all matching rows.
            page1 = client.get(
                "/api/stocks/volume-surge", params={"pageSize": 2, "page": 1}
            ).json()
            page2 = client.get(
                "/api/stocks/volume-surge", params={"pageSize": 2, "page": 2}
            ).json()
            assert [i["ticker"] for i in page1["items"]] == ["BBB", "AAA"]
            assert [i["ticker"] for i in page2["items"]] == ["CCC"]
            assert page1["totalCount"] == 3
            assert page2["totalCount"] == 3

            # Two sort levels: all three share a sector, so the tie-break —
            # biggest price move first — decides the whole order. It matches
            # none of the single-column orders above, so the second level is
            # demonstrably doing the work.
            body = client.get(
                "/api/stocks/volume-surge",
                params={"sortBy": "sector,priceChangePct", "sortDir": "asc,desc"},
            ).json()
            assert [i["ticker"] for i in body["items"]] == ["CCC", "AAA", "BBB"]

    def test_invalid_sort_by_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/volume-surge", params={"sortBy": "nonsense"}
            )
        assert resp.status_code == 400

    def test_invalid_sort_dir_rejected(self) -> None:
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/volume-surge",
                params={"sortBy": "ticker", "sortDir": "sideways"},
            )
        assert resp.status_code == 400

    def test_one_failing_ticker_does_not_break_the_scan(self) -> None:
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company("bad", "Bad SA"), _company("good", "Good SA")])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FlakyStooqClient(
            quotes=_surge_series(), bad_ticker="bad"
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/volume-surge")
        assert resp.status_code == 200
        body = resp.json()
        assert [i["ticker"] for i in body["items"]] == ["GOOD"]
        assert body["scannedCount"] == 1  # the failed ticker was never scored

    def test_second_request_served_from_response_cache(self) -> None:
        stooq = _CountingStooqClient(quotes=_surge_series())
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        with TestClient(app) as client:
            client.get("/api/stocks/volume-surge")
            first_calls = stooq.calls
            # Clearing the per-ticker history cache proves the second hit is
            # served by the response-level cache, not the shared history cache.
            history_cache.clear()
            client.get("/api/stocks/volume-surge")
        assert first_calls > 0
        assert stooq.calls == first_calls

    def test_different_settings_recompute_and_cache_separately(self) -> None:
        stooq = _CountingStooqClient(quotes=_surge_series())
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        custom = '{"sos": {"volMult": 3.0}}'
        with TestClient(app) as client:
            client.get("/api/stocks/volume-surge")
            # Cold history for the custom-settings request so the recompute
            # is observable through the fetch counter.
            history_cache.clear()
            client.get("/api/stocks/volume-surge", params={"settings": custom})
            calls_after_custom = stooq.calls
            client.get("/api/stocks/volume-surge", params={"settings": custom})
        assert calls_after_custom > 1  # custom settings did recompute
        assert stooq.calls == calls_after_custom  # …and were cached separately

    def test_different_parameters_cached_separately(self) -> None:
        stooq = _CountingStooqClient(quotes=_surge_series())
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: stooq
        with TestClient(app) as client:
            a = client.get("/api/stocks/volume-surge").json()
            b = client.get(
                "/api/stocks/volume-surge", params={"minRatio": 2.5}
            ).json()
        assert a["minRatio"] == 1.5
        assert b["minRatio"] == 2.5

    def test_rating_matches_ranking_for_same_data(self) -> None:
        # The surge list shows the same VSA rating the ranking page shows.
        closes = [100 + (i % 7) * 2.5 - (i % 3) for i in range(60)]
        volumes = [200_000 + i * 1_000 for i in range(57)] + [900_000] * 3
        quotes = _series(volumes, closes=closes)
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=quotes
        )
        with TestClient(app) as client:
            surge = client.get("/api/stocks/volume-surge").json()
            ranking = client.get("/api/stocks/ranking").json()
        assert len(surge["items"]) == 1
        assert len(ranking) == 1
        assert surge["items"][0]["currentRating"] == ranking[0]["currentRating"]

    def test_page_past_the_end_returns_empty_page(self) -> None:
        # Deep-linking a page beyond the result set (e.g. after the cached
        # scan shrank) must return an empty page with the true totalCount,
        # not an error.
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService([_company()])
        )
        app.dependency_overrides[get_stooq_client] = lambda: _FakeStooqClient(
            quotes=_surge_series()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/volume-surge", params={"page": 5, "pageSize": 2}
            ).json()
        assert body["items"] == []
        assert body["totalCount"] == 1

    def test_sort_by_sector_handles_missing_sector(self) -> None:
        # `sector` is Optional — sorting by it must not compare None with str.
        # None sorts as an empty string, i.e. first ascending.
        volumes = [100_000] * 57 + [300_000] * 3
        series = _series(volumes)
        app.dependency_overrides[get_gpw_company_service] = lambda: (
            _FakeCompanyService(
                [
                    _company("bnk", "Bank SA", sector="Banks"),
                    _company("non", "NoSector SA", sector=None),
                ]
            )
        )
        app.dependency_overrides[get_stooq_client] = lambda: _PerTickerStooqClient(
            {"bnk": series, "non": series}
        )
        with TestClient(app) as client:
            resp = client.get(
                "/api/stocks/volume-surge",
                params={"sortBy": "sector", "sortDir": "asc"},
            )
        assert resp.status_code == 200
        assert [i["ticker"] for i in resp.json()["items"]] == ["NON", "BNK"]


# ── Failure visibility ────────────────────────────────────────────────────────


class _ExplodingRepo:
    """Repository stub whose every query raises (simulates the DB dying)."""

    async def get_quotes(self, ticker, from_date=None, to_date=None):
        raise RuntimeError("db down")


class TestScanFailureLogging:
    def test_db_failure_is_logged_not_silent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # A repo that raises out of every scan task must not crash the scan —
        # and, crucially, must not degrade it *silently*: an empty result with
        # no log line would look like a quiet market instead of an outage.
        async def run() -> object:
            return await compute_volume_surge(
                companies=[_company()],
                stooq=_FakeStooqClient(_surge_series()),
                history_cache=TTLCache(),
                history_cache_ttl=60,
                repo=_ExplodingRepo(),
            )

        with caplog.at_level(
            logging.ERROR, logger="app.services.volume_surge_service"
        ):
            resp = asyncio.run(run())
        assert resp.items == []
        assert resp.scanned_count == 0
        assert any(
            "tst" in record.getMessage() and "db down" in record.getMessage()
            for record in caplog.records
        )
