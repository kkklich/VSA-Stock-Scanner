"""The shipped Polish catalogue covers imported stocks without relaxing validation."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.markets import normalize_ticker
from app.services.gpw_company_service import GpwCompanyService
from app.services.portfolio import holdings
from app.services.xtb_import import _company, prepare_import
from app.services.xtb_wallet_import import parse_xtb_wallets
from tests.test_xtb_wallet_import import BUY_TIME, OPEN_HEADERS, workbook

CATALOGUE = Path(__file__).resolve().parents[1] / "app/data/gpw-companies.json"


@pytest.mark.parametrize("symbol", ["CRQ.PL", "S2B.PL", "1AT.PL", "3RG.PL", "CAR.PL"])
def test_requested_and_new_polish_stocks_resolve_through_the_real_import_catalogue(symbol):
    company = _company(symbol, GpwCompanyService())
    assert company.ticker == symbol[:-3].lower()
    assert company.market == "gpw"
    assert company.currency == "PLN"
    assert company.name.strip()


def test_open_wallet_accepts_requested_stocks_and_preserves_small_execution_prices():
    rows = [
        ["IKE", "example-crq", "CRQ.PL", "STOCK", "BUY", 7, 0, 0, 0.0001, BUY_TIME, 0],
        ["IKE", "example-s2b", "S2B.PL", "STOCK", "BUY", 4, 0, 0, 0.001, BUY_TIME, 0],
    ]
    data = workbook(("Open Positions", OPEN_HEADERS, rows))
    wallets = parse_xtb_wallets(data, "example.xlsx", GpwCompanyService())
    assert len(wallets) == 1
    wallet = wallets[0]
    assert wallet["error"] is None
    plan = prepare_import(wallet["parsed"], [], "fifo")
    assert plan["ready"] == 2
    assert plan["errors"] == 0
    assert plan["ledgerError"] is None
    trades = {trade["ticker"]: trade for trade in plan["ledger"]}
    assert set(trades) == {"crq", "s2b"}
    assert trades["crq"]["quantity"] == "7"
    assert trades["crq"]["price"] == "0.0001"
    assert trades["s2b"]["quantity"] == "4"
    assert trades["s2b"]["price"] == "0.001"
    positions = {position["ticker"]: position for position in holdings(plan["ledger"], "fifo")}
    assert positions["crq"]["cost"] == Decimal("0.0007")
    assert positions["s2b"]["cost"] == Decimal("0.004")


def test_shipped_polish_catalogue_has_unique_normalized_tickers_and_complete_labels():
    rows = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    assert rows
    tickers = [row["ticker"] for row in rows]
    assert len(tickers) == len(set(tickers))
    for row in rows:
        assert {"ticker", "name", "sector"} <= row.keys()
        assert normalize_ticker(row["ticker"]) == row["ticker"]
        assert "." not in row["ticker"]
        assert isinstance(row["name"], str) and row["name"] == row["name"].strip()
        assert row["name"]
        assert row["sector"] is None or isinstance(row["sector"], str)
    loaded = GpwCompanyService().get_companies("gpw")
    assert {company.ticker for company in loaded} == set(tickers)
