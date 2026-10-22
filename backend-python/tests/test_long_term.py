"""Economic direction, missing-data safety and temporal boundaries for QVM."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.analysis.long_term import compute_long_term
from app.models.long_term import MODEL_VERSION, LongTermRankingResponse
from app.models.stocks import FinancialMetrics, GpwCompany, StooqDailyQuote

AS_OF = date(2026, 10, 22)
OBSERVED = datetime(2026, 10, 22, 12, tzinfo=UTC)


def _bars(strength: int = 1, *, price: int = 100, volume: int = 100_000):
    days = []
    day = AS_OF
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return [
        StooqDailyQuote(
            date=day,
            open=Decimal(str(price * (1 + i * strength / 1000))),
            high=Decimal(str(price * (1 + i * strength / 1000))),
            low=Decimal(str(price * (1 + i * strength / 1000))),
            close=Decimal(str(price * (1 + i * strength / 1000))),
            volume=volume,
        )
        for i, day in enumerate(reversed(days))
    ]


def _universe(count: int = 6, *, market: str = "gpw", currency: str = "PLN"):
    companies, quotes, fundamentals = [], {}, {}
    for i in range(count):
        ticker = f"s{i}" if market == "gpw" else f"s{i}.l"
        companies.append(
            GpwCompany(
                ticker=ticker,
                name=f"Stock {i}",
                sector="Industry",
                market=market,
                currency=currency,
                market_cap=200_000_000,
            )
        )
        quotes[ticker] = _bars(i + 1)
        fundamentals[ticker] = {
            "metrics": FinancialMetrics(
                return_on_equity=(i + 1) / 10,
                return_on_assets=(i + 1) / 100,
                pe_ratio=60 / (i + 1),
                total_revenue=100_000_000,
                net_income=1_000_000 * (i + 1),
                market_cap=200_000_000,
            ),
            "observed_at": OBSERVED,
        }
    return companies, quotes, fundamentals


def _compute(universe):
    return {row.ticker: row for row in compute_long_term(*universe, as_of=AS_OF)}


def _metrics(universe, ticker: str, **changes):
    fundamentals = universe[2]
    fundamentals[ticker]["metrics"] = fundamentals[ticker]["metrics"].model_copy(update=changes)


def test_direction_equal_weights_and_json_contract():
    universe = _universe()
    rows = compute_long_term(*universe, as_of=AS_OF)
    assert [row.ticker for row in rows] == [f"s{i}" for i in reversed(range(6))]
    assert rows[0].score == rows[0].quality_score == rows[0].value_score == 100
    assert rows[-1].score == rows[-1].momentum_score == 0
    assert rows[2].score == pytest.approx(
        (rows[2].quality_score + rows[2].value_score + rows[2].momentum_score) / 3
    )
    assert all(row.coverage == 100 and row.eligible and not row.missing for row in rows)
    payload = LongTermRankingResponse(
        market="gpw",
        as_of=AS_OF,
        db_enabled=True,
        items=rows,
        total_count=6,
        scored_count=6,
    ).model_dump(mode="json", by_alias=True)
    assert payload["modelVersion"] == MODEL_VERSION == "qvm-v1"
    assert payload["items"][0]["asOf"] == "2026-10-22"
    assert payload["items"][0]["qualityScore"] == 100
    assert rows[0].inputs["roe"] == 0.6
    assert rows[0].inputs["netMargin"] == 0.06
    assert rows[0].inputs["earningsYield"] == 0.1


def test_ties_have_midpoint_rank_and_order_is_stable():
    universe = _universe()
    for ticker in universe[1]:
        universe[1][ticker] = universe[1]["s0"]
        universe[2][ticker] = universe[2]["s0"]
    rows = compute_long_term(*universe, as_of=AS_OF)
    assert all(row.score == 50 for row in rows)
    assert [row.ticker for row in rows] == [f"s{i}" for i in range(6)]
    # Two tied lowest values share ranks 0 and 1, i.e. 10 on a six-item scale.
    universe = _universe()
    universe[2]["s1"] = universe[2]["s0"]
    rows = _compute(universe)
    assert rows["s0"].quality_score == rows["s1"].quality_score == 10


@pytest.mark.parametrize("pe", [None, 0, -10, float("nan"), float("inf")])
def test_invalid_valuation_stays_missing_even_with_forward_pe(pe):
    universe = _universe()
    _metrics(universe, "s0", pe_ratio=pe, forward_pe=5)
    row = _compute(universe)["s0"]
    assert row.value_score is None and row.score is None
    assert "value_missing" in row.missing
    assert row.coverage == 83.33


def test_known_loss_scores_zero_and_positive_roe_from_negative_equity_is_ignored():
    universe = _universe()
    _metrics(universe, "s0", net_income=-1_000_000, pe_ratio=5, return_on_equity=9)
    row = _compute(universe)["s0"]
    assert row.inputs["roe"] is None
    assert row.inputs["earningsYield"] == row.value_score == 0
    assert row.quality_score is not None  # ROA and margin still suffice.
    assert row.score is not None
    # Losses are never called average valuation merely because all peers lose.
    for company in universe[0]:
        _metrics(universe, company.ticker, net_income=-1_000_000, pe_ratio=None)
    assert all(row.value_score == 0 for row in _compute(universe).values())


def test_nonpositive_eps_is_known_unprofitable_and_one_quality_input_is_insufficient():
    universe = _universe()
    _metrics(universe, "s0", net_income=None, eps=0, pe_ratio=None, return_on_assets=None)
    row = _compute(universe)["s0"]
    assert row.value_score == 0
    assert row.quality_score is None and row.score is None
    assert "quality_missing" in row.missing


@pytest.mark.parametrize("eps", [-1, 0])
def test_nonpositive_eps_without_net_income_cannot_create_quality_from_negative_equity(eps):
    universe = _universe()
    _metrics(universe, "s0", net_income=None, eps=eps, pe_ratio=None, return_on_equity=9)
    row = _compute(universe)["s0"]
    assert row.inputs["roe"] is None
    assert row.value_score == 0
    # With income absent, net margin is also unavailable. Only ROA remains:
    # the apparently excellent ROE must not manufacture a second quality input.
    assert row.quality_score is None and row.score is None and not row.eligible
    assert "quality_missing" in row.missing


def test_third_quality_input_is_optional():
    universe = _universe()
    _metrics(universe, "s0", return_on_assets=None)
    row = _compute(universe)["s0"]
    assert row.quality_score == 0 and row.score is not None
    assert row.coverage == 83.33


def test_sector_fallback_and_market_isolation():
    universe = _universe()
    universe[0][:] = [
        company.model_copy(update={"sector": "Small" if i < 4 else "Other"})
        for i, company in enumerate(universe[0])
    ]
    assert all(row.comparison_group == "market" for row in _compute(universe).values())
    universe[0][:] = [
        company.model_copy(update={"sector": "Large" if i < 5 else "Other"})
        for i, company in enumerate(universe[0])
    ]
    rows = _compute(universe)
    assert rows["s4"].quality_score == 100 and rows["s4"].comparison_group == "sector"
    assert rows["s5"].comparison_group == "market"
    other = _universe(4, market="uk", currency="GBp")
    combined = (universe[0] + other[0], universe[1] | other[1], universe[2] | other[2])
    rows = _compute(combined)
    assert all(rows[company.ticker].score is None for company in other[0])
    assert rows["s4"].score == _compute(universe)["s4"].score


def test_sparse_financial_metric_uses_market_fallback():
    universe = _universe(10)
    universe[0][:] = [
        company.model_copy(update={"sector": "A" if i < 5 else "B"})
        for i, company in enumerate(universe[0])
    ]
    _metrics(universe, "s0", net_income=None)
    row = _compute(universe)["s1"]
    assert row.comparison_group == "mixed" and row.peer_count == 5
    assert row.score is not None


def test_fewer_than_five_observations_does_not_invent_percentiles():
    rows = _compute(_universe(4))
    assert all(row.score is None and row.missing == ["peers_missing"] for row in rows.values())
    assert all(row.coverage == 100 for row in rows.values())
    assert all(row.peer_count == 0 for row in rows.values())


@pytest.mark.parametrize("case", ["short", "compressed", "gappy", "duplicates"])
def test_momentum_requires_a_complete_plausible_year(case):
    universe = _universe()
    bars = universe[1]["s0"]
    if case == "short":
        bars = bars[1:]
    elif case == "compressed":
        bars = [
            bar.model_copy(update={"date": AS_OF - timedelta(days=252 - i)})
            for i, bar in enumerate(bars)
        ]
    elif case == "gappy":
        bars = [
            bar.model_copy(update={"date": AS_OF - timedelta(days=3 * (252 - i))})
            for i, bar in enumerate(bars)
        ]
    else:
        bars = bars[1:] + [bars[-1]]
    universe[1]["s0"] = bars
    row = _compute(universe)["s0"]
    assert row.inputs["momentum12_1"] is None and row.inputs["momentum6_1"] is None
    assert row.momentum_score is None and row.score is None
    assert "momentum_missing" in row.missing


def test_last_month_and_future_bars_cannot_change_momentum():
    universe = _universe()
    before = _compute(universe)["s0"]
    bars = universe[1]["s0"]
    universe[1]["s0"] = bars[:-21] + [
        bar.model_copy(update={"close": bar.close * 100}) for bar in bars[-21:]
    ]
    universe[1]["s0"] += [
        bars[-1].model_copy(
            update={
                "date": AS_OF + timedelta(days=1),
                "close": Decimal("1000000"),
            }
        )
    ]
    after = _compute(universe)["s0"]
    assert after.inputs == before.inputs
    assert after.momentum_score == before.momentum_score
    assert after.as_of == AS_OF


@pytest.mark.parametrize("kind", ["missing", "future", "naive", "stale"])
def test_financial_observations_must_be_known_and_fresh(kind):
    universe = _universe()
    if kind == "missing":
        del universe[2]["s0"]
    else:
        universe[2]["s0"]["observed_at"] = {
            "future": OBSERVED + timedelta(days=1),
            "naive": OBSERVED.replace(tzinfo=None),
            "stale": OBSERVED - timedelta(days=46),
        }[kind]
    rows = _compute(universe)
    row = rows["s0"]
    assert row.score is None and row.quality_score is None and row.value_score is None
    assert row.inputs["roe"] is None and row.inputs["earningsYield"] is None
    assert ("fundamentals_stale" if kind == "stale" else "fundamentals_missing") in row.missing
    assert not {"quality_missing", "value_missing", "momentum_missing"}.intersection(row.missing)
    assert rows["s1"].peer_count == 5 and rows["s1"].score == 0


@pytest.mark.parametrize("reason", ["price_stale", "liquidity", "market_cap"])
def test_excluded_rows_are_retained_but_never_used_as_reference_peers(reason):
    universe = _universe()
    if reason == "price_stale":
        universe[1]["s0"] = [
            bar.model_copy(update={"date": bar.date - timedelta(days=14)})
            for bar in universe[1]["s0"]
        ]
    elif reason == "liquidity":
        universe[1]["s0"] = [bar.model_copy(update={"volume": 1}) for bar in universe[1]["s0"]]
    else:
        _metrics(universe, "s0", market_cap=10_000_000)
    rows = _compute(universe)
    assert len(rows) == 6 and rows["s0"].score is None and reason in rows["s0"].missing
    assert rows["s0"].coverage == 100
    assert rows["s0"].missing == [reason]
    assert rows["s1"].score == 0 and rows["s1"].peer_count == 5
    if reason == "price_stale":
        assert rows["s0"].as_of == AS_OF - timedelta(days=14)


def test_exclusion_does_not_hide_a_genuinely_missing_input():
    universe = _universe()
    _metrics(universe, "s0", market_cap=10_000_000, pe_ratio=None)
    row = _compute(universe)["s0"]
    assert row.score is None and row.coverage == 83.33
    assert row.missing == ["market_cap", "value_missing"]


def test_no_prices_has_no_fabricated_session_date():
    universe = _universe()
    universe[1]["s0"] = []
    row = _compute(universe)["s0"]
    assert row.as_of is None and row.score is None
    assert "price_stale" in row.missing


@pytest.mark.parametrize(
    "currency,price,volume,cap",
    [
        ("GBp", 10_000, 1000, 25_000_000),  # £25M cap, pence quotes: both clear PLN floors.
        ("USD", 100, 300, 30_000_000),  # A dollar-denominated London listing.
    ],
)
def test_london_floors_respect_quote_and_major_units(currency, price, volume, cap):
    universe = _universe(market="uk", currency=currency)
    for company in universe[0]:
        universe[1][company.ticker] = _bars(price=price, volume=volume)
        _metrics(universe, company.ticker, market_cap=cap, financial_currency="EUR")
    rows = _compute(universe)
    assert all(row.score is not None for row in rows.values())
    assert all(
        "market_cap" not in row.missing and "liquidity" not in row.missing for row in rows.values()
    )


def test_unknown_currency_fails_closed_for_one_row_only():
    universe = _universe()
    universe[0][0] = universe[0][0].model_copy(update={"currency": "XYZ"})
    rows = _compute(universe)
    assert rows["s0"].score is None and "liquidity" in rows["s0"].missing
    assert rows["s1"].score is not None
