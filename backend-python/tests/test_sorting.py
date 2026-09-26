"""Multi-column sorting: `sortBy`/`sortDir` as ordered lists of levels.

The tables let the user sort by one column and then break its ties with
another ("sector A→Z, best rating first"). On the wire that is two
comma-separated lists, so the first column and direction are exactly what an
older single-column client sends — the compatibility case is pinned here too.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.routers.stocks import (
    MAX_SORT_LEVELS,
    _apply_sort,
    _parse_sort_levels,
    _sort_value,
)

# A small whitelist standing in for a real endpoint's: camelCase query key →
# the attribute it reads.
ALLOWED = {
    "sector": "sector",
    "currentRating": "current_rating",
    "ticker": "ticker",
    "lastPrice": "last_price",
}


@dataclass
class Row:
    ticker: str
    sector: str | None
    current_rating: int
    last_price: float | None = None


def _rows() -> list[Row]:
    return [
        Row("PKO", "Banks", 70),
        Row("KGH", "Mining", 90),
        Row("PKN", "Energy", 70),
        Row("CDR", "Banks", 90),
        Row("ALR", "Banks", 70),
    ]


def _order(rows: list[Row], sort_by: str, sort_dir: str) -> list[str]:
    levels = _parse_sort_levels(sort_by, sort_dir, ALLOWED)
    return [r.ticker for r in _apply_sort(rows, levels, _sort_value)]


class TestParseSortLevels:
    def test_single_column_is_unchanged(self) -> None:
        """What every client sent before multi-column sorting existed."""
        assert _parse_sort_levels("currentRating", "desc", ALLOWED) == [
            ("current_rating", True)
        ]
        assert _parse_sort_levels("ticker", "asc", ALLOWED) == [("ticker", False)]

    def test_two_columns_keep_their_own_directions(self) -> None:
        assert _parse_sort_levels("sector,currentRating", "asc,desc", ALLOWED) == [
            ("sector", False),
            ("current_rating", True),
        ]

    def test_missing_direction_falls_back_to_the_endpoint_default(self) -> None:
        # Only the first level names a direction; the second takes the default.
        assert _parse_sort_levels("sector,currentRating", "asc", ALLOWED) == [
            ("sector", False),
            ("current_rating", True),
        ]
        assert _parse_sort_levels("sector,ticker", "", ALLOWED, default_dir="asc") == [
            ("sector", False),
            ("ticker", False),
        ]

    def test_whitespace_around_values_is_tolerated(self) -> None:
        assert _parse_sort_levels(" sector , ticker ", " asc , DESC ", ALLOWED) == [
            ("sector", False),
            ("ticker", True),
        ]

    def test_a_repeated_column_is_kept_once(self) -> None:
        """Naming a column again could never change the order — drop the echo.

        The surviving levels keep the direction sent at THEIR position: the two
        lists are positional, so dropping the echo must not shift ``ticker``
        onto the direction meant for the duplicate.
        """
        levels = _parse_sort_levels("sector,sector,ticker", "asc,desc,desc", ALLOWED)
        assert levels == [("sector", False), ("ticker", True)]

    def test_unknown_column_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _parse_sort_levels("sector,__class__", "asc,asc", ALLOWED)
        assert exc.value.status_code == 400
        assert "__class__" in exc.value.detail

    def test_unknown_direction_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _parse_sort_levels("sector", "sideways", ALLOWED)
        assert exc.value.status_code == 400
        assert "sideways" in exc.value.detail

    def test_empty_sort_by_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _parse_sort_levels("", "asc", ALLOWED)
        assert exc.value.status_code == 400

    def test_more_levels_than_allowed_rejected(self) -> None:
        too_many = ",".join(list(ALLOWED)[: MAX_SORT_LEVELS + 1])
        with pytest.raises(HTTPException) as exc:
            _parse_sort_levels(too_many, "asc", ALLOWED)
        assert exc.value.status_code == 400
        assert str(MAX_SORT_LEVELS) in exc.value.detail

    def test_more_directions_than_columns_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _parse_sort_levels("sector", "asc,desc", ALLOWED)
        assert exc.value.status_code == 400


class TestApplySort:
    def test_one_level_matches_the_old_single_column_sort(self) -> None:
        rows = _rows()
        expected = sorted(rows, key=lambda r: r.ticker, reverse=True)
        assert _order(rows, "ticker", "desc") == [r.ticker for r in expected]

    def test_second_level_breaks_the_first_ones_ties(self) -> None:
        # Sector A→Z, and inside each sector the best rating first.
        assert _order(_rows(), "sector,currentRating", "asc,desc") == [
            "CDR",  # Banks 90
            "PKO",  # Banks 70  ─ tie on 70 broken by the input order (stable)
            "ALR",  # Banks 70
            "PKN",  # Energy
            "KGH",  # Mining
        ]

    def test_each_level_keeps_its_own_direction(self) -> None:
        """One `reverse` flag over a tuple key could not express this."""
        assert _order(_rows(), "currentRating,ticker", "desc,asc") == [
            "CDR",
            "KGH",  # 90s, A→Z
            "ALR",
            "PKN",
            "PKO",  # 70s, A→Z
        ]
        assert _order(_rows(), "currentRating,ticker", "desc,desc") == [
            "KGH",
            "CDR",
            "PKO",
            "PKN",
            "ALR",
        ]

    def test_third_level_breaks_the_seconds_ties(self) -> None:
        rows = [
            Row("AAA", "Banks", 70, 5.0),
            Row("BBB", "Banks", 70, 9.0),
            Row("CCC", "Banks", 90, 1.0),
        ]
        assert _order(rows, "sector,currentRating,lastPrice", "asc,asc,desc") == [
            "BBB",
            "AAA",
            "CCC",
        ]

    def test_a_missing_value_still_sorts(self) -> None:
        """A null in a later level must not break the whole ordering."""
        rows = [
            Row("AAA", None, 70, None),
            Row("BBB", "Banks", 70, 3.0),
        ]
        assert _order(rows, "currentRating,sector", "desc,asc") == ["AAA", "BBB"]

    def test_input_is_not_mutated(self) -> None:
        rows = _rows()
        before = [r.ticker for r in rows]
        _order(rows, "ticker", "asc")
        assert [r.ticker for r in rows] == before
