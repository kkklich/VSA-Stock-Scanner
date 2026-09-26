"""Run the owner's VSA program (VSA V4) on a stock the app has stored.

The program (``app/analysis/vsa4``) was supplied as a command-line tool that
reads a CSV you prepare and writes four audit files. This script does the
preparing: it takes a ticker's bars from the app's database, writes them as
the program's CSV, and runs the program's own CLI on it — so every bar-by-bar
flag, reason, stop and trade can be inspected exactly as the program sees it.

Run it from ``backend-python/`` (PostgreSQL must be running)::

    .venv/Scripts/python.exe -m scripts.vsa4_run kgh
    .venv/Scripts/python.exe -m scripts.vsa4_run kgh --years 3 --output results/kgh
    .venv/Scripts/python.exe -m scripts.vsa4_run aapl.us --config my_config.json

Writes to ``--output`` (default ``vsa4_results/<ticker>``):

    bars.csv      the input handed to the program (timestamp,open,...,volume)
    signals.csv   every bar: features, candidate_* flags, reasons, confirmations
    trades.csv    the simulated trades
    equity.csv    the account after every session
    summary.json  the statistics, the full configuration, the input's SHA-256

Unlike the app's stock page, this is the program exactly as shipped: its own
defaults (1 bp commission and slippage, both long and short setups) unless a
``--config`` JSON says otherwise — see the program's README for every field.
The one adaptation is the same as the app's: ``min_tick`` is sized to the
stock's price when the config does not set it (``adapter.tick_size``).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from app.analysis.vsa4.adapter import tick_size, to_engine_bars
from app.analysis.vsa4.cli import run
from app.analysis.vsa4.engine import Config, VSAError
from app.config import settings
from app.db.base import build_engine, build_session_factory
from app.db.repository import PostgresQuoteRepository
from app.markets import normalize_ticker
from app.models import StooqDailyQuote


async def _load(ticker: str, years: float) -> list[StooqDailyQuote]:
    engine = build_engine(settings.database_url)
    try:
        repo = PostgresQuoteRepository(build_session_factory(engine))
        start = date.today() - timedelta(days=round(years * 365.25))
        return await repo.get_quotes(ticker, start, None)
    finally:
        await engine.dispose()


def _write_bars(path: Path, quotes: list[StooqDailyQuote]) -> float:
    """Write the program's input CSV; returns the last close."""
    bars, _ = to_engine_bars(quotes)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for b in bars:
            writer.writerow([b.timestamp, b.open, b.high, b.low, b.close, b.volume])
    return bars[-1].close if bars else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the VSA program (VSA V4) on a stored ticker and write its audit files."
    )
    parser.add_argument("ticker", help="kgh, pko, aapl.us, sap.de, ...")
    parser.add_argument("--years", type=float, default=5.0, help="history to use (default 5)")
    parser.add_argument("--output", help="folder for the results (default vsa4_results/<ticker>)")
    parser.add_argument("--config", help="JSON overriding the program's defaults")
    args = parser.parse_args(argv)

    ticker = normalize_ticker(args.ticker)
    if ticker is None:
        print(f"Not a ticker: {args.ticker!r}", file=sys.stderr)
        return 2
    if not settings.database_url:
        print("No database configured (STOCKPILOT_DATABASE_URL).", file=sys.stderr)
        return 2

    quotes = asyncio.run(_load(ticker, args.years))
    if not quotes:
        print(f"No stored bars for {ticker}. Open its stock page once to fetch them.",
              file=sys.stderr)
        return 1

    out = Path(args.output or f"vsa4_results/{ticker}")
    out.mkdir(parents=True, exist_ok=True)
    last_close = _write_bars(out / "bars.csv", quotes)

    try:
        overrides = (
            json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
        )
        overrides.setdefault("min_tick", tick_size(last_close))
        config = Config.from_mapping(overrides)
        protected = [Path(args.config)] if args.config else []
        summary = run(out / "bars.csv", out, config, protected_inputs=protected)
    except (VSAError, OSError, ValueError) as exc:
        print(f"VSA program error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({
        "ticker": ticker,
        "bars": summary["bar_count"],
        "from": summary["first_timestamp"],
        "to": summary["last_timestamp"],
        "long_setups": summary["long_setup_confirmations"],
        "short_setups": summary["short_setup_confirmations"],
        "closed_trades": summary["closed_trades"],
        "open_trades": summary["open_trades"],
        "win_rate_pct": summary["win_rate_pct"],
        "final_equity": summary["final_equity"],
        "results": str(out.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
