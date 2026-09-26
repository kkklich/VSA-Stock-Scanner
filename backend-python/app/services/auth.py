"""User accounts: password hashing, JWT tokens and brute-force throttling.

The app is public — every page can still be read without an account — but a
visitor can register one and stay signed in across visits. Nothing here talks
to the network: passwords are hashed locally with bcrypt and the tokens are
signed locally with HS256, so accounts work exactly the same on a laptop as on
the VPS.

Two tokens, the standard split:

* **access token** — short-lived (30 minutes by default). Sent as
  ``Authorization: Bearer …`` on every request. Short, because a copy of it
  that leaks is only useful until it expires.
* **refresh token** — long-lived (30 days). Only ever sent to
  ``POST /api/auth/refresh`` to mint a new access token, so the visitor is not
  asked for the password again every half hour.

Both carry ``ver`` — the user's ``token_version``. Changing the password bumps
that number, which instantly invalidates every token issued before the change
without needing a server-side token store.

NOT here yet (no e-mail is sent by this app — see agent/ROADMAP.md #30):
address verification and password reset by e-mail.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# Claim values for the ``typ`` field, so a refresh token can never be replayed
# as an access token (it would otherwise be a 30-day password equivalent).
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

_ALGORITHM = "HS256"

# bcrypt hashes at most the first 72 BYTES of a password and silently ignores
# the rest — two different long passwords would then unlock the same account.
# Rather than pre-hashing (which hides the limit), refuse anything longer and
# say so.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8

# Deliberately permissive: this is a typo check, not an attempt to decide which
# addresses exist. Real verification needs a confirmation e-mail, which this
# app does not send yet.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
MAX_EMAIL_LENGTH = 254
MAX_DISPLAY_NAME_LENGTH = 80


class AuthError(Exception):
    """A credential or token problem, with a message safe to show a visitor."""


# ── Secret ────────────────────────────────────────────────────────────────────

# Generated once per process when STOCKPILOT_JWT_SECRET is unset. The key is as
# strong as a configured one; what it costs is continuity — every session ends
# when the backend restarts, because the next process signs with a different
# key. **Running without the setting is the owner's deliberate choice
# (2026-09-23): being asked to sign in again after an update is acceptable**,
# so this is a supported mode, not a misconfiguration to warn visitors about.
#
# The one case where it stops being merely inconvenient: more than one worker
# or replica. Each process would invent its own key, so a token minted by one
# would be refused by the next — sign-in would fail at random rather than only
# after a restart. Production runs a single Uvicorn worker on purpose (the
# scheduler and every cache are in-process), so this is a constraint to
# remember if that ever changes, not a problem today.
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)
_WARNED_ABOUT_EPHEMERAL = False


def jwt_secret() -> str:
    """The key the tokens are signed with."""
    global _WARNED_ABOUT_EPHEMERAL
    configured = settings.jwt_secret.strip()
    if configured:
        return configured
    if not _WARNED_ABOUT_EPHEMERAL:
        _WARNED_ABOUT_EPHEMERAL = True
        logger.info(
            "STOCKPILOT_JWT_SECRET is not set — signing logins with a key "
            "generated for this process, so every session ends when this "
            "process does. Set the secret to keep people signed in across "
            "restarts (required if this API is ever run with more than one "
            "worker)."
        )
    return _EPHEMERAL_SECRET


# ── Passwords ─────────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Return the bcrypt hash to store. Never store the password itself."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """True when ``password`` matches the stored hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # A stored hash that bcrypt cannot parse (hand-edited row, truncated
        # column). Treat as "does not match" rather than failing the request.
        logger.error("Stored password hash is not a valid bcrypt hash.")
        return False


_COMMON_PASSWORDS = frozenset({
    "password", "password123", "12345678", "123456789", "qwertyui",
    "qwerty1234", "letmein1", "admin123", "welcome1", "iloveyou",
})


def validate_password(password: str) -> str:
    """Return the password if it is usable, else raise :class:`AuthError`."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise AuthError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes long "
            "(bcrypt ignores anything past that)."
        )
    if password.lower() in _COMMON_PASSWORDS:
        raise AuthError("That password is too common and easily guessed.")
    return password


# ── E-mail / display name ─────────────────────────────────────────────────────


def normalize_email(email: str) -> str:
    """Lower-cased and trimmed — the form stored and compared against.

    Addresses are case-insensitive in practice, so ``Krzysztof@x.pl`` and
    ``krzysztof@x.pl`` must not become two accounts.
    """
    normalized = email.strip().lower()
    if len(normalized) > MAX_EMAIL_LENGTH or not _EMAIL_RE.match(normalized):
        raise AuthError("That does not look like an e-mail address.")
    return normalized


def clean_display_name(name: str | None, email: str) -> str:
    """A name to greet the visitor by: what they typed, else the local part."""
    candidate = (name or "").strip()
    if not candidate:
        candidate = email.split("@", 1)[0]
    return candidate[:MAX_DISPLAY_NAME_LENGTH]


def is_admin_email(email: str) -> bool:
    """True when the address is listed in ``STOCKPILOT_ADMIN_EMAILS``.

    The only way to become an admin: there is no self-service promotion and no
    "first account wins" rule, which would hand the site to whoever registered
    first. The role is informational today — ``/api/admin/*`` still uses its own
    shared token — but it is stored from the start so the gate can move later
    without a migration.
    """
    listed = {
        part.strip().lower()
        for part in settings.admin_emails.split(",")
        if part.strip()
    }
    return email.lower() in listed


# ── Tokens ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """What a verified token says about who is calling."""

    user_id: int
    email: str
    role: str
    token_version: int
    token_type: str
    expires_at: datetime


def _create_token(
    *,
    user_id: int,
    email: str,
    role: str,
    token_version: int,
    token_type: str,
    lifetime: timedelta,
) -> tuple[str, datetime]:
    now = datetime.now(tz=UTC)
    expires_at = now + lifetime
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "ver": token_version,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=_ALGORITHM), expires_at


def create_access_token(
    *, user_id: int, email: str, role: str, token_version: int
) -> tuple[str, int]:
    """Return ``(token, seconds_until_it_expires)``."""
    lifetime = timedelta(minutes=settings.jwt_access_minutes)
    token, _ = _create_token(
        user_id=user_id,
        email=email,
        role=role,
        token_version=token_version,
        token_type=TOKEN_TYPE_ACCESS,
        lifetime=lifetime,
    )
    return token, int(lifetime.total_seconds())


def create_refresh_token(
    *, user_id: int, email: str, role: str, token_version: int
) -> str:
    token, _ = _create_token(
        user_id=user_id,
        email=email,
        role=role,
        token_version=token_version,
        token_type=TOKEN_TYPE_REFRESH,
        lifetime=timedelta(days=settings.jwt_refresh_days),
    )
    return token


def decode_token(token: str, *, expected_type: str) -> TokenClaims:
    """Verify a token's signature, expiry and kind, or raise :class:`AuthError`.

    ``expected_type`` is what makes the two tokens genuinely different: a
    30-day refresh token presented as a bearer credential is rejected here
    rather than accepted as a very long-lived login.
    """
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Your session has expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid sign-in token.") from exc

    if payload.get("typ") != expected_type:
        raise AuthError("Invalid sign-in token.")
    try:
        user_id = int(payload["sub"])
        return TokenClaims(
            user_id=user_id,
            email=str(payload.get("email", "")),
            role=str(payload.get("role", "user")),
            token_version=int(payload.get("ver", 0)),
            token_type=str(payload["typ"]),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("Invalid sign-in token.") from exc


# ── Brute-force throttle ──────────────────────────────────────────────────────


class LoginThrottle:
    """Counts recent failed sign-ins per key (an e-mail, or a caller's IP).

    In-process and deliberately simple: the API runs as a single Uvicorn worker
    (the scheduler and every cache are in-process too), so one dictionary is the
    whole picture. It cannot survive a restart, which is the right trade — a
    restart is rare, and locking a real visitor out of their account across one
    would be worse than letting a guesser start over.
    """

    def __init__(self, *, max_failures: int = 10, window_seconds: int = 900) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        stamps = [t for t in self._failures.get(key, []) if now - t < self._window]
        if stamps:
            self._failures[key] = stamps
        else:
            self._failures.pop(key, None)
        return stamps

    def is_blocked(self, key: str) -> bool:
        return len(self._recent(key, time.monotonic())) >= self._max

    def retry_after_seconds(self, key: str) -> int:
        now = time.monotonic()
        stamps = self._recent(key, now)
        if len(stamps) < self._max:
            return 0
        return max(1, int(self._window - (now - stamps[0])))

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        stamps = self._recent(key, now)
        stamps.append(now)
        self._failures[key] = stamps
        # Bound the dictionary: a flood of distinct keys (spoofed addresses)
        # must not grow the process. Dropping the least recently active entry
        # only ever forgives failures, never invents them.
        if len(self._failures) > 4096:
            oldest = min(self._failures, key=lambda k: self._failures[k][-1])
            self._failures.pop(oldest, None)

    def clear(self, key: str) -> None:
        """Forget a key's failures — called after a successful sign-in."""
        self._failures.pop(key, None)
