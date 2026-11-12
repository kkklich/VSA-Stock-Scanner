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


def test_worksheet_preview_links_cash_operations_and_keeps_snapshots_separate(client):
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
    assert {
        wallet["name"]: (wallet["brokerAccountId"], wallet["linksBrokerAccount"])
        for wallet in preview["wallets"]
    } == {
        "Closed Positions": (None, False),
        "Cash Operations": (ACCOUNT, True),
        "Open Positions": (None, False),
    }
    assert worksheets.portfolios(client) == []

    committed = worksheets.upload(client, report, token=preview["previewToken"])
    assert committed.status_code == 200, committed.text
    assert committed.json()["created"] == 3
    assert {
        wallet["name"]: wallet["brokerAccountId"] for wallet in worksheets.portfolios(client)
    } == {
        "Closed Positions": None,
        "Cash Operations": ACCOUNT,
        "Open Positions": None,
    }


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
