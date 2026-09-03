# CLAUDE.md — Project Context for StockPilot

> Read this first every session. **All project information and documentation lives in the `agent/` folder** — read **`agent/DOCUMENTATION.md`** for the full specification before writing any code, and skim the reference material there (blueprint, VSA source text).
>
> **Rule:** any new documentation, notes, specs, or reference material about this application **must be created in and kept inside the `agent/` folder**. Do not scatter docs across the repo root.

## What this project is

**StockPilot** is a Volume Spread Analysis (VSA) stock scanner for the **Warsaw Stock Exchange (GPW)**. It ranks GPW-listed stocks by a computed **VSA Rating (0–100)**, shows interactive candlestick charts with VSA signal overlays (Spring, Upthrust, Test, SOS, SOW, No Demand), and surfaces tactical metrics per stock. Data refreshes once daily after the GPW end-of-day close.

The owner (Krzysztof) is **not a coder** — explain decisions in plain language, avoid unnecessary jargon, and don't assume prior knowledge of the toolchain. When something needs a manual step (installing software, registering a domain, setting a secret), spell it out clearly.

## Tech stack

- **Frontend:** React + TypeScript, built with Vite. Charts via TradingView Lightweight Charts. Styling via Tailwind CSS (strict dark mode).
- **Backend:** **Python 3.12 + FastAPI** (Uvicorn/Gunicorn). Data via pandas/numpy; stooq.pl for GPW EOD data (httpx); SQLAlchemy 2.0 + Alembic; APScheduler for the daily job; cachetools for caching; pytest + Ruff.
- **Database:** PostgreSQL + TimescaleDB (time-series).
- **Infra:** Docker + Docker Compose, Nginx reverse proxy, GitHub Actions CI/CD, Cyber_Folks VPS (Ubuntu), Let's Encrypt TLS.

> Backend is **Python, not C#/.NET** (decided 2026-06-29). Full library list and rationale in `agent/DOCUMENTATION.md` §2 / §2.1.

## Repository layout (mono-repo)

```
frontend/         React + TypeScript (Vite) → src/{api,components,hooks,types}
                  + Dockerfile, nginx.conf (production image)
backend-python/   Python + FastAPI Web API  → app/{routers,models,services,analysis,db,jobs,data},
                  alembic/, tests/ + Dockerfile
deploy/           VPS deployment: vps-setup.sh, deploy.sh, backup-db.sh, nginx/stockpilot.conf
docker-compose.prod.yml + .env.prod.example   Production stack (db + api + web)
.github/workflows/   ci.yml (lint/test/build) + deploy.yml (SSH deploy to the VPS)
agent/      ALL project documentation & reference material lives here:
              - DOCUMENTATION.md   Full project specification
              - DEPLOYMENT.md      Step-by-step publish-to-the-internet guide
              - Blueprint (.docx), VSA source text (.pdf), reference images
            (gitignored — do not commit)
```

> Documentation home: the `agent/` folder is the single source of truth for everything written about this app. New docs go here, not in the repo root.

## API contract (do not change without updating DOCUMENTATION.md)

- `GET /api/stocks/ranking` — dashboard feed. Returns ranked `StockRankingItem[]`. Supports `page`, `pageSize` (≤ 500), `settings`, plus server-side sorting/filtering: `sortBy` (one of ticker, name, lastPrice, priceChangePct, currentRating, ratingChange, lastSignal, daysSinceSignal, volume, sector, aiConfidence, combinedScore; default `currentRating`), `sortDir` (`asc`|`desc`, default `desc`), `q` (search ticker/name), `minRating`/`maxRating` (0–100 rating band), `signal` (verdict filter), `sector` (exact sector name, case-insensitive), `maxDaysSinceSignal` (0–999; last signal at most this many sessions ago — also drops stocks with no signal, whose sentinel is 999), `minPrice`/`maxPrice` (PLN), `minVolume` (20-session median volume, shares), `maxDistFrom52wHighPct`/`maxDistFrom52wLowPct` (within N% of the 52-week high/low), `new52wHigh`/`new52wLow` (booleans — the latest session set a fresh 52-week extreme), `tickers` (comma-separated allow-list, e.g. favorites), `methods` (comma-separated trading-method ids that fold into the combined cross-method score and the `combinedScore` sort — unknown ids ignored; empty/absent = all methods). Each row also carries the **pluggable trading-method results** (added 2026-09-01): `methodResults` — a map keyed by method id (`vsa`, `minervini`, …), each `{ methodId, score (0–100), daysSince (999 = not recently), fired, detail, available }` — plus `combinedScore` (mean of the *selected* methods' scores, `null` when the row can evaluate none of them; computed per-request from `methods`). The methods self-register in `app/analysis/methods/` (see `GET /api/stocks/methods`); adding one is writing one class. Note (2026-09-03): the ranking path now feeds each method a universe-wide **relative-strength percentile**, so Minervini's `score`/`detail` on this endpoint reflect its RS rule 8 (scored `/8`, e.g. `"8/8 rules"`) — higher than the standalone `/{ticker}` paths, which have no universe and fall back to the 7 structural rules. Each row also carries the **52-week context**: `distFrom52wHighPct` (≤ 0), `distFrom52wLowPct` (≥ 0), `isNew52wHigh`, `isNew52wLow` — window anchored to the stock's last session, at most 52 weeks of stored history. The two percentages are `null` and both flags `false` when the stored bars do **not** span ~52 weeks (< 330 days between the oldest bar in the window and the last session — a recent listing, a shallow DB, a gappy series): a three-month high must never be reported as a "new 52-week high". All filters are cheap in-memory passes over the cached ranking (used by the `/filters` screener page). The count of all matching rows before pagination is returned in the `X-Total-Count` response header (exposed via CORS). Cached in-process per settings hash, recomputed after daily ingestion.
- `GET /api/stocks/methods` — **trading-method catalogue** (added 2026-09-01) for the dashboard's method selector. Returns `TradingMethodInfo[]` in display order (VSA first): `{ id, name, description, source, sourceUrl, direction }`. Every registered method (`app/analysis/methods/`) appears here automatically; the selector reads it to know which per-method columns it can show.
- `GET /api/stocks/methods/{method_id}/backtest` — **the GPW back-test gate** (added 2026-09-02) for one trading method: proves the method on stored GPW history before its score is trusted with money. Every *long* firing of the method across the tracked universe (from its `signals()`) is judged — forward return over the next `forwardSessions` (3–30, default 10) sessions versus the stock's **own median forward move** (baseline) — and folded into `{ methodId, name, asOf, forwardSessions, scannedCount, signalCount, evaluatedCount, winCount, winRatePct, avgForwardReturnPct, baselineReturnPct, avgExcessReturnPct, rewardRisk, passes, grade, summary, engine }`. The gate `passes` when the setup beat the stock's own baseline **more than 50%** of the time (`winRatePct`) **and** the average edge (`avgExcessReturnPct`) is positive; `grade` is `strong` (winRate ≥ 55% with avg edge ≥ 1.0 pp and `rewardRisk` ≥ 1.2, or `rewardRisk` `null`), `pass`, `fail`, or `insufficient` (< 30 judged firings across the universe — then `passes` is `null`). `rewardRisk` is avg winner magnitude ÷ avg loser magnitude in the baseline-excess frame (`null` when undefined). This is the roadmap's planned **GPW back-test gate**, but **informational only** for now — the ranking does not yet enforce `passes`. Generic — it drives off `TradingMethod.signals`, so it judges every method with no per-method code; 404 on an unknown id. Supports `settings`. Heavy (fetches ~4 years/ticker into its own `backtest-history:` cache); cached per (method, horizon, settings) with a lock + generation guard, so the first call is slow and the rest instant until the next refresh.
- `GET /api/stocks/{ticker}/signals` — chart feed. Returns `{ ticker, history[], vsaSignals[], methodSignals[] }`. Supports `fromDate`, `toDate` (default last 12 months), `settings`. **`methodSignals` (added 2026-09-01)** carries the **per-method chart overlays** for every registered trading method *other than* VSA (whose markers are `vsaSignals`): a list of `{ methodId, name, direction, signals[{date, label, type}] }`, one group per method (empty `signals` = did not fire in the window). These power the stock chart's toggleable per-method marker layers (`ChartMethodLegend` chooser; VSA arrows + one coloured-circle layer per other method; selection persisted in localStorage). The overlays are evaluated on a window extended ~400 days **before** `fromDate` (so trend-following methods like Minervini's 200-day MA have enough run-up) and clipped to the displayed range — `history`, `vsaSignals` and the rating are unaffected and stay exactly the requested window. Each `TradingMethod` supplies its overlay via a new `signals(bars, config)` method (`app/analysis/methods/base.py`; default empty).
- `GET /api/stocks/scanner/stats` — back-test effectiveness per signal type ("success" = beating the stock's own median forward move; winner/loser magnitudes use the same baseline-excess frame). `rewardRisk` is `null` when undefined (wins with no losses, or nothing judged) — the Scanner page renders that as an emerald "—" (best case) and sorts it first. Supports `settings`.
- `GET /api/stocks/{ticker}/fundamentals` — company description + financial ratios + quarterly reports, plus **investment spending** (`capex`, added 2026-07-22 — the same `CapexSummary` object a `/capex` row carries, so the stock page and the screen can never disagree; `null` when Yahoo has no cash-flow statement. A single ticker is cheap enough to fetch live, so a stock page shows capex before the weekly fundamentals pass has run, and persists what it fetched; a company Yahoo has no statement for persists nothing, so that "nothing to find" answer is remembered in the history cache for a day instead of re-fetching on every page view), plus **returns & income** (added 2026-07-21): `priceReturns` (`ytdPct`, `y1Pct`, `y3Pct`, `y5Pct`, `maxPct`, `maxFromDate`) computed from the stored EOD bars by `app/analysis/returns.py` — a horizon is `null` when stored history doesn't reach back that far, and a baseline bar may be at most 2× the horizon old; `ttmRevenue`/`ttmNetIncome` (last four reported quarters summed, `null` unless all four are present); and `metrics.returnOnEquity`/`returnOnAssets` (fractions from Yahoo, 0.184 = 18.4%). Price returns exclude dividends. Requesting this endpoint fetches ~5 years of bars via `_get_quotes`, which **backfills and persists** any history the DB lacks for that ticker. `metrics.dividendYield` is already a **percent** (0.51 = 0.51%) — never rescale it.
- `GET /api/stocks/{ticker}/ai-analysis` — AI insight: second opinion on the rule-detected signals, computed **locally** by the built-in expert-system engine (`app/analysis/ai_insight.py`) — no external AI services or API keys. Returns `{ ticker, asOf, verdict, confidence, summary, signalAssessments[], keyObservations[], engine }`. Supports `settings`.
- `GET /api/stocks/{ticker}/trust-score` — VSA **prediction-accuracy ("trust") score** for one stock: every historical Strong Buy/Strong Sell signal old enough to judge is back-tested (forward return over the next 10 sessions vs. the stock's own median 10-session move as baseline) and folded into a single 0–100 score, shrunk toward the neutral 50 when there are few cases so one lucky signal never scores 100. Returns `{ ticker, asOf, score, grade, horizonSessions, evaluatedCount, goodCount, freshCount, buyEvaluated, buyGood, sellEvaluated, sellGood, baselineReturnPct, avgExcessReturnPct, summary, events[], engine }` (`score` is `null` / `grade: "insufficient"` when fewer than 8 strong signals are old enough to judge). Computed locally by `app/analysis/trust_score.py`; shown in the "Signal Trust Score" card next to AI Insight on the stock-detail page. Supports `settings`.
- `GET /api/stocks/{ticker}/opinion-summary` — **consolidated analytics opinion** (added 2026-09-02, roadmap #24): the stock page's "bottom line" that fuses every other per-stock opinion into one read. Reuses the same local engines the individual cards use — the VSA rating/verdict, the AI Insight second opinion (`ai_insight.py`), the Signal Trust Score (`trust_score.py`) and every registered trading method (`methods/`) — so it can never contradict them; no external AI services. Returns `{ ticker, name, asOf, stance, agreement, headline, summary, sources[], engine }`. `stance` is the consolidated direction (`bullish`/`bearish`/`neutral`/`mixed` — "mixed" when bullish and bearish sources genuinely conflict); `agreement` (0–100) is how strongly the directional sources line up (share of the largest agreeing camp — 100 = unanimous, 50 = evenly split). Each `sources[]` row is `{ key, label, kind, stance, headline, detail, firedRecently }`: **direction** sources vote on the consensus (VSA verdict, AI Insight verdict, and each long-only method — a method leans bullish or stays neutral, never bearish), while the one **reliability** source (the Trust Score) does not vote — it is coloured green (reliable) → red (unreliable) and only modulates the takeaway. The AI verdict's lean is scaled by its confidence; VSA and AI weight 1.0, each method 0.6. Computed by `app/analysis/analytics_summary.py`; shown in the "Analytics summary" card at the top of the stock-detail right column. Supports `settings`. Deterministic; not cached (one cheap fold over already-computed engines).
- `POST /api/stocks/refresh` — starts the **data-refresh pipeline** in the background (Yahoo ingest → ranking recompute with DEFAULT settings → daily rating snapshots saved to DB); returns 202 + status. This and the nightly 18:00 job are the ONLY triggers that pull fresh data from Yahoo. `GET /api/stocks/refresh/status` — same payload `{ state, lastStartedAt, lastRefreshAt, lastError, stocksRanked, dbEnabled }` for polling.
- `GET /api/stocks/{ticker}/rating-history` — stored daily rating snapshots `{ ticker, points[{date, rating, verdict, close}], source }` (the "attractiveness over time" chart). Supports `fromDate`, `toDate` (default last 12 months). Snapshots always use DEFAULT engine settings; when none exist yet the history is computed on the fly (`source: "computed"`).
- `GET /api/stocks/heatmap` — Sector heatmap feed (`/heatmap` page, Finviz-style treemap). Returns `{ asOf, items[] }`; each item: `ticker, name, sector, marketCap, lastPrice, currentRating, lastSignal, change1D, change1M, change1Y, changeMax` (percent changes, `null` when stored history is too short or too gappy — a 1M/1Y baseline may be at most 2× the horizon old; MAX = full stored history). Same pre-filters as the ranking, evaluated on the same 120-day window (stale/suspended stocks are excluded); rating computed on that window too. Supports `settings`; cached per settings hash with a per-key lock (concurrent cold requests share one computation) and a generation guard (a result computed while the nightly refresh cleared the cache is served but not cached).
- `GET /api/stocks/volume-surge` — **unusual-volume scanner** (`/volume-surge` page). Finds stocks whose average volume over the last `recentDays` sessions (1–10, default 3) is at least `minRatio` (1–10, default 1.5) times their own average over the `baselineDays` sessions (10–60, default 20) immediately before — multi-day **relative volume (RVOL)**; the baseline excludes the recent window so a surge can't inflate its own reference. Server-side sorting + pagination: `sortBy` (one of ticker, name, sector, lastPrice, recentAvgVolume, baselineAvgVolume, volumeRatio, lastDayRatio, daysAboveBaseline, priceChangePct, currentRating, lastSignal; default `volumeRatio`), `sortDir` (`asc`|`desc`, default `desc`), `page`, `pageSize` (≤ 500, default 25). Returns `{ asOf, recentDays, baselineDays, minRatio, scannedCount, totalCount, items[] }` (`totalCount` = matching rows before pagination); each item: `ticker, name, sector, lastPrice, recentAvgVolume, baselineAvgVolume, volumeRatio, lastDayRatio, daysAboveBaseline, priceChangePct, currentRating, lastSignal`. Same pre-filters and 120-day window as the ranking (shares its per-ticker history cache). Supports `settings`; the full scan is cached per (screen params, settings hash) with a per-key lock and generation guard like the heatmap — sorting/pagination is a cheap per-request pass. Computed by `app/services/volume_surge_service.py`.
- `GET /api/stocks/{ticker}/volume` — **single-stock volume (RVOL) reading** (added 2026-09-02) for the stock-detail page's "Volume (RVOL)" card. The one-ticker form of `/volume-surge`: the same multi-day relative volume computed with the shared `compute_surge_metrics` helper, so the card and the scanner never disagree. Params `recentDays` (1–10, default 3), `baselineDays` (10–60, default 20). Returns `{ ticker, asOf, recentDays, baselineDays, available, recentAvgVolume, baselineAvgVolume, volumeRatio, lastDayRatio, daysAboveBaseline, priceChangePct, lastVolume }`; `available` is `false` and every figure `null` when the stored history is shorter than `recentDays + baselineDays`. No `settings` (volume is VSA-independent). Fetches the same ~365-day window as the other per-ticker endpoints (shared history cache). Frontend: `VolumeCard` + `useTickerVolume`.
- `GET /api/stocks/capex` — **investment-spending screen** (`/capex` page). How much money each tracked company spends on investing in its own business (capital expenditure — plants, machines, buildings, software). Reads the **database only** (`company_cashflow`, filled by the ingest's weekly fundamentals pass) — never a live fetch, because the screen covers all companies at once. Filters: `q` (search ticker/name), `sector`, `currency` (reporting currency, **default `PLN`**, `all` to lift it — amounts in different currencies are not comparable), `withData` (default `true`; `false` also returns companies with no reported capex). Sorting/pagination: `sortBy` (one of ticker, name, sector, capex, capexTtm, capexAnnual, capexGrowthYoyPct, capexToRevenuePct, capexToOcfPct, operatingCashFlow; default `capex`), `sortDir`, `page`, `pageSize` (≤ 500, default 25). Returns `{ asOf, totalCount, withDataCount, scannedCount, items[] }`; each item: `ticker, name, sector, currency, basis, capex, capexTtm, capexAnnual, annualPeriodEnd, capexPrevAnnual, capexGrowthYoyPct, capexToRevenuePct, capexToOcfPct, operatingCashFlow`. `capex` is **positive money spent** (Yahoo reports it negative) and `basis` says whether it covers the last four quarters (`"ttm"`) or the latest full year (`"annual"`) — both ratios use that same basis. A TTM sum needs all four quarters; a ratio is `null` when its denominator is missing or non-positive. Missing figures are `null`, never `0`. Computed by `app/services/capex_service.py`; the whole screen is cached under `capex:full` with a lock + generation guard, and filter/sort/page is a cheap per-request pass. A **failed DB read answers 503 and is never cached** (an empty screen would otherwise be remembered as "this app has no capex data" for the whole TTL); "no database configured" is a stable state and stays cached. No `settings` parameter (fundamentals, not VSA).
- `settings` (optional, on the analysis endpoints: ranking, signals, scanner/stats, ai-analysis, trust-score, opinion-summary, heatmap, volume-surge) — URL-encoded JSON with the user's per-signal VSA thresholds/toggles from the Scanner page (see `agent/CODEBASE-OVERVIEW.md` §3.1).

Mandatory ranking pre-filters: 20-session median turnover > 100,000 PLN; market cap > 100M PLN (applied when known from `company-details.json`); recency — a ticker whose last bar lags the scan's newest session by more than 10 calendar days (suspended/stale listing) is excluded. The heatmap and volume-surge scans apply the same pre-filters.

Analysis vs. fetch window: ranking, volume-surge and scanner-stats **fetch** ~380 calendar days per ticker (`CONTEXT_HISTORY_DAYS`, needed for the 52-week context) but run every VSA metric on the unchanged **120-day analysis slice** — so the longer fetch never moves a rating. All three share one cached per-ticker history keyed by that fetch window.

## Conventions

- **Colors:** bullish/strength = emerald `#10B981`; bearish/weakness = rose `#F43F5E`. Strict dark mode (`bg-slate-950`/`900`, `text-slate-100`).
- **VSA rating badges:** green > 70, amber/slate neutral, red < 30.
- **TypeScript:** keep shared types in `frontend/src/types/`. No `any` unless unavoidable.
- **Python:** type hints everywhere; Pydantic schemas for all API payloads; format & lint with Ruff; tests with pytest.
- **Mock-first:** build and validate UI against local mock JSON (matching the API payloads in `agent/DOCUMENTATION.md` §5) before wiring real data.
- **Secrets:** never hardcode or commit credentials, SSH keys, or DB passwords. Use environment variables (`pydantic-settings` / `.env`) / GitHub Secrets.
- **CORS:** configure allowed origins explicitly in `app/main.py` via FastAPI `CORSMiddleware`.

## Working agreement (how Claude should operate here)

- Before coding, read `agent/DOCUMENTATION.md` and skim the relevant existing files. Don't duplicate what exists.
- Prefer small, reviewable steps. After scaffolding or a meaningful change, briefly say what changed and what to do next.
- When introducing a tool the owner must install (Node, .NET SDK, Docker), give the exact commands and a one-line reason.
- Keep this file and `agent/DOCUMENTATION.md` in sync. If the API contract, stack, or structure changes, update both. All documentation updates belong in the `agent/` folder.
- If a request is ambiguous (scope, design choice), ask before building rather than guessing.
- Verify before declaring done: for frontend, the app should build/run; for backend, the project should compile. Note anything left untested.

## Current status

**The full as-built state lives in `agent/CODEBASE-OVERVIEW.md` — read that for
details.** Summary (2026-07-03):

- **Fully live, no mock data.** All pages (Dashboard, Watchlist, Scanner,
  Stock detail/Charts) run against the Python backend. The legacy C# `backend/`
  has been removed; `backend-python/` (port 5111, `run-backend-python.bat`) is
  the only backend.
- **Data:** Yahoo Finance (`.WA` tickers) is the primary source, stooq.pl the
  fallback. PostgreSQL stores EOD bars + daily rating snapshots (optional —
  app runs stateless without it). Every list and scan page is served from
  DB/cache. Only three things ever go out to Yahoo: the nightly 18:00 refresh,
  the UI Refresh button (both `RefreshService`,
  `app/services/refresh_service.py`) and — for **one stock at a time** —
  opening a stock page, where `GET /api/stocks/{ticker}/fundamentals` fills in
  what the database is missing for that company: up to ~5 years of price bars
  (for the multi-year returns) and its cash-flow statement (for the capex
  figures). Both are saved, so the second visit costs nothing; a company Yahoo
  has no cash-flow statement for is remembered as such for a day so the page
  stops re-asking.
- **VSA engine is configurable:** the Scanner page's toggles + per-signal
  sliders are the real engine configuration, sent via the `settings` query
  parameter and applied by `app/analysis/vsa.py` (`VsaConfig`). Ranking,
  chart overlays and back-test stats all follow the user's settings.
- **Fundamentals:** the stock-detail page shows live market cap / P/E / EPS /
  dividend yield via `GET /api/stocks/{ticker}/fundamentals`.
- **Rating history (added 2026-07-10):** every refresh stores one VSA rating
  per (ticker, day) in `rating_snapshots`; the stock-detail page charts it
  ("Rating history" card) so the owner can see attractiveness change over time.
- **Sector heatmap (added 2026-07-12):** `/heatmap` page in the sidebar —
  Finviz-style treemap (tile size = market cap, color = VSA rating or
  1D/1M/1Y/MAX price change) fed by `GET /api/stocks/heatmap`.
- **Signal trust score (added 2026-07-13):** the stock-detail page shows a
  "Signal Trust Score" card next to AI Insight — a back-test of this stock's
  own historical Strong Buy/Sell signals rolled into a 0–100 accuracy score
  (`GET /api/stocks/{ticker}/trust-score`, `app/analysis/trust_score.py`).
- **Volume surge scanner (added 2026-07-15):** `/volume-surge` page in the
  sidebar — stocks trading on unusually high volume right now, found by
  multi-day relative volume (RVOL: last few sessions' average volume vs the
  stock's own baseline average before them), shown with the price move over
  the surge window and the VSA rating/verdict for context
  (`GET /api/stocks/volume-surge`, `app/services/volume_surge_service.py`).
- **Filters page / stock screener (added 2026-07-15):** `/filters` page in the
  sidebar — screen the ranking by sector, VSA rating band, signal + signal
  age, price range and minimum volume (all applied server-side by the ranking
  endpoint's filter params), with **named filter presets** saved in
  localStorage and re-runnable in one click.
- **VSA engine review (2026-07-18, follow-ups 2026-07-19):** correctness pass
  verified against the VSA source texts. The verdict badge is now derived
  from the same decayed net score as the rating (no more "rating 97 + Sell"
  contradictions); zero-spread and suspended-stock guards stop phantom
  signals; SOS, the high-volume Spring and SOW reject excessive (climactic)
  volume via an adaptive cap (`max(4×, 1.5 × vol_mult)`, so a raised volume
  slider can never make the rules unsatisfiable; the Upthrust is deliberately
  uncapped); the Successful Test must dip into the lower part of the recent
  range ("area of previous selling") and shares the low-volume Spring's
  shallow-penetration limit, so a deep low-volume breakdown is never read as
  bullish; a recency pre-filter drops suspended/stale listings (last bar
  > 10 days behind the scan's newest session) from ranking, heatmap and
  volume-surge; scanner back-test stats are baseline-adjusted (beat the
  stock's own median move, not zero) with magnitudes in the same
  baseline-excess frame, and reward/risk is null when undefined (shown as
  "—", best case, in the UI); the trust score uses the median edge, stronger
  shrinkage and needs ≥ 8 judged signals for a numeric score; ratings/verdicts
  are keyed to the last session date instead of the calendar day (no weekend
  decay). Trend-context (background) gating added 2026-09-03: bullish
  structures (Spring/Test) are suppressed in a clearly falling background and
  bearish ones (Upthrust/No Demand) in a clearly rising one; SOS now requires
  a genuine break above resistance; and a wide up-bar on climactic volume in
  new-high ground is reclassified as a bearish buying climax (reusing the
  Upthrust marker) instead of being silently dropped. The gate is on by
  default and configurable in code (`VsaConfig.use_trend_context`).
  REMAINING LIMITATION: the background read is a single 30-bar-MA proxy, not
  full Wyckoff accumulation/distribution phase analysis (see `agent/ROADMAP.md`).
- **Volume-scanner verification (2026-07-20):** the RVOL method was checked
  against three independent sources (public scanner references, the VSA
  source text, a first-principles code review) — method confirmed sound.
  Fixes applied: per-ticker error logging after the concurrent scans so a
  mid-scan DB failure can no longer return an empty 200 silently (volume
  surge, ranking, heatmap, scanner stats); the "Price move" tooltip no longer
  claims high volume on a rise is simply strength (buying-climax caveat);
  softened "standard screen"/threshold claims in docstrings; duplicate-row
  guard in the page's infinite scroll; volume-surge endpoint documented in
  `agent/DOCUMENTATION.md` §5. Refinement ideas (median baseline,
  earnings-date flag, bar-level context) in `agent/ROADMAP.md` #15b.
- **52-week context (added 2026-07-21):** every ranking row carries where the
  stock sits in its 52-week range — percent below the high, percent above the
  low, and "new 52-week high/low" flags for a session that set a fresh
  extreme. Sortable columns on the `/filters` page plus a "52-week range"
  select (New high / Within 5% of high / Within 5% of low / New low). The
  ranking, volume-surge and scanner-stats services now fetch ~380 days per
  ticker but still analyse the same 120-day slice, so no rating changed. A
  stock whose stored bars do not actually cover ~52 weeks (< 330 days) shows
  blanks instead of numbers — otherwise its three-month high would be
  advertised on the screener as a fresh 52-week high.
- **Returns & income on the fundamentals card (added 2026-07-21):** the
  stock-detail card now has a "Price return" section (this year / 1Y / 3Y /
  5Y / since-first-stored-bar, computed from stored bars by
  `app/analysis/returns.py`, dividends excluded) and an "Income" section
  (trailing-12-month revenue and net income summed from the last four
  quarters, plus ROE/ROA). Opening a stock page backfills that ticker's
  history to ~5 years once, so the multi-year returns are real rather than
  blank. Fixed at the same time: the dividend yield was displayed 100× too
  high for any stock yielding under 1% (KGHM showed 51% instead of 0.51%) —
  Yahoo's value is already a percent and must not be rescaled.
- **Deployment (added 2026-07-22):** the app can now be published to the
  Cyber_Folks VPS. `docker-compose.prod.yml` runs three containers —
  `db` (postgres:16-alpine, volume `pgdata`), `api` (python:3.12-slim,
  **single Uvicorn worker** because the scheduler + caches are in-process),
  `web` (Node build → Nginx serving `dist/` and proxying `/api` to the API, so
  the browser is same-origin and CORS is never exercised). Only `web` is
  published, to `127.0.0.1:8080`; the host's Nginx + Certbot terminate TLS
  (`deploy/nginx/stockpilot.conf`). One-time server prep is
  `deploy/vps-setup.sh`; deploys are `deploy/deploy.sh` (also invoked over SSH
  by `.github/workflows/deploy.yml`); `deploy/backup-db.sh` dumps the DB.
  `.env.prod` (gitignored) holds `DOMAIN` + `POSTGRES_PASSWORD`. **The owner's
  walkthrough is `agent/DEPLOYMENT.md`** — read it before changing any deploy
  file, and keep it in sync with `agent/DOCUMENTATION.md` §9.
- **Wider GPW coverage (2026-07-22):** the tracked universe grew from 193 to
  **290 companies** — Dadelo (`dad`), Bank Handlowy, Mo-BRUK, Sygnity, Ryvu,
  MLP Group, Onde, Grupa Pracuj, DataWalk, Lubawa, Wittchen and ~85 more, each
  verified against Yahoo Finance before being added to
  `app/data/gpw-companies.json` (+ enriched `company-details.json`).
- **Scroll changes the chart range (2026-07-22):** on the stock-detail chart,
  scrolling/zooming out past the loaded history steps up to the next range
  (3M → 6M → 1Y → 2Y → MAX) and zooming in steps back down — the 3M/6M/1Y/2Y/MAX
  buttons still work and stay in sync. See `StockChart`'s `onSpanSettled` prop.
- **Schema drift guard:** `_ADDED_COLUMNS` in `app/main.py` applies
  `ALTER TABLE … ADD COLUMN IF NOT EXISTS` on startup for columns added to
  tables that already exist (`create_all` only creates whole missing tables).
  The owner never has to run a migration by hand; the equivalent Alembic
  revision is kept in `alembic/versions/` for managed deployments.
- **Investment spending / capex (added 2026-07-22):** `/capex` page in the
  sidebar ("Investment") — how much money each company puts into its own
  business, biggest investor first: capex over the last four quarters (or the
  latest full year, marked FY), change vs last year, capex as % of revenue
  (capital intensity) and as % of operating cash flow (above 100% = investing
  more than the business generates). Data comes from the Yahoo cash-flow
  statement the app already had access to — no new provider — stored in the
  new `company_cashflow` table by the ingest's weekly fundamentals pass and
  served from the DB (`GET /api/stocks/capex`,
  `app/services/capex_service.py`). Coverage is real but partial (~95% of
  companies have an annual figure, ~82% a trailing-12-month one); missing
  values stay blank instead of becoming zero. Reporting currency is stored
  with every figure and the screen defaults to złoty reporters, because
  580bn HUF is far less money than 30bn PLN and mixing them in one sorted
  column is nonsense. The same numbers appear in an "Investment (capex)"
  section of the stock-detail fundamentals card.
- **Pluggable trading-method framework (added 2026-09-01, roadmap 23a):** the
  generic engine is built first, so adding a trading method is *just writing one
  class*. `app/analysis/methods/` holds a `TradingMethod` base + a self-register
  registry (`base.py`); each method answers one pure question — *does this
  mechanical setup fire on this stock's EOD bars today, and did it fire
  recently?* — plus a 0–100 score and self-describing metadata (name,
  description, evidence source). **VSA is refactored to be a member of this list**
  (`vsa_method.py`), not a hard-coded special case, and the first concrete
  example is the **Minervini Trend Template** (`minervini.py`; Mark Minervini,
  *Trade Like a Stock Market Wizard* — price/moving-average structure, rules
  1–7, plus **rule 8 (cross-sectional RS-rank ≥ 70)** since 2026-09-03: the
  ranking pre-computes each stock's relative strength (IBD-style blended
  3/6/9/12-month return) as a 0–100 universe percentile and folds it into the
  score, so the ranking path scores `/8` and only top-30%-RS stocks reach a
  full 100; the standalone/single-stock path (no universe) falls back to the
  7 structural rules `/7`. `fired`/recency stay structural. A GPW back-test
  gate is still a planned follow-up. A second example, **Volume Breakout**
  (`volume_breakout.py`, id `breakout`; added 2026-09-02), is the
  volume-confirmed base breakout of O'Neil (CANSLIM) and Minervini (VCP): a
  close above the highest high of the prior 50 sessions on volume ≥ 1.5× the
  prior-50-session average, closing strong — and, since 2026-09-03, **only out
  of a real base**: firing now also requires volume to have dried up into the
  pivot (measured on the pre-breakout bar) and the prior base to be tight
  (≤ 35% deep), so news gaps and vertical trend-continuation no longer fire.
  Volume-based, medium-term, long-only (same "needs a GPW back-test before it
  guides money" caveat as Minervini). The
  ranking computes every method's result per stock (baked into
  the cache), exposes them as `methodResults` + a `combinedScore`, and the
  Dashboard now shows a **method selector (multi-select)**, one **column per
  selected method** (score + a "fired recently" chip) and a **Combined column**
  that ranks companies across all the chosen methods (`GET /api/stocks/methods`,
  ranking `methods` param + `combinedScore` sort; frontend `MethodPicker`,
  `MethodCells`, `useMethods`). This supersedes the "one page per method"
  default for methods added under this framework.
- **Trading methods on the stock chart (added 2026-09-01):** the stock-detail
  chart now overlays each trading method's firing history as markers and lets
  the user choose which methods are visible. VSA keeps its arrow markers; every
  other method (Minervini + Volume Breakout today) is a coloured-circle layer,
  toggled from an on-chart chooser/legend (`ChartMethodLegend`, selection
  persisted in localStorage). Backend: each `TradingMethod` gained a
  `signals(bars, config)` overlay method (`app/analysis/methods/base.py`, default
  empty; VSA reuses `detect_signals`, Minervini marks each bar the 7/7 template
  turns on, Volume Breakout marks the first bar of each breakout), and
  `GET /{ticker}/signals` now returns `methodSignals` (see API contract).
  Overlays are computed on a window extended ~400 days before the display range
  and clipped to it, so a short (3M/6M) chart still shows Minervini markers
  without changing the candles/VSA/rating.
- **Consolidated analytics summary (added 2026-09-02, roadmap #24):** the
  stock-detail page now leads its right column with an **"Analytics summary"**
  card — the *bottom line* that pulls the app's separate opinions together
  instead of making the reader assemble them from four cards. `GET
  /api/stocks/{ticker}/opinion-summary` (`app/analysis/analytics_summary.py`)
  reuses the same local engines the individual cards use — the VSA
  rating/verdict, the AI Insight second opinion, the Signal Trust Score and
  every trading method — and folds them into one **stance**
  (bullish/bearish/neutral/**mixed**), an **agreement** score (how strongly the
  signals line up), a one-line takeaway and a plain-language paragraph
  reconciling them (where they agree, where they conflict, and how much to
  trust the VSA calls on this stock). Direction sources (VSA, AI, each long-only
  method) vote on the consensus; the Trust Score is a *reliability* gauge that
  doesn't vote but tempers the takeaway. Deterministic and local — no external
  AI services — so the summary can never contradict the cards it summarises.
  Frontend: `AnalyticsSummaryCard`, `useOpinionSummary`.
- **Volume & investment on the stock page (added 2026-09-02):** the stock-detail
  page now carries the `/volume-surge` and `/capex` information for the one
  stock. A new **Volume (RVOL) card** shows the stock's multi-day relative
  volume — recent vs baseline average volume, the ratio, the latest-day RVOL,
  sessions above baseline and the price move over the window — from the new
  `GET /api/stocks/{ticker}/volume` endpoint, which reuses the volume-surge
  service's `compute_surge_metrics` so the card and the scanner always agree
  (`VolumeCard`, `useTickerVolume`). Investment spending moved out of the
  cramped Fundamentals section into its own **Investment (capex) card**, fuller
  than before (adds operating cash flow) and fed the same fundamentals payload
  the Fundamentals card uses — the page fetches fundamentals once and shares it,
  so no extra request (`InvestmentCard`; `useFundamentals` lifted to the page).
- **Tests:** backend `pytest` — 381 passing (the 2026-09-03 trading-method
  refactor adds trend-context / SOS-resistance / buying-climax tests to
  `tests/test_vsa.py`, plus Minervini RS-rank, 52-week-window and Volume
  Breakout base-gating tests to `tests/test_methods.py`; earlier:
  `TestVolumeBreakout`, `tests/test_method_backtest.py` for the generic GPW
  back-test gate, and `TestGetMethodBacktest` in `tests/test_api.py`); frontend
  `npm run build` passes and `vitest` has 20 passing.
  Layout is responsive (sidebar drawer below `lg`; every list/screener page —
  Dashboard, Watchlist, Filters, Volume Surge, Capex — swaps its wide data table
  for a stacked card list below `lg`, so phones and tablets never scroll
  sideways; the full tables return at `lg`+).
- **Known gaps:** Settings page is a placeholder; favorites & filter presets
  are localStorage-only; frontend unit coverage is still thin (a handful of
  component/lib tests); see `agent/ROADMAP.md`.
- **Feature checklist:** `agent/FEATURE-CHECKLIST.md` — done/not-done list of
  all features, incl. planned "popular scanner" additions (2026-07-09).

---
*Last updated: 2026-09-03 (**Trading-method audit + Tier-1/Tier-2 refactor.** Each method was verified against its canonical source (VSA → Tom Williams *Master the Markets*; Minervini → *Trade Like a Stock Market Wizard*; Volume Breakout → O'Neil CANSLIM + Minervini VCP). Tier-1 bug fixes: Volume Breakout's two dead firing rules removed + zero-range strong-close fixed; Minervini's truncated 52-week window + left-edge chart marker fixed; VSA warm-up comment corrected. Tier-2 methodology upgrades (these shift ratings — a data refresh is advisable): VSA trend-context/background gate (`VsaConfig.use_trend_context`, on by default) + SOS resistance-break + climactic-volume reclassification; Minervini rule 8 (universe RS-rank ≥ 70) in the ranking path; Volume Breakout now fires only out of a real, tight base. Backend `pytest` 361 → 381 green. Previously: Generic **GPW back-test gate** — `app/services/method_backtest_service.py` + `GET /api/stocks/methods/{id}/backtest` — proves any trading method on stored GPW history via its `signals()`: judges every long firing's forward return vs the stock's own median move and `passes` when it beat that baseline > 50% of the time with a positive average edge (informational only for now — the ranking does not yet enforce it). Earlier same day: Volume Breakout trading method (`volume_breakout.py`, id `breakout`); single-stock Volume (RVOL) + Investment (capex) cards + `/{ticker}/volume`; consolidated analytics-opinion summary card + `/opinion-summary` — roadmap #24.)*
