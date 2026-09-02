"""Pluggable trading-method framework — the common interface + registry.

Every trading method the app can rank stocks by (VSA today, momentum /
Minervini / breakout screens tomorrow) implements the same tiny contract:
answer one pure question — *does this mechanical setup fire on this stock's
end-of-day bars today, and did it fire recently?* — plus a 0–100 attractiveness
score for cross-method ranking, and self-describing metadata (name,
plain-language description, and an evidence source).

Concrete methods live next to this file and **self-register** with
``@register_method``. The rest of the app discovers them through the registry
(``all_methods`` / ``get_method``), so adding a new method is *just writing one
class* — no per-method plumbing in the services, router or UI. This is the
generic engine roadmap item 23a asks for; VSA is a first-class member of the
same list rather than a hard-coded special case.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.analysis.vsa import VsaConfig
from app.models import StooqDailyQuote

# Sentinel for "the setup never fired within the evaluated window" — matches the
# ranking's existing ``days_since_signal`` convention (999 = never), so the two
# read the same way in the UI.
NEVER_FIRED = 999


@dataclass(frozen=True)
class MethodSignal:
    """One past bar on which a method's entry setup fired — a chart overlay marker.

    Where ``MethodResult`` is a single point-in-time read (score + how recently
    the setup last fired), this is the *time series* of firings that the stock
    chart draws as markers, one per method.

    Attributes:
        date:  The session the setup fired on.
        label: Short on-chart tag (e.g. "Spring", "Trend Template").
        type:  ``"Bullish"`` or ``"Bearish"``. Every setup we ship is a
               long entry ("Bullish"); VSA also surfaces the bearish
               structures that shape its rating.
    """

    date: date
    label: str
    type: str


@dataclass(frozen=True)
class MethodResult:
    """One trading method's read of a single stock, as of its last bar.

    Attributes:
        score:       0–100 attractiveness for THIS method, used by the
                     cross-method combined ranking. 50 is the neutral middle
                     for signed methods (VSA); for a checklist method it is
                     simply "how much of the setup is currently satisfied".
        days_since:  Age in days of the most recent bar on which the method's
                     entry setup fired (``NEVER_FIRED`` when it did not fire in
                     the evaluated window). ``fired`` is exactly
                     ``days_since == 0``.
        fired:       Did the setup trigger on the most recent bar?
        detail:      One short human-readable note (e.g. "6/7 rules",
                     "Strong Buy"); optional.
        available:   ``False`` when the stock has too little history to
                     evaluate this method at all — ``score`` / ``fired`` are
                     then meaningless and callers should render a blank.
    """

    score: int
    days_since: int = NEVER_FIRED
    fired: bool = False
    detail: str | None = None
    available: bool = True

    @classmethod
    def unavailable(cls, detail: str | None = None) -> MethodResult:
        """A "cannot evaluate this stock" result (too little history, etc.)."""
        return cls(
            score=0, days_since=NEVER_FIRED, fired=False, detail=detail, available=False
        )


class TradingMethod(ABC):
    """A pluggable, mechanical, end-of-day trading method.

    Subclasses set the metadata class attributes and implement ``evaluate``.
    They must be pure (no I/O) and long-only for now (see ``direction``).
    """

    #: Stable slug used in the API, cache keys and the frontend (e.g. "vsa").
    id: str
    #: Display/registration order (lower first). Makes the UI order explicit
    #: and independent of import order. VSA leads at 10.
    order: int = 100
    #: Short display name shown as the column header (e.g. "VSA rating").
    name: str
    #: One-paragraph plain-language explainer shown in the UI.
    description: str
    #: Where the method comes from (book / paper / site) — the evidence trail.
    source: str
    #: A link to that source, or ``None``.
    source_url: str | None = None
    #: "Bullish" — every method we ship is a long-only setup for now.
    direction: str = "Bullish"

    @abstractmethod
    def evaluate(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> MethodResult:
        """Evaluate the method on one stock's chronological OHLCV history.

        ``bars`` is the full fetched window (up to ~52 weeks, oldest first);
        the method slices out however much it needs. ``config`` carries the
        user's VSA settings and is used only by methods built on the VSA
        engine — others ignore it.

        Must never raise on malformed or short input: return
        ``MethodResult.unavailable()`` instead, so one bad stock can never
        break a whole scan.
        """
        raise NotImplementedError

    def signals(
        self,
        bars: Sequence[StooqDailyQuote],
        config: VsaConfig | None = None,
    ) -> list[MethodSignal]:
        """Every bar in ``bars`` on which this method's setup fired, oldest first.

        Powers the stock chart's per-method overlay markers, so the user can
        see *where in history* each method would have triggered — not just its
        latest read. The default is an empty list (a method with only a
        point-in-time score); methods with per-bar events override this.

        Like ``evaluate``, it must never raise on short or malformed input —
        return ``[]`` instead.
        """
        return []


# ── Registry ──────────────────────────────────────────────────────────────────

# Registration order is the display order (VSA first). ``__init__`` imports the
# concrete method modules in the intended order, and each ``@register_method``
# appends to this dict as it is imported.
_REGISTRY: dict[str, TradingMethod] = {}


def register_method(cls: type[TradingMethod]) -> type[TradingMethod]:
    """Class decorator: instantiate a method and add it to the global registry.

    Raises on a duplicate id so two methods can never silently collide.
    """
    instance = cls()
    if not getattr(instance, "id", None):
        raise ValueError(f"{cls.__name__} must define a non-empty 'id'.")
    if instance.id in _REGISTRY:
        raise ValueError(f"Duplicate trading-method id: {instance.id!r}")
    _REGISTRY[instance.id] = instance
    return cls


def all_methods() -> list[TradingMethod]:
    """Every registered method, in display order (by ``order`` then ``id``)."""
    return sorted(_REGISTRY.values(), key=lambda m: (m.order, m.id))


def method_ids() -> list[str]:
    """Every registered method id, in display order."""
    return [m.id for m in all_methods()]


def get_method(method_id: str) -> TradingMethod | None:
    """Look up one method by id, or ``None`` if unknown."""
    return _REGISTRY.get(method_id)
