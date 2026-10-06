"""Sign-in: passwords, tokens, throttling and the /api/auth endpoints.

The account store is faked in memory (``_FakeUserRepository``) so the suite
needs no database, exactly as the market-data tests fake the quote repository.
What is NOT faked is the part worth testing: bcrypt hashing, the real JWT
encode/decode and the router's own rules.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.models import UserRow
from app.db.user_repository import EmailAlreadyRegistered
from app.dependencies import get_login_throttle, get_user_repository
from app.main import app
from app.services import auth as auth_service
from app.services.auth import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    AuthError,
    LoginThrottle,
    clean_display_name,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
)

# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeUserRepository:
    """The UserRepository contract over a dict."""

    def __init__(self) -> None:
        self.rows: dict[int, UserRow] = {}
        self._next_id = 1

    async def create(
        self, *, email: str, password_hash: str, display_name: str, role: str = "user"
    ) -> UserRow:
        if any(r.email == email for r in self.rows.values()):
            raise EmailAlreadyRegistered(email)
        row = UserRow(
            id=self._next_id,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            is_active=True,
            email_verified=False,
            token_version=1,
            created_at=datetime.now(tz=UTC),
            last_login_at=None,
        )
        self.rows[row.id] = row
        self._next_id += 1
        return row

    async def get_by_email(self, email: str) -> UserRow | None:
        return next((r for r in self.rows.values() if r.email == email), None)

    async def get_by_id(self, user_id: int) -> UserRow | None:
        return self.rows.get(user_id)

    async def touch_last_login(self, user_id: int) -> None:
        row = self.rows.get(user_id)
        if row is not None:
            row.last_login_at = datetime.now(tz=UTC)

    async def set_password(self, user_id: int, password_hash: str) -> None:
        row = self.rows[user_id]
        row.password_hash = password_hash
        row.token_version += 1

    async def count(self) -> int:
        return len(self.rows)


@pytest.fixture
def repo() -> _FakeUserRepository:
    return _FakeUserRepository()


@pytest.fixture
def client(repo: _FakeUserRepository):
    """A TestClient with accounts available and a fresh sign-in throttle."""
    throttle = LoginThrottle()
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_login_throttle] = lambda: throttle
    with TestClient(app) as test_client:
        test_client.throttle = throttle  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()


def _register(client: TestClient, email="ala@example.com", password="tajne-haslo-1"):
    return client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )


# ── Passwords ─────────────────────────────────────────────────────────────────


class TestPasswords:
    def test_hash_is_not_the_password_and_verifies(self) -> None:
        hashed = hash_password("tajne-haslo-1")
        assert "tajne-haslo-1" not in hashed
        assert verify_password("tajne-haslo-1", hashed)
        assert not verify_password("tajne-haslo-2", hashed)

    def test_same_password_hashes_differently_each_time(self) -> None:
        # Per-password salt: two people with the same password must not share
        # a hash, or one leaked hash would identify every account using it.
        assert hash_password("tajne-haslo-1") != hash_password("tajne-haslo-1")

    def test_short_password_is_refused(self) -> None:
        with pytest.raises(AuthError):
            validate_password("krotkie")

    def test_password_past_bcrypt_limit_is_refused_not_truncated(self) -> None:
        # bcrypt ignores everything past 72 bytes; accepting a longer password
        # would mean two different ones open the same account.
        with pytest.raises(AuthError):
            validate_password("a" * 73)
        assert validate_password("a" * 72) == "a" * 72

    def test_corrupt_stored_hash_is_a_mismatch_not_a_crash(self) -> None:
        assert verify_password("tajne-haslo-1", "not-a-bcrypt-hash") is False

    def test_common_passwords_are_refused(self) -> None:
        for common in ["password123", "12345678", "qwerty1234", "admin123"]:
            with pytest.raises(AuthError) as exc_info:
                validate_password(common)
            assert "too common" in str(exc_info.value).lower()


# ── E-mail + display name ─────────────────────────────────────────────────────


class TestEmail:
    def test_address_is_lowercased_and_trimmed(self) -> None:
        assert normalize_email("  Ala@Example.PL ") == "ala@example.pl"

    @pytest.mark.parametrize(
        "bad", ["", "ala", "ala@", "@example.pl", "ala@example", "a b@example.pl"]
    )
    def test_malformed_addresses_are_refused(self, bad: str) -> None:
        with pytest.raises(AuthError):
            normalize_email(bad)

    def test_display_name_falls_back_to_the_local_part(self) -> None:
        assert clean_display_name(None, "ala@example.pl") == "ala"
        assert clean_display_name("  Ala K  ", "ala@example.pl") == "Ala K"


# ── Tokens ────────────────────────────────────────────────────────────────────


class TestTokens:
    def test_round_trip_carries_the_account(self) -> None:
        token, expires_in = create_access_token(
            user_id=7, email="ala@example.pl", role="user", token_version=3
        )
        claims = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
        assert (claims.user_id, claims.email, claims.token_version) == (
            7,
            "ala@example.pl",
            3,
        )
        assert expires_in == settings.jwt_access_minutes * 60

    def test_a_refresh_token_is_not_accepted_as_an_access_token(self) -> None:
        # Otherwise the 30-day token would be a 30-day password equivalent.
        refresh = create_refresh_token(
            user_id=1, email="ala@example.pl", role="user", token_version=1
        )
        with pytest.raises(AuthError):
            decode_token(refresh, expected_type=TOKEN_TYPE_ACCESS)
        assert (
            decode_token(refresh, expected_type=TOKEN_TYPE_REFRESH).token_type
            == TOKEN_TYPE_REFRESH
        )

    def test_a_token_signed_with_another_key_is_refused(self) -> None:
        forged = jwt.encode(
            {
                "sub": "1",
                "typ": TOKEN_TYPE_ACCESS,
                "ver": 1,
                "exp": int((datetime.now(tz=UTC) + timedelta(hours=1)).timestamp()),
            },
            "not-the-servers-secret",
            algorithm="HS256",
        )
        with pytest.raises(AuthError):
            decode_token(forged, expected_type=TOKEN_TYPE_ACCESS)

    def test_an_expired_token_is_refused(self) -> None:
        expired = jwt.encode(
            {
                "sub": "1",
                "typ": TOKEN_TYPE_ACCESS,
                "ver": 1,
                "exp": int((datetime.now(tz=UTC) - timedelta(minutes=1)).timestamp()),
            },
            auth_service.jwt_secret(),
            algorithm="HS256",
        )
        with pytest.raises(AuthError):
            decode_token(expired, expected_type=TOKEN_TYPE_ACCESS)


# ── Throttle ──────────────────────────────────────────────────────────────────


class TestLoginThrottle:
    def test_blocks_after_the_limit_and_clears_on_success(self) -> None:
        throttle = LoginThrottle(max_failures=3, window_seconds=900)
        for _ in range(3):
            throttle.record_failure("email:ala@example.pl")
        assert throttle.is_blocked("email:ala@example.pl")
        assert throttle.retry_after_seconds("email:ala@example.pl") > 0
        throttle.clear("email:ala@example.pl")
        assert not throttle.is_blocked("email:ala@example.pl")

    def test_failures_are_counted_per_key(self) -> None:
        throttle = LoginThrottle(max_failures=2, window_seconds=900)
        throttle.record_failure("email:ala@example.pl")
        throttle.record_failure("email:ala@example.pl")
        assert throttle.is_blocked("email:ala@example.pl")
        assert not throttle.is_blocked("email:ola@example.pl")

    def test_old_failures_fall_out_of_the_window(self) -> None:
        throttle = LoginThrottle(max_failures=2, window_seconds=0)
        throttle.record_failure("ip:1.2.3.4")
        throttle.record_failure("ip:1.2.3.4")
        assert not throttle.is_blocked("ip:1.2.3.4")


# ── Endpoints ─────────────────────────────────────────────────────────────────


class TestRegister:
    def test_creates_an_account_and_signs_it_in(self, client: TestClient) -> None:
        response = _register(client)
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "ala@example.com"
        assert body["user"]["displayName"] == "ala"
        assert body["tokenType"] == "bearer"
        assert body["accessToken"] and body["refreshToken"]

    def test_never_returns_the_password_or_its_hash(
        self, client: TestClient, repo: _FakeUserRepository
    ) -> None:
        raw = _register(client).text
        assert "tajne-haslo-1" not in raw
        assert repo.rows[1].password_hash not in raw

    def test_the_same_address_cannot_register_twice(self, client: TestClient) -> None:
        assert _register(client).status_code == 201
        second = _register(client, email="ALA@example.com", password="inne-haslo-12")
        assert second.status_code == 409

    def test_a_weak_password_is_refused(self, client: TestClient) -> None:
        response = _register(client, password="krotkie")
        assert response.status_code == 400
        assert "8" in response.json()["detail"]["message"]

    def test_a_malformed_address_is_refused(self, client: TestClient) -> None:
        assert _register(client, email="nonsense").status_code == 400

    def test_the_admin_email_list_is_the_only_way_to_become_admin(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert _register(client).json()["user"]["role"] == "user"
        monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
        promoted = _register(client, email="boss@example.com")
        assert promoted.json()["user"]["role"] == "admin"

    def test_admin_registration_requires_admin_token_when_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
        monkeypatch.setattr(settings, "admin_token", "super-secret-token")

        # Registration without token fails with 403
        denied = client.post(
            "/api/auth/register",
            json={"email": "boss@example.com", "password": "tajne-haslo-1"},
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "admin_token_required"

        # Registration with wrong token fails with 403
        denied_wrong = client.post(
            "/api/auth/register",
            json={"email": "boss@example.com", "password": "tajne-haslo-1"},
            headers={"X-Admin-Token": "wrong-token"},
        )
        assert denied_wrong.status_code == 403

        # Registration with correct token succeeds and grants admin role
        allowed = client.post(
            "/api/auth/register",
            json={"email": "boss@example.com", "password": "tajne-haslo-1"},
            headers={"X-Admin-Token": "super-secret-token"},
        )
        assert allowed.status_code == 201
        assert allowed.json()["user"]["role"] == "admin"

    def test_registration_can_be_closed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "registration_open", False)
        assert _register(client).status_code == 403


class TestLogin:
    def test_correct_credentials_return_tokens(self, client: TestClient) -> None:
        _register(client)
        response = client.post(
            "/api/auth/login",
            json={"email": "Ala@Example.com", "password": "tajne-haslo-1"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "ala@example.com"

    def test_wrong_password_and_unknown_account_answer_identically(
        self, client: TestClient
    ) -> None:
        # Different messages would turn this endpoint into a way to find out
        # which addresses are registered here.
        _register(client)
        wrong = client.post(
            "/api/auth/login",
            json={"email": "ala@example.com", "password": "zupelnie-inne"},
        )
        unknown = client.post(
            "/api/auth/login",
            json={"email": "nikt@example.com", "password": "zupelnie-inne"},
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["detail"] == unknown.json()["detail"]

    def test_a_deactivated_account_cannot_sign_in(
        self, client: TestClient, repo: _FakeUserRepository
    ) -> None:
        _register(client)
        repo.rows[1].is_active = False
        response = client.post(
            "/api/auth/login",
            json={"email": "ala@example.com", "password": "tajne-haslo-1"},
        )
        assert response.status_code == 401

    def test_repeated_failures_are_throttled(self, client: TestClient) -> None:
        _register(client)
        codes = [
            client.post(
                "/api/auth/login",
                json={"email": "ala@example.com", "password": "zle-haslo-xx"},
            ).status_code
            for _ in range(12)
        ]
        assert 429 in codes
        assert codes[-1] == 429

    def test_attacker_cannot_lock_out_legitimate_user(
        self, client: TestClient
    ) -> None:
        _register(client)
        attacker_headers = {"X-Forwarded-For": "198.51.100.5"}
        # Attacker on an external IP spams wrong password repeatedly until email throttling kicks in
        for _ in range(12):
            client.post(
                "/api/auth/login",
                json={"email": "ala@example.com", "password": "wrong-password-guess"},
                headers=attacker_headers,
            )
        # Verify that wrong password attempts for this email now receive 429 even from another IP
        wrong = client.post(
            "/api/auth/login",
            json={"email": "ala@example.com", "password": "wrong-password-guess"},
            headers={"X-Forwarded-For": "198.51.100.6"},
        )
        assert wrong.status_code == 429

        # Legitimate user from their own IP entering the correct password can
        # still log in successfully
        legit = client.post(
            "/api/auth/login",
            json={"email": "ala@example.com", "password": "tajne-haslo-1"},
            headers={"X-Forwarded-For": "203.0.113.42"},
        )
        assert legit.status_code == 200
        assert legit.json()["user"]["email"] == "ala@example.com"

    def test_a_successful_sign_in_clears_the_throttle(self, client: TestClient) -> None:
        _register(client)
        for _ in range(3):
            client.post(
                "/api/auth/login",
                json={"email": "ala@example.com", "password": "zle-haslo-xx"},
            )
        good = client.post(
            "/api/auth/login",
            json={"email": "ala@example.com", "password": "tajne-haslo-1"},
        )
        assert good.status_code == 200
        assert not client.throttle.is_blocked("email:ala@example.com")  # type: ignore[attr-defined]

    def test_last_login_is_recorded(
        self, client: TestClient, repo: _FakeUserRepository
    ) -> None:
        _register(client)
        assert repo.rows[1].last_login_at is None
        client.post(
            "/api/auth/login",
            json={"email": "ala@example.com", "password": "tajne-haslo-1"},
        )
        assert repo.rows[1].last_login_at is not None


class TestMe:
    def test_returns_the_signed_in_account(self, client: TestClient) -> None:
        token = _register(client).json()["accessToken"]
        response = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == "ala@example.com"

    def test_without_a_token_it_is_401(self, client: TestClient) -> None:
        assert client.get("/api/auth/me").status_code == 401

    def test_a_garbage_token_is_401(self, client: TestClient) -> None:
        response = client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not-a-token"}
        )
        assert response.status_code == 401

    def test_a_refresh_token_is_not_a_bearer_credential(
        self, client: TestClient
    ) -> None:
        refresh = _register(client).json()["refreshToken"]
        response = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {refresh}"}
        )
        assert response.status_code == 401

    def test_a_deleted_account_cannot_keep_using_its_token(
        self, client: TestClient, repo: _FakeUserRepository
    ) -> None:
        token = _register(client).json()["accessToken"]
        repo.rows.clear()
        response = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestRefresh:
    def test_exchanges_a_refresh_token_for_a_working_access_token(
        self, client: TestClient
    ) -> None:
        refresh = _register(client).json()["refreshToken"]
        response = client.post("/api/auth/refresh", json={"refreshToken": refresh})
        assert response.status_code == 200
        new_access = response.json()["accessToken"]
        assert (
            client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}
            ).status_code
            == 200
        )

    def test_an_access_token_cannot_be_used_to_refresh(
        self, client: TestClient
    ) -> None:
        access = _register(client).json()["accessToken"]
        assert (
            client.post("/api/auth/refresh", json={"refreshToken": access}).status_code
            == 401
        )

    def test_refresh_via_httponly_cookie(self, client: TestClient) -> None:
        reg_response = _register(client)
        assert reg_response.status_code == 201
        assert "stockpilot_refresh_token" in reg_response.cookies

        # Call refresh without body, relying on the HttpOnly cookie
        response = client.post("/api/auth/refresh", json={})
        assert response.status_code == 200
        new_access = response.json()["accessToken"]
        assert (
            client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {new_access}"}
            ).status_code
            == 200
        )
        # Cookie is rotated on refresh
        assert "stockpilot_refresh_token" in response.cookies

    def test_logout_clears_cookie(self, client: TestClient) -> None:
        _register(client)
        logout_response = client.post("/api/auth/logout")
        assert logout_response.status_code == 200
        # Subsequent refresh without token or cookie fails
        refresh_response = client.post("/api/auth/refresh", json={})
        assert refresh_response.status_code == 401


class TestChangePassword:
    def test_changes_the_password_and_returns_usable_tokens(
        self, client: TestClient
    ) -> None:
        token = _register(client).json()["accessToken"]
        response = client.post(
            "/api/auth/change-password",
            json={"currentPassword": "tajne-haslo-1", "newPassword": "nowe-haslo-99"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        # Signed in with the NEW token, and the new password works.
        assert (
            client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {response.json()['accessToken']}"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "ala@example.com", "password": "nowe-haslo-99"},
            ).status_code
            == 200
        )

    def test_old_tokens_stop_working_after_the_change(
        self, client: TestClient
    ) -> None:
        # token_version is bumped, so a session someone else was holding dies
        # with the old password.
        body = _register(client).json()
        old_access, old_refresh = body["accessToken"], body["refreshToken"]
        client.post(
            "/api/auth/change-password",
            json={"currentPassword": "tajne-haslo-1", "newPassword": "nowe-haslo-99"},
            headers={"Authorization": f"Bearer {old_access}"},
        )
        assert (
            client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {old_access}"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/refresh", json={"refreshToken": old_refresh}
            ).status_code
            == 401
        )

    def test_the_wrong_current_password_changes_nothing(
        self, client: TestClient, repo: _FakeUserRepository
    ) -> None:
        token = _register(client).json()["accessToken"]
        before = repo.rows[1].password_hash
        response = client.post(
            "/api/auth/change-password",
            json={"currentPassword": "nie-to-haslo", "newPassword": "nowe-haslo-99"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert repo.rows[1].password_hash == before

    def test_a_weak_new_password_is_refused(self, client: TestClient) -> None:
        token = _register(client).json()["accessToken"]
        response = client.post(
            "/api/auth/change-password",
            json={"currentPassword": "tajne-haslo-1", "newPassword": "krotkie"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400


class TestWithoutDatabase:
    """The app also runs stateless — accounts then have nowhere to live."""

    def test_config_reports_accounts_unavailable(self) -> None:
        app.dependency_overrides[get_user_repository] = lambda: None
        try:
            with TestClient(app) as client:
                body = client.get("/api/auth/config").json()
                assert body["enabled"] is False
        finally:
            app.dependency_overrides.clear()

    def test_register_and_login_answer_503(self) -> None:
        app.dependency_overrides[get_user_repository] = lambda: None
        try:
            with TestClient(app) as client:
                assert _register(client).status_code == 503
                assert (
                    client.post(
                        "/api/auth/login",
                        json={"email": "ala@example.com", "password": "tajne-haslo-1"},
                    ).status_code
                    == 503
                )
        finally:
            app.dependency_overrides.clear()


class TestErrorCodes:
    """Every failure carries a stable code, so the UI can speak Polish."""

    def test_each_failure_names_its_cause(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _register(client)
        monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
        monkeypatch.setattr(settings, "admin_token", "secret")
        cases = [
            (
                client.post(
                    "/api/auth/login",
                    json={"email": "ala@example.com", "password": "zle-haslo-xx"},
                ),
                "bad_credentials",
            ),
            (_register(client), "email_taken"),
            (_register(client, email="ola@example.com", password="x"), "weak_password"),
            (_register(client, email="nonsense"), "invalid_email"),
            (client.get("/api/auth/me"), "not_signed_in"),
            (
                client.post(
                    "/api/auth/register",
                    json={"email": "admin@example.com", "password": "tajne-haslo-1"},
                ),
                "admin_token_required",
            ),
        ]
        for response, expected in cases:
            body = response.json()["detail"]
            assert body["code"] == expected, body
            # The English message is still there as a fallback for a client
            # that does not know the code.
            assert body["message"]


class TestConfig:
    def test_reports_what_the_sign_in_screen_needs(self, client: TestClient) -> None:
        body = client.get("/api/auth/config").json()
        assert body["enabled"] is True
        assert body["registrationOpen"] is True
        assert "persistentSessions" in body


class TestPublicPagesStayPublic:
    """Signing in is optional: the market data is readable without an account."""

    def test_the_company_list_needs_no_token(self, client: TestClient) -> None:
        assert client.get("/api/stocks").status_code == 200

    def test_the_password_never_reaches_the_action_log(
        self, client: TestClient
    ) -> None:
        # Credentials travel in the POST body, which the log does not record —
        # only the method, the route template and the query string.
        from app.dependencies import action_log

        _register(client)
        entries = [
            e
            for e in action_log.recent(action="/api/auth/register")
            if e.path == "/api/auth/register"
        ]
        assert entries, "the registration should be on the record"
        assert all("tajne-haslo-1" not in (e.query or "") for e in entries)
