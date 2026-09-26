"""The owner's VSA program, vendored: the engine behind the "VSA V4" method.

Krzysztof supplied it on 2026-09-24 as ``VSA - kompendium i program Python``:
a written compendium of Rafał Glinicki's 30-lesson VSA course and his four 2018
webinars (``kompendium.md``, marked [K] course / [M] map / [F] formalisation /
[L] gap), plus a standard-library Python program that formalises it — 15 named
VSA signals and the WFO on both sides, the lesson 21/23 sequence
(strength → No Supply/Test → confirmation) and a single-position trade
simulator. Its 14 unit tests and 8 independent checks travel with it
(``tests/test_vsa4_program.py``).

Files, and how each differs from the package:

* ``engine.py``   — python/engine.py (SHA-256 16a7a08f...). Detection and
  sequence logic unchanged; a few lines marked ``[StockPilot]`` REPORT the
  sequence state the function already keeps (``long_background``,
  ``long_setup_pending``, the short twins, ``setup_primary_signal``).
* ``backtest.py`` — python/backtest.py (SHA-256 145640aa...). Import only.
* ``cli.py``      — python/vsa.py (SHA-256 1dff4a4a...). Imports only.
* ``adapter.py``  — new: StockPilot bars in, the program's results out.

Kept deliberately close to the originals (Ruff is told to leave the three
vendored files alone in ``pyproject.toml``) so that a later version of the
package can be diffed straight against them.
"""
