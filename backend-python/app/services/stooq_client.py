"""Async client for fetching end-of-day market data from stooq.pl.

stooq.pl guards its CSV endpoints with a hashcash-style proof-of-work challenge:
the page ships a constant ``c`` and a difficulty ``d``, and the browser must find
an integer ``n`` such that the hex of ``SHA-256(c + n)`` starts with ``d`` leading
zero nibbles, then POST ``c`` and ``n`` to ``/__verify`` to obtain an auth cookie.
This client solves that challenge automatically and retries the original request;
a shared cookie jar (on the injected ``httpx.AsyncClient``) keeps the auth cookie
across calls.

This is a direct port of the .NET ``StooqClient``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.models import StooqDailyQuote
from app.services.exceptions import StooqAccessError

logger = logging.getLogger(__name__)

# Safety cap on proof-of-work iterations (difficulty 4 averages ~65k).
_MAX_PROOF_OF_WORK_ITERATIONS = 100_000_000

# Markers that indicate stooq.pl refused the request rather than returning CSV data.
_DENIAL_MARKERS = (
    "Odmowa dostępu",  # access denied
    "Przekroczony",  # limit exceeded
    "Exceeded the daily hits limit",
    "Brak danych",  # no data
    "Wybrana lokalizacja nie istnieje",  # location does not exist
    "requires JavaScript",
)

# Matches the inline proof-of-work challenge, e.g. c="AAA...",d=4
_CHALLENGE_RE = re.compile(r'c="(?P<c>[^"]+)",d=(?P<d>\d+)')


class StooqClient:
    """Downloads EOD OHLCV history from stooq.pl, transparently solving its anti-bot challenge."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def get_daily_history(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[StooqDailyQuote]:
        """Download EOD OHLCV history for ``ticker`` (oldest bar first).

        Raises:
            ValueError: the ticker is empty.
            StooqAccessError: stooq.pl refused or returned no usable data.
        """
        if not ticker or not ticker.strip():
            raise ValueError("Ticker must be provided.")

        url = _build_daily_url(ticker.strip().casefold(), from_date, to_date)
        csv = await self._get_with_challenge(url)
        return _parse_daily_csv(csv, ticker)

    async def _get_with_challenge(self, url: str) -> str:
        """GET ``url``, solving the anti-bot challenge if present, and return the body."""
        body = (await self._http.get(url)).text

        challenge = _CHALLENGE_RE.search(body)
        if challenge:
            logger.debug("stooq.pl issued an anti-bot challenge; solving proof-of-work.")

            c = challenge.group("c")
            difficulty = int(challenge.group("d"))
            # Offload CPU-bound POW to a thread so the event loop stays free.
            n = await asyncio.to_thread(_solve_proof_of_work, c, difficulty)

            verify_url = _verify_url_for(url)
            verify_response = await self._http.post(verify_url, data={"c": c, "n": str(n)})
            verify_response.raise_for_status()

            body = (await self._http.get(url)).text
            if _CHALLENGE_RE.search(body):
                raise StooqAccessError(
                    "stooq.pl re-issued the anti-bot challenge after verification."
                )

        _ensure_not_blocked(body)
        return body


def _build_daily_url(ticker: str, from_date: date | None, to_date: date | None) -> str:
    # https://stooq.pl/q/d/l/?s=kgh&i=d[&d1=YYYYMMDD&d2=YYYYMMDD]
    url = f"https://stooq.pl/q/d/l/?s={quote(ticker, safe='')}&i=d"
    if from_date is not None:
        url += f"&d1={from_date:%Y%m%d}"
    if to_date is not None:
        url += f"&d2={to_date:%Y%m%d}"
    return url


def _verify_url_for(url: str) -> str:
    """Return ``scheme://authority/__verify`` for the given URL."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/__verify", "", ""))


def _solve_proof_of_work(challenge: str, difficulty: int) -> int:
    """Find the smallest non-negative ``n`` whose ``SHA-256(challenge + n)`` hex
    begins with ``difficulty`` zero nibbles."""
    challenge_bytes = challenge.encode("utf-8")

    for n in range(_MAX_PROOF_OF_WORK_ITERATIONS):
        digest = hashlib.sha256(challenge_bytes + str(n).encode("ascii")).digest()
        if _has_leading_zero_nibbles(digest, difficulty):
            return n

    raise StooqAccessError(
        f"Could not solve the stooq.pl proof-of-work within "
        f"{_MAX_PROOF_OF_WORK_ITERATIONS} attempts."
    )


def _has_leading_zero_nibbles(digest: bytes, nibbles: int) -> bool:
    for i in range(nibbles):
        byte = digest[i // 2]
        nibble = (byte >> 4) if i % 2 == 0 else (byte & 0x0F)
        if nibble != 0:
            return False
    return True


def _ensure_not_blocked(body: str) -> None:
    lowered = body.casefold()
    for marker in _DENIAL_MARKERS:
        if marker.casefold() in lowered:
            snippet = body.strip()[:160]
            raise StooqAccessError(f'stooq.pl denied the request: "{snippet}"')


def _parse_daily_csv(csv: str, ticker: str) -> list[StooqDailyQuote]:
    """Parse stooq's daily CSV positionally, skipping the header and any junk rows.

    stooq returns ``Date,Open,High,Low,Close,Volume`` (or the Polish equivalent) as
    the first line; rows whose first column is not a date are skipped.
    """
    quotes: list[StooqDailyQuote] = []

    for line in csv.splitlines():
        if not line.strip():
            continue

        columns = line.split(",")
        if len(columns) < 6:
            continue

        parsed_date = _try_parse_date(columns[0])
        if parsed_date is None:
            continue

        try:
            open_ = Decimal(columns[1])
            high = Decimal(columns[2])
            low = Decimal(columns[3])
            close = Decimal(columns[4])
        except (InvalidOperation, ValueError):
            continue

        # Volume can be blank (e.g. for indices) — treat as zero.
        volume = _try_parse_int(columns[5])

        quotes.append(
            StooqDailyQuote(
                date=parsed_date,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )

    if not quotes:
        raise StooqAccessError(f"stooq.pl returned no parseable daily data for '{ticker}'.")

    return quotes


def _try_parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _try_parse_int(value: str) -> int:
    try:
        # stooq volumes are integers, but tolerate a stray decimal point.
        return int(Decimal(value))
    except (InvalidOperation, ValueError):
        return 0
