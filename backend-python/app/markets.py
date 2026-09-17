"""The stock markets the scanner can track — the one place that knows them.

Until 2026-09 StockPilot tracked the Warsaw Stock Exchange only, and that
assumption was spread through the code: a hard-coded ``.WA`` Yahoo suffix,
quality floors in złoty and a schedule on Warsaw time. Adding US and
Western-European stocks (roadmap #22, ``agent/MULTI-MARKET-PLAN.md``) makes
each of those facts depend on *which* market a stock trades on, and this
module is where that is answered.

**How a stock is identified.** A GPW ticker stays exactly as it always was:
``kgh``. A stock from any other market carries a market suffix — ``aapl.us``,
``sap.de``, ``mc.pa``, ``asml.as``, ``hsba.l``. The bare code cannot be reused,
because the clashes are real: GPW ``pep`` (Polenergia) and PepsiCo ``PEP``, GPW
``bdx`` (Budimex) and Becton Dickinson ``BDX``, GPW ``nwg`` (Newag) and NatWest
``NWG.L``. Leaving GPW unsuffixed means no stored bar, link or favorite had to
change.

**Money.** Prices stay exactly as Yahoo quotes them — in pence for most of
London (``GBp``: 1513.6 means £15.136) — and are converted only where stocks
are held to one bar: the liquidity and market-cap floors, which are defined in
złoty. The conversion starts from each *stock's* quote currency, not its
market's: London alone quotes lines in pence, dollars (Compass Group,
InterContinental Hotels) and euros (Metlen). The rates are fixed
approximations. The floors are coarse by design, and every index member clears
them by orders of magnitude, so a few percent of currency drift cannot move a
stock across them.

**Time.** Each market knows its exchange time zone and closing time, so a bar
for a session that is still trading can be recognised and refused. Such a bar
carries a fraction of a normal day's volume, and unusually low volume is
exactly what VSA reads as a signal (No Demand, the Test).

**Which markets are live** is a setting (``STOCKPILOT_MARKETS``, default
``gpw``), so markets can be switched on one at a time. The GPW is always on:
the whole app was built around it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.models import GpwCompany

logger = logging.getLogger(__name__)

GPW_ID = "gpw"

# A daily bar is only trusted once the session has closed AND the data provider
# has had a moment to publish the final print (closing auctions end a few
# minutes after the bell, and the day's volume is filled in after that).
SESSION_SETTLE = timedelta(minutes=15)

# Quality floors every ranked stock must clear (blueprint §5), in złoty.
MIN_MEDIAN_TURNOVER_PLN = 100_000.0
MIN_MARKET_CAP_PLN = 100_000_000

# The ticker columns in the database are VARCHAR(20).
MAX_TICKER_LENGTH = 20

#: Approximate złoty value of one unit of every currency a tracked stock is
#: quoted in. Only the quality floors use these (see the module docstring).
#: Over the year to 2026-09: USD/PLN 3.49–3.81, EUR/PLN 4.20–4.36, GBP/PLN
#: 4.78–5.10. "GBp" is one penny, the unit most London prices are quoted in.
PLN_PER_UNIT: dict[str, float] = {
    "PLN": 1.0,
    "USD": 3.8,
    "EUR": 4.35,
    "GBP": 5.1,
    "GBp": 0.051,
}


@dataclass(frozen=True)
class Market:
    """One stock market the scanner can track."""

    #: Short id used in URLs, settings and the company files ("gpw", "us").
    id: str
    #: Full name for the UI ("London Stock Exchange").
    name: str
    #: Compact label for a switcher or a chip ("GPW", "USA", "UK").
    short_name: str
    #: The country the market is in.
    country: str
    #: Coarse grouping for quick filters: "poland", "europe" or "usa".
    region: str
    #: The listing venue(s) as shown to the reader.
    exchange: str
    #: What the app appends to an exchange symbol ("" for the GPW, ".us" …).
    ticker_suffix: str
    #: What Yahoo appends to the same symbol (".WA", "" for US listings …).
    yahoo_suffix: str
    #: The currency most of its prices are quoted in, exactly as Yahoo writes
    #: it — "GBp" (pence) for London. A company's own ``currency`` wins where
    #: it differs (a London line quoted in dollars).
    currency: str
    #: The exchange's own time zone (IANA name).
    timezone: str
    #: Local time after which the day's bar is complete — the end of the
    #: closing auction, not of continuous trading.
    close_time: time
    #: Which nightly data run fetches this market ("europe" or "us").
    refresh_run: str = "europe"
    #: The indices the tracked companies are selected from (ids of INDEX_NAMES).
    indices: tuple[str, ...] = ()

    @property
    def tz(self) -> ZoneInfo:
        """The exchange time zone (ZoneInfo caches instances per key)."""
        return ZoneInfo(self.timezone)

    @property
    def major_currency(self) -> str:
        """The currency whole amounts (market cap) are stated in — GBP for pence."""
        return major_currency(self.currency)

    def session_is_final(self, day: date, now: datetime | None = None) -> bool:
        """Has the session dated ``day`` finished trading and settled?

        Days before today (in the exchange's own time zone) always have; today
        has once ``close_time`` plus ``SESSION_SETTLE`` has passed. A day after
        today cannot have, which also covers a timestamp read in the wrong zone.
        """
        current = (now or datetime.now(tz=UTC)).astimezone(self.tz)
        today = current.date()
        if day < today:
            return True
        if day > today:
            return False
        closes = datetime.combine(day, self.close_time, tzinfo=self.tz)
        return current >= closes + SESSION_SETTLE

    def latest_final_session(self, now: datetime | None = None) -> date:
        """The most recent weekday whose session has finished and settled.

        Public holidays are not known here, so on a holiday this names a day
        that never traded — callers treat it as "the newest session there
        could be", never as proof that one happened.
        """
        current = (now or datetime.now(tz=UTC)).astimezone(self.tz)
        day = current.date()
        while day.weekday() >= 5 or not self.session_is_final(day, current):
            day -= timedelta(days=1)
        return day


GPW = Market(
    id=GPW_ID,
    name="Warsaw Stock Exchange",
    short_name="GPW",
    country="Poland",
    region="poland",
    exchange="GPW",
    ticker_suffix="",
    yahoo_suffix=".WA",
    currency="PLN",
    timezone="Europe/Warsaw",
    # Continuous trading ends 16:50; the closing auction is done by 17:05.
    close_time=time(17, 5),
)

US = Market(
    id="us",
    name="US stock market (NASDAQ and NYSE)",
    short_name="USA",
    country="United States",
    region="usa",
    exchange="NASDAQ / NYSE",
    ticker_suffix=".us",
    yahoo_suffix="",
    currency="USD",
    timezone="America/New_York",
    # The closing cross prints at 16:00.
    close_time=time(16, 0),
    refresh_run="us",
    indices=("sp500", "ndx"),
)

GERMANY = Market(
    id="de",
    name="Xetra (Deutsche Börse)",
    short_name="Germany",
    country="Germany",
    region="europe",
    exchange="Xetra",
    ticker_suffix=".de",
    yahoo_suffix=".DE",
    currency="EUR",
    timezone="Europe/Berlin",
    # Continuous trading ends 17:30; the closing auction ends by ~17:35.
    close_time=time(17, 40),
    indices=("dax",),
)

FRANCE = Market(
    id="fr",
    name="Euronext Paris",
    short_name="France",
    country="France",
    region="europe",
    exchange="Euronext Paris",
    ticker_suffix=".pa",
    yahoo_suffix=".PA",
    currency="EUR",
    timezone="Europe/Paris",
    close_time=time(17, 40),
    indices=("cac40",),
)

NETHERLANDS = Market(
    id="nl",
    name="Euronext Amsterdam",
    short_name="Netherlands",
    country="Netherlands",
    region="europe",
    exchange="Euronext Amsterdam",
    ticker_suffix=".as",
    yahoo_suffix=".AS",
    currency="EUR",
    timezone="Europe/Amsterdam",
    close_time=time(17, 40),
    indices=("aex",),
)

UNITED_KINGDOM = Market(
    id="uk",
    name="London Stock Exchange",
    short_name="UK",
    country="United Kingdom",
    region="europe",
    exchange="LSE",
    ticker_suffix=".l",
    yahoo_suffix=".L",
    currency="GBp",
    timezone="Europe/London",
    # Continuous trading ends 16:30; the closing auction ends by ~16:35.
    close_time=time(16, 40),
    indices=("ftse100",),
)

#: Every market the app knows, in display order.
MARKETS: tuple[Market, ...] = (GPW, US, GERMANY, FRANCE, NETHERLANDS, UNITED_KINGDOM)

#: Display names of the indices the foreign universes are built from.
INDEX_NAMES: dict[str, str] = {
    "sp500": "S&P 500",
    "ndx": "NASDAQ-100",
    "dax": "DAX",
    "cac40": "CAC 40",
    "aex": "AEX",
    "ftse100": "FTSE 100",
}

_BY_ID: dict[str, Market] = {m.id: m for m in MARKETS}
_BY_SUFFIX: dict[str, Market] = {m.ticker_suffix: m for m in MARKETS if m.ticker_suffix}
_BY_YAHOO_SUFFIX: dict[str, Market] = {
    m.yahoo_suffix: m for m in MARKETS if m.yahoo_suffix
}

# A GPW code is what it has always been: letters and digits only.
_GPW_CODE = re.compile(r"[a-z0-9]{1,20}")
# A foreign exchange symbol may also carry a hyphen for a share class, the way
# Yahoo writes them ("BRK-B", "BT-A"). The overall length is capped separately
# (MAX_TICKER_LENGTH), suffix included.
_FOREIGN_CODE = re.compile(r"[a-z0-9][a-z0-9-]{0,18}")
# Yahoo's own GPW suffix is accepted as another spelling of a bare GPW code, so
# "KGH.WA" (how Yahoo and most foreign sites write it) resolves to "kgh".
_GPW_ALIAS_SUFFIX = ".wa"


def get_market(market_id: str | None) -> Market | None:
    """A market by id (case-insensitive), or ``None`` when unknown."""
    if not market_id:
        return None
    return _BY_ID.get(market_id.strip().casefold())


def normalize_ticker(raw: str | None) -> str | None:
    """The canonical (lower-case) ticker, or ``None`` when it is not one.

    Accepts a bare GPW code (``KGH``), Yahoo's spelling of it (``KGH.WA``) and
    a suffixed foreign ticker (``AAPL.US``, ``BT-A.L``). Anything else — an
    unknown suffix, stray characters, an over-long value — is rejected, so the
    result is always safe to use as a cache key or a database value.
    """
    if raw is None:
        return None
    value = raw.strip().casefold()
    if not value or len(value) > MAX_TICKER_LENGTH:
        return None
    head, dot, tail = value.rpartition(".")
    if not dot:
        return value if _GPW_CODE.fullmatch(value) else None
    suffix = dot + tail
    if suffix == _GPW_ALIAS_SUFFIX:
        return head if _GPW_CODE.fullmatch(head) else None
    if suffix not in _BY_SUFFIX or not _FOREIGN_CODE.fullmatch(head):
        return None
    return value


def market_of(ticker: str) -> Market:
    """The market a ticker belongs to — the GPW when it carries no suffix.

    Raises ``ValueError`` for a suffix no market uses. Pass a normalised
    ticker; the check is on its last dot-separated part only.
    """
    _, dot, tail = ticker.strip().casefold().rpartition(".")
    if not dot:
        return GPW
    market = _BY_SUFFIX.get(dot + tail)
    if market is None:
        raise ValueError(f"No market uses the suffix in ticker {ticker!r}.")
    return market


def ticker_symbol(ticker: str) -> str:
    """The exchange symbol without the app's market suffix ("aapl.us" → "AAPL")."""
    head, dot, tail = ticker.strip().rpartition(".")
    return (head if dot else tail).upper()


def yahoo_symbol(ticker: str) -> str:
    """The symbol Yahoo Finance knows the stock by.

    ``kgh`` → ``KGH.WA``, ``aapl.us`` → ``AAPL``, ``brk-b.us`` → ``BRK-B``,
    ``hsba.l`` → ``HSBA.L``. Raises ``ValueError`` for anything that is not a
    valid ticker.
    """
    normalized = normalize_ticker(ticker)
    if normalized is None:
        raise ValueError(f"Not a valid ticker: {ticker!r}.")
    return ticker_symbol(normalized) + market_of(normalized).yahoo_suffix


def market_for_yahoo_symbol(symbol: str) -> Market:
    """The market a Yahoo symbol trades on — US when it has no suffix.

    Raises ``ValueError`` for a Yahoo suffix this app does not track.
    """
    _, dot, tail = symbol.strip().upper().rpartition(".")
    if not dot:
        return US
    market = _BY_YAHOO_SUFFIX.get(dot + tail)
    if market is None:
        raise ValueError(f"No tracked market uses the Yahoo symbol {symbol!r}.")
    return market


def ticker_for(symbol: str, market: Market) -> str | None:
    """The app ticker for an exchange symbol on ``market``, or ``None``.

    ``("AAPL", US)`` → ``aapl.us``; ``("SAP.DE", GERMANY)`` → ``sap.de`` (a
    Yahoo suffix already on the symbol is not doubled); ``("KGH", GPW)`` →
    ``kgh``. A US share-class dot (``BRK.B``, the way index providers write it)
    becomes Yahoo's hyphen.
    """
    base = symbol.strip().casefold()
    yahoo_suffix = market.yahoo_suffix.casefold()
    if yahoo_suffix and base.endswith(yahoo_suffix):
        base = base[: -len(yahoo_suffix)]
    if market.id == US.id:
        base = base.replace(".", "-")
    return normalize_ticker(base + market.ticker_suffix)


# Unknown ids already warned about, so a bad setting is reported once rather
# than on every request that asks which markets are on.
_warned_unknown: set[str] = set()


def parse_market_ids(raw: str | None) -> tuple[str, ...]:
    """The known market ids in a comma-separated setting, in display order.

    ``all`` switches every market on. The GPW is always included. Unknown ids
    are ignored with a warning rather than stopping the app: a typo in a
    deployment setting should cost one market, not the whole site.
    """
    wanted = {part.strip().casefold() for part in (raw or "").split(",") if part.strip()}
    if "all" in wanted:
        return tuple(m.id for m in MARKETS)
    unknown = wanted - set(_BY_ID)
    for market_id in sorted(unknown - _warned_unknown):
        logger.warning(
            "Ignoring unknown market %r in STOCKPILOT_MARKETS (known: %s).",
            market_id,
            ", ".join(_BY_ID),
        )
        _warned_unknown.add(market_id)
    return tuple(m.id for m in MARKETS if m.id in wanted or m.id == GPW_ID)


def enabled_markets() -> tuple[Market, ...]:
    """The markets this deployment serves (``STOCKPILOT_MARKETS``)."""
    from app.config import settings  # deferred: config must stay importable alone

    ids = set(parse_market_ids(settings.markets))
    return tuple(m for m in MARKETS if m.id in ids)


def is_enabled(market_id: str) -> bool:
    """True when the market with this id is switched on."""
    return any(m.id == market_id for m in enabled_markets())


def major_currency(currency: str) -> str:
    """The currency whole amounts are stated in — "GBP" for a pence quote."""
    return "GBP" if currency == "GBp" else currency


def to_pln(amount: float, currency: str) -> float:
    """``amount`` of ``currency`` in approximate złoty.

    Raises ``ValueError`` for a currency without a rate — the company lists
    only admit currencies ``PLN_PER_UNIT`` knows, so this means bad data.
    """
    try:
        return amount * PLN_PER_UNIT[currency]
    except KeyError:
        raise ValueError(f"No złoty rate for currency {currency!r}.") from None


def quote_currency(company: GpwCompany) -> str:
    """The currency a company's prices are quoted in — its own, else its market's."""
    return company.currency or market_of(company.ticker).currency


@dataclass(frozen=True)
class RefreshRun:
    """One scheduled nightly data run and the markets it refreshes."""

    #: "europe" (the GPW and the European exchanges) or "us".
    id: str
    hour: int
    minute: int
    #: The zone the time is read in — the run follows that clock through
    #: daylight-saving changes.
    timezone: str
    market_ids: tuple[str, ...]

    @property
    def job_id(self) -> str:
        """The scheduler's job id ("daily_ingest" is the original, European run)."""
        return "daily_ingest" if self.id == "europe" else f"daily_ingest_{self.id}"

    @property
    def schedule(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d} {self.timezone}"


def refresh_runs() -> list[RefreshRun]:
    """The nightly runs this deployment needs, one per group of served markets.

    Europe and the GPW at ``STOCKPILOT_INGEST_HOUR:MINUTE`` Warsaw time (every
    European exchange has closed by 17:35); the US, when served, at
    ``STOCKPILOT_US_INGEST_HOUR:MINUTE`` New York time — after its own close,
    whatever the transatlantic daylight-saving gap is that week.
    """
    from app.config import settings  # deferred: config must stay importable alone

    served = enabled_markets()
    runs: list[RefreshRun] = []
    for run_id, hour, minute, zone in (
        ("europe", settings.ingest_hour, settings.ingest_minute, "Europe/Warsaw"),
        ("us", settings.us_ingest_hour, settings.us_ingest_minute, "America/New_York"),
    ):
        ids = tuple(m.id for m in served if m.refresh_run == run_id)
        if ids:
            runs.append(RefreshRun(run_id, hour, minute, zone, ids))
    return runs


def below_liquidity_floor(median_turnover: float, currency: str) -> bool:
    """True when a stock trades too little to rank (median turnover < 100k PLN).

    ``median_turnover`` is price × volume in the stock's quote ``currency``
    (pence for most of London), as ``app.analysis.statistics.median_turnover``
    returns it.
    """
    return to_pln(median_turnover, currency) < MIN_MEDIAN_TURNOVER_PLN


def below_market_cap_floor(market_cap: float | None, currency: str) -> bool:
    """True when a company is known to be too small to rank (< 100M PLN).

    Only a *known* capitalisation can fail — missing metadata never hides a
    company. ``market_cap`` is in the major unit of the quote ``currency``, as
    Yahoo reports it: pounds, not pence, for a London line quoted in pence.
    """
    if market_cap is None:
        return False
    return to_pln(market_cap, major_currency(currency)) < MIN_MARKET_CAP_PLN
