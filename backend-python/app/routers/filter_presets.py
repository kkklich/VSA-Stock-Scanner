"""Account-scoped screener presets shared by the owner's signed-in devices."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.db.filter_preset_repository import FilterPresetError
from app.db.models import UserRow
from app.db.user_repository import UserRepository
from app.dependencies import get_user_repository
from app.models.filter_presets import AddFilterPresets, FilterPreset, PresetId
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/filter-presets", tags=["filter-presets"])


async def preset_owner(
    user: Annotated[UserRow, Depends(get_current_user)],
    x_expected_user_id: Annotated[int | None, Header()] = None,
) -> UserRow:
    # Another tab can replace the browser's bearer token before this tab re-renders.
    if x_expected_user_id is not None and x_expected_user_id != user.id:
        raise HTTPException(409, detail={"code": "account_changed", "message": "account_changed"})
    return user


Owner = Annotated[UserRow, Depends(preset_owner)]
Repository = Annotated[UserRepository, Depends(get_user_repository)]


async def execute(response, operation):
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await operation
    except FilterPresetError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.code}) from exc


@router.get("", response_model=list[FilterPreset])
async def list_presets(user: Owner, repo: Repository, response: Response):
    return await execute(response, repo.filter_presets.list(user.id))


@router.post("", response_model=list[FilterPreset])
async def add_presets(payload: AddFilterPresets, user: Owner, repo: Repository, response: Response):
    presets = [preset.model_dump() for preset in payload.presets]
    return await execute(response, repo.filter_presets.add(user.id, presets))


@router.delete("/{preset_id}", response_model=list[FilterPreset])
async def delete_preset(preset_id: PresetId, user: Owner, repo: Repository, response: Response):
    return await execute(response, repo.filter_presets.delete(user.id, preset_id))
