"""Only share transactions may contribute to Polish insider share quantities."""

from datetime import date

import pytest

from app.services.mar_notification_parser import parse_mar_text

STUB = {
    "publication_date": date(2026, 9, 16),
    "title": "Powiadomienie w trybie art. 19 MAR",
}
PERSON = """
1 Dane osoby pełniącej obowiązki zarządcze
a) Nazwa/Nazwisko Jan Testowy
2 Powód powiadomienia
a) Stanowisko/status Prezes Zarządu
b) Powiadomienie pierwotne
3 Dane emitenta
a) Nazwa TEST S.A.
"""


def transaction(instrument: str | None, operation: str = "Nabycie") -> str:
    description = f"a) Opis instrumentu finansowego {instrument}" if instrument else ""
    return f"""
4 Szczegółowe informacje dotyczące transakcji
{description}
b) Rodzaj transakcji {operation}
c) Cena i wolumen
20 PLN 100
d) Informacje zbiorcze
100 20 PLN
e) Data transakcji 2026-09-15
f) Miejsce transakcji GPW
"""


@pytest.mark.parametrize("operation, direction", [("Nabycie", "buy"), ("Sprzedaż", "sell")])
def test_stock_quantities_and_direction_are_preserved(operation, direction):
    (tx,) = parse_mar_text(PERSON + transaction("Akcje zwykłe PLTEST000001", operation), STUB)
    assert tx.insider_name == "Jan Testowy"
    assert tx.transaction_type == direction
    assert tx.is_open_market is True
    assert tx.shares == 100
    assert tx.value == 2000


@pytest.mark.parametrize(
    "instrument",
    [
        "Obligacje serii A PLTEST000002",
        "Bonds PLTEST000002",
        "Opcje na akcje TEST S.A.",
        "Stock options",
        "Warranty subskrypcyjne na akcje TEST S.A.",
        "Certyfikaty inwestycyjne",
        "Kontrakty terminowe na akcje",
        "Jednostki uczestnictwa funduszu",
        "Prawa poboru akcji",
    ],
)
def test_explicit_non_share_instruments_do_not_become_share_purchases(instrument):
    assert parse_mar_text(PERSON + transaction(instrument), STUB) == []


@pytest.mark.parametrize("instrument", [None, "PLTEST000001", "Instrument emitenta"])
def test_unspecified_or_unclear_instrument_keeps_existing_behavior(instrument):
    (tx,) = parse_mar_text(PERSON + transaction(instrument), STUB)
    assert tx.shares == 100


@pytest.mark.parametrize("bonds_first", [True, False])
def test_each_transaction_uses_its_own_preceding_instrument(bonds_first):
    stock = transaction("Akcje zwykłe PLTEST000001", "Sprzedaż")
    bond = transaction("Obligacje serii A PLTEST000002")
    blocks = bond + stock if bonds_first else stock + bond
    (tx,) = parse_mar_text(PERSON + blocks, STUB)
    assert tx.transaction_type == "sell"
    assert tx.shares == 100


def test_previous_bond_description_does_not_filter_a_later_unspecified_block():
    blocks = transaction("Obligacje serii A") + transaction(None, "Sprzedaż")
    (tx,) = parse_mar_text(PERSON + blocks, STUB)
    assert tx.transaction_type == "sell"
    assert tx.shares == 100
