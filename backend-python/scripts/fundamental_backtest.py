"""Read-only audit and ANNUAL-PROXY backtest of fundamentals, never a PIT claim.

Outputs and immutable downloaded evidence live under agent/, not application DB.
Run from backend-python: python -m scripts.fundamental_backtest --prepare|--download|--analyze
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import text

from app.analysis.fundamentals import financial_profile
from app.config import Settings
from app.db.base import build_engine
from app.markets import yahoo_symbol
from app.services.gpw_company_service import GpwCompanyService

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "agent/fundamental-backtest-2026-10-30"
MARKETS = ("us", "fr", "gpw")
END = date(2026, 10, 30)
SCHEMA = 2


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


async def audit():
    settings = Settings()
    if not settings.database_url:
        return {"database_configured": False}, {}
    engine = build_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            output = {}
            queries = {
                "price_coverage": """SELECT CASE WHEN ticker LIKE '%.us' THEN 'us'
                    WHEN ticker LIKE '%.pa' THEN 'fr' WHEN ticker NOT LIKE '%.%' THEN 'gpw'
                    ELSE 'other' END market, count(DISTINCT ticker) companies, min(date) first,
                    max(date) last, count(*) bars FROM daily_quotes GROUP BY 1""",
                "financial_observations": """SELECT kind,count(*) n,count(DISTINCT ticker)
                    companies,min(observed_at) first,max(observed_at) last
                    FROM financial_observations GROUP BY kind""",
                "score_observations": """SELECT market,model_version,count(*) n,
                    count(DISTINCT ticker) companies,min(recorded_at) first,max(recorded_at) last
                    FROM long_term_snapshots GROUP BY 1,2""",
                "extended_data_column": """SELECT column_name FROM information_schema.columns
                    WHERE table_name='company_fundamentals'
                    AND column_name='fundamental_details'""",
            }
            for key, query in queries.items():
                output[key] = [dict(row) for row in (await conn.execute(text(query))).mappings()]
            currencies = dict(
                (
                    await conn.execute(
                        text("SELECT ticker,financial_currency FROM company_fundamentals")
                    )
                ).all()
            )
            return output, currencies
    finally:
        await engine.dispose()


def prepare():
    if (OUT / "specification.json").exists():
        raise RuntimeError(
            "Specification already frozen; reuse it rather than select after results."
        )
    coverage, currencies = asyncio.run(audit())
    service = GpwCompanyService()
    selected = []
    for market in MARKETS:
        sectors = defaultdict(list)
        for company in service.get_companies(market):
            sectors[company.sector or "Unknown"].append(company)
        for group in sectors.values():
            group.sort(key=lambda c: (-(c.market_cap or 0), c.ticker))
        # Deterministic sector round-robin, never chosen using a realized return.
        chosen = []
        while sectors and len(chosen) < 100:
            for sector in sorted(list(sectors)):
                chosen.append(sectors[sector].pop(0))
                if not sectors[sector]:
                    del sectors[sector]
                if len(chosen) == 100:
                    break
        for company in sorted(chosen, key=lambda c: c.ticker):
            row = company.model_dump(
                include={
                    "ticker",
                    "name",
                    "market",
                    "sector",
                    "industry",
                    "currency",
                    "market_cap",
                }
            )
            row.update(
                symbol=yahoo_symbol(company.ticker),
                profile=financial_profile(company),
                financial_currency=currencies.get(company.ticker),
            )
            selected.append(row)
    save(OUT / "database_audit.json", coverage)
    save(OUT / "universe.json", selected)
    source = ROOT / "backend-python/app/analysis/fundamentals.py"
    save(
        OUT / "specification.json",
        {
            "prepared_at": datetime.now(UTC).isoformat(),
            "kind": "EXPLORATORY ANNUAL PROXY; NOT POINT-IN-TIME VALIDATION OF PRODUCTION MODEL",
            "markets": MARKETS,
            "companies": len(selected),
            "sample_limit_each_market": 100,
            "selection": (
                "Current app universe; sector round-robin, current cap descending within sector"
            ),
            "formation_dates": [f"{year}-06-30" for year in range(2023, 2027)],
            "horizons_months": [6, 12, 24, 36],
            "publication_lags_days": [180, 270],
            "primary_lag_days": 180,
            "end_exclusive": END.isoformat(),
            "primary": "Corporate profiles; overall top versus bottom quartile; 12 calendar months",
            "secondary": (
                "6/24/36 months; score >=70 or <=30; each pillar; financial profiles separate"
            ),
            "benchmark": (
                "Equal-weight stocks with the same available score, market, profile and cohort"
            ),
            "execution": (
                "First traded adjusted open after formation, first traded adjusted close at horizon"
            ),
            "cost_bps_each_side": 25,
            "bootstrap_seed": 20261030,
            "bootstrap_replicates": 2000,
            "production_scorer_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "warnings": [
                "No historical publication timestamps; fiscal-end lag is an assumption",
                "Downloaded statements can include later restatements",
                "Current survivors and current metadata; no historical index membership/delistings",
                "Annual profitability/growth/cash flow replace the production TTM/quarterly inputs",
                "Reported average diluted shares proxy historical market capitalization",
                "Current reporting currency is an assumption for historical statement units",
                "No weight tuning or production changes; overlapping holding periods are dependent",
            ],
        },
    )
    print(
        json.dumps(
            {
                "prepared": len(selected),
                "by_market": {m: sum(c["market"] == m for c in selected) for m in MARKETS},
            }
        ),
        flush=True,
    )


def cache_path(symbol):
    return OUT / "raw" / f"{symbol.replace('.', '_').replace('/', '_')}.json"


def download_one(company):
    import yfinance as yf

    path = cache_path(company["symbol"])
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("schema") == SCHEMA and cached.get("prices", {}).get("data"):
            return {
                "symbol": company["symbol"],
                "cached": True,
                "income_periods": len(cached.get("income_stmt", {}).get("columns", [])),
            }
    ticker = yf.Ticker(company["symbol"])
    raw = {
        "schema": SCHEMA,
        "symbol": company["symbol"],
        "fetched_at": datetime.now(UTC).isoformat(),
        "errors": {},
    }
    summary = {"symbol": company["symbol"]}
    for key in ("income_stmt", "balance_sheet", "cashflow"):
        try:
            frame = getattr(ticker, key)
            raw[key] = json.loads(frame.to_json(orient="split", date_format="iso"))
            summary[key] = len(frame.columns)
        except Exception as exc:
            raw["errors"][key] = type(exc).__name__
    try:
        prices = ticker.history(
            start="2018-01-01",
            end=END.isoformat(),
            auto_adjust=False,
            actions=True,
            raise_errors=True,
        )
        raw["prices"] = json.loads(prices.to_json(orient="split", date_format="iso"))
        summary["price_rows"] = len(prices)
    except Exception as exc:
        raw["errors"]["prices"] = type(exc).__name__
    save(path, raw)
    return summary


def download():
    import yfinance as yf

    (OUT / "yf-cache").mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(OUT / "yf-cache"))
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    companies = json.loads((OUT / "universe.json").read_text(encoding="utf-8"))
    completed, started = [], time.monotonic()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(download_one, c): c for c in companies}
        for future in as_completed(futures):
            try:
                completed.append(future.result())
            except Exception as exc:
                completed.append({"symbol": futures[future]["symbol"], "error": type(exc).__name__})
            if len(completed) % 10 == 0 or len(completed) == len(companies):
                print(
                    json.dumps(
                        {
                            "downloaded": len(completed),
                            "total": len(companies),
                            "seconds": round(time.monotonic() - started),
                            "latest": completed[-1],
                        }
                    ),
                    flush=True,
                )
    save(OUT / "downloads.json", completed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.download:
        download()
    if args.analyze:
        from scripts.fundamental_backtest_analysis import analyze

        analyze(OUT)
