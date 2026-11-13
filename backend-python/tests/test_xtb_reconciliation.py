"""A linked XTB snapshot corrects holdings without adding fictitious trades."""

import io
from datetime import datetime

import openpyxl
import pytest

from tests.test_portfolios import client as portfolio_client
from tests.test_portfolios import trade
from tests.test_xtb_wallet_import import CLOSED_HEADERS, OPEN_HEADERS
from tests.test_xtb_wallet_import import closed as closed_position

URL = "/api/portfolios/imports/xtb/wallets"
PARAMS = {"filename": "example.xlsx"}
OWNER = {"X-Expected-User-Id": "1"}


@pytest.fixture
def client():
    yield from portfolio_client.__wrapped__()


def report(
    *,
    position=12345,
    aggregate_quantity=10,
    cash_account="example-account",
    open_account="example-report",
    cash_currency=None,
    open_currency=None,
    include_closed=False,
):
    book = openpyxl.Workbook()
    cash = book.active
    cash.title = "Cash Operations"
    cash.append(["Account number", cash_account])
    if cash_currency:
        cash.append(["Account currency", cash_currency])
    cash.append(["Date to (UTC)", datetime(2026, 1, 5, 12)])
    cash.append(
        [
            "Type",
            "Instrument",
            "Ticker",
            "Category",
            "Time",
            "Amount",
            "ID",
            "Comment",
            "Product",
            "Position ID",
        ]
    )
    cash.append(
        [
            "Stock purchase",
            "Example",
            "KGH.PL",
            "STOCK",
            datetime(2026, 1, 2, 12),
            -200,
            "10001",
            "OPEN BUY KGH.PL 2 @ 100",
            "IKE",
            "12345",
        ]
    )
    opened = book.create_sheet("Open Positions")
    opened.append(["Account number", open_account])
    if open_currency:
        opened.append(["Account currency", open_currency])
    opened.append(["Data as of report generated", datetime(2026, 1, 5, 12, 0, 0, 500000)])
    opened.append(OPEN_HEADERS)
    opened.append(["IKE", "Example", "KGH.PL", "STOCK", "", aggregate_quantity])
    opened.append(
        ["IKE", position, "KGH.PL", "", "BUY", 10, 300, 30, 20, datetime(2026, 1, 2, 12), 0]
    )
    opened.append(["IKE", "Added", "CRQ.PL", "STOCK", "", 1])
    opened.append(["IKE", 88888, "CRQ.PL", "", "BUY", 1, 10, 10, 0.1, datetime(2026, 1, 3, 12), 0])
    if include_closed:
        closed = book.create_sheet("Closed Positions", 0)
        closed.append(["Account number", cash_account])
        closed.append(CLOSED_HEADERS)
        closed.append(closed_position())
    data = io.BytesIO()
    book.save(data)
    return data.getvalue()


def preview(client, body):
    response = client.post(URL + "/preview", params=PARAMS, headers=OWNER, content=body)
    assert response.status_code == 200, response.text
    return response.json()


def cash_wallet(client):
    return next(
        w for w in client.get("/api/portfolios").json()["items"] if w["name"] == "Cash Operations"
    )


def test_snapshot_reconciles_cash_wallet_and_preserves_history_and_future_sales(client):
    body = report()
    plan = preview(client, body)
    assert plan["ready"] == 1
    assert plan["errors"] == 0
    assert plan["skippedSheets"] == []
    assert len(plan["wallets"]) == 1
    changes = {entry["ticker"]: entry for entry in plan["wallets"][0]["reconciliation"]["changes"]}
    assert changes["kgh"]["previousQuantity"] == "2"
    assert changes["kgh"]["quantity"] == "10"
    assert changes["crq"]["previousQuantity"] == "0"
    assert changes["crq"]["quantity"] == "1"
    saved = client.post(
        URL, params=PARAMS, content=body, headers={**OWNER, "X-XTB-Preview": plan["previewToken"]}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["created"] == 1
    assert saved.json()["imported"] == 1
    wallet = cash_wallet(client)
    assert len(wallet["transactions"]) == 1
    assert wallet["transactions"][0]["quantity"] == "2"
    assert "ledger" not in wallet
    positions = {p["ticker"]: p for p in wallet["positions"]}
    assert (positions["kgh"]["quantity"], positions["kgh"]["cost"]) == (10, 200)
    assert (positions["crq"]["quantity"], positions["crq"]["cost"]) == (1, 0.1)

    historical = trade(client, wallet, date="2026-01-04")
    assert historical.status_code == 409
    assert historical.json()["detail"]["code"] == "xtb_snapshot_locked"
    deletion = client.delete(
        f"/api/portfolios/{wallet['id']}/transactions/{wallet['transactions'][0]['id']}",
        params={"version": wallet["version"]},
    )
    assert deletion.status_code == 409
    sale = trade(client, wallet, date="2026-01-06", side="sell", quantity="3", price="30", fees="0")
    assert sale.status_code == 201, sale.text
    assert len(sale.json()["transactions"]) == 2
    after = next(p for p in cash_wallet(client)["positions"] if p["ticker"] == "kgh")
    assert (after["quantity"], after["cost"], after["realizedPnl"]) == (7, 140, 30)


@pytest.mark.parametrize("position", [12345, 54321])
def test_full_export_uses_one_wallet_when_open_account_differs(client, position):
    body = report(
        position=position,
        cash_account="00123456",
        open_account="00123457",
        include_closed=True,
    )
    plan = preview(client, body)
    assert plan["newWallets"] == plan["ready"] == 1
    [wallet] = plan["wallets"]
    assert wallet["brokerAccountId"] == "00123456"
    matching_lots = position == 12345
    assert bool(wallet["reconciliation"]) == matching_lots
    assert plan["skippedSheets"] == (
        ["Closed Positions"] if matching_lots else ["Closed Positions", "Open Positions"]
    )

    headers = {**OWNER, "X-XTB-Preview": plan["previewToken"]}
    for created in (1, 0):
        saved = client.post(URL, params=PARAMS, content=body, headers=headers)
        assert saved.status_code == 200, saved.text
        assert saved.json()["created"] == saved.json()["imported"] == created
    [saved] = client.get("/api/portfolios").json()["items"]
    assert len(saved["transactions"]) == 1
    positions = {p["ticker"]: p["quantity"] for p in saved["positions"]}
    assert positions == ({"kgh": 10, "crq": 1} if matching_lots else {"kgh": 2})


@pytest.mark.parametrize(
    "settings",
    [
        {"position": 54321},
        {"aggregate_quantity": 11},
        {"cash_account": "00123456", "open_account": "00123457"},
    ],
)
def test_unlinked_or_inconsistent_snapshot_cannot_change_cash_holdings(client, settings):
    plan = preview(client, report(**settings))
    cash = plan["wallets"][0]
    assert cash["reconciliation"] is None
    assert "xtb_reconciliation_unavailable" in cash["warnings"]


def test_open_positions_in_another_account_currency_do_not_reconcile_cash_wallet(client):
    body = report(cash_account="00123456", cash_currency="PLN", open_currency="EUR")
    plan = preview(client, body)
    wallets = {wallet["sheet"]: wallet for wallet in plan["wallets"]}
    assert wallets["Open Positions"]["brokerAccountCurrency"] == "EUR"
    cash = wallets["Cash Operations"]
    assert cash["brokerAccountCurrency"] == "PLN"
    assert cash["reconciliation"] is None
    assert "xtb_reconciliation_unavailable" in cash["warnings"]
