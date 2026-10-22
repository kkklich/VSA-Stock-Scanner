"""Observation cutoffs use exchange dates and exact acquisition timestamps."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.markets import market_of
from app.models import FinancialMetrics, GpwCompany, StooqDailyQuote
from app.services.long_term_service import build_long_term_ranking


class Observations:
    def __init__(self, companies, now, observed_at):
        exchange = market_of(companies[0].ticker)
        day = exchange.latest_final_session(now)
        days = []
        while len(days) < 253:
            if day.weekday() < 5:
                days.append(day)
            day -= timedelta(days=1)
        self.bars = [
            StooqDailyQuote(
                date=day,
                open=Decimal(100),
                high=Decimal(100),
                low=Decimal(100),
                close=Decimal(100),
                volume=100_000,
            )
            for day in reversed(days)
        ]
        self.observations = {
            c.ticker: {
                "metrics": FinancialMetrics(
                    pe_ratio=10,
                    return_on_equity=0.1,
                    return_on_assets=0.05,
                    total_revenue=100_000_000,
                    net_income=10_000_000,
                    market_cap=500_000_000,
                ),
                "observed_at": observed_at,
            }
            for c in companies
        }

    async def get_quotes(self, _ticker, from_date, to_date):
        return [bar for bar in self.bars if from_date <= bar.date <= to_date]

    async def get_long_term_inputs(self, _tickers):
        return self.observations


def _companies(market):
    suffix, currency = (".us", "USD") if market == "us" else ("", "PLN")
    return [
        GpwCompany(ticker=f"clock{i}{suffix}", name=f"Clock {i}", market=market, currency=currency)
        for i in range(5)
    ]


@pytest.mark.parametrize(
    "market,now,observed_at",
    [
        (
            "gpw",
            datetime(2026, 10, 22, 22, 30, tzinfo=UTC),
            datetime(2026, 10, 22, 22, 25, tzinfo=UTC),
        ),  # In Warsaw both timestamps are already Oct 23; the prices describe Oct 22.
        (
            "us",
            datetime(2026, 10, 23, 1, tzinfo=UTC),
            datetime(2026, 9, 8, 1, tzinfo=UTC),
        ),  # In New York these are Oct 22 and Sep 7: exactly the admissible 45-day age.
    ],
)
async def test_midnight_never_turns_known_fundamentals_into_future_or_stale_data(
    market,
    now,
    observed_at,
):
    companies = _companies(market)
    repo = Observations(companies, now, observed_at)
    result = await build_long_term_ranking(companies, market, repo, now=now)
    assert result.scored_count == 5
    assert all(row.score == 50 and not row.missing for row in result.items)
    assert all(row.as_of == market_of(row.ticker).latest_final_session(now) for row in result.items)


async def test_later_observation_on_same_local_day_is_not_available_yet():
    now = datetime(2026, 10, 22, 22, 30, tzinfo=UTC)
    companies = _companies("gpw")
    repo = Observations(companies, now, now + timedelta(seconds=1))
    result = await build_long_term_ranking(companies, "gpw", repo, now=now)
    assert result.scored_count == 0
    assert all("fundamentals_missing" in row.missing for row in result.items)
    assert all(row.fundamentals_observed_at is None for row in result.items)
