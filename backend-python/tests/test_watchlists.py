"""Exercise ownership and persistence through the real router and SQL repository."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import UserRow, WatchlistRow
from app.db.watchlist_repository import WatchlistRepository
from app.dependencies import get_user_repository
from app.routers.auth import get_current_user
from app.routers.watchlists import router


class SQLSession:
    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.session.close()

    @asynccontextmanager
    async def begin(self):
        with self.session.begin():
            yield

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def delete(self, row):
        self.session.delete(row)


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    UserRow.__table__.create(engine)
    WatchlistRow.__table__.create(engine)
    with Session(engine) as session:
        for user_id in (1, 2):
            session.add(UserRow(
                id=user_id, email=f"{user_id}@example.com", password_hash="test",
                display_name="Test", created_at=datetime.now(UTC),
            ))
        session.commit()
    repo = SimpleNamespace(watchlists=WatchlistRepository(lambda: SQLSession(engine)))
    owner = SimpleNamespace(id=1)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(app) as connection:
        connection.owner = owner
        yield connection
    engine.dispose()


def bootstrap(client):
    response = client.post("/api/watchlists/bootstrap", json={"name": "Ulubione"})
    assert response.status_code == 200
    return response.json()[0]["id"]


def test_full_lifecycle_and_idempotent_import(client):
    first = bootstrap(client)
    assert bootstrap(client) == first
    created = client.post("/api/watchlists", json={"name": "  Długoterminowo  "})
    assert created.status_code == 201
    second = next(row["id"] for row in created.json() if row["id"] != first)
    path = f"/api/watchlists/{second}"
    for _ in range(2):
        added = client.put(path + "/members", json={"tickers": ["pkn", "AAPL", "VOD.L"]})
        assert added.status_code == 200
    rows = client.get("/api/watchlists").json()
    assert next(row for row in rows if row["id"] == first)["tickers"] == []
    assert next(row for row in rows if row["id"] == second)["tickers"] == [
        "AAPL", "PKN", "VOD.L",
    ]
    assert client.patch(path, json={"name": "Do analizy"}).status_code == 200
    assert client.delete(path + "/members", follow_redirects=True).status_code == 422
    removed = client.request("DELETE", path + "/members", json={"tickers": ["PKN"]})
    assert "PKN" not in next(row for row in removed.json() if row["id"] == second)["tickers"]
    assert client.delete(path).status_code == 200
    assert client.delete(f"/api/watchlists/{first}").status_code == 409


def test_accounts_cannot_read_or_modify_other_lists(client):
    other = bootstrap(client)
    client.owner.id = 2
    assert client.get("/api/watchlists").json() == []
    own = bootstrap(client)
    assert own != other
    path = f"/api/watchlists/{other}"
    for method, suffix, payload in (
        ("PATCH", "", {"name": "Stolen"}), ("DELETE", "", None),
        ("PUT", "/members", {"tickers": ["PKN"]}),
        ("DELETE", "/members", {"tickers": ["PKN"]}),
    ):
        assert client.request(method, path + suffix, json=payload).status_code == 404
    client.owner.id = 1
    assert client.get("/api/watchlists").json() == [
        {"id": other, "name": "Ulubione", "tickers": []},
    ]


def test_validation_limits_and_authentication(client):
    first = bootstrap(client)
    for name in ("", "   ", "x" * 81):
        assert client.post("/api/watchlists", json={"name": name}).status_code == 422
    assert client.post("/api/watchlists", json={"name": "ulubione"}).status_code == 409
    path = f"/api/watchlists/{first}/members"
    assert client.put(path, json={"tickers": ["bad/ticker"]}).status_code == 422
    assert client.put(path, json={"tickers": [f"T{i}" for i in range(500)]}).status_code == 200
    assert client.put(path, json={"tickers": ["EXTRA"]}).status_code == 409
    for index in range(19):
        assert client.post("/api/watchlists", json={"name": str(index)}).status_code == 201
    assert client.post("/api/watchlists", json={"name": "extra"}).status_code == 409
    client.app.dependency_overrides.pop(get_current_user)
    assert client.get("/api/watchlists").status_code == 401
    assert client.post("/api/watchlists/bootstrap", json={"name": "Test"}).status_code == 401


def test_migration_creates_and_removes_only_watchlist_table():
    path = Path(__file__).parents[1] / "alembic/versions/010_watchlists.py"
    spec = spec_from_file_location("watchlists_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    UserRow.__table__.create(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "watchlists" in inspect(connection).get_table_names()
            foreign_key = inspect(connection).get_foreign_keys("watchlists")[0]
            assert foreign_key["referred_table"] == "users"
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["users"]
    engine.dispose()
