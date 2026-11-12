"""A named snapshot of the screener controls, including defaults for older presets."""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.services.insider_screen_service import InsiderActivity

PresetId = Annotated[
    str, StringConstraints(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"),
]
Rating = Annotated[int, Field(ge=0, le=100)]
Amount = Annotated[float, Field(ge=0, allow_inf_nan=False)]
ChangePct = Annotated[float, Field(ge=-100, allow_inf_nan=False)]


class ScreenFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(default="", max_length=64)
    sector: str = Field(default="all", max_length=64)
    minRating: Rating = 0
    maxRating: Rating = 100
    signal: Literal["all", "Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"] = "all"
    maxDaysSinceSignal: int | None = Field(default=None, ge=0, le=999)
    minPrice: Amount | None = None
    maxPrice: Amount | None = None
    minVolume: int | None = Field(default=None, ge=0)
    maxVolume: int | None = Field(default=None, ge=0)
    minPriceChangePct: ChangePct | None = None
    maxPriceChangePct: ChangePct | None = None
    minCombinedScore: Rating | None = None
    maxCombinedScore: Rating | None = None
    range52w: Literal["any", "newHigh", "nearHigh", "newLow", "nearLow"] = "any"
    weeklyConfirms: bool = False
    insiderActivity: InsiderActivity = "all"
    insiderEnd: str = Field(default="", pattern=r"^(?:[0-9]{4}-[0-9]{2}-[0-9]{2})?$")
    insiderDays: int = Field(default=100, ge=1, le=365)
    minInsiderValue: Amount | None = None
    minInsiderTrades: int | None = Field(default=None, ge=1)
    maxInsiderTradeAge: int | None = Field(default=None, ge=0, le=365)
    minInsiderValueLast30Days: Amount | None = None

    @field_validator("insiderEnd")
    @classmethod
    def validate_insider_end(cls, value: str) -> str:
        if value:
            date.fromisoformat(value)
        return value


class FilterPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: PresetId
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    createdAt: AwareDatetime
    filters: ScreenFilters


class AddFilterPresets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presets: list[FilterPreset] = Field(min_length=1, max_length=100)
