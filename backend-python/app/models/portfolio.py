"""Validated account portfolio commands; monetary values remain decimal strings."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.markets import normalize_ticker

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Amount = Annotated[
    Decimal,
    Field(gt=0, le=Decimal("1000000000000"), max_digits=24, decimal_places=8, allow_inf_nan=False),
]
CostMethod = Literal["fifo", "moving_average"]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreatePortfolio(Command):
    id: UUID
    name: Name
    broker: Name
    cost_method: CostMethod = Field(default="fifo", alias="costMethod")


class UpdatePortfolio(Command):
    version: int = Field(ge=1)
    name: Name
    broker: Name
    cost_method: CostMethod = Field(alias="costMethod")


class AddTransaction(Command):
    id: UUID
    version: int = Field(ge=1)
    ticker: str
    date: date
    side: Literal["buy", "sell"]
    quantity: Amount
    price: Amount
    fees: Decimal = Field(
        default=Decimal(0),
        ge=0,
        le=Decimal("1000000000000"),
        max_digits=24,
        decimal_places=8,
        allow_inf_nan=False,
    )
    currency: Literal["PLN", "USD", "EUR", "GBP", "GBp"]

    @field_validator("ticker")
    @classmethod
    def ticker_valid(cls, value):
        ticker = normalize_ticker(value)
        if ticker is None:
            raise ValueError("Invalid ticker")
        return ticker

    @field_validator("date")
    @classmethod
    def date_valid(cls, value):
        # The account UI records completed transactions in Warsaw calendar time.
        from datetime import datetime
        from zoneinfo import ZoneInfo

        if value > datetime.now(ZoneInfo("Europe/Warsaw")).date():
            raise ValueError("Future transactions are not supported")
        return value
