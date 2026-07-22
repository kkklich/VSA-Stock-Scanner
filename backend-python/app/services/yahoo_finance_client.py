"""Yahoo Finance data client for GPW OHLCV data.

Replaces stooq.pl as the primary data source.  yfinance is synchronous
internally so each download runs in a thread via asyncio.to_thread().

GPW ticker mapping:  'kgh' (internal lowercase) → 'KGH.WA' (Yahoo Finance)

The class-level semaphore caps the number of simultaneous yfinance downloads
for the entire process, regardless of how many callers use this client.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.models import (
    CashflowPeriod,
    FinancialMetrics,
    QuarterlyReport,
    StooqDailyQuote,
)
from app.services.exceptions import StooqAccessError

logger = logging.getLogger(__name__)

_FOUR = Decimal("0.0001")

# Cash-flow statement rows we read, in fallback order. Yahoo labels the capex
# line "Capital Expenditure" for most companies; a minority only carry
# "Purchase Of PPE" (the same thing under the statement's own wording). Both
# are cash OUTFLOWS (negative), so both normalise to positive spend the same
# way. "Net PPE Purchase And Sale" is deliberately NOT used as a fallback: it
# nets asset sales against purchases and can even be positive, which is a
# different quantity from "money invested".
_CAPEX_ROWS = ("Capital Expenditure", "Purchase Of PPE")
_OCF_ROWS = ("Operating Cash Flow",)
_FCF_ROWS = ("Free Cash Flow",)
# Reported periods kept per ticker: 8 quarters covers two years of TTM sums,
# 5 years covers the year-on-year comparison with room to spare.
_MAX_QUARTERS = 8
_MAX_YEARS = 5


class YahooFinanceClient:
    """Downloads GPW EOD OHLCV data from Yahoo Finance via yfinance.

    Implements the same ``get_daily_history`` interface as StooqClient so all
    existing code (ingest service, ranking service, routers) works without
    any changes.
    """

    # Class-level semaphore: shared across all instances, limits total
    # simultaneous yfinance downloads for the whole process.
    _semaphore: asyncio.Semaphore | None = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(5)
        return cls._semaphore

    async def get_daily_history(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[StooqDailyQuote]:
        """Download EOD OHLCV bars for a GPW ticker (stooq lowercase format).

        Args:
            ticker:     Lowercase GPW ticker, e.g. ``'kgh'``.
            from_date:  Oldest bar to include (inclusive).
            to_date:    Newest bar to include (inclusive); defaults to today.

        Raises:
            ValueError:      Ticker is empty.
            StooqAccessError: Yahoo Finance returned no usable data.
        """
        if not ticker or not ticker.strip():
            raise ValueError("Ticker must be provided.")

        yf_ticker = ticker.strip().upper() + ".WA"
        async with self._get_semaphore():
            return await asyncio.to_thread(
                self._fetch_sync, yf_ticker, from_date, to_date
            )

    def _fetch_sync(
        self,
        yf_ticker: str,
        from_date: date | None,
        to_date: date | None,
    ) -> list[StooqDailyQuote]:
        """Synchronous download — runs inside a ThreadPoolExecutor thread."""
        import yfinance as yf  # deferred: yfinance is a heavy import

        # Yahoo Finance ``end`` is exclusive; our to_date is inclusive.
        end = (to_date + timedelta(days=1)).isoformat() if to_date else None
        start = from_date.isoformat() if from_date else None

        try:
            obj = yf.Ticker(yf_ticker)
            df = obj.history(
                start=start,
                end=end,
                auto_adjust=True,
                actions=False,
                raise_errors=False,
            )
        except Exception as exc:
            raise StooqAccessError(
                f"Yahoo Finance request failed for '{yf_ticker}': {exc}"
            ) from exc

        if df is None or df.empty:
            raise StooqAccessError(
                f"Yahoo Finance returned no data for '{yf_ticker}'."
            )

        # Normalize column names: some yfinance versions return lowercase.
        df.columns = [c.capitalize() for c in df.columns]

        quotes: list[StooqDailyQuote] = []
        for ts, row in df.iterrows():
            try:
                open_ = float(row["Open"])
                high = float(row["High"])
                low = float(row["Low"])
                close = float(row["Close"])
                volume = int(row.get("Volume", 0))

                if any(math.isnan(v) for v in (open_, high, low, close)):
                    continue

                quotes.append(
                    StooqDailyQuote(
                        date=ts.date(),
                        open=Decimal(str(open_)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        high=Decimal(str(high)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        low=Decimal(str(low)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        close=Decimal(str(close)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        volume=volume,
                    )
                )
            except Exception:
                logger.debug("Skipping malformed row for %s on %s.", yf_ticker, ts)

        if not quotes:
            raise StooqAccessError(
                f"Yahoo Finance returned no parseable rows for '{yf_ticker}'."
            )

        return sorted(quotes, key=lambda q: q.date)

    # ── Fundamentals ──────────────────────────────────────────────────────────

    async def get_fundamentals(self, ticker: str) -> FinancialMetrics:
        """Return the latest financial metrics for a GPW ticker."""
        yf_ticker = ticker.strip().upper() + ".WA"
        async with self._get_semaphore():
            return await asyncio.to_thread(self._fetch_fundamentals_sync, yf_ticker)

    def _fetch_fundamentals_sync(self, yf_ticker: str) -> FinancialMetrics:
        import yfinance as yf

        try:
            info = yf.Ticker(yf_ticker).info or {}
        except Exception as exc:
            logger.warning("Could not fetch fundamentals for %s: %s", yf_ticker, exc)
            info = {}

        def _safe(key: str):
            val = info.get(key)
            return val if val not in (None, "None", "", "N/A") else None

        return FinancialMetrics(
            market_cap=_safe("marketCap"),
            pe_ratio=_safe("trailingPE"),
            forward_pe=_safe("forwardPE"),
            eps=_safe("trailingEps"),
            dividend_yield=_safe("dividendYield"),
            total_revenue=_safe("totalRevenue"),
            net_income=_safe("netIncomeToCommon"),
            shares_outstanding=_safe("sharesOutstanding"),
            # Yahoo reports these as fractions (0.184 = 18.4% return).
            return_on_equity=_safe("returnOnEquity"),
            return_on_assets=_safe("returnOnAssets"),
        )

    async def get_quarterly_reports(self, ticker: str) -> list[QuarterlyReport]:
        """Return the last 8 quarters of income-statement data for a GPW ticker."""
        yf_ticker = ticker.strip().upper() + ".WA"
        async with self._get_semaphore():
            return await asyncio.to_thread(self._fetch_quarterly_sync, yf_ticker)

    def _fetch_quarterly_sync(self, yf_ticker: str) -> list[QuarterlyReport]:
        import yfinance as yf

        try:
            stmt = yf.Ticker(yf_ticker).quarterly_income_stmt
        except Exception as exc:
            logger.warning("Could not fetch quarterly reports for %s: %s", yf_ticker, exc)
            return []

        if stmt is None or stmt.empty:
            return []

        def _row_val(col, name: str):
            for idx in stmt.index:
                if str(idx).lower() == name.lower():
                    val = stmt.loc[idx, col]
                    try:
                        f = float(val)
                        return None if math.isnan(f) else int(f)
                    except (TypeError, ValueError):
                        return None
            return None

        reports = []
        for col in stmt.columns[:8]:
            period_end = col.date() if hasattr(col, "date") else None
            if period_end is None:
                continue
            reports.append(
                QuarterlyReport(
                    period_end=period_end.isoformat(),
                    total_revenue=_row_val(col, "Total Revenue"),
                    net_income=_row_val(col, "Net Income"),
                    operating_income=_row_val(col, "Operating Income"),
                )
            )
        return reports

    # ── Cash flow (capital expenditure) ───────────────────────────────────────

    async def get_cashflow_periods(self, ticker: str) -> list[CashflowPeriod]:
        """Return annual + quarterly cash-flow periods for a GPW ticker.

        Feeds the capex screen ("how much does this company invest in
        itself"). Periods with no capex figure at all are dropped — Yahoo
        often lists the row but leaves the cell empty, and an empty row is
        indistinguishable from "invested nothing" once stored.
        """
        yf_ticker = ticker.strip().upper() + ".WA"
        async with self._get_semaphore():
            return await asyncio.to_thread(self._fetch_cashflow_sync, yf_ticker)

    def _fetch_cashflow_sync(self, yf_ticker: str) -> list[CashflowPeriod]:
        import yfinance as yf

        try:
            tk = yf.Ticker(yf_ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open %s for cash flow: %s", yf_ticker, exc)
            return []

        # The reporting currency is NOT always PLN (foreign dual-listings
        # report in EUR/USD/CZK…), and a figure without its currency is
        # meaningless, so it travels with every period.
        currency: str | None = None
        try:
            currency = (tk.info or {}).get("financialCurrency")
        except Exception as exc:  # noqa: BLE001
            logger.debug("No reporting currency for %s: %s", yf_ticker, exc)

        periods: list[CashflowPeriod] = []
        for attr, period_type, limit in (
            ("cashflow", "annual", _MAX_YEARS),
            ("quarterly_cashflow", "quarterly", _MAX_QUARTERS),
        ):
            try:
                frame = getattr(tk, attr)
            except Exception as exc:  # noqa: BLE001
                logger.debug("No %s for %s: %s", attr, yf_ticker, exc)
                continue
            periods.extend(
                _periods_from_frame(frame, period_type, currency, limit)  # type: ignore[arg-type]
            )

        return periods


# ── Cash-flow frame parsing (module level: pure, unit-testable) ───────────────

def _frame_value(frame, column, row_names: tuple[str, ...], labels: dict) -> int | None:
    """First present, non-empty value among ``row_names`` for one period.

    Yahoo frequently lists a row and leaves the cell empty (NaN) for the most
    recent period, so "the row exists" is not the same as "there is a number".

    ``labels`` maps a row's printed label to its index object. The caller builds
    it once per frame: this runs three times per reporting period and up to 13
    periods per company, so rebuilding the same map here meant ~39 rebuilds per
    ticker on a weekly pass over ~290 companies.
    """
    for name in row_names:
        idx = labels.get(name)
        if idx is None:
            continue
        try:
            value = float(frame.loc[idx, column])
        except (TypeError, ValueError):
            continue
        if math.isnan(value):
            continue
        return int(value)
    return None


def _periods_from_frame(
    frame,
    period_type: str,
    currency: str | None,
    limit: int,
) -> list[CashflowPeriod]:
    """Extract capex / cash-flow figures from one yfinance cash-flow frame.

    Columns are reporting periods (newest first), rows are statement lines.
    Periods without a capex figure are skipped.
    """
    if frame is None or getattr(frame, "empty", True):
        return []

    # Row labels are the same for every period in the frame, so resolve them
    # once here instead of on each of the ~39 per-ticker value lookups below.
    labels = {str(idx): idx for idx in frame.index}

    periods: list[CashflowPeriod] = []
    for column in list(frame.columns)[:limit]:
        period_end = column.date() if hasattr(column, "date") else None
        if period_end is None:
            continue
        capex = _frame_value(frame, column, _CAPEX_ROWS, labels)
        if capex is None:
            continue
        periods.append(
            CashflowPeriod(
                period_end=period_end.isoformat(),
                period_type=period_type,  # type: ignore[arg-type]  # caller passes a literal
                # Yahoo reports capex as a negative cash outflow; store it as
                # positive "money spent" so it reads and sorts naturally.
                capex=abs(capex),
                operating_cash_flow=_frame_value(frame, column, _OCF_ROWS, labels),
                free_cash_flow=_frame_value(frame, column, _FCF_ROWS, labels),
                currency=currency,
            )
        )
    return periods
