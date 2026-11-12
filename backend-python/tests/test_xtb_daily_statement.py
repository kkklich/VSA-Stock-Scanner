"""Regression coverage for encrypted XTB DailyStatement portfolio imports."""

from io import BytesIO

import pytest
from pydantic import SecretStr
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from app.config import settings
from app.services.portfolio import PortfolioError
from app.services.xtb_daily_statement import parse_xtb_daily_statement
from tests import test_xtb_import

client = test_xtb_import.client
automation_portfolio = test_xtb_import.automation_portfolio

PASSWORD = "synthetic-statement-password"
ACCOUNT_ID = "10000000"


def statement(*, side="kupna", count=1, repeat=False, account_id=ACCOUNT_ID):
    def columns(*cells):
        return "".join(f"{cell:<24}" for cell in cells).rstrip()

    header = columns(
        "Nr",
        "Numer zlecenia",
        "Symbol, którego",
        "Nazwa",
        "Wolumen",
        "Data i czas",
        "Zlecenie",
        "Cena",
        "Cena całkowita",
        "Klasa aktywów",
        "Waluta",
        "Kurs",
        "Koszty",
        "Prowizja",
        "Łączne koszty",
    )
    row = columns(
        "1",
        "100010001",
        "NVD.DE",
        "Example stock",
        "0,5000",
        "02.01.2026",
        "rynkowe",
        "110,50",
        "55,25",
        "Prawa ułamkowe",
        "EUR",
        "4.1234",
        "-0,25",
        "0,00",
        "-0,25",
    )
    continuation = columns("", "", "", "", "", "13:10:30", "", "", "", "dot. akcji")
    lines = [
        "Potwierdzenie zleceń wykonanych w dniu 02.01.2026",
        columns("Imię i nazwisko", "Konto", "Waluta rachunku", "Saldo"),
        columns("Test Investor", account_id, "PLN", "0,00"),
        f"Wykonane zlecenia {side} Praw Ułamkowych ({count})",
        header,
        row,
        continuation,
    ]
    if repeat:
        lines.extend([row, continuation])

    # Courier keeps the column positions predictable. Declare the Polish glyphs
    # explicitly so the generated PDF has searchable text without external fonts.
    glyphs = {
        "ą": "aogonek",
        "ę": "eogonek",
        "ł": "lslash",
        "Ł": "Lslash",
        "ń": "nacute",
        "ó": "oacute",
        "ż": "zdotaccent",
    }
    differences = ArrayObject()
    for letter, glyph in glyphs.items():
        differences.extend([NumberObject(letter.encode("cp1250")[0]), NameObject(f"/{glyph}")])
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Courier"),
            NameObject("/Encoding"): DictionaryObject(
                {
                    NameObject("/BaseEncoding"): NameObject("/WinAnsiEncoding"),
                    NameObject("/Differences"): differences,
                }
            ),
        }
    )
    writer = PdfWriter()
    page = writer.add_blank_page(width=2100, height=300)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        }
    )
    stream = DecodedStreamObject()
    encoded_lines = [f"<{line.encode('cp1250').hex()}> Tj T*" for line in lines]
    stream.set_data(("BT /F1 9 Tf 14 TL 20 270 Td\n" + "\n".join(encoded_lines) + "\nET").encode())
    page[NameObject("/Contents")] = stream
    writer.encrypt(PASSWORD, algorithm="AES-128")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def post_statement(client, content):
    return client.post(
        "/api/portfolios/imports/xtb/automation",
        content=content,
        headers={
            "Authorization": f"Bearer {test_xtb_import.AUTOMATION_TOKEN}",
            "X-Import-Filename": "DailyStatement.pdf",
        },
    )


@pytest.fixture
def linked_automation_portfolio(client, automation_portfolio):
    updated = client.patch(
        f"/api/portfolios/{automation_portfolio['id']}",
        json={
            "name": automation_portfolio["name"],
            "broker": "XTB",
            "brokerAccountId": ACCOUNT_ID,
            "costMethod": automation_portfolio["costMethod"],
            "version": automation_portfolio["version"],
        },
    )
    assert updated.status_code == 200, updated.text
    return updated.json()


def test_daily_statement_preserves_leading_zero_in_account_id():
    parsed = parse_xtb_daily_statement(
        statement(account_id="00123456"), PASSWORD, test_xtb_import.Companies()
    )
    assert parsed.broker_account_id == "00123456"


def test_daily_statement_rejects_invalid_account_id():
    with pytest.raises(PortfolioError) as raised:
        parse_xtb_daily_statement(
            statement(account_id="unknown"), PASSWORD, test_xtb_import.Companies()
        )
    assert raised.value.code == "import_statement_broker_account_missing"


def test_encrypted_statement_purchase_is_saved_once(
    client, linked_automation_portfolio, monkeypatch
):
    monkeypatch.setattr(settings, "xtb_statement_password", SecretStr(PASSWORD))
    monkeypatch.setattr(settings, "xtb_automation_portfolio_id", None)
    pdf = statement()
    first = post_statement(client, pdf)
    assert first.status_code == 200, first.text
    assert first.json()["imported"] == 1
    assert first.json()["warnings"] == ["fx_cost_not_imported"]
    retry = post_statement(client, pdf)
    assert retry.status_code == 200, retry.text
    assert (retry.json()["duplicates"], retry.json()["imported"]) == (1, 0)
    [saved] = client.get("/api/portfolios").json()["items"][0]["transactions"]
    assert saved["ticker"] == "nvd.de"
    assert saved["currency"] == "EUR"
    assert saved["quantity"] == "0.5000"
    assert saved["price"] == "110.50"
    assert saved["executedAt"] == "2026-01-02T13:10:30.000000"


@pytest.mark.parametrize(
    ("options", "password", "code"),
    [
        ({}, "incorrect", "import_statement_password_invalid"),
        ({"count": 2}, PASSWORD, "import_invalid_daily_statement"),
        ({"count": 2, "repeat": True}, PASSWORD, "import_statement_ambiguous_fill"),
    ],
)
def test_invalid_statement_saves_nothing(
    client, automation_portfolio, monkeypatch, options, password, code
):
    monkeypatch.setattr(settings, "xtb_statement_password", SecretStr(password))
    result = post_statement(client, statement(**options))
    assert result.status_code == 422, result.text
    assert result.json()["detail"]["code"] == code
    assert client.get("/api/portfolios").json()["items"][0]["transactions"] == []


def test_sale_only_statement_is_a_noop(client, linked_automation_portfolio, monkeypatch):
    monkeypatch.setattr(settings, "xtb_statement_password", SecretStr(PASSWORD))
    result = post_statement(client, statement(side="sprzedaży"))
    assert result.status_code == 200, result.text
    assert (result.json()["imported"], result.json()["ignoredSales"]) == (0, 1)
