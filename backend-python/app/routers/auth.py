"""Sign-in endpoints — optional accounts for visitors.

    GET  /api/auth/config           — is sign-in available here, is it open?
    POST /api/auth/register         — create an account
    POST /api/auth/login            — exchange e-mail + password for tokens
    POST /api/auth/refresh          — exchange a refresh token for a new pair
    GET  /api/auth/me               — who am I (requires a bearer token)
    POST /api/auth/change-password  — change it while signed in

The site stays public: nothing in ``/api/stocks`` requires an account. An
account is a place to put per-person settings, and the sign-in state is what
the top bar shows. ``get_optional_user`` is the dependency to use when an
endpoint wants to know who is calling without demanding it;
``get_current_user`` is the one that requires it.

No e-mail is sent by this app yet, so there is deliberately no "verify your
address" step and no "forgot my password" link — see agent/ROADMAP.md #30.
A signed-in visitor can still change their own password.
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.config import settings
from app.db.models import UserRow
from app.db.user_repository import EmailAlreadyRegistered, UserRepository
from app.dependencies import get_login_throttle, get_user_repository
from app.models.auth import (
    AuthConfigResponse,
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
)
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
    is_admin_email,
    normalize_email,
    validate_password,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for "no such account" and for "wrong password" alike: telling the
# two apart would turn this endpoint into a way to find out which addresses are
# registered here.
_BAD_CREDENTIALS = "E-mail or password is incorrect."


def _fail(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    """An error the sign-in screen can translate.

    ``detail`` is an object rather than a plain string: the message stays
    English like every other message this API returns, but ``code`` is stable,
    so the frontend can show the visitor's own language and fall back to the
    message for anything it does not recognise. These endpoints are the one
    part of the API an ordinary visitor reads directly, which is what makes
    the extra shape worth it.
    """
    return HTTPException(
        status_code, detail={"code": code, "message": message}, headers=headers
    )


def _require_repo(
    repo: UserRepository | None,
) -> UserRepository:
    if repo is None:
        raise _fail(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "accounts_unavailable",
            "Accounts are unavailable on this deployment: no database is "
            "configured (STOCKPILOT_DATABASE_URL).",
        )
    return repo


def _to_user_response(row: UserRow) -> UserResponse:
    return UserResponse(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        role=row.role,
        email_verified=row.email_verified,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )


REFRESH_COOKIE_NAME = "stockpilot_refresh_token"
LEGACY_REFRESH_COOKIE_NAME = "refresh_token"


def _is_secure_request(request: Request | None) -> bool:
    if request is None:
        return False
    if request.url.scheme == "https":
        return True
    proto = request.headers.get("x-forwarded-proto", "")
    return proto.lower() == "https"


def _set_refresh_cookie(
    response: Response,
    refresh_token: str,
    request: Request | None = None,
) -> None:
    max_age = settings.jwt_refresh_days * 86400
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        expires=max_age,
        path="/api/auth",
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(request),
    )


def _delete_refresh_cookie(
    response: Response,
    request: Request | None = None,
) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(request),
    )
    response.delete_cookie(
        key=LEGACY_REFRESH_COOKIE_NAME,
        path="/api/auth",
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(request),
    )


def _issue(
    row: UserRow,
    response: Response | None = None,
    request: Request | None = None,
) -> AuthResponse:
    """Mint a fresh token pair for an account and set the HttpOnly cookie."""
    access, expires_in = create_access_token(
        user_id=row.id,
        email=row.email,
        role=row.role,
        token_version=row.token_version,
    )
    refresh = create_refresh_token(
        user_id=row.id,
        email=row.email,
        role=row.role,
        token_version=row.token_version,
    )
    if response is not None:
        _set_refresh_cookie(response, refresh, request)

    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
        user=_to_user_response(row),
    )


def _client_key(request: Request) -> str:
    """A throttling key for the caller's address."""
    from app.services.action_log import _client_ip

    ip = _client_ip(request) if request else None
    return f"ip:{ip or (request.client.host if request and request.client else 'unknown')}"


# ── Dependencies other routers can use ────────────────────────────────────────


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    repo: Annotated[UserRepository | None, Depends(get_user_repository)] = None,
) -> UserRow | None:
    """The signed-in account, or None — never raises.

    For endpoints that behave slightly differently for a signed-in visitor but
    must keep working for everyone else (which, on this site, is all of them).
    """
    if not authorization or repo is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        claims = decode_token(token.strip(), expected_type=TOKEN_TYPE_ACCESS)
    except AuthError:
        return None
    row = await repo.get_by_id(claims.user_id)
    if row is None or not row.is_active or row.token_version != claims.token_version:
        return None
    return row


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    repo: Annotated[UserRepository | None, Depends(get_user_repository)] = None,
) -> UserRow:
    """The signed-in account, or 401. For endpoints that require an account."""
    repository = _require_repo(repo)
    if not authorization:
        raise _fail(
            status.HTTP_401_UNAUTHORIZED,
            "not_signed_in",
            "Sign in to use this.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _fail(
            status.HTTP_401_UNAUTHORIZED,
            "not_signed_in",
            "Expected an 'Authorization: Bearer <token>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(token.strip(), expected_type=TOKEN_TYPE_ACCESS)
    except AuthError as exc:
        raise _fail(
            status.HTTP_401_UNAUTHORIZED,
            "session_expired",
            str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    row = await repository.get_by_id(claims.user_id)
    if row is None or not row.is_active:
        raise _fail(
            status.HTTP_401_UNAUTHORIZED, "account_not_found", "Account not found."
        )
    if row.token_version != claims.token_version:
        # The password changed after this token was issued.
        raise _fail(
            status.HTTP_401_UNAUTHORIZED,
            "session_expired",
            "Your session has ended. Please sign in again.",
        )
    return row


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/config",
    response_model=AuthConfigResponse,
    summary="Whether accounts work on this deployment",
)
async def auth_config(
    repo: Annotated[UserRepository | None, Depends(get_user_repository)] = None,
) -> AuthConfigResponse:
    return AuthConfigResponse(
        enabled=repo is not None,
        registration_open=settings.registration_open,
        persistent_sessions=bool(settings.jwt_secret.strip()),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
async def register(
    payload: RegisterRequest,
    response: Response,
    request: Request,
    repo: Annotated[UserRepository | None, Depends(get_user_repository)] = None,
    throttle: Annotated[LoginThrottle, Depends(get_login_throttle)] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> AuthResponse:
    repository = _require_repo(repo)
    if not settings.registration_open:
        raise _fail(
            status.HTTP_403_FORBIDDEN,
            "registration_closed",
            "New accounts are closed on this deployment.",
        )

    # Registration is rate-limited by address too: it is the one endpoint that
    # writes a row for an anonymous caller.
    key = _client_key(request)
    if throttle is not None and throttle.is_blocked(key):
        raise _fail(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_attempts",
            "Too many attempts. Please wait a few minutes.",
            headers={"Retry-After": str(throttle.retry_after_seconds(key))},
        )

    try:
        email = normalize_email(payload.email)
    except AuthError as exc:
        if throttle is not None:
            throttle.record_failure(key)
        raise _fail(status.HTTP_400_BAD_REQUEST, "invalid_email", str(exc)) from exc
    try:
        validate_password(payload.password)
    except AuthError as exc:
        if throttle is not None:
            throttle.record_failure(key)
        raise _fail(status.HTTP_400_BAD_REQUEST, "weak_password", str(exc)) from exc

    wants_admin = is_admin_email(email)
    if wants_admin and settings.admin_token:
        if not x_admin_token or not secrets.compare_digest(
            x_admin_token, settings.admin_token
        ):
            raise _fail(
                status.HTTP_403_FORBIDDEN,
                "admin_token_required",
                "Registering an administrator account requires the administrator token.",
            )

    try:
        row = await repository.create(
            email=email,
            password_hash=hash_password(payload.password),
            display_name=clean_display_name(payload.display_name, email),
            role="admin" if wants_admin else "user",
        )
    except EmailAlreadyRegistered as exc:
        raise _fail(
            status.HTTP_409_CONFLICT,
            "email_taken",
            "That e-mail address already has an account. Sign in instead.",
        ) from exc

    logger.info("New account registered (id=%s).", row.id)
    return _issue(row, response=response, request=request)


@router.post("/login", response_model=AuthResponse, summary="Sign in")
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    repo: Annotated[UserRepository | None, Depends(get_user_repository)] = None,
    throttle: Annotated[LoginThrottle, Depends(get_login_throttle)] = None,
) -> AuthResponse:
    repository = _require_repo(repo)

    try:
        email = normalize_email(payload.email)
    except AuthError as exc:
        raise _fail(
            status.HTTP_401_UNAUTHORIZED, "bad_credentials", _BAD_CREDENTIALS
        ) from exc

    # Throttled on both the address and the caller's IP: the first stops one
    # account being ground through a password list from many machines, the
    # second stops one machine walking a list of addresses.
    ip_key = _client_key(request)
    email_key = f"email:{email}"
    keys = [email_key, ip_key]

    # Block the caller IP if this address has flooded failed attempts
    if throttle is not None and throttle.is_blocked(ip_key):
        raise _fail(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_attempts",
            "Too many sign-in attempts from this address. Please wait a few minutes.",
            headers={"Retry-After": str(throttle.retry_after_seconds(ip_key))},
        )

    row = await repository.get_by_email(email)
    credentials_valid = (
        row is not None
        and row.is_active
        and verify_password(payload.password, row.password_hash)
    )

    if not credentials_valid:
        if throttle is not None:
            for key in keys:
                throttle.record_failure(key)
        # If this email has sustained repeated failures, throttle bad guesses
        # without locking out a genuine user who enters the correct password.
        if throttle is not None and throttle.is_blocked(email_key):
            raise _fail(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "too_many_attempts",
                "Too many sign-in attempts. Please wait a few minutes.",
                headers={"Retry-After": str(throttle.retry_after_seconds(email_key))},
            )
        raise _fail(status.HTTP_401_UNAUTHORIZED, "bad_credentials", _BAD_CREDENTIALS)

    if throttle is not None:
        for key in keys:
            throttle.clear(key)

    try:
        await repository.touch_last_login(row.id)
    except Exception:
        # A failed bookkeeping write must not cost someone their sign-in.
        logger.exception("Could not record last_login_at for user %s.", row.id)

    return _issue(row, response=response, request=request)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Get a new access token from a refresh token or cookie",
)
async def refresh(
    response: Response,
    request: Request,
    payload: RefreshRequest | None = None,
    repo: Annotated[UserRepository | None, Depends(get_user_repository)] = None,
) -> AuthResponse:
    repository = _require_repo(repo)

    token_str: str | None = None
    if payload is not None and payload.refresh_token:
        token_str = payload.refresh_token
    else:
        token_str = request.cookies.get(REFRESH_COOKIE_NAME) or request.cookies.get(
            LEGACY_REFRESH_COOKIE_NAME
        )

    if not token_str:
        raise _fail(
            status.HTTP_401_UNAUTHORIZED,
            "session_expired",
            "Your session has ended. Please sign in again.",
        )

    try:
        claims = decode_token(token_str, expected_type=TOKEN_TYPE_REFRESH)
    except AuthError as exc:
        raise _fail(status.HTTP_401_UNAUTHORIZED, "session_expired", str(exc)) from exc

    row = await repository.get_by_id(claims.user_id)
    if row is None or not row.is_active or row.token_version != claims.token_version:
        raise _fail(
            status.HTTP_401_UNAUTHORIZED,
            "session_expired",
            "Your session has ended. Please sign in again.",
        )
    return _issue(row, response=response, request=request)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Sign out and clear refresh cookie",
)
async def logout(
    response: Response,
    request: Request,
) -> dict[str, bool]:
    _delete_refresh_cookie(response, request)
    return {"ok": True}


@router.get("/me", response_model=UserResponse, summary="The signed-in account")
async def me(user: Annotated[UserRow, Depends(get_current_user)]) -> UserResponse:
    return _to_user_response(user)


@router.post(
    "/change-password",
    response_model=AuthResponse,
    summary="Change your own password",
)
async def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    request: Request,
    user: Annotated[UserRow, Depends(get_current_user)],
    repo: Annotated[UserRepository | None, Depends(get_user_repository)] = None,
) -> AuthResponse:
    repository = _require_repo(repo)
    if not verify_password(payload.current_password, user.password_hash):
        raise _fail(
            status.HTTP_401_UNAUTHORIZED,
            "wrong_current_password",
            "Your current password is incorrect.",
        )
    try:
        validate_password(payload.new_password)
    except AuthError as exc:
        raise _fail(status.HTTP_400_BAD_REQUEST, "weak_password", str(exc)) from exc

    await repository.set_password(user.id, hash_password(payload.new_password))
    # Re-read so the new token carries the bumped token_version — otherwise the
    # caller would be signed out by their own password change.
    updated = await repository.get_by_id(user.id)
    if updated is None:  # pragma: no cover — the row was just written
        raise _fail(
            status.HTTP_401_UNAUTHORIZED, "account_not_found", "Account not found."
        )
    return _issue(updated, response=response, request=request)
