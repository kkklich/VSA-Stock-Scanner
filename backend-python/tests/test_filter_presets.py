"""Persist real account presets through the same endpoints used by each device."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.models import FilterPresetRow, UserRow
from app.db.user_repository import UserRepository
from app.dependencies import get_user_repository
from app.routers.auth import get_current_user
from app.routers.filter_presets import router
from tests.test_watchlists import SQLSession

URL = "/api/filter-presets"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    UserRow.__table__.create(engine)
    FilterPresetRow.__table__.create(engine)
    with Session(engine) as session:
        for user_id in (1, 2):
            session.add(UserRow(id=user_id, email=f"{user_id}@example.com", password_hash="test",
                                display_name="Test", created_at=datetime.now(UTC)))
        session.commit()
    app = FastAPI()
    app.include_router(router)
    repo = UserRepository(lambda: SQLSession(engine))
    owner = SimpleNamespace(id=1)
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_user_repository] = lambda: repo
    with TestClient(app) as connection:
        connection.owner = owner
        yield connection
    engine.dispose()


def preset(preset_id="t-123", **filters):
    return {
        "id": preset_id, "name": "Spółki", "createdAt": "2026-11-06T12:00:00Z",
        "filters": filters,
    }


def test_account_round_trip_from_another_device_and_idempotent_import(client):
    mobile = TestClient(client.app)
    legacy = preset(minRating=50, weeklyConfirms=True)
    current = preset("t-456", q="pkn", minInsiderValueLast30Days=500.75, minPriceChangePct=-3.5,
                     insiderEnd="2026-11-06", insiderDays=90)
    result = client.post(URL, json={"presets": [legacy, current]})
    assert result.status_code == 200
    assert result.headers["cache-control"] == "private, no-store"
    rows = result.json()
    assert mobile.get(URL).json() == rows
    saved = {row["id"]: row["filters"] for row in rows}
    assert saved["t-123"]["minRating"] == 50
    assert saved["t-123"]["weeklyConfirms"] is True
    assert saved["t-123"]["insiderDays"] == 100
    assert saved["t-123"]["insiderEnd"] == ""
    for key, value in current["filters"].items():
        assert saved["t-456"][key] == value
    assert mobile.post(URL, json={"presets": [legacy, current]}).json() == rows
    assert mobile.delete(URL + "/t-123").status_code == 200
    assert [row["id"] for row in client.get(URL).json()] == ["t-456"]


def test_stale_conflicting_import_is_atomic(client):
    first = client.post(URL, json={"presets": [preset(minRating=10)]}).json()
    result = client.post(URL, json={"presets": [preset("second"), preset(minRating=20)]})
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "id_conflict"
    assert client.get(URL).json() == first


def test_owner_scoping_including_identical_local_ids_and_authentication(client):
    entry = preset(q="first")
    first = client.post(URL, json={"presets": [entry]}).json()
    client.owner.id = 2
    assert client.get(URL).json() == []
    assert client.delete(URL + "/t-123").status_code == 404
    assert client.post(URL, json={"presets": [preset(q="second")]}).status_code == 200
    assert client.delete(URL + "/t-123").json() == []
    client.owner.id = 1
    assert client.get(URL).json() == first
    client.app.dependency_overrides.pop(get_current_user)
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"presets": [entry]}).status_code == 401
    assert client.delete(URL + "/t-123").status_code == 401


def test_invalid_batch_cannot_partially_save(client):
    for bad in (preset("bad/id"), {**preset(), "name": "  "}, preset(minRating=101),
                preset(insiderActivity="unknown"), preset(insiderEnd="2026-02-30"),
                preset(extra="unsupported")):
        assert client.post(URL, json={"presets": [preset("valid"), bad]}).status_code == 422
    assert client.get(URL).json() == []


def test_stale_tab_cannot_read_save_or_delete_with_a_replaced_account_token(client):
    stale = {"X-Expected-User-Id": "1"}
    client.owner.id = 2
    current = client.post(URL, json={"presets": [preset()]},
                          headers={"X-Expected-User-Id": "2"}).json()
    responses = [
        client.get(URL, headers=stale),
        client.post(URL, json={"presets": [preset("unwanted")]}, headers=stale),
        client.delete(URL + "/t-123", headers=stale),
    ]
    for response in responses:
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "account_changed"
    assert client.get(URL).json() == current


def test_browser_can_preflight_an_account_guarded_delete():
    from app.main import app

    response = TestClient(app).options(URL + "/t-123", headers={
        "Origin": settings.cors_allowed_origins[0],
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "Authorization, X-Expected-User-Id",
    })
    assert response.status_code == 200
