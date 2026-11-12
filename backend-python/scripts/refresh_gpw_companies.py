"""Add Main Market companies from the GPW's official company directory.

Source: https://www.gpw.pl/spolki?limit=1000&offset=0
The directory supplies registered names and exchange tickers. A Yahoo profile,
sector classification or recent trading history is not required for inclusion.
Existing metadata and historical symbols remain unchanged for portfolio imports.

Run from backend-python/::

    .venv/Scripts/python.exe -m scripts.refresh_gpw_companies
    .venv/Scripts/python.exe -m scripts.refresh_gpw_companies --source-html saved.html

Only the official Main Market table is parsed; NewConnect is a separate directory.
The CLI rejects downloads with fewer than 300 distinct companies before writing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from app.markets import GPW_ID, market_of, normalize_ticker

GPW_COMPANIES_URL = "https://www.gpw.pl/spolki?limit=1000&offset=0"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "app" / "data" / "gpw-companies.json"
MIN_GPW_COMPANIES = 300


def _ticker(value):
    ticker = normalize_ticker(value) if isinstance(value, str) else None
    if ticker is None or market_of(ticker).id != GPW_ID or "." in value:
        raise ValueError(f"Invalid GPW ticker: {value!r}")
    return ticker


def parse_gpw_companies(html: str) -> list[dict]:
    """Read names and ticker spans from the official, server-rendered table."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("table#lista-spolek tbody#search-result")
    if body is None:
        raise ValueError("The official GPW company table was not found")
    companies = {}
    for row in body.select("tr"):
        name_element = row.select_one('a[href*="spolka?isin="] strong.name')
        if name_element is None:
            raise ValueError("A GPW company row has no company name or profile link")
        spans = name_element.select("span.grey")
        if len(spans) != 1:
            raise ValueError("A GPW company row has no unambiguous ticker")
        symbol_text = spans[0].get_text(" ", strip=True)
        match = re.fullmatch(r"\(([A-Z0-9]{1,8})\)", symbol_text)
        if match is None:
            raise ValueError(f"Invalid GPW ticker label: {symbol_text!r}")
        ticker = _ticker(match[1])
        full_name = " ".join(name_element.get_text(" ", strip=True).split())
        if not full_name.endswith(symbol_text):
            raise ValueError("The GPW ticker is not at the end of the company name")
        name = full_name[: -len(symbol_text)].strip()
        if not name:
            raise ValueError(f"The GPW company {ticker!r} has an empty name")
        company = {"ticker": ticker, "name": name, "sector": None}
        previous = companies.get(ticker)
        if previous is not None and previous != company:
            raise ValueError(f"Conflicting GPW directory entries for {ticker!r}")
        companies[ticker] = company
    return [companies[ticker] for ticker in sorted(companies)]


def merge_companies(existing: list[dict], official: list[dict]) -> list[dict]:
    """Add directory members while preserving every existing entry and field."""
    if not isinstance(existing, list) or not isinstance(official, list):
        raise ValueError("Company data must be a list")
    merged = {}
    for company in existing:
        if not isinstance(company, dict):
            raise ValueError("Every existing company must be an object")
        ticker = _ticker(company.get("ticker"))
        if ticker in merged:
            raise ValueError(f"Duplicate existing GPW ticker: {ticker!r}")
        merged[ticker] = dict(company)
    incoming = {}
    for company in official:
        if not isinstance(company, dict):
            raise ValueError("Every official company must be an object")
        ticker = _ticker(company.get("ticker"))
        if ticker in incoming and incoming[ticker] != company:
            raise ValueError(f"Conflicting GPW directory entries for {ticker!r}")
        incoming[ticker] = company
        if ticker not in merged:
            merged[ticker] = {"ticker": ticker, "name": company["name"], "sector": None}
    return [merged[ticker] for ticker in sorted(merged)]


def refresh_companies(*, output: Path, source_html: Path | None = None) -> tuple[int, int]:
    if source_html is not None:
        html = source_html.read_text(encoding="utf-8-sig")
    else:
        response = httpx.get(
            GPW_COMPANIES_URL,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "StockPilot-universe-builder/1.0 (+https://stocksignal.pl)"},
        )
        response.raise_for_status()
        html = response.text
    official = parse_gpw_companies(html)
    if len(official) < MIN_GPW_COMPANIES:
        raise ValueError(
            f"The GPW directory returned only {len(official)} distinct companies; "
            f"at least {MIN_GPW_COMPANIES} are required. The existing file was not changed."
        )
    existing = json.loads(output.read_text(encoding="utf-8-sig")) if output.exists() else []
    merged = merge_companies(existing, official)
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(text)
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(merged) - len(existing), len(merged)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-html", type=Path, help="Use a saved official GPW directory page")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Company JSON to merge into"
    )
    args = parser.parse_args(argv)
    try:
        added, count = refresh_companies(output=args.output, source_html=args.source_html)
    except (OSError, ValueError, httpx.HTTPError) as exc:
        print(f"GPW refresh failed: {exc}", file=sys.stderr)
        return 1
    print(f"Added {added} GPW companies. Saved {count} companies to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
