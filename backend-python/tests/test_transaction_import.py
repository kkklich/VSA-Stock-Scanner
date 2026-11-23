"""JSON automation: private routing, reviewed decimals, atomic ledgers and retries."""

from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import SecretStr

from app.config import settings
from tests import test_xtb_import

client = test_xtb_import.client
automation_portfolio = test_xtb_import.automation_portfolio
URL = "/api/portfolios/imports/transactions"
ACCOUNT = "0052446029"
PAYLOAD = {
    "status": "ready",
    "brokerAccountId": ACCOUNT,
    "reportDate": "2026-01-02",
    "transactions": [
        {
            "orderId": "2955645632",
            "ticker": "kty",
            "date": "2026-01-02",
            "side": "buy",
            "quantity": "0.2954",
            "price": "1225.00000",
            "fees": "0",
            "currency": "PLN",
        }
    ],
}


@pytest.fixture
def linked(client, automation_portfolio, monkeypatch):
    result = client.patch(
        f"/api/portfolios/{automation_portfolio['id']}",
        json={
            "name": "JSON wallet",
            "broker": "XTB",
            "brokerAccountId": ACCOUNT,
            "costMethod": "fifo",
            "version": automation_portfolio["version"],
        },
    )
    assert result.status_code == 200, result.text
    monkeypatch.setattr(settings, "xtb_automation_portfolio_id", None)
    return result.json()


def post(client, payload=None, token=test_xtb_import.AUTOMATION_TOKEN):
    return client.post(
        URL,
        json=PAYLOAD if payload is None else payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def wallet(client):
    return client.get("/api/portfolios").json()["items"][0]


def test_save_exact_decimals_and_retry(client, linked):
    first = post(client)
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    assert first.json() == {
        "imported": 1,
        "duplicates": 0,
        "skipped": 0,
        "version": linked["version"] + 1,
        "brokerAccountId": ACCOUNT,
        "warnings": [],
    }
    retry = post(client)
    assert retry.status_code == 200, retry.text
    assert (retry.json()["imported"], retry.json()["duplicates"]) == (0, 1)
    assert retry.json()["version"] == first.json()["version"]
    [saved] = wallet(client)["transactions"]
    assert (saved["quantity"], saved["price"], saved["fees"]) == ("0.2954", "1225.00000", "0")
    assert wallet(client)["brokerAccountId"] == ACCOUNT


@pytest.mark.parametrize(
    "changes",
    [
        {"fees": None},
        {"fees": "-1"},
        {"fees": "NaN"},
        {"quantity": "0"},
        {"price": "Infinity"},
        {"quantity": "0.123456789"},
        {"date": "2099-01-01"},
        {"orderId": 2955645632},
        {"ticker": "not-a-stock"},
        {"currency": "USD"},
        {"date": "2026-01-03"},
    ],
)
def test_invalid_row_leaves_entire_batch_untouched(client, linked, changes):
    payload = deepcopy(PAYLOAD)
    payload["transactions"].append({**payload["transactions"][0], "orderId": "2", **changes})
    result = post(client, payload)
    assert result.status_code == 422, result.text
    saved = wallet(client)
    assert (saved["version"], saved["transactions"]) == (linked["version"], [])


@pytest.mark.parametrize("field", ["fees", "orderId", "quantity"])
def test_missing_required_execution_field(client, linked, field):
    payload = deepcopy(PAYLOAD)
    del payload["transactions"][0][field]
    assert post(client, payload).status_code == 422
    assert wallet(client)["transactions"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "needs_review"},
        {"candidates": []},
        {"missingFields": []},
        {"konto": ACCOUNT},
        {"transactions": []},
        {"brokerAccountId": 52446029},
    ],
)
def test_review_output_cannot_be_saved_directly(client, linked, changes):
    assert post(client, {**deepcopy(PAYLOAD), **changes}).status_code == 422
    assert wallet(client)["transactions"] == []


def test_sale_ledger_and_oversell_are_atomic(client, linked):
    payload = deepcopy(PAYLOAD)
    payload["transactions"].append(
        {
            **payload["transactions"][0],
            "orderId": "2",
            "side": "sell",
            "quantity": "0.1",
        }
    )
    saved = post(client, payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["imported"] == 2
    assert len(wallet(client)["transactions"]) == 2
    bad = deepcopy(PAYLOAD)
    bad["transactions"][0].update(orderId="3", side="sell", quantity="10")
    result = post(client, bad)
    assert result.status_code == 409, result.text
    assert len(wallet(client)["transactions"]) == 2


def test_changed_execution_conflicts_instead_of_overwriting(client, linked):
    assert post(client).status_code == 200
    changed = deepcopy(PAYLOAD)
    changed["transactions"][0]["fees"] = "1"
    result = post(client, changed)
    assert result.status_code == 422, result.text
    assert wallet(client)["transactions"][0]["fees"] == "0"


def test_partial_fills_require_distinct_stable_execution_ids(client, linked):
    payload = deepcopy(PAYLOAD)
    payload["transactions"].append(deepcopy(payload["transactions"][0]))
    assert post(client, payload).json()["detail"]["code"] == "import_ambiguous_execution"
    for index, entry in enumerate(payload["transactions"]):
        entry["executionId"] = f"fill_{index}"
    result = post(client, payload)
    assert result.status_code == 200, result.text
    assert result.json()["imported"] == 2
    assert post(client, payload).json()["duplicates"] == 2


def test_token_and_owner_scope(client, linked, monkeypatch):
    assert post(client, token="wrong").status_code == 401
    assert client.post(URL, json=PAYLOAD).status_code == 401
    monkeypatch.setattr(settings, "xtb_automation_user_id", 2)
    assert post(client).status_code == 404
    monkeypatch.setattr(settings, "xtb_automation_token", SecretStr(""))
    assert post(client).status_code == 404
    assert wallet(client)["transactions"] == []


def test_fixed_wallet_must_match_account(client, linked, monkeypatch):
    monkeypatch.setattr(settings, "xtb_automation_portfolio_id", UUID(linked["id"]))
    result = post(client, {**PAYLOAD, "brokerAccountId": "99999"})
    assert result.status_code == 409, result.text
    assert wallet(client)["transactions"] == []


def test_unlinked_account_is_not_created(client, linked):
    result = post(client, {**PAYLOAD, "brokerAccountId": "99999"})
    assert result.status_code == 404, result.text
    assert result.json()["detail"]["code"] == "broker_account_unlinked"
    assert wallet(client)["transactions"] == []


def test_possible_spreadsheet_overlap_requires_review(client, linked):
    assert post(client).status_code == 200
    data = (
        b"ID,Type,Time,Symbol,Quantity,Price,Currency,Commission\n"
        b"123,Buy,2026-01-02 12:00:00,KTY.PL,0.2954,1225,PLN,0\n"
    )
    result = test_xtb_import.automation_request(client, data)
    assert result.status_code == 422, result.text
    assert len(wallet(client)["transactions"]) == 1


def test_database_unavailable(client, linked):
    from app.dependencies import get_user_repository

    client.app_instance.dependency_overrides[get_user_repository] = lambda: None
    assert post(client).status_code == 503
