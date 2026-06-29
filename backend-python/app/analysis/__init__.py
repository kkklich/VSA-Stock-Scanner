"""Analysis package — VSA signal detection and statistical metrics.

This is where the scanner's brain will live. It is intentionally separated from
the data-access (``services``) and transport (``routers``) layers so the maths can
be developed and unit-tested in isolation against plain OHLCV bars.

Planned modules:
    - ``vsa``        — Volume Spread Analysis signal detection (Spring, Upthrust,
                       Test, SOS, SOW, No Demand) and the 0–100 VSA rating with
                       Time Decay.
    - ``statistics`` — descriptive metrics (relative volume, close position within
                       spread, moving medians) and the ranking pre-filters.
"""
