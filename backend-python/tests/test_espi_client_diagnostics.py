"""Report incomplete ESPI downloads instead of treating them as no trading."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.models import InsiderTransactionItem
from app.services.espi_client import EspiClient


def _listing(count: int = 1) -> str:
    return "<ul>" + "".join(
        f'<li><span class="date">16-09-2026</span>'
        f'<strong class="name">TEST S.A.</strong>'
        f'<a href="komunikat?geru_id={number}">Report</a>'
        '<p>Powiadomienie art. 19 MAR</p></li>'
        for number in range(count)
    ) + "</ul>"


def _trade() -> InsiderTransactionItem:
    return InsiderTransactionItem(
        publication_date=date(2026, 9, 16),
        trade_date=date(2026, 9, 15),
        insider_name="Jan Testowy",
        transaction_type="buy",
        shares=123,
        price=10,
        currency="PLN",
        value=1230,
        source="espi",
    )


@pytest.mark.asyncio
async def test_failed_search_is_distinct_from_empty_search_and_warnings_reset(monkeypatch):
    client = EspiClient()
    monkeypatch.setattr(client, "_post_form", AsyncMock(side_effect=[None, "<ul></ul>"]))

    assert await client.get_company_insider_transactions("TEST S.A.", "TEST") == []
    assert any("Nie udało się pobrać listy" in warning for warning in client.warnings)

    assert await client.get_company_insider_transactions("TEST S.A.", "TEST") == []
    assert client.warnings == []


@pytest.mark.asyncio
async def test_blocked_search_page_is_not_treated_as_no_transactions(monkeypatch):
    client = EspiClient()
    monkeypatch.setattr(
        client, "_post_form", AsyncMock(return_value="<title>Request Rejected</title>")
    )
    assert await client.get_company_insider_transactions("TEST S.A.", "TEST") == []
    assert client.warnings


@pytest.mark.asyncio
async def test_report_limit_is_configurable_and_reports_truncation(monkeypatch):
    client = EspiClient()
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=_listing(3)))
    get_report = AsyncMock(return_value='<div class="report-data">Nabycie akcji</div>')
    monkeypatch.setattr(client, "_get_url", get_report)

    items = await client.get_company_insider_transactions("TEST S.A.", "TEST", report_limit=2)
    assert len(items) == 2
    assert get_report.await_count == 2
    assert any("2 z 3" in warning for warning in client.warnings)


@pytest.mark.asyncio
async def test_failed_report_download_is_visible(monkeypatch):
    client = EspiClient()
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=_listing()))
    monkeypatch.setattr(client, "_get_url", AsyncMock(return_value=None))

    assert await client.get_company_insider_transactions("TEST S.A.", "TEST") == []
    assert any("Nie udało się pobrać raportu:" in warning for warning in client.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize("unreadable", [None, b"scan"])
async def test_one_readable_pdf_does_not_hide_failed_or_scanned_attachments(
    monkeypatch, unreadable
):
    client = EspiClient()
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=_listing()))
    monkeypatch.setattr(
        client,
        "_get_url",
        AsyncMock(
            return_value='<div class="report-data">'
            '<a href="attachment/one.pdf">one</a>'
            '<a href="attachment/two.pdf">two</a></div>'
        ),
    )
    monkeypatch.setattr(client, "_get_pdf", AsyncMock(side_effect=[b"good", unreadable]))
    monkeypatch.setattr(client, "_get_issuer_pdf", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.espi_client.parse_mar_pdf",
        lambda content, stub: [_trade()] if content == b"good" else [],
    )

    items = await client.get_company_insider_transactions("TEST S.A.", "TEST")
    assert len(items) == 1
    assert items[0].shares == 123
    assert len(client.warnings) == 1
    assert "two.pdf" in client.warnings[0]
    assert "one.pdf" not in client.warnings[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(("limit", "report_limit"), [(0, 1), (1, 0), (-1, 1)])
async def test_non_positive_limits_fail_before_downloading(monkeypatch, limit, report_limit):
    client = EspiClient()
    fetch = AsyncMock()
    monkeypatch.setattr(client, "_post_form", fetch)
    with pytest.raises(ValueError, match="większe od zera"):
        await client.get_company_insider_transactions(
            "TEST S.A.", "TEST", limit=limit, report_limit=report_limit
        )
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejected_pdf_is_not_reintroduced_as_a_share_trade_from_html(monkeypatch):
    client = EspiClient()
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=_listing()))
    monkeypatch.setattr(
        client, "_get_url", AsyncMock(return_value=(
            '<div class="report-data"><p>Nabycie: wolumen 1000 sztuk</p>'
            '<a href="attachment/bonds.pdf">Obligacje</a></div>'
        )),
    )
    monkeypatch.setattr(client, "_get_pdf", AsyncMock(return_value=b"bond notification"))
    monkeypatch.setattr("app.services.espi_client.parse_mar_pdf", lambda content, stub: [])

    assert await client.get_company_insider_transactions("TEST S.A.", "TEST") == []
    assert any("inny instrument niż akcje" in warning for warning in client.warnings)


@pytest.mark.asyncio
async def test_issuer_abbreviation_can_be_found_by_ticker(monkeypatch):
    client = EspiClient()
    queries = []

    async def search(url, data):
        queries.append(data["searchText"])
        if data["searchText"] == "PKO":
            return _listing().replace("TEST S.A.", "PKO BANK POLSKI S.A.")
        return "<ul></ul>"

    monkeypatch.setattr(client, "_post_form", search)
    monkeypatch.setattr(client, "_get_url", AsyncMock(return_value="<p>Nabycie akcji</p>"))
    items = await client.get_company_insider_transactions(
        "Powszechna Kasa Oszczędności Bank Polski Spółka Akcyjna", "PKO"
    )
    assert queries == ["Powszechna", "PKO"]
    assert len(items) == 1
