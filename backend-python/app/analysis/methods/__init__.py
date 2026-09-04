"""Trading-method framework: the pluggable engine behind the multi-method list.

Importing this package registers every concrete method (in display order) so
``all_methods()`` / ``get_method()`` see them. Adding a new method is just
dropping a module here and importing it below — no other wiring needed.
"""

from __future__ import annotations

from app.analysis.methods import minervini as _minervini  # noqa: F401
from app.analysis.methods import volume_breakout as _volume_breakout  # noqa: F401
from app.analysis.methods import vsa_glinicki as _vsa_glinicki  # noqa: F401
from app.analysis.methods import vsa_method as _vsa_method  # noqa: F401
from app.analysis.methods.base import (
    NEVER_FIRED,
    MethodResult,
    MethodSignal,
    TradingMethod,
    all_methods,
    get_method,
    method_ids,
    register_method,
)

# The concrete-method modules above are imported for their registration side
# effect (each class uses @register_method). Display order does NOT depend on
# this import order — it comes from each method's `order` attribute, so ruff is
# free to sort these imports.

__all__ = [
    "NEVER_FIRED",
    "MethodResult",
    "MethodSignal",
    "TradingMethod",
    "all_methods",
    "get_method",
    "method_ids",
    "register_method",
]
