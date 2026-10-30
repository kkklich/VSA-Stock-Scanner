"""Real SQL persistence and API authorization for private observation evidence."""

from copy import deepcopy
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.journal_repository import JournalRepository
from app.db.models import JournalEntryRow, UserRow
from app.dependencies import get_user_repository
from app.routers.auth import get_current_user
from app.routers.journal import router
from tests.test_watchlists import SQLSession


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    UserRow.__table__.create(engine)
    JournalEntryRow.__table__.create(engine)
    with Session(engine) as session:
        for user_id in (1, 2):
            session.add(UserRow(
                id=user_id, email=f"journal{user_id}@example.com", password_hash="test",
                display_name="Test", created_at=datetime.now(UTC),
            ))
        session.commit()
    app = FastAPI()
    app.include_router(router)
    owner = SimpleNamespace(id=1)
    repository = SimpleNamespace(journal=JournalRepository(lambda: SQLSession(engine)))
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_user_repository] = lambda: repository
    with TestClient(app) as connection:
        connection.owner = owner
        yield connection
    engine.dispose()


def payload():
    return {
        "id": str(uuid4()), "ticker": "pkn", "note": "Breakout under observation",
        "confirmation": "Close above resistance", "invalidation": "Close below the base",
        "snapshot": {
            "schemaVersion": 1, "name": "PKN", "currency": "PLN", "market": "gpw",
            "interval": "1d", "referencePrice": 100,
            "combinedScore": 75, "ratingSession": "2026-10-28",
            "methodScores": [{"methodId": "vsa4", "score": 75, "detail": "Spring"}],
            "history": [{"time": "2026-10-28", "open": 99, "high": 101,
                         "low": 98, "close": 100, "volume": 10000}],
            "overlays": [{"methodId": "vsa4", "color": "#10b981", "signals": [
                {"date": "2026-10-28", "label": "Spring", "type": "Bullish"},
            ]}],
        },
    }


def test_frozen_evidence_survives_review_and_duplicate_submission(client):
    original = payload()
    created = client.post("/api/journal", json=original)
    assert created.status_code == 201
    assert created.headers["cache-control"] == "private, no-store"
    saved = created.json()
    assert saved["ticker"] == "PKN"
    original["snapshot"]["combinedScore"] = 1
    repeated = client.post("/api/journal", json=original)
    assert repeated.json()["snapshot"] == saved["snapshot"]
    listing = client.get("/api/journal?ticker=pkn").json()
    assert listing["total"] == 1
    assert "snapshot" not in listing["items"][0]
    path = f'/api/journal/{saved["id"]}'
    altered = client.patch(path, json={"version": 1, "status": "confirmed", "note": "Changed"})
    assert altered.status_code == 422
    updated = client.patch(path, json={
        "version": 1, "status": "confirmed", "review": "Held above resistance",
    })
    assert updated.status_code == 200
    current = client.get(path).json()
    assert current["snapshot"] == saved["snapshot"]
    assert current["note"] == saved["note"]
    assert current["confirmation"] == saved["confirmation"]
    assert current["version"] == 2
    assert current["review"] == "Held above resistance"
    assert client.patch(path, json={"version": 1, "status": "closed"}).status_code == 409
    assert client.delete(path + "?version=1").status_code == 409
    assert client.delete(path + "?version=2").status_code == 200
    assert client.get(path).status_code == 404


def test_all_reads_and_writes_are_account_scoped(client):
    entry = payload()
    assert client.post("/api/journal", json=entry).status_code == 201
    path = f'/api/journal/{entry["id"]}'
    client.owner.id = 2
    assert client.get("/api/journal").json() == {"items": [], "total": 0}
    assert client.get(path).status_code == 404
    assert client.patch(path, json={"version": 1, "status": "closed"}).status_code == 404
    assert client.delete(path + "?version=1").status_code == 404
    assert client.post("/api/journal", json=entry).status_code == 409
    own = payload()
    assert client.post("/api/journal", json=own).status_code == 201
    client.owner.id = 1
    assert client.get("/api/journal").json()["items"][0]["id"] == entry["id"]
    client.app.dependency_overrides.pop(get_current_user)
    assert client.get("/api/journal").status_code == 401
    assert client.post("/api/journal", json=payload()).status_code == 401


def test_rejects_malformed_or_unbounded_snapshots(client):
    valid = payload()
    variants = []
    for changes in ({"note": " "}, {"userId": 2}, {"note": "x" * 5001}):
        variants.append({**deepcopy(valid), **changes})
    for changes in (
        {"history": []}, {"referencePrice": 101}, {"combinedScore": 101},
        {"history": valid["snapshot"]["history"] * 2},
        {"history": [{**valid["snapshot"]["history"][0], "low": 105}]},
    ):
        altered = deepcopy(valid)
        altered["snapshot"].update(changes)
        variants.append(altered)
    for variant in variants:
        assert client.post("/api/journal", json=variant).status_code == 422
    assert client.get("/api/journal?limit=51").status_code == 422
    assert client.get("/api/journal?offset=-1").status_code == 422


def test_pagination_and_ticker_filter(client):
    for ticker in ("PKN", "AAPL.US", "PKN"):
        item = payload()
        item["ticker"] = ticker
        assert client.post("/api/journal", json=item).status_code == 201
    assert client.get("/api/journal?ticker=PKN").json()["total"] == 2
    first = client.get("/api/journal?limit=1").json()
    second = client.get("/api/journal?limit=1&offset=1").json()
    assert first["total"] == second["total"] == 3
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_migration_round_trip():
    path = Path(__file__).parents[1] / "alembic/versions/011_observation_journal.py"
    spec = spec_from_file_location("journal_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    UserRow.__table__.create(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "journal_entries" in inspect(connection).get_table_names()
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["users"]
    engine.dispose()
