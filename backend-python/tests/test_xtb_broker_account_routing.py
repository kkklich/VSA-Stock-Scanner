"""XTB imports link and route wallets by their broker account IDs."""

from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.config import settings
from tests import test_xtb_import as reports
from tests import test_xtb_wallet_endpoints as worksheets
from tests import test_xtb_wallet_import as native

client = reports.client
ACCOUNT = "001234"
OTHER_ACCOUNT = "005678"


def account_csv(account):
    return f"Account number,{account}\n".encode("ascii") + reports.AUTOMATION_CSV


def linked_wallet(client, account):
    response = client.post(
        "/api/portfolios",
        json={
            "id": str(uuid4()),
            "name": "Brokerage",
            "broker": "XTB",
            "brokerAccountId": account,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def configure_automation(monkeypatch, owner):
    monkeypatch.setattr(settings, "xtb_automation_token", SecretStr(reports.AUTOMATION_TOKEN))
    monkeypatch.setattr(settings, "xtb_automation_user_id", owner)
    monkeypatch.setattr(settings, "xtb_automation_portfolio_id", None)


def test_spreadsheet_import_links_selected_wallet_and_rejects_account_mismatch(client):
    wallet = reports.create(client)
    report = account_csv(ACCOUNT)

    preview = reports.preview(client, wallet, report, filename="history.csv")
    assert preview.status_code == 200, preview.text
    assert preview.json()["sourceBrokerAccountId"] == ACCOUNT
    assert preview.json()["brokerAccountId"] == ACCOUNT
    assert preview.json()["linksBrokerAccount"] is True
    assert worksheets.portfolios(client)[0]["brokerAccountId"] is None

    committed = reports.commit(client, wallet, report, filename="history.csv")
    assert committed.status_code == 200, committed.text
    assert committed.json()["imported"] == 1
    [saved] = worksheets.portfolios(client)
    assert saved["brokerAccountId"] == ACCOUNT
    assert len(saved["transactions"]) == 1

    wrong_report = account_csv(OTHER_ACCOUNT)
    for upload in (reports.preview, reports.commit):
        mismatch = upload(client, saved, wrong_report, filename="history.csv")
        assert mismatch.status_code == 409, mismatch.text
        assert mismatch.json()["detail"]["code"] == "broker_account_mismatch"
    assert worksheets.portfolios(client) == [saved]


def test_automation_routes_only_within_configured_owner(client, monkeypatch):
    own_wallet = linked_wallet(client, ACCOUNT)
    client.owner.id = 2
    other_wallet = linked_wallet(client, ACCOUNT)
    linked_wallet(client, OTHER_ACCOUNT)
    configure_automation(monkeypatch, owner=1)

    accepted = reports.automation_request(client, account_csv(ACCOUNT))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["imported"] == 1
    assert all(not wallet["transactions"] for wallet in worksheets.portfolios(client))
    assert other_wallet["id"] in {wallet["id"] for wallet in worksheets.portfolios(client)}

    not_owned = reports.automation_request(client, account_csv(OTHER_ACCOUNT))
    assert not_owned.status_code == 404, not_owned.text
    assert not_owned.json()["detail"]["code"] == "broker_account_unlinked"
    client.owner.id = 1
    [saved] = worksheets.portfolios(client)
    assert saved["id"] == own_wallet["id"]
    assert len(saved["transactions"]) == 1


@pytest.mark.parametrize(
    ("report", "status", "code"),
    [
        (reports.AUTOMATION_CSV, 422, "broker_account_required"),
        (account_csv(OTHER_ACCOUNT), 404, "broker_account_unlinked"),
    ],
)
def test_automation_requires_a_linked_report_account(client, monkeypatch, report, status, code):
    linked_wallet(client, ACCOUNT)
    configure_automation(monkeypatch, owner=client.owner.id)

    rejected = reports.automation_request(client, report)
    assert rejected.status_code == status, rejected.text
    assert rejected.json()["detail"]["code"] == code
    assert all(not wallet["transactions"] for wallet in worksheets.portfolios(client))


def test_worksheet_preview_uses_one_cash_ledger_and_skips_supplemental_snapshots(client):
    metadata = ["Account number", ACCOUNT]
    report = worksheets.workbook(
        {
            "Closed Positions": [metadata, native.CLOSED_HEADERS, native.closed()],
            "Cash Operations": [metadata, reports.HEADERS, reports.cash()],
            "Open Positions": [metadata, native.OPEN_HEADERS, native.opened()],
        }
    )

    preview = worksheets.preview(client, report)
    assert preview["errors"] == 0
    assert {wallet["sourceBrokerAccountId"] for wallet in preview["wallets"]} == {ACCOUNT}
    assert preview["skippedSheets"] == ["Closed Positions", "Open Positions"]
    [plan] = preview["wallets"]
    assert plan["name"] == "Cash Operations"
    assert plan["brokerAccountId"] == ACCOUNT
    assert plan["linksBrokerAccount"] is True
    assert plan["brokerAccountCurrency"] == "PLN"
    assert worksheets.portfolios(client) == []

    committed = worksheets.upload(client, report, token=preview["previewToken"])
    assert committed.status_code == 200, committed.text
    assert committed.json()["created"] == 1
    [wallet] = worksheets.portfolios(client)
    assert wallet["brokerAccountId"] == ACCOUNT
    assert wallet["brokerAccountCurrency"] == "PLN"
    assert len(wallet["transactions"]) == 1


def test_full_workbook_routes_by_cash_and_closed_account_when_open_header_differs(client):
    def report(reference):
        return worksheets.workbook(
            {
                "Closed Positions": [
                    ["Account number", ACCOUNT], native.CLOSED_HEADERS, native.closed(),
                ],
                "Cash Operations": [
                    ["Account number", ACCOUNT], reports.HEADERS, reports.cash(reference),
                ],
                "Open Positions": [
                    ["Account number", OTHER_ACCOUNT], native.OPEN_HEADERS, native.opened(),
                ],
            }
        )

    first_file = report("first-operation")
    preview = worksheets.preview(client, first_file)
    assert preview["newWallets"] == 1
    assert preview["skippedSheets"] == ["Closed Positions", "Open Positions"]
    [plan] = preview["wallets"]
    assert plan["brokerAccountId"] == ACCOUNT
    assert plan["ready"] == 1
    assert plan["reconciliation"] is None
    committed = worksheets.upload(client, first_file, token=preview["previewToken"])
    assert committed.status_code == 200, committed.text
    assert committed.json()["created"] == 1

    next_file = report("next-operation")
    updated = worksheets.preview(client, next_file)
    assert updated["newWallets"] == 0
    [destination] = updated["wallets"]
    assert destination["id"] == plan["id"]
    assert destination["ready"] == 1
    assert destination["brokerAccountId"] == ACCOUNT


def test_updated_report_routes_by_account_and_keeps_distinct_account_currencies(client):
    own_wallet = linked_wallet(client, ACCOUNT)
    report = worksheets.workbook(
        {
            "Cash Operations": [["Account number", ACCOUNT], reports.HEADERS, reports.cash()],
            "Open Positions": [["Account number", ACCOUNT], native.OPEN_HEADERS, native.opened()],
            "EUR account": [
                ["Account number", OTHER_ACCOUNT],
                reports.HEADERS,
                reports.cash("eur-1", currency="EUR"),
            ],
        }
    )
    preview = worksheets.preview(client, report)
    assert preview["newWallets"] == 1
    assert preview["skippedSheets"] == ["Open Positions"]
    first, second = preview["wallets"]
    assert first["id"] == own_wallet["id"] and first["brokerAccountCurrency"] == "PLN"
    assert second["brokerAccountCurrency"] == "EUR"

    committed = worksheets.upload(client, report, token=preview["previewToken"])
    assert committed.status_code == 200, committed.text
    assert committed.json()["imported"] == 2
    assert committed.json()["created"] == 1
    retry = worksheets.upload(client, report, token=preview["previewToken"])
    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicates"] == 2

    updated = worksheets.workbook(
        {
            "Cash Operations": [
                ["Account number", ACCOUNT],
                reports.HEADERS,
                reports.cash(),
                reports.cash("new-2"),
            ],
        }
    )
    next_preview = worksheets.preview(client, updated)
    assert next_preview["newWallets"] == 0
    assert next_preview["ready"] == 1
    assert next_preview["wallets"][0]["id"] == own_wallet["id"]
    saved = worksheets.upload(client, updated, token=next_preview["previewToken"])
    assert saved.status_code == 200, saved.text
    wallets = {row["brokerAccountCurrency"]: row for row in worksheets.portfolios(client)}
    assert len(wallets["PLN"]["transactions"]) == 2
    assert wallets["EUR"]["transactions"][0]["currency"] == "PLN"


def test_explicit_target_is_owner_scoped_and_rejects_different_report_currency(client):
    wallet = linked_wallet(client, ACCOUNT)
    other = linked_wallet(client, OTHER_ACCOUNT)
    data = worksheets.workbook({"Report": [reports.HEADERS, reports.cash()]})
    preview = worksheets.preview(client, data, target=wallet["id"])
    wrong_target = worksheets.upload(
        client, data, token=preview["previewToken"], target=other["id"]
    )
    assert wrong_target.status_code == 409, wrong_target.text
    assert wrong_target.json()["detail"]["code"] == "import_preview_changed"
    saved = worksheets.upload(client, data, token=preview["previewToken"], target=wallet["id"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["created"] == 0

    wrong_currency = worksheets.workbook(
        {"Report": [reports.HEADERS, reports.cash(currency="EUR")]}
    )
    rejected = worksheets.upload(client, wrong_currency, target=wallet["id"])
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "broker_account_currency_mismatch"
    client.owner.id = 2
    assert worksheets.upload(client, data, target=wallet["id"]).status_code == 404


def test_open_positions_can_initialize_empty_matched_wallet(client):
    wallet = linked_wallet(client, ACCOUNT)
    metadata = [["Account number", ACCOUNT], ["Account currency", "PLN"]]
    report = worksheets.workbook(
        {
            "Cash Operations": [*metadata, reports.HEADERS],
            "Open Positions": [*metadata, native.OPEN_HEADERS, native.opened()],
        }
    )
    plan = worksheets.preview(client, report)
    assert plan["newWallets"] == 0
    assert plan["ready"] == 1
    assert plan["wallets"][0]["id"] == wallet["id"]
    assert plan["skippedSheets"] == ["Cash Operations"]
    committed = worksheets.upload(client, report, token=plan["previewToken"])
    assert committed.status_code == 200, committed.text
    retry = worksheets.upload(client, report, token=plan["previewToken"])
    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicates"] == 1
    [saved] = worksheets.portfolios(client)
    assert saved["positions"][0]["quantity"] == 2

    cash_report = worksheets.workbook(
        {
            "Cash Operations": [*metadata, reports.HEADERS, reports.cash()],
        }
    )
    [cash_plan] = worksheets.preview(client, cash_report)["wallets"]
    assert cash_plan["ledgerError"] == "import_snapshot_history_conflict"


def test_worksheet_title_does_not_turn_executed_trades_into_a_snapshot(client):
    wallet = linked_wallet(client, ACCOUNT)
    headers = ["ID", "Type", "Time", "Ticker", "Quantity", "Price", "Currency"]
    report = worksheets.workbook(
        {"Open Positions": [headers, ["1", "Buy", "2026-01-02", "KGH.PL", 2, 100, "PLN"]]}
    )
    preview = worksheets.preview(client, report, target=wallet["id"])
    assert preview["skippedSheets"] == []
    assert preview["ready"] == 1
    assert preview["newWallets"] == 0


def test_unidentified_cash_sections_with_same_currency_are_ambiguous(client):
    report = worksheets.workbook(
        {
            "Cash Operations": [reports.HEADERS, reports.cash("one")],
            "Cash History": [reports.HEADERS, reports.cash("two")],
        }
    )
    rejected = worksheets.upload(client, report)
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["detail"]["code"] == "import_ambiguous_wallet"


def test_reupload_links_existing_worksheet_wallet_without_duplicating_its_trade(client):
    report = worksheets.workbook(
        {"Cash Operations": [["Account number", ACCOUNT], reports.HEADERS, reports.cash()]}
    )
    first_preview = worksheets.preview(client, report)
    first = worksheets.upload(client, report, token=first_preview["previewToken"])
    assert first.status_code == 200, first.text
    assert first.json()["created"] == first.json()["imported"] == 1
    retry = worksheets.upload(client, report, token=first_preview["previewToken"])
    assert retry.status_code == 200, retry.text
    assert retry.json()["created"] == retry.json()["imported"] == 0
    assert retry.json()["duplicates"] == 1
    [wallet] = worksheets.portfolios(client)

    unlinked = client.patch(
        f"/api/portfolios/{wallet['id']}",
        json={
            "name": wallet["name"],
            "broker": wallet["broker"],
            "costMethod": wallet["costMethod"],
            "version": wallet["version"],
            "brokerAccountId": None,
        },
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["brokerAccountId"] is None

    repeated_preview = worksheets.preview(client, report)
    assert repeated_preview["newWallets"] == 0
    [plan] = repeated_preview["wallets"]
    assert plan["id"] == wallet["id"]
    assert plan["brokerAccountId"] == ACCOUNT
    assert plan["linksBrokerAccount"] is True
    assert plan["ready"] == 0
    assert plan["duplicates"] == 1

    repeated = worksheets.upload(client, report, token=repeated_preview["previewToken"])
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] == repeated.json()["imported"] == 0
    assert repeated.json()["duplicates"] == 1
    [relinked] = worksheets.portfolios(client)
    assert relinked["id"] == wallet["id"]
    assert relinked["brokerAccountId"] == ACCOUNT
    assert relinked["transactions"] == wallet["transactions"]


def test_worksheet_commit_rejects_a_link_that_changed_since_preview(client):
    report = worksheets.workbook(
        {"Cash Operations": [["Account number", ACCOUNT], reports.HEADERS, reports.cash()]}
    )
    preview = worksheets.preview(client, report)
    [plan] = preview["wallets"]
    assert plan["linksBrokerAccount"] is True

    other_wallet = linked_wallet(client, ACCOUNT)
    assert other_wallet["id"] != plan["id"]

    stale = worksheets.upload(client, report, token=preview["previewToken"])
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "import_preview_changed"
    [saved] = worksheets.portfolios(client)
    assert saved["id"] == other_wallet["id"]
    assert saved["brokerAccountId"] == ACCOUNT
    assert saved["transactions"] == []
