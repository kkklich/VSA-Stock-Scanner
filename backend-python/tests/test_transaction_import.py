"""JSON automation: private routing, reviewed decimals, atomic ledgers and retries."""

from copy import deepcopy
from uuid import UUID, uuid4

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
    body = PAYLOAD if payload is None else payload
    return client.post(
        URL,
        json=body if isinstance(body, list) else [body],
        headers={"Authorization": f"Bearer {token}"},
    )


def wallet(client):
    return client.get("/api/portfolios").json()["items"][0]


def test_save_exact_decimals_and_retry(client, linked):
    first = post(client)
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "private, no-store"
    assert first.json() == [
        {
            "imported": 1,
            "duplicates": 0,
            "skipped": 0,
            "version": linked["version"] + 1,
            "brokerAccountId": ACCOUNT,
            "warnings": [],
        }
    ]
    retry = post(client)
    assert retry.status_code == 200, retry.text
    assert (retry.json()[0]["imported"], retry.json()[0]["duplicates"]) == (0, 1)
    assert retry.json()[0]["version"] == first.json()[0]["version"]
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
    assert saved.json()[0]["imported"] == 2
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
    context = result.json()["detail"]["context"]
    assert context["reportIndex"] == 0
    assert context["brokerAccountId"] == ACCOUNT
    [error] = context["errors"]
    assert (error["row"], error["orderId"], error["ticker"], error["code"]) == (
        1,
        "2955645632",
        "kty",
        "reference_conflict",
    )
    assert "different details" in error["message"]
    assert wallet(client)["transactions"][0]["fees"] == "0"


def test_partial_fills_require_distinct_stable_execution_ids(client, linked):
    payload = deepcopy(PAYLOAD)
    payload["transactions"].append(deepcopy(payload["transactions"][0]))
    assert post(client, payload).json()["detail"]["code"] == "import_ambiguous_execution"
    for index, entry in enumerate(payload["transactions"]):
        entry["executionId"] = f"fill_{index}"
    result = post(client, payload)
    assert result.status_code == 200, result.text
    assert result.json()[0]["imported"] == 2
    assert post(client, payload).json()[0]["duplicates"] == 2


def test_token_and_owner_scope(client, linked, monkeypatch):
    assert post(client, token="wrong").status_code == 401
    assert client.post(URL, json=[PAYLOAD]).status_code == 401
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


def test_possible_spreadsheet_overlap_requires_review(client, linked, monkeypatch):
    assert post(client).status_code == 200
    monkeypatch.setattr(settings, "xtb_automation_portfolio_id", UUID(linked["id"]))
    data = (
        b"ID,Type,Time,Symbol,Quantity,Price,Currency,Commission\n"
        b"123,Buy,2026-01-02 12:00:00,KTY.PL,0.2954,1225,PLN,0\n"
    )
    result = test_xtb_import.automation_request(client, data)
    assert result.status_code == 422, result.text
    [error] = result.json()["detail"]["context"]["errors"]
    assert error["code"] == "xtb_source_overlap"
    assert len(wallet(client)["transactions"]) == 1


def test_json_error_identifies_existing_spreadsheet_overlap(client, linked):
    data = (
        b"ID,Type,Time,Symbol,Quantity,Price,Currency,Commission\n"
        b"123,Buy,2026-01-02 12:00:00,KTY.PL,0.2954,1225,PLN,0\n"
    )
    saved = test_xtb_import.commit(client, linked, data, filename="history.csv")
    assert saved.status_code == 200, saved.text
    result = post(client)
    assert result.status_code == 422, result.text
    context = result.json()["detail"]["context"]
    assert context["reportIndex"] == 0
    [error] = context["errors"]
    assert (error["row"], error["orderId"], error["ticker"], error["code"]) == (
        1,
        "2955645632",
        "kty",
        "xtb_source_overlap",
    )
    assert "another XTB import format" in error["message"]
    assert "transaction" not in error
    assert len(wallet(client)["transactions"]) == 1


def test_json_error_identifies_existing_manual_overlap(client, linked):
    trade = {key: value for key, value in PAYLOAD["transactions"][0].items() if key != "orderId"}
    saved = client.post(
        f"/api/portfolios/{linked['id']}/transactions",
        json={
            **trade,
            "id": str(uuid4()),
            "version": linked["version"],
        },
    )
    assert saved.status_code == 201, saved.text
    result = post(client)
    assert result.status_code == 422, result.text
    [error] = result.json()["detail"]["context"]["errors"]
    assert error["code"] == "manual_overlap"
    assert error["orderId"] == "2955645632"
    assert len(wallet(client)["transactions"]) == 1


def test_database_unavailable(client, linked):
    from app.dependencies import get_user_repository

    client.app_instance.dependency_overrides[get_user_repository] = lambda: None
    assert post(client).status_code == 503


def test_multiple_reports_for_same_wallet_and_retries(client, linked):
    second = deepcopy(PAYLOAD)
    second["reportDate"] = "2026-01-03"
    second["transactions"][0].update(orderId="2", date="2026-01-03")
    result = post(client, [PAYLOAD, second])
    assert result.status_code == 200, result.text
    assert [report["imported"] for report in result.json()] == [1, 1]
    assert [report["version"] for report in result.json()] == [
        linked["version"] + 1,
        linked["version"] + 2,
    ]
    assert len(wallet(client)["transactions"]) == 2
    retry = post(client, [PAYLOAD, second])
    assert retry.status_code == 200, retry.text
    assert [report["duplicates"] for report in retry.json()] == [1, 1]
    assert [report["imported"] for report in retry.json()] == [0, 0]
    assert wallet(client)["version"] == linked["version"] + 2


def test_repeated_report_within_batch_is_a_duplicate(client, linked):
    result = post(client, [PAYLOAD, PAYLOAD])
    assert result.status_code == 200, result.text
    assert [report["imported"] for report in result.json()] == [1, 0]
    assert [report["duplicates"] for report in result.json()] == [0, 1]
    assert len(wallet(client)["transactions"]) == 1


def another_wallet(client):
    result = client.post(
        "/api/portfolios",
        json={
            "id": str(uuid4()),
            "name": "Second wallet",
            "broker": "XTB",
            "brokerAccountId": "12345678",
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_batch_routes_reports_to_different_wallets(client, linked):
    other = another_wallet(client)
    report = {**deepcopy(PAYLOAD), "brokerAccountId": other["brokerAccountId"]}
    result = post(client, [PAYLOAD, report])
    assert result.status_code == 200, result.text
    assert [row["brokerAccountId"] for row in result.json()] == [ACCOUNT, other["brokerAccountId"]]
    wallets = client.get("/api/portfolios").json()["items"]
    assert [len(row["transactions"]) for row in wallets] == [1, 1]
    retry = post(client, [PAYLOAD, report])
    assert [row["duplicates"] for row in retry.json()] == [1, 1]


@pytest.mark.parametrize("failure", ["unlinked", "oversell", "changed_reference", "invalid_ticker"])
def test_later_report_failure_rolls_back_whole_request(client, linked, failure):
    bad = deepcopy(PAYLOAD)
    bad["transactions"][0]["orderId"] = "2"
    if failure == "unlinked":
        bad["brokerAccountId"] = "99999999"
    elif failure == "oversell":
        bad["transactions"][0].update(side="sell", quantity="10")
    elif failure == "changed_reference":
        bad["transactions"][0].update(orderId="2955645632", fees="1")
    else:
        bad["transactions"][0]["ticker"] = "not-a-stock"
    result = post(client, [PAYLOAD, bad])
    assert result.status_code in {404, 409, 422}, result.text
    if failure == "changed_reference":
        assert result.json()["detail"]["context"]["reportIndex"] == 1
    saved = wallet(client)
    assert (saved["version"], saved["transactions"]) == (linked["version"], [])


def test_failure_in_second_wallet_rolls_back_first_wallet(client, linked):
    other = another_wallet(client)
    bad = {**deepcopy(PAYLOAD), "brokerAccountId": other["brokerAccountId"]}
    bad["transactions"][0].update(side="sell", quantity="10")
    assert post(client, [PAYLOAD, bad]).status_code == 409
    wallets = client.get("/api/portfolios").json()["items"]
    assert [row["transactions"] for row in wallets] == [[], []]
    assert [row["version"] for row in wallets] == [linked["version"], other["version"]]


def test_fixed_wallet_restriction_applies_to_every_report(client, linked, monkeypatch):
    other = another_wallet(client)
    monkeypatch.setattr(settings, "xtb_automation_portfolio_id", UUID(linked["id"]))
    report = {**deepcopy(PAYLOAD), "brokerAccountId": other["brokerAccountId"]}
    result = post(client, [PAYLOAD, report])
    assert result.status_code == 409, result.text
    assert wallet(client)["transactions"] == []


@pytest.mark.parametrize("body", [[], PAYLOAD, [PAYLOAD] * 101])
def test_body_requires_bounded_nonempty_array(client, linked, body):
    result = client.post(
        URL,
        json=body,
        headers={
            "Authorization": f"Bearer {test_xtb_import.AUTOMATION_TOKEN}",
        },
    )
    assert result.status_code == 422, result.text
    assert wallet(client)["transactions"] == []


def test_total_transactions_across_reports_are_bounded(client, linked):
    report = {**deepcopy(PAYLOAD), "transactions": PAYLOAD["transactions"] * 501}
    result = post(client, [report, report])
    assert result.status_code == 422, result.text
    assert wallet(client)["transactions"] == []
