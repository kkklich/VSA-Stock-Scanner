"""Bounded, typed screen snapshots; no arbitrary HTML, URLs or executable content."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

Ticker = Annotated[str, StringConstraints(
    strip_whitespace=True, to_upper=True, min_length=1, max_length=20,
    pattern=r"^[A-Za-z0-9.^=_-]+$",
)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Score = Annotated[float, Field(ge=0, le=100)]
Status = Literal["observing", "confirmed", "invalidated", "closed"]


class Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False,
    )


class Candle(Model):
    time: date | datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @model_validator(mode="after")
    def valid_prices(self):
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Invalid candle range")
        return self


class Marker(Model):
    date: date | datetime
    label: str = Field(max_length=160)
    type: Literal["Bullish", "Bearish", "Watch"]


class Overlay(Model):
    method_id: str = Field(max_length=60)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    directional_color: bool = False
    signals: list[Marker] = Field(max_length=10000)


class MethodScore(Model):
    method_id: str = Field(max_length=60)
    score: Score | None
    detail: str | None = Field(default=None, max_length=2000)


def time_key(value: date | datetime) -> float:
    if not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    return value.replace(tzinfo=value.tzinfo or UTC).timestamp()


class Snapshot(Model):
    schema_version: Literal[1] = 1
    name: str = Field(max_length=200)
    currency: str = Field(max_length=12)
    market: str = Field(max_length=20)
    interval: Literal["30m", "1h", "4h", "1d", "1w"]
    # Last completed bar, deliberately not an unfinished live price.
    reference_price: float = Field(gt=0)
    rating: Score | None = None
    combined_score: Score | None = None
    rating_session: date | None = None
    method_scores: list[MethodScore] = Field(default_factory=list, max_length=30)
    history: list[Candle] = Field(min_length=1, max_length=5000)
    overlays: list[Overlay] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def valid_history(self):
        if sum(len(layer.signals) for layer in self.overlays) > 20000:
            raise ValueError("Too many chart markers")
        keys = [time_key(bar.time) for bar in self.history]
        if any(a >= b for a, b in zip(keys, keys[1:], strict=False)):
            raise ValueError("Candles must be unique and chronological")
        if self.reference_price != self.history[-1].close:
            raise ValueError("Reference price must match the last completed candle")
        return self


class CreateEntry(Model):
    id: UUID
    ticker: Ticker
    note: Text = Field(min_length=1)
    confirmation: Text = ""
    invalidation: Text = ""
    snapshot: Snapshot


class ReviewEntry(Model):
    version: int = Field(ge=1)
    status: Status
    review: Text = ""
