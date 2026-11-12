"""Worksheet wallets are previewed, saved atomically, private and safe to retry."""

import io

import openpyxl
import pytest
from fastapi import HTTPException

from app.routers.auth import get_current_user
from app.routers.portfolios import gpw_company_service
from app.services.xtb_import import MAX_FILE_BYTES
from tests.test_portfolios import client as portfolio_client
from tests.test_portfolios import create
from tests.test_xtb_import import HEADERS, cash
from tests.test_xtb_wallet_import import CLOSED_HEADERS, OPEN_HEADERS
from tests.test_xtb_wallet_import import workbook as native_workbook


@pytest.fixture
def client():
    yield from portfolio_client.__wrapped__()


def workbook(sheets=None):
    sheets = (
        sheets
        if sheets is not None
        else {
            "Wallet A": [HEADERS, cash()],
            "Wallet B": [HEADERS, cash(comment="OPEN BUY 2 @ 105")],
        }
    )
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def upload(client, data, *, token=None, partial=False, filename="example.xlsx"):
    suffix = "/preview" if token is None else ""
    headers = {
        "Content-Type": "application/octet-stream",
        "X-Expected-User-Id": str(client.owner.id),
    }
    if token is not None:
        headers["X-XTB-Preview"] = token
    return client.post(
        f"/api/portfolios/imports/xtb/wallets{suffix}",
        params={"filename": filename, "allow_partial": partial},
        content=data,
        headers=headers,
    )


def preview(client, data, **kwargs):
    response = upload(client, data, **kwargs)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["previewToken"]
    return plan


def portfolios(client):
    return client.get("/api/portfolios").json()["items"]


def test_wallet_preview_is_read_only_and_assigns_each_sheet_its_own_wallet(client):
    response = upload(client, workbook())
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    plan = response.json()
    assert plan["previewToken"]
    assert plan["newWallets"] == 2
    assert plan["blockingError"] is None
    assert plan["ready"] == 2
    assert plan["errors"] == 0
    assert [item["name"] for item in plan["wallets"]] == ["Wallet A", "Wallet B"]
    assert len({item["id"] for item in plan["wallets"]}) == 2
    for item in plan["wallets"]:
        assert item["version"] is None
        assert item["ready"] == 1
        assert item["error"] is None
        assert item["ledgerError"] is None
        assert "ledger" not in item
        assert "additions" not in item
    assert portfolios(client) == []


def test_wallet_commit_creates_separate_ledgers_and_reselecting_bytes_reuses_wallets(client):
    data = workbook()
    plan = preview(client, data)
    response = upload(client, data, token=plan["previewToken"])
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["created"] == 2
    assert saved["imported"] == 2
    assert saved["duplicates"] == 0
    assert saved["skipped"] == 0
    before = portfolios(client)
    assert len(before) == 2
    assert {p["id"] for p in before} == {p["id"] for p in plan["wallets"]}
    assert {p["name"] for p in before} == {"Wallet A", "Wallet B"}
    assert all(p["broker"] == "XTB" and p["costMethod"] == "fifo" for p in before)
    assert all(len(p["transactions"]) == 1 for p in before)
    assert {p["positions"][0]["quantity"] for p in before} == {2, 10}

    retry = upload(client, data, token=plan["previewToken"])
    assert retry.status_code == 200, retry.text
    assert retry.json()["created"] == retry.json()["imported"] == 0
    assert retry.json()["duplicates"] == 2

    repeated_plan = preview(client, data, filename="copied.xlsx")
    assert repeated_plan["newWallets"] == 0
    assert repeated_plan["blockingError"] is None
    assert repeated_plan["ready"] == 0
    assert all(item["version"] is not None for item in repeated_plan["wallets"])
    assert all(item["duplicates"] == 1 for item in repeated_plan["wallets"])
    assert {p["id"] for p in repeated_plan["wallets"]} == {p["id"] for p in before}
    repeated = upload(client, data, token=repeated_plan["previewToken"], filename="copied.xlsx")
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] == 0
    assert repeated.json()["imported"] == 0
    assert repeated.json()["duplicates"] == 2
    assert portfolios(client) == before


def test_invalid_rows_require_partial_choice_before_any_wallet_is_created(client):
    data = workbook(
        {
            "Wallet A": [HEADERS, cash(), cash("bad", symbol="UNKNOWN.PL")],
            "Wallet B": [HEADERS, cash()],
        }
    )
    plan = preview(client, data)
    assert plan["errors"] == 1
    rejected = upload(client, data, token=plan["previewToken"])
    assert rejected.status_code == 422, rejected.text
    assert portfolios(client) == []

    saved = upload(client, data, token=plan["previewToken"], partial=True)
    assert saved.status_code == 200, saved.text
    assert saved.json()["created"] == 2
    assert saved.json()["imported"] == 2
    assert saved.json()["skipped"] == 1
    assert all(len(p["transactions"]) == 1 for p in portfolios(client))


def test_partial_consent_does_not_cover_errors_that_appear_after_preview(client, monkeypatch):
    data = workbook(
        {
            "Wallet A": [
                HEADERS,
                cash(),
                cash("pkn-fill", symbol="PKN.PL"),
                cash("unknown-fill", symbol="UNKNOWN.PL"),
            ],
            "Wallet B": [HEADERS, cash()],
        }
    )
    plan = preview(client, data)
    assert plan["ready"] == 3
    assert plan["errors"] == 1

    find = gpw_company_service.find
    monkeypatch.setattr(
        gpw_company_service, "find", lambda ticker: None if ticker == "pkn" else find(ticker)
    )
    rejected = upload(client, data, token=plan["previewToken"], partial=True)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "import_preview_changed"
    assert portfolios(client) == []


def test_empty_native_sheets_create_wallets_without_inventing_transactions(client):
    data = native_workbook(
        ("Closed Positions", CLOSED_HEADERS, []),
        ("Cash Operations", HEADERS, []),
        ("Open Positions", OPEN_HEADERS, []),
    )
    plan = preview(client, data)
    assert plan["newWallets"] == 3
    assert plan["blockingError"] is None
    assert plan["ready"] == 0
    assert plan["errors"] == 0
    assert all(item["error"] is None for item in plan["wallets"])
    assert portfolios(client) == []

    saved = upload(client, data, token=plan["previewToken"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["created"] == 3
    assert saved.json()["imported"] == 0
    wallets = portfolios(client)
    assert {p["name"] for p in wallets} == {"Cash Operations", "Closed Positions", "Open Positions"}
    assert all(p["transactions"] == [] for p in wallets)


@pytest.mark.parametrize(
    ("bad_rows", "expected_code"),
    [
        ([HEADERS, cash("bad", symbol="UNKNOWN.PL")], "import_no_transactions"),
        ([["Not an XTB report"], ["unrelated", "values"]], "import_unrecognized_format"),
    ],
)
def test_unimportable_sheet_blocks_entire_batch_even_with_partial_choice(
    client, bad_rows, expected_code
):
    data = workbook({"Valid": [HEADERS, cash()], "Needs attention": bad_rows})
    plan = preview(client, data)
    assert plan["wallets"][1]["error"] == expected_code
    saved = upload(client, data, token=plan["previewToken"], partial=True)
    assert saved.status_code == 422, saved.text
    assert saved.json()["detail"]["code"] == expected_code
    assert portfolios(client) == []


def test_insufficient_holdings_in_one_sheet_rolls_back_other_wallets(client):
    data = workbook(
        {
            "Valid": [HEADERS, cash()],
            "Sale without purchase": [
                HEADERS,
                cash("sale", "Stock sell", comment="CLOSE BUY 10 @ 120"),
            ],
        }
    )
    plan = preview(client, data)
    assert plan["wallets"][1]["ledgerError"] == "insufficient_shares"
    saved = upload(client, data, token=plan["previewToken"], partial=True)
    assert saved.status_code == 409, saved.text
    assert portfolios(client) == []


def test_account_wallet_limit_is_checked_for_whole_batch_before_creation(client):
    for _ in range(19):
        create(client)
    data = workbook()
    plan = preview(client, data)
    assert plan["newWallets"] == 2
    assert plan["blockingError"] == "portfolio_limit"
    saved = upload(client, data, token=plan["previewToken"])
    assert saved.status_code == 409, saved.text
    assert saved.json()["detail"]["code"] == "portfolio_limit"
    assert len(portfolios(client)) == 19


def test_identical_file_reuses_wallets_only_within_the_same_account(client):
    data = workbook()
    first = upload(client, data, token=preview(client, data)["previewToken"])
    assert first.status_code == 200, first.text
    first_ids = {p["id"] for p in portfolios(client)}

    client.owner.id = 2
    assert portfolios(client) == []
    plan = preview(client, data)
    assert all(item["version"] is None for item in plan["wallets"])
    second = upload(client, data, token=plan["previewToken"])
    assert second.status_code == 200, second.text
    assert second.json()["created"] == 2
    assert first_ids.isdisjoint({p["id"] for p in portfolios(client)})
    client.owner.id = 1
    assert {p["id"] for p in portfolios(client)} == first_ids


def test_wallet_upload_requires_sign_in_before_parsing_and_bounds_raw_body(client):
    too_large = upload(client, b"x" * (MAX_FILE_BYTES + 1))
    assert too_large.status_code == 413, too_large.text
    assert portfolios(client) == []

    def guest():
        raise HTTPException(status_code=401, detail="Sign in")

    client.app_instance.dependency_overrides[get_current_user] = guest
    for token in (None, "0" * 64):
        response = upload(client, b"invalid workbook", token=token)
        assert response.status_code == 401, response.text
