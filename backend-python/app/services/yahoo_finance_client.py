"""Yahoo Finance data client — OHLCV bars and fundamentals for every market.

Replaces stooq.pl as the primary data source.  yfinance is synchronous
internally so each download runs in a thread via asyncio.to_thread().

Ticker mapping (``app/markets.py``): the app's lower-case ticker becomes the
symbol Yahoo knows — 'kgh' → 'KGH.WA', 'aapl.us' → 'AAPL', 'hsba.l' → 'HSBA.L'.

The class-level semaphore caps the number of simultaneous yfinance downloads
for the entire process, regardless of how many callers use this client.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TypeVar

from app.analysis.timeframe import IntradayBar
from app.markets import market_for_yahoo_symbol, yahoo_symbol
from app.models import (
    CashflowPeriod,
    FinancialMetrics,
    QuarterlyReport,
    StooqDailyQuote,
)
from app.services.exceptions import NoIntradayDataError, StooqAccessError

logger = logging.getLogger(__name__)

_FOUR = Decimal("0.0001")


_T = TypeVar("_T")

# Yahoo answers bursts with "Too Many Requests" (seen 2026-09-16 while checking
# ~500 US listings). The download gate keeps requests few at a time, but a
# nightly run over a thousand tickers can still trip the limit, so a
# rate-limited call waits and tries again instead of costing the ticker its
# night. The wait is spent in the worker thread while holding the gate, which
# slows the whole run down — exactly what the limit asks for.
_RATE_LIMIT_WAITS_SECONDS = (15.0, 45.0)


def _utcnow() -> datetime:
    """The current moment — one seam, so tests can put the clock mid-session."""
    return datetime.now(tz=UTC)


def _sleep(seconds: float) -> None:
    """A pause — one seam, so tests do not wait out a rate limit."""
    time.sleep(seconds)


def _is_rate_limited(exc: BaseException) -> bool:
    return "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc)


def _with_rate_limit_retry(call: Callable[[], _T], what: str) -> _T:
    """Run ``call``; on Yahoo's rate limit wait and retry, then give up."""
    for wait in _RATE_LIMIT_WAITS_SECONDS:
        try:
            return call()
        except Exception as exc:
            if not _is_rate_limited(exc):
                raise
            logger.warning("Yahoo rate limit on %s; retrying in %.0f s.", what, wait)
            _sleep(wait)
    return call()

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


def _volume_or_nan(row) -> float:
    """A bar's volume as a float, or NaN when Yahoo did not report one.

    Returning NaN rather than 0 lets the callers treat a missing volume exactly
    like a missing price — one ``math.isnan`` check drops the bar — instead of
    the two download paths quietly disagreeing about it, which is how the daily
    path came to skip such bars (``int(nan)`` raised into a blanket ``except``)
    while the intraday one turned them into zero-volume candles.
    """
    raw = row.get("Volume")
    if raw is None:
        return float("nan")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("nan")


class YahooFinanceClient:
    """Downloads EOD OHLCV data (and fundamentals) from Yahoo Finance via yfinance.

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
        """Download EOD OHLCV bars for one ticker.

        Only **finished** sessions are returned: a bar for a session still
        trading is left out (see ``_fetch_sync``).

        Args:
            ticker:     The app's ticker, e.g. ``'kgh'`` or ``'aapl.us'``.
            from_date:  Oldest bar to include (inclusive).
            to_date:    Newest bar to include (inclusive); defaults to today.

        Raises:
            ValueError:      Ticker is empty or not a valid ticker.
            StooqAccessError: Yahoo Finance returned no usable data.
        """
        if not ticker or not ticker.strip():
            raise ValueError("Ticker must be provided.")

        yf_ticker = yahoo_symbol(ticker)
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
        """Synchronous download — runs inside a ThreadPoolExecutor thread.

        A bar for a session that has not finished yet is dropped. Yahoo serves
        the day in progress as if it were a normal daily bar — at 17:39 Warsaw
        (11:39 New York) AAPL's "today" had a fifth of a normal day's volume —
        and unusually low volume is precisely what VSA reads as a signal. The
        ingest re-fetches the last few days every night, so the finished bar is
        picked up by the first run after the close.
        """
        import yfinance as yf  # deferred: yfinance is a heavy import

        market = market_for_yahoo_symbol(yf_ticker)
        now = _utcnow()

        # Yahoo Finance ``end`` is exclusive; our to_date is inclusive.
        end = (to_date + timedelta(days=1)).isoformat() if to_date else None
        start = from_date.isoformat() if from_date else None

        try:
            df = _with_rate_limit_retry(
                lambda: yf.Ticker(yf_ticker).history(
                    start=start,
                    end=end,
                    auto_adjust=True,
                    actions=False,
                    raise_errors=False,
                ),
                yf_ticker,
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
        unfinished = 0
        for ts, row in df.iterrows():
            try:
                # Daily bars are stamped at midnight in the exchange's own
                # zone, so the timestamp's date is the session date.
                if not market.session_is_final(ts.date(), now):
                    unfinished += 1
                    continue

                open_ = float(row["Open"])
                high = float(row["High"])
                low = float(row["Low"])
                close = float(row["Close"])
                volume = _volume_or_nan(row)

                # A bar with a missing volume is dropped, not defaulted to
                # zero. VSA reads volume, and several of its rules fire on
                # UNUSUALLY LOW volume (No Demand, the Test), so a fabricated
                # zero is not a harmless placeholder — it is the quietest bar
                # the stock has ever printed, and it would manufacture bearish
                # signals out of a gap in Yahoo's data. Losing one candle is
                # the cheaper mistake. The intraday path does the same.
                if any(math.isnan(v) for v in (open_, high, low, close, volume)):
                    continue

                quotes.append(
                    StooqDailyQuote(
                        date=ts.date(),
                        open=Decimal(str(open_)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        high=Decimal(str(high)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        low=Decimal(str(low)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        close=Decimal(str(close)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        volume=int(volume),
                    )
                )
            except Exception:
                logger.debug("Skipping malformed row for %s on %s.", yf_ticker, ts)

        if not quotes:
            if unfinished:
                # Everything Yahoo had was the session still in progress. That
                # is not a provider failure — nothing is final yet.
                return []
            raise StooqAccessError(
                f"Yahoo Finance returned no parseable rows for '{yf_ticker}'."
            )

        return sorted(quotes, key=lambda q: q.date)

    # ── Intraday bars (chart timeframes) ─────────────────────────────────────

    async def get_intraday_history(
        self,
        ticker: str,
        interval: str,
        lookback_days: int,
    ) -> list[IntradayBar]:
        """Download intraday OHLCV bars for one ticker.

        Unlike the EOD history, intraday bars are **not stored** by this app —
        Yahoo only serves a limited recent window of them (60 days at 30m, 730
        at 1h), so they are fetched on demand when someone opens an intraday
        chart and cached briefly by the caller.

        Args:
            ticker:        The app's ticker, e.g. ``'jsw'`` or ``'aapl.us'``.
            interval:      Yahoo interval string, ``'30m'`` or ``'1h'``.
            lookback_days: How many calendar days back to request.

        Raises:
            ValueError:       Ticker is empty or not a valid ticker.
            StooqAccessError: Yahoo Finance returned no usable intraday data.
        """
        if not ticker or not ticker.strip():
            raise ValueError("Ticker must be provided.")

        yf_ticker = yahoo_symbol(ticker)
        async with self._get_semaphore():
            return await asyncio.to_thread(
                self._fetch_intraday_sync, yf_ticker, interval, max(1, lookback_days)
            )

    def _fetch_intraday_sync(
        self,
        yf_ticker: str,
        interval: str,
        lookback_days: int,
    ) -> list[IntradayBar]:
        """Synchronous intraday download — runs inside a ThreadPoolExecutor thread."""
        import yfinance as yf  # deferred: yfinance is a heavy import

        exchange_tz = market_for_yahoo_symbol(yf_ticker).tz

        try:
            df = yf.Ticker(yf_ticker).history(
                period=f"{lookback_days}d",
                interval=interval,
                auto_adjust=True,
                actions=False,
                raise_errors=False,
            )
        except Exception as exc:
            raise StooqAccessError(
                f"Yahoo Finance intraday request failed for '{yf_ticker}': {exc}"
            ) from exc

        # The request itself succeeded and came back empty: Yahoo has no
        # intraday history for this listing. That is a fact about the ticker,
        # not an outage, so it gets its own exception type — see
        # NoIntradayDataError for why the distinction matters.
        if df is None or df.empty:
            raise NoIntradayDataError(
                f"Yahoo Finance returned no {interval} data for '{yf_ticker}'."
            )

        df.columns = [c.capitalize() for c in df.columns]

        bars: list[IntradayBar] = []
        for ts, row in df.iterrows():
            try:
                open_ = float(row["Open"])
                high = float(row["High"])
                low = float(row["Low"])
                close = float(row["Close"])
                volume = _volume_or_nan(row)

                # Same rule as the daily path above: a bar whose volume Yahoo
                # did not report is dropped rather than defaulted to zero, so
                # the VSA engine never sees a fabricated "quietest bar ever".
                if any(math.isnan(v) for v in (open_, high, low, close, volume)):
                    continue

                # Yahoo stamps bars in the exchange's own timezone; anything
                # else (a naive or UTC index) is converted to it, so a bar is
                # always labelled with the exchange's wall-clock time it traded
                # (Warsaw for the GPW, New York for US stocks).
                stamp = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=exchange_tz)
                else:
                    stamp = stamp.astimezone(exchange_tz)

                bars.append(
                    IntradayBar(
                        date=stamp,
                        open=Decimal(str(open_)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        high=Decimal(str(high)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        low=Decimal(str(low)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        close=Decimal(str(close)).quantize(_FOUR, rounding=ROUND_HALF_UP),
                        volume=int(volume),
                    )
                )
            except Exception:
                logger.debug(
                    "Skipping malformed %s row for %s on %s.", interval, yf_ticker, ts
                )

        if not bars:
            raise NoIntradayDataError(
                f"Yahoo Finance returned no parseable {interval} rows for '{yf_ticker}'."
            )

        return sorted(bars, key=lambda b: b.date)

    # ── Fundamentals ──────────────────────────────────────────────────────────

    async def get_fundamentals(self, ticker: str) -> FinancialMetrics:
        """Return the latest financial metrics for one ticker."""
        yf_ticker = yahoo_symbol(ticker)
        async with self._get_semaphore():
            return await asyncio.to_thread(self._fetch_fundamentals_sync, yf_ticker)

    def _fetch_fundamentals_sync(self, yf_ticker: str) -> FinancialMetrics:
        import yfinance as yf

        try:
            info = _with_rate_limit_retry(lambda: yf.Ticker(yf_ticker).info, yf_ticker) or {}
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
            financial_currency=_safe("financialCurrency"),
            # Yahoo reports these as fractions (0.184 = 18.4% return).
            return_on_equity=_safe("returnOnEquity"),
            return_on_assets=_safe("returnOnAssets"),
        )

    async def get_quarterly_reports(self, ticker: str) -> list[QuarterlyReport]:
        """Return the last 8 quarters of income-statement data for one ticker."""
        yf_ticker = yahoo_symbol(ticker)
        async with self._get_semaphore():
            return await asyncio.to_thread(self._fetch_quarterly_sync, yf_ticker)

    def _fetch_quarterly_sync(self, yf_ticker: str) -> list[QuarterlyReport]:
        import yfinance as yf

        try:
            stmt = _with_rate_limit_retry(
                lambda: yf.Ticker(yf_ticker).quarterly_income_stmt, yf_ticker
            )
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
        """Return annual + quarterly cash-flow periods for one ticker.

        Feeds the capex screen ("how much does this company invest in
        itself"). Periods with no capex figure at all are dropped — Yahoo
        often lists the row but leaves the cell empty, and an empty row is
        indistinguishable from "invested nothing" once stored.
        """
        yf_ticker = yahoo_symbol(ticker)
        async with self._get_semaphore():
            return await asyncio.to_thread(self._fetch_cashflow_sync, yf_ticker)

    def _fetch_cashflow_sync(self, yf_ticker: str) -> list[CashflowPeriod]:
        import yfinance as yf

        try:
            tk = yf.Ticker(yf_ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open %s for cash flow: %s", yf_ticker, exc)
            return []

        # The reporting currency is NOT always the trading currency (GPW
        # dual-listings report in EUR/USD/CZK…, HSBC trades in pence and
        # reports in dollars), and a figure without its currency is
        # meaningless, so it travels with every period.
        currency: str | None = None
        try:
            info = _with_rate_limit_retry(lambda: tk.info, yf_ticker) or {}
            currency = info.get("financialCurrency")
        except Exception as exc:  # noqa: BLE001
            logger.debug("No reporting currency for %s: %s", yf_ticker, exc)

        periods: list[CashflowPeriod] = []
        for attr, period_type, limit in (
            ("cashflow", "annual", _MAX_YEARS),
            ("quarterly_cashflow", "quarterly", _MAX_QUARTERS),
        ):
            try:
                frame = _with_rate_limit_retry(
                    lambda name=attr: getattr(tk, name), yf_ticker
                )
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
