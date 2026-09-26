"""Unit and API tests for insider transactions (Yahoo Finance + GPW ESPI MAR Art. 19)."""

from __future__ import annotations

from datetime import date
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.db.repository import InMemoryQuoteRepository
from app.dependencies import get_quote_repository
from app.main import app
from app.models.stocks import InsiderTransactionItem
from app.services.espi_client import (
    is_mar19_title,
    parse_espi_list_html,
    parse_espi_report_html,
)
from app.services.insider_service import build_insider_response
from app.services.yahoo_finance_client import (
    _classify_yahoo_trade,
    _parse_insider_frame,
)


def test_classify_yahoo_trade() -> None:
    tx_type, is_open = _classify_yahoo_trade(
        "Purchase at price 145.50 per share.", "", 145.50
    )
    assert tx_type == "buy"
    assert is_open is True

    tx_type, is_open = _classify_yahoo_trade(
        "Sale at price 210.25 - 212.00 per share.", "", 211.125
    )
    assert tx_type == "sell"
    assert is_open is True

    tx_type, is_open = _classify_yahoo_trade(
        "Stock Award(Grant) at price 0.00 per share.", "", 0.0
    )
    assert tx_type == "grant"
    assert is_open is False

    tx_type, is_open = _classify_yahoo_trade("Stock Gift", "", None)
    assert tx_type == "gift"
    assert is_open is False


def test_parse_yahoo_insider_frame() -> None:
    df = pd.DataFrame(
        [
            {
                "Shares": 10000,
                "Value": 1500000.0,
                "URL": "https://sec.gov/filing/1",
                "Text": "Purchase at price 150.00 per share.",
                "Insider": "SMITH JOHN",
                "Position": "Chief Executive Officer",
                "Transaction": "",
                "Start Date": "2026-03-10",
                "Ownership": "D",
            },
            {
                "Shares": 5000,
                "Value": 0.0,
                "URL": "",
                "Text": "Stock Award(Grant) at price 0.00 per share.",
                "Insider": "DOE JANE",
                "Position": "Director",
                "Transaction": "",
                "Start Date": "2026-03-08",
                "Ownership": "D",
            },
        ]
    )
    items = _parse_insider_frame(df, "AAPL")
    assert len(items) == 2

    buy_item = items[0]
    assert buy_item.transaction_type == "buy"
    assert buy_item.is_open_market is True
    assert buy_item.shares == 10000
    assert buy_item.price == 150.0
    assert buy_item.value == 1500000.0
    assert buy_item.role == "Chief Executive Officer"
    assert buy_item.publication_date == date(2026, 3, 10)
    assert buy_item.source == "yahoo"

    grant_item = items[1]
    assert grant_item.transaction_type == "grant"
    assert grant_item.is_open_market is False


def test_espi_is_mar19_title_filters_correctly() -> None:
    assert is_mar19_title(
        "Powiadomienie o transakcjach, o których mowa w art. 19 ust. 1 rozporządzenia MAR"
    )
    assert is_mar19_title(
        "Zawiadomienie osoby pełniącej obowiązki zarządcze (art. 19 MAR)"
    )
    assert not is_mar19_title(
        "Zawiadomienie w trybie art. 69 ustawy o ofercie publicznej o zmianie udziału"
    )
    assert not is_mar19_title("Skup akcji własnych - raport tygodniowy")


def test_parse_espi_list_and_report_html() -> None:
    list_html = """
    <ul>
      <li>
        <span class="date">15-03-2026 14:22:10 | Bieżący | ESPI | 12/2026</span>
        <strong class="name"><a href="espi-ebi-report?geru_id=481001&amp;title=Powiadomienie">CD PROJEKT S.A.</a></strong>
        <p>Powiadomienie o transakcjach, o których mowa w art. 19 ust. 1 rozporządzenia MAR</p>
      </li>
      <li>
        <span class="date">14-03-2026 10:00:00 | Bieżący | ESPI | 11/2026</span>
        <strong class="name"><a href="espi-ebi-report?geru_id=481000&amp;title=Art69">CD PROJEKT S.A.</a></strong>
        <p>Zawiadomienie w trybie art. 69 ustawy o ofercie publicznej</p>
      </li>
    </ul>
    """
    # parse_espi_list_html automatically filters to MAR Art. 19 stubs only
    stubs = parse_espi_list_html(list_html)
    assert len(stubs) == 1
    assert stubs[0]["geru_id"] == "481001"
    assert stubs[0]["publication_date"] == date(2026, 3, 15)

    report_html = """
    <html>
      <body>
        <div class="report-content">
          <p>Zarząd spółki CD PROJEKT S.A. informuje o otrzymaniu powiadomienia w trybie art. 19 ust. 1 MAR.</p>
          <p>Osoba pełniąca obowiązki zarządcze: Jan Kowalski - Prezes Zarządu</p>
          <p>Rodzaj transakcji: Nabycie akcji na rynku regulowanym GPW</p>
          <p>Data transakcji: 2026-03-14</p>
          <p>Wolumen: 15 000 szt.</p>
          <p>Cena: 142,50 PLN</p>
        </div>
      </body>
    </html>
    """
    tx = parse_espi_report_html(
        report_html,
        stub=stubs[0],
    )
    assert tx.transaction_type == "buy"
    assert tx.is_open_market is True
    assert tx.shares == 15000
    assert tx.price == 142.50
    assert tx.value == 15000 * 142.50
    assert tx.publication_date == date(2026, 3, 15)
    assert tx.role == "Prezes Zarządu"
    assert tx.source == "espi"


def test_build_insider_response_daily_aggregation_and_filtering() -> None:
    txs = [
        InsiderTransactionItem(
            trade_date=date(2026, 4, 1),
            publication_date=date(2026, 4, 2),
            insider_name="Jan Kowalski",
            role="Prezes Zarządu",
            transaction_type="buy",
            is_open_market=True,
            shares=10000,
            price=50.0,
            currency="PLN",
            value=500000.0,
            source="espi",
        ),
        InsiderTransactionItem(
            trade_date=date(2026, 4, 1),
            publication_date=date(2026, 4, 2),
            insider_name="Anna Nowak",
            role="Członek Zarządu",
            transaction_type="buy",
            is_open_market=True,
            shares=5000,
            price=50.0,
            currency="PLN",
            value=250000.0,
            source="espi",
        ),
        InsiderTransactionItem(
            trade_date=date(2026, 4, 5),
            publication_date=date(2026, 4, 6),
            insider_name="Piotr Wiśniewski",
            role="Członek Rady Nadzorczej",
            transaction_type="sell",
            is_open_market=True,
            shares=2000,
            price=55.0,
            currency="PLN",
            value=110000.0,
            source="espi",
        ),
        InsiderTransactionItem(
            trade_date=date(2026, 4, 7),
            publication_date=date(2026, 4, 7),
            insider_name="Jan Kowalski",
            role="Prezes Zarządu",
            transaction_type="grant",
            is_open_market=False,
            shares=20000,
            price=0.0,
            currency="PLN",
            value=0.0,
            source="espi",
        ),
    ]

    resp = build_insider_response(
        "CDR",
        name="CD PROJEKT",
        market="gpw",
        currency="PLN",
        transactions=txs,
        include_all=False,
    )

    # Grant is filtered out when include_all=False
    assert len(resp.transactions) == 3
    assert resp.summary.total_purchases_count == 2
    assert resp.summary.total_sales_count == 1
    assert resp.summary.total_purchases_shares == 15000
    assert resp.summary.total_sales_shares == 2000
    assert resp.summary.net_shares == 13000
    assert resp.summary.net_value == 640000.0

    # Two same-day buys on 2026-04-02 are merged into one chart marker
    assert len(resp.chart_markers) == 2
    m1 = resp.chart_markers[0]
    assert m1.date == "2026-04-02"
    assert m1.type == "Bullish"
    assert m1.label == "INS +15k"
    assert m1.shares == 15000
    assert m1.transaction_count == 2
    assert "Prezes Zarządu" in m1.roles
    assert "Członek Zarządu" in m1.roles

    m2 = resp.chart_markers[1]
    assert m2.date == "2026-04-06"
    assert m2.type == "Bearish"
    assert m2.label == "INS -2k"
    assert m2.shares == 2000


@pytest.mark.asyncio
async def test_in_memory_repo_and_api_endpoint() -> None:
    repo = InMemoryQuoteRepository()
    await repo.upsert_insider_transactions(
        "PKO",
        [
            InsiderTransactionItem(
                trade_date=date(2026, 3, 20),
                publication_date=date(2026, 3, 21),
                insider_name="Prezes PKO",
                role="Prezes Zarządu",
                transaction_type="buy",
                is_open_market=True,
                shares=4500,
                price=60.0,
                currency="PLN",
                value=270000.0,
                source="espi",
                source_url="https://www.gpw.pl/espi-ebi-report?geru_id=123",
            )
        ],
    )

    app.dependency_overrides[get_quote_repository] = lambda: repo
    try:
        with TestClient(app) as client:
            res = client.get("/api/stocks/PKO/insider-transactions")
            assert res.status_code == 200
            payload = res.json()
            assert payload["ticker"] == "PKO"
            assert payload["summary"]["totalPurchasesCount"] == 1
            assert payload["summary"]["totalPurchasesShares"] == 4500
            assert len(payload["chartMarkers"]) == 1
            assert payload["chartMarkers"][0]["label"] == "INS +4.5k"
            assert payload["chartMarkers"][0]["type"] == "Bullish"
    finally:
        app.dependency_overrides.pop(get_quote_repository, None)


def test_scheduler_registers_12_00_insider_refresh() -> None:
    from app.jobs.daily_ingest import INSIDER_JOB_ID, build_scheduler

    class _DummyRefresh:
        async def run(self, **_kwargs) -> None:
            pass

        async def run_insider_refresh(self) -> None:
            pass

    scheduler = build_scheduler(_DummyRefresh())
    job = scheduler.get_job(INSIDER_JOB_ID)
    assert job is not None
    trigger_str = str(job.trigger)
    assert "hour='12'" in trigger_str
    assert "minute='0'" in trigger_str

