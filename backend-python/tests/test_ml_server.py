"""Running the AI jobs on the server (decision D6, 2026-09-26).

Where files go when ``STOCKPILOT_ML_DIR`` names the server folder, the trial
register carrying the trials run elsewhere, one-stock-at-a-time reading, and
the back-fill's brake on a run of failed downloads.
"""

from __future__ import annotations

import asyncio
import csv
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app.db.repository import InMemoryQuoteRepository
from app.ml import trials
from app.ml.backfill import BackfillResult, run_backfill
from app.ml.data_access import stream_stock_inputs
from app.ml.trials import BASELINE_FILE, ensure_register, trial_count
from app.services.exceptions import StooqAccessError
from tests.ml_synthetic import random_walk_bars

BACKEND = Path(__file__).resolve().parents[1]


class TestFolders:
    def test_one_folder_holds_everything_on_the_server(self, tmp_path):
        code = (
            "from app.ml import ML_DATA_DIR, AGENT_ML_DIR; from app.ml.trials import TRIALS_FILE; "
            "print(ML_DATA_DIR); print(AGENT_ML_DIR); print(TRIALS_FILE)"
        )
        env = {**os.environ, "STOCKPILOT_ML_DIR": str(tmp_path)}
        result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env,
                                capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        data, reports, register = result.stdout.strip().splitlines()[-3:]
        assert Path(data) == tmp_path / "data"
        assert Path(reports) == tmp_path
        assert Path(register) == tmp_path / "trials.csv"

    def test_without_it_the_laptop_folders_are_used(self):
        from app.ml import AGENT_ML_DIR, ML_DATA_DIR

        if os.environ.get("STOCKPILOT_ML_DIR"):
            pytest.skip("STOCKPILOT_ML_DIR is set in this environment")
        assert ML_DATA_DIR == BACKEND / "ml_data"
        assert AGENT_ML_DIR == BACKEND.parent / "agent" / "ml"


class TestRegisterBaseline:
    def test_the_baseline_holds_the_pilot_trials(self):
        with BASELINE_FILE.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 14
        assert {r["phase"] for r in rows} == {"1"}

    def test_the_servers_register_starts_from_the_baseline(self, tmp_path, monkeypatch):
        server_register = tmp_path / "trials.csv"
        monkeypatch.setattr(trials, "TRIALS_FILE", server_register)
        ensure_register(server_register)
        assert trial_count(server_register) == 14
        # The next trial is number 15 — the pilot's trials keep counting.
        assert trials.append_trial({"model": "logistic"}, server_register) == 15

    def test_any_other_register_starts_empty(self, tmp_path):
        other = tmp_path / "scratch.csv"
        ensure_register(other)
        assert trial_count(other) == 0


class TestStreaming:
    @staticmethod
    def _make() -> InMemoryQuoteRepository:
        async def make():
            repo = InMemoryQuoteRepository()
            await repo.upsert_quotes("kgh", random_walk_bars(60, seed=1))
            await repo.upsert_quotes("pko", random_walk_bars(60, seed=2, start=date(2021, 1, 4)))
            return repo

        return asyncio.run(make())

    def test_yields_companies_with_bars_one_at_a_time(self):
        repo = self._make()
        stream = stream_stock_inputs(["gpw"], tickers=["kgh", "pko", "cdr"], repo=repo)
        first = next(stream)
        assert first.market == "gpw" and first.currency == "PLN" and len(first.bars) == 60
        rest = list(stream)
        assert {first.ticker, *(s.ticker for s in rest)} == {"kgh", "pko"}  # cdr: no bars

    def test_since_limits_the_history(self):
        repo = self._make()
        (pko,) = list(stream_stock_inputs(["gpw"], since=date(2021, 2, 1), tickers=["pko"],
                                          repo=repo))
        assert min(b.date for b in pko.bars) >= date(2021, 2, 1)


class _Client:
    def __init__(self, fail: set[str]):
        self.fail = fail

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        if ticker in self.fail:
            raise StooqAccessError("429 Too Many Requests")
        return random_walk_bars(30, seed=len(ticker))


async def _no_sleep(_seconds):
    return None


class TestBackfillBrake:
    @pytest.mark.asyncio
    async def test_stops_after_a_run_of_failures(self):
        tickers = [f"t{i}" for i in range(20)]
        seen: list[BackfillResult] = []
        run = await run_backfill(tickers, _Client(set(tickers)), InMemoryQuoteRepository(),
                                 on_result=seen.append, stop_after_failures=8, sleep=_no_sleep)
        assert run.stopped_early and run.processed == 8 and len(seen) == 8
        assert run.by_status == {"failed": 8}

    @pytest.mark.asyncio
    async def test_a_success_resets_the_count(self):
        tickers = [f"t{i}" for i in range(12)]
        failing = {t for i, t in enumerate(tickers) if i % 4 != 3}  # 3 fail, 1 works, …
        run = await run_backfill(tickers, _Client(failing), InMemoryQuoteRepository(),
                                 stop_after_failures=4, sleep=_no_sleep)
        assert not run.stopped_early and run.processed == 12
        assert run.by_status == {"failed": 9, "new": 3}

    @pytest.mark.asyncio
    async def test_it_pauses_between_tickers(self):
        pauses: list[float] = []

        async def remember(seconds):
            pauses.append(seconds)

        await run_backfill(["a", "b", "c"], _Client(set()), InMemoryQuoteRepository(),
                           pause=2.5, sleep=remember)
        assert pauses == [2.5, 2.5, 2.5]
