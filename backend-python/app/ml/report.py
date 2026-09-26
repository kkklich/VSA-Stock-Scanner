"""Small Markdown helpers for the AI layer's reports (plan §20)."""

from __future__ import annotations

import math
from collections.abc import Sequence


def fmt_pct(value: float | None, digits: int = 1) -> str:
    """A fraction as a percentage (0.523 → "52.3%"); "—" when missing."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value * 100:.{digits}f}%"


def fmt_pp(value: float | None, digits: int = 2) -> str:
    """Percentage points with a sign (1.09 → "+1.09 pp"); "—" when missing."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:+.{digits}f} pp"


def fmt_num(value: float | None, digits: int = 2, signed: bool = False) -> str:
    """A plain number; "—" when missing."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def md_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """A GitHub-flavoured Markdown table."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)
