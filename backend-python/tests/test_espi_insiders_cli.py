"""Check financial totals and the user's CLI report/export workflow."""

import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import AsyncMock

import pytest

from app.models import InsiderTransactionItem
from scripts import espi_insiders as cli


def trade(**changes) -> InsiderTransactionItem:
    values = {
        "publication_date": date(2026, 10, 10),
        "trade_date": date(2026, 9, 15),
        "insider_name": "Jan Testowy",
        "role": "Prezes Zarządu",
        "transaction_type": "buy",
        "shares": 100,
        "price": 12.5,
        "currency": "PLN",
        "source": "espi",
        "source_url": "https://www.gpw.pl/komunikat?geru_id=123",
    }
    return InsiderTransactionItem(**(values | changes))


def test_person_totals_keep_currencies_separate_and_exclude_gifts_and_unnamed_people():
    summaries = cli.summarize_transactions([
        trade(),
        trade(insider_name="  JAN   testowy  ", shares=25, price=10),
        trade(transaction_type="sell", shares=40, price=15),
        trade(currency="EUR", shares=8, price=4),
        trade(transaction_type="gift", shares=9000, price=0),
        trade(insider_name=None, shares=700),
    ])
    assert len(summaries) == 2
    by_currency = {row.currency: row for row in summaries}
    assert by_currency["PLN"].buy_shares == 125
    assert by_currency["PLN"].sell_shares == 40
    assert by_currency["PLN"].net_shares == 85
    assert by_currency["PLN"].buy_value == Decimal("1500")
    assert by_currency["PLN"].sell_value == Decimal("600")
    assert by_currency["EUR"].buy_shares == 8
    assert by_currency["EUR"].buy_value == Decimal("32")


def test_unknown_totals_stay_unknown_and_known_zero_price_stays_zero():
    unknown, = cli.summarize_transactions([
        trade(shares=None, price=10),
        trade(shares=20, price=10),
        trade(transaction_type="sell", shares=5, price=0),
    ])
    assert unknown.buy_shares is None
    assert unknown.buy_value is None
    assert unknown.net_shares is None
    assert unknown.sell_shares == 5
    assert unknown.sell_value == Decimal(0)

    missing_value, = cli.summarize_transactions([trade(price=None)])
    assert missing_value.buy_shares == 100
    assert missing_value.buy_value is None
    assert cli.transaction_value(trade(value=0, price=100)) == Decimal(0)


def test_html_escapes_report_content_and_rejects_javascript_source_urls():
    report = cli.render_html(
        '<script>alert("title")</script>',
        [trade(
            insider_name='<img src=x onerror="alert(1)">',
            role="<b>zarząd</b>",
            source_url="javascript:alert('source')",
        ), trade(insider_name="SOURCE_0")],
        ["<script>alert('warning')</script>"],
        "<em>scope</em>",
    )
    assert "<script>" not in report
    assert "<img " not in report
    assert "<b>zarząd</b>" not in report
    assert "javascript:" not in report
    assert "&lt;script&gt;" in report
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in report
    assert "&lt;em&gt;scope&lt;/em&gt;" in report
    assert "<td>SOURCE_0</td>" in report


def test_csv_has_polish_decimals_bom_and_preserves_unknown_vs_zero(tmp_path):
    output = tmp_path / "transakcje.csv"
    cli.write_csv(output, [
        trade(insider_name="=NieUruchamiaj()", shares=None, price=None, trade_date=None),
        trade(shares=0, price=0, value=0),
        trade(shares=3, price=12.125),
    ])
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(StringIO(output.read_text(encoding="utf-8-sig")), delimiter=";"))
    assert rows[0]["Liczba akcji"] == ""
    assert rows[0]["Cena za akcję"] == ""
    assert rows[0]["Wartość"] == ""
    assert rows[0]["Data transakcji"] == ""
    assert rows[0]["Osoba / podmiot"] == "'=NieUruchamiaj()"
    assert rows[1]["Liczba akcji"] == "0"
    assert Decimal(rows[1]["Cena za akcję"].replace(",", ".")) == 0
    assert Decimal(rows[1]["Wartość"].replace(",", ".")) == 0
    assert rows[2]["Cena za akcję"] == "12,125"
    assert rows[2]["Wartość"] == "36,375"


def test_main_exports_only_matching_person_and_actual_trade_dates(monkeypatch, tmp_path, capsys):
    load = AsyncMock(return_value=(
        "Insiderzy GPW — TEST",
        [
            trade(trade_date=date(2026, 9, 1), shares=111),
            trade(
                trade_date=date(2026, 8, 31), publication_date=date(2026, 9, 5),
                transaction_type="sell", shares=222,
            ),
            trade(insider_name="Anna Testowa", shares=333),
            trade(trade_date=None, shares=444),
        ],
        [],
        "Odczyt testowy.",
    ))
    monkeypatch.setattr(cli, "load_transactions", load)
    html_file, csv_file = tmp_path / "raport.html", tmp_path / "raport.csv"

    result = cli.main([
        "--ticker", "TEST", "--insider", "jAN", "--from", "2026-09-01",
        "--to", "2026-09-30", "--html", str(html_file), "--csv", str(csv_file),
    ])

    assert result == 0
    load.assert_awaited_once()
    rows = list(csv.DictReader(StringIO(csv_file.read_text(encoding="utf-8-sig")), delimiter=";"))
    assert len(rows) == 1
    assert rows[0]["Liczba akcji"] == "111"
    assert rows[0]["Data transakcji"] == "2026-09-01"
    assert rows[0]["Publikacja"] == "2026-10-10"
    report = html_file.read_text(encoding="utf-8")
    assert "Jan Testowy" in report
    assert "Anna Testowa" not in report
    assert "Filtr dat pominął 1 rekordów" in report
    assert "Filtr osoby/podmiotu: jAN" in report
    assert "Zakupy i sprzedaż według osoby" in capsys.readouterr().out


@pytest.mark.parametrize(("arguments", "message"), [
    (["--pdf", "powiadomienie.pdf"], "--published"),
    (["--ticker", "TEST", "--open"], "--open wymaga --html"),
])
def test_required_options_fail_before_loading(monkeypatch, capsys, arguments, message):
    load = AsyncMock()
    monkeypatch.setattr(cli, "load_transactions", load)
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 2
    assert message in capsys.readouterr().err
    load.assert_not_awaited()
