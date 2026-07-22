"""Capital-expenditure ("how much do they invest?") screen.

Builds the data behind ``GET /api/stocks/capex``: for every tracked GPW
company, how much money it actually spends on investing in its own business.

**Capex** (capital expenditure) is the cash a company puts into plants,
machines, buildings, vehicles and software — the "purchase of property, plant
and equipment" line of the cash-flow statement. Read plainly: a company that
keeps investing is building future capacity; one whose capex has collapsed is
often harvesting an existing business rather than growing it.

Four numbers make that comparable across companies of very different sizes:

  * **capex** — the money itself, over the last four reported quarters (TTM)
    or, when quarterly data is missing, the latest full year (``basis`` says
    which, so the two are never silently mixed).
  * **capex growth YoY** — latest full year vs the year before. Uses annual
    figures on both sides, because Yahoo publishes only ~5 quarters and a
    quarter-on-quarter comparison would be seasonal noise.
  * **capex / revenue** — capital intensity. A small company investing 20% of
    its revenue is doing something a giant investing 3% is not.
  * **capex / operating cash flow** — above 100% the investment is bigger than
    what the business itself generated, so it is being funded from cash
    reserves or debt.

Data source: Yahoo Finance cash-flow statements, stored in ``company_cashflow``
by the ingest job's fundamentals pass (see ``app/jobs/daily_ingest.py``). This
service never calls Yahoo — the screen covers the whole universe at once, so
it reads the database and nothing else. Coverage is genuinely incomplete
(Yahoo has no usable capex for roughly one company in twenty, and no full four
quarters for about one in five); those rows keep their identity and carry
``None`` figures rather than being dropped or zero-filled.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.models import CapexItem, CapexResponse, CapexSummary, CashflowPeriod, GpwCompany

logger = logging.getLogger(__name__)

# Quarters summed for a trailing-twelve-month figure. Single definition: the
# fundamentals endpoint sums revenue and net income by exactly the same rule.
_TTM_QUARTERS = 4


def sum_ttm(records: Sequence[Any], field: str, sort_attr: str = "period_end") -> int | None:
    """Sum ``field`` over the four newest of ``records``.

    Shared by every trailing-twelve-month figure in the app (capex, operating
    cash flow, revenue, net income) — one rule, one place, so the stock page
    and the capex screen can never disagree about what "TTM" means.

    Returns ``None`` unless all four periods are present AND each carries the
    figure: a partial sum would understate a year and, on a ratio, produce a
    confidently wrong percentage. ``records`` may arrive in any order, so they
    are sorted newest-first here rather than trusting the caller.
    """
    newest = sorted(records, key=lambda r: getattr(r, sort_attr), reverse=True)
    newest = newest[:_TTM_QUARTERS]
    if len(newest) < _TTM_QUARTERS:
        return None
    values = [getattr(r, field) for r in newest]
    if any(v is None for v in values):
        return None
    return sum(values)


def _sum_ttm(periods: Sequence[CashflowPeriod], field: str) -> int | None:
    """Trailing-twelve-month ``field`` from a company's cash-flow periods.

    A cash-flow list holds annual AND quarterly rows for the same company, so
    the quarterly ones are picked out before the shared four-period sum runs.
    """
    return sum_ttm([p for p in periods if p.period_type == "quarterly"], field)


def _pct(numerator: int | None, denominator: int | None) -> float | None:
    """``numerator`` as a percentage of ``denominator``, or None.

    A non-positive denominator (a loss-making quarter's operating cash flow,
    or a missing revenue) has no meaningful percentage — better a blank cell
    than a negative "capital intensity".
    """
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def summarize_capex(
    periods: Sequence[CashflowPeriod],
    ttm_revenue: int | None = None,
) -> CapexSummary:
    """Condense one company's stored cash-flow periods into a screen row.

    Pure arithmetic — no I/O — so the rules above are unit-testable. An empty
    or capex-less input yields an all-``None`` summary (``basis`` is ``None``),
    which the UI renders as blank cells rather than zeros.
    """
    annual = sorted(
        (p for p in periods if p.period_type == "annual"),
        key=lambda p: p.period_end,
        reverse=True,
    )
    latest_annual = annual[0] if annual else None
    prev_annual = annual[1] if len(annual) > 1 else None

    capex_ttm = _sum_ttm(periods, "capex")
    ocf_ttm = _sum_ttm(periods, "operating_cash_flow")
    capex_annual = latest_annual.capex if latest_annual else None

    # Prefer the trailing twelve months (more current); fall back to the last
    # full year. Every ratio below is then computed on that same basis, so a
    # row never divides a yearly figure by a quarterly one.
    if capex_ttm is not None:
        basis: str | None = "ttm"
        capex = capex_ttm
        ocf = ocf_ttm
    elif capex_annual is not None:
        basis = "annual"
        capex = capex_annual
        ocf = latest_annual.operating_cash_flow if latest_annual else None
    else:
        basis = None
        capex = None
        ocf = None

    # Year-on-year change in yearly investment, both sides annual.
    growth = None
    if (
        latest_annual is not None
        and prev_annual is not None
        and latest_annual.capex is not None
        and prev_annual.capex
    ):
        growth = round(
            (latest_annual.capex - prev_annual.capex) / prev_annual.capex * 100, 1
        )

    currency = next((p.currency for p in periods if p.currency), None)

    return CapexSummary(
        currency=currency,
        basis=basis,  # type: ignore[arg-type]  # constrained by construction above
        capex=capex,
        capex_ttm=capex_ttm,
        capex_annual=capex_annual,
        annual_period_end=latest_annual.period_end if latest_annual else None,
        capex_prev_annual=prev_annual.capex if prev_annual else None,
        capex_growth_yoy_pct=growth,
        # Revenue is Yahoo's trailing-twelve-month figure. Pairing it with an
        # annual-basis capex is an approximation, which is exactly what
        # ``basis`` tells the reader.
        capex_to_revenue_pct=_pct(capex, ttm_revenue),
        capex_to_ocf_pct=_pct(capex, ocf),
        operating_cash_flow=ocf,
    )


def build_capex_screen(
    companies: Sequence[GpwCompany],
    cashflow: dict[str, list[CashflowPeriod]],
    revenue: dict[str, int],
) -> CapexResponse:
    """Assemble the full capex screen from stored cash-flow + revenue data.

    Every tracked company gets a row; those Yahoo has no capex for come back
    with blank figures (the endpoint can filter them out). Rows are ordered by
    capex descending, biggest investor first, with the no-data rows last.
    """
    items: list[CapexItem] = []
    for company in companies:
        periods = cashflow.get(company.ticker, [])
        summary = summarize_capex(periods, revenue.get(company.ticker))
        items.append(
            CapexItem(
                ticker=company.ticker.upper(),
                name=company.name,
                sector=company.sector,
                **summary.model_dump(),
            )
        )

    with_data = [i for i in items if i.capex is not None]
    as_of = max(
        (i.annual_period_end for i in items if i.annual_period_end), default=None
    )
    # Newest quarter end can be more recent than the newest year end.
    latest_quarter = max(
        (
            p.period_end
            for periods in cashflow.values()
            for p in periods
            if p.period_type == "quarterly"
        ),
        default=None,
    )
    if latest_quarter and (as_of is None or latest_quarter > as_of):
        as_of = latest_quarter

    items.sort(key=lambda i: (i.capex is None, -(i.capex or 0)))

    return CapexResponse(
        as_of=as_of,
        total_count=len(items),
        with_data_count=len(with_data),
        scanned_count=len(companies),
        items=items,
    )
