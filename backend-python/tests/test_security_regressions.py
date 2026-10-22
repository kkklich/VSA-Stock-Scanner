"""Regression coverage for the reviewed account, provider and back-test boundaries."""

from __future__ import annotations

import asyncio
import json
import ssl
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.analysis.methods import all_methods
from app.config import settings
from app.db.repository import InMemoryQuoteRepository
from app.dependencies import get_login_throttle, get_user_repository
from app.jobs.daily_ingest import IngestService
from app.main import app
from app.models import GpwCompany, MethodBacktestResponse
from app.routers import auth, stocks
from app.services import auth as auth_service
from app.services.auth import LoginThrottle
from app.services.cache import LockRegistry, TTLCache
from app.services.espi_client import EspiClient
from tests.test_auth import _FakeUserRepository


@pytest.fixture
def accounts(monkeypatch):
    repo = _FakeUserRepository()
    throttle = LoginThrottle(max_failures=3)
    monkeypatch.setattr(settings, "admin_token", "")
    monkeypatch.setattr(settings, "admin_emails", "")
    monkeypatch.setattr(settings, "registration_open", True)
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_login_throttle] = lambda: throttle
    with TestClient(app) as client:
        yield client, repo, throttle
    app.dependency_overrides.pop(get_user_repository, None)
    app.dependency_overrides.pop(get_login_throttle, None)


def register(client, email="user@example.com", **kwargs):
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "a-long-test-password",
        },
        **kwargs,
    )


def test_valid_and_duplicate_registrations_spend_admission(accounts, monkeypatch):
    client, _repo, _throttle = accounts
    original = auth.hash_password
    calls = []
    monkeypatch.setattr(
        auth, "hash_password", lambda value: (calls.append(value), original(value))[1]
    )
    assert register(client).status_code == 201
    assert register(client).status_code == 409
    assert register(client).status_code == 409
    blocked = register(client, "other@example.com")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert len(calls) == 3


def test_other_account_success_does_not_reset_ip_budget(accounts):
    client, _repo, _throttle = accounts
    register(client, "victim@example.com")
    register(client, "attacker@example.com")
    for _ in range(2):
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "email": "victim@example.com",
                    "password": "wrong-password",
                },
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "attacker@example.com",
                "password": "a-long-test-password",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "victim@example.com",
                "password": "wrong-password",
            },
        ).status_code
        == 429
    )
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": "attacker@example.com",
                "password": "a-long-test-password",
            },
        ).status_code
        == 429
    )


def test_successful_logins_do_not_exhaust_shared_ip(accounts):
    client, _repo, _throttle = accounts
    register(client)
    for _ in range(12):
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "a-long-test-password"},
            ).status_code
            == 200
        )


def test_success_releases_only_its_reservation_with_equal_timestamps(monkeypatch):
    monkeypatch.setattr(auth_service, "time", SimpleNamespace(monotonic=lambda: 1000.0))
    throttle = LoginThrottle(max_failures=2)
    success = throttle.record_failure("ip:shared")
    throttle.record_failure("ip:shared")
    throttle.forgive("ip:shared", success)
    assert not throttle.is_blocked("ip:shared")
    throttle.record_failure("ip:shared")
    assert throttle.is_blocked("ip:shared")


def test_account_budget_precedes_password_check_and_allows_recovery(accounts, monkeypatch):
    client, _repo, throttle = accounts
    register(client)
    clock = [1000.0]
    monkeypatch.setattr(auth_service, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original = auth.verify_password
    calls = []
    monkeypatch.setattr(
        auth, "verify_password", lambda *args: (calls.append(args), original(*args))[1]
    )
    for i in range(3):
        client.post(
            "/api/auth/login",
            headers={"X-Real-IP": f"198.51.100.{i}"},
            json={
                "email": "user@example.com",
                "password": "wrong-password",
            },
        )
    blocked = client.post(
        "/api/auth/login",
        headers={"X-Real-IP": "203.0.113.1"},
        json={
            "email": "user@example.com",
            "password": "a-long-test-password",
        },
    )
    assert blocked.status_code == 429
    assert len(calls) == 3
    clock[0] += int(blocked.headers["Retry-After"])
    recovered = client.post(
        "/api/auth/login",
        headers={"X-Real-IP": "203.0.113.1"},
        json={
            "email": "user@example.com",
            "password": "a-long-test-password",
        },
    )
    assert recovered.status_code == 200
    assert not throttle.is_blocked("email:user@example.com")


async def test_login_reserves_admission_before_repository_await(accounts, monkeypatch):
    _client, repo, throttle = accounts
    entered = asyncio.Event()
    release = asyncio.Event()
    lookups = []

    async def lookup(email):
        lookups.append(email)
        entered.set()
        await release.wait()
        return None

    monkeypatch.setattr(repo, "get_by_email", lookup)

    async def call():
        try:
            return await auth.login(
                auth.LoginRequest(email="unknown@example.com", password="wrong-password"),
                auth.Response(),
                request_for("198.51.100.10"),
                repo,
                throttle,
            )
        except HTTPException as exc:
            return exc.status_code

    tasks = [asyncio.create_task(call()) for _ in range(8)]
    await entered.wait()
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)
    assert len(lookups) == 3
    assert results.count(429) >= 5


async def test_password_workers_stay_bounded_when_caller_is_cancelled():
    release = threading.Event()
    started = []
    finished = []
    guard = threading.Lock()

    def work():
        with guard:
            started.append(True)
        try:
            release.wait(5)
            return True
        finally:
            finished.append(True)

    tasks = [asyncio.create_task(auth._password_work(work)) for _ in range(4)]
    try:

        async def all_started():
            while len(started) < 4:
                await asyncio.sleep(0.001)

        await asyncio.wait_for(all_started(), 3)
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        with pytest.raises(HTTPException) as busy:
            await auth._password_work(lambda: False)
        assert busy.value.status_code == 429
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        while len(finished) < len(started):
            await asyncio.sleep(0.001)
    assert await auth._password_work(lambda: "available") == "available"


@pytest.mark.parametrize("path", ["/logs", "/logs/summary", "/errors", "/health"])
def test_admin_fails_closed_without_a_secret(accounts, path):
    client, _repo, _throttle = accounts
    assert client.get("/api/admin" + path).status_code == 401
    assert client.get("/api/admin" + path, headers={"X-Admin-Token": "anything"}).status_code == 401


def test_privileged_registration_requires_secret_and_admin_jwt_still_works(accounts, monkeypatch):
    client, repo, _throttle = accounts
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    assert register(client, "boss@example.com").status_code == 403
    monkeypatch.setattr(settings, "admin_token", "test-provisioning-token")
    created = register(
        client,
        "boss@example.com",
        headers={
            "X-Admin-Token": "test-provisioning-token",
        },
    )
    assert created.status_code == 201
    monkeypatch.setattr(settings, "admin_token", "")
    token = created.json()["accessToken"]
    assert (
        client.get(
            "/api/admin/health",
            headers={
                "Authorization": f"Bearer {token}",
            },
        ).status_code
        == 200
    )
    repo.rows[1].role = "user"
    assert (
        client.get(
            "/api/admin/health",
            headers={
                "Authorization": f"Bearer {token}",
            },
        ).status_code
        == 401
    )


@pytest.mark.parametrize("proto,secure", [("https", True), ("http", False), ("", False)])
def test_cookie_issue_refresh_and_deletion_follow_external_scheme(accounts, proto, secure):
    client, _repo, _throttle = accounts
    headers = {"X-Forwarded-Proto": proto} if proto else {}
    created = register(client, headers=headers)
    cookie = created.headers["set-cookie"]
    assert ("; Secure" in cookie) is secure
    refreshed = client.post(
        "/api/auth/refresh",
        headers=headers,
        json={
            "refreshToken": created.json()["refreshToken"],
        },
    )
    assert refreshed.status_code == 200
    assert ("; Secure" in refreshed.headers["set-cookie"]) is secure
    logout = client.post("/api/auth/logout", headers=headers)
    assert ("; Secure" in logout.headers["set-cookie"]) is secure


def test_https_request_itself_sets_secure_cookie(accounts):
    client, _repo, _throttle = accounts
    result = client.post(
        "https://testserver/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "a-long-test-password",
        },
    )
    assert "; Secure" in result.headers["set-cookie"]


def test_production_api_locations_preserve_trusted_edge_scheme():
    config = (Path(__file__).resolve().parents[2] / "frontend/nginx.conf").read_text()
    assert "map $http_x_forwarded_proto $stockpilot_forwarded_proto" in config
    assert "default $scheme;" in config
    assert "https https;" in config
    assert config.count("proxy_set_header X-Forwarded-Proto $stockpilot_forwarded_proto;") == 2
    assert "proxy_set_header X-Forwarded-Proto $scheme;" not in config


@pytest.fixture
def backtests(monkeypatch):
    monkeypatch.setattr(stocks, "_method_backtest_gate", threading.BoundedSemaphore(1))
    monkeypatch.setattr(stocks, "_method_backtest_locks", LockRegistry())
    monkeypatch.setattr(
        stocks, "_method_backtest_budget", LoginThrottle(max_failures=2, window_seconds=60)
    )
    cache = TTLCache()

    class Companies:
        def get_companies(self, _market):
            return [GpwCompany(ticker="kgh", name="KGHM")]

    async def call(method="vsa4", value=1.200001, ip=None, horizon=10):
        return await stocks.get_method_backtest(
            method,
            request=request_for(ip) if ip else None,
            forward_sessions=horizon,
            vsa_settings=json.dumps({"spring": {"spreadMult": value}}),
            market="gpw",
            companies=Companies(),
            stooq=None,
            cache=cache,
            history_cache=TTLCache(),
            repo=None,
        )

    return call


def request_for(ip):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": (ip, 1234),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def fake_stats(kwargs):
    return MethodBacktestResponse(
        method_id=kwargs["method"].id,
        name=kwargs["method"].name,
        forward_sessions=kwargs["forward_sessions"],
    )


@pytest.mark.parametrize("method", [m.id for m in all_methods() if m.id != "vsa"])
async def test_irrelevant_settings_reuse_backtest_result(backtests, monkeypatch, method):
    calls = []

    async def compute(**kwargs):
        calls.append(kwargs)
        return fake_stats(kwargs)

    monkeypatch.setattr(stocks, "compute_method_backtest", compute)
    first = await backtests(method, 1.200001)
    second = await backtests(method, 1.200002)
    assert first is second
    assert len(calls) == 1
    assert calls[0]["config"].is_default()


async def test_real_settings_are_limited_but_cache_hits_and_other_clients_work(
    backtests,
    monkeypatch,
):
    calls = []

    async def compute(**kwargs):
        calls.append(kwargs)
        return fake_stats(kwargs)

    monkeypatch.setattr(stocks, "compute_method_backtest", compute)
    first = await backtests("vsa", 1.200001, "198.51.100.1")
    await backtests("vsa", 1.200002, "198.51.100.1")
    with pytest.raises(HTTPException) as limited:
        await backtests("vsa", 1.200003, "198.51.100.1")
    assert limited.value.status_code == 429
    assert await backtests("vsa", 1.200001, "198.51.100.1") is first
    await backtests("vsa", 1.200003, "198.51.100.2")
    assert len(calls) == 3


async def test_distinct_jobs_fail_fast_and_disconnect_does_not_release_work(backtests, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def compute(**kwargs):
        entered.set()
        await release.wait()
        return fake_stats(kwargs)

    monkeypatch.setattr(stocks, "compute_method_backtest", compute)
    first = asyncio.create_task(backtests("vsa", 1.200001))
    await entered.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    try:
        with pytest.raises(HTTPException) as busy:
            await backtests("vsa", 1.200002)
        assert busy.value.status_code == 429
    finally:
        release.set()
        for _ in range(5):
            await asyncio.sleep(0)
    await backtests("vsa", 1.200002)


async def test_provider_clients_use_real_certificate_validation(monkeypatch):
    original = httpx.AsyncClient
    contexts = []

    def factory(**kwargs):
        client = original(**kwargs)
        contexts.append(client._transport._pool._ssl_context)
        client.get = AsyncMock(return_value=httpx.Response(200, text="report " * 20))
        client.post = AsyncMock(return_value=httpx.Response(200, text="listing " * 20))
        return client

    monkeypatch.setattr("app.services.espi_client.httpx.AsyncClient", factory)
    client = EspiClient()
    assert await client._post_form("https://www.gpw.pl/ajaxindex.php", {})
    assert await client._get_url("https://www.gpw.pl/espi-ebi-report?geru_id=1")
    assert len(contexts) == 2
    assert all(ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname for ctx in contexts)


def test_curl_fallback_cannot_disable_tls_or_downgrade_redirects(monkeypatch):
    commands = []

    def check_output(command, **kwargs):
        commands.append(command)
        return b"test response"

    monkeypatch.setattr("subprocess.check_output", check_output)
    EspiClient._curl_post_sync("https://www.gpw.pl/ajaxindex.php", {})
    EspiClient._curl_get_sync("https://www.gpw.pl/espi-ebi-report?geru_id=1")
    for command in commands:
        assert command[command.index("--proto") + 1] == "=https"
        assert "-k" not in command and "--insecure" not in command
    get = commands[1]
    assert get[get.index("--proto-redir") + 1] == "=https"


async def test_noon_refresh_downloads_and_invalidates_only_insider_cache(monkeypatch):
    history = TTLCache()
    history.set("insider-checked:kgh", True, 60)
    history.set("insider-miss:pko", True, 60)
    history.set("history:kgh", "keep", 60)
    companies = [GpwCompany(ticker=ticker, name=ticker) for ticker in ("kgh", "pko")]
    ingest = IngestService(companies, None, InMemoryQuoteRepository(), history, TTLCache())
    fetch = AsyncMock(side_effect=[2, 3])
    monkeypatch.setattr(ingest, "_fetch_company_insiders", fetch)
    assert await ingest.run_insider_refresh() == {"companies": 2, "transactions": 5}
    assert fetch.await_count == 2
    assert history.get("insider-checked:kgh") is None
    assert history.get("insider-miss:pko") is None
    assert history.get("history:kgh") == "keep"
