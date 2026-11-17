"""Report incomplete ESPI downloads instead of treating them as no trading."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.models import InsiderTransactionItem
from app.services import espi_pap_reports
from app.services.cache import TTLCache
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
@pytest.mark.parametrize("gpw_report", [None, "<html><title>Access denied</title></html>"])
async def test_failed_gpw_report_is_recovered_from_issuer_archive(monkeypatch, gpw_report):
    client = EspiClient()
    listing = _listing().replace("TEST S.A.", "CYBER_FOLKS S.A.").replace(
        "16-09-2026", "16-09-2026 17:07:24 | Bieżący | ESPI | 034/2026"
    )
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=listing))
    archive = '''<div class="reports__result">
    <a class="reports__result-title" href="/raporty/34-2026/">Raport bieżący 34/2026</a>
    <div class="reports__result-files"><a href="/2026/notice.pdf">PDF</a></div></div>'''
    detail = """<main><h2>Raport bieżący 34/2026</h2><p>16/09/2026 • 17:07</p>
    <p>Temat:</p><p>Powiadomienie art. 19 MAR</p></main>"""
    monkeypatch.setattr(client, "_get_url", AsyncMock(side_effect=[gpw_report, archive, detail]))
    download = AsyncMock(return_value=b"pdf")
    monkeypatch.setattr(client, "_get_pdf", download)
    monkeypatch.setattr(
        "app.services.espi_client.parse_mar_pdf",
        lambda content, stub: [_trade().model_copy(update={"source_url": stub["url"]})],
    )

    (item,) = await client.get_company_insider_transactions("Cyber_Folks S.A.", "CBF")
    assert item.insider_name == "Jan Testowy"
    assert item.shares == 123
    assert item.source_url == "https://www.gpw.pl/komunikat?geru_id=0"
    download.assert_awaited_once_with("https://investors.cyberfolks.pl/2026/notice.pdf")
    assert client.warnings == []


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
async def test_exchange_isin_finds_issuer_and_excludes_similar_companies(monkeypatch):
    client = EspiClient()
    queries = []

    async def search(url, data):
        queries.append(data["searchText"])
        assert data["searchText"] == "PLPKO0000016"
        return (
            _listing().replace("TEST S.A.", "PKO BANK POLSKI S.A. (PLPKO0000016)")
            + _listing().replace("TEST S.A.", "PKO BANK HIPOTECZNY S.A. (PLPKBEX00072)")
        )

    monkeypatch.setattr(client, "_post_form", search)
    monkeypatch.setattr(
        client, "_get_url", AsyncMock(return_value='<div class="report-data">Nabycie akcji</div>')
    )
    items = await client.get_company_insider_transactions(
        "Powszechna Kasa Oszczędności Bank Polski Spółka Akcyjna", "PKO"
    )
    assert queries == ["PLPKO0000016"]
    assert len(items) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("gpw_detail_available", [True, False])
async def test_pap_recovers_a_non_cbf_filing(monkeypatch, gpw_detail_available):
    monkeypatch.setattr(espi_pap_reports, "_archive_pages", TTLCache())
    monkeypatch.setattr(espi_pap_reports, "_report_copies", TTLCache())
    client = EspiClient()
    title = "Powiadomienie art. 19 MAR"
    isin = "PLBH00000012"
    listing = _listing().replace("TEST S.A.", f"BANK HANDLOWY S.A. ({isin})").replace(
        "16-09-2026", "16-09-2026 17:07:24 | Bieżący | ESPI | 043/2026"
    )
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=listing))

    def article(day, url):
        return f"""
        <li class="news"><div class="newsWrapper">
          <a href="{url}"><span class="title">Bank S.A. (43/2026) {title}</span></a>
          <ul class="moreInfo"><li class="date">{day}, 17:07</li>
            <li class="source"><a href="/zrodlo/ESPI">ESPI</a></li>
          </ul>
        </div></li>
        """

    pager = '<ul class="pagination"><li><a href="?page=2">3</a></li></ul>'
    path = "/sites/default/files/attachments/202609/DOC.20260916.123.notice.pdf"
    report = f"""
    <article class="node--view-mode-full">
      <ul class="tags"><li><a>Bank S.A.-{isin}-BHANDLOWY</a></li>
        <li><a>43/2026</a></li></ul>
      <div class="attachments"><a href="{path}">PDF</a>
        <a href="https://example.com{path}">External PDF</a></div>
    </article>
    """
    pap = "https://pap-mediaroom.pl"
    gpw = "https://www.gpw.pl"
    html = {
        f"{pap}/zrodlo/ESPI?page=0": article("17.09.2026", "/newer") + pager,
        f"{pap}/zrodlo/ESPI?page=1": (
            article("16.09.2026", "/other-bank") + article("16.09.2026", "/matched") + pager
        ),
        f"{pap}/other-bank": report.replace(isin, "PLPKO0000016"),
        f"{pap}/matched": report,
    }
    if gpw_detail_available:
        html[f"{gpw}/komunikat?geru_id=0"] = (
            '<div class="report-data"><a href="attachment/notice.pdf,123">PDF</a></div>'
        )
    monkeypatch.setattr(client, "_get_url", AsyncMock(side_effect=html.get))

    async def download(url):
        return b"published PDF" if url == pap + path else None

    monkeypatch.setattr(client, "_get_pdf", AsyncMock(side_effect=download))
    monkeypatch.setattr(
        "app.services.espi_client.parse_mar_pdf",
        lambda content, stub: [_trade().model_copy(update={"source_url": stub["url"]})],
    )
    (tx,) = await client.get_company_insider_transactions("Bank Handlowy S.A.", "BHW")
    assert tx.shares == 123
    assert tx.source_url == f"{gpw}/komunikat?geru_id=0"
    assert client.warnings == []


@pytest.mark.asyncio
async def test_issuer_correction_replaces_only_the_referenced_trade(monkeypatch):
    client = EspiClient()
    original, correction = _listing(2).removeprefix("<ul>").removesuffix("</ul>").split("</li>")[:2]
    original = original.replace("16-09-2026", "16-09-2026 | Bieżący | ESPI | 3/2026")
    correction = correction.replace("16-09-2026", "17-09-2026 | Bieżący | ESPI | 4/2026")
    correction = correction.replace("Powiadomienie", "Otrzymanie korekty zawiadomienia")
    listing = f"<ul>{correction}</li>{original}</li></ul>"
    monkeypatch.setattr(client, "_post_form", AsyncMock(return_value=listing))

    async def report(url):
        context = (
            "Korekta dotyczy powiadomienia w raporcie bieżącym ESPI nr 3/2026."
            if "geru_id=1" in url else ""
        )
        return f'<div class="report-data">{context}<a href="attachment/notice.pdf">PDF</a></div>'

    def read_pdf(content, stub):
        tx = _trade().model_copy(update={
            "publication_date": stub["publication_date"], "source_url": stub["url"],
        })
        if stub["geru_id"] == "1":
            return [tx]
        return [
            tx.model_copy(update={"shares": 120, "value": 1200}),
            tx.model_copy(update={"insider_name": "Inny Insider"}),
        ]

    monkeypatch.setattr(client, "_get_url", report)
    monkeypatch.setattr(client, "_get_pdf", AsyncMock(return_value=b"pdf"))
    monkeypatch.setattr("app.services.espi_client.parse_mar_pdf", read_pdf)
    items = await client.get_company_insider_transactions("TEST S.A.", "TEST")
    assert [(item.insider_name, item.shares) for item in items] == [
        ("Jan Testowy", 123), ("Inny Insider", 123),
    ]
    from app.services.insider_screen_service import summarize_insider_activity

    old = _trade().model_copy(update={
        "source_url": "https://www.gpw.pl/espi-ebi-report?geru_id=0", "value": 1200,
    })
    assert summarize_insider_activity([old, *items]).purchases_value_pln == 2460
