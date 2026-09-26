"""One-time history back-fill for the AI layer's training — plan §16, decision D2.

Downloads each tracked company's daily history back to 1995 (or its listing)
and adds the part the database does not hold yet — never mixing two price
scales (see ``app/ml/backfill.py``). **Run it by hand, on your PC, once** —
never on the server and never on a schedule. It is the one ML tool that goes
out to Yahoo, and the owner approves it (decision D2) before it is run.

Run from ``backend-python/`` with PostgreSQL running::

    .venv/Scripts/python.exe -m scripts.ml_backfill_history --dry-run
    .venv/Scripts/python.exe -m scripts.ml_backfill_history --markets gpw
    .venv/Scripts/python.exe -m scripts.ml_backfill_history --markets all

It is **resumable**: progress is kept in ``ml_data/backfill-progress.json``,
and a ticker already done is skipped unless ``--force`` is given. At the end
a summary is written to ``ml_data/backfill-report-<date>.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

from app.config import settings
from app.db.base import build_engine, build_session_factory
from app.db.repository import PostgresQuoteRepository
from app.ml import ML_DATA_DIR
from app.ml.backfill import BACKFILL_FROM, DONE_STATUSES, backfill_ticker
from app.ml.data_access import parse_markets
from app.services.gpw_company_service import GpwCompanyService
from app.services.yahoo_finance_client import YahooFinanceClient

PROGRESS_FILE = ML_DATA_DIR / "backfill-progress.json"


def _load_progress(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_progress(path: Path, progress: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(progress, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


async def _run(args: argparse.Namespace) -> int:
    markets = parse_markets(args.markets)
    service = GpwCompanyService()
    companies = [c for m in markets for c in service.get_companies(m)]
    if args.tickers:
        wanted = {t.strip().lower() for t in args.tickers.split(",")}
        companies = [c for c in companies if c.ticker in wanted]
    start = date.fromisoformat(args.from_date)
    progress = {} if args.force else _load_progress(PROGRESS_FILE)

    engine = build_engine(settings.database_url)
    try:
        repo = PostgresQuoteRepository(build_session_factory(engine))
        todo = [
            c for c in companies if progress.get(c.ticker, {}).get("status") not in DONE_STATUSES
        ]
        print(f"{len(companies)} companies on {', '.join(markets)}; "
              f"{len(companies) - len(todo)} already done, {len(todo)} to do; from {start}.")

        if args.dry_run:
            spans = {c.ticker: await repo.get_quote_date_range(c.ticker) for c in todo}
            no_data = sum(1 for s in spans.values() if s is None)
            recent = sum(1 for s in spans.values() if s and s[0] > date(2020, 1, 1))
            print(f"Dry run - nothing downloaded. Of those {len(todo)}: {no_data} have no "
                  f"stored bars, {recent} start after 2020 and would gain the most.")
            print("Run again without --dry-run to download (after approving decision D2).")
            return 0

        client = YahooFinanceClient()
        counts: dict[str, int] = {}
        started = time.perf_counter()
        for i, company in enumerate(todo, start=1):
            result = await backfill_ticker(company.ticker, client, repo, start=start)
            counts[result.status] = counts.get(result.status, 0) + 1
            progress[company.ticker] = {
                "status": result.status,
                "storedFirst": result.stored_first,
                "fetchedFirst": result.fetched_first,
                "written": result.written,
                "detail": result.detail,
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            _save_progress(PROGRESS_FILE, progress)
            print(f"[{i}/{len(todo)}] {company.ticker:10s} {result.status:9s} "
                  f"+{result.written} bars (from {result.fetched_first}) {result.detail}")
            await asyncio.sleep(args.pause)
    finally:
        await engine.dispose()

    report = {
        "finishedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "markets": markets,
        "from": str(start),
        "processed": len(todo),
        "byStatus": counts,
        "seconds": round(time.perf_counter() - started, 1),
    }
    out = ML_DATA_DIR / f"backfill-report-{date.today()}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if counts.get("failed", 0) <= max(1, len(todo) // 10) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-time history back-fill for AI training (decision D2). PC only."
    )
    parser.add_argument("--markets", default="gpw", help="gpw (default), a list, or all")
    parser.add_argument("--tickers", help="comma-separated subset, e.g. kgh,pko")
    parser.add_argument("--from", dest="from_date", default=str(BACKFILL_FROM),
                        help=f"oldest date to ask for (default {BACKFILL_FROM})")
    parser.add_argument("--pause", type=float, default=1.0,
                        help="seconds between tickers, to stay polite (default 1)")
    parser.add_argument("--force", action="store_true", help="redo tickers already done")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be done; download nothing")
    args = parser.parse_args(argv)
    if not settings.database_url:
        print("No database configured (STOCKPILOT_DATABASE_URL).", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
