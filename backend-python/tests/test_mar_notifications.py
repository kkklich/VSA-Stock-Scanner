"""Regression coverage for Polish MAR forms and GPW report discovery."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.db.repository import InMemoryQuoteRepository
from app.services.espi_client import EspiClient, parse_espi_list_html, parse_espi_report_html
from app.services.insider_service import build_insider_response
from app.services.mar_notification_parser import parse_mar_pdf, parse_mar_text

STUB = {
    "publication_date": date(2026, 9, 16),
    "title": "Powiadomienie o transakcjach nabycia w trybie art. 19 MAR",
    "url": "https://www.gpw.pl/komunikat?geru_id=497134",
}

# Standard MAR layout, including the execution and aggregate rows. The aggregate
# must not be counted again, nor may the next row's price become part of a volume.
FORM = """
1 Dane osoby pełniącej obowiązki zarządcze / osoby blisko z nią związanej
a) Nazwa/Nazwisko Jan Testowy
2 Powód powiadomienia
a) Stanowisko/status Wiceprezes Zarządu
b) Powiadomienie pierwotne / zmiana Powiadomienie pierwotne
3 Dane emitenta
a) Nazwa TEST S.A.
4 Szczegółowe informacje dotyczące transakcji
a) Opis instrumentu finansowego Akcje PLTEST000001
b) Rodzaj transakcji Nabycie
c) Cena i wolumen Cena Wolumen
198 PLN 5
198 PLN 7
198 PLN 74
198 PLN 76
198 PLN 4838
d) Informacje zbiorcze
 - Łączny wolumen
 - Cena
5000
198 PLN
e) Data transakcji 2026-09-09
f) Miejsce transakcji XWAR – GPW rynek akcji
* Niepotrzebne skreślić
"""


def test_standard_mar_execution_rows_and_separate_dates():
    (tx,) = parse_mar_text(FORM, STUB)
    assert tx.insider_name == "Jan Testowy"
    assert tx.role == "Wiceprezes Zarządu"
    assert tx.trade_date == date(2026, 9, 9)
    assert tx.publication_date == date(2026, 9, 16)
    assert tx.transaction_type == "buy"
    assert tx.shares == 5000
    assert tx.price == 198
    assert tx.value == 990000
    response = build_insider_response("TEST", transactions=[tx])
    assert response.chart_markers[0].date == "2026-09-16"


def test_multiple_notices_and_directions_remain_separate():
    sell = FORM.replace("Nabycie", "Sprzedaż").replace("2026-09-09", "10.09.2026")
    buy_tx, sell_tx = parse_mar_text(FORM + sell, STUB)
    assert buy_tx.transaction_type == "buy"
    assert sell_tx.transaction_type == "sell"
    assert sell_tx.trade_date == date(2026, 9, 10)


@pytest.mark.parametrize("operation", ["Ustanowienie zastawu", "Otrzymanie darowizny"])
def test_non_market_operations_not_in_buy_sell_summary(operation):
    (tx,) = parse_mar_text(FORM.replace("Nabycie", operation), STUB)
    assert tx.is_open_market is False
    assert build_insider_response("TEST", transactions=[tx]).transactions == []


def test_unknown_trade_date_is_never_the_publication_date():
    tx = parse_espi_report_html("<p>Powiadomienie o nabyciu akcji</p>", STUB)
    assert tx.trade_date is None
    assert tx.publication_date == STUB["publication_date"]
    assert parse_mar_pdf(b"not a pdf", STUB) == []


def test_preparation_date_and_navigation_do_not_change_trade_details():
    html = """<p>Skup akcji własnych – program motywacyjny</p>
    <div class="report-data"><table><tr><td>Data sporządzenia</td>
    <td>2026-09-15</td></tr></table><p>Nabycie akcji</p></div>"""
    tx = parse_espi_report_html(html, STUB)
    assert tx.transaction_type == "buy"
    assert tx.publication_date == date(2026, 9, 16)


def test_actual_gpw_report_url_and_missing_list_date():
    row = """<li><span class="date">16-09-2026 17:07:24</span>
    <strong class="name">CYBER_FOLKS SPÓŁKA AKCYJNA</strong>
    <a href="komunikat?geru_id=497134&amp;title=MAR">więcej</a>
    <p>Powiadomienie w trybie art. 19 MAR</p></li>"""
    (stub,) = parse_espi_list_html(row, "Cyber_Folks")
    assert stub["url"] == "https://www.gpw.pl/komunikat?geru_id=497134&title=MAR"
    assert parse_espi_list_html(row.replace("16-09-2026", "unknown")) == []


@pytest.mark.asyncio
async def test_same_volume_on_distinct_dates_or_prices_is_not_lost():
    (tx,) = parse_mar_text(FORM, STUB)
    different_day = tx.model_copy(update={"trade_date": date(2026, 9, 10)})
    different_price = tx.model_copy(update={"price": 199})
    repo = InMemoryQuoteRepository()
    assert await repo.upsert_insider_transactions("TEST", [tx, different_day, different_price]) == 3
    assert await repo.upsert_insider_transactions("TEST", [tx, different_day, different_price]) == 0


@pytest.mark.asyncio
async def test_exact_issuer_mirror_is_used_when_gpw_blocks_pdf(monkeypatch):
    client = EspiClient()
    filename = "zal01_notice.pdf"
    index = f'<a href="/uploads/DOC.20260916.123.{filename}">PDF</a>'
    get_html = AsyncMock(return_value=index)
    get_pdf = AsyncMock(return_value=b"pdf")
    monkeypatch.setattr(client, "_get_url", get_html)
    monkeypatch.setattr(client, "_get_pdf", get_pdf)
    assert (
        await client._get_issuer_pdf(
            f"https://www.gpw.pl/attachment/{filename},123,20260916", "Cyber_Folks S.A."
        )
        == b"pdf"
    )
    get_pdf.assert_awaited_once_with(
        f"https://investors.cyberfolks.pl/uploads/DOC.20260916.123.{filename}"
    )
    assert (
        await client._get_issuer_pdf(
            "https://www.gpw.pl/attachment/different.pdf,123", "Cyber_Folks S.A."
        )
        is None
    )


@pytest.mark.asyncio
async def test_attachment_details_replace_report_container(monkeypatch):
    client = EspiClient()
    listing = """<li><span class="date">16-09-2026</span>
    <strong class="name">TEST S.A.</strong>
    <a href="komunikat?geru_id=123">Report</a><p>art. 19 MAR</p></li>"""
    report = """<div class="report-data"><p>art. 19 MAR</p>
    <a href="attachment/notice.pdf,123">notice.pdf</a>
    <a href="attachment/notice.pdf,123">notice.pdf</a></div>"""
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=listing))
    monkeypatch.setattr(client, "_get_url", AsyncMock(return_value=report))
    get_pdf = AsyncMock(return_value=b"pdf")
    monkeypatch.setattr(client, "_get_pdf", get_pdf)
    monkeypatch.setattr(
        "app.services.espi_client.parse_mar_pdf", lambda content, stub: parse_mar_text(FORM, stub)
    )
    (tx,) = await client.get_company_insider_transactions("TEST S.A.", "TEST")
    assert tx.shares == 5000
    assert tx.trade_date == date(2026, 9, 9)
    get_pdf.assert_awaited_once()


@pytest.mark.asyncio
async def test_live_transactions_survive_repeat_requests_without_database(monkeypatch):
    from app.routers.stocks import _espi_client, _load_ticker_insider_transactions
    from app.services.cache import TTLCache

    tx, = parse_mar_text(FORM, STUB)
    fetch = AsyncMock(return_value=[tx])
    monkeypatch.setattr(_espi_client, "get_company_insider_transactions", fetch)
    cache = TTLCache()
    kwargs = dict(
        company=None, market="gpw", currency="PLN", repo=None, stooq=None, cache=cache
    )
    assert await _load_ticker_insider_transactions("TEST", **kwargs) == [tx]
    # Date filters must not discard the underlying cached history.
    assert await _load_ticker_insider_transactions(
        "TEST", from_date=date(2026, 9, 17), **kwargs
    ) == []
    assert await _load_ticker_insider_transactions("TEST", **kwargs) == [tx]
    fetch.assert_awaited_once()
