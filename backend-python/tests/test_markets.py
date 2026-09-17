"""Tests for the market registry (app/markets.py).

Pinned here:

* the ticker scheme — a GPW code stays bare, every other market carries a
  suffix, and only well-formed tickers survive ``normalize_ticker``;
* the mapping to Yahoo symbols and back, for every market;
* money: most London prices are in pence, and the złoty floors are converted
  from each stock's own quote currency before it is judged against them;
* time: a session only counts once its exchange has closed (plus a settling
  buffer), on the exchange's own clock — including the weeks when US and EU
  daylight saving disagree;
* the ``STOCKPILOT_MARKETS`` switch.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app import markets
from app.config import settings
from app.markets import (
    FRANCE,
    GERMANY,
    GPW,
    INDEX_NAMES,
    MARKETS,
    MAX_TICKER_LENGTH,
    NETHERLANDS,
    PLN_PER_UNIT,
    UNITED_KINGDOM,
    US,
    below_liquidity_floor,
    below_market_cap_floor,
    enabled_markets,
    get_market,
    is_enabled,
    major_currency,
    market_for_yahoo_symbol,
    market_of,
    normalize_ticker,
    parse_market_ids,
    quote_currency,
    ticker_for,
    ticker_symbol,
    to_pln,
    yahoo_symbol,
)
from app.models import GpwCompany

_WARSAW = ZoneInfo("Europe/Warsaw")
_NEW_YORK = ZoneInfo("America/New_York")
_LONDON = ZoneInfo("Europe/London")


# ── The registry itself ───────────────────────────────────────────────────────


class TestRegistry:
    def test_gpw_comes_first(self) -> None:
        # Display order: the site's home market leads every switcher.
        assert MARKETS[0] is GPW

    def test_ids_and_suffixes_are_unique(self) -> None:
        assert len({m.id for m in MARKETS}) == len(MARKETS)
        suffixes = [m.ticker_suffix for m in MARKETS]
        assert len(set(suffixes)) == len(suffixes)
        yahoo = [m.yahoo_suffix for m in MARKETS]
        assert len(set(yahoo)) == len(yahoo)

    def test_only_the_gpw_is_unsuffixed_in_the_app(self) -> None:
        assert [m.id for m in MARKETS if not m.ticker_suffix] == ["gpw"]

    def test_only_the_us_is_unsuffixed_on_yahoo(self) -> None:
        assert [m.id for m in MARKETS if not m.yahoo_suffix] == ["us"]

    def test_every_index_has_a_display_name(self) -> None:
        for market in MARKETS:
            for index_id in market.indices:
                assert index_id in INDEX_NAMES

    def test_every_time_zone_is_real(self) -> None:
        for market in MARKETS:
            assert market.tz.key == market.timezone

    def test_get_market_is_case_insensitive(self) -> None:
        assert get_market("US") is US
        assert get_market(" uk ") is UNITED_KINGDOM
        assert get_market("xx") is None
        assert get_market(None) is None
        assert get_market("") is None


# ── Tickers ───────────────────────────────────────────────────────────────────


class TestNormalizeTicker:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("kgh", "kgh"),
            (" KGH ", "kgh"),
            ("11b", "11b"),
            # Yahoo's spelling of a GPW code is the same stock.
            ("KGH.WA", "kgh"),
            ("AAPL.US", "aapl.us"),
            ("brk-b.US", "brk-b.us"),
            ("SAP.DE", "sap.de"),
            ("mc.pa", "mc.pa"),
            ("ASML.AS", "asml.as"),
            ("HSBA.L", "hsba.l"),
            ("BT-A.L", "bt-a.l"),
            ("1cov.de", "1cov.de"),
        ],
    )
    def test_valid_tickers(self, raw: str, expected: str) -> None:
        assert normalize_ticker(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "   ",
            "a" * (MAX_TICKER_LENGTH + 1),
            # A GPW code never had a hyphen.
            "abc-def",
            "foo.xx",
            ".us",
            "-abc.us",
            "aapl.us.us",
            "!!!",
            "../etc",
            "k g h",
            "kgh.",
            "ąbc",
        ],
    )
    def test_invalid_tickers(self, raw: str | None) -> None:
        assert normalize_ticker(raw) is None

    def test_the_length_limit_matches_the_database_column(self) -> None:
        # companies.ticker / daily_quotes.ticker are VARCHAR(20).
        assert MAX_TICKER_LENGTH == 20
        assert normalize_ticker("a" * 17 + ".us") == "a" * 17 + ".us"


class TestMarketOf:
    def test_bare_code_is_gpw(self) -> None:
        assert market_of("kgh") is GPW

    @pytest.mark.parametrize(
        ("ticker", "market"),
        [
            ("aapl.us", US),
            ("sap.de", GERMANY),
            ("mc.pa", FRANCE),
            ("asml.as", NETHERLANDS),
            ("hsba.l", UNITED_KINGDOM),
        ],
    )
    def test_suffix_picks_the_market(self, ticker: str, market) -> None:
        assert market_of(ticker) is market

    def test_unknown_suffix_raises(self) -> None:
        with pytest.raises(ValueError):
            market_of("abc.xx")


class TestTheClashesThatForcedTheSuffix:
    """Real pairs of different companies sharing one bare code."""

    @pytest.mark.parametrize(
        ("gpw", "foreign", "foreign_yahoo"),
        [
            ("pep", "pep.us", "PEP"),  # Polenergia vs PepsiCo
            ("bdx", "bdx.us", "BDX"),  # Budimex vs Becton Dickinson
            ("nwg", "nwg.l", "NWG.L"),  # Newag vs NatWest
        ],
    )
    def test_both_stocks_stay_apart(self, gpw: str, foreign: str, foreign_yahoo: str) -> None:
        assert normalize_ticker(gpw) != normalize_ticker(foreign)
        assert yahoo_symbol(gpw) == gpw.upper() + ".WA"
        assert yahoo_symbol(foreign) == foreign_yahoo


class TestYahooSymbols:
    @pytest.mark.parametrize(
        ("ticker", "symbol"),
        [
            ("kgh", "KGH.WA"),
            ("KGH.WA", "KGH.WA"),
            ("aapl.us", "AAPL"),
            ("brk-b.us", "BRK-B"),
            ("sap.de", "SAP.DE"),
            ("mc.pa", "MC.PA"),
            ("asml.as", "ASML.AS"),
            ("hsba.l", "HSBA.L"),
            ("bt-a.l", "BT-A.L"),
        ],
    )
    def test_ticker_to_yahoo(self, ticker: str, symbol: str) -> None:
        assert yahoo_symbol(ticker) == symbol

    def test_invalid_ticker_is_refused(self) -> None:
        with pytest.raises(ValueError):
            yahoo_symbol("not a ticker")

    @pytest.mark.parametrize(
        ("symbol", "market"),
        [
            ("KGH.WA", GPW),
            ("AAPL", US),
            ("BRK-B", US),
            ("SAP.DE", GERMANY),
            ("MC.PA", FRANCE),
            ("ASML.AS", NETHERLANDS),
            ("HSBA.L", UNITED_KINGDOM),
            ("hsba.l", UNITED_KINGDOM),
        ],
    )
    def test_yahoo_to_market(self, symbol: str, market) -> None:
        assert market_for_yahoo_symbol(symbol) is market

    def test_an_untracked_yahoo_suffix_is_refused(self) -> None:
        with pytest.raises(ValueError):
            market_for_yahoo_symbol("SHOP.TO")

    @pytest.mark.parametrize("ticker", ["kgh", "aapl.us", "sap.de", "mc.pa", "asml.as", "hsba.l"])
    def test_round_trip(self, ticker: str) -> None:
        assert market_for_yahoo_symbol(yahoo_symbol(ticker)) is market_of(ticker)

    def test_display_symbol_drops_the_suffix(self) -> None:
        assert ticker_symbol("aapl.us") == "AAPL"
        assert ticker_symbol("bt-a.l") == "BT-A"
        assert ticker_symbol("kgh") == "KGH"


class TestTickerFor:
    @pytest.mark.parametrize(
        ("symbol", "market", "ticker"),
        [
            ("AAPL", US, "aapl.us"),
            # Index providers write share classes with a dot; Yahoo uses a hyphen.
            ("BRK.B", US, "brk-b.us"),
            ("SAP.DE", GERMANY, "sap.de"),
            ("SAP", GERMANY, "sap.de"),
            ("AC.PA", FRANCE, "ac.pa"),
            ("ABN.AS", NETHERLANDS, "abn.as"),
            ("III", UNITED_KINGDOM, "iii.l"),
            ("BT-A", UNITED_KINGDOM, "bt-a.l"),
            ("KGH", GPW, "kgh"),
        ],
    )
    def test_symbols_become_app_tickers(self, symbol: str, market, ticker: str) -> None:
        assert ticker_for(symbol, market) == ticker

    def test_garbage_gives_none(self) -> None:
        assert ticker_for("N/A", US) is None
        assert ticker_for("", UNITED_KINGDOM) is None


# ── Money ─────────────────────────────────────────────────────────────────────


class TestMoney:
    def test_london_quotes_in_pence_and_states_caps_in_pounds(self) -> None:
        assert UNITED_KINGDOM.currency == "GBp"
        assert UNITED_KINGDOM.major_currency == "GBP"
        assert major_currency("GBp") == "GBP"
        assert US.major_currency == "USD"
        assert GPW.major_currency == "PLN"

    def test_every_market_currency_has_a_rate(self) -> None:
        for market in MARKETS:
            assert market.currency in PLN_PER_UNIT
            assert market.major_currency in PLN_PER_UNIT

    def test_a_penny_is_a_hundredth_of_a_pound(self) -> None:
        assert PLN_PER_UNIT["GBp"] == pytest.approx(PLN_PER_UNIT["GBP"] / 100)

    def test_amounts_are_converted_to_zloty(self) -> None:
        assert to_pln(100_000, "PLN") == 100_000
        assert to_pln(30_000, "USD") == pytest.approx(114_000)
        # 2,000,000 pence = £20,000.
        assert to_pln(2_000_000, "GBp") == pytest.approx(102_000)

    def test_an_unknown_currency_is_an_error_not_a_guess(self) -> None:
        with pytest.raises(ValueError):
            to_pln(1.0, "CHF")

    def test_liquidity_floor_on_the_gpw_is_unchanged(self) -> None:
        assert below_liquidity_floor(99_999.0, "PLN")
        assert not below_liquidity_floor(100_000.0, "PLN")

    def test_dollars_are_worth_more_than_zloty(self) -> None:
        # 30,000 USD a day is ~114,000 PLN: liquid enough, although the raw
        # number is under the złoty floor.
        assert not below_liquidity_floor(30_000.0, "USD")
        assert below_liquidity_floor(20_000.0, "USD")

    def test_pence_are_not_pounds(self) -> None:
        # 1,500,000 pence is £15,000 ≈ 76,500 PLN — too thin, however large the
        # raw number looks.
        assert below_liquidity_floor(1_500_000.0, "GBp")
        assert not below_liquidity_floor(2_500_000.0, "GBp")

    def test_market_cap_floor(self) -> None:
        assert not below_market_cap_floor(None, "PLN")
        assert below_market_cap_floor(99_999_999, "PLN")
        assert not below_market_cap_floor(100_000_000, "PLN")
        # 30M USD ≈ 114M PLN passes; the same number in złoty would not.
        assert not below_market_cap_floor(30_000_000, "USD")
        # A pence-quoted company states its cap in pounds: 19M GBP ≈ 97M PLN.
        assert below_market_cap_floor(19_000_000, "GBp")
        assert not below_market_cap_floor(20_000_000, "GBp")


class TestQuoteCurrency:
    def test_a_companys_own_currency_wins(self) -> None:
        # Compass Group trades in dollars on the London exchange (2026-09).
        compass = GpwCompany(ticker="cpg.l", name="Compass Group", currency="USD")
        assert quote_currency(compass) == "USD"

    def test_otherwise_the_markets_currency_applies(self) -> None:
        assert quote_currency(GpwCompany(ticker="hsba.l", name="HSBC")) == "GBp"
        assert quote_currency(GpwCompany(ticker="kgh", name="KGHM")) == "PLN"
        assert quote_currency(GpwCompany(ticker="aapl.us", name="Apple")) == "USD"


# ── Time ──────────────────────────────────────────────────────────────────────


def _at(zone: ZoneInfo, *args: int) -> datetime:
    return datetime(*args, tzinfo=zone)


class TestSessionIsFinal:
    def test_an_earlier_day_is_always_final(self) -> None:
        now = _at(_WARSAW, 2026, 9, 16, 9, 0)
        assert GPW.session_is_final(date(2026, 9, 15), now)

    def test_a_later_day_never_is(self) -> None:
        now = _at(_WARSAW, 2026, 9, 16, 23, 0)
        assert not GPW.session_is_final(date(2026, 9, 17), now)

    def test_gpw_today_needs_the_close_plus_the_settling_buffer(self) -> None:
        day = date(2026, 9, 16)
        assert not GPW.session_is_final(day, _at(_WARSAW, 2026, 9, 16, 16, 0))
        assert not GPW.session_is_final(day, _at(_WARSAW, 2026, 9, 16, 17, 19))
        assert GPW.session_is_final(day, _at(_WARSAW, 2026, 9, 16, 17, 20))
        # The nightly run's own start time.
        assert GPW.session_is_final(day, _at(_WARSAW, 2026, 9, 16, 18, 0))

    def test_us_session_still_open_at_the_warsaw_evening_run(self) -> None:
        # The moment this was observed live: 17:39 Warsaw = 11:39 New York.
        now = _at(_WARSAW, 2026, 9, 16, 17, 39)
        assert not US.session_is_final(date(2026, 9, 16), now)
        # And the European run at 18:00 must not store it either.
        assert not US.session_is_final(date(2026, 9, 16), _at(_WARSAW, 2026, 9, 16, 18, 0))

    def test_us_session_final_after_the_new_york_close(self) -> None:
        # 22:16 Warsaw = 16:16 New York in September (both on summer time).
        assert US.session_is_final(date(2026, 9, 16), _at(_WARSAW, 2026, 9, 16, 22, 16))
        assert not US.session_is_final(date(2026, 9, 16), _at(_WARSAW, 2026, 9, 16, 22, 14))

    def test_the_daylight_saving_gap_is_measured_on_new_yorks_clock(self) -> None:
        # 10 March 2026: New York is already on summer time (since 8 March),
        # Warsaw is not (until 29 March), so the gap is five hours, not six.
        day = date(2026, 3, 10)
        assert not US.session_is_final(day, _at(_WARSAW, 2026, 3, 10, 21, 10))  # 16:10 NY
        assert US.session_is_final(day, _at(_WARSAW, 2026, 3, 10, 21, 20))  # 16:20 NY

    def test_a_late_utc_moment_is_read_in_each_exchanges_own_date(self) -> None:
        # 23:30 UTC on the 16th: 19:30 in New York (the 16th, closed) and
        # 01:30 on the 17th in Warsaw (so the 16th is simply "yesterday").
        now = datetime(2026, 9, 16, 23, 30, tzinfo=UTC)
        assert US.session_is_final(date(2026, 9, 16), now)
        assert GPW.session_is_final(date(2026, 9, 16), now)
        assert not GPW.session_is_final(date(2026, 9, 17), now)

    def test_london_closes_earlier(self) -> None:
        day = date(2026, 9, 16)
        assert not UNITED_KINGDOM.session_is_final(day, _at(_LONDON, 2026, 9, 16, 16, 54))
        assert UNITED_KINGDOM.session_is_final(day, _at(_LONDON, 2026, 9, 16, 16, 55))

    def test_every_european_market_is_final_by_the_1800_warsaw_run(self) -> None:
        run = _at(_WARSAW, 2026, 9, 16, 18, 0)
        for market in MARKETS:
            if market.refresh_run == "europe":
                assert market.session_is_final(date(2026, 9, 16), run), market.id

    def test_the_us_market_belongs_to_its_own_run(self) -> None:
        assert US.refresh_run == "us"
        assert {m.refresh_run for m in MARKETS} == {"europe", "us"}


# ── The STOCKPILOT_MARKETS switch ─────────────────────────────────────────────


class TestEnabledMarkets:
    def test_empty_setting_means_the_gpw_alone(self) -> None:
        assert parse_market_ids("") == ("gpw",)
        assert parse_market_ids(None) == ("gpw",)

    def test_the_gpw_cannot_be_switched_off(self) -> None:
        assert parse_market_ids("us") == ("gpw", "us")

    def test_display_order_and_case_do_not_depend_on_the_setting(self) -> None:
        assert parse_market_ids(" UK, us ,de") == ("gpw", "us", "de", "uk")

    def test_all_switches_everything_on(self) -> None:
        assert parse_market_ids("all") == tuple(m.id for m in MARKETS)

    def test_unknown_ids_are_ignored_and_reported_once(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(markets, "_warned_unknown", set())
        with caplog.at_level(logging.WARNING, logger="app.markets"):
            assert parse_market_ids("us,xx") == ("gpw", "us")
            assert parse_market_ids("us,xx") == ("gpw", "us")
        warnings = [r for r in caplog.records if "xx" in r.getMessage()]
        assert len(warnings) == 1

    def test_enabled_markets_follows_the_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "markets", "gpw")
        assert enabled_markets() == (GPW,)
        assert not is_enabled("us")
        monkeypatch.setattr(settings, "markets", "us,uk")
        assert enabled_markets() == (GPW, US, UNITED_KINGDOM)
        assert is_enabled("uk")
        assert is_enabled("gpw")

    def test_the_default_serves_the_gpw_only(self) -> None:
        # Nothing changes for visitors until a deployment opts in.
        from app.config import Settings

        assert Settings.model_fields["markets"].default == "gpw"
