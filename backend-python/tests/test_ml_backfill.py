"""The one-time history back-fill never splices two price scales together."""

from __future__ import annotations

from datetime import date

import pytest

from app.db.repository import InMemoryQuoteRepository
from app.ml.backfill import backfill_ticker
from app.services.exceptions import StooqAccessError
from tests.ml_synthetic import bar, weekdays

DAYS = weekdays(date(2020, 1, 6), 60)


def _series(days, scale: float = 1.0):
    return [bar(d, 10 * scale, 11 * scale, 9 * scale, 10 * scale, 1000) for d in days]


class _Client:
    def __init__(self, bars=None, error: Exception | None = None):
        self.bars = bars or []
        self.error = error
        self.calls: list[date | None] = []

    async def get_daily_history(self, ticker, from_date=None, to_date=None):
        self.calls.append(from_date)
        if self.error:
            raise self.error
        return list(self.bars)


async def _repo_with(bars):
    repo = InMemoryQuoteRepository()
    if bars:
        await repo.upsert_quotes("kgh", bars)
    return repo


@pytest.mark.asyncio
async def test_adds_only_the_older_bars_when_the_series_agree():
    repo = await _repo_with(_series(DAYS[30:]))
    result = await backfill_ticker("kgh", _Client(_series(DAYS)), repo)
    assert result.status == "extended" and result.written == 30
    span = await repo.get_quote_date_range("kgh")
    assert span[0] == DAYS[0]


@pytest.mark.asyncio
async def test_nothing_older_means_unchanged():
    repo = await _repo_with(_series(DAYS))
    result = await backfill_ticker("kgh", _Client(_series(DAYS[10:])), repo)
    assert result.status == "unchanged" and result.written == 0


@pytest.mark.asyncio
async def test_a_restated_series_that_covers_everything_replaces_it():
    repo = await _repo_with(_series(DAYS[30:]))  # stored on the old scale
    result = await backfill_ticker("kgh", _Client(_series(DAYS, scale=0.5)), repo)
    assert result.status == "rebuilt"
    stored = await repo.get_quotes("kgh", DAYS[0], None)
    assert {float(b.close) for b in stored} == {5.0}  # one scale throughout


@pytest.mark.asyncio
async def test_a_restated_series_that_starts_too_late_writes_nothing():
    old = _series(DAYS)
    repo = await _repo_with(old)
    result = await backfill_ticker("kgh", _Client(_series(DAYS[20:], scale=0.5)), repo)
    assert result.status == "refused" and result.written == 0
    stored = await repo.get_quotes("kgh", DAYS[0], None)
    assert {float(b.close) for b in stored} == {10.0}


@pytest.mark.asyncio
async def test_a_ticker_with_nothing_stored_gets_everything():
    repo = await _repo_with([])
    result = await backfill_ticker("kgh", _Client(_series(DAYS)), repo)
    assert result.status == "new" and result.written == 60


@pytest.mark.asyncio
async def test_failures_are_reported_not_raised():
    repo = await _repo_with(_series(DAYS))
    failed = await backfill_ticker("kgh", _Client(error=StooqAccessError("no data")), repo)
    assert failed.status == "failed" and "no data" in failed.detail
    empty = await backfill_ticker("kgh", _Client([]), repo)
    assert empty.status == "empty"


@pytest.mark.asyncio
async def test_asks_from_the_requested_start():
    client = _Client(_series(DAYS))
    await backfill_ticker("kgh", client, await _repo_with([]), start=date(2001, 2, 3))
    assert client.calls == [date(2001, 2, 3)]
