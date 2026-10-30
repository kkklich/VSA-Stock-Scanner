"""Named watchlists are always scoped to the authenticated account."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from app.db.models import UserRow
from app.db.user_repository import UserRepository
from app.db.watchlist_repository import WatchlistError
from app.dependencies import get_user_repository
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])
Owner = Annotated[UserRow, Depends(get_current_user)]
Repository = Annotated[UserRepository, Depends(get_user_repository)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Ticker = Annotated[str, StringConstraints(
    strip_whitespace=True, to_upper=True, min_length=1, max_length=20,
    pattern=r"^[A-Za-z0-9.^=_-]+$",
)]


class NamedList(BaseModel):
    name: Name


class Members(BaseModel):
    tickers: list[Ticker] = Field(min_length=1, max_length=500)


async def change(repo, user, operation, **kwargs):
    try:
        return await repo.watchlists.change(user.id, operation, **kwargs)
    except WatchlistError as exc:
        raise HTTPException(exc.status, detail={
            "code": exc.code, "message": exc.code,
        }) from exc


@router.get("")
async def lists(user: Owner, repo: Repository):
    return await change(repo, user, "read")


@router.post("/bootstrap")
async def bootstrap(payload: NamedList, user: Owner, repo: Repository):
    return await change(repo, user, "bootstrap", name=payload.name)


@router.post("", status_code=201)
async def create(payload: NamedList, user: Owner, repo: Repository):
    return await change(repo, user, "create", name=payload.name)


@router.patch("/{list_id}")
async def rename(list_id: str, payload: NamedList, user: Owner, repo: Repository):
    return await change(repo, user, "rename", list_id=list_id, name=payload.name)


@router.delete("/{list_id}")
async def delete(list_id: str, user: Owner, repo: Repository):
    return await change(repo, user, "delete", list_id=list_id)


@router.put("/{list_id}/members")
async def add(list_id: str, payload: Members, user: Owner, repo: Repository):
    return await change(repo, user, "add", list_id=list_id, tickers=payload.tickers)


@router.delete("/{list_id}/members")
async def remove(list_id: str, payload: Members, user: Owner, repo: Repository):
    return await change(repo, user, "remove", list_id=list_id, tickers=payload.tickers)
