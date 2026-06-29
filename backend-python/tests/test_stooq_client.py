"""Tests for the stooq client's pure helpers and challenge solver."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

import pytest

from app.services.exceptions import StooqAccessError
from app.services.stooq_client import (
    _build_daily_url,
    _has_leading_zero_nibbles,
    _parse_daily_csv,
    _solve_proof_of_work,
    _verify_url_for,
)


def test_build_daily_url_without_dates() -> None:
    assert _build_daily_url("kgh", None, None) == "https://stooq.pl/q/d/l/?s=kgh&i=d"


def test_build_daily_url_with_date_range() -> None:
    url = _build_daily_url("kgh", date(2026, 1, 2), date(2026, 6, 25))
    assert url == "https://stooq.pl/q/d/l/?s=kgh&i=d&d1=20260102&d2=20260625"


def test_verify_url_for_strips_path_and_query() -> None:
    url = "https://stooq.pl/q/d/l/?s=kgh&i=d"
    assert _verify_url_for(url) == "https://stooq.pl/__verify"


def test_solve_proof_of_work_matches_difficulty() -> None:
    challenge = "abc"
    difficulty = 2
    n = _solve_proof_of_work(challenge, difficulty)

    digest = hashlib.sha256(f"{challenge}{n}".encode()).hexdigest()
    assert digest.startswith("0" * difficulty)
    assert _has_leading_zero_nibbles(bytes.fromhex(digest), difficulty)


def test_parse_daily_csv_reads_ohlcv_and_skips_header() -> None:
    csv = "\n".join(
        [
            "Date,Open,High,Low,Close,Volume",
            "2026-06-24,140.20,145.00,139.80,144.50,120000",
            "2026-06-25,144.60,146.10,143.00,143.20,98000",
            "",  # trailing blank line
        ]
    )

    quotes = _parse_daily_csv(csv, "kgh")

    assert len(quotes) == 2
    first = quotes[0]
    assert first.date == date(2026, 6, 24)
    assert first.open == Decimal("140.20")
    assert first.close == Decimal("144.50")
    assert first.volume == 120000


def test_parse_daily_csv_treats_blank_volume_as_zero() -> None:
    csv = "Date,Open,High,Low,Close,Volume\n2026-06-24,100,101,99,100.5,"
    quotes = _parse_daily_csv(csv, "wig")
    assert quotes[0].volume == 0


def test_parse_daily_csv_raises_when_no_data_rows() -> None:
    with pytest.raises(StooqAccessError):
        _parse_daily_csv("Date,Open,High,Low,Close,Volume\n", "kgh")
