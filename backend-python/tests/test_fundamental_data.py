"""Annual ratios must use matching dates and economically valid denominators."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest
import yfinance

from app.services.fundamental_data import extract_fundamental_details
from app.services.yahoo_finance_client import YahooFinanceClient


def frames():
    dates = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
    income = pd.DataFrame(
        {
            "Total Revenue": [1331, 1210, 1100, 1000],
            "Diluted EPS": [1.331, 1.21, 1.1, 1],
            "Operating Income": [133.1, 121, 110, 100],
            "EBIT": [200, 180, 160, 140],
            "Interest Expense": [20, 18, 16, 14],
            "Pretax Income": [180, 162, 144, 126],
            "Tax Provision": [36, 32.4, 28.8, 25.2],
        },
        index=dates,
    ).T
    balance = pd.DataFrame(
        {"Total Debt": [100, 100, 100, 100], "Stockholders Equity": [900, 700, 600, 500]},
        index=dates,
    ).T
    return income, balance


def test_cagr_roic_interest_and_margin_stability_use_real_financial_periods():
    details = extract_fundamental_details(
        {"totalDebt": 100, "totalCash": 50, "ebitda": 200}, *frames(), today=date(2026, 10, 30)
    )
    assert details.net_debt_to_ebitda == 0.25
    assert details.return_on_invested_capital == pytest.approx(160 / 900)
    assert details.interest_coverage == 10
    assert details.revenue_cagr_3y == pytest.approx(0.1, abs=0.0001)
    assert details.eps_cagr_3y == pytest.approx(0.1, abs=0.0001)
    assert details.operating_margin_volatility == pytest.approx(0)
    assert details.annual_period_end == date(2025, 12, 31)
    payload = details.model_dump(mode="json", by_alias=True)
    assert payload["revenueCagr3y"] == details.revenue_cagr_3y
    assert payload["epsCagr3y"] == details.eps_cagr_3y


def test_empty_statements_do_not_require_another_data_source():
    details = extract_fundamental_details(
        {"operatingMargins": 0.1, "priceToBook": 2}, today=date(2026, 10, 30)
    )
    assert details.operating_margin == 0.1 and details.price_to_book == 2
    assert details.return_on_invested_capital is None and details.revenue_cagr_3y is None


@pytest.mark.parametrize("ebitda", [0, -1, None, float("nan"), float("inf")])
def test_invalid_ebitda_never_creates_a_leverage_ratio(ebitda):
    details = extract_fundamental_details(
        {"totalDebt": 100, "totalCash": 10, "ebitda": ebitda}, today=date(2026, 10, 30)
    )
    assert details.net_debt_to_ebitda is None


def test_negative_equity_tax_and_cagr_bases_are_unavailable():
    income, balance = frames()
    income.loc["Diluted EPS", pd.Timestamp("2022-12-31")] = -1
    balance.loc["Stockholders Equity", pd.Timestamp("2024-12-31")] = -100
    income.loc["Tax Provision", pd.Timestamp("2025-12-31")] = -36
    details = extract_fundamental_details({}, income, balance, today=date(2026, 10, 30))
    assert details.eps_cagr_3y is None and details.return_on_invested_capital is None


def test_old_annual_statements_remain_unavailable_after_a_fresh_download():
    details = extract_fundamental_details({}, *frames(), today=date(2028, 10, 30))
    assert details.annual_period_end is None
    assert details.return_on_invested_capital is None
    assert details.revenue_cagr_3y is None


def test_yahoo_adapter_includes_the_observed_annual_and_balance_sheet_inputs(monkeypatch):
    income, balance = frames()
    fake = SimpleNamespace(
        info={
            "marketCap": 200_000_000,
            "totalDebt": 100,
            "totalCash": 50,
            "ebitda": 200,
            "operatingMargins": 0.15,
            "financialCurrency": "PLN",
        },
        income_stmt=income,
        balance_sheet=balance,
    )
    monkeypatch.setattr(yfinance, "Ticker", lambda _: fake)
    monkeypatch.setattr(
        "app.services.yahoo_finance_client._utcnow", lambda: datetime(2026, 10, 30, tzinfo=UTC)
    )
    metrics = YahooFinanceClient()._fetch_fundamentals_sync("TEST.WA")
    assert metrics.market_cap == 200_000_000
    assert metrics.fundamental_details.return_on_invested_capital == pytest.approx(160 / 900)
    assert metrics.fundamental_details.net_debt_to_ebitda == 0.25


def test_missing_annual_frames_do_not_discard_available_ratios(monkeypatch):
    fake = SimpleNamespace(info={"operatingMargins": 0.15, "trailingPE": 12})
    monkeypatch.setattr(yfinance, "Ticker", lambda _: fake)
    metrics = YahooFinanceClient()._fetch_fundamentals_sync("TEST.WA")
    assert metrics.pe_ratio == 12
    assert metrics.fundamental_details.operating_margin == 0.15
    assert metrics.fundamental_details.return_on_invested_capital is None


def test_quarterly_eps_remains_fractional_for_yoy_growth(monkeypatch):
    fake = SimpleNamespace(
        quarterly_income_stmt=pd.DataFrame(
            {
                pd.Timestamp("2026-06-30"): {"Total Revenue": 1000, "Diluted EPS": 1.25},
                pd.Timestamp("2025-06-30"): {"Total Revenue": 900, "Diluted EPS": 0.75},
            }
        )
    )
    monkeypatch.setattr(yfinance, "Ticker", lambda _: fake)
    reports = YahooFinanceClient()._fetch_quarterly_sync("TEST.WA")
    assert [r.eps for r in reports] == [1.25, 0.75]


def test_missing_diluted_eps_falls_back_to_basic_eps(monkeypatch):
    fake = SimpleNamespace(
        quarterly_income_stmt=pd.DataFrame(
            {
                pd.Timestamp("2026-06-30"): {"Diluted EPS": float("nan"), "Basic EPS": 0.75},
            }
        )
    )
    monkeypatch.setattr(yfinance, "Ticker", lambda _: fake)
    assert YahooFinanceClient()._fetch_quarterly_sync("TEST.WA")[0].eps == 0.75
