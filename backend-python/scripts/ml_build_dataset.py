"""Build the AI layer's training datasets from the stored bars — plan §19.1.

Reads the app's database (never downloads), computes every feature and label
(``app/ml``) **one stock at a time**, and writes per market, under the ML data
folder (``backend-python/ml_data/`` on a PC, ``~/stockpilot/ml/data`` on the
server)::

    job1-<market>.csv.gz   one row per firing of VSA V4, Weinstein, Glinicki V1
                           and Volume Breakout (the signal filter, Job 1)
    job2-<market>.csv.gz   every 5th session of every stock (the learned
                           Combined score, Job 2)

each with a ``.meta.json`` naming exactly what went in. Markets are built one
after another — the cross-sectional features compare stocks within a market,
and one market at a time keeps the memory to one market's worth.

On the server (decision D6)::

    bash deploy/ml-run.sh dataset
    bash deploy/ml-run.sh dataset --markets all

On a PC, from ``backend-python/`` with PostgreSQL running::

    .venv/Scripts/python.exe -m scripts.ml_build_dataset
"""

from __future__ import annotations

import argparse
import sys
import time

from app.config import settings
from app.ml import ML_DATA_DIR
from app.ml.data_access import parse_markets, peak_memory_mb, stream_stock_inputs
from app.ml.dataset import HORIZONS, JOB1_METHODS, JOB2_EVERY, build_datasets, write_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the AI layer's datasets.")
    parser.add_argument("--markets", default="gpw", help="gpw (default), a list, or all")
    parser.add_argument("--every", type=int, default=JOB2_EVERY,
                        help=f"Job 2 keeps every Nth session (default {JOB2_EVERY})")
    args = parser.parse_args(argv)
    if not settings.database_url:
        print("No database configured (STOCKPILOT_DATABASE_URL).", file=sys.stderr)
        return 2

    started = time.perf_counter()
    wrote = 0
    for market in parse_markets(args.markets):
        t0 = time.perf_counter()

        def progress(i: int, ticker: str, market: str = market) -> None:
            if i % 50 == 0:
                print(f"  {market}: {i} companies ({ticker})", flush=True)

        job1, job2 = build_datasets(
            stream_stock_inputs([market]), HORIZONS, progress=progress, every=args.every
        )
        if job2.empty and job1.empty:
            print(f"{market}: no stored bars — skipped.")
            continue
        meta = {"markets": [market], "horizons": list(HORIZONS)}
        info1 = write_dataset(job1, ML_DATA_DIR / f"job1-{market}.csv.gz",
                              {**meta, "job": 1, "methods": list(JOB1_METHODS)})
        info2 = write_dataset(job2, ML_DATA_DIR / f"job2-{market}.csv.gz",
                              {**meta, "job": 2, "every": args.every})
        wrote += 1
        for info in (info1, info2):
            print(f"Wrote {info['file']}: {info['rows']:,} rows x {info['columns']} columns, "
                  f"{info['firstDate']} to {info['lastDate']}")
        print(f"{market} done in {time.perf_counter() - t0:.0f}s.", flush=True)

    peak = peak_memory_mb()
    print(f"Done in {time.perf_counter() - started:.0f}s"
          + (f"; peak memory {peak:.0f} MB." if peak else "."))
    return 0 if wrote else 1


if __name__ == "__main__":
    raise SystemExit(main())
