"""A reviewed workbook cannot follow a browser tab into a different account."""

import pytest

from tests.test_portfolios import client as portfolio_client
from tests.test_portfolios import create
from tests.test_xtb_wallet_endpoints import workbook

URL = "/api/portfolios/imports/xtb/wallets"
PARAMS = {"filename": "example.xlsx"}


@pytest.fixture
def client():
    yield from portfolio_client.__wrapped__()


def test_stale_account_is_rejected_before_parsing_and_cannot_reuse_preview(client):
    body = workbook()
    expected_a = {"X-Expected-User-Id": "1"}
    preview = client.post(URL + "/preview", params=PARAMS, headers=expected_a, content=body)
    assert preview.status_code == 200, preview.text
    token = preview.json()["previewToken"]

    client.owner.id = 2
    # A second tab has changed the bearer. The first tab still sends A's header.
    mismatched = client.post(URL + "/preview", params=PARAMS, headers=expected_a, content=b"bad")
    assert mismatched.status_code == 409
    assert mismatched.json()["detail"]["code"] == "account_changed"
    for expected, code in (("1", "account_changed"), ("2", "import_preview_changed")):
        saved = client.post(
            URL,
            params=PARAMS,
            content=body,
            headers={"X-Expected-User-Id": expected, "X-XTB-Preview": token},
        )
        assert saved.status_code == 409
        assert saved.json()["detail"]["code"] == code
    assert client.get("/api/portfolios").json()["items"] == []

    client.owner.id = 1
    assert client.get("/api/portfolios").json()["items"] == []
    headers = {**expected_a, "X-XTB-Preview": token}
    for created in (2, 0):
        accepted = client.post(URL, params=PARAMS, content=body, headers=headers)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["created"] == created


def test_missing_account_and_missing_or_forged_review_cannot_save(client):
    body = workbook()
    expected_a = {"X-Expected-User-Id": "1"}
    assert client.post(URL + "/preview", params=PARAMS, content=body).status_code == 422
    assert client.post(URL, params=PARAMS, headers=expected_a, content=body).status_code == 422
    forged = client.post(
        URL, params=PARAMS, content=body, headers={**expected_a, "X-XTB-Preview": "0" * 64}
    )
    assert forged.status_code == 409
    assert forged.json()["detail"]["code"] == "import_preview_changed"
    assert client.get("/api/portfolios").json()["items"] == []


def test_stale_account_cannot_reload_or_import_into_an_existing_wallet(client):
    client.owner.id = 2
    wallet = create(client)
    stale_headers = {"X-Expected-User-Id": "1"}
    loaded = client.get("/api/portfolios", headers=stale_headers)
    assert loaded.status_code == 409
    assert loaded.json()["detail"]["code"] == "account_changed"

    legacy_url = f"/api/portfolios/{wallet['id']}/imports/xtb"
    for suffix in ("/preview", ""):
        saved = client.post(
            legacy_url + suffix,
            params={**PARAMS, "version": 1},
            headers=stale_headers,
            content=b"not parsed",
        )
        assert saved.status_code == 409
        assert saved.json()["detail"]["code"] == "account_changed"

    current = client.get("/api/portfolios", headers={"X-Expected-User-Id": "2"})
    assert current.status_code == 200
    assert current.json()["items"][0]["transactions"] == []
