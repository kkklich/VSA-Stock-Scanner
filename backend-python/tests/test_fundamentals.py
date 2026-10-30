"""Economic direction, comparability and missing-evidence safety of fundamentals."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.analysis.fundamentals import assess_fundamentals, financial_profile
from app.analysis.long_term import compute_long_term
from app.models.stocks import FinancialMetrics, FundamentalDetails, GpwCompany, StooqDailyQuote

TODAY = date(2026, 10, 30)
NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)
PERIODS = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]


def universe(count=6, *, profile="corporate"):
    companies, observations = [], {}
    for i in range(count):
        strength = i + 1
        ticker = f"f{i}"
        companies.append(
            GpwCompany(
                ticker=ticker,
                name=f"Company {i}",
                market="gpw",
                currency="PLN",
                sector="Industrials" if profile == "corporate" else "Financial Services",
                industry={
                    "corporate": "Machinery",
                    "bank": "Banks—Diversified",
                    "insurance": "Insurance—Life",
                    "financial": "Asset Management",
                }[profile],
            )
        )
        reports = [
            dict(periodEnd=p, totalRevenue=1000, netIncome=100, eps=1 + strength / 10)
            for p in PERIODS
        ]
        reports[-1].update(totalRevenue=1000 / (1 + strength / 10), eps=1)
        details = FundamentalDetails(
            operating_margin=strength / 10,
            return_on_invested_capital=strength / 10,
            revenue_cagr_3y=strength / 10,
            eps_cagr_3y=strength / 10,
            operating_margin_volatility=0.1 / strength,
            net_debt_to_ebitda=6 - strength,
            interest_coverage=strength,
            enterprise_to_ebitda=60 / strength,
            price_to_book=6 / strength,
            book_value=10,
            ebitda=1000,
            latest_period_end="2026-06-30",
            annual_period_end="2025-12-31",
        )
        observations[ticker] = {
            "metrics": FinancialMetrics(
                return_on_equity=strength / 10,
                return_on_assets=strength / 100,
                total_revenue=4000,
                net_income=100 * strength,
                pe_ratio=60 / strength,
                market_cap=1_000_000,
                financial_currency="PLN",
                fundamental_details=details,
            ),
            "observed_at": NOW,
            "statements": {
                "quarterly": {
                    "observed_at": NOW,
                    "payload": {"reports": reports, "financialCurrency": "PLN"},
                },
                "cashflow": {
                    "observed_at": NOW,
                    "payload": {
                        "periods": [
                            dict(
                                periodEnd=p,
                                periodType="quarterly",
                                operatingCashFlow=100 * strength,
                                freeCashFlow=80 * strength,
                                capex=20 * strength,
                                currency="PLN",
                            )
                            for p in PERIODS[:4]
                        ]
                    },
                },
            },
        }
    return companies, observations


def compute(data):
    return assess_fundamentals(*data, as_of=TODAY, exclusions={})


def test_full_fundamental_assessment_does_not_require_price_momentum_history():
    companies, observations = universe()
    for obs in observations.values():
        obs["metrics"] = obs["metrics"].model_copy(update={"market_cap": 200_000_000})
    bars = [
        StooqDailyQuote(
            date=TODAY - timedelta(days=i),
            open=Decimal(100),
            high=Decimal(101),
            low=Decimal(99),
            close=Decimal(100),
            volume=100_000,
        )
        for i in reversed(range(25))
    ]
    result = compute_long_term(
        companies, {c.ticker: bars for c in companies}, observations, as_of=TODAY
    )
    assert all(item.score is None and item.momentum_score is None for item in result)
    assert all(item.fundamental_analysis.score is not None for item in result)


def change(data, ticker="f0", **details):
    obs = data[1][ticker]
    metric = obs["metrics"]
    obs["metrics"] = metric.model_copy(
        update={
            "fundamental_details": metric.fundamental_details.model_copy(update=details),
        }
    )


def test_five_equal_pillars_reward_growth_quality_cash_and_lower_debt():
    rows = compute(universe())
    assert rows["f5"].score == 100
    assert rows["f0"].score == 0
    assert list(rows["f0"].pillars) == ["profitability", "growth", "cashflow", "debt", "valuation"]
    assert rows["f3"].score == pytest.approx(sum(rows["f3"].pillars.values()) / 5)
    assert rows["f3"].coverage == 100
    assert rows["f3"].comparison_group == "sector"
    assert rows["f3"].peer_count == 6
    assert rows["f3"].model_dump(mode="json", by_alias=True)["modelVersion"] == "fundamentals-v1"


@pytest.mark.parametrize("profile", ["bank", "insurance", "financial"])
def test_financial_profiles_do_not_use_industrial_leverage_or_cash_flow(profile):
    rows = compute(universe(profile=profile))
    row = rows["f5"]
    assert row.profile == profile
    assert set(row.pillars) == {"profitability", "growth", "valuation"}
    assert row.not_applicable == ["cashflow", "debt"]
    assert "netDebtToEbitda" not in row.inputs
    assert "bookYield" in row.inputs and row.score == 100
    assert "limited_financial_profile" in row.warnings


def test_missing_data_never_becomes_a_neutral_or_bullish_score():
    data = universe()
    data[1]["f0"]["statements"] = {}
    change(data, revenue_cagr_3y=None, eps_cagr_3y=None)
    row = compute(data)["f0"]
    assert row.score is None
    assert row.pillars["cashflow"] is None and row.pillars["growth"] is None
    assert row.coverage < 100
    assert "growth_missing" in row.missing and "cashflow_missing" in row.missing
    assert row.pillars["profitability"] is not None


def test_four_peers_cannot_invent_percentiles():
    rows = compute(universe(4))
    assert all(row.score is None and row.coverage == 100 for row in rows.values())
    assert all(row.peer_count == 0 for row in rows.values())


def test_companies_never_compare_to_other_markets_or_other_financial_profiles():
    data = universe(4)
    others, evidence = universe(6, profile="bank")
    for company in others:
        ticker = f"b{company.ticker}"
        data[0].append(company.model_copy(update={"ticker": ticker}))
        data[1][ticker] = evidence[company.ticker]
    assert compute(data)["f0"].score is None
    data[0][4:] = [c.model_copy(update={"market": "us"}) for c in data[0][4:]]
    assert compute(data)["f0"].score is None


@pytest.mark.parametrize("shift", [-46, 1])
def test_old_or_future_acquisitions_are_not_evidence(shift):
    data = universe()
    data[1]["f0"]["observed_at"] = NOW + timedelta(days=shift)
    row = compute(data)["f0"]
    assert row.score is None and not row.metric_scores
    assert all(value is None for value in row.inputs.values())


@pytest.mark.parametrize("period", [date(2023, 1, 1), date(2026, 12, 31)])
def test_fresh_download_cannot_make_a_stale_or_future_report_current(period):
    data = universe()
    change(data, latest_period_end=period)
    row = compute(data)["f0"]
    assert row.score is None and "report_stale" in row.missing


def test_stale_or_future_statements_cannot_supply_cashflow():
    data = universe()
    data[1]["f0"]["statements"]["cashflow"]["observed_at"] = NOW + timedelta(days=1)
    row = compute(data)["f0"]
    assert row.inputs["fcfMargin"] is None and row.pillars["cashflow"] is None


@pytest.mark.parametrize("case", ["currency", "period", "gap", "duplicate"])
def test_cash_quality_requires_matching_contiguous_periods_and_currency(case):
    data = universe()
    obs = data[1]["f0"]
    periods = obs["statements"]["cashflow"]["payload"]["periods"]
    if case == "currency":
        periods[0]["currency"] = "USD"
    elif case == "period":
        periods[0]["periodEnd"] = "2026-06-29"
    elif case == "gap":
        periods[1]["periodEnd"] = "2024-03-31"
    else:
        periods[1]["periodEnd"] = periods[0]["periodEnd"]
    row = compute(data)["f0"]
    assert row.inputs["fcfMargin"] is None
    assert row.inputs["cashConversion"] is None
    assert row.score is None


def test_currency_mismatch_only_withholds_market_cap_based_valuation():
    data = universe()
    data[0][0] = data[0][0].model_copy(update={"currency": "USD"})
    row = compute(data)["f0"]
    assert row.inputs["fcfYield"] is None
    assert row.inputs["fcfMargin"] is not None
    assert "valuation_currency_mismatch" in row.warnings
    assert row.pillars["valuation"] is not None  # P/E and EV/EBITDA remain usable.


def test_negative_equity_and_losses_do_not_manufacture_profitability_or_value():
    data = universe(profile="bank")
    metrics = data[1]["f0"]["metrics"]
    data[1]["f0"]["metrics"] = metrics.model_copy(update={"net_income": -100, "pe_ratio": 1})
    change(data, book_value=-5, price_to_book=0.1)
    row = compute(data)["f0"]
    assert row.inputs["roe"] is None and row.inputs["bookYield"] is None
    assert row.metric_scores["earningsYield"] == 0
    assert row.score is None and "loss_making" in row.warnings


def test_negative_ebitda_cannot_turn_debt_into_a_positive_signal():
    data = universe()
    change(data, ebitda=-100, net_debt_to_ebitda=-100, enterprise_to_ebitda=1)
    row = compute(data)["f0"]
    assert row.inputs["netDebtToEbitda"] is None
    assert row.metric_scores["ebitdaYield"] == 0
    assert "nonpositive_ebitda" in row.warnings


def test_fcf_is_derived_only_from_known_ocf_and_capex():
    data = universe()
    periods = data[1]["f0"]["statements"]["cashflow"]["payload"]["periods"]
    for period in periods:
        period["freeCashFlow"] = None
    assert compute(data)["f0"].inputs["fcfMargin"] == pytest.approx(0.08)
    periods[0]["capex"] = None
    assert compute(data)["f0"].inputs["fcfMargin"] is None


def test_negative_growth_is_never_reported_as_top_growth():
    data = universe()
    for obs in data[1].values():
        obs["statements"] = {}
        details = obs["metrics"].fundamental_details.model_copy(
            update={
                "revenue_cagr_3y": -0.1,
                "eps_cagr_3y": -0.1,
            }
        )
        obs["metrics"] = obs["metrics"].model_copy(update={"fundamental_details": details})
    assert all(row.pillars["growth"] <= 50 for row in compute(data).values())


def test_existing_eligibility_exclusions_are_respected():
    companies, observations = universe()
    rows = assess_fundamentals(
        companies, observations, as_of=TODAY, exclusions={"f0": ["liquidity"]}
    )
    assert rows["f0"].score is None and "liquidity" in rows["f0"].missing
    assert rows["f1"].peer_count == 5


@pytest.mark.parametrize(
    ("name", "sector", "industry", "profile"),
    [
        ("mBank", None, None, "bank"),
        ("Powszechny Zakład Ubezpieczeń", None, None, "insurance"),
        ("Example", "Financial Services", "Insurance—Life", "insurance"),
        ("Example", "Finanse", None, "financial"),
        ("Example", "Technology", "Software", "corporate"),
    ],
)
def test_profiles_follow_industry_before_broad_sector(name, sector, industry, profile):
    assert (
        financial_profile(GpwCompany(ticker="x", name=name, sector=sector, industry=industry))
        == profile
    )
