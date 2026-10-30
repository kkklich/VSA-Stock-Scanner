"""Extract financial evidence from Yahoo frames without inventing missing inputs."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from statistics import pstdev

from app.models.stocks import FundamentalDetails


def finite(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _value(frame, column, *names: str) -> float | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    for name in names:
        if name in frame.index and column in frame.columns:
            value = finite(frame.loc[name, column])
            if value is not None:
                return value
    return None


def _columns(frame, today: date) -> list:
    if frame is None or getattr(frame, "empty", True):
        return []
    return sorted(
        (col for col in frame.columns if hasattr(col, "date") and col.date() <= today),
        reverse=True,
    )


def _cagr(current: float | None, previous: float | None, years: float) -> float | None:
    # Loss-to-profit transitions and negative bases do not have meaningful CAGRs.
    if current is None or previous is None or current <= 0 or previous <= 0:
        return None
    return finite((current / previous) ** (1 / years) - 1)


def extract_fundamental_details(info: dict, income=None, balance=None, *, today: date):
    debt, cash, ebitda = (finite(info.get(key)) for key in ("totalDebt", "totalCash", "ebitda"))
    period = finite(info.get("mostRecentQuarter"))
    try:
        period_end = datetime.fromtimestamp(period, UTC).date() if period is not None else None
    except (ValueError, OverflowError, OSError):
        period_end = None
    values = dict(
        operating_margin=finite(info.get("operatingMargins")),
        enterprise_to_ebitda=finite(info.get("enterpriseToEbitda")),
        price_to_book=finite(info.get("priceToBook")),
        book_value=finite(info.get("bookValue")),
        total_debt=debt,
        total_cash=cash,
        ebitda=ebitda,
        net_debt_to_ebitda=(
            finite((debt - cash) / ebitda)
            if debt is not None
            and debt >= 0
            and cash is not None
            and cash >= 0
            and ebitda is not None
            and ebitda > 0
            else None
        ),
        latest_period_end=period_end,
    )
    columns = _columns(income, today)
    # Annual metrics are not refreshed by fetching the same old statement again.
    if columns and (today - columns[0].date()).days <= 550:
        latest = columns[0]
        values["annual_period_end"] = latest.date()
        ebit = _value(income, latest, "EBIT", "Operating Income")
        interest = _value(income, latest, "Interest Expense", "Interest Expense Non Operating")
        if ebit is not None and interest is not None and abs(interest) > 0:
            values["interest_coverage"] = finite(ebit / abs(interest))

        margins, margin_dates = [], []
        for col in columns[:5]:
            revenue = _value(income, col, "Total Revenue")
            operating = _value(income, col, "Operating Income")
            if revenue is not None and revenue > 0 and operating is not None:
                margins.append(operating / revenue)
                margin_dates.append(col)
        if len(margins) >= 3 and all(
            330 <= (a.date() - b.date()).days <= 400
            for a, b in zip(margin_dates, margin_dates[1:], strict=False)
        ):
            values["operating_margin_volatility"] = pstdev(margins)

        old = next((col for col in columns if 1000 <= (latest - col).days <= 1190), None)
        if old is not None:
            years = (latest - old).days / 365.25
            values["revenue_cagr_3y"] = _cagr(
                _value(income, latest, "Total Revenue"),
                _value(income, old, "Total Revenue"),
                years,
            )
            values["eps_cagr_3y"] = _cagr(
                _value(income, latest, "Diluted EPS", "Basic EPS"),
                _value(income, old, "Diluted EPS", "Basic EPS"),
                years,
            )

        previous = next((col for col in columns[1:] if 330 <= (latest - col).days <= 400), None)
        pretax = _value(income, latest, "Pretax Income")
        tax = _value(income, latest, "Tax Provision")
        capitals = []
        for col in (latest, previous):
            d = _value(balance, col, "Total Debt")
            equity = _value(balance, col, "Stockholders Equity", "Common Stock Equity")
            if d is not None and d >= 0 and equity is not None and equity > 0:
                capitals.append(d + equity)
        if (
            len(capitals) == 2
            and ebit is not None
            and pretax is not None
            and pretax > 0
            and tax is not None
            and 0 <= tax / pretax <= 1
        ):
            # NOPAT / average interest-bearing debt plus shareholders' equity.
            values["return_on_invested_capital"] = finite(
                ebit * (1 - tax / pretax) / (sum(capitals) / 2)
            )
    return FundamentalDetails(**values)
