"""Pydantic models for the sign-in endpoints (see agent/DOCUMENTATION.md §5.4).

Passwords only ever travel INTO the API, in a POST body — never in a query
string, which the action log records, and never back out in any response.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.auth import MAX_EMAIL_LENGTH, MAX_PASSWORD_BYTES


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


class AuthModel(BaseModel):
    """camelCase in JSON, snake_case in Python — as the rest of the API."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)


class RegisterRequest(AuthModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    # The length rules live in app/services/auth.py so the message a visitor
    # sees says WHY; this bound only stops an absurd payload.
    password: str = Field(max_length=1024)
    display_name: str | None = Field(default=None, max_length=80)


class LoginRequest(AuthModel):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=1024)


class RefreshRequest(AuthModel):
    refresh_token: str | None = Field(default=None, max_length=4096)


class ChangePasswordRequest(AuthModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=MAX_PASSWORD_BYTES * 4)


class UserResponse(AuthModel):
    """Who is signed in. Never carries the password hash."""

    id: int
    email: str
    display_name: str
    role: str
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AuthResponse(AuthModel):
    """What a successful register / login / refresh returns."""

    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    # Seconds until the ACCESS token expires; the browser refreshes before then.
    expires_in: int
    user: UserResponse


class AuthConfigResponse(AuthModel):
    """What the sign-in screen needs to know before showing anything.

    ``enabled`` is false when the deployment has no database: accounts have
    nowhere to live, so the UI hides the sign-in button instead of offering a
    form that can only fail.
    """

    enabled: bool
    registration_open: bool
    # True when the login tokens are signed with a configured secret. False
    # means a restart signs everyone out — fine locally, a warning in
    # production.
    persistent_sessions: bool
