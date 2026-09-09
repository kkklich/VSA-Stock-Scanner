"""Service-layer exceptions."""

from __future__ import annotations


class StooqAccessError(Exception):
    """Raised when stooq.pl refuses to serve data.

    Examples: an unsolved anti-bot challenge, an access denial ("Odmowa dostępu"),
    an exceeded daily download limit, or an otherwise unrecognized (non-CSV) response.
    The router maps this to an HTTP 502 (Bad Gateway).
    """


class NoIntradayDataError(StooqAccessError):
    """The provider answered, and its answer was "there is nothing here".

    A subclass so every existing ``except StooqAccessError`` handler keeps
    working unchanged, but a distinguishable one, because the two situations
    call for opposite responses. "The provider is unreachable" is temporary and
    worth retrying (HTTP 502); "this company has no intraday history" is a
    permanent fact about the ticker, and retrying it six times over fifteen
    seconds — which is exactly what the frontend's 502 backoff did — just asks
    Yahoo the same question six times to get the same answer (HTTP 404).

    Only intraday bars can hit this: they are the one series the app does not
    store, and Yahoo simply has no intraday history for many thinly traded GPW
    listings.
    """
