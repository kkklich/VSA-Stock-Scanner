"""Tests for the company-list builder (scripts/build_market_universe.py).

No network: the HTTP client and ``yfinance.Ticker`` are fakes. What is pinned
is the part a quarterly rebuild depends on — reading the member tables,
spelling symbols the way Yahoo does, the verification rules, and a written file
the company service can load.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yfinance

from app.markets import FRANCE, GERMANY, UNITED_KINGDOM, US
from app.services.gpw_company_service import GpwCompanyService
from scripts import build_market_universe as builder

# ── Fakes ─────────────────────────────────────────────────────────────────────


class _Response:
    def __init__(self, text: str = "", payload: dict | None = None) -> None:
        self.text = text
        self._payload = payload

    def raise_for_status(self) -> _Response:
        return self

    def json(self) -> dict:
        return self._payload or {}


class _Client:
    """Serves canned responses per URL, in order when a URL has several."""

    def __init__(self, responses: dict[str, list[_Response]]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def get(self, url: str, headers: dict | None = None) -> _Response:
        self.calls.append(url)
        queue = self._responses[url]
        return queue.pop(0) if len(queue) > 1 else queue[0]


def _table(header: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table id="constituents"><tr>{head}</tr>{body}</table>'


def _page(header: list[str], rows: list[list[str]]) -> _Response:
    return _Response(text=f"<html><body><p>intro</p>{_table(header, rows)}</body></html>")


# ── Symbols ───────────────────────────────────────────────────────────────────


class TestCleanSymbol:
    @pytest.mark.parametrize(
        ("raw", "market", "expected"),
        [
            ("BT.A", UNITED_KINGDOM, "BT-A"),
            ("BP.", UNITED_KINGDOM, "BP"),
            ("III", UNITED_KINGDOM, "III"),
            # Listed under another market's suffix: look for the local line.
            ("AIR.PA", GERMANY, "AIR"),
            ("MT.AS", FRANCE, "MT"),
            # The market's own suffix is left for ticker_for to remove.
            ("SAP.DE", GERMANY, "SAP.DE"),
            # US share classes are turned into Yahoo's hyphen by ticker_for.
            ("BRK.B", US, "BRK.B"),
            (" aapl ", US, "AAPL"),
        ],
    )
    def test_spelling(self, raw: str, market, expected: str) -> None:
        assert builder.clean_symbol(raw, market) == expected


# ── Member lists ──────────────────────────────────────────────────────────────


class TestMemberLists:
    def test_the_named_column_is_read_and_footnotes_dropped(self) -> None:
        url = builder.WIKIPEDIA["ftse100"][0]
        client = _Client(
            {
                url: [
                    _page(
                        ["Company", "Ticker", "Sector"],
                        [
                            ["3i", "III", "Financials"],
                            ["BT Group", "BT.A <sup>[1]</sup>", "Telecoms"],
                            ["", "", ""],
                        ],
                    )
                ]
            }
        )
        members = builder.wikipedia_members("ftse100", client)
        assert [m.symbol for m in members] == ["III", "BT.A"]
        assert {m.index_id for m in members} == {"ftse100"}

    def test_a_changed_layout_is_an_error_not_an_empty_list(self) -> None:
        url = builder.WIKIPEDIA["dax"][0]
        client = _Client({url: [_page(["Company", "Symbol"], [["SAP", "SAP.DE"]])]})
        with pytest.raises(RuntimeError, match="Ticker"):
            builder.wikipedia_members("dax", client)

    def test_a_suspiciously_short_list_is_refused(self) -> None:
        url = builder.WIKIPEDIA["aex"][0]
        client = _Client({url: [_page(["Ticker", "Company"], [["ASML.AS", "ASML"]])]})
        with pytest.raises(RuntimeError, match="only 1 members"):
            builder.fetch_members("aex", client)

    def test_nasdaqs_intermittent_empty_answer_is_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(builder.time, "sleep", lambda _s: None)
        empty = _Response(payload={"data": None, "status": {"rCode": 200}})
        full = _Response(payload={"data": {"data": {"rows": [{"symbol": "AAPL"}]}}})
        client = _Client({builder.NASDAQ_100_URL: [empty, empty, full]})
        members = builder.nasdaq_100_members(client)
        assert [m.symbol for m in members] == ["AAPL"]
        assert len(client.calls) == 3

    def test_members_of_both_us_indices_are_merged(self) -> None:
        url = builder.WIKIPEDIA["sp500"][0]
        sp500 = [["AAPL", "Apple"], ["BRK.B", "Berkshire"]] + [
            [f"S{i}", "x"] for i in range(460)
        ]
        ndx = [{"symbol": "AAPL"}, {"symbol": "ASML"}] + [
            {"symbol": f"N{i}"} for i in range(95)
        ]
        client = _Client(
            {
                url: [_page(["Symbol", "Security"], sp500)],
                builder.NASDAQ_100_URL: [
                    _Response(payload={"data": {"data": {"rows": ndx}}})
                ],
            }
        )
        build = builder.collect_members(US, client)
        assert build.members["aapl.us"] == ["sp500", "ndx"]
        assert build.members["brk-b.us"] == ["sp500"]
        assert build.members["asml.us"] == ["ndx"]


# ── Verification ──────────────────────────────────────────────────────────────


def _bars(traded: int) -> pd.DataFrame:
    index = pd.date_range("2026-09-01", periods=traded, freq="D", tz="Europe/London")
    return pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1000}, index=index
    )


_GOOD_INFO = {
    "longName": "HSBC Holdings plc",
    "sector": "Financial Services",
    "industry": "Banks - Diversified",
    "country": "United Kingdom",
    "currency": "GBp",
    "exchange": "LSE",
    "marketCap": 259_123_183_616,
    "fullTimeEmployees": 206_161,
    "website": "https://www.hsbc.com",
    "longBusinessSummary": "A bank.",
}


@pytest.fixture
def fake_yahoo(monkeypatch: pytest.MonkeyPatch):
    state: dict = {"info": dict(_GOOD_INFO), "bars": _bars(10), "asked": []}

    class _Ticker:
        def __init__(self, symbol: str) -> None:
            state["asked"].append(symbol)
            self.info = state["info"]

        def history(self, **_kwargs):
            return state["bars"]

    monkeypatch.setattr(yfinance, "Ticker", _Ticker)
    return state


class TestVerify:
    def test_a_real_company_is_kept_with_its_profile(self, fake_yahoo) -> None:
        outcome = builder.verify("hsba.l", ["ftse100"], UNITED_KINGDOM)
        assert fake_yahoo["asked"] == ["HSBA.L"]
        assert outcome.reason is None
        assert outcome.company == {
            "ticker": "hsba.l",
            "symbol": "HSBA.L",
            "name": "HSBC Holdings plc",
            "sector": "Financial Services",
            "industry": "Banks - Diversified",
            "country": "United Kingdom",
            "exchange": "LSE",
            "currency": "GBp",
            "marketCap": 259_123_183_616,
            "employees": 206_161,
            "website": "https://www.hsbc.com",
            "description": "A bank.",
            "indices": ["ftse100"],
        }

    def test_too_few_recent_sessions_is_rejected(self, fake_yahoo) -> None:
        fake_yahoo["bars"] = _bars(builder.MIN_RECENT_BARS - 1)
        outcome = builder.verify("hsba.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is None
        assert "traded sessions" in outcome.reason

    def test_no_name_is_rejected(self, fake_yahoo) -> None:
        fake_yahoo["info"] = {**_GOOD_INFO, "longName": None, "shortName": ""}
        outcome = builder.verify("hsba.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is None
        assert "name" in outcome.reason

    def test_a_member_without_a_sector_is_kept(self, fake_yahoo) -> None:
        # Yahoo leaves the sector blank for real FTSE 100 members (3i Group,
        # the investment trusts); the index already proves they exist.
        fake_yahoo["info"] = {**_GOOD_INFO, "sector": None}
        outcome = builder.verify("iii.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is not None
        assert outcome.company["sector"] is None

    def test_a_line_quoted_in_dollars_keeps_its_own_currency(self, fake_yahoo) -> None:
        # Compass Group is quoted in USD on the London exchange.
        fake_yahoo["info"] = {**_GOOD_INFO, "currency": "USD"}
        outcome = builder.verify("cpg.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is not None
        assert outcome.company["currency"] == "USD"

    def test_a_currency_the_app_cannot_convert_is_rejected(self, fake_yahoo) -> None:
        fake_yahoo["info"] = {**_GOOD_INFO, "currency": "CHF"}
        outcome = builder.verify("hsba.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is None
        assert "CHF" in outcome.reason

    def test_a_zero_market_cap_is_stored_as_unknown(self, fake_yahoo) -> None:
        # Yahoo answered 0 for Michelin (2026-09); a zero would fail the floor.
        fake_yahoo["info"] = {**_GOOD_INFO, "marketCap": 0}
        outcome = builder.verify("hsba.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is not None
        assert outcome.company["marketCap"] is None


# ── The whole market ──────────────────────────────────────────────────────────


class TestBuildMarket:
    def test_written_file_loads_in_the_app(
        self, fake_yahoo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        url = builder.WIKIPEDIA["ftse100"][0]
        rows = [["HSBC", "HSBA"], ["Dead plc", "DEAD"]] + [
            [f"C{i}", f"C{i}X"] for i in range(95)
        ]
        client = _Client({url: [_page(["Company", "Ticker"], rows)]})

        real_verify = builder.verify

        def verify(ticker, indices, market):
            if ticker == "dead.l":
                return builder.Outcome("DEAD.L", indices, reason="gone")
            if ticker.startswith("c"):
                return builder.Outcome(ticker.upper(), indices, reason="skipped in test")
            return real_verify(ticker, indices, market)

        monkeypatch.setattr(builder, "verify", verify)
        payload = builder.build_market(UNITED_KINGDOM, client, log=lambda _m: None)

        assert [c["ticker"] for c in payload["companies"]] == ["hsba.l"]
        assert {"symbol": "DEAD.L", "indices": ["ftse100"], "reason": "gone"} in payload[
            "rejected"
        ]
        assert payload["market"] == "uk"
        assert payload["sources"] == {"ftse100": url}

        path = builder.write_market(payload, tmp_path)
        assert json.loads(path.read_text(encoding="utf-8"))["companies"][0]["name"] == (
            "HSBC Holdings plc"
        )
        service = GpwCompanyService(markets_dir=tmp_path)
        [hsbc] = service.get_companies("uk")
        assert (hsbc.ticker, hsbc.currency, hsbc.exchange) == ("hsba.l", "GBp", "LSE")

    def test_a_failed_download_leaves_the_existing_file_alone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        existing = tmp_path / "nl.json"
        existing.write_text('{"companies": []}', encoding="utf-8")
        monkeypatch.setattr(builder, "OUTPUT_DIR", tmp_path)

        def broken(*_args, **_kwargs):
            raise RuntimeError("no constituents table")

        monkeypatch.setattr(builder, "build_market", broken)
        assert builder.main(["nl"]) == 1
        assert existing.read_text(encoding="utf-8") == '{"companies": []}'
        assert "NOT rebuilt" in capsys.readouterr().out

    def test_only_index_markets_can_be_built(self) -> None:
        with pytest.raises(SystemExit):
            builder.main(["gpw"])


class TestRetryRejected:
    def test_only_the_rejected_members_are_checked_again(
        self, fake_yahoo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        previous = {
            "market": "uk",
            "generatedAt": "2026-09-01",
            "companies": [{"ticker": "bp.l", "name": "BP p.l.c."}],
            "rejected": [
                # A Yahoo symbol a rate-limited run could not check.
                {"symbol": "HSBA.L", "indices": ["ftse100"], "reason": "Too Many Requests"},
                # A source spelling that never mapped (and still does not).
                {"symbol": "N/A", "indices": ["ftse100"], "reason": "not a UK symbol"},
                # Already verified since — not asked for again.
                {"symbol": "BP.L", "indices": ["ftse100"], "reason": "Too Many Requests"},
            ],
        }
        payload = builder.retry_rejected(UNITED_KINGDOM, previous, log=lambda _m: None)

        assert fake_yahoo["asked"] == ["HSBA.L"]
        assert [c["ticker"] for c in payload["companies"]] == ["bp.l", "hsba.l"]
        assert [r["symbol"] for r in payload["rejected"]] == ["N/A"]
        # The list keeps its original date and says when it was patched.
        assert payload["generatedAt"] == "2026-09-01"
        assert "updatedAt" in payload

    def test_a_source_spelling_is_retried_on_the_local_line(self, fake_yahoo) -> None:
        previous = {
            "companies": [],
            "rejected": [{"symbol": "AIR.PA", "indices": ["dax"], "reason": "x"}],
        }
        fake_yahoo["info"] = {**_GOOD_INFO, "currency": "EUR", "exchange": "GER"}
        payload = builder.retry_rejected(GERMANY, previous, log=lambda _m: None)
        assert fake_yahoo["asked"] == ["AIR.DE"]
        assert payload["companies"][0]["exchange"] == "Xetra"


class TestRateLimits:
    def test_a_rate_limit_waits_longer_than_an_ordinary_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        waits: list[float] = []
        monkeypatch.setattr(builder.time, "sleep", waits.append)
        calls = {"n": 0}

        class _Flaky:
            def __init__(self, _symbol: str) -> None:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("Too Many Requests. Rate limited. Try after a while.")
                if calls["n"] == 2:
                    raise RuntimeError("connection reset")
                self.info = dict(_GOOD_INFO)

            def history(self, **_kwargs):
                return _bars(10)

        monkeypatch.setattr(yfinance, "Ticker", _Flaky)
        outcome = builder.verify("hsba.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is not None
        assert waits == [builder._RATE_LIMIT_WAIT_SECONDS[0], builder._ERROR_WAIT_SECONDS[1]]

    def test_giving_up_is_reported_with_the_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(builder.time, "sleep", lambda _s: None)

        class _Limited:
            def __init__(self, _symbol: str) -> None:
                raise RuntimeError("Too Many Requests")

        monkeypatch.setattr(yfinance, "Ticker", _Limited)
        outcome = builder.verify("hsba.l", ["ftse100"], UNITED_KINGDOM)
        assert outcome.company is None
        assert "Too Many Requests" in outcome.reason
