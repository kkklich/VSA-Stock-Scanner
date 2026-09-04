"""Chart timeframes: bar aggregation, the interval table, and the endpoint.

Covers ``app.analysis.timeframe`` plus the ``interval`` parameter on
``GET /api/stocks/{ticker}/signals`` — including the invariant the feature
rests on: switching the chart's bar size must not move the stock's daily
rating, price or verdict, because every other card on the page shows those.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.analysis.timeframe import (
    DEFAULT_TIMEFRAME,
    TIMEFRAMES,
    IntradayBar,
    bars_per_session,
    clamp_lookback_days,
    get_timeframe,
    group_intraday,
    timeframe_ids,
)
from app.dependencies import get_stooq_client, history_cache, ranking_cache
from app.main import app
from app.models import StooqDailyQuote
from app.routers.stocks import _backfill_attempted
from app.services.exceptions import StooqAccessError

WARSAW = ZoneInfo("Europe/Warsaw")


def _bar(
    day: str,
    hour: int,
    open_: float = 10.0,
    high: float = 11.0,
    low: float = 9.0,
    close: float = 10.5,
    volume: int = 1_000,
) -> IntradayBar:
    return IntradayBar(
        date=datetime.fromisoformat(day).replace(hour=hour, tzinfo=WARSAW),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


# ── The timeframe table ───────────────────────────────────────────────────────


class TestTimeframeTable:
    def test_offers_the_five_chart_bar_sizes(self) -> None:
        assert timeframe_ids() == ("30m", "1h", "4h", "1d", "1w")

    def test_daily_is_the_default(self) -> None:
        assert DEFAULT_TIMEFRAME == "1d"
        spec = get_timeframe(None)
        assert spec is not None and spec.id == "1d"

    def test_lookup_is_case_insensitive_and_trims(self) -> None:
        spec = get_timeframe("  1H ")
        assert spec is not None and spec.id == "1h"

    def test_unknown_interval_is_rejected(self) -> None:
        assert get_timeframe("5m") is None
        assert get_timeframe("") is None

    def test_only_intraday_sizes_are_flagged_intraday(self) -> None:
        intraday = {tf.id for tf in TIMEFRAMES if tf.intraday}
        assert intraday == {"30m", "1h", "4h"}

    def test_four_hour_is_built_from_hourly_bars(self) -> None:
        spec = get_timeframe("4h")
        assert spec is not None
        # Yahoo has no 4-hour interval, so it must ask for 1h and group them.
        assert spec.yahoo_interval == "1h"
        assert spec.group == 4

    def test_bars_per_session_shrinks_as_bars_grow(self) -> None:
        counts = [bars_per_session(tf) for tf in TIMEFRAMES]
        assert counts == sorted(counts, reverse=True)
        daily = get_timeframe("1d")
        assert daily is not None and bars_per_session(daily) == 1

    def test_lookback_is_clamped_to_what_the_provider_serves(self) -> None:
        half_hour = get_timeframe("30m")
        assert half_hour is not None
        # 30-minute history stops at 60 days however much is asked for.
        assert clamp_lookback_days(half_hour, 3650) == 60
        assert clamp_lookback_days(half_hour, 10) == 10

    def test_daily_history_is_not_capped(self) -> None:
        daily = get_timeframe("1d")
        assert daily is not None
        assert clamp_lookback_days(daily, 3650) == 3650


# ── Intraday aggregation ──────────────────────────────────────────────────────


class TestGroupIntraday:
    def test_group_of_one_returns_the_bars_unchanged(self) -> None:
        bars = [_bar("2026-09-01", h) for h in range(9, 13)]
        assert group_intraday(bars, 1) == bars

    def test_merges_ohlcv_across_the_group(self) -> None:
        bars = [
            _bar("2026-09-01", 9, open_=10, high=12, low=9, close=11, volume=100),
            _bar("2026-09-01", 10, open_=11, high=15, low=10, close=14, volume=200),
            _bar("2026-09-01", 11, open_=14, high=14, low=8, close=9, volume=300),
            _bar("2026-09-01", 12, open_=9, high=13, low=9, close=13, volume=400),
        ]
        merged_bars = group_intraday(bars, 4)
        assert len(merged_bars) == 1
        merged = merged_bars[0]
        assert merged.open == Decimal("10")  # first open
        assert merged.high == Decimal("15")  # highest high
        assert merged.low == Decimal("8")  # lowest low
        assert merged.close == Decimal("13")  # last close
        assert merged.volume == 1000  # summed volume
        # Stamped with the group's FIRST bar — how a chart labels a candle.
        assert merged.date.hour == 9

    def test_never_groups_across_the_overnight_gap(self) -> None:
        # Two half-sessions: a group spanning them would describe a price range
        # that never traded as one stretch.
        bars = [_bar("2026-09-01", h) for h in (9, 10)]
        bars += [_bar("2026-09-02", h) for h in (9, 10)]
        merged = group_intraday(bars, 4)
        assert len(merged) == 2
        assert [b.date.date() for b in merged] == [date(2026, 9, 1), date(2026, 9, 2)]

    def test_gpw_session_becomes_two_four_hour_bars(self) -> None:
        # 09:00-17:00 = nine hourly stamps; the lone 17:00 closing-auction bar
        # is folded into the afternoon rather than becoming a bar of its own.
        bars = [_bar("2026-09-01", h) for h in range(9, 18)]
        merged = group_intraday(bars, 4)
        assert [b.date.hour for b in merged] == [9, 13]

    def test_stub_tail_is_folded_into_the_previous_group(self) -> None:
        bars = [_bar("2026-09-01", h, volume=10) for h in range(9, 18)]
        merged = group_intraday(bars, 4)
        # Nothing may be dropped: every input bar's volume is accounted for.
        assert sum(b.volume for b in merged) == 90
        assert merged[-1].volume == 50  # 13:00-17:00 = five bars

    def test_a_half_length_tail_stays_its_own_bar(self) -> None:
        # Only a tail shorter than half the group is folded back; two of four
        # bars is a real (if short) candle.
        bars = [_bar("2026-09-01", h) for h in (9, 10, 11, 12, 13, 14)]
        merged = group_intraday(bars, 4)
        assert [b.date.hour for b in merged] == [9, 13]

    def test_unsorted_input_is_ordered_first(self) -> None:
        bars = [_bar("2026-09-01", h) for h in (11, 9, 12, 10)]
        merged = group_intraday(bars, 4)
        assert len(merged) == 1
        assert merged[0].date.hour == 9

    def test_empty_input(self) -> None:
        assert group_intraday([], 4) == []


# ── GET /api/stocks/{ticker}/signals?interval=... ─────────────────────────────


def _daily(n: int = 400) -> list[StooqDailyQuote]:
    """A daily series ending today, long enough to rate and to resample."""
    start = date.today() - timedelta(days=n - 1)
    out: list[StooqDailyQuote] = []
    for i in range(n):
        base = 100 + (i % 7)
        out.append(
            StooqDailyQuote(
                date=start + timedelta(days=i),
                open=Decimal(str(base)),
                high=Decimal(str(base + 2)),
                low=Decimal(str(base - 2)),
                close=Decimal(str(base + 1)),
                volume=200_000 + (i % 5) * 10_000,
            )
        )
    return out


def _intraday(sessions: int = 40) -> list[IntradayBar]:
    """Hourly bars over the last `sessions` weekdays, 09:00-17:00 Warsaw."""
    out: list[IntradayBar] = []
    day = date.today() - timedelta(days=sessions)
    while day <= date.today():
        if day.weekday() < 5:
            for i, hour in enumerate(range(9, 18)):
                base = 100 + (i % 5)
                out.append(
                    IntradayBar(
                        date=datetime(day.year, day.month, day.day, hour, tzinfo=WARSAW),
                        open=Decimal(str(base)),
                        high=Decimal(str(base + 2)),
                        low=Decimal(str(base - 2)),
                        close=Decimal(str(base + 1)),
                        volume=10_000 + i * 100,
                    )
                )
        day += timedelta(days=1)
    return out


class _FakeTimeframeClient:
    """Serves canned daily AND intraday series, with no network access."""

    def __init__(
        self,
        daily: list[StooqDailyQuote],
        intraday: list[IntradayBar] | None = None,
        intraday_error: Exception | None = None,
    ) -> None:
        self._daily = daily
        self._intraday = intraday or []
        self._intraday_error = intraday_error
        self.intraday_calls: list[tuple[str, str, int]] = []

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        return self._daily

    async def get_intraday_history(self, ticker, interval, lookback_days):
        self.intraday_calls.append((ticker, interval, lookback_days))
        if self._intraday_error is not None:
            raise self._intraday_error
        return self._intraday


@pytest.fixture(autouse=True)
def _clear_state():
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()
    app.dependency_overrides.clear()
    yield
    history_cache.clear()
    ranking_cache.clear()
    _backfill_attempted.clear()
    app.dependency_overrides.clear()


class TestSignalsInterval:
    def test_defaults_to_daily_bars(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals").json()
        assert body["interval"] == "1d"
        assert body["intraday"] is False
        # Dates, not timestamps — the payload older clients already read.
        assert "T" not in body["history"][0]["time"]

    def test_unknown_interval_is_a_400_that_lists_the_valid_ones(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily()
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/signals", params={"interval": "5m"})
        assert resp.status_code == 400
        assert "30m" in resp.json()["detail"]

    def test_weekly_aggregates_the_daily_bars_without_fetching_intraday(self) -> None:
        fake = _FakeTimeframeClient(_daily())
        app.dependency_overrides[get_stooq_client] = lambda: fake
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals", params={"interval": "1w"}).json()
        assert body["interval"] == "1w"
        assert body["intraday"] is False
        assert fake.intraday_calls == []  # no new data source
        # Roughly one bar a week, so far fewer than the daily series behind it.
        assert 0 < len(body["history"]) < len(_daily()) / 4

    def test_intraday_bars_carry_exchange_local_timestamps(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily(), _intraday()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals", params={"interval": "1h"}).json()
        assert body["interval"] == "1h"
        assert body["intraday"] is True
        first = body["history"][0]["time"]
        assert "T" in first
        # Warsaw runs one or two hours ahead of UTC, never at UTC itself.
        assert first.endswith("+01:00") or first.endswith("+02:00")

    def test_four_hour_asks_the_provider_for_hourly_bars(self) -> None:
        fake = _FakeTimeframeClient(_daily(), _intraday())
        app.dependency_overrides[get_stooq_client] = lambda: fake
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals", params={"interval": "4h"}).json()
        assert [call[1] for call in fake.intraday_calls] == ["1h"]
        # Nine hourly bars a session collapse into two four-hour ones.
        assert 0 < len(body["history"]) < len(_intraday()) / 3

    def test_intraday_lookback_is_clamped_to_the_provider_limit(self) -> None:
        fake = _FakeTimeframeClient(_daily(), _intraday())
        app.dependency_overrides[get_stooq_client] = lambda: fake
        with TestClient(app) as client:
            client.get(
                "/api/stocks/kgh/signals",
                params={"interval": "30m", "fromDate": "2020-01-01"},
            )
        assert fake.intraday_calls[0][2] == 60  # not the ~2200 days requested

    def test_provider_failure_is_reported_as_a_bad_gateway(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily(), intraday_error=StooqAccessError("no intraday data")
        )
        with TestClient(app) as client:
            resp = client.get("/api/stocks/kgh/signals", params={"interval": "30m"})
        assert resp.status_code == 502
        assert "no intraday data" in resp.json()["detail"]

    def test_method_overlays_are_daily_only(self) -> None:
        """A 200-*day* MA means nothing on 30-minute bars — better no layer."""
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily(), _intraday()
        )
        with TestClient(app) as client:
            daily = client.get("/api/stocks/kgh/signals").json()
            intraday = client.get(
                "/api/stocks/kgh/signals", params={"interval": "1h"}
            ).json()
        assert len(daily["methodSignals"]) > 0
        assert intraday["methodSignals"] == []

    def test_rating_and_price_do_not_move_with_the_chart_bar_size(self) -> None:
        """The header rating is the app's daily read, shown on every other card
        too, so changing the chart's bar size must not change it."""
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily(), _intraday()
        )
        recent = (date.today() - timedelta(days=20)).isoformat()
        with TestClient(app) as client:
            results = {
                interval: client.get(
                    "/api/stocks/kgh/signals",
                    params={"interval": interval, "fromDate": recent},
                ).json()
                for interval in ("1d", "1w", "4h", "1h", "30m")
            }
        baseline = results["1d"]
        for interval, body in results.items():
            assert body["currentRating"] == baseline["currentRating"], interval
            assert body["ratingChange"] == baseline["ratingChange"], interval
            assert body["lastPrice"] == baseline["lastPrice"], interval
            assert body["priceChangePct"] == baseline["priceChangePct"], interval

    def test_history_start_reports_what_was_really_served(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily(), _intraday()
        )
        with TestClient(app) as client:
            body = client.get(
                "/api/stocks/kgh/signals",
                params={"interval": "1h", "fromDate": "2020-01-01"},
            ).json()
        # Asked for 2020; the provider only has weeks of intraday history, and
        # the response says so instead of implying the window was honoured.
        assert body["historyStart"] > "2020-01-01"
        assert body["historyStart"] == body["history"][0]["time"][:10]

    def test_signals_sit_on_bars_that_are_actually_shown(self) -> None:
        app.dependency_overrides[get_stooq_client] = lambda: _FakeTimeframeClient(
            _daily(), _intraday()
        )
        with TestClient(app) as client:
            body = client.get("/api/stocks/kgh/signals", params={"interval": "1h"}).json()
        shown = {bar["time"] for bar in body["history"]}
        assert all(sig["date"] in shown for sig in body["vsaSignals"])
