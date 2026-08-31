---
name: add-trading-scanner
description: >-
  Research, vet, and add a new trading-method scanner to StockPilot (the VSA/GPW
  stock app in this repo) — a screen that computes ONE proven trading strategy
  across every tracked company and displays the matches, in the same shape as
  the existing /volume-surge scanner. Use this whenever the user wants to find or
  add a trading method, strategy, setup, pattern, or "trade" to the app: e.g.
  "find a good momentum strategy and add it", "add a 52-week breakout scanner",
  "build a Minervini/VCP screen", "add an algorithm that flags <pattern> for all
  stocks", or even a bare "find me a good trade and add it" / "add a new scanner".
  Covers both halves — sourcing a method from traders with verifiable track
  records and vetting it, then reducing it to mechanical end-of-day rules,
  back-testing it on stored GPW history, and scaffolding the full backend service
  + API endpoint + frontend page + docs. Trigger even when the user only says
  "find a trade" or "add a scanner" without naming a specific method, and even if
  they don't say the word "scanner".
---

# Add a trading-method scanner to StockPilot

## What you are building

A **scanner**: one trading method, reduced to objective rules, computed across
**every tracked GPW company**, exposed as a `GET /api/stocks/<name>` endpoint and
a sidebar page — exactly like the existing **`/volume-surge`** scanner. The whole
universe is evaluated; the page lists the companies that currently match (and
carries each row's VSA rating/verdict for context), server-side sorted and
paginated.

This skill has two connected jobs, in order: **(1) find & vet a method**, then
**(2) build it as a scanner** — but only if it passes two hard gates first.

## Two hard gates (check BEFORE writing any code)

These exist because the expensive, wasteful failure is building a whole page for
a method that either can't be computed from our data or doesn't actually work on
GPW. Screen both out early.

1. **Computable on our data.** The method must reduce to objective boolean rules
   over the data we already store: **end-of-day OHLCV bars + the Yahoo
   fundamentals**. If it needs intraday ticks, order-flow/level-2, news reading,
   or human discretion, it **cannot** become a scanner here — say so plainly and
   offer the closest EOD-computable cousin instead (e.g. an intraday breakout →
   a daily 52-week-high / range breakout).
2. **Beats a fair baseline on GPW.** Before shipping a page, back-test the rules
   on our own stored history and confirm the setup's forward return beats the
   stock's own median forward move (see Phase 2). A method that famously works in
   US large-caps may not transfer to the GPW universe. If it doesn't beat the
   baseline, **report that honestly and do not ship a scanner for it** — offer to
   try a different method or a rule tweak.

Never ship a scanner that fails either gate. A screen the owner can't trust is
worse than no screen.

## Phase 1 — Find & vet the method

The full sourcing + vetting playbook already lives in the repo at
**`agent/TRADING-METHODS-RESEARCH.md`** — read it and follow it. In short:

- **Source from durable, evidence-backed places**, not course-selling gurus:
  trading books that codify a full mechanical method (O'Neil CANSLIM, Minervini
  SEPA/VCP, Weinstein stage analysis, Connors RSI-2, Gray's *Quantitative
  Momentum/Value*), academic factor research (SSRN, Alpha Architect), and
  platforms with *verified/backtestable* track records (QuantConnect, Composer,
  Collective2, TipRanks). Use `WebSearch`/`WebFetch` to pull the exact rules and
  the evidence it worked.
- **Vet each candidate**: multi-year record across *both* bull and bear markets;
  risk-adjusted (max drawdown / Sharpe, not headline %); many trades, not a
  lucky few; transparent about losers; and the author earns from trading, not
  from selling the system. Discard anything with "guaranteed", no drawdown, only
  recent months, or an upsell funnel.
- **If the user named no method**, shortlist 3–5 that fit our EOD data and are
  low-effort because they overlap what the app already computes — momentum
  (12-1), 52-week-high breakout (we carry 52-week context), Minervini trend
  template / VCP, Weinstein Stage-2, Connors RSI-2, relative strength vs WIG.

**Output of this phase — get the user to confirm before building:** the chosen
method, its **exact entry rules written as booleans over OHLCV/fundamentals**,
one line of evidence it works, and which columns the page will show. Building
touches ~15 files across backend, frontend and docs, so confirm scope first
(name, rules, and any tunable knobs like thresholds/windows).

## Phase 2 — Prove it on GPW history (the backtest gate)

Reuse the app's existing back-test frame rather than inventing one — the engine
in **`backend-python/app/services/scanner_service.py`** already measures, per
setup occurrence over the stored history, the **forward return over the next
~10 sessions versus the stock's own median forward move** (baseline = skill, not
market drift). Mirror that frame for the new rule:

- Detect the setup on each ticker's stored bars, look forward N sessions, and
  compare against the same per-stock median baseline.
- Report hit-rate and average excess return across the universe. Ship only if it
  meaningfully beats the baseline. Keep the check as a small script or a pytest
  so it's repeatable when thresholds change.

Tell the user the backtest result in plain language before building the UI.

## Phase 3 — Build the scanner

Follow **`references/build-scanner.md`** — it lists every file to touch, in
order, mirroring `/volume-surge` end to end. The codebase evolves, so treat the
current `/volume-surge` implementation as the source of truth: open
`volume_surge_service.py`, its endpoint in `routers/stocks.py`, and
`VolumeSurgePage.tsx` and copy their *current* shape rather than assuming this
recipe is verbatim. Preserve the patterns that already fixed real bugs — the
shared per-ticker history cache key, the standard pre-filters
(liquidity/market-cap/recency), per-ticker error logging after the concurrent
scan (so a mid-scan DB failure can't return an empty 200), and the cache
lock + generation guard.

## Phase 4 — Verify and report

- Backend: run `pytest` and `ruff` via the repo's venv python (see the memory
  note on the dev toolchain — python isn't on PATH; use
  `backend-python/.venv`). Add tests for the new pure metrics function.
- Frontend: `npm run build` in `frontend/` must pass.
- Optionally launch the app (`/run` or `preview_start`) and open the new page to
  confirm it renders and returns rows.
- Update the docs (`CLAUDE.md` API contract + status, `agent/DOCUMENTATION.md`
  §5, `agent/CODEBASE-OVERVIEW.md`) and move the roadmap item (`agent/ROADMAP.md`
  #23) toward Done. Keeping docs in sync is a project rule.
- Report: the method + why it's trustworthy, the backtest number, the new URL,
  and how to reach it from the sidebar.

## Honesty

The owner is not a coder and is trusting these screens with real decisions. If a
method can't be computed from our data, doesn't beat the baseline, or has only
marketing behind it, say so and stop — don't dress a weak idea up as a working
scanner. A truthful "this one didn't hold up on GPW, here's what I'd try instead"
is the valuable answer.
