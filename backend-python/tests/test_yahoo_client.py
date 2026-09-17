"""Tests for the Yahoo Finance client's market handling.

No network: ``yfinance.Ticker`` is replaced by a fake that records which symbol
was asked for and serves a canned frame, and the client's clock is pinned.

Pinned here:

* every market's ticker reaches Yahoo under the symbol Yahoo knows;
* a bar for a session that is still trading is never returned — the case
  observed live on 2026-09-16, when the US session was open at the time of the
  Warsaw evening run;
* intraday bars are labelled on the exchange's own clock.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd
import pytest
import yfinance

from app.services import yahoo_finance_client
from app.services.exceptions import StooqAccessError
from app.services.yahoo_finance_client import YahooFinanceClient


class _FakeTicker:
    """Stands in for ``yfinance.Ticker``: records the symbol, serves a frame."""

    requested: list[str] = []
    frame: pd.DataFrame | None = None

    def __init__(self, symbol: str) -> None:
        _FakeTicker.requested.append(symbol)

    def history(self, **_kwargs) -> pd.DataFrame | None:
        return None if _FakeTicker.frame is None else _FakeTicker.frame.copy()


@pytest.fixture
def fake_yahoo(monkeypatch: pytest.MonkeyPatch) -> type[_FakeTicker]:
    _FakeTicker.requested = []
    _FakeTicker.frame = None
    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)
    return _FakeTicker


def _pin_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(yahoo_finance_client, "_utcnow", lambda: moment)


def _daily_frame(days: list[str], zone: str, volume: int = 50_000_000) -> pd.DataFrame:
    """Daily bars stamped at midnight in the exchange's zone, as Yahoo does."""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in days]).tz_localize(zone)
    n = len(days)
    return pd.DataFrame(
        {
            "Open": [100.0] * n,
            "High": [102.0] * n,
            "Low": [99.0] * n,
            "Close": [101.0] * n,
            "Volume": [volume] * n,
        },
        index=index,
    )


def _history(ticker: str) -> list:
    return asyncio.run(YahooFinanceClient().get_daily_history(ticker))


# 11:39 in New York on 16 September 2026 (17:39 in Warsaw) — US session open.
_US_MID_SESSION = datetime(2026, 9, 16, 15, 39, tzinfo=UTC)
# 16:30 in New York — the US session has closed and settled.
_US_AFTER_CLOSE = datetime(2026, 9, 16, 20, 30, tzinfo=UTC)


class TestSymbols:
    @pytest.mark.parametrize(
        ("ticker", "symbol", "zone"),
        [
            ("kgh", "KGH.WA", "Europe/Warsaw"),
            ("aapl.us", "AAPL", "America/New_York"),
            ("brk-b.us", "BRK-B", "America/New_York"),
            ("sap.de", "SAP.DE", "Europe/Berlin"),
            ("mc.pa", "MC.PA", "Europe/Paris"),
            ("asml.as", "ASML.AS", "Europe/Amsterdam"),
            ("hsba.l", "HSBA.L", "Europe/London"),
        ],
    )
    def test_each_market_is_asked_for_by_its_yahoo_symbol(
        self,
        fake_yahoo: type[_FakeTicker],
        monkeypatch: pytest.MonkeyPatch,
        ticker: str,
        symbol: str,
        zone: str,
    ) -> None:
        _pin_clock(monkeypatch, _US_AFTER_CLOSE)
        fake_yahoo.frame = _daily_frame(["2026-09-14", "2026-09-15"], zone)
        quotes = _history(ticker)
        assert fake_yahoo.requested == [symbol]
        assert [q.date for q in quotes] == [date(2026, 9, 14), date(2026, 9, 15)]

    def test_an_invalid_ticker_never_reaches_yahoo(self, fake_yahoo: type[_FakeTicker]) -> None:
        with pytest.raises(ValueError):
            _history("not a ticker")
        assert fake_yahoo.requested == []

    def test_fundamentals_use_the_same_mapping(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fundamentals read ``Ticker(...).info``; the fake has none, which the
        # client treats as "no data" — what matters is the symbol it asked for.
        monkeypatch.setattr(_FakeTicker, "info", {}, raising=False)
        asyncio.run(YahooFinanceClient().get_fundamentals("hsba.l"))
        assert fake_yahoo.requested == ["HSBA.L"]


class TestUnfinishedSessions:
    def test_the_session_in_progress_is_dropped(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _pin_clock(monkeypatch, _US_MID_SESSION)
        fake_yahoo.frame = _daily_frame(
            ["2026-09-14", "2026-09-15", "2026-09-16"], "America/New_York"
        )
        quotes = _history("aapl.us")
        assert [q.date for q in quotes] == [date(2026, 9, 14), date(2026, 9, 15)]

    def test_the_same_bar_is_kept_once_the_session_has_closed(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _pin_clock(monkeypatch, _US_AFTER_CLOSE)
        fake_yahoo.frame = _daily_frame(
            ["2026-09-14", "2026-09-15", "2026-09-16"], "America/New_York"
        )
        quotes = _history("aapl.us")
        assert quotes[-1].date == date(2026, 9, 16)
        assert quotes[-1].close == Decimal("101.0000")

    def test_a_closed_market_is_unaffected_by_another_one_trading(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 17:39 Warsaw: the GPW has closed although New York is mid-session.
        _pin_clock(monkeypatch, _US_MID_SESSION)
        fake_yahoo.frame = _daily_frame(["2026-09-15", "2026-09-16"], "Europe/Warsaw")
        quotes = _history("kgh")
        assert [q.date for q in quotes] == [date(2026, 9, 15), date(2026, 9, 16)]

    def test_nothing_final_yet_is_an_empty_answer_not_an_error(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A provider that only has today's unfinished bar has not failed —
        # the ingest must not count the ticker as broken.
        _pin_clock(monkeypatch, _US_MID_SESSION)
        fake_yahoo.frame = _daily_frame(["2026-09-16"], "America/New_York")
        assert _history("aapl.us") == []

    def test_no_data_at_all_is_still_an_error(
        self, fake_yahoo: type[_FakeTicker], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _pin_clock(monkeypatch, _US_AFTER_CLOSE)
        fake_yahoo.frame = pd.DataFrame()
        with pytest.raises(StooqAccessError):
            _history("aapl.us")


class TestIntradayClock:
    def _utc_hourly(self, stamps: list[str]) -> pd.DataFrame:
        index = pd.DatetimeIndex([pd.Timestamp(s) for s in stamps]).tz_localize("UTC")
        n = len(stamps)
        return pd.DataFrame(
            {
                "Open": [10.0] * n,
                "High": [11.0] * n,
                "Low": [9.0] * n,
                "Close": [10.5] * n,
                "Volume": [1000] * n,
            },
            index=index,
        )

    def test_us_bars_are_labelled_in_new_york_time(
        self, fake_yahoo: type[_FakeTicker]
    ) -> None:
        fake_yahoo.frame = self._utc_hourly(["2026-09-15 13:30", "2026-09-15 14:30"])
        bars = asyncio.run(YahooFinanceClient().get_intraday_history("aapl.us", "1h", 5))
        assert fake_yahoo.requested == ["AAPL"]
        assert bars[0].date.isoformat() == "2026-09-15T09:30:00-04:00"

    def test_gpw_bars_stay_on_warsaw_time(self, fake_yahoo: type[_FakeTicker]) -> None:
        fake_yahoo.frame = self._utc_hourly(["2026-09-15 07:00"])
        bars = asyncio.run(YahooFinanceClient().get_intraday_history("jsw", "1h", 5))
        assert fake_yahoo.requested == ["JSW.WA"]
        assert bars[0].date.isoformat() == "2026-09-15T09:00:00+02:00"

    def test_london_bars_are_labelled_in_london_time(
        self, fake_yahoo: type[_FakeTicker]
    ) -> None:
        fake_yahoo.frame = self._utc_hourly(["2026-09-15 07:00"])
        bars = asyncio.run(YahooFinanceClient().get_intraday_history("hsba.l", "30m", 5))
        assert bars[0].date.isoformat() == "2026-09-15T08:00:00+01:00"
