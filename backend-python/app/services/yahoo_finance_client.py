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

from app.models import FinancialMetrics, QuarterlyReport, StooqDailyQuote
from app.services.exceptions import StooqAccessError

logger = logging.getLogger(__name__)

_FOUR = Decimal("0.0001")


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
