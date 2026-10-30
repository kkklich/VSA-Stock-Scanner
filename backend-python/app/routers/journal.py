"""Account-only journal: neither reads nor mutations accept an owner from a client."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.db.journal_repository import JournalError
from app.db.models import UserRow
from app.db.user_repository import UserRepository
from app.dependencies import get_user_repository
from app.models.journal import CreateEntry, ReviewEntry, Ticker
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/journal", tags=["journal"])
Owner = Annotated[UserRow, Depends(get_current_user)]
Repository = Annotated[UserRepository, Depends(get_user_repository)]


async def execute(response: Response, operation):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await operation
    except JournalError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.code}) from exc


@router.get("")
async def entries(
    user: Owner, repo: Repository, response: Response,
    ticker: Ticker | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return await execute(response, repo.journal.list(user.id, ticker, offset, limit))


@router.post("", status_code=201)
async def create(payload: CreateEntry, user: Owner, repo: Repository, response: Response):
    return await execute(response, repo.journal.create(user.id, payload))


@router.get("/{entry_id}")
async def detail(entry_id: UUID, user: Owner, repo: Repository, response: Response):
    return await execute(response, repo.journal.get(user.id, str(entry_id)))


@router.patch("/{entry_id}")
async def review(
    entry_id: UUID, payload: ReviewEntry, user: Owner, repo: Repository, response: Response,
):
    return await execute(response, repo.journal.review(user.id, str(entry_id), payload))


@router.delete("/{entry_id}")
async def delete(
    entry_id: UUID, user: Owner, repo: Repository, response: Response,
    version: Annotated[int, Query(ge=1)],
):
    return await execute(response, repo.journal.delete(user.id, str(entry_id), version))
