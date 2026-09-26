"""The VSA program's own 45-bar sample, pinned for the VSA V4 tests.

From ``python/sample_ohlcv.csv`` in the owner's "VSA - kompendium i program
Python" package (2026-09-24). SYNTHETIC EDUCATIONAL DATA, NOT MARKET DATA — it
was built to walk the program through one complete long sequence: a Selling
Climax, a No Supply, a confirming up bar on bar 27 and a trade that reaches its
3R target by a gap on bar 33. The package shipped the result of running it with
the program's defaults (``python/demo_results``); ``DEMO_*`` below are copied
from that ``summary.json`` / ``trades.csv`` so the tests can prove the app runs
the program exactly as shipped.

The original timestamps are one minute apart; the tests re-label them as
consecutive calendar days, which no rule of the program looks at.
Rows are (open, high, low, close, volume).
"""

from __future__ import annotations

SAMPLE_BARS: tuple[tuple[float, float, float, float, int], ...] = (
    (120.1, 120.4, 119.4, 120.0, 100),
    (119.7, 120.0, 119.0, 119.6, 100),
    (119.3, 119.6, 118.6, 119.2, 100),
    (118.9, 119.2, 118.2, 118.8, 100),
    (118.5, 118.8, 117.8, 118.4, 100),
    (118.1, 118.4, 117.4, 118.0, 100),
    (117.7, 118.0, 117.0, 117.6, 100),
    (117.3, 117.6, 116.6, 117.2, 100),
    (116.9, 117.2, 116.2, 116.8, 100),
    (116.5, 116.8, 115.8, 116.4, 100),
    (116.1, 116.4, 115.4, 116.0, 100),
    (115.7, 116.0, 115.0, 115.6, 100),
    (115.3, 115.6, 114.6, 115.2, 100),
    (114.9, 115.2, 114.2, 114.8, 100),
    (114.5, 114.8, 113.8, 114.4, 100),
    (114.1, 114.4, 113.4, 114.0, 100),
    (113.7, 114.0, 113.0, 113.6, 100),
    (113.3, 113.6, 112.6, 113.2, 100),
    (112.9, 113.2, 112.2, 112.8, 100),
    (112.5, 112.8, 111.8, 112.4, 100),
    (112.1, 112.4, 111.4, 112.0, 100),
    (111.7, 112.0, 111.0, 111.6, 100),
    (111.3, 111.6, 110.6, 111.2, 100),
    (110.9, 111.2, 110.2, 110.8, 100),
    (110.5, 110.8, 109.8, 110.4, 100),
    (110.5, 111.2, 109.5, 110.1, 400),
    (110.1, 110.2, 109.55, 109.9, 90),
    (110.0, 111.0, 109.8, 110.8, 200),
    (110.9, 111.35, 110.65, 111.0, 150),
    (111.8, 112.25, 111.55, 111.9, 150),
    (112.7, 113.15, 112.45, 112.8, 150),
    (113.6, 114.05, 113.35, 113.7, 150),
    (114.5, 114.95, 114.25, 114.6, 150),
    (115.4, 115.85, 115.15, 115.5, 150),
    (116.3, 116.75, 116.05, 116.4, 150),
    (117.2, 117.65, 116.95, 117.3, 150),
    (118.1, 118.55, 117.85, 118.2, 150),
    (119.0, 119.45, 118.75, 119.1, 150),
    (119.9, 120.35, 119.65, 120.0, 150),
    (120.8, 121.25, 120.55, 120.9, 150),
    (121.7, 122.15, 121.45, 121.8, 150),
    (122.6, 123.05, 122.35, 122.7, 150),
    (123.5, 123.95, 123.25, 123.6, 150),
    (124.4, 124.85, 124.15, 124.5, 150),
    (125.3, 125.75, 125.05, 125.4, 150),
)

# python/demo_results/summary.json (program defaults: 1 bp commission and
# 1 bp slippage each way, both sides traded).
DEMO_FINAL_EQUITY = 10291.874515766398
DEMO_CLOSED_TRADES = 1
DEMO_LONG_SETUPS = 1
DEMO_SHORT_SETUPS = 0
# python/demo_results/trades.csv
DEMO_SIGNAL_BAR = 27
DEMO_ENTRY_BAR = 28
DEMO_EXIT_BAR = 33
DEMO_EXIT_REASON = "take_profit_gap_open"
DEMO_SIGNAL_NAME = "long:no_supply"
DEMO_ENTRY_PRICE = 110.91109
DEMO_STOP_LOSS = 109.44803571428571
