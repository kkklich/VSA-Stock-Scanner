"""Tests for the hourly live prices (app/services/live_prices.py).

No network: Yahoo is a fake, and every clock is pinned. Pinned here:

* when a market counts as trading (``Market.session_in_progress``);
* the session download keeps today's unfinished bar APART from the finished
  ones, with the previous close and the time of the last trade;
* a run downloads only the markets trading at that moment, skips a market
  whose largest stocks have no bar for today (a holiday) and one whose largest
  stocks cannot be downloaded at all, and records what it did;
* a live price is shown only while it is newer than the finished data under
  it — and never changes a rating;
* the endpoints lay it over the ranking, the heatmap and the stock page, and
  the refresh status says when it last changed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest
import yfinance
from fastapi.testclient import TestClient

from app.dependencies import (
    get_gpw_company_service,
    get_live_prices,
    get_stooq_client,
    history_cache,
    ranking_cache,
)
from app.jobs.daily_ingest import build_scheduler
from app.main import app
from app.markets import GPW, UNITED_KINGDOM, US
from app.models import GpwCompany, HeatmapItem, LivePrice, StockRankingItem, StooqDailyQuote
from app.services import yahoo_finance_client
from app.services.action_log import (
    OUTCOME_FAILED,
    OUTCOME_FINISHED,
    OUTCOME_STARTED,
    ActionLogService,
)
from app.services.exceptions import StooqAccessError
from app.services.live_prices import (
    ACTION,
    JOB_ID,
    LivePriceService,
    LiveRunStats,
    cron_minutes,
    live_price_from,
    overlay_row,
    overlay_tile,
    run_outcome,
)
from app.services.refresh_service import RefreshService
from app.services.yahoo_finance_client import SessionBar, SessionQuote, YahooFinanceClient

# 12:00 in Warsaw on Thursday 24 September 2026 — the GPW mid-session, New York
# at 06:00 (closed).
_GPW_NOON = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
_TODAY = date(2026, 9, 24)
_YESTERDAY = date(2026, 9, 23)


def _warsaw(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=GPW.tz)


def _new_york(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=US.tz)


# ── When is a market trading? ─────────────────────────────────────────────────


class TestSessionInProgress:
    @pytest.mark.parametrize(
        ("hour", "minute", "expected"),
        [
            (8, 59, False),  # before the bell
            (9, 0, False),  # the bell itself: nothing has printed yet
            (9, 1, True),
            (12, 0, True),
            (17, 5, True),  # closing auction just over, not yet settled
            (17, 19, True),
            (17, 20, False),  # 17:05 + 15 min: the bar is final
            (22, 0, False),
        ],
    )
    def test_the_gpw_trades_from_nine_until_its_bar_is_final(
        self, hour: int, minute: int, expected: bool
    ) -> None:
        assert GPW.session_in_progress(_warsaw(_TODAY, hour, minute)) is expected

    def test_new_york_on_its_own_clock(self) -> None:
        assert not US.session_in_progress(_new_york(_TODAY, 9, 30))
        assert US.session_in_progress(_new_york(_TODAY, 10, 0))
        assert US.session_in_progress(_new_york(_TODAY, 16, 14))
        assert not US.session_in_progress(_new_york(_TODAY, 16, 15))
        # Mid-day in Warsaw is before the open in New York.
        assert not US.session_in_progress(_GPW_NOON)

    def test_london_opens_at_eight_its_own_time(self) -> None:
        # 08:30 London is 09:30 Warsaw: both are trading.
        london_open = datetime(2026, 9, 24, 8, 30, tzinfo=UNITED_KINGDOM.tz)
        assert UNITED_KINGDOM.session_in_progress(london_open)
        assert GPW.session_in_progress(london_open)
        # 07:59 London is before its bell (and 08:59 Warsaw, before the GPW's).
        before = datetime(2026, 9, 24, 7, 59, tzinfo=UNITED_KINGDOM.tz)
        assert not UNITED_KINGDOM.session_in_progress(before)
        assert not GPW.session_in_progress(before)

    def test_weekends_never_trade(self) -> None:
        saturday = date(2026, 9, 26)
        assert not GPW.session_in_progress(_warsaw(saturday, 12))
        assert not US.session_in_progress(_new_york(saturday, 12))

    def test_local_date_is_the_exchanges_calendar(self) -> None:
        # 23:30 in Warsaw is still the same day in New York.
        late = _warsaw(_TODAY, 23, 30)
        assert GPW.local_date(late) == _TODAY
        assert US.local_date(late) == _TODAY
        # 01:30 in Warsaw is the next day there, still the day before in New York.
        after_midnight = _warsaw(date(2026, 9, 25), 1, 30)
        assert GPW.local_date(after_midnight) == date(2026, 9, 25)
        assert US.local_date(after_midnight) == _TODAY


class TestCronMinutes:
    def test_hourly_is_the_full_hour(self) -> None:
        assert cron_minutes(60) == "0"

    def test_a_divisor_of_an_hour(self) -> None:
        assert cron_minutes(30) == "*/30"
        assert cron_minutes(15) == "*/15"

    def test_anything_else_falls_back_to_hourly(self) -> None:
        assert cron_minutes(45) == "0"
        assert cron_minutes(0) == "0"


# ── The session download (Yahoo client) ───────────────────────────────────────


class _FakeHistoryMeta:
    def __init__(self, meta: dict | None) -> None:
        self._history_metadata = meta


class _FakeTicker:
    """Stands in for ``yfinance.Ticker``, with the metadata where yfinance keeps it."""

    requested: list[str] = []
    frame: pd.DataFrame | None = None
    meta: dict | None = None

    def __init__(self, symbol: str) -> None:
        _FakeTicker.requested.append(symbol)
        self._price_history = None

    def history(self, **_kwargs) -> pd.DataFrame | None:
        self._price_history = _FakeHistoryMeta(_FakeTicker.meta)
        return None if _FakeTicker.frame is None else _FakeTicker.frame.copy()


@pytest.fixture
def fake_yahoo(monkeypatch: pytest.MonkeyPatch) -> type[_FakeTicker]:
    _FakeTicker.requested = []
    _FakeTicker.frame = None
    _FakeTicker.meta = None
    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    return _FakeTicker


def _frame(rows: list[tuple[str, float, float]], zone: str) -> pd.DataFrame:
    """Daily bars ``(day, close, volume)`` stamped at midnight in the exchange zone."""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d, _, _ in rows]).tz_localize(zone)
    return pd.DataFrame(
        {
            "Open": [c - 1.0 for _, c, _ in rows],
            "High": [c + 2.0 for _, c, _ in rows],
            "Low": [c - 2.0 for _, c, _ in rows],
            "Close": [c for _, c, _ in rows],
            "Volume": [v for _, _, v in rows],
        },
        index=index,
    )


def _session(ticker: str) -> SessionQuote:
    return asyncio.run(YahooFinanceClient().get_session_quote(ticker))


class TestGetSessionQuote:
    def test_todays_bar_travels_apart_from_the_finished_ones(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(yahoo_finance_client, "_utcnow", lambda: _GPW_NOON)
        fake_yahoo.frame = _frame(
            [("2026-09-22", 98.0, 500_000), ("2026-09-23", 100.0, 520_000),
             ("2026-09-24", 103.0, 150_000)],
            "Europe/Warsaw",
        )
        traded = datetime(2026, 9, 24, 9, 44, tzinfo=UTC)
        fake_yahoo.meta = {"regularMarketTime": int(traded.timestamp())}
        quote = _session("kgh")
        assert fake_yahoo.requested == ["KGH.WA"]
        assert quote.today == _TODAY
        assert quote.final is False
        assert quote.bar == SessionBar(
            open=102.0, high=105.0, low=101.0, close=103.0, volume=150_000
        )
        assert quote.previous_date == _YESTERDAY
        assert quote.previous_close == 100.0
        assert quote.last_trade_at == datetime(2026, 9, 24, 9, 44, tzinfo=UTC)

    def test_after_the_close_the_bar_is_final(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            yahoo_finance_client, "_utcnow", lambda: _warsaw(_TODAY, 17, 30).astimezone(UTC)
        )
        fake_yahoo.frame = _frame(
            [("2026-09-23", 100.0, 520_000), ("2026-09-24", 103.0, 600_000)], "Europe/Warsaw"
        )
        assert _session("kgh").final is True

    def test_no_bar_for_today_keeps_the_previous_close(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(yahoo_finance_client, "_utcnow", lambda: _GPW_NOON)
        fake_yahoo.frame = _frame([("2026-09-23", 100.0, 520_000)], "Europe/Warsaw")
        quote = _session("kgh")
        assert quote.bar is None
        assert quote.previous_close == 100.0
        # No metadata: no trade time, and no failure over it.
        assert quote.last_trade_at is None

    def test_a_missing_volume_does_not_cost_the_price(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(yahoo_finance_client, "_utcnow", lambda: _GPW_NOON)
        fake_yahoo.frame = _frame(
            [("2026-09-23", 100.0, 520_000), ("2026-09-24", 103.0, float("nan"))],
            "Europe/Warsaw",
        )
        quote = _session("kgh")
        assert quote.bar is not None
        assert quote.bar.close == 103.0
        assert quote.bar.volume is None

    def test_nothing_at_all_is_a_provider_error(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(yahoo_finance_client, "_utcnow", lambda: _GPW_NOON)
        fake_yahoo.frame = None
        with pytest.raises(StooqAccessError):
            _session("kgh")

    def test_a_us_stock_reads_new_yorks_calendar(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 01:30 in Warsaw on the 25th is still the 24th in New York.
        monkeypatch.setattr(
            yahoo_finance_client,
            "_utcnow",
            lambda: _warsaw(date(2026, 9, 25), 1, 30).astimezone(UTC),
        )
        fake_yahoo.frame = _frame(
            [("2026-09-23", 330.0, 30_000_000), ("2026-09-24", 336.0, 40_000_000)],
            "America/New_York",
        )
        quote = _session("aapl.us")
        assert fake_yahoo.requested == ["AAPL"]
        assert quote.today == _TODAY
        assert quote.bar is not None and quote.final is True


# ── From a download to a live price ───────────────────────────────────────────


def _quote(
    *,
    close: float | None = 103.0,
    previous: float | None = 100.0,
    volume: int | None = 150_000,
    today: date = _TODAY,
    trade_at: datetime | None = None,
) -> SessionQuote:
    return SessionQuote(
        today=today,
        bar=(
            None
            if close is None
            else SessionBar(open=101.0, high=close + 1, low=99.0, close=close, volume=volume)
        ),
        final=False,
        previous_date=today - timedelta(days=1),
        previous_close=previous,
        last_trade_at=trade_at,
    )


class TestLivePriceFrom:
    def test_a_traded_session(self) -> None:
        trade_at = datetime(2026, 9, 24, 9, 44, tzinfo=UTC)
        live = live_price_from(_quote(trade_at=trade_at), _GPW_NOON)
        assert live is not None
        assert live.session_date == _TODAY
        assert live.price == 103.0
        assert live.change_pct == 3.0
        assert live.volume == 150_000
        assert live.as_of == trade_at
        assert live.fetched_at == _GPW_NOON

    def test_the_trade_time_falls_back_to_the_download_time(self) -> None:
        live = live_price_from(_quote(), _GPW_NOON)
        assert live is not None and live.as_of == _GPW_NOON

    def test_not_traded_yet_is_the_previous_close_unchanged(self) -> None:
        live = live_price_from(_quote(close=None), _GPW_NOON)
        assert live is not None
        assert live.price == 100.0
        assert live.change_pct == 0.0
        assert live.volume == 0

    def test_nothing_to_state_it_from(self) -> None:
        assert live_price_from(_quote(close=None, previous=None), _GPW_NOON) is None

    def test_no_previous_close_means_no_change(self) -> None:
        live = live_price_from(_quote(previous=None), _GPW_NOON)
        assert live is not None and live.change_pct is None


# ── The run ───────────────────────────────────────────────────────────────────


def _company(ticker: str, cap: int | None, market: str = "gpw") -> GpwCompany:
    return GpwCompany(ticker=ticker, name=ticker.upper(), market=market, market_cap=cap)


_GPW_COMPANIES = [
    _company("pko", 200_000_000_000),
    _company("pkn", 150_000_000_000),
    _company("pzu", 100_000_000_000),
    _company("kgh", 60_000_000_000),
    _company("small", None),
]
_US_COMPANY = _company("aapl.us", 3_000_000_000_000, market="us")


class _FakeSource:
    """Serves canned session quotes (or raises) and records what was asked."""

    def __init__(self, answers: dict[str, SessionQuote | Exception] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    async def get_session_quote(self, ticker: str) -> SessionQuote:
        self.asked.append(ticker)
        answer = self.answers.get(ticker, _quote())
        if isinstance(answer, Exception):
            raise answer
        return answer


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _service(
    source: _FakeSource,
    now: datetime = _GPW_NOON,
    companies: list[GpwCompany] | None = None,
    log: ActionLogService | None = None,
) -> tuple[LivePriceService, _Clock]:
    clock = _Clock(now)
    service = LivePriceService(
        companies=companies if companies is not None else [*_GPW_COMPANIES, _US_COMPANY],
        client=source,
        action_log=log,
        clock=clock,
    )
    return service, clock


class TestRun:
    def test_only_the_markets_trading_now_are_downloaded(self) -> None:
        source = _FakeSource()
        service, _ = _service(source)
        stats = asyncio.run(service.run())
        assert stats is not None
        assert stats.markets == ["gpw"]
        assert "aapl.us" not in source.asked
        assert sorted(source.asked) == sorted(c.ticker for c in _GPW_COMPANIES)
        assert stats.updated == len(_GPW_COMPANIES)
        assert service.get("kgh") is not None
        assert service.get("aapl.us") is None

    def test_the_largest_companies_are_asked_first(self) -> None:
        source = _FakeSource()
        service, _ = _service(source)
        asyncio.run(service.run())
        assert source.asked[:3] == ["pko", "pkn", "pzu"]

    def test_nothing_trading_is_a_silent_no_op(self) -> None:
        log = ActionLogService(to_file=False)
        source = _FakeSource()
        # 03:00 in Warsaw: nothing anywhere is open.
        service, _ = _service(source, now=_warsaw(_TODAY, 3).astimezone(UTC), log=log)
        stats = asyncio.run(service.run())
        assert stats is not None and stats.markets == []
        assert source.asked == []
        assert log.recent(action=ACTION) == []

    def test_a_holiday_costs_three_downloads_not_three_hundred(self) -> None:
        # The largest stocks answer, but none has a bar for today.
        source = _FakeSource({c.ticker: _quote(close=None) for c in _GPW_COMPANIES})
        service, _ = _service(source)
        stats = asyncio.run(service.run())
        assert stats is not None
        assert stats.quiet_markets == ["gpw"]
        assert source.asked == ["pko", "pkn", "pzu"]
        assert stats.companies == 0 and stats.updated == 0
        assert service.get("pko") is None
        assert run_outcome(stats) == OUTCOME_FINISHED

    def test_one_probe_trading_is_enough(self) -> None:
        answers: dict[str, SessionQuote | Exception] = {
            "pko": _quote(close=None),
            "pkn": _quote(),
            "pzu": _quote(close=None),
        }
        service, _ = _service(_FakeSource(answers))
        stats = asyncio.run(service.run())
        assert stats is not None and stats.quiet_markets == []
        assert stats.updated == 3  # pkn, kgh, small
        assert stats.not_traded == 2  # pko and pzu: not traded yet today
        pko = service.get("pko")
        assert pko is not None and pko.change_pct == 0.0 and pko.volume == 0

    def test_an_unreachable_provider_is_not_asked_three_hundred_times(self) -> None:
        answers: dict[str, SessionQuote | Exception] = {
            c.ticker: StooqAccessError("down") for c in _GPW_COMPANIES
        }
        source = _FakeSource(answers)
        service, _ = _service(source)
        stats = asyncio.run(service.run())
        assert stats is not None
        assert source.asked == ["pko", "pkn", "pzu"]
        assert stats.failed == len(_GPW_COMPANIES)
        assert run_outcome(stats) == OUTCOME_FAILED

    def test_a_few_failures_are_counted_not_fatal(self) -> None:
        companies = [_company(f"s{i}", 1_000_000_000 - i) for i in range(30)]
        answers: dict[str, SessionQuote | Exception] = {"s29": StooqAccessError("dead symbol")}
        service, _ = _service(_FakeSource(answers), companies=companies)
        stats = asyncio.run(service.run())
        assert stats is not None
        assert stats.failed == 1 and stats.failures == ["s29"]
        assert run_outcome(stats) == OUTCOME_FINISHED

    def test_many_failures_fail_the_run(self) -> None:
        companies = [_company(f"s{i}", 1_000_000_000 - i) for i in range(30)]
        answers: dict[str, SessionQuote | Exception] = {
            f"s{i}": StooqAccessError("no") for i in range(20, 30)
        }
        service, _ = _service(_FakeSource(answers), companies=companies)
        stats = asyncio.run(service.run())
        assert stats is not None and stats.failed == 10
        assert run_outcome(stats) == OUTCOME_FAILED

    def test_the_run_is_on_the_record(self) -> None:
        log = ActionLogService(to_file=False)
        service, _ = _service(_FakeSource(), log=log)
        asyncio.run(service.run(trigger="scheduled"))
        entries = log.recent(action=ACTION)
        assert [e.outcome for e in entries] == [OUTCOME_FINISHED, OUTCOME_STARTED]
        detail = entries[0].detail or {}
        assert detail["trigger"] == "scheduled"
        assert detail["markets"] == ["gpw"]
        assert detail["updated"] == len(_GPW_COMPANIES)
        assert entries[0].kind == "job"

    def test_a_second_run_while_one_is_going_is_skipped(self) -> None:
        async def scenario() -> tuple[LiveRunStats | None, LiveRunStats | None]:
            gate = asyncio.Event()

            class _Slow(_FakeSource):
                async def get_session_quote(self, ticker: str) -> SessionQuote:
                    await gate.wait()
                    return await super().get_session_quote(ticker)

            service, _ = _service(_Slow())
            first = asyncio.create_task(service.run())
            await asyncio.sleep(0)
            second = await service.run()
            gate.set()
            return await first, second

        first, second = asyncio.run(scenario())
        assert first is not None and first.updated == len(_GPW_COMPANIES)
        assert second is None

    def test_a_price_from_an_earlier_day_is_never_served(self) -> None:
        service, clock = _service(_FakeSource())
        asyncio.run(service.run())
        assert service.get("kgh") is not None
        clock.now = _GPW_NOON + timedelta(days=1)
        assert service.get("kgh") is None
        assert service.market_times() == {}

    def test_yesterdays_prices_go_on_the_next_run(self) -> None:
        source = _FakeSource()
        service, clock = _service(source)
        asyncio.run(service.run())
        # The next day "kgh" fails; its stale entry must not linger.
        clock.now = _GPW_NOON + timedelta(days=1)
        tomorrow = _TODAY + timedelta(days=1)
        source.answers = {c.ticker: _quote(today=tomorrow) for c in _GPW_COMPANIES}
        source.answers["kgh"] = StooqAccessError("gone")
        asyncio.run(service.run())
        assert service.get("pko") is not None
        assert "kgh" not in service._prices

    def test_market_times_and_last_update(self) -> None:
        service, _ = _service(_FakeSource())
        assert service.last_update_at is None
        asyncio.run(service.run())
        assert service.last_update_at == _GPW_NOON
        assert service.market_times() == {"gpw": _GPW_NOON}

    def test_a_refresh_limited_to_other_markets_downloads_nothing(self) -> None:
        source = _FakeSource()
        service, _ = _service(source)
        stats = asyncio.run(service.run(markets=["us"]))
        assert stats is not None and stats.markets == []
        assert source.asked == []


# ── Laying a live price over a payload ────────────────────────────────────────


def _live(price: float = 103.0, change: float | None = 3.0, day: date = _TODAY) -> LivePrice:
    return LivePrice(
        session_date=day,
        price=price,
        open=101.0,
        high=104.0,
        low=99.0,
        volume=150_000,
        previous_close=100.0,
        change_pct=change,
        as_of=_GPW_NOON,
        fetched_at=_GPW_NOON,
    )


def _row(last_session: date | None = _YESTERDAY) -> StockRankingItem:
    return StockRankingItem(
        ticker="KGH",
        name="KGHM",
        last_session=last_session,
        last_price=100.0,
        price_change_pct=-1.5,
        current_rating=72,
        rating_change=3,
        last_signal="Buy",
        days_since_signal=2,
        sparkline=[97.0, 98.0, 99.0, 100.0],
        volume=500_000,
    )


class TestOverlayRow:
    def test_a_newer_session_shows_todays_price(self) -> None:
        row = _row()
        shown = overlay_row(row, _live())
        assert shown.last_price == 103.0
        assert shown.price_change_pct == 3.0
        assert shown.sparkline == [98.0, 99.0, 100.0, 103.0]
        assert shown.live is not None
        # The analysis is untouched...
        assert shown.current_rating == 72
        assert shown.rating_change == 3
        assert shown.last_signal == "Buy"
        assert shown.last_session == _YESTERDAY
        # ...and so is the cached row it was copied from.
        assert row.last_price == 100.0 and row.live is None

    def test_the_finished_session_supersedes_it(self) -> None:
        row = _row(last_session=_TODAY)
        assert overlay_row(row, _live()) is row

    def test_an_unknown_session_is_left_alone(self) -> None:
        row = _row(last_session=None)
        assert overlay_row(row, _live()) is row

    def test_no_change_keeps_the_rows_own(self) -> None:
        shown = overlay_row(_row(), _live(change=None))
        assert shown.last_price == 103.0
        assert shown.price_change_pct == -1.5

    def test_the_service_overlays_only_its_own_tickers(self) -> None:
        service, _ = _service(_FakeSource({"kgh": _quote(close=110.0)}))
        asyncio.run(service.run())
        other = _row().model_copy(update={"ticker": "CDR"})
        shown = service.overlay_rows([_row(), other])
        assert shown[0].last_price == 110.0
        assert shown[1] is other


class TestOverlayTile:
    def test_every_horizon_is_measured_from_todays_price(self) -> None:
        tile = HeatmapItem(
            ticker="KGH",
            name="KGHM",
            last_price=100.0,
            current_rating=72,
            last_signal="Buy",
            change_1d=-1.5,
            change_1m=25.0,
            change_1y=-20.0,
            change_max=100.0,
            last_session=_YESTERDAY,
            baseline_1m=80.0,
            baseline_1y=125.0,
            baseline_max=50.0,
        )
        shown = overlay_tile(tile, _live(price=110.0, change=10.0))
        assert shown.last_price == 110.0
        assert shown.change_1d == 10.0
        assert shown.change_1m == 37.5
        assert shown.change_1y == -12.0
        assert shown.change_max == 120.0
        assert shown.current_rating == 72
        assert shown.live is not None

    def test_the_finished_session_supersedes_it(self) -> None:
        tile = HeatmapItem(
            ticker="KGH", name="KGHM", last_price=100.0, current_rating=72,
            last_signal="Buy", last_session=_TODAY,
        )
        assert overlay_tile(tile, _live()) is tile


# ── The scheduler and the refresh pipeline ────────────────────────────────────


class _Refresh:
    async def run(self, **_kwargs) -> None:
        return None


class TestScheduling:
    def test_the_live_job_fires_at_every_full_hour(self) -> None:
        service, _ = _service(_FakeSource())
        scheduler = build_scheduler(_Refresh(), live=service, live_interval_minutes=60)
        job = scheduler.get_job(JOB_ID)
        assert job is not None
        assert "minute='0'" in str(job.trigger)
        assert scheduler.get_job("daily_ingest") is not None

    def test_a_shorter_cadence(self) -> None:
        service, _ = _service(_FakeSource())
        scheduler = build_scheduler(_Refresh(), live=service, live_interval_minutes=30)
        assert "minute='*/30'" in str(scheduler.get_job(JOB_ID).trigger)

    def test_no_service_no_job(self) -> None:
        assert build_scheduler(_Refresh()).get_job(JOB_ID) is None


class TestRefreshStep:
    def test_the_refresh_button_ends_with_todays_prices(self) -> None:
        source = _FakeSource()
        service, _ = _service(source, companies=_GPW_COMPANIES)

        class _EmptyClient:
            async def get_daily_history(self, *_args, **_kwargs) -> list:
                return []

        refresh = RefreshService(
            companies=_GPW_COMPANIES,
            stooq=_EmptyClient(),  # type: ignore[arg-type]
            history_cache=history_cache,
            ranking_cache=ranking_cache,
            live=service,
        )
        asyncio.run(refresh.run(trigger="manual"))
        assert refresh.last_error is None
        assert service.get("pko") is not None


# ── Endpoints ─────────────────────────────────────────────────────────────────


def _bar(d: date, close: float = 100.0) -> StooqDailyQuote:
    return StooqDailyQuote(
        date=d,
        open=Decimal("99"),
        high=Decimal("102"),
        low=Decimal("98"),
        close=Decimal(str(close)),
        volume=200_000,
    )


def _history_to_yesterday(n: int = 40) -> list[StooqDailyQuote]:
    """``n`` flat daily bars ending on the GPW's yesterday — today not stored yet."""
    last = GPW.local_date() - timedelta(days=1)
    return [_bar(last - timedelta(days=n - 1 - i)) for i in range(n)]


class _FakeHistoryClient:
    def __init__(self, quotes: list[StooqDailyQuote]) -> None:
        self._quotes = quotes

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return [q for q in self._quotes if to_date is None or q.date <= to_date]


class _OneCompany:
    def __init__(self, company: GpwCompany) -> None:
        self._company = company

    def get_companies(self, market: str = "gpw") -> list[GpwCompany]:
        return [self._company] if market == "gpw" else []

    def find(self, ticker: str) -> GpwCompany | None:
        return self._company if ticker.casefold() == self._company.ticker else None


def _todays(price: float = 110.0, change: float = 10.0) -> LivePrice:
    today = GPW.local_date()
    now = datetime.now(tz=UTC)
    return LivePrice(
        session_date=today,
        price=price,
        open=101.0,
        high=111.0,
        low=100.0,
        volume=90_000,
        previous_close=100.0,
        change_pct=change,
        as_of=now,
        fetched_at=now,
    )


def _service_holding(**prices: LivePrice) -> LivePriceService:
    service = LivePriceService(companies=[], client=_FakeSource())
    service._prices.update(prices)
    service._market_fetched["gpw"] = datetime.now(tz=UTC)
    service.last_update_at = datetime.now(tz=UTC)
    return service


@pytest.fixture(autouse=True)
def _clear_caches_and_overrides():
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    app.dependency_overrides.clear()


class TestEndpoints:
    def _install(self, live: LivePriceService | None) -> None:
        company = GpwCompany(ticker="kgh", name="KGHM", market_cap=60_000_000_000)
        app.dependency_overrides[get_gpw_company_service] = lambda: _OneCompany(company)
        app.dependency_overrides[get_stooq_client] = lambda: _FakeHistoryClient(
            _history_to_yesterday()
        )
        app.dependency_overrides[get_live_prices] = lambda: live

    def test_the_ranking_shows_todays_price_and_keeps_the_rating(self) -> None:
        self._install(None)
        with TestClient(app) as client:
            before = client.get("/api/stocks/ranking").json()[0]
        ranking_cache.clear()
        history_cache.clear()
        self._install(_service_holding(kgh=_todays()))
        with TestClient(app) as client:
            after = client.get("/api/stocks/ranking").json()[0]
        assert before["live"] is None
        assert after["lastPrice"] == 110.0
        assert after["priceChangePct"] == 10.0
        assert after["live"]["price"] == 110.0
        assert after["live"]["sessionDate"] == GPW.local_date().isoformat()
        for unchanged in ("currentRating", "ratingChange", "lastSignal", "lastSession"):
            assert after[unchanged] == before[unchanged]

    def test_price_bounds_read_the_live_price(self) -> None:
        self._install(_service_holding(kgh=_todays(price=110.0)))
        with TestClient(app) as client:
            above = client.get("/api/stocks/ranking", params={"minPrice": 105}).json()
            below = client.get("/api/stocks/ranking", params={"maxPrice": 105}).json()
        assert [r["ticker"] for r in above] == ["KGH"]
        assert below == []

    def test_the_stock_page_carries_todays_price(self) -> None:
        self._install(_service_holding(kgh=_todays()))
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals").json()
        assert body["lastPrice"] == 110.0
        assert body["priceChangePct"] == 10.0
        assert body["live"]["price"] == 110.0
        # The candles stay finished sessions: today is not among them.
        assert body["history"][-1]["time"] < GPW.local_date().isoformat()

    def test_a_chart_ending_in_the_past_gets_no_live_price(self) -> None:
        self._install(_service_holding(kgh=_todays()))
        to_date = (GPW.local_date() - timedelta(days=5)).isoformat()
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals", params={"toDate": to_date}).json()
        assert body["live"] is None
        assert body["lastPrice"] == 100.0

    def test_the_rating_does_not_move_with_the_live_price(self) -> None:
        self._install(None)
        with TestClient(app) as client:
            plain = client.get("/api/stocks/kgh/signals").json()
        history_cache.clear()
        self._install(_service_holding(kgh=_todays(price=150.0, change=50.0)))
        with TestClient(app) as client:
            live = client.get("/api/stocks/kgh/signals").json()
        assert live["currentRating"] == plain["currentRating"]
        assert live["ratingChange"] == plain["ratingChange"]
        assert live["vsaSignals"] == plain["vsaSignals"]
        assert live["history"] == plain["history"]

    def test_the_heatmap_tile_is_measured_from_todays_price(self) -> None:
        self._install(_service_holding(kgh=_todays(price=110.0, change=10.0)))
        with TestClient(app) as client:
            body = client.get("/api/stocks/heatmap").json()
        [tile] = body["items"]
        assert tile["lastPrice"] == 110.0
        assert tile["change1D"] == 10.0
        assert tile["live"]["price"] == 110.0
        # The internal reference closes never leave the server.
        assert "baseline1M" not in tile and "baselineMax" not in tile
        assert "lastSession" not in tile

    def test_the_refresh_status_says_when_prices_last_changed(self) -> None:
        self._install(_service_holding(kgh=_todays()))
        with TestClient(app) as client:
            body = client.get("/api/stocks/refresh/status").json()
        assert body["livePricesAt"] is not None
        assert set(body["liveMarkets"]) == {"gpw"}

    def test_without_the_service_nothing_changes(self) -> None:
        self._install(None)
        with TestClient(app) as client:
            status = client.get("/api/stocks/refresh/status").json()
            row = client.get("/api/stocks/ranking").json()[0]
        assert status["livePricesAt"] is None
        assert status["liveMarkets"] == {}
        assert row["live"] is None
        assert row["lastPrice"] == 100.0
