"""Runtime policy for archived trading methods, shared by every application path."""

# Disabled at the owner's request (2026-10-29). Keep their implementations and
# algorithm tests for reference, but do not advertise, rank, backtest or draw
# these methods in the running application. VSA V4 stays active.
# To reactivate a method, remove its id here and restore the matching UI flag
# in frontend/src/lib/methodStatus.ts. Classic VSA also owns the legacy rating,
# scanner, weekly rating, AI/trust panels and historical rating snapshots.
INACTIVE_METHOD_IDS = frozenset({"vsa", "glinicki", "vsa3"})


def is_method_active(method_id: str) -> bool:
    return method_id not in INACTIVE_METHOD_IDS
