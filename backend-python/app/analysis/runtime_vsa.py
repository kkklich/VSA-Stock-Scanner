"""Application entry point for the archived Classic VSA detector.

Services must use this gate rather than call the legacy detector directly.
Its pure implementation in vsa.py remains usable by archived algorithm tests
and explicit offline research; disabling a method must not erase its code.
"""
from collections.abc import Sequence

from app.analysis import vsa
from app.analysis.method_status import is_method_active
from app.models import StooqDailyQuote


def detect_signals(
    bars: Sequence[StooqDailyQuote], config: vsa.VsaConfig | None = None
) -> list[vsa.VsaSignal]:
    # Short-circuit before building dataframes or calculating any classic VSA
    # features. Compatibility fields stay neutral; the UI hides those fields.
    if not is_method_active("vsa"):
        return []
    return vsa.detect_signals(bars, config)
