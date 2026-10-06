"""What theory says each measurement *should* do — the Phase-1 coefficient review.

Plan §15, task 1.3: every logistic weight is set beside the sign the source
material expects. A weight pointing the other way is investigated **as a
possible data bug first**, and only then read as a finding (the VSA rating's
inversion on GPW history, ``VSA-PHASE-ANALYSIS.md`` §7, is the precedent).

Only features with a clear expectation are listed. A market-wide value (the
``reg_*`` regime columns) has **no** linear expectation for L1: L1 compares
stocks with each other on the same day, so a number every stock shares that
day cannot say which of them wins. Such values can matter only through
interactions, which Phase 2's trees can learn and a logistic regression
cannot.
"""

from __future__ import annotations

#: feature → (expected sign, why)
EXPECTED_SIGNS: dict[str, tuple[int, str]] = {
    "vsa_rating": (+1, "the app's VSA rating — higher is meant to be more bullish"),
    "vsa_net": (+1, "the decayed VSA signal balance behind the rating"),
    "vsa_verdict": (+1, "the verdict badge (Strong Sell −2 … Strong Buy +2)"),
    "vsa_spring5": (+1, "Spring: supply tested below support (Master the Markets)"),
    "vsa_test5": (+1, "Successful Test: no supply on a dip (Master the Markets)"),
    "vsa_sos5": (+1, "Sign of Strength (Master the Markets)"),
    "vsa_upthrust5": (-1, "Upthrust: weakness after a rise (Master the Markets)"),
    "vsa_nodemand5": (-1, "No Demand (Master the Markets)"),
    "vsa_sow5": (-1, "Sign of Weakness (Master the Markets)"),
    "phase_accumulation": (+1, "accumulation background (Wyckoff)"),
    "phase_markup": (+1, "mark-up background (Wyckoff)"),
    "phase_distribution": (-1, "distribution background (Wyckoff)"),
    "phase_markdown": (-1, "mark-down background (Wyckoff)"),
    "trend_ctx": (+1, "the engine's background trend is up"),
    "weekly_rating": (+1, "the higher timeframe is bullish"),
    "weekly_agree": (+1, "the weekly read confirms the daily one"),
    "rs_pct": (+1, "relative strength / momentum (O'Neil, Minervini; Jegadeesh & Titman 1993)"),
    "mom_12_1_pct": (+1, "12-1 momentum (Jegadeesh & Titman 1993)"),
    "dist_52w_high": (+1, "nearness to the 52-week high (George & Hwang 2004)"),
    "m_minervini_fired5": (+1, "a long setup fired recently"),
    "m_breakout_fired5": (+1, "a long setup fired recently"),
    "m_glinicki_fired5": (+1, "a long setup fired recently"),
    "m_vsa4_fired5": (+1, "a long setup fired recently"),
    "m_weinstein_fired5": (+1, "a long setup fired recently"),
    "m_vsa4_bear5": (-1, "VSA V4's weakness mirror fired recently"),
    "h_confluence": (+1, "several methods agree"),
    "zero_vol_60": (-1, "untraded sessions — an illiquid or halted stock"),
}


def verdict(feature: str, weight: float) -> str:
    """"✓" when the weight points the expected way, "✗" when not, "—" when no view."""
    expected = EXPECTED_SIGNS.get(feature)
    if expected is None or weight == 0:
        return "—"
    return "✓" if (weight > 0) == (expected[0] > 0) else "✗"
