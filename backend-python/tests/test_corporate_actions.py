"""Corporate-action handling: splits and dividends in a stored price history.

Two layers are covered here:

  * :mod:`app.analysis.corporate_actions` — the pure comparison that decides
    whether the data provider has restated a stock's past.
  * :class:`app.jobs.daily_ingest.IngestService` — what the nightly job does
    about it: rebuild the ticker's whole stored history rather than top it up
    with bars measured on a different scale.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.analysis.corporate_actions import (
    AdjustmentCheck,
    detect_adjustment,
)
from app.db.repository import InMemoryQuoteRepository
from app.jobs.daily_ingest import IngestService
from app.models import GpwCompany, RatingPoint, StooqDailyQuote
from app.services.cache import TTLCache
from app.services.exceptions import StooqAccessError

# ── Helpers ───────────────────────────────────────────────────────────────────


def _bar(day: date, close: float, volume: int = 100_000) -> StooqDailyQuote:
    """One OHLCV bar whose whole candle sits on the same scale as ``close``."""
    return StooqDailyQuote(
        date=day,
        open=Decimal(str(round(close * 0.99, 4))),
        high=Decimal(str(round(close * 1.02, 4))),
        low=Decimal(str(round(close * 0.98, 4))),
        close=Decimal(str(close)),
        volume=volume,
    )


def _series(start: date, count: int, close: float) -> list[StooqDailyQuote]:
    """``count`` consecutive daily bars, all at the same price."""
    return [_bar(start + timedelta(days=i), close) for i in range(count)]


def _company(ticker: str = "kgh") -> GpwCompany:
    return GpwCompany(ticker=ticker, name=ticker.upper(), sector="Test")


class _ScaledProvider:
    """A data provider serving one canned history, honouring ``from_date``.

    Stands in for Yahoo. ``fail_after`` makes every call past the first N raise,
    which is how the "the repair download itself failed" path is exercised.
    """

    def __init__(
        self,
        bars: list[StooqDailyQuote],
        fail_after: int | None = None,
    ) -> None:
        self._bars = bars
        self._fail_after = fail_after
        self.calls: list[tuple[str, date | None]] = []

    async def get_daily_history(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[StooqDailyQuote]:
        self.calls.append((ticker, from_date))
        if self._fail_after is not None and len(self.calls) > self._fail_after:
            raise StooqAccessError("Simulated provider outage")
        bars = [
            b
            for b in self._bars
            if (from_date is None or b.date >= from_date)
            and (to_date is None or b.date <= to_date)
        ]
        if not bars:
            raise StooqAccessError(f"No data for {ticker}")
        return bars


def _make_service(
    provider: _ScaledProvider,
    repo: InMemoryQuoteRepository,
    ticker: str = "kgh",
) -> IngestService:
    return IngestService(
        companies=[_company(ticker)],
        stooq=provider,  # type: ignore[arg-type]  # duck-typed in production too
        repo=repo,
        history_cache=TTLCache(),
        ranking_cache=TTLCache(),
    )


# ── The pure check ────────────────────────────────────────────────────────────


class TestDetectAdjustment:
    def test_identical_series_is_not_an_adjustment(self) -> None:
        bars = _series(date(2026, 6, 1), 5, 100.0)
        check = detect_adjustment(bars, bars)
        assert check.adjusted is False
        assert check.ratio is None

    def test_forward_split_is_detected_with_its_ratio(self) -> None:
        """A 1:4 split quarters every past price the provider serves."""
        stored = _series(date(2026, 6, 1), 5, 100.0)
        fetched = _series(date(2026, 6, 1), 5, 25.0)

        check = detect_adjustment(stored, fetched)

        assert check.adjusted is True
        assert check.ratio == 0.25
        assert check.compared == 5
        assert check.mismatched == 5
        assert check.consistent is True
        assert "1:4 split" in check.reason

    def test_reverse_split_is_detected(self) -> None:
        stored = _series(date(2026, 6, 1), 4, 2.0)
        fetched = _series(date(2026, 6, 1), 4, 20.0)

        check = detect_adjustment(stored, fetched)

        assert check.adjusted is True
        assert check.ratio == 10.0
        assert "10:1 split" in check.reason

    def test_dividend_adjustment_is_detected_and_not_called_a_split(self) -> None:
        """A dividend rescales the past by a small, non-split factor."""
        stored = _series(date(2026, 6, 1), 5, 100.0)
        fetched = _series(date(2026, 6, 1), 5, 96.5)  # ~3.5% distribution

        check = detect_adjustment(stored, fetched)

        assert check.adjusted is True
        assert check.ratio == 0.965
        assert "dividend or other adjustment" in check.reason

    def test_difference_below_tolerance_is_ignored(self) -> None:
        """Rounding-scale noise must not trigger a full re-download."""
        stored = _series(date(2026, 6, 1), 5, 100.0)
        fetched = _series(date(2026, 6, 1), 5, 100.2)  # 0.2%, under the 0.5% floor

        check = detect_adjustment(stored, fetched)

        assert check.adjusted is False
        assert check.compared == 5
        assert check.mismatched == 0

    def test_only_overlapping_dates_are_compared(self) -> None:
        stored = _series(date(2026, 6, 1), 3, 100.0)
        # Fresh bars for entirely different days: nothing to compare, so no
        # conclusion may be drawn either way.
        fetched = _series(date(2026, 7, 1), 3, 25.0)

        check = detect_adjustment(stored, fetched)

        assert check.adjusted is False
        assert check.compared == 0

    def test_partial_overlap_uses_the_shared_dates_only(self) -> None:
        stored = _series(date(2026, 6, 1), 5, 100.0)
        # The provider's window starts two days into the stored one.
        fetched = _series(date(2026, 6, 3), 6, 50.0)

        check = detect_adjustment(stored, fetched)

        assert check.compared == 3
        assert check.mismatched == 3
        assert check.ratio == 0.5
        assert check.first_date == date(2026, 6, 3)
        assert check.last_date == date(2026, 6, 5)

    def test_varying_ratios_are_reported_as_a_restatement(self) -> None:
        """Individually corrected figures are not one corporate action."""
        start = date(2026, 6, 1)
        stored = [_bar(start, 100.0), _bar(start + timedelta(days=1), 100.0)]
        fetched = [_bar(start, 50.0), _bar(start + timedelta(days=1), 80.0)]

        check = detect_adjustment(stored, fetched)

        assert check.adjusted is True
        assert check.consistent is False
        assert "varying amounts" in check.reason

    def test_empty_input_is_not_an_adjustment(self) -> None:
        bars = _series(date(2026, 6, 1), 3, 100.0)
        assert detect_adjustment([], bars).adjusted is False
        assert detect_adjustment(bars, []).adjusted is False

    def test_non_positive_close_cannot_anchor_a_ratio(self) -> None:
        """A zero close is a data defect, not a price to divide by."""
        day = date(2026, 6, 1)
        stored = [_bar(day, 100.0)]
        fetched = [
            StooqDailyQuote(
                date=day,
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                volume=0,
            )
        ]

        check = detect_adjustment(stored, fetched)

        assert check.adjusted is False
        assert check.compared == 0

    def test_volume_alone_never_triggers_a_repair(self) -> None:
        """Late-reported trades revise volume; the few-day re-fetch handles that."""
        day = date(2026, 6, 1)
        stored = [_bar(day, 100.0, volume=100_000)]
        fetched = [_bar(day, 100.0, volume=180_000)]

        assert detect_adjustment(stored, fetched).adjusted is False

    def test_min_mismatch_can_require_corroboration(self) -> None:
        start = date(2026, 6, 1)
        stored = _series(start, 3, 100.0)
        fetched = [_bar(start, 25.0)] + _series(start + timedelta(days=1), 2, 100.0)

        assert detect_adjustment(stored, fetched, min_mismatch=1).adjusted is True
        assert detect_adjustment(stored, fetched, min_mismatch=2).adjusted is False

    def test_default_check_reports_nothing_compared(self) -> None:
        assert AdjustmentCheck(adjusted=False).ratio is None


# ── The repository primitives the repair needs ────────────────────────────────


class TestRepositorySupport:
    def test_date_range_is_none_for_an_unknown_ticker(self) -> None:
        repo = InMemoryQuoteRepository()
        assert asyncio.run(repo.get_quote_date_range("kgh")) is None

    def test_date_range_spans_oldest_to_newest(self) -> None:
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", _series(date(2026, 1, 5), 40, 10.0)))
        assert asyncio.run(repo.get_quote_date_range("kgh")) == (
            date(2026, 1, 5),
            date(2026, 2, 13),
        )

    def test_rating_snapshots_follow_the_repaired_bars(self) -> None:
        repo = InMemoryQuoteRepository()
        day = date(2026, 6, 1)
        asyncio.run(repo.upsert_quotes("kgh", [_bar(day, 25.0)]))
        asyncio.run(
            repo.upsert_rating_snapshots(
                "kgh", [RatingPoint(date=day, rating=70, verdict="Buy", close=100.0)]
            )
        )

        updated = asyncio.run(repo.resync_rating_snapshot_closes("kgh"))

        assert updated == 1
        points = asyncio.run(repo.get_rating_history("kgh", day))
        assert points[0].close == 25.0
        # The rating itself is scale-free and must not be touched.
        assert points[0].rating == 70
        assert points[0].verdict == "Buy"

    def test_snapshot_without_a_bar_is_left_alone(self) -> None:
        repo = InMemoryQuoteRepository()
        day = date(2026, 6, 1)
        asyncio.run(
            repo.upsert_rating_snapshots(
                "kgh", [RatingPoint(date=day, rating=55, verdict="Hold", close=42.0)]
            )
        )

        assert asyncio.run(repo.resync_rating_snapshot_closes("kgh")) == 0
        assert asyncio.run(repo.get_rating_history("kgh", day))[0].close == 42.0


# ── What the nightly ingest does about it ─────────────────────────────────────


class TestIngestCorporateActions:
    """The regression this whole feature exists for.

    Without it, a 1:4 split leaves the database holding years of 100 PLN bars
    followed by a 25 PLN one — a stock that appears to have lost three quarters
    of its value overnight, which the VSA engine reads as a selling climax.
    """

    def _split_setup(
        self,
        *,
        history_days: int = 30,
        old_close: float = 100.0,
        new_close: float = 25.0,
        fail_after: int | None = None,
    ) -> tuple[IngestService, _ScaledProvider, InMemoryQuoteRepository, date]:
        today = date.today()
        start = today - timedelta(days=history_days - 1)

        repo = InMemoryQuoteRepository()
        # What the database holds: the whole history on the pre-split scale.
        asyncio.run(repo.upsert_quotes("kgh", _series(start, history_days, old_close)))

        # What the provider serves now: the same days, all restated.
        provider = _ScaledProvider(
            _series(start, history_days, new_close), fail_after=fail_after
        )
        return _make_service(provider, repo), provider, repo, start

    def test_split_rebuilds_the_whole_stored_history(self) -> None:
        svc, provider, repo, start = self._split_setup()

        stats = asyncio.run(svc.run())

        stored = asyncio.run(repo.get_quotes("kgh", start))
        assert len(stored) == 30
        # Every bar, not just the ones inside the nightly window.
        assert {float(q.close) for q in stored} == {25.0}
        assert stats is not None
        assert stats.adjusted == 1
        assert stats.adjusted_tickers == ["kgh"]
        assert stats.failed == 0
        # One ordinary fetch plus one repair fetch.
        assert len(provider.calls) == 2
        assert provider.calls[1][1] == start  # repaired from the first stored bar

    def test_repair_is_recorded_in_the_action_log_detail(self) -> None:
        svc, _, _, _ = self._split_setup()

        stats = asyncio.run(svc.run())

        assert stats is not None
        detail = stats.as_detail()
        assert detail["adjusted"] == 1
        assert detail["adjustedTickers"] == ["kgh"]

    def test_dividend_adjustment_also_rebuilds(self) -> None:
        svc, _, repo, start = self._split_setup(old_close=100.0, new_close=96.0)

        stats = asyncio.run(svc.run())

        stored = asyncio.run(repo.get_quotes("kgh", start))
        assert {float(q.close) for q in stored} == {96.0}
        assert stats is not None and stats.adjusted == 1

    def test_unchanged_history_is_topped_up_as_before(self) -> None:
        """The common case must cost exactly one fetch and change nothing."""
        svc, provider, repo, start = self._split_setup(
            old_close=100.0, new_close=100.0
        )

        stats = asyncio.run(svc.run())

        assert len(provider.calls) == 1
        assert stats is not None
        assert stats.adjusted == 0
        assert stats.fetched == 1
        stored = asyncio.run(repo.get_quotes("kgh", start))
        assert {float(q.close) for q in stored} == {100.0}

    def test_failed_repair_writes_nothing_rather_than_mixing_scales(self) -> None:
        """A stale history beats an internally inconsistent one."""
        svc, provider, repo, start = self._split_setup(fail_after=1)

        stats = asyncio.run(svc.run())

        stored = asyncio.run(repo.get_quotes("kgh", start))
        # Untouched: still entirely on the old scale, so tonight's run sees the
        # same mismatch and can try again.
        assert {float(q.close) for q in stored} == {100.0}
        assert stats is not None
        assert stats.adjusted == 0
        assert stats.failed == 1
        assert stats.failures == ["kgh"]
        assert stats.bars_written == 0
        assert len(provider.calls) == 2

    def test_rating_snapshots_are_rescaled_with_the_bars(self) -> None:
        svc, _, repo, start = self._split_setup()
        asyncio.run(
            repo.upsert_rating_snapshots(
                "kgh",
                [
                    RatingPoint(date=start, rating=80, verdict="Buy", close=100.0),
                    RatingPoint(
                        date=start + timedelta(days=1),
                        rating=81,
                        verdict="Buy",
                        close=100.0,
                    ),
                ],
            )
        )

        asyncio.run(svc.run())

        points = asyncio.run(repo.get_rating_history("kgh", start))
        assert [p.close for p in points] == [25.0, 25.0]
        assert [p.rating for p in points] == [80, 81]

    def test_a_new_ticker_still_uses_the_normal_window(self) -> None:
        """Nothing stored: there is no overlap to check and no gap to close."""
        today = date.today()
        repo = InMemoryQuoteRepository()
        provider = _ScaledProvider(_series(today - timedelta(days=29), 30, 25.0))
        svc = _make_service(provider, repo)

        stats = asyncio.run(svc.run())

        assert len(provider.calls) == 1
        assert provider.calls[0][1] == today - timedelta(days=5)
        assert stats is not None and stats.adjusted == 0

    def test_stale_stored_history_widens_the_fetch_to_regain_overlap(self) -> None:
        """After an outage the window would otherwise overlap nothing."""
        today = date.today()
        last_stored = today - timedelta(days=20)
        repo = InMemoryQuoteRepository()
        asyncio.run(
            repo.upsert_quotes("kgh", _series(last_stored - timedelta(days=9), 10, 100.0))
        )
        provider = _ScaledProvider(_series(today - timedelta(days=60), 61, 100.0))
        svc = _make_service(provider, repo)

        asyncio.run(svc.run())

        # Reaches back past the last stored bar rather than the last five days,
        # so the gap is filled and there are bars to compare.
        assert provider.calls[0][1] == last_stored - timedelta(days=5)

    def test_widened_fetch_still_detects_an_adjustment(self) -> None:
        today = date.today()
        last_stored = today - timedelta(days=20)
        start = last_stored - timedelta(days=9)
        repo = InMemoryQuoteRepository()
        asyncio.run(repo.upsert_quotes("kgh", _series(start, 10, 100.0)))
        provider = _ScaledProvider(_series(today - timedelta(days=60), 61, 25.0))
        svc = _make_service(provider, repo)

        stats = asyncio.run(svc.run())

        assert stats is not None and stats.adjusted == 1
        stored = asyncio.run(repo.get_quotes("kgh", start))
        assert {float(q.close) for q in stored} == {25.0}

    def test_full_bootstrap_skips_the_gap_widening(self) -> None:
        """A full ingest already asks for everything; widening is meaningless."""
        today = date.today()
        repo = InMemoryQuoteRepository()
        asyncio.run(
            repo.upsert_quotes("kgh", _series(today - timedelta(days=200), 5, 100.0))
        )
        provider = _ScaledProvider(_series(today - timedelta(days=399), 400, 100.0))
        svc = _make_service(provider, repo)

        asyncio.run(svc.run(full=True))

        assert provider.calls[0][1] == today - timedelta(days=400)
