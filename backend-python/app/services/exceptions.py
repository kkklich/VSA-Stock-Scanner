"""Service-layer exceptions."""

from __future__ import annotations


class StooqAccessError(Exception):
    """Raised when stooq.pl refuses to serve data.

    Examples: an unsolved anti-bot challenge, an access denial ("Odmowa dostępu"),
    an exceeded daily download limit, or an otherwise unrecognized (non-CSV) response.
    The router maps this to an HTTP 502 (Bad Gateway).
    """
