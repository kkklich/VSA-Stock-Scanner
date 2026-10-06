"""The website's Education section stays in step with the trading-method code.

Two things on the website describe the methods in words, and neither can
follow a code change by itself:

* the **Education articles** (``frontend/src/content/*.md`` and ``*.en.md``,
  Polish and English), which quote each method's exact thresholds — "a close
  above the highest high of the previous 50 sessions", "at least 2x the prior
  ten weeks' volume";
* the **Polish method descriptions** (``methodDescriptions`` in
  ``frontend/src/i18n/locales/pl.json``), which translate the English
  ``description`` each method class carries.

This file turns a silent drift into a failing test that says what to update.
It reads the frontend files directly: CI checks out the whole repository, so
``../frontend`` is always there. Added 2026-09-26 with the Education section
(agent/ROADMAP.md #32).

It checks rules, not results: the measured figures the articles quote (hit
rates, edges, firing counts) come from one-off measurements and are dated in
the text, so they are not something a test can recompute.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from pathlib import Path

import pytest

from app.analysis import vsa
from app.analysis.methods import (
    all_methods,
    minervini,
    pocket_pivot,
    volume_breakout,
    vsa_method,
    weinstein,
)
from app.services import ranking_service

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_PL_LOCALE = _FRONTEND / "src" / "i18n" / "locales" / "pl.json"
_REGISTRY = _FRONTEND / "src" / "content" / "education.ts"

# The English description of every method, fingerprinted when its Polish
# translation was last written or reviewed. A mismatch means the English text
# changed. Re-read the method, then update:
#   1. its Polish translation — pl.json, methodDescriptions.<id>;
#   2. if the change is about the rules, its Education article in BOTH
#      languages (frontend/src/content/);
#   3. the fingerprint below (the failure message prints the new one).
ENGLISH_FINGERPRINTS: dict[str, str] = {
    "vsa": "d69e8b0ac4f3791e",
    "minervini": "071ce7d4cb66a877",
    "breakout": "829944bd0ed621e9",
    "glinicki": "b4b04b9239e40d18",
    "vsa3": "6c113f70f3a1488d",
    "vsa4": "75722581663caeec",
    "weinstein": "8eb942649e1041d1",
    "pocket_pivot": "c0deefbdbfaef603",
}

# Every threshold an Education article states, as the article states it. A
# mismatch means the code's rule changed and the article now describes a rule
# the app no longer applies: update the article in BOTH languages, then the
# value here. (Article slug in brackets.)
ARTICLE_RULES: list[tuple[str, object, str, object]] = [
    # [vsa-rating] — the background check, the climax cap and the verdict
    # boundaries (the six patterns' table and the half-life have their own
    # tests below).
    ("vsa-rating", vsa, "_LOW_VOL_MULT", 0.7),
    ("vsa-rating", vsa, "_EXCESSIVE_VOL_MULT", 4.0),
    ("vsa-rating", vsa, "_TREND_LOOKBACK", 30),
    ("vsa-rating", vsa, "_TREND_BAND", 0.03),
    ("vsa-rating", vsa, "_SHALLOW_PENETRATION_SPREADS", 0.5),
    ("vsa-rating", vsa, "_VERDICT_STRONG_NET", 1.2),
    ("vsa-rating", vsa, "_VERDICT_LEAN_NET", 0.45),
    ("vsa-rating", vsa_method, "_ANALYSIS_DAYS", 120),
    # [minervini]
    ("minervini", minervini, "_SMA_SHORT", 50),
    ("minervini", minervini, "_SMA_MID", 150),
    ("minervini", minervini, "_SMA_LONG", 200),
    ("minervini", minervini, "_TREND_LOOKBACK", 20),
    ("minervini", minervini, "_WEEK52", 252),
    ("minervini", minervini, "_MIN_ABOVE_LOW", 0.30),
    ("minervini", minervini, "_MAX_BELOW_HIGH", 0.25),
    ("minervini", minervini, "_RS_RANK_MIN", 70.0),
    ("minervini", minervini, "_RECENCY_SCAN", 90),
    ("minervini", ranking_service, "_RS_OFFSETS", (63, 126, 189, 252)),
    ("minervini", ranking_service, "_RS_WEIGHTS", (0.4, 0.2, 0.2, 0.2)),
    # [volume-breakout]
    ("volume-breakout", volume_breakout, "_LOOKBACK", 50),
    ("volume-breakout", volume_breakout, "_BASELINE", 50),
    ("volume-breakout", volume_breakout, "_VOL_MULT", 1.5),
    ("volume-breakout", volume_breakout, "_VDU_RECENT", 10),
    ("volume-breakout", volume_breakout, "_VDU_PRIOR", 40),
    ("volume-breakout", volume_breakout, "_BASE_MAX_DEPTH", 0.35),
    ("volume-breakout", volume_breakout, "_NEAR_HIGH", 0.15),
    ("volume-breakout", volume_breakout, "_RECENT_FIRED", 10),
    ("volume-breakout", volume_breakout, "_RECENCY_SCAN", 60),
    ("volume-breakout", volume_breakout, "_MIN_BARS", 160),
    # [weinstein]
    ("weinstein", weinstein, "_MA_WEEKS", 30),
    ("weinstein", weinstein, "_BASE_WEEKS", 20),
    ("weinstein", weinstein, "_BASE_MAX_DEPTH", 0.30),
    ("weinstein", weinstein, "_MA_FLAT_WEEKS", 10),
    ("weinstein", weinstein, "_MA_MAX_RISE", 0.10),
    ("weinstein", weinstein, "_VOL_WEEKS", 10),
    ("weinstein", weinstein, "_VOL_MULT", 2.0),
    ("weinstein", weinstein, "_MAX_EXTENSION", 0.20),
    ("weinstein", weinstein, "_RECENT_WEEKS", 4),
    ("weinstein", weinstein, "_MIN_WEEKS", 40),
    # [pocket-pivot]
    ("pocket-pivot", pocket_pivot, "_DOWN_WINDOW", 10),
    ("pocket-pivot", pocket_pivot, "_SMA_FAST", 10),
    ("pocket-pivot", pocket_pivot, "_SMA_MID", 50),
    ("pocket-pivot", pocket_pivot, "_SMA_SLOW", 200),
    ("pocket-pivot", pocket_pivot, "_MA_TOUCH", 0.02),
    ("pocket-pivot", pocket_pivot, "_QUIET_DAYS", 5),
    ("pocket-pivot", pocket_pivot, "_QUIET_BASELINE", 50),
    ("pocket-pivot", pocket_pivot, "_WEDGE_DAYS", 5),
    ("pocket-pivot", pocket_pivot, "_WEDGE_MIN_RISING", 4),
    ("pocket-pivot", pocket_pivot, "_RECENT_FIRED", 10),
    ("pocket-pivot", pocket_pivot, "_RECENCY_SCAN", 60),
    ("pocket-pivot", pocket_pivot, "_MIN_BARS", 200),
]

# The six patterns' default thresholds as the VSA-rating article's table
# states them: (spread multiple, volume multiple, close position, lookback).
_VSA_ARTICLE_TABLE: dict[str, tuple[float, float, float, int]] = {
    "Spring": (1.2, 1.2, 0.6, 20),
    "SOS": (1.5, 1.5, 0.65, 20),
    "Successful Test": (1.0, 0.7, 0.65, 20),
    "Upthrust": (1.2, 1.3, 0.3, 20),
    "SOW": (1.5, 1.5, 0.35, 20),
    "No Demand": (0.7, 0.7, 0.65, 20),
}


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _polish_descriptions() -> dict[str, str]:
    data = json.loads(_PL_LOCALE.read_text(encoding="utf-8"))
    return data.get("methodDescriptions", {})


def _methods_with_articles() -> set[str]:
    """Method ids some Education article explains, read from the registry."""
    source = _REGISTRY.read_text(encoding="utf-8")
    ids: set[str] = set()
    for block in re.findall(r"methodIds:\s*\[([^\]]*)\]", source):
        ids.update(re.findall(r"'([^']+)'", block))
    return ids


def test_every_method_has_a_polish_description() -> None:
    polish = _polish_descriptions()
    missing = [m.id for m in all_methods() if not polish.get(m.id, "").strip()]
    assert not missing, (
        f"No Polish description for {missing}. Add a translation of the method's "
        "English `description` to frontend/src/i18n/locales/pl.json under "
        "methodDescriptions.<id>, and its fingerprint to ENGLISH_FINGERPRINTS here."
    )


@pytest.mark.parametrize("method", all_methods(), ids=lambda m: m.id)
def test_english_description_unchanged_since_translated(method) -> None:
    expected = ENGLISH_FINGERPRINTS.get(method.id)
    actual = _fingerprint(method.description)
    assert expected is not None, (
        f"{method.id} has no recorded fingerprint. Once its Polish description is "
        f'written, add "{method.id}": "{actual}" to ENGLISH_FINGERPRINTS.'
    )
    assert actual == expected, (
        f"The English description of {method.id} changed. Update its Polish "
        f"translation (pl.json, methodDescriptions.{method.id}) and, if the rules "
        "changed, its Education article in both languages; then set its "
        f'fingerprint here to "{actual}".'
    )


def test_every_method_has_an_education_article() -> None:
    covered = _methods_with_articles()
    missing = [m.id for m in all_methods() if m.id not in covered]
    assert not missing, (
        f"No Education article explains {missing}. Write one in Polish and English "
        "(frontend/src/content/<name>.md + <name>.en.md) and register it in "
        "frontend/src/content/education.ts with the method id in `methodIds`."
    )


@pytest.mark.parametrize(
    ("article", "module", "name", "expected"),
    ARTICLE_RULES,
    ids=[f"{a}:{n}" for a, _, n, _ in ARTICLE_RULES],
)
def test_article_rules_match_the_code(article, module, name, expected) -> None:
    actual = getattr(module, name)
    assert actual == expected, (
        f"{module.__name__}.{name} is now {actual!r}, but the '{article}' Education "
        f"article describes {expected!r}. Update the article in BOTH languages "
        f"(frontend/src/content/), then the expected value in ARTICLE_RULES."
    )


def test_vsa_article_table_matches_the_default_thresholds() -> None:
    by_name = {name.value: params for name, params in vsa.DEFAULT_SIGNAL_PARAMS.items()}
    assert set(by_name) == set(_VSA_ARTICLE_TABLE), (
        "The VSA engine's patterns changed; the 'vsa-rating' article's table "
        "lists Spring, SOS, Successful Test, Upthrust, SOW and No Demand."
    )
    for name, (spread, vol, close_pos, lookback) in _VSA_ARTICLE_TABLE.items():
        p = by_name[name]
        assert (p.spread_mult, p.vol_mult, p.close_pos, p.lookback) == (
            spread,
            vol,
            close_pos,
            lookback,
        ), (
            f"The default {name} thresholds changed to {p}; update the table in the "
            "'vsa-rating' article in both languages, then _VSA_ARTICLE_TABLE here."
        )


@pytest.mark.parametrize("func", [vsa.compute_rating, vsa.verdict_from_signals])
def test_vsa_article_half_life_matches(func) -> None:
    # The article: "that weight halves every 30 days".
    default = inspect.signature(func).parameters["half_life_days"].default
    assert default == 30, (
        f"{func.__name__}'s half-life is now {default} days; the 'vsa-rating' "
        "article says 30. Update it in both languages."
    )
