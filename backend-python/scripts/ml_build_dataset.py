"""Build the AI layer's training datasets from the stored bars — plan §19.1.

Reads the app's database (never downloads), computes every feature and label
(``app/ml``), and writes two datasets under ``backend-python/ml_data/``:

    job1-<markets>.csv.gz   one row per firing of VSA V4, Weinstein, Glinicki V1
                            and Volume Breakout (the signal filter, Job 1)
    job2-<markets>.csv.gz   every 5th session of every stock (the learned
                            Combined score, Job 2)

each with a ``.meta.json`` naming exactly what went in. Run from
``backend-python/`` with PostgreSQL running::

    .venv/Scripts/python.exe -m scripts.ml_build_dataset
    .venv/Scripts/python.exe -m scripts.ml_build_dataset --markets all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from app.config import settings
from app.ml import ML_DATA_DIR
from app.ml.data_access import load_stock_inputs, parse_markets
from app.ml.dataset import (
    HORIZONS,
    JOB1_METHODS,
    JOB2_EVERY,
    build_panel,
    job1_rows,
    job2_rows,
    write_dataset,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AI layer's datasets (Phase 0).")
    parser.add_argument("--markets", default="gpw", help="gpw (default), a list, or all")
    parser.add_argument("--every", type=int, default=JOB2_EVERY,
                        help=f"Job 2 keeps every Nth session (default {JOB2_EVERY})")
    args = parser.parse_args(argv)
    if not settings.database_url:
        print("No database configured (STOCKPILOT_DATABASE_URL).", file=sys.stderr)
        return 2

    markets = parse_markets(args.markets)
    started = time.perf_counter()
    stocks = asyncio.run(load_stock_inputs(markets))
    print(f"Loaded {len(stocks)} companies with stored bars "
          f"({sum(len(s.bars) for s in stocks):,} bars) in {time.perf_counter() - started:.0f}s.")

    def progress(i: int, total: int, ticker: str) -> None:
        if i % 25 == 0 or i == total:
            print(f"  features {i}/{total} ({ticker})")

    panel = build_panel(stocks, HORIZONS, progress=progress)
    if panel.empty:
        print("Nothing to build.", file=sys.stderr)
        return 1
    tag = "-".join(markets) if len(markets) < 6 else "all"
    meta = {"markets": markets, "horizons": list(HORIZONS), "companies": len(stocks)}
    job1 = job1_rows(panel, JOB1_METHODS)
    job2 = job2_rows(panel, HORIZONS, every=args.every)
    info1 = write_dataset(job1, ML_DATA_DIR / f"job1-{tag}.csv.gz",
                          {**meta, "job": 1, "methods": list(JOB1_METHODS)})
    info2 = write_dataset(job2, ML_DATA_DIR / f"job2-{tag}.csv.gz",
                          {**meta, "job": 2, "every": args.every})
    for info in (info1, info2):
        print(f"Wrote {info['file']}: {info['rows']:,} rows x {info['columns']} columns, "
              f"{info['firstDate']} to {info['lastDate']}")
    print(f"Done in {time.perf_counter() - started:.0f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
