"""Sector-aware fundamental percentiles from acquired financial evidence only.

Five equal-weight pillars for operating companies; three for financial firms.
Cash-flow and industrial leverage ratios are inapplicable to financial firms.
At least five eligible, same-market, same-profile observations per input are
required. Missing inputs are never neutral scores. No price momentum enters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import mean

from app.models.fundamentals import FundamentalAssessment
from app.models.stocks import FinancialMetrics, GpwCompany
from app.services.fundamental_data import finite

MIN_PEERS = 5
PILLARS = {
    "profitability": ("roe", "roa", "operatingMargin", "netMargin", "roic", "marginVolatility"),
    "growth": ("revenueGrowthYoy", "epsGrowthYoy", "revenueCagr3y", "epsCagr3y"),
    "cashflow": ("fcfMargin", "ocfMargin", "cashConversion"),
    "debt": ("netDebtToEbitda", "interestCoverage"),
    "valuation": ("earningsYield", "ebitdaYield", "fcfYield"),
}
FINANCIAL_PILLARS = {
    "profitability": ("roe", "roa"),
    "growth": PILLARS["growth"],
    "valuation": ("earningsYield", "bookYield"),
}
MIN_INPUTS = {"profitability": 2, "growth": 1, "cashflow": 2, "debt": 1, "valuation": 2}


def financial_profile(company: GpwCompany) -> str:
    specific = f"{company.industry or ''} {company.name}".casefold()
    sector = (company.sector or "").casefold()
    if "bank" in specific or "bank" in sector:
        return "bank"
    if any(word in f"{specific} {sector}" for word in ("insurance", "ubezpiecz")):
        return "insurance"
    if any(word in sector for word in ("financial", "finans")):
        return "financial"
    return "corporate"


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _fresh(stamp, as_of: date) -> bool:
    return (
        isinstance(stamp, datetime)
        and stamp.tzinfo is not None
        and stamp.utcoffset() is not None
        and 0 <= (as_of - stamp.date()).days <= 45
    )


def _ratio(a, b, *, positive: bool = True) -> float | None:
    a, b = finite(a), finite(b)
    if a is None or b is None or (b <= 0 if positive else b == 0):
        return None
    return finite(a / b)


def _statement(observation: dict, kind: str, as_of: date) -> dict:
    statement = observation.get("statements", {}).get(kind, {})
    return statement.get("payload", {}) if _fresh(statement.get("observed_at"), as_of) else {}


def _periods(values: list, as_of: date) -> list[dict]:
    unique = {
        row["periodEnd"]: row
        for row in values
        if isinstance(row, dict)
        and (day := _day(row.get("periodEnd"))) is not None
        and day <= as_of
    }
    return [unique[key] for key in sorted(unique, reverse=True)]


def _four(rows: list[dict], as_of: date) -> list[dict]:
    rows = rows[:4]
    if len(rows) != 4 or (as_of - _day(rows[0]["periodEnd"])).days > 190:
        return []
    if not all(
        65 <= (_day(a["periodEnd"]) - _day(b["periodEnd"])).days <= 115
        for a, b in zip(rows, rows[1:], strict=False)
    ):
        return []
    if not 250 <= (_day(rows[0]["periodEnd"]) - _day(rows[-1]["periodEnd"])).days <= 310:
        return []
    return rows


def _sum(rows: list[dict], key: str) -> float | None:
    numbers = [finite(row.get(key)) for row in rows]
    return finite(sum(numbers)) if len(numbers) == 4 and None not in numbers else None


@dataclass
class _Evidence:
    company: GpwCompany
    profile: str
    inputs: dict[str, float | None]
    excluded: list[str]
    warnings: list[str] = field(default_factory=list)
    latest: date | None = None
    annual: date | None = None

    @property
    def pillars(self):
        return PILLARS if self.profile == "corporate" else FINANCIAL_PILLARS


def _evidence(company: GpwCompany, observation: dict, excluded: list[str], as_of: date):
    profile = financial_profile(company)
    pillars = PILLARS if profile == "corporate" else FINANCIAL_PILLARS
    row = _Evidence(
        company, profile, dict.fromkeys(k for ks in pillars.values() for k in ks), list(excluded)
    )
    metrics = observation.get("metrics")
    if not isinstance(metrics, FinancialMetrics) or not _fresh(
        observation.get("observed_at"), as_of
    ):
        if "fundamentals_missing" not in row.excluded:
            row.excluded.append("fundamentals_stale")
        return row
    inputs = row.inputs
    loss = any(v is not None and v <= 0 for v in (metrics.net_income, metrics.eps))
    roe = finite(metrics.return_on_equity)
    inputs["roe"] = None if loss and roe is not None and roe > 0 else roe
    inputs["roa"] = finite(metrics.return_on_assets)
    pe = finite(metrics.pe_ratio)
    inputs["earningsYield"] = 0.0 if loss else _ratio(1, pe)
    if loss:
        row.warnings.append("loss_making")
    details = metrics.fundamental_details
    if details is not None:
        row.latest, row.annual = details.latest_period_end, details.annual_period_end
        if row.latest is not None and not 0 <= (as_of - row.latest).days <= 550:
            row.excluded.append("report_stale")
        if row.latest is None:
            row.warnings.append("report_date_unknown")
        if profile == "corporate":
            inputs["operatingMargin"] = finite(details.operating_margin)
            inputs["netMargin"] = _ratio(metrics.net_income, metrics.total_revenue)
            inputs["netDebtToEbitda"] = finite(details.net_debt_to_ebitda)
            inputs["ebitdaYield"] = _ratio(1, details.enterprise_to_ebitda)
            if details.ebitda is not None and details.ebitda <= 0:
                inputs["netDebtToEbitda"] = None
                inputs["ebitdaYield"] = 0.0
                row.warnings.append("nonpositive_ebitda")
        else:
            inputs["bookYield"] = (
                _ratio(1, details.price_to_book)
                if details.book_value is not None and details.book_value > 0
                else None
            )
        if row.annual is not None and 0 <= (as_of - row.annual).days <= 550:
            inputs["revenueCagr3y"] = finite(details.revenue_cagr_3y)
            inputs["epsCagr3y"] = finite(details.eps_cagr_3y)
            if profile == "corporate":
                inputs["roic"] = finite(details.return_on_invested_capital)
                volatility = finite(details.operating_margin_volatility)
                inputs["marginVolatility"] = volatility if volatility is not None else None
                inputs["interestCoverage"] = finite(details.interest_coverage)
    elif profile == "corporate":
        inputs["netMargin"] = _ratio(metrics.net_income, metrics.total_revenue)

    quarterly = _statement(observation, "quarterly", as_of)
    reports = _periods(quarterly.get("reports", []), as_of)
    if reports and (as_of - _day(reports[0]["periodEnd"])).days <= 190:
        latest = reports[0]
        prior = next(
            (
                r
                for r in reports[1:]
                if 330 <= (_day(latest["periodEnd"]) - _day(r["periodEnd"])).days <= 400
            ),
            None,
        )
        if prior:
            for name, key in (("revenueGrowthYoy", "totalRevenue"), ("epsGrowthYoy", "eps")):
                ratio = _ratio(latest.get(key), prior.get(key))
                inputs[name] = ratio - 1 if ratio is not None else None

    if profile != "corporate":
        row.warnings.append("limited_financial_profile")
        return row
    cash_payload = _statement(observation, "cashflow", as_of)
    cash = _four(
        _periods(
            [p for p in cash_payload.get("periods", []) if p.get("periodType") == "quarterly"],
            as_of,
        ),
        as_of,
    )
    income = _four(reports, as_of)
    currencies = {p.get("currency") for p in cash}
    coherent = (
        cash
        and income
        and [p["periodEnd"] for p in cash] == [p["periodEnd"] for p in income]
        and len(currencies) == 1
        and None not in currencies
        and currencies == {quarterly.get("financialCurrency")} == {metrics.financial_currency}
    )
    if coherent:
        # Derive missing FCF only when both operating cash flow and capex exist.
        cash = [dict(p) for p in cash]
        for period in cash:
            if period.get("freeCashFlow") is None:
                ocf, capex = finite(period.get("operatingCashFlow")), finite(period.get("capex"))
                if ocf is not None and capex is not None and capex >= 0:
                    period["freeCashFlow"] = ocf - capex
        ocf, fcf = _sum(cash, "operatingCashFlow"), _sum(cash, "freeCashFlow")
        revenue, profit = _sum(income, "totalRevenue"), _sum(income, "netIncome")
        inputs["fcfMargin"], inputs["ocfMargin"] = _ratio(fcf, revenue), _ratio(ocf, revenue)
        inputs["cashConversion"] = _ratio(ocf, profit)
        currency = "GBP" if company.currency == "GBp" else company.currency
        if currency and currencies == {currency}:
            inputs["fcfYield"] = _ratio(fcf, metrics.market_cap)
        else:
            row.warnings.append("valuation_currency_mismatch")
        if fcf is not None and fcf <= 0:
            row.warnings.append("nonpositive_fcf")
        if profit is not None and profit > 0 and ocf is not None and ocf < profit:
            row.warnings.append("weak_cash_conversion")
    if inputs["netDebtToEbitda"] is not None and inputs["netDebtToEbitda"] > 3:
        row.warnings.append("high_debt")
    if inputs["interestCoverage"] is not None and inputs["interestCoverage"] < 1:
        row.warnings.append("interest_not_covered")
    return row


def assess_fundamentals(
    companies: list[GpwCompany],
    observations: dict[str, dict],
    *,
    as_of: date,
    exclusions: dict[str, list[str]],
) -> dict[str, FundamentalAssessment]:
    rows = [
        _evidence(c, observations.get(c.ticker, {}), exclusions.get(c.ticker, []), as_of)
        for c in companies
    ]
    output = {}
    for row in rows:
        ranked, groups, counts = {}, set(), []
        if not row.excluded:
            for key, value in row.inputs.items():
                if value is None:
                    continue
                peers = [
                    p
                    for p in rows
                    if not p.excluded
                    and p.profile == row.profile
                    and p.company.market == row.company.market
                    and p.inputs.get(key) is not None
                ]
                sector = [
                    p
                    for p in peers
                    if row.company.sector and p.company.sector == row.company.sector
                ]
                group = "sector" if len(sector) >= MIN_PEERS else "market"
                peers = sector if group == "sector" else peers
                if len(peers) < MIN_PEERS:
                    continue
                values = [p.inputs[key] for p in peers]
                below, tied = sum(v < value for v in values), sum(v == value for v in values)
                score = 100 * (below + (tied - 1) / 2) / (len(values) - 1)
                if key in ("netDebtToEbitda", "marginVolatility"):
                    score = 100 - score
                if (
                    key
                    in (
                        "roe",
                        "roa",
                        "roic",
                        "operatingMargin",
                        "netMargin",
                        "fcfMargin",
                        "ocfMargin",
                        "cashConversion",
                        "earningsYield",
                        "ebitdaYield",
                        "fcfYield",
                        "bookYield",
                        "interestCoverage",
                    )
                    and value <= 0
                ):
                    score = 0.0
                if key in PILLARS["growth"] and value < 0:
                    score = min(score, 50.0)
                ranked[key] = round(score, 2)
                counts.append(len(peers))
                groups.add(group)
        pillars = {}
        missing = list(dict.fromkeys(row.excluded))
        for pillar, keys in row.pillars.items():
            parts = [ranked[key] for key in keys if key in ranked]
            pillars[pillar] = round(mean(parts), 2) if len(parts) >= MIN_INPUTS[pillar] else None
            if pillars[pillar] is None:
                missing.append(f"{pillar}_missing")
                if (
                    not row.excluded
                    and sum(row.inputs[k] is not None for k in keys) >= MIN_INPUTS[pillar]
                ):
                    if "peers_missing" not in missing:
                        missing.append("peers_missing")
        total = mean(pillars.values()) if all(v is not None for v in pillars.values()) else None
        output[row.company.ticker] = FundamentalAssessment(
            profile=row.profile,
            score=round(total, 2) if total is not None else None,
            pillars=pillars,
            inputs=row.inputs,
            metric_scores=ranked,
            coverage=round(
                100 * sum(v is not None for v in row.inputs.values()) / len(row.inputs), 2
            ),
            missing=missing,
            warnings=row.warnings,
            not_applicable=["cashflow", "debt"] if row.profile != "corporate" else [],
            comparison_group=next(iter(groups))
            if len(groups) == 1
            else "mixed"
            if groups
            else "market",
            peer_count=min(counts, default=0),
            latest_period_end=row.latest,
            annual_period_end=row.annual,
        )
    return output
