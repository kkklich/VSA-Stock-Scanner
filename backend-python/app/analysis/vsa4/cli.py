"""CLI entry point for the educational, standard-library VSA engine.

[StockPilot] Vendored from the owner's "VSA - kompendium i program Python"
package (python/vsa.py, SHA-256 1dff4a4a...eaf55d, supplied 2026-09-24).
Unchanged except this note and the two imports below. Run it from
``backend-python`` exactly like the original::

    python -m app.analysis.vsa4.cli --input bars.csv --output results

``scripts/vsa4_run.py`` feeds it a stored ticker instead of a CSV you prepared.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.analysis.vsa4.backtest import TRADE_FIELDS, run_backtest  # [StockPilot] was: from backtest
from app.analysis.vsa4.engine import Config, SIGNAL_NAMES, VSAError, analyze, config_as_dict, load_ohlcv_csv  # [StockPilot] was: from engine


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(
    input_path: Path, output_dir: Path, config: Config,
    protected_inputs: list[Path] | None = None,
) -> dict[str, Any]:
    protected = [input_path, *(protected_inputs or [])]
    destinations = [output_dir / name for name in ("signals.csv", "trades.csv", "equity.csv", "summary.json")]
    protected_resolved = {item.resolve() for item in protected}
    collision = next((item for item in destinations if item.resolve() in protected_resolved), None)
    if collision is not None:
        raise VSAError(f"Plik wynikowy {collision} wskazuje na plik wejściowy; wybierz inny katalog --output.")
    bars = load_ohlcv_csv(input_path)
    try:
        input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise VSAError(f"Nie można policzyć SHA-256 pliku wejściowego: {exc}") from exc
    signal_rows = analyze(bars, config)
    trades, equity_rows, summary = run_backtest(bars, signal_rows, config)
    summary.update({
        "input_file": str(input_path),
        "input_sha256": input_hash,
        "bar_count": len(bars),
        "first_timestamp": bars[0].timestamp,
        "last_timestamp": bars[-1].timestamp,
        "configuration": config_as_dict(config),
        "signal_candidate_counts": {
            name: sum(bool(row[f"candidate_{name}"]) for row in signal_rows)
            for name in SIGNAL_NAMES
        },
        "long_setup_confirmations": sum(bool(row["long_setup_confirmation"]) for row in signal_rows),
        "short_setup_confirmations": sum(bool(row["short_setup_confirmation"]) for row in signal_rows),
    })
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "signals.csv", signal_rows)
    _write_csv(output_dir / "trades.csv", trades, TRADE_FIELDS)
    _write_csv(output_dir / "equity.csv", equity_rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Edukacyjny, heurystyczny analizator i backtester sygnałów VSA (bez integracji z brokerem)."
    )
    parser.add_argument("--input", required=True, help="CSV z kolumnami timestamp,open,high,low,close,volume")
    parser.add_argument("--output", required=True, help="Katalog na summary.json, signals.csv, trades.csv i equity.csv")
    parser.add_argument("--config", help="Opcjonalny plik JSON nadpisujący parametry domyślne")
    end_group = parser.add_mutually_exclusive_group()
    end_group.add_argument("--close-open-at-end", action="store_true", help="Zamknij otwartą pozycję na ostatnim close (z kosztem/slippage)")
    end_group.add_argument("--leave-open-at-end", action="store_true", help="Pozostaw pozycję otwartą i pokaż jej mark-to-market")
    args = parser.parse_args(argv)
    try:
        config = Config.from_json(args.config) if args.config else Config()
        if args.close_open_at_end:
            config = replace(config, close_positions_at_end=True)
        elif args.leave_open_at_end:
            config = replace(config, close_positions_at_end=False)
        config.validate()
        protected = [Path(args.config)] if args.config else []
        summary = run(Path(args.input), Path(args.output), config, protected_inputs=protected)
    except (VSAError, OSError, ValueError) as exc:
        print(f"Błąd VSA: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "bar_count": summary["bar_count"],
        "closed_trades": summary["closed_trades"],
        "open_trades": summary["open_trades"],
        "final_equity": summary["final_equity"],
        "results": str(Path(args.output).resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
