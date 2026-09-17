"""Build the company lists for the non-GPW markets.

Writes ``app/data/markets/<market>.json`` — the companies the scanner tracks on
each foreign market — from the members of that market's indices (see
``agent/MULTI-MARKET-PLAN.md``):

    us  S&P 500 + NASDAQ-100     de  DAX 40      fr  CAC 40
    nl  AEX                      uk  FTSE 100

Run it from ``backend-python/`` when index members change (the indices are
rebalanced quarterly)::

    .venv/Scripts/python.exe -m scripts.build_market_universe           # all
    .venv/Scripts/python.exe -m scripts.build_market_universe us uk     # some
    .venv/Scripts/python.exe -m scripts.build_market_universe us --retry-rejected

For each member the script asks Yahoo Finance for the company profile and the
last few weeks of daily bars, and keeps the company only when it has **traded
recently** (bars with volume) and has a **name**. Unlike the GPW list, a sector
is not required: index membership already proves the company is real, and
Yahoo leaves the sector blank for some genuine members (3i Group, Michelin,
the investment trusts in the FTSE 100). The quote currency must be one the app
can convert to złoty (``app.markets.PLN_PER_UNIT``) — London quotes some lines
in dollars or euros rather than pence, and each company's own currency is
recorded. Everything left out is listed under ``rejected`` in the written
file, with the reason, so a rebuild can be reviewed rather than trusted.

Yahoo rate-limits bursts ("Too Many Requests"). The script backs off and
retries, and a member it still could not check is listed as rejected with that
reason; ``--retry-rejected`` then re-checks just those, keeping the rest.

Where the member lists come from:

* S&P 500, DAX, CAC 40, AEX, FTSE 100 — the constituents table on each index's
  English Wikipedia page;
* NASDAQ-100 — Nasdaq's own public list (Wikipedia stopped listing it).

A market whose member list cannot be downloaded is left untouched rather than
overwritten with an empty file. Parsing uses BeautifulSoup, which ships with
yfinance.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from app.markets import (
    FRANCE,
    GERMANY,
    MARKETS,
    NETHERLANDS,
    PLN_PER_UNIT,
    UNITED_KINGDOM,
    US,
    Market,
    get_market,
    ticker_for,
    yahoo_symbol,
)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "markets"

# Wikipedia asks automated clients to identify themselves; the project's public
# site is the contact point.
_WIKI_HEADERS = {"User-Agent": "StockPilot-universe-builder/1.0 (+https://stocksignal.pl)"}
# Nasdaq's API answers browsers only.
_NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}

WIKIPEDIA = {
    "sp500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol"),
    "dax": ("https://en.wikipedia.org/wiki/DAX", "Ticker"),
    "cac40": ("https://en.wikipedia.org/wiki/CAC_40", "Ticker"),
    "aex": ("https://en.wikipedia.org/wiki/AEX_index", "Ticker"),
    "ftse100": ("https://en.wikipedia.org/wiki/FTSE_100_Index", "Ticker"),
}
NASDAQ_100_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"

# How many members an index is expected to have, give or take a share class.
# A download far below this is a changed page layout, not a smaller index.
EXPECTED_SIZE = {"sp500": 500, "ndx": 100, "dax": 40, "cac40": 40, "aex": 25, "ftse100": 100}

# Yahoo's exchange codes, as the reader knows them.
EXCHANGE_NAMES = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "ASE": "NYSE American",
    "PCX": "NYSE Arca",
    "BTS": "Cboe BZX",
    "GER": "Xetra",
    "PAR": "Euronext Paris",
    "AMS": "Euronext Amsterdam",
    "LSE": "LSE",
}

# A member must have traded this recently, on at least this many sessions.
RECENT_DAYS = 21
MIN_RECENT_BARS = 5

_WORKERS = 3
_ATTEMPTS = 4
# Yahoo answers bursts with "Too Many Requests" (518 US lookups hit it on
# 2026-09-16); those need a real pause, other errors only a short one.
_RATE_LIMIT_WAIT_SECONDS = (30, 60, 120)
_ERROR_WAIT_SECONDS = (5, 10, 15)


@dataclass
class Member:
    """One index member as the source lists it."""

    symbol: str
    index_id: str


@dataclass
class Outcome:
    """What verifying one symbol produced: a company, or a reason it was left out."""

    symbol: str
    indices: list[str]
    company: dict | None = None
    reason: str | None = None


@dataclass
class MarketBuild:
    market: Market
    members: dict[str, list[str]] = field(default_factory=dict)  # ticker → indices
    unmapped: list[dict] = field(default_factory=list)


# ── Member lists ──────────────────────────────────────────────────────────────


def wikipedia_members(index_id: str, client: httpx.Client) -> list[Member]:
    """Symbols from the ``constituents`` table of an index's Wikipedia page."""
    url, column = WIKIPEDIA[index_id]
    html = client.get(url, headers=_WIKI_HEADERS).raise_for_status().text
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="constituents") or soup.find("table", class_="wikitable")
    if table is None:
        raise RuntimeError(f"{index_id}: no constituents table at {url}")

    rows = table.find_all("tr")
    headers = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
    try:
        position = headers.index(column)
    except ValueError as exc:
        raise RuntimeError(f"{index_id}: no {column!r} column in {headers}") from exc

    members: list[Member] = []
    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) <= position:
            continue
        symbol = cells[position].get_text(" ", strip=True).split(" ")[0]
        if symbol:
            members.append(Member(symbol=symbol, index_id=index_id))
    return members


def nasdaq_100_members(client: httpx.Client, attempts: int = 6) -> list[Member]:
    """The NASDAQ-100 from Nasdaq's own public list.

    The service intermittently answers 200 with no data and "Error while
    calling vendor" (seen 2026-09-16), so an empty answer is retried.
    """
    rows: list[dict] = []
    for attempt in range(1, attempts + 1):
        payload = client.get(NASDAQ_100_URL, headers=_NASDAQ_HEADERS).raise_for_status().json()
        rows = ((payload.get("data") or {}).get("data") or {}).get("rows") or []
        if rows:
            break
        if attempt < attempts:
            time.sleep(10 * attempt)
    return [Member(symbol=r["symbol"], index_id="ndx") for r in rows if r.get("symbol")]


def fetch_members(index_id: str, client: httpx.Client) -> list[Member]:
    members = (
        nasdaq_100_members(client) if index_id == "ndx" else wikipedia_members(index_id, client)
    )
    if len(members) < EXPECTED_SIZE[index_id] * 0.9:
        raise RuntimeError(
            f"{index_id}: only {len(members)} members found "
            f"(expected ~{EXPECTED_SIZE[index_id]}) — the source layout may have changed."
        )
    return members


def clean_symbol(symbol: str, market: Market) -> str:
    """Undo the source's spelling where it differs from Yahoo's.

    London symbols on Wikipedia carry trailing dots ("BP.") and share-class
    dots ("BT.A"); Yahoo writes "BP" and "BT-A" before its own ".L".

    A member quoted with ANOTHER tracked market's Yahoo suffix — the DAX page
    lists Airbus as "AIR.PA", the CAC 40 page ArcelorMittal as "MT.AS" — is
    looked for on this market under the same symbol instead: the index is
    calculated from the local line, and verification drops it if that line
    does not exist.
    """
    cleaned = symbol.strip().upper()
    base, dot, suffix = cleaned.rpartition(".")
    foreign = {m.yahoo_suffix for m in MARKETS if m.yahoo_suffix and m.id != market.id}
    if dot and "." + suffix in foreign:
        cleaned = base
    if market.id == UNITED_KINGDOM.id:
        cleaned = cleaned.rstrip(".").replace(".", "-")
    return cleaned


# ── Verification on Yahoo ─────────────────────────────────────────────────────


def _usable(value: object) -> object | None:
    return None if value in (None, "", "None", "N/A") else value


def _is_rate_limit(exc: Exception) -> bool:
    return "RateLimit" in type(exc).__name__ or "Too Many Requests" in str(exc)


def verify(ticker: str, indices: list[str], market: Market) -> Outcome:
    """Ask Yahoo for the profile and recent bars of one stock."""
    import yfinance as yf  # deferred: heavy import

    symbol = yahoo_symbol(ticker)
    last_error: Exception | None = None
    for attempt in range(_ATTEMPTS):
        try:
            handle = yf.Ticker(symbol)
            info = handle.info or {}
            bars = handle.history(
                start=(date.today() - timedelta(days=RECENT_DAYS)).isoformat(),
                auto_adjust=True,
                actions=False,
                raise_errors=False,
            )
            break
        except Exception as exc:  # noqa: BLE001 — retried, then reported
            last_error = exc
            if attempt + 1 < _ATTEMPTS:
                waits = _RATE_LIMIT_WAIT_SECONDS if _is_rate_limit(exc) else _ERROR_WAIT_SECONDS
                time.sleep(waits[min(attempt, len(waits) - 1)])
    else:
        return Outcome(symbol, indices, reason=f"Yahoo request failed: {last_error}")

    traded = 0 if bars is None or bars.empty else int((bars["Volume"] > 0).sum())
    if traded < MIN_RECENT_BARS:
        return Outcome(
            symbol, indices, reason=f"only {traded} traded sessions in {RECENT_DAYS} days"
        )

    name = _usable(info.get("longName")) or _usable(info.get("shortName"))
    if not name:
        return Outcome(symbol, indices, reason="no company name on Yahoo")

    currency = _usable(info.get("currency"))
    if currency not in PLN_PER_UNIT:
        return Outcome(
            symbol, indices, reason=f"quoted in {currency}, which the app cannot convert"
        )

    exchange_code = _usable(info.get("exchange"))
    exchange = EXCHANGE_NAMES.get(str(exchange_code)) or _usable(info.get("fullExchangeName"))
    company = {
        "ticker": ticker,
        "symbol": symbol,
        "name": str(name).strip(),
        "sector": _usable(info.get("sector")),
        "industry": _usable(info.get("industry")),
        "country": _usable(info.get("country")),
        "exchange": exchange or market.exchange,
        "currency": currency,
        # Yahoo answers 0 when it does not know (Michelin, 2026-09); a zero
        # would fail the market-cap floor, so it is stored as unknown.
        "marketCap": _usable(info.get("marketCap")) or None,
        "employees": _usable(info.get("fullTimeEmployees")),
        "website": _usable(info.get("website")),
        "description": _usable(info.get("longBusinessSummary")),
        "indices": sorted(indices),
    }
    return Outcome(symbol, indices, company=company)


# ── Building one market ───────────────────────────────────────────────────────


def collect_members(market: Market, client: httpx.Client) -> MarketBuild:
    build = MarketBuild(market=market)
    for index_id in market.indices:
        for member in fetch_members(index_id, client):
            symbol = clean_symbol(member.symbol, market)
            ticker = ticker_for(symbol, market)
            if ticker is None:
                build.unmapped.append(
                    {
                        "symbol": member.symbol,
                        "indices": [index_id],
                        "reason": f"not a {market.short_name} symbol",
                    }
                )
                continue
            build.members.setdefault(ticker, [])
            if index_id not in build.members[ticker]:
                build.members[ticker].append(index_id)
    return build


def _verify_all(
    members: dict[str, list[str]], market: Market, log: Callable[[str], None]
) -> list[Outcome]:
    outcomes: list[Outcome] = []
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = [
            pool.submit(verify, ticker, indices, market) for ticker, indices in members.items()
        ]
        for done, future in enumerate(futures, start=1):
            outcomes.append(future.result())
            if done % 50 == 0:
                log(f"[{market.id}] verified {done}/{len(futures)}")
    return outcomes


def _rejection(outcome: Outcome) -> dict:
    return {"symbol": outcome.symbol, "indices": sorted(outcome.indices), "reason": outcome.reason}


def _payload(
    market: Market,
    companies: list[dict],
    rejected: list[dict],
    generated_at: str | None = None,
) -> dict:
    payload = {
        "market": market.id,
        "name": market.name,
        "generatedAt": generated_at or date.today().isoformat(),
        "sources": {
            index_id: (NASDAQ_100_URL if index_id == "ndx" else WIKIPEDIA[index_id][0])
            for index_id in market.indices
        },
        "verification": (
            f"Each company returned at least {MIN_RECENT_BARS} traded daily bars in "
            f"the {RECENT_DAYS} days before it was verified and a company name "
            "from Yahoo Finance, with prices quoted in a currency the app converts "
            f"({', '.join(PLN_PER_UNIT)})."
        ),
        "companies": sorted(companies, key=lambda c: c["ticker"]),
        "rejected": sorted(rejected, key=lambda r: r["symbol"]),
    }
    if generated_at is not None:
        payload["updatedAt"] = date.today().isoformat()
    return payload


def build_market(
    market: Market,
    client: httpx.Client,
    log: Callable[[str], None] = print,
) -> dict:
    """Download the member lists and verify every member."""
    build = collect_members(market, client)
    log(f"[{market.id}] {len(build.members)} members to verify")
    outcomes = _verify_all(build.members, market, log)
    companies = [o.company for o in outcomes if o.company is not None]
    rejected = build.unmapped + [_rejection(o) for o in outcomes if o.company is None]
    return _payload(market, companies, rejected)


def retry_rejected(
    market: Market,
    previous: dict,
    log: Callable[[str], None] = print,
) -> dict:
    """Re-verify only what an earlier build left out; keep everything else.

    For a run that Yahoo cut short with "Too Many Requests": the members it
    could not check are listed under ``rejected``, and asking again for just
    those is minutes instead of a full rebuild. Stored symbols are Yahoo's
    ("HSBA.L") for verified members and the source's ("AIR.PA", "BT.A") for
    unmapped ones, so both spellings are tried.
    """
    companies = {c["ticker"]: c for c in previous.get("companies", [])}
    members: dict[str, list[str]] = {}
    still_rejected: list[dict] = []
    for item in previous.get("rejected", []):
        symbol = item["symbol"]
        ticker = ticker_for(symbol, market) or ticker_for(clean_symbol(symbol, market), market)
        if ticker is None or ticker in companies:
            if ticker is None:
                still_rejected.append(item)
            continue
        indices = members.setdefault(ticker, [])
        indices.extend(ix for ix in item.get("indices", []) if ix not in indices)

    log(f"[{market.id}] re-verifying {len(members)} previously rejected members")
    for outcome in _verify_all(members, market, log):
        if outcome.company is not None:
            companies[outcome.company["ticker"]] = outcome.company
        else:
            still_rejected.append(_rejection(outcome))
    return _payload(
        market,
        list(companies.values()),
        still_rejected,
        generated_at=previous.get("generatedAt") or date.today().isoformat(),
    )


def write_market(payload: dict, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{payload['market']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ── Entry point ───────────────────────────────────────────────────────────────

FOREIGN_MARKETS = (US, GERMANY, FRANCE, NETHERLANDS, UNITED_KINGDOM)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    everything = ", ".join(m.id for m in FOREIGN_MARKETS)
    parser.add_argument(
        "markets",
        nargs="*",
        help=f"market ids to rebuild (default: all of {everything})",
    )
    parser.add_argument(
        "--retry-rejected",
        action="store_true",
        help="re-verify only the members an earlier build left out, keeping the rest",
    )
    args = parser.parse_args(argv)

    chosen: list[Market] = []
    for market_id in args.markets or [m.id for m in FOREIGN_MARKETS]:
        market = get_market(market_id)
        if market is None or not market.indices:
            known = ", ".join(m.id for m in MARKETS if m.indices)
            parser.error(f"unknown or non-index market {market_id!r} (choose from {known})")
        chosen.append(market)

    failed = False
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        for market in chosen:
            try:
                if args.retry_rejected:
                    existing = OUTPUT_DIR / f"{market.id}.json"
                    previous = json.loads(existing.read_text(encoding="utf-8"))
                    payload = retry_rejected(market, previous)
                else:
                    payload = build_market(market, client)
            except Exception as exc:  # noqa: BLE001 — one market must not stop the rest
                print(f"[{market.id}] NOT rebuilt, existing file left as it was: {exc}")
                failed = True
                continue
            path = write_market(payload)
            print(
                f"[{market.id}] wrote {len(payload['companies'])} companies to {path} "
                f"({len(payload['rejected'])} rejected)"
            )
            for item in payload["rejected"]:
                print(f"    - {item['symbol']} ({', '.join(item['indices'])}): {item['reason']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
