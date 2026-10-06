# CLAUDE.md — Project Context for StockPilot

> Read this first every session. **All project information and documentation lives in the `agent/` folder** — read **`agent/DOCUMENTATION.md`** for the full specification before writing any code, and skim the reference material there (blueprint, VSA source text).
>
> **Rule:** any new documentation, notes, specs, or reference material about this application **must be created in and kept inside the `agent/` folder**. Do not scatter docs across the repo root.

## What this project is

**StockPilot** is a Volume Spread Analysis (VSA) stock scanner for the **Warsaw Stock Exchange (GPW)**. It ranks GPW-listed stocks by a computed **VSA Rating (0–100)**, shows interactive candlestick charts with VSA signal overlays (Spring, Upthrust, Test, SOS, SOW, No Demand), and surfaces tactical metrics per stock. Data refreshes once daily after the GPW end-of-day close; **since 2026-09-25, while an exchange is open, its prices (not its ratings) are also refreshed every hour** (see "Live prices" in the API contract). **Since 2026-09-17 it can also track foreign index members** — USA (S&P 500 ∪ NASDAQ-100), Germany (DAX), France (CAC 40), the Netherlands (AEX) and the UK (FTSE 100) — switched on per deployment with `STOCKPILOT_MARKETS` (backend default: GPW only; the production compose file defaults to `all` since 2026-09-22); see "Markets" in the API contract and `agent/MULTI-MARKET-PLAN.md`.

The owner (Krzysztof) is **not a coder** — explain decisions in plain language, avoid unnecessary jargon, and don't assume prior knowledge of the toolchain. When something needs a manual step (installing software, registering a domain, setting a secret), spell it out clearly.

## Tech stack

- **Frontend:** React + TypeScript, built with Vite. Charts via TradingView Lightweight Charts. Styling via Tailwind CSS — **two themes, dark (default) and light**, switched by a CSS-variable palette in `src/index.css`.
- **Backend:** **Python 3.12 + FastAPI** (Uvicorn/Gunicorn). Data via pandas/numpy; stooq.pl for GPW EOD data (httpx); SQLAlchemy 2.0 + Alembic; APScheduler for the daily job; cachetools for caching; pytest + Ruff.
- **Database:** PostgreSQL + TimescaleDB (time-series).
- **Infra:** Docker + Docker Compose, Nginx reverse proxy, GitHub Actions CI/CD, Cyber_Folks VPS (Ubuntu), Let's Encrypt TLS.

> Backend is **Python, not C#/.NET** (decided 2026-06-29). Full library list and rationale in `agent/DOCUMENTATION.md` §2 / §2.1.

## Repository layout (mono-repo)

```
frontend/         React + TypeScript (Vite) → src/{api,components,hooks,types}
                  + Dockerfile, nginx.conf (production image)
backend-python/   Python + FastAPI Web API  → app/{routers,models,services,analysis,db,jobs,data},
                  app/markets.py (market registry), app/data/markets/<id>.json
                  (foreign company lists), app/ml/ (AI research bench — never
                  imported by the running app), scripts/ (build_market_universe.py,
                  ml_*.py),
                  alembic/, tests/ + Dockerfile
deploy/           VPS deployment: vps-setup.sh, deploy.sh, backup-db.sh, ml-run.sh
                  (AI research jobs on the server), nginx/stockpilot.conf
docker-compose.prod.yml + .env.prod.example   Production stack (db + api + web, plus
                  the `ml` job container that only deploy/ml-run.sh starts)
.github/workflows/   ci.yml (lint/test/build; Docker build only if those pass)
                     + deploy.yml (SSH deploy to the VPS — runs only after a
                       green CI run on main, never in parallel with it)
agent/      ALL project documentation & reference material lives here:
              - DOCUMENTATION.md   Full project specification
              - DEPLOYMENT.md      Step-by-step publish-to-the-internet guide
              - MULTI-MARKET-PLAN.md  Foreign markets: plan, decisions, measurements
              - AI-ALGORITHMS-PLAN.md AI / machine-learning layer: research + plan
                                      (roadmap #31 — Phase 0 test bench built)
              - ml/                   the AI bench's design choices, reports,
                                      research log and trial register
              - Blueprint (.docx), VSA source text (.pdf), reference images
            (gitignored — do not commit)
```

> Documentation home: the `agent/` folder is the single source of truth for everything written about this app. New docs go here, not in the repo root.

## API contract (do not change without updating DOCUMENTATION.md)

- **Markets (added 2026-09-17).** A deployment serves the markets named in `STOCKPILOT_MARKETS` (comma-separated ids `gpw`, `us`, `de`, `fr`, `nl`, `uk`, or `all`; default `gpw`; the GPW is always served). **Tickers:** a GPW ticker stays a bare code (`kgh`) — every existing link, favorite and stored bar keeps working — and a foreign one carries a market suffix: `aapl.us`, `brk-b.us`, `sap.de`, `mc.pa`, `asml.as`, `hsba.l` (Yahoo symbols `AAPL`, `BRK-B`, `SAP.DE`, `MC.PA`, `ASML.AS`, `HSBA.L`; `KGH.WA` is also accepted and means `kgh`). A malformed ticker is a 400; a foreign ticker that is not a tracked company on a served market is a 404 **before** anything is downloaded. **`GET /api/stocks/markets`** lists the served markets in display order: `{ id, name, shortName, country, region, exchange, currency, majorCurrency, timezone, tickerSuffix, refreshRun, companyCount, indices[{id, name}] }` (`currency` is the market's usual quote currency — `GBp`, pence, for London; `majorCurrency` the one whole amounts are stated in). **`market` query parameter** on `GET /api/stocks` (company list), `ranking`, `volume-surge`, `scanner/stats`, `heatmap`, `capex` and `methods/{id}/backtest`: absent = `gpw` (an older client gets exactly the old answer); `all` is accepted by the company list, ranking, volume surge (both assembled from the per-market results) and scanner stats (one pooled back-test under its own cache key) and is a 400 on heatmap, capex and the back-test, which compare money or rank stocks against each other and therefore always work within one market; a market the deployment does not serve is a 400 naming the valid ones. Cache keys carry the market. **Unequal sessions (added 2026-09-17).** Every ranking row carries `lastSession` — the date of the bar its figures describe. Exchanges settle hours apart (GPW 17:20 Warsaw, Xetra/Euronext/London ~17:55, the US only at ~22:15 Warsaw, after which the US ingest runs at 23:15), so for roughly five hours each weekday evening a pooled list legitimately holds today's European rows beside yesterday's American ones — and the Dashboard opens sorted by `priceChangePct`, which then compares two different days. Nothing is wrong with the data; the field exists so the UI can say so (`SessionNote`, shown only when the loaded rows disagree). **New payload fields:** ranking/heatmap/volume-surge rows and the company list carry `market` and `currency` (the stock's **own** quote currency — London quotes most lines in pence but Compass and IHG in USD and Metlen in EUR); the company list, `/{ticker}/signals` and `/{ticker}/fundamentals` also carry `exchange`; `fundamentals.metrics.financialCurrency` is the currency the company *reports* in (HSBC: quoted in pence, reports in USD; stored in `company_fundamentals.financial_currency`, alembic `005`); `rating-history` carries `currency`. **Floors** (below) are defined in złoty and applied through each stock's own quote currency with fixed approximate rates (`PLN_PER_UNIT` in `app/markets.py`: USD 3.8, EUR 4.35, GBP 5.1, a penny 0.051). **Money in a pooled list (added 2026-09-17).** Within one market almost every price is in one currency (London's exceptions — Compass and IHG in USD, Metlen in EUR — are converted to pence for the `lastPrice` sort and the price bounds, `price_unit` in `_sort_value` / `_query_ranking`, fixed 2026-09-21); pool several (`market=all`) and they stop being comparable, because London quotes most lines in *pence*. Sorting the raw figures then ranks by the size of the currency's unit rather than by money — 17,760 GBp (≈906 PLN) landed above 6,242.23 USD (≈23,720 PLN), the most expensive stock in the list, at position 12. So **only when markets are pooled**: the `lastPrice` sort key, the `volume` sort key (share count × last close — a share is a consistent unit but a 15-pound line and a 5-złoty line trade wildly different counts for the same money) and the `minPrice`/`maxPrice` bounds are all put on a common złoty scale through the same `PLN_PER_UNIT` rates (`_sort_value(..., pooled=True)` and `_query_ranking(..., pooled=...)` in `app/routers/stocks.py`; the non-raising `to_pln_or_none` in `app/markets.py`, so one row with an unexpected currency sorts last instead of failing the listing). The **published figures are never converted** — a London row still reports `7600.0` / `"GBp"` — only the ordering changes, and the frontend prints an "≈ N PLN" second line under the money columns so the order is legible. With a single market every other key keeps its original, unconverted meaning and a row already in the market's currency keeps its exact figure, so a GPW-only deployment is byte-identical to before. The same rule covers volume-surge's `lastPrice` / `recentAvgVolume` / `baselineAvgVolume`. Heatmap, capex and the back-test are still a 400 on `all` — they compare money in ways a fixed-rate approximation should not paper over. **Unfinished sessions:** a daily bar dated today is dropped until that exchange has closed plus 15 minutes (`Market.session_is_final`) — for the GPW that means no bar for today before 17:20 Warsaw.
- **Live prices while an exchange is open (added 2026-09-25).** Every full hour (`STOCKPILOT_LIVE_PRICES_INTERVAL_MINUTES`, default 60, must divide an hour; `STOCKPILOT_LIVE_PRICES_ENABLED`, default on; scheduled only with a database, like the nightly jobs) each served market **trading at that moment** (`Market.session_in_progress`: weekday, after `open_time` — GPW/Xetra/Euronext 09:00, London 08:00, US 09:30 local — until close + 15 min) gets every tracked stock's **session so far** downloaded (`app/services/live_prices.py`, `YahooFinanceClient.get_session_quote`) and kept **in memory only**. The owner chose **"live prices, ratings at the close"**: ranking rows, heatmap tiles and `/{ticker}/signals` carry `live` = `{ sessionDate, price, open, high, low, volume, previousClose, changePct, asOf, fetchedAt }` (volume `0` = not traded yet today, shown at the previous close, 0%), and while it is attached **`lastPrice`/`priceChangePct` (and the last sparkline point, and a tile's four changes) are today's** — but `lastSession`, the rating, the signal, every method score, `history[]` and every marker stay the last **finished** session's, and nothing unfinished is ever stored or analysed. Attached only while `live.sessionDate > lastSession` on the exchange's current day (the evening run's final bar supersedes it) and on `/signals` only without `toDate`; laid over **before** filters/sorts, per request, never cached. `GET/POST /api/stocks/refresh[/status]` gained `livePricesAt` and `liveMarkets` (`{market: ISO}`), which open pages poll to reload themselves. The Refresh button ends its pipeline with the same step; a restart mid-session downloads at once. Each run is a `job.live` action-log entry (failed = nothing priced or > 10% failed). A market's three largest stocks are asked first — no bar for today from any = holiday/not yet, the rest skipped. Details: `agent/DOCUMENTATION.md` Endpoint 17.
- `GET /api/stocks/ranking` — dashboard feed. Returns ranked `StockRankingItem[]`. Supports `page`, `pageSize` (≤ 500), `settings`, plus server-side sorting/filtering: `sortBy` (one of ticker, name, lastPrice, priceChangePct, currentRating, ratingChange, lastSignal, daysSinceSignal, volume, sector, aiConfidence, weeklyRating, combinedScore; default `currentRating`), `sortDir` (`asc`|`desc`, default `desc`) — **both are comma-separated lists since 2026-09-23** (see "Multi-column sorting" below), `q` (search ticker/name), `minRating`/`maxRating` (0–100 rating band), `signal` (verdict filter), `sector` (exact sector name, case-insensitive), `maxDaysSinceSignal` (0–999; last signal at most this many sessions ago — also drops stocks with no signal, whose sentinel is 999), `minPrice`/`maxPrice` (in the market's own quote currency — PLN for the GPW, pence for London, whose few lines quoted in dollars or euros are converted to it — and **in złoty when markets are pooled**, see "Money in a pooled list" below), `minVolume` (20-session median volume, shares — *not* converted, because a share is the same unit on every market), `maxDistFrom52wHighPct`/`maxDistFrom52wLowPct` (within N% of the 52-week high/low), `new52wHigh`/`new52wLow` (booleans — the latest session set a fresh 52-week extreme), `weeklyConfirms` (boolean — only rows whose weekly VSA verdict agrees with their daily one), `tickers` (comma-separated allow-list, e.g. favorites), `methods` (comma-separated trading-method ids that fold into the combined cross-method score and the `combinedScore` sort — unknown ids ignored; empty/absent = all methods). Each row also carries the **pluggable trading-method results** (added 2026-09-01): `methodResults` — a map keyed by method id (`vsa`, `minervini`, …), each `{ methodId, score (0–100), daysSince (999 = not recently), fired, detail, available }` — plus `combinedScore` (mean of the *selected* methods' scores, `null` when the row can evaluate none of them; computed per-request from `methods`). The methods self-register in `app/analysis/methods/` (see `GET /api/stocks/methods`); adding one is writing one class. Note (2026-09-03): the ranking path now feeds each method a universe-wide **relative-strength percentile**, so Minervini's `score`/`detail` on this endpoint reflect its RS rule 8 (scored `/8`, e.g. `"8/8 rules"`) — higher than the standalone `/{ticker}` paths, which have no universe and fall back to the 7 structural rules. Each row also carries the **52-week context**: `distFrom52wHighPct` (≤ 0), `distFrom52wLowPct` (≥ 0), `isNew52wHigh`, `isNew52wLow` — window anchored to the stock's last session, at most 52 weeks of stored history. The two percentages are `null` and both flags `false` when the stored bars do **not** span ~52 weeks (< 330 days between the oldest bar in the window and the last session — a recent listing, a shallow DB, a gappy series): a three-month high must never be reported as a "new 52-week high". Each row also carries the **multi-timeframe (weekly) confirmation** (added 2026-09-04): `weeklyRating` (0–100), `weeklySignal` (the weekly verdict) and `weeklyAgreement` — `"confirms"` when the weekly verdict leans the same non-neutral way as the daily one, `"conflicts"` when it leans the opposite way, `"neutral"` when either side is Hold. `app/analysis/weekly.py` resamples the stock’s own daily bars into weekly candles (ISO weeks) and runs the SAME VSA engine with the SAME `settings` over them — no new data source and no extra fetch, it reads the ~380-day window the ranking already pulls, and the daily rating/verdict/signals are untouched. All three are `null` when the stored history yields fewer than ~30 weekly bars (`_MIN_WEEKLY_BARS`), so a shaky read from a handful of weekly candles is never published. All filters are cheap in-memory passes over the cached ranking (used by the `/filters` screener page). The count of all matching rows before pagination is returned in the `X-Total-Count` response header (exposed via CORS). Cached in-process per settings hash, recomputed after daily ingestion.
- **Multi-column sorting (added 2026-09-23).** On `ranking`, `volume-surge` and `capex`, `sortBy` and `sortDir` are **comma-separated lists** — at most `MAX_SORT_LEVELS` (3) columns, each with its own direction — so a table sorts by one column and then by another: `sortBy=sector,currentRating&sortDir=asc,desc` is "sector A→Z, best rating first inside each sector". The first column is the visible order; the rest only break its ties. **One value in each is exactly the old behaviour**, so every older client and every bookmarked URL is unaffected. A direction is optional per level and falls back to the endpoint's default. A repeated column is kept once at its first position (the lists are positional, so dropping the echo never shifts a later column onto the duplicate's direction). Each of these is a `400` naming what was wrong: an unknown column, a direction other than `asc`/`desc`, more directions than columns, more than three columns — **note that an invalid `sortDir` now answers `400` instead of FastAPI's `422`**, because it can no longer be declared as a `Literal`. `_parse_sort_levels` + `_apply_sort` in `app/routers/stocks.py`; the ordering is one stable sort per level applied least-significant first, which is what lets every level keep its own direction.
- `GET /api/stocks/methods` — **trading-method catalogue** (added 2026-09-01) for the dashboard's method selector. Returns `TradingMethodInfo[]` in display order (VSA first): `{ id, name, description, source, sourceUrl, direction }`. Every registered method (`app/analysis/methods/`) appears here automatically; the selector reads it to know which per-method columns it can show.
- `GET /api/stocks/methods/{method_id}/backtest` — **the GPW back-test gate** (added 2026-09-02) for one trading method: proves the method on stored GPW history before its score is trusted with money. Every *long* firing of the method across the tracked universe (from its `signals()`) is judged — forward return over the next `forwardSessions` (3–30, default 10) sessions versus the stock's **own median forward move** (baseline) — and folded into `{ methodId, name, asOf, forwardSessions, scannedCount, signalCount, evaluatedCount, winCount, winRatePct, avgForwardReturnPct, baselineReturnPct, avgExcessReturnPct, rewardRisk, passes, grade, summary, engine }`. The gate `passes` when the setup beat the stock's own baseline **more than 50%** of the time (`winRatePct`) **and** the average edge (`avgExcessReturnPct`) is positive; `grade` is `strong` (winRate ≥ 55% with avg edge ≥ 1.0 pp and `rewardRisk` ≥ 1.2, or `rewardRisk` `null`), `pass`, `fail`, or `insufficient` (< 30 judged firings across the universe — then `passes` is `null`). `rewardRisk` is avg winner magnitude ÷ avg loser magnitude in the baseline-excess frame (`null` when undefined). This is the roadmap's planned **GPW back-test gate**, but **informational only** for now — the ranking does not yet enforce `passes`. Generic — it drives off `TradingMethod.signals`, so it judges every method with no per-method code; 404 on an unknown id. Supports `settings`. Heavy (fetches ~4 years/ticker into its own `backtest-history:` cache); cached per (method, horizon, settings) with a lock + generation guard, so the first call is slow and the rest instant until the next refresh.
- `GET /api/stocks/{ticker}/signals` — chart feed. Returns `{ ticker, history[], vsaSignals[], methodSignals[], interval, intraday, historyStart, weeklyRating, weeklySignal, weeklyAgreement }`. Supports `fromDate`, `toDate` (default last 12 months), `settings`, and **`interval`** — the chart's bar size (added 2026-09-05): `30m`, `1h`, `4h`, `1d` (default) or `1w`; an unknown value is a 400 listing the valid ones. VSA is timeframe-agnostic, so the unchanged engine runs over whichever series is picked with the same `settings`. `1d` is the stored EOD bars (exactly as before); `1w` aggregates those into ISO-week candles (`resample_weekly`); `30m`/`1h` are fetched live from Yahoo and **not stored** (the provider caps history at ~60 days and ~730 days respectively); `4h` is aggregated from the `1h` bars, since Yahoo has no 4-hour interval. Grouping never spans the overnight gap, so a GPW session yields two 4h bars with the 17:00 closing auction folded into the afternoon. **The timeframe changes only the chart.** `currentRating`, `ratingChange`, `lastPrice` and `priceChangePct` stay the app's daily read — on a non-daily chart they are computed from a standard ~1-year daily window, because an intraday range is short by nature (five days of 30-minute candles is five daily bars, under the engine's lookback) and would otherwise collapse the page's rating to a neutral 50 on a timeframe switch. `methodSignals` comes back **empty** on any non-daily interval: Minervini's 200-*day* MA and the breakout's 50-*day* base silently become a 2-week MA and a two-day "base" on 30-minute bars — a different rule wearing the method's name. `interval`/`intraday`/`historyStart` report what was actually served (an intraday request beyond the provider's cap is trimmed, and `historyStart` says so). **Bar times:** daily/weekly bars keep the plain `"2026-09-04"` form, so the existing payload is unchanged; intraday bars are moments and carry a full exchange-local timestamp, `"2026-09-04T13:00:00+02:00"` (`vsaSignals[].date` follows the same rule). Intraday is the one chart timeframe that reaches out to Yahoo — one ticker at a time, only when selected, cached per (ticker, interval, window) for 5 minutes (not the 24h end-of-day TTL, which would freeze a 30-minute chart for a whole session). Aggregation + the interval table: `app/analysis/timeframe.py`. **`weeklyRating` / `weeklySignal` / `weeklyAgreement` (added 2026-09-09)** are the same multi-timeframe read the ranking rows carry, from the same `app/analysis/weekly.py` over the same capped 52-week window (so the stock page and the dashboard's "1W" chip can never disagree), computed out of the wide daily window this endpoint already fetches — no extra request. Like the rating, they are a **daily** read and do NOT follow `interval`; the agreement is measured against this endpoint's own daily verdict, and all three are `null` below ~30 weekly bars. **`methodSignals` (added 2026-09-01)** carries the **per-method chart overlays** for every registered trading method *other than* VSA (whose markers are `vsaSignals`): a list of `{ methodId, name, direction, signals[{date, label, type}] }`, one group per method (empty `signals` = did not fire in the window). These power the stock chart's toggleable per-method marker layers (`ChartMethodLegend` chooser; VSA arrows + one layer per other method — a dot in the method's own fixed colour, its label green / red / grey by direction, see "Chart signal colours" in the status below; selection persisted in localStorage). **`type` is `"Bullish"`, `"Bearish"` or `"Watch"` (added 2026-09-22).** The first two are firings — the setup was taken. A **`"Watch"` is not a trade**: it marks a bar the method assessed and *refused*, its `label` carrying the reason (`"Hammer + Shakeout · no sequence, R/R 2.6:1"`), and only VSA V3 emits them today. The chart draws a Watch as a muted **square** in the method's colour, with a grey label, below the bar instead of a solid dot, and the **back-test judges only `"Bullish"` markers** (`method_backtest_service`), so a refused pattern can never enter a statistic. The overlays are evaluated on a window extended ~400 days **before** `fromDate` (so trend-following methods like Minervini's 200-day MA have enough run-up) and clipped to the displayed range — `history`, `vsaSignals` and the rating are unaffected and stay exactly the requested window. Each `TradingMethod` supplies its overlay via a new `signals(bars, config)` method (`app/analysis/methods/base.py`; default empty).
- `GET /api/stocks/scanner/stats` — back-test effectiveness per signal type ("success" = beating the stock's own median forward move; winner/loser magnitudes use the same baseline-excess frame). `rewardRisk` is `null` when undefined (wins with no losses, or nothing judged) — the Scanner page renders that as an emerald "—" (best case) and sorts it first. Supports `settings`.
- `GET /api/stocks/{ticker}/fundamentals` — company description + financial ratios + quarterly reports, plus **investment spending** (`capex`, added 2026-07-22 — the same `CapexSummary` object a `/capex` row carries, so the stock page and the screen can never disagree; `null` when Yahoo has no cash-flow statement. A single ticker is cheap enough to fetch live, so a stock page shows capex before the weekly fundamentals pass has run, and persists what it fetched; a company Yahoo has no statement for persists nothing, so that "nothing to find" answer is remembered in the history cache for a day instead of re-fetching on every page view), plus **returns & income** (added 2026-07-21): `priceReturns` (`ytdPct`, `y1Pct`, `y3Pct`, `y5Pct`, `maxPct`, `maxFromDate`) computed from the stored EOD bars by `app/analysis/returns.py` — a horizon is `null` when stored history doesn't reach back that far, and a baseline bar may be at most 2× the horizon old; `ttmRevenue`/`ttmNetIncome` (last four reported quarters summed, `null` unless all four are present); and `metrics.returnOnEquity`/`returnOnAssets` (fractions from Yahoo, 0.184 = 18.4%). Price returns exclude dividends. Requesting this endpoint fetches ~5 years of bars via `_get_quotes`, which **backfills and persists** any history the DB lacks for that ticker. `metrics.dividendYield` is already a **percent** (0.51 = 0.51%) — never rescale it.
- `GET /api/stocks/{ticker}/ai-analysis` — AI insight: second opinion on the rule-detected signals, computed **locally** by the built-in expert-system engine (`app/analysis/ai_insight.py`) — no external AI services or API keys. Returns `{ ticker, asOf, verdict, confidence, summary, signalAssessments[], keyObservations[], engine }`. Supports `settings`.
- `GET /api/stocks/{ticker}/trust-score` — VSA **prediction-accuracy ("trust") score** for one stock: every historical Strong Buy/Strong Sell signal old enough to judge is back-tested (forward return over the next 10 sessions vs. the stock's own median 10-session move as baseline) and folded into a single 0–100 score, shrunk toward the neutral 50 when there are few cases so one lucky signal never scores 100. Returns `{ ticker, asOf, score, grade, horizonSessions, evaluatedCount, goodCount, freshCount, buyEvaluated, buyGood, sellEvaluated, sellGood, baselineReturnPct, avgExcessReturnPct, summary, events[], engine }` (`score` is `null` / `grade: "insufficient"` when fewer than 8 strong signals are old enough to judge). Computed locally by `app/analysis/trust_score.py`; shown in the "Signal Trust Score" card next to AI Insight on the stock-detail page. Supports `settings`.
- `GET /api/stocks/{ticker}/opinion-summary` — **consolidated analytics opinion** (added 2026-09-02, roadmap #24): the stock page's "bottom line" that fuses every other per-stock opinion into one read. Reuses the same local engines the individual cards use — the VSA rating/verdict, the AI Insight second opinion (`ai_insight.py`), the Signal Trust Score (`trust_score.py`) and every registered trading method (`methods/`) — so it can never contradict them; no external AI services. Returns `{ ticker, name, asOf, stance, agreement, headline, summary, sources[], engine }`. `stance` is the consolidated direction (`bullish`/`bearish`/`neutral`/`mixed` — "mixed" when bullish and bearish sources genuinely conflict); `agreement` (0–100) is how strongly the directional sources line up (share of the largest agreeing camp — 100 = unanimous, 50 = evenly split). Each `sources[]` row is `{ key, label, kind, stance, headline, detail, firedRecently }`: **direction** sources vote on the consensus (VSA verdict, AI Insight verdict, and each long-only method — a method leans bullish or stays neutral, never bearish), while the one **reliability** source (the Trust Score) does not vote — it is coloured green (reliable) → red (unreliable) and only modulates the takeaway. The AI verdict's lean is scaled by its confidence; VSA and AI weight 1.0, each method 0.6. Computed by `app/analysis/analytics_summary.py`; shown in the "Analytics summary" card at the top of the stock-detail right column. Supports `settings`. Deterministic; not cached (one cheap fold over already-computed engines). **Windows (fixed 2026-09-27):** VSA / AI / trust read one year, like their cards; the trading methods read the ranking's `CONTEXT_HISTORY_DAYS` window, so each method row matches its Dashboard column (one year is ~250 sessions — Minervini, needing 252, had read "unavailable" on every stock page).
- `POST /api/stocks/refresh` — starts the **data-refresh pipeline** in the background (Yahoo ingest → ranking recompute with DEFAULT settings → daily rating snapshots saved to DB) for **every served market**; returns 202 + status. This and the nightly runs are the ONLY triggers that pull fresh data from Yahoo for the whole universe. **Nightly runs (since 2026-09-17):** one per group of served markets (`app/markets.py` → `refresh_runs()`): `daily_ingest` — GPW + Europe at `STOCKPILOT_INGEST_HOUR:MINUTE` **Warsaw** time (default 18:00) — and, when the US is served, `daily_ingest_us` at `STOCKPILOT_US_INGEST_HOUR:MINUTE` **New York** time (default 17:15, ≈ 23:15 Warsaw). Each run ingests, re-ranks, snapshots and clears the caches of **its own markets only** (`app/services/market_cache.py`). The weekly fundamentals pass (Mondays, a full download, or an empty table) runs inside each run for its markets; a market downloaded in full for the first time gets its fundamentals without re-fetching the others'. **Start-up check** (`IngestService.bootstrap_plan`): a market where under half the tickers have any stored bar gets the full ~400-day download, one where under 90% carry its newest *finished* session gets a top-up, a current one is left alone (a restart no longer re-downloads everything before 18:00). `GET /api/stocks/refresh/status` — same payload `{ state, lastStartedAt, lastRefreshAt, lastError, stocksRanked, dbEnabled }` for polling.
- `GET /api/stocks/{ticker}/rating-history` — stored daily rating snapshots `{ ticker, points[{date, rating, verdict, close}], source }` (the "attractiveness over time" chart). Supports `fromDate`, `toDate` (default last 12 months). Snapshots always use DEFAULT engine settings; when none exist yet the history is computed on the fly (`source: "computed"`).
- `GET /api/stocks/heatmap` — Sector heatmap feed (`/heatmap` page, Finviz-style treemap). Returns `{ asOf, items[] }`; each item: `ticker, name, sector, marketCap, lastPrice, currentRating, lastSignal, change1D, change1M, change1Y, changeMax` (percent changes, `null` when stored history is too short or too gappy — a 1M/1Y baseline may be at most 2× the horizon old; MAX = full stored history). Items also carry `market` and `currency`. Same pre-filters as the ranking, evaluated on the same 120-day window (stale/suspended stocks are excluded); rating computed on that window too. Since 2026-09-17 the heatmap reads the ranking's cached per-ticker window (`CONTEXT_HISTORY_DAYS`) instead of holding five years per stock, and takes MAX's baseline — the oldest stored close — from one database query (`get_first_closes`; without a database, the oldest bar of the window). Always one market (`market`, `all` is a 400). Supports `settings`; cached per settings hash with a per-key lock (concurrent cold requests share one computation) and a generation guard (a result computed while the nightly refresh cleared the cache is served but not cached).
- `GET /api/stocks/market-overview` — **market breadth + biggest rating movers** (added 2026-09-25, roadmap #5) for the Dashboard's top cards. One pass over the cached ranking rows (nothing new downloaded or stored; reads each row's `ratingChange`, verdict, price change and 52-week flags). Params `market` (an id or `all`), `limit` (1–25, default 5), `settings`. Returns `{ asOf, market, breadth{ total, strongBuy, buy, hold, sell, strongSell, bullishPct, bearishPct, averageRating, advancers, decliners, unchanged, ratingUp, ratingDown, new52wHighs, new52wLows }, moversUp[], moversDown[] }`; a mover is `{ ticker, name, market, currency, lastSession, lastPrice, priceChangePct, previousRating, currentRating, ratingChange, lastSignal }`, only stocks that actually moved are listed. Counts only — no single "market score". Live prices move only the price-based counts. Not cached. `app/services/market_overview.py`; details: `agent/DOCUMENTATION.md` Endpoint 18.
- `GET /api/stocks/volume-surge` — **unusual-volume scanner** (`/volume-surge` page). Finds stocks whose average volume over the last `recentDays` sessions (1–10, default 3) is at least `minRatio` (1–10, default 1.5) times their **typical (median) session** over the `baselineDays` sessions (10–60, default 20) immediately before (median since 2026-09-26, roadmap #15b — the mean before; the field name `baselineAvgVolume` is kept) — multi-day **relative volume (RVOL)**; the baseline excludes the recent window so a surge can't inflate its own reference. Server-side sorting + pagination: `sortBy` (one of ticker, name, sector, lastPrice, recentAvgVolume, baselineAvgVolume, volumeRatio, lastDayRatio, daysAboveBaseline, peakVolumeRatio, priceChangePct, currentRating, lastSignal; default `volumeRatio`), `sortDir` (`asc`|`desc`, default `desc`; both accept up to three comma-separated columns — see "Multi-column sorting"), `page`, `pageSize` (≤ 500, default 25). Returns `{ asOf, recentDays, baselineDays, minRatio, scannedCount, totalCount, items[] }` (`totalCount` = matching rows before pagination); each item: `ticker, name, sector, lastPrice, recentAvgVolume, baselineAvgVolume, volumeRatio, lastDayRatio, daysAboveBaseline, priceChangePct, currentRating, lastSignal` plus, since 2026-09-26, the **surge context**: `daysSinceSignal`, `signalInWindow`, `surgeStart`, the busiest session's `peakDate`/`peakVolumeRatio`/`peakChangePct`/`peakSpreadRatio`/`peakClosePosition`, `breaksHigh`/`breaksLow` (left the baseline's range) and `reportDate` (a company report from the session before the window through its last session; from `company_fundamentals.last_report_date`/`next_report_date`, alembic `008`, filled by the weekly fundamentals pass from Yahoo's `earningsTimestamp*` and merged, never overwritten — `merge_report_dates`). `/{ticker}/fundamentals` `metrics` gained `lastReportDate`/`nextReportDate`. Details: `agent/DOCUMENTATION.md` Endpoint 7. Same pre-filters and 120-day window as the ranking (shares its per-ticker history cache). Supports `settings`; the full scan is cached per (screen params, settings hash) with a per-key lock and generation guard like the heatmap — sorting/pagination is a cheap per-request pass. Computed by `app/services/volume_surge_service.py`.
- `GET /api/stocks/{ticker}/volume` — **single-stock volume (RVOL) reading** (added 2026-09-02) for the stock-detail page's "Volume (RVOL)" card. The one-ticker form of `/volume-surge`: the same multi-day relative volume computed with the shared `compute_surge_metrics` helper, so the card and the scanner never disagree. Params `recentDays` (1–10, default 3), `baselineDays` (10–60, default 20). Returns `{ ticker, asOf, recentDays, baselineDays, available, recentAvgVolume, baselineAvgVolume, volumeRatio, lastDayRatio, daysAboveBaseline, priceChangePct, lastVolume }`; `available` is `false` and every figure `null` when the stored history is shorter than `recentDays + baselineDays`. No `settings` (volume is VSA-independent). Fetches the same ~365-day window as the other per-ticker endpoints (shared history cache). Frontend: `VolumeCard` + `useTickerVolume`.
- `GET /api/stocks/{ticker}/trade-simulation` — **VSA V4 trade simulation** (added 2026-09-24): the owner's own VSA program (vendored, behaviour unchanged, in `app/analysis/vsa4/`) and **its own single-position simulator** replayed over the stock's ~5-year window (the fundamentals endpoint's fetch — same cache key). Each confirmed strength → No Supply/Test → confirmation sequence is entered at the next open with a structural stop and a 3R target, 1% of the account at risk, one position at a time, stop first when stop and target share a bar. Params: `sides` (`long` default — short setups dropped, the app is long-only — or `both`), `commissionBps` / `slippageBps` (0–200, defaults **20 / 5**: stock-like, because the program's 1 bp defaults are for futures). `sides=both&commissionBps=1&slippageBps=1` is the program exactly as shipped. Returns `{ ticker, methodId, currency, fromDate, asOf, barCount, sides, initialCapital, riskPct, rewardRisk, commissionPct, slippagePct, finalEquity, totalReturnPct, maxDrawdownPct, closedTrades, openTrades, wins, losses, winRatePct, profitFactor, avgR, skippedEntries, longSetups, shortSetups, buyHoldReturnPct, trades[{status, direction, signalDate, entryDate, exitDate, setup, entryPrice, stopLoss, takeProfit, exitPrice, exitReason, quantity, netPnl, netR, returnPct}], equity[{date, equity, drawdownPct}], engine }` — `profitFactor` `null` with no loss, the equity curve thinned to ~300 points. `400` bad ticker, `404` no history, `422` bad parameter. `app/services/trade_simulation_service.py`; frontend `TradeSimulationCard` + `useTradeSimulation`.
- `GET /api/stocks/capex` — **investment-spending screen** (`/capex` page). How much money each tracked company spends on investing in its own business (capital expenditure — plants, machines, buildings, software). Reads the **database only** (`company_cashflow`, filled by the ingest's weekly fundamentals pass) — never a live fetch, because the screen covers all companies at once. Filters: `market` (one market, default `gpw`), `q` (search ticker/name), `sector`, `currency` (reporting currency, **default: the market's major currency** — PLN for the GPW, USD for the US, EUR for DE/FR/NL, GBP for the UK — `all` to lift it; amounts in different currencies are not comparable), `withData` (default `true`; `false` also returns companies with no reported capex). Sorting/pagination: `sortBy` (one of ticker, name, sector, capex, capexTtm, capexAnnual, capexGrowthYoyPct, capexToRevenuePct, capexToOcfPct, operatingCashFlow; default `capex`), `sortDir` (both accept up to three comma-separated columns — see "Multi-column sorting"), `page`, `pageSize` (≤ 500, default 25). Returns `{ asOf, totalCount, withDataCount, scannedCount, items[] }`; each item: `ticker, name, sector, market, currency, basis, capex, capexTtm, capexAnnual, annualPeriodEnd, capexPrevAnnual, capexGrowthYoyPct, capexToRevenuePct, capexToOcfPct, operatingCashFlow`. `capex` is **positive money spent** (Yahoo reports it negative) and `basis` says whether it covers the last four quarters (`"ttm"`) or the latest full year (`"annual"`) — both ratios use that same basis. A TTM sum needs all four quarters; a ratio is `null` when its denominator is missing or non-positive. Missing figures are `null`, never `0`. Computed by `app/services/capex_service.py`; the whole screen is cached per market under `capex:{market}:full` with a lock + generation guard, and filter/sort/page is a cheap per-request pass. A **failed DB read answers 503 and is never cached** (an empty screen would otherwise be remembered as "this app has no capex data" for the whole TTL); "no database configured" is a stable state and stays cached. No `settings` parameter (fundamentals, not VSA).
- `GET /api/admin/logs` — **action log / audit trail** (added 2026-09-08). The recorded API calls and background jobs, newest first. Filters: `kind` (`request`|`job`), `action` (case-insensitive substring of the route template or job name), `outcome` (`ok`|`client_error`|`server_error`|`started`|`finished`|`failed`|`skipped`), `fromDate`/`toDate` (a value without a timezone is read as UTC), `page`, `pageSize` (≤ 500, default 50). Returns `{ source, totalCount, page, pageSize, items[] }`, each item `{ timestamp, timestampLocal, requestId, kind, action, outcome, durationMs, method, path, query, statusCode, responseBytes, clientIp, userAgent, detail }`; the pre-pagination count is also in `X-Total-Count`. `action` is the **route template** (`/api/stocks/{ticker}/signals`) so every ticker's calls group together; `path` keeps the concrete one. `source` is `"database"` when the rows came from the `action_logs` table and `"memory"` when they came from the in-process ring buffer (no DB configured — the app is designed to run stateless, so the audit trail must work in that mode too).
- `GET /api/admin/logs/summary` — action-log health + **the latest outcome of every background job** (added 2026-09-08). Param `hours` (1–720, default 24). Returns `{ asOf, source, enabled, filePath, dbActive, retentionDays, recordedCount, dbWrittenCount, droppedCount, windowHours, totalInWindow, byAction, byOutcome, lastJobs[] }`. `lastJobs` is the operational read — the newest entry per job name (`job.refresh`, `job.ingest`, `job.startup`), which is where a silently failing nightly ingest shows up. `job.ingest` reports `failed` only when **nothing was fetched at all** or when **more than 10% of the tracked universe errored** (`refresh_service.ingest_outcome`) — one flaky Yahoo response out of ~290 is an ordinary night, and shouting about it here would train the reader to ignore the one screen meant to surface a genuinely broken run; the counters ride in `detail` either way.
- `GET /api/admin/errors` — **error tracking** (added 2026-09-09). Recent failures, **grouped by what went wrong** — an ingest where 290 tickers fail is one group with `count: 290`, not 290 rows. Params `hours` (1–720, default 24), `limit` (1–200, default 50). Returns `{ asOf, source, windowHours, totalCount, groupCount, trackedSince, items[] }`, each item `{ fingerprint, errorType, message, lastMessage, where, source, count, firstSeen, lastSeen, lastSeenLocal, traceback, context }`. Errors are collected by an `ErrorTrackingHandler` on the **root logger**, so every `logger.error`/`logger.exception` already in the app becomes a tracked error with no call-site change — including failures that never reach an HTTP response. The fingerprint is error type + app source line + message *template* (digits collapsed), which is what does the grouping. Each group is mirrored into the action log as a `kind="error"` entry (throttled to one per group per minute, carrying an `occurrences` count), so it inherits the file, the `action_logs` table and the 30-day prune — **no new table, no migration**. `source` is `"database"` (rebuilt from stored entries, survives restarts) or `"memory"` (this process only). `app/services/error_tracker.py`.
- `GET /api/admin/health` — **system health** (added 2026-09-09): did the refresh run, is the data current, what is failing. Returns `{ asOf, asOfLocal, status, version, uptimeSeconds, protected, ingest, data, errors, log }`. `ingest.status` is `ok`|`running`|`stale`|`failed`|`never` measured against the scheduled 18:00 Europe/Warsaw run — **`stale` = the run came due and nothing happened** (90-minute grace) — with the last run's outcome, trigger, duration and the ingest counters (`fetched`, `skipped`, `failed`, `barsWritten`), `expectedAt`, `ranSinceExpected` and `nextRunAt` (read from the scheduler itself). `data` is read from the **database rather than from what the job claimed**: `latestBarDate`, `tickersCurrent`/`tickersTracked`, `coveragePct`, `barCount`, status `ok`|`updating`|`stale`|`empty`|`disabled`|`error` — a session older than **4 weekdays** or coverage under 90% is `stale`, *unless a refresh is running*, when partial coverage is `updating` (at 18:00 the ingest is legitimately mid-universe). The session age is counted Mon–Fri, not in calendar days: the GPW is shut all weekend, so Friday's bar read on Monday is three calendar days old with nothing wrong, and a Friday-plus-Monday holiday pair (1/3 May, the Corpus Christi bridge) or the 24–26 December cluster used to false-alarm. **Per run and per market (2026-09-17):** `ingest.runs[]` holds one such verdict per nightly run (`runId`, `markets`, each judged against its own schedule and time zone) and the headline `ingest` is the worst of them; `data.markets[]` is `{ market, status, latestBarDate, sessionAgeDays, tickersTracked, tickersWithData, tickersCurrent, coveragePct }` per served market, each measured against its own newest finished session (a US stock without today's bar at 20:00 Warsaw is not behind). With one market the payload is as before: `ingest.runs` stays empty (there is only the one run) and `data.markets` has a single row. `errors` is the 24 h window with the loudest three groups inline; errors only ever raise the overall status to `warn`. `log` reports whether the audit trail itself is recording. `app/services/system_health.py` + `app/db/health_repository.py`.
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`,
  `GET /api/auth/me`, `POST /api/auth/change-password`, `GET /api/auth/config`
  — **optional user accounts** (added 2026-09-22). The site stays public:
  **nothing under `/api/stocks` requires a token** and every page works signed
  out. **Anyone may register** (`STOCKPILOT_REGISTRATION_OPEN`, default true).
  Register/login/refresh return `{ accessToken, refreshToken, tokenType,
  expiresIn, user{ id, email, displayName, role, emailVerified, createdAt,
  lastLoginAt } }`; no password or hash is ever in a response. **Two HS256
  JWTs signed locally** (`app/services/auth.py`): an access token (30 min,
  `Authorization: Bearer …`) and a refresh token (30 days, accepted only by
  `/refresh`) — the `typ` claim is checked on decode, so a refresh token can
  never be replayed as a bearer credential, and both carry `ver` =
  `users.token_version`, which a password change bumps to invalidate every
  earlier token without a server-side store. Passwords are bcrypt, ≥ 8
  characters and ≤ 72 **bytes** (bcrypt ignores the rest, so a longer one is
  refused rather than silently truncated). `GET /config` →
  `{ enabled, registrationOpen, persistentSessions }` tells the UI whether
  accounts work here at all (`enabled: false` with no database → every other
  route answers 503) and whether a restart will sign everyone out
  (`persistentSessions: false` when `STOCKPILOT_JWT_SECRET` is unset).
  **Errors carry a code**: `detail` is `{ code, message }` — `bad_credentials`,
  `email_taken`, `weak_password`, `invalid_email`, `too_many_attempts`,
  `registration_closed`, `accounts_unavailable`, `wrong_current_password`,
  `session_expired`, `not_signed_in`, `account_not_found` — so the frontend
  can show the visitor's own language (`lib/authErrors.ts`) and fall back to
  the English message. "No such account" and "wrong password" answer
  identically, so the form cannot be used to find out who is registered.
  Failed sign-ins are throttled per address **and** per caller IP (10 per 15
  min → 429 + `Retry-After`). Roles are `user`/`admin`, set only from
  `STOCKPILOT_ADMIN_EMAILS` at registration and informational for now
  (`/api/admin/*` still uses its own token). **No e-mail is sent** — no
  address verification, no password reset (`agent/ROADMAP.md` #30).
  Storage: `users`, alembic `006`.
- **`/api/admin/*` access:** when `STOCKPILOT_ADMIN_TOKEN` is set, every admin endpoint requires a matching `X-Admin-Token` header (`secrets.compare_digest`) and answers `401` otherwise; empty leaves them open (right for a laptop, wrong for a public deployment), and `health` reports `protected: false` so the UI can warn. **Set it on the VPS** — these endpoints expose stack traces, file paths and visitor IP addresses.
- `settings` (optional, on the analysis endpoints: ranking, signals, scanner/stats, ai-analysis, trust-score, opinion-summary, heatmap, volume-surge) — URL-encoded JSON with the user's per-signal VSA thresholds/toggles from the Scanner page (see `agent/CODEBASE-OVERVIEW.md` §3.1).

Mandatory ranking pre-filters: 20-session median turnover > 100,000 PLN; market cap > 100M PLN (applied when known — from `company-details.json` for the GPW, from `app/data/markets/<id>.json` for the other markets); both converted from **each stock's own quote currency** (`below_liquidity_floor` / `below_market_cap_floor` in `app/markets.py`); recency — a ticker whose last bar lags the scan's newest session by more than 10 calendar days (suspended/stale listing) is excluded. The heatmap and volume-surge scans apply the same pre-filters.

Analysis vs. fetch window: ranking, volume-surge and scanner-stats **fetch** ~520 calendar days per ticker (`CONTEXT_HISTORY_DAYS`, needed for the 52-week context and the relative-strength rank) but run every VSA metric on the unchanged **120-day analysis slice** — so the longer fetch never moves a rating. All three — and, since 2026-09-17, the heatmap — share one cached per-ticker history keyed by that fetch window.

## Conventions

- **Colors:** bullish/strength = emerald `#10B981`; bearish/weakness = rose `#F43F5E`. **Two themes** — dark (the default) and light. Style with the neutral ramp used *semantically* (`bg-slate-950` = page, `bg-slate-900` = card, `border-slate-800`, `text-slate-500` = muted, `text-slate-100` = primary) and both themes follow automatically; `src/index.css` redefines what each step means. Never hard-code a hex in a component — for canvas/SVG colours use `lib/chartTheme.ts` or `var(--color-…)`.
- **VSA rating badges:** green > 70, amber/slate neutral, red < 30.
- **TypeScript:** keep shared types in `frontend/src/types/`. No `any` unless unavoidable.
- **Python:** type hints everywhere; Pydantic schemas for all API payloads; format & lint with Ruff; tests with pytest.
- **Mock-first:** build and validate UI against local mock JSON (matching the API payloads in `agent/DOCUMENTATION.md` §5) before wiring real data.
- **Secrets:** never hardcode or commit credentials, SSH keys, or DB passwords. Use environment variables (`pydantic-settings` / `.env`) / GitHub Secrets. The **action log** follows the same rule: it stores the `settings` blob as a `sha256:` fingerprint and masks credential-looking query parameters — when adding a parameter that could carry anything sensitive, add its name to `_MASKED_PARAMS` in `app/services/action_log.py`. Anything added under `/api/admin/*` is behind the optional `STOCKPILOT_ADMIN_TOKEN` gate and may expose internals — keep it that way rather than adding an unguarded diagnostic route.
- **New background job?** Record it in the action log (`ActionLogService.log_job`, `kind="job"`) with `started` / `finished` / `failed` and real counters. A job accepted with a `202` can never report its own outcome through HTTP; the log entry is the only place it can.
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
- **Data:** Yahoo Finance (`.WA` tickers; `AAPL`, `SAP.DE`, `MC.PA`,
  `ASML.AS`, `HSBA.L` for the foreign markets) is the primary source, stooq.pl
  the GPW fallback. PostgreSQL stores EOD bars + daily rating snapshots (optional —
  app runs stateless without it). Every list and scan page is served from
  DB/cache. Only four things ever go out to Yahoo: the nightly refreshes
  (18:00 Warsaw; plus 17:15 New York when the US is served), the hourly
  live prices while an exchange is open (`app/services/live_prices.py`, kept
  in memory, never stored), the UI Refresh button (both `RefreshService`,
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
- **Background/phase analysis built, shipped OFF (2026-09-23, roadmap #15a):**
  `app/analysis/phase.py` reads each bar's background as a Wyckoff phase
  (accumulation / mark-up / distribution / mark-down / neutral) from
  **volume** evidence sourced to *Master the Markets*, not from a moving
  average — the book defines distribution as "high volume on up-bars near a
  market top", which a price MA cannot see. It scales a signal's `strength`
  and never removes one. **`VsaConfig.use_phase_analysis` defaults to
  `False`**: measured over 291 GPW tickers and 4 years of bars it did not
  reliably improve the rating (slightly better at 5/10/20 sessions, worse at
  60, +13% CPU), so it is not worth moving every rating in the app for. The
  default config still hashes as default, so existing caches are untouched.
  **Separately, that measurement found the VSA rating is inverted on GPW
  history** — the 0–29 bucket beat the 70–100 bucket at every horizon (win
  rate 53.6% vs 45.1% at 60 sessions), which is pre-existing and consistent
  with the VSA method already failing its own back-test gate at 44.4%.
  Numbers, caveats and the open decision: **`agent/VSA-PHASE-ANALYSIS.md`**.
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
- **Symbol maintenance (2026-09-07):** the universe is **288 companies**. GPW
  listings get renamed and withdrawn a few times a year and Yahoo drops the old
  symbol, so the seed file needs an occasional sweep: `ccc` → `mdv` (CCC S.A.
  renamed itself Modivo S.A. on 2026-02-19, ticker CCC → MDV; Yahoo moved the
  full history to `MDV.WA`), `spl` removed (Santander Bank Polska became Erste
  Bank Polska and is already tracked as `ebp`), `woj` removed (Wojas withdrawn
  from the Main Market 2024-11-08). A dead symbol is now logged **once** and
  remembered for an hour (`NEGATIVE_CACHE_SECONDS`) instead of being
  re-requested and re-logged by every scan, and `yfinance`'s duplicate ERROR
  line is silenced in `app/main.py` — the app reports every skip itself.
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
  guides money" caveat as Minervini). A third, **VSA Glinicki V1**
  (`vsa_glinicki.py`, id `glinicki`; added 2026-09-04), is the buying half of
  Rafał Glinicki's five-lesson XTB VSA course run as the course's own master
  algorithm — phase → background → zone → formation → effort-vs-result — with
  six bullish formations (Morning Star, Bullish Engulfing, Piercing Line,
  Outside Bar, Hammer, Inside Bar breakout) and all three of the course's
  disqualifiers (out of phase / outside the zone / unconfirmed by volume) as
  hard gates, so it fires only on a complete setup; needs just 70 bars, so it
  covers newer listings than Minervini. (A fourth method, **VSA 2** / `vsa2`,
  added 2026-09-10, was removed on 2026-09-24). The
  ranking computes every method's result per stock (baked into
  the cache), exposes them as `methodResults` + a `combinedScore`, and the
  Dashboard now shows a **method selector (multi-select)**, one **column per
  selected method** (score + a "fired recently" chip) and a **Combined column**
  that ranks companies across all the chosen methods (`GET /api/stocks/methods`,
  ranking `methods` param + `combinedScore` sort; frontend `MethodPicker`,
  `MethodCells`, `useMethods`). This supersedes the "one page per method"
  default for methods added under this framework.
- **VSA V3 (added 2026-09-22):** a fifth trading method, `vsa3.py` (id `vsa3`,
  shown as "VSA V3", order 60) — the same Glinicki course as V2, but read from
  *Kompendium VSA*, a synthesis of the **transcripts** of all 34 recordings that
  Krzysztof supplied as an artifact (V2 was built from the slides, when only
  lesson 1 had a transcript). The spoken material fills in what V2 had to
  leave out, so V3 is the course's whole **seven-layer decision loop** around
  lesson 29's Scenario 5, every layer a hard gate: a **weekly uptrend** (the
  last quarter of completed weeks made a higher high and a higher low — reads
  40% up / 33% down / 27% undecided on GPW history, the course's "undecided
  happens as often as the other two"); daily **volume not bearish** (zigzag
  waves, lesson 6); a **WM** by geometry, the full eight-condition **WFO**, or
  the end of an **ABC correction** (the compendium's proposed definition); **no
  supply at the peak**; a corrective approach **ended by an accent** (lesson
  27); a formation **confirmed** by a VSA signal; a closed **three-signal
  sequence** in the course's category order (climactic/absorbing first, testing
  last — the categories are what the transcripts add); and **R/R ≥ 3:1**. Where
  the transcripts overrule V2's slide reading V3 follows them (close position in
  thirds, the Two Bar Reversal's V₂ > V₁, the Morning Star's stop under all
  three candles, "ultra" volume as a window maximum); V2 is untouched. **Strict
  by the owner's choice (2026-09-22):** across the whole stored history of all
  1,014 companies it completes **4 times** (3 on the GPW) — the three-signal
  sequence rarely fits a daily pullback's low — so the back-test gate can never
  judge it, and its practical output is the score, how many of the seven layers
  stand today (on 2026-09-22: 2 companies at 6/7, 11 at 5/7). A pattern at the
  low that missed at most two layers is **reported instead of hidden**: in
  `detail` as "not taken" with the reasons, and **on the chart as a muted
  square marker** labelled the same way (a `"Watch"` marker — see the API
  contract; the back-test ignores them). Both came from Krzysztof's Alior Bank
  15.09.2026 Hammer, which V3 assessed (5 of 7 layers, refused on R/R 2.6:1 and
  a missing test) while showing nothing anywhere: *"Hammer + Shakeout · no
  sequence, R/R 2.6:1"*, pinned on real bars in `TestAliorHammer`
  (`tests/data_alr_2026.py`) — without changing what fires,
  the score or the back-test. The method itself needed **no frontend change**
  — the picker, column, combined score, chart layer and analytics summary
  picked it up from the registry, which also means the Dashboard's default
  **Combined** column now averages six methods instead of five; the only
  frontend work was teaching the chart to draw the new `"Watch"` marker.
  Details and the measured funnel: `agent/CODEBASE-OVERVIEW.md` §3.3a.
  **Superseded 2026-09-24 — the code was relaxed** (sequence → score booster,
  correction needs only quiet *or* fading volume *or* an accent, wider
  geometry, and a Hammer with no signal confirms itself on its own volume):
  it now completes **394 times** in all stored history, 75 of them such
  Hammers, which since 2026-09-27 are labelled "Hammer + high/low volume"
  instead of a Shakeout/Test the detectors had rejected. Whether the owner
  wants the relaxation — or the Hammer exception — is still an open question.
- **Weinstein Stage 2 (added 2026-09-23, roadmap #28):** a sixth trading
  method, `weinstein.py` (id `weinstein`, shown as "Weinstein Stage 2", order
  70) — Stan Weinstein's stage analysis (*Secrets for Profiting in Bull and
  Bear Markets*, 1988) and **the first method that runs on weekly bars**. His
  stages, his 30-week moving average and his 2× volume test are all defined
  weekly, so the weekly candles are aggregated from the stored daily ones
  (`app/analysis/weekly.py` — no new data source, nothing extra downloaded)
  and the **forming week is dropped**, because he buys a weekly *close* and a
  part-built week carries a fifth of a week's volume. It buys the moment
  **Stage 1 turns into Stage 2**: six hard gates — a tight 20-week base, a
  close above its top and above the 30-week MA, that MA having **stopped
  falling** but **not risen more than 10%** over ten weeks, and weekly volume
  at least twice the prior ten weeks'. The rise cap is the method's whole
  point: without it the same rules also fire on a flat base sitting on top of
  a steep advance — a stock already deep in Stage 2, which is Bulkowski's
  late-Stage-2 buy (+4.1%, 57% winners) rather than the transition (+13.2%,
  69%). Measured over the whole stored GPW history: **0.32 firings per
  ticker-year**, 174 firings on 69 of 292 tickers, with the rise cap alone
  refusing 4,467 candidate weeks. **On the app's own back-test gate it passes
  at the default 10 sessions** (51.0% hit rate, +0.64 pp edge, R/R 1.27 over
  98 judged firings) — which no shipped method except VSA 2 manages at any
  horizon — and at 30 sessions it earns its biggest edge, **+2.07 pp with R/R
  1.96**, while *failing*, because the gate tests a >50% hit rate and this
  profile wins 45.9% of the time with winners twice the size of losers. The
  same measurement **settles the roadmap's open hypothesis**: like-for-like,
  Minervini scores **−0.38 / −0.57 pp** at 10/30 sessions because its template
  fires while a stock is already *inside* Stage 2, and buying the transition
  instead turns that negative edge positive. The roadmap's verified Dom
  Development example is pinned on 138 real weekly bars
  (`tests/data_dom_2022.py`): the week of 2022-12-19 fires at the recorded
  6.9× volume, and the July 2023 *continuation* breakout — recorded as a much
  worse trade — is refused by the rise cap. **No frontend change was needed**;
  the sixth non-VSA method also exactly fills the six-colour chart-overlay
  palette. Details: `agent/CODEBASE-OVERVIEW.md` §3.3a.
- **VSA V4 — the owner's own VSA program (added 2026-09-24):** Krzysztof
  supplied "VSA - kompendium i program Python" — a new compendium of the
  Glinicki course (30 lessons + the 2018 webinars, rules marked [K]/[M]/[F]/[L])
  and a standard-library Python program formalising it, with its own 14 tests
  and 8 independent checks — and asked for it as a new trading method and for
  the script to be integrated. **The program is vendored, not rewritten**:
  `backend-python/app/analysis/vsa4/` holds `engine.py`, `backtest.py` and
  `cli.py` byte-identical to the package apart from imports and a few
  `[StockPilot]` lines that only *report* the sequence state; Ruff leaves them
  in their original style. It is proven equal to the original on all 1,014
  stored companies (430,602 bars, zero differences), its own 22 tests run
  against the copy, and the package's demo result is reproduced to the last
  digit. It is wired in three ways: (1) the **`vsa4` trading method**
  (`methods/vsa4.py`, "VSA V4", order 65) — fires on the program's lesson 21/23
  sequence (strength → No Supply/Test → an up bar confirming it), scores where
  that sequence stands (100 confirmed today … 65 test awaiting confirmation …
  50 strength awaiting a test … 35 nothing … lower when the weakness mirror is
  in play), and draws Bullish / Bearish / Watch chart markers; (2) the
  **trade-simulation card** on the stock page, running the program's own
  simulator (see the API contract); (3) **`scripts/vsa4_run.py <ticker>`**,
  which runs the program's CLI on a stored ticker and writes its four audit
  files. The method needed no frontend change except a **seventh chart-overlay
  colour** (blue — Weinstein moved to it). **Measured on GPW history:** 2.3 long
  setups per ticker-year on 241 of 292 tickers, and **the back-test gate passes
  at both 10 sessions (+1.09 pp, 51.5%, R/R 1.44, n 1,109) and 30 sessions
  (+2.19 pp, 52.5%, R/R 1.53, n 1,073)** — the only method that passes at both,
  on thresholds never fitted to GPW data. The program's own simulator, long
  only, 0.20% + 0.05% costs: 1,027 trades, 32.4% winners, +0.20 R a trade,
  profit factor 1.29; the short side takes that to ≈ 0. Cost: ~15 ms a stock
  in a ranking build, because `evaluate` analyses only the last 160 sessions
  (the engine is ~85 ms per 1,000 bars; the first 120 of the slice are
  warm-up, measured to converge by bar 70 on 4,064 real slices). Source
  material: `agent/vsa4-source/`. Details: `agent/CODEBASE-OVERVIEW.md` §3.3a
  and `agent/DOCUMENTATION.md` §5 Endpoint 16.
- **VSA Kompendium page (added 2026-09-25):** Krzysztof asked to see
  `kompendium_VSA.html` — the VSA compendium behind VSA V4 — on the website
  itself, not only in `agent/`. New public page `/vsa-kompendium` ("Kompendium
  VSA" in the sidebar under Help): the full compendium (15 sections + Appendix A,
  ~580 lines) rendered from `frontend/src/content/vsaKompendium.md`, with a
  table of contents, the two reference diagrams, a "Download PDF" link and the
  usual not-investment-advice note. **The article stays Polish** whatever the
  UI language (chosen by the owner; the page says so); only the page chrome is
  PL/EN. Frontend only — no API change. Adds `react-markdown`, `remark-gfm`,
  `rehype-slug`, `github-slugger`. Static files live in `frontend/public/vsa/`
  (these ship; `agent/` does not). Details: `agent/CODEBASE-OVERVIEW.md` §4.1.
  **Superseded 2026-09-26:** the Kompendium is now the first article of the
  **Education section** (see below) and is in Polish **and** English.
- **Education section — step 1 (added 2026-09-26, roadmap #32):** Krzysztof
  asked for one section holding the knowledge behind every trading method in
  the app, with every article in Polish and English. `/education` lists the
  articles (registry `frontend/src/content/education.ts`) and one card per
  method from `GET /api/stocks/methods`, each linking its article or saying
  one is coming; the sidebar's "Kompendium VSA" link became "Education". The
  Kompendium moved to `/education/vsa-kompendium` (`/vsa-kompendium`
  redirects), gained a full English translation (`vsaKompendium.en.md`, 581
  lines, same structure — a test enforces it) and English diagrams
  (`public/vsa/*.en.svg`); the PDF stays Polish. Articles render through the
  shared `components/MarkdownArticle.tsx`. **Adding an article = a `.md` +
  `.en.md` pair and one registry entry; always write both languages.**
  Frontend only, no API change. **Step 2 (same day):** four method articles,
  PL + EN — the VSA rating, Minervini, Volume Breakout, Weinstein Stage 2 —
  at `/education/<slug>` (`EducationArticlePage`). Each states the exact rules
  the code checks and the measured results honestly (no method is sold as a
  forecast); **when a method's rules or measurements change, update its
  article in both languages.** Still to write: VSA V1/V3/V4 (Pocket Pivot's
  article, `/education/pocket-pivot`, was added the same day — see its entry).
  **Step 3 (2026-09-27):** method descriptions are Polish on the method
  cards, the Dashboard's method picker and its column tooltips
  (`methodDescriptions.<id>` in `pl.json` via `lib/methodText.ts`; English
  stays the backend's `description`, and an untranslated method falls back to
  it). **Drift guard:** `backend-python/tests/test_education_sync.py` fails
  when a method has no Polish description or no article, when its English
  description changes (fingerprinted), or when a threshold an article quotes
  changes — so **changing a method's rules or description means updating
  its article (both languages), `pl.json`, and the pinned value in that
  test.** Also 2026-09-27: `main` had been failing CI (so never deploying)
  on 18 Ruff findings and 2 ESLint/1 `tsc` errors in committed files from
  other work; all fixed without behaviour changes (line wrapping, an unused
  import, an intentionally-unused parameter marked as such), and the whole
  tree is clean again.
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
- **Chart signal colours (2026-09-25):** every chart marker now answers two
  questions with two colours, at Krzysztof's request ("I don't know which ones
  are positive or negative", then "each type of trading should have its own
  colour"). **Good or bad news:** VSA's arrows and every method's *label* are
  green (positive), red (negative) or grey (a "watch" — seen, not taken).
  **Which method:** the *dot* beside a label is in that method's own colour —
  Minervini amber, Volume Breakout indigo, V1 fuchsia, V3 purple, V4 orange,
  Weinstein blue; VSA is the arrows. A Lightweight Charts marker has one
  colour, so each method signal is two stacked markers: the dot, then a size-0
  marker the library draws as text alone. Colours are **fixed per method id**
  (`methodColors` + `methodColorsFor` in `lib/chartTheme.ts`, spares for a new
  method) — they used to be handed out by position, so removing VSA 2 had
  silently recoloured every method after it — and none is green, red or grey.
  The legend's chips show each method's dot (VSA an arrow), and a key row
  under them spells out the three label colours. Frontend only; the API is
  unchanged. Details: `agent/CODEBASE-OVERVIEW.md` §4.12.
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
- **Multi-timeframe weekly confirmation (added 2026-09-04, roadmap #8):** the
  ranking now answers "does the weekly chart agree?" for every stock.
  `app/analysis/weekly.py` resamples each stock’s stored daily bars into
  weekly candles (ISO weeks) and runs the **same VSA engine with the same
  user settings** over them — the 20-session lookback simply becomes 20
  weeks. Every row carries `weeklyRating`, `weeklySignal` and
  `weeklyAgreement` ("confirms" / "conflicts" / "neutral"), the Dashboard
  shows it as a chip beside the signal badge (green "1W ✓" / rose "1W ✗",
  nothing when neutral or unavailable), and the ranking gained a
  `weeklyConfirms` filter (a "Weekly timeframe" select on `/filters`) plus a
  `weeklyRating` sort. No new data source and no extra fetch — it reads the
  ~380-day window the ranking already pulls — and the daily rating, verdict
  and signals are unchanged. A stock with under ~30 weekly bars reports
  `null` instead of a verdict guessed from a few weekly candles.
- **Weekly rating on the stock page (added 2026-09-09):** the weekly read was
  computed for every ranking row but only visible as the Dashboard's small
  "1W ✓/✗" chip — the stock-detail page, the one screen about a single company,
  never showed it. The **VSA Rating card** now carries a "Weekly (1W)" section
  under the daily rating: the weekly rating on a meter, its verdict badge, and
  one plain sentence on what it means for the daily call (green "the weekly
  chart confirms the daily signal", red "…contradicts… treat the daily call
  with caution"). A stock with under ~30 weeks of history says so instead of
  showing a made-up number. `GET /api/stocks/{ticker}/signals` gained
  `weeklyRating` / `weeklySignal` / `weeklyAgreement` for it — same engine,
  same 52-week window and same `settings` as the ranking uses, folded out of
  the daily window the endpoint already fetches, so nothing new is downloaded
  and the card can never contradict the dashboard chip. It stays the **daily**
  read: switching the chart to 30m or 1W does not move it.
- **Chart timeframes (added 2026-09-05):** the stock chart is no longer daily-only
  — a bar-size selector next to the range buttons offers **30m, 1H, 4H, 1D and
  1W**, and the VSA engine (which is timeframe-agnostic) runs on whichever is
  chosen, with the user's same Scanner settings. Daily is unchanged; weekly is
  aggregated from the stored daily bars; 30m/1h come live from Yahoo (the only
  intraday source — the app stores no intraday history, so those timeframes
  reach back ~60 days and ~2 years respectively) and 4h is built from the hourly
  bars. The range buttons change with the bar size (a 30-minute chart offers
  5D…2M, a weekly one 1Y…MAX) and the axis switches to showing the time of day.
  **Everything else on the page stays daily**: the header rating, the price and
  the trading-method overlays are the app's daily read, so switching timeframe
  can never make the chart contradict the dashboard, the analytics summary or
  the ranking. Backend: `app/analysis/timeframe.py` +
  `YahooFinanceClient.get_intraday_history` + the `interval` parameter on
  `GET /{ticker}/signals`; frontend: `INTERVAL_OPTIONS`/`INTERVAL_RANGES` in
  `ChartsPage` and `toChartTime` in `src/lib/chartTime.ts`.
- **Tests:** backend `pytest` — **1177 passing, whole suite** (measured
  2026-09-24 after the VSA V4 work; 57 of them are that work —
  `tests/test_vsa4_program.py`, the owner's own 14 tests + 8 independent
  checks run against the vendored copy, and `tests/test_vsa4.py`, 35 cases:
  the adapter's repairs and tick sizing, the package's demo result reproduced,
  every rung of the score ladder on the program's own sample, the Bullish /
  Bearish / Watch markers, slice-vs-full-history equality and `evaluate` /
  `signals` agreement on every prefix, and the endpoint. The rest of the gap
  over 1106 is other sessions' work in the same tree). **1106 passing** was the
  count measured 2026-09-23 after the Weinstein work. 27 of them are that work
  (`tests/test_weinstein.py` — the complete setup, one fixture per rule, the
  weekly mechanics including that a forming week and a two-day surge cannot
  fire, the overlay, `evaluate`/`signals` agreement under truncation, the
  guards, and both halves of the real Dom Development example); the rest of
  the gap over the previous count is another session's phase-analysis work in
  the same tree, so this total is not simply 1075 + 27. **1075 passing** was
  the count before
  (measured 2026-09-23 after the
  multi-column sorting work; 20 of them are that work — 16 in
  `tests/test_sorting.py` (parsing `sortBy`/`sortDir` as lists, a single column
  still meaning exactly what it did, a repeated column keeping its own
  direction, every rejection, and that a second level really breaks the first's
  ties while each level keeps its own direction) plus four endpoint cases in
  `test_api.py`, `test_volume_surge.py` and `test_capex.py`. **1074** was the
  count before it (measured 2026-09-22 after the sign-in work; 50 of them `tests/test_auth.py`: bcrypt hashing and the password
  rules, e-mail normalisation, the JWT round trip and the three ways a token is
  refused (wrong key, expired, wrong `typ`), the sign-in throttle, and every
  endpoint — including that "no such account" and "wrong password" answer
  identically, that a password change invalidates the older tokens, that every
  failure names a stable code, that the market data still needs no token, and
  that the password never reaches the action log). **989** before that
  (measured 2026-09-22; 32 of them
  VSA V3, `tests/test_vsa3.py`: the complete setup, one fixture per layer it can
  fail on, the weekly block rule, the WFO's condition 6, the ABC's quiet C wave,
  the sequence order rules, the signal detectors, the guards, and the owner's
  Alior 15.09.2026 Hammer on real bars — assessed, refused, and marked on the
  chart as a "Watch"; plus one in `tests/test_method_backtest.py` pinning that a
  "Watch" marker is never judged as a trade). Previously
  **949** (measured 2026-09-21; 9 of them
  the "All markets" audit, `TestPooledMoneyOrdering` in
  `tests/test_multi_market.py`: price and volume ordered by money across
  currencies, a pooled price bound read as złoty, a single market left exactly
  as it was, published figures never converted, and every row reporting its
  session. Previously **940** (measured 2026-09-17; 256 of
  them are the multi-market work: `tests/test_markets.py` (the registry,
  ticker parsing, currency floors, finished-session rules),
  `tests/test_yahoo_client.py` (symbol mapping, unfinished bars, rate-limit
  back-off), `tests/test_multi_market.py` (company lists, ticker resolution,
  market-scoped endpoints), `tests/test_build_market_universe.py` (the list
  builder) and `tests/test_multi_market_pipeline.py` (scoped ingest and cache
  clearing, both schedules, the start-up plan, per-market health, the
  fundamentals scope). Previously **684** (measured 2026-09-14; 4 of them
  are the 2026-09-14 VSA 2 source-fidelity fixes, in `TestVsa2`: a Buying Climax
  at the peak killing the setup, a halted stock not counting as “corrective
  volume”, the Two Bar Reversal needing lesson 11's low-volume pair, and the
  WFO's reference low sitting inside the correction. 15 of them
  are the 2026-09-10 VSA 2 method, `TestVsa2` in `tests/test_methods.py`: the
  complete setup firing, each of the six conditions rejecting on its own
  (place / no-supply-at-peak / corrective volume / formation-without-signal /
  R/R below 3:1), the WFO as the second route to a place, the course's pink-volume
  rule, recency, the overlay, a downtrend scoring under the bullish-lean
  threshold, "no pullback setup" on a stock at new highs, and the frozen/empty
  guards — plus a registry case pinning VSA 2 as distinct from V1. The previous
  count was 665, not the 642 this file recorded on 2026-09-09; 4 of those
  are the 2026-09-09 weekly-on-the-stock-page fields, `TestGetSignals` in
  `tests/test_api.py`: present with enough history, `null` below the
  ~30-weekly-bar floor, unmoved by the chart's `interval`, and equal to the
  same stock's ranking row; 27 of
  them are the 2026-09-09 corporate-action handling,
  `tests/test_corporate_actions.py`: the pure split/dividend detection and the
  ingest's repair, including that a failed repair writes nothing rather than
  mixing two price scales; 44 are the 2026-09-09 observability work,
  `tests/test_observability.py`: error grouping and its bounds, the
  root-logger bridge, the throttled mirror into the action log with its
  `occurrences` count, every ingest verdict (ran / stale / failed / never /
  running) and data verdict (fresh / weekend / stale / partial-during-a-run /
  no-database / unreadable), and the endpoints including the admin-token gate;
  42 are the 2026-09-08 action log,
  `tests/test_action_log.py`: query
  sanitising, the rotating file surviving a restart, request/job recording, the
  admin endpoints and the batched database writer). Previously 525 (2026-09-07; 3 of
  them are the 2026-09-07 dead-symbol guard, `TestDeadTickerNegativeCache` in
  `tests/test_ranking.py`: a ticker the data provider cannot serve is asked
  about once, the remembered failure never outlives the caller's own cache TTL,
  and the negative window stays shorter than the 24h history TTL).
  Of these, 20 are the 2026-09-04 VSA Glinicki V1 method: `TestVsaGlinicki` in
  `tests/test_methods.py` — one case per formation, one per disqualifier, plus
  recency/overlay/frozen-series guards — and a registry/order case;
  the 2026-09-03 trading-method
  refactor adds trend-context / SOS-resistance / buying-climax tests to
  `tests/test_vsa.py`, plus Minervini RS-rank, 52-week-window and Volume
  Breakout base-gating tests to `tests/test_methods.py`; earlier:
  `TestVolumeBreakout`, `tests/test_method_backtest.py` for the generic GPW
  back-test gate, and `TestGetMethodBacktest` in `tests/test_api.py`). The
  2026-09-05 chart timeframes add 28 in `tests/test_timeframe.py` — bar
  aggregation, the interval table and the endpoint, including the invariant
  that rating and price never move with the chart's bar size. Frontend
  `vitest` is green (**199 cases** on 2026-09-24 — 6 of them the VSA V4
  trade-simulation card, `components/TradeSimulationCard.test.tsx`; the Vite
  build passes, and `tsc -b` then failed only on an unused import in
  `api/client.ts` that another session's sign-in work had in progress;
  **193 cases** on 2026-09-23 —
  23 of them the multi-column sorting work: the click grammar in
  `lib/sorting.test.ts`, the rebuilt `components/SortMenu.test.tsx` and two
  Dashboard cases; **155** on 2026-09-21 —
  13 of them the "All markets" audit: złoty conversion in `lib/markets.test.ts`,
  the session check in `lib/sessions.test.ts`, `fmtApproxPln` in
  `lib/format.test.ts`; **142** on 2026-09-17 —
  28 of them the market selection, market clock, switcher, currency formatting
  and refresh-caption cases; 113 before), 3 of them the
  2026-09-09 `pages/ChartsPage.test.tsx` (the Rating card's weekly section
  confirming, conflicting and unavailable) and 8 in
  `StockChart.test.tsx` (`toChartTime`, the intraday axis, marker ordering).
  Layout is responsive (sidebar drawer below `lg`; every list/screener page —
  Dashboard, Watchlist, Filters, Volume Surge, Capex — swaps its wide data table
  for a stacked card list below `lg`, so phones and tablets never scroll
  sideways; the full tables return at `lg`+).
- **Light & dark themes (added 2026-09-04):** the app is no longer dark-only.
  A **Light / Dark / System** switch sits in the top bar (and as an Appearance
  section on the now-real Settings page); the choice is remembered
  (`localStorage['stockpilot:theme']`) and applied by an inline script in
  `index.html` before the first paint, so nothing flashes. **Dark is the
  default and is unchanged to the shade.** It works as a palette swap, not a
  rewrite: every component already used Tailwind's neutral ramp semantically,
  and `frontend/src/index.css` redefines what each step means per theme
  (`:root` = light, `.dark` = Tailwind's own defaults). `src/lib/theme.ts`
  owns the state, `src/lib/chartTheme.ts` the colours that cannot be CSS
  variables (candlestick chart, heatmap tiles, method-overlay markers), and
  inline SVG uses `var(--color-…)`. Details: `agent/DOCUMENTATION.md` §3.2
  and `agent/CODEBASE-OVERVIEW.md` §4.4.
- **Action log / audit trail (added 2026-09-08):** every API call and every
  background job is now recorded and **saved** — what was done, when, how long
  it took, how it ended. A FastAPI middleware writes one entry per request
  (grouped by route template, with a sanitised query, the status, the duration
  and an `X-Request-Id` echoed to the caller); `RefreshService` / `IngestService`
  write their own `job.refresh` / `job.ingest` entries with started / finished /
  **failed** and the counters (`stocksRanked`, `fetched`, `skipped`, `failed`,
  `barsWritten`), which is what makes a nightly run that quietly fetched nothing
  visible. Entries go to **three** places: a rotating JSON-lines file
  (`backend-python/logs/actions.jsonl`, 10 MB × 6, written synchronously so a
  record survives a crash — in production the container's `/app/logs` is
  bind-mounted to `~/stockpilot/logs` on the VPS, so it is a plain server file
  read with `tail -f`, prepared by `deploy/deploy.sh`), the
  **`action_logs` table** (queued and batched off the request path, pruned after
  30 days) and an in-process ring buffer so the audit trail also works with no
  database. Read it back at `GET /api/admin/logs` and
  `GET /api/admin/logs/summary`. `app/services/action_log.py`,
  `app/db/action_log_repository.py`, `app/routers/admin.py`, alembic `004`;
  settings are `STOCKPILOT_ACTION_LOG_*` (see `backend-python/.env.example`).
  Not built yet: the Settings-page screen that would show this in the UI.
- **Legal information (added 2026-09-08):** the site is public, so it now
  carries the documents a public financial-information site has to publish. A
  new `/legal` page holds the **legal disclaimer** (what the ratings are and
  are not, methodology, horizon, risk warning, data sources, conflicts of
  interest, dating — the checklist MAR art. 20 / Reg. 2016/958 expects of a
  published investment recommendation), the **regulamin** required by art. 8
  UŚUDE and a **privacy policy** (server logs only; no cookies and no
  analytics, so no consent banner is needed). A `Footer` on every page carries
  the short "not investment advice" line, the publisher's contact and the link;
  a `DisclaimerNote` sits under the Dashboard ranking heading and on the
  stock-detail header. Publisher: Krzysztof Klich, kklich97@gmail.com. All copy
  lives in `pl.json`/`en.json` under `legal.*`. **Still open, and not fixable
  with a disclaimer:** Yahoo/stooq quotes are redistributed publicly against
  those providers' terms — see `agent/DOCUMENTATION.md` §12.
- **Customizable ranking columns (added 2026-09-08, roadmap #9):** the
  Dashboard, Watchlist and Filters screener each hard-coded their own table;
  all three now render from **one column registry**
  (`frontend/src/lib/rankingColumns.tsx`) and a **Columns** dropdown
  (`ColumnPicker`) lets the user show/hide 14 columns — Company (locked), Name,
  Sector, Price, Change, From 52w high/low, Rating, Rating Δ, Signal, Days ago,
  Volume, AI confidence, Trend. The choice is shared by all three pages and
  remembered per browser (`useRankingColumns`, two localStorage keys), because
  they show the same rows from the same endpoint. **It works on phones**: the
  stacked card list shown below `lg` renders from the *same* column list as the
  wide table (`components/RankingTable.tsx`), so hiding a column hides it there
  too, and — since a card list has no headers to tap — every page also gained a
  Sort menu built from the visible columns (Filters and Watchlist had no mobile
  sort control at all before). Nothing new is fetched: every column reads a
  field the ranking payload already carried. **Reordering added 2026-09-09:**
  each row in the Columns dropdown has ▲/▼ arrows that move that column left or
  right in the table, stored as a separate list of ids
  (`stockpilot:ranking-column-order:v1`) so an existing visibility choice keeps
  working; the arrangement is shared by all three pages and reorders the phone
  card list too. A *shown* column hops over hidden neighbours in one click, so
  the table always visibly changes; the identity column stays pinned first.
  Details: `agent/CODEBASE-OVERVIEW.md` §4.6.
- **Favorites filter on the Dashboard (added 2026-09-09):** a star toggle in the
  Dashboard toolbar (badged with the count) narrows the ranking to the starred
  companies, using the ranking endpoint’s existing `tickers` allow-list the
  way the Watchlist already did — the stars are localStorage-only, so filtering
  client-side would only ever cover the rows already scrolled into view. The
  Refresh button in the same toolbar is now **icon-only** (its word moved to
  the tooltip and `aria-label`).
- **Observability — error tracking + ingest health (added 2026-09-09,
  roadmap #19):** the app now says whether it is working. A new **System page**
  (`/system` — not linked from the sidebar since 2026-09-16; type the address)
  leads with *did the data refresh run?* — the last
  `job.refresh`/`job.ingest` outcome measured against the scheduled 18:00 run,
  with the counters that prove it did real work — then what the database
  actually holds (newest session, how many of the 288 companies have it), then
  **grouped errors** with expandable tracebacks, then the recent-actions table
  the action log had been missing a UI for. Errors are collected by an
  `ErrorTrackingHandler` on the root logger, so every `logger.error` already in
  the codebase is captured with no call-site change, and grouped by error type +
  app source line + message *template*: 290 failing tickers read as one problem
  seen 290 times. Groups are mirrored into the action log as `kind="error"`
  entries (throttled, with an `occurrences` count), so they persist with no new
  table and no migration. `GET /api/admin/errors`, `GET /api/admin/health`;
  `app/services/error_tracker.py`, `app/services/system_health.py`,
  `app/db/health_repository.py`. All `/api/admin/*` endpoints now sit behind an
  optional `STOCKPILOT_ADMIN_TOKEN` (`X-Admin-Token` header) — unset locally,
  **to be set on the VPS**, since these screens carry tracebacks and visitor IP
  addresses; the page warns when it is open and takes the token itself.
- **Corporate-action handling (added 2026-09-09, roadmap #18):** the stored
  price history now stays on **one scale** through splits and dividends. Yahoo
  serves adjusted prices and rewrites a stock's *entire* past the moment a
  corporate action happens, but the nightly ingest only re-fetches five days —
  so the database used to end up holding a handful of new-scale bars on top of
  years of old-scale ones. For a 1:10 split that is a stored history in which
  the stock appears to lose 90% of its value in one session on a volume spike:
  a textbook VSA selling climax that never happened, poisoning the rating, the
  signals, the 52-week range, the returns and the back-tests. No corporate-action
  feed and no new data source were needed — the ingest's five-day window already
  overlaps stored bars, and the two must agree bar for bar. New
  `app/analysis/corporate_actions.py` (`detect_adjustment`) compares the
  overlapping closes and reports the ratio, how many bars disagreed and whether
  they all disagree by the *same* factor (a corporate action) or by varying ones
  (the provider correcting individual figures); the threshold is 0.5% and only
  **prices** are compared, because Yahoo also revises a session's volume for a
  day or two after the close and the re-fetch window already absorbs that. On a
  hit, `IngestService` re-downloads the ticker from its first stored bar
  (`QuoteRepository.get_quote_date_range`) instead of topping up, and re-points
  the stored rating snapshots' `close` at the rebuilt bars
  (`resync_rating_snapshot_closes`) — the rating itself is scale-free, the price
  charted beside it is not. A **failed** repair writes nothing for that ticker
  (a day-stale history beats an inconsistent one) and the next run retries — and
  so does a repair that comes back **shorter than the stored history**, since
  `upsert_quotes` never deletes and the older prefix (backfilled from stooq by
  the single-ticker read path) would keep the pre-split scale.
  Repairs are counted in the action log (`adjusted`, `adjustedTickers`). Two
  supporting behaviours: the fetch widens to regain overlap when a ticker's
  stored history ends before the window (an outage would otherwise hide the
  mismatch), and the single-ticker read path serves freshly fetched bars without
  persisting them when it sees a mismatch, leaving the stored series for the
  nightly ingest to fix properly. Details: `agent/CODEBASE-OVERVIEW.md` §3.2a.
- **Foreign markets (added 2026-09-17, roadmap #22):** the app can now also
  track **722 foreign companies** — USA 518 (S&P 500 ∪ NASDAQ-100: 343 NYSE,
  174 NASDAQ, 1 Cboe), Germany 40 (DAX), France 39 (CAC 40; ArcelorMittal's
  Paris line has no Yahoo data and the company is tracked in Amsterdam),
  Netherlands 25 (AEX), UK 100 (FTSE 100: 97 quoted in pence, 2 in USD, 1 in
  EUR). **Off by default**: `STOCKPILOT_MARKETS` names the served markets
  (`gpw` default, `all`, or a list), so the live site is unchanged until the
  owner switches them on. The registry is `app/markets.py` (ids, exchanges,
  currencies, time zones, closing times, Yahoo suffixes, which nightly run
  each belongs to, the złoty rate table and the floor helpers); the company
  lists are `app/data/markets/<id>.json`, built and verified against Yahoo by
  `backend-python/scripts/build_market_universe.py` (re-run it when the
  indices rebalance; `--retry-rejected` re-checks only what a run left out).
  Foreign tickers carry a market suffix (`aapl.us`, `hsba.l`); GPW tickers are
  unchanged. Every list endpoint takes a `market` parameter; a **market
  selector** in the top bar (shown only when more than one market is served,
  remembered per browser) drives the Dashboard, Watchlist, Filters, Volume
  surge and Scanner — including "All markets" — while the Heatmap and
  Investment pages show market tabs because they always compare within one
  market. Prices carry their own currency (`332.41 USD`, `1,507.80 GBX`);
  foreign rows carry a market badge. The data pipeline runs **twice a night**
  when the US is served (Europe + GPW 18:00 Warsaw, US 17:15 New York), each
  run refreshing only its own markets; the start-up check downloads only what
  a market is missing; a bar for a session still trading is never stored
  (**intended behaviour change for the GPW:** no bar for today before 17:20);
  Yahoo's rate limit is absorbed by back-off and retry; the System page
  reports every run and every market separately. Measured on the local
  database with everything switched on: first download 15 min 43 s (1,008 of
  1,010 companies, 198,777 bars), database 50 → 89 MB, backend memory ~700 MB
  warm vs ~320 MB for the GPW alone, 849 stocks ranked. Plan, decisions,
  measurements and open risks: `agent/MULTI-MARKET-PLAN.md`; switching the
  markets on in production: `agent/DEPLOYMENT.md` §10.
- **"All markets" audit (2026-09-17):** the owner reported that with every
  market selected the Dashboard's companies were not all sorted correctly.
  Audited live against the local PostgreSQL with all six markets served (850
  ranked). The sorting *code* was fine — every column came back monotonic —
  but the **money columns compared raw numbers across five currencies**, and
  London quotes most lines in pence: NVR (6,242.23 USD ≈ 23,720 PLN, the most
  expensive stock in the list) sat at position 12, below nine London lines
  worth 250–900 PLN each. Fixed by putting `lastPrice`, `volume` (as turnover)
  and the `minPrice`/`maxPrice` bounds on a common złoty scale **only when
  markets are pooled**, through the same fixed rates the quality floors use;
  published figures are untouched, a single-market request is unchanged, and
  each row now prints an "≈ N PLN" second line so the order is legible. Found
  and fixed at the same time: a pooled list could silently mix **two different
  sessions** (Europe settles ~17:55 Warsaw, the US at ~22:15, so all evening
  the American rows are a day behind) with no way to tell — every ranking row
  now carries `lastSession` and the three list pages show a `SessionNote` when
  the loaded rows disagree. Two further findings were left as known limitations
  (`agent/ROADMAP.md` #26, #27): nine cross-listed companies occupy two rows
  with contradictory ratings (Airbus Sell 28 in Frankfurt vs Strong Sell 17 in
  Paris; CCEP Hold 50 in London vs Strong Sell 17 in the US), because a
  secondary listing's thin volume is exactly what VSA reads as a signal; and
  the Combined column sorts within-market relative-strength percentiles against
  each other. Verified clean: no duplicate tickers, one sector taxonomy across
  all markets, and `market=all` correctly refused on heatmap/capex/back-test.
  Details and the measured tables: `agent/MULTI-MARKET-PLAN.md` phase 8.
- **Sign in / user accounts (added 2026-09-22):** visitors can create an
  account and stay signed in, and the control lives in the **main window's top
  bar** — "Sign in" when signed out, the person's initials plus a small menu
  (Account settings / Sign out) when signed in. **Anyone can create an
  account**; the site itself is unchanged and entirely public, since no page
  and no `/api/stocks` endpoint requires one. `/login` is one screen with both
  Sign in and Create account, inside the normal app shell rather than as a
  gate, and `noindex`. Settings gained an **Account** section (who is signed
  in, change password, sign out). Backend: `app/services/auth.py` (bcrypt +
  two HS256 JWTs — a 30-minute access token and a 30-day refresh token, a
  per-address/per-IP sign-in throttle), `app/routers/auth.py`,
  `app/db/user_repository.py`, the `users` table (alembic `006`, created
  automatically on startup). The browser renews the short token by itself:
  `api/client.ts` answers one 401 by refreshing **once** and replaying the
  request, sharing a single refresh across concurrent calls, so a 30-minute
  token never signs anyone out mid-click. **`STOCKPILOT_JWT_SECRET` is
  deliberately left unset** (Krzysztof, 2026-09-23: "it is not a problem, it
  can sign out everyone") — the app then signs tokens with a key generated per
  start, which is just as strong but ends every session when the process does,
  so a deploy or a reboot asks people to sign in again. This is a supported
  mode, **not** a to-do: the sign-in page says only what it means for a visitor
  ("You may be asked to sign in again after a site update", `auth.sessionsMayEnd`,
  in muted grey rather than an amber warning), and the backend notes it at INFO
  once per start. It would become **required** if the API ever ran with more
  than one worker or replica — each process would invent its own key and logins
  would fail at random rather than only after a restart; production runs a
  single Uvicorn worker on purpose, so that does not apply today.
  **No e-mail is sent, by request**: no address confirmation and no password
  reset, which the sign-in screen states out loud; a signed-in visitor can
  change their own password. Building it is roadmap #30.
- **Multi-column sorting (added 2026-09-23):** every sortable table can now be
  sorted by **one column and then by another** — "sector A→Z, best rating first
  inside each sector", "signal first, biggest volume surge within it". A sort is
  an ordered list of up to **three levels**: the first is the order you see, the
  rest only break its ties. The way in is a **Sort menu in every list page's
  toolbar, on every screen size** — the active levels at the top (numbered,
  each with its own ↑/↓ and a remove ×) above a "Then by" list of the remaining
  columns, and a trigger reading e.g. "Signal +1". On a wide table the headers
  work too: a plain click sorts by one column (and is always the way back to a
  simple ordering), **shift-click** adds a column as the next level, flips it,
  and on a third shift-click removes it again; each sorted header shows its
  position (1, 2, 3). The menu was originally phones-only with shift-click as
  the desktop path, and that **read as broken** (2026-09-23): nothing advertises
  the gesture, and a tie-break often reorders nothing visible — the Dashboard
  opens sorted by Change %, where 25 rows held 4 ties, so a correctly-added
  second level moved nothing on screen. Showing the menu everywhere states the
  ordering outright instead. Volume surge and Investment gained the menu, which
  they had never had. **The menu offers only the columns that are switched on**,
  so sorting by Sector means showing the Sector column first.
  All five list pages (Dashboard, Watchlist, Filters, Volume surge, Investment)
  share the rules (`frontend/src/lib/sorting.ts`) and the state
  (`hooks/useTableSort.ts`), so they behave identically. On the wire it is the
  same two parameters as comma-separated lists, and a single level is
  byte-identical to what the app sent before, so nothing that already worked
  changed. Details: `agent/CODEBASE-OVERVIEW.md` §4.11.
- **Market overview on the Dashboard (added 2026-09-25, roadmap #5):** three
  cards above the ranking — **Market breadth** (a five-segment Strong Buy →
  Strong Sell bar with every count as text, bullish / bearish share, price
  up/down, rating up/down, new 52-week highs/lows, average rating) and the five
  stocks whose VSA rating **rose** / **fell** the most since the previous
  session. It needed no new data: every ranking row already carries
  `ratingChange`, so `GET /api/stocks/market-overview` is a pass over the cached
  ranking (the roadmap had assumed it needed `rating_snapshots`). It describes
  the whole market (search/filters below do not change it), follows the top
  bar's market including "All markets", and steps aside silently if its request
  fails. Counts only, by design. On real GPW data rating rises are tiny most
  days (biggest riser +1, biggest faller −24 on 2026-09-25 — the rating is a
  decayed score); a minimum-move threshold is the obvious follow-up. Details:
  `agent/CODEBASE-OVERVIEW.md` §4.14.
- **Live prices every hour while an exchange is open (added 2026-09-25):**
  Krzysztof asked for the data to be downloaded every hour while the market
  is open. Asked whether that should move the ratings too, he chose **live
  prices, ratings at the close** — an unfinished day carries part of its volume
  and VSA reads low volume as a signal, so the analysis keeps running on
  finished sessions only and **do not feed the partial bar to the engine**. At
  every full hour each served market that is trading gets every tracked stock's
  session so far downloaded (`app/services/live_prices.py`; 288 GPW stocks in
  ~18 s, 518 US in ~31 s, 3 at a time so visitors keep two Yahoo slots) and held
  in memory; the ranking, heatmap and stock page show today's price and change
  with a blue dot / "Today 14:44" chip, a note saying the ratings are from the
  last finished session, today's candle drawn hollow on the daily chart with a
  grey partial-volume bar, and the top bar's "Last sync" at the hourly time.
  Open pages reload themselves quietly within ~5 minutes of new data
  (`frontend/src/hooks/useDataVersion.ts`). Only runs with a database (a
  backend without PostgreSQL shows no live prices), and holidays are detected
  by asking a market's three largest stocks first. Details:
  `agent/CODEBASE-OVERVIEW.md` §3.6c and §4.13.
- **AI / machine-learning layer — Phase 0 (test bench) BUILT 2026-09-25;
  Phase 1 (logistic regression) RUN AS A PILOT 2026-09-26 — the filter found
  nothing, so nothing ships; Phase 2 waits for decision D2 (roadmap #31,
  absorbs #29):** Krzysztof asked for a plan to make
  the trading methods more precise with AI, then asked for it to be
  implemented. **Phase 0 is built:** `backend-python/app/ml/` (point-in-time
  features, labels, walk-forward validation, the random-filter benchmark,
  overfitting statistics, dataset assembly, the back-fill logic, the trial
  register) plus `scripts/ml_report.py`, `ml_build_dataset.py` and
  `ml_backfill_history.py`. **The running app never imports `app.ml`**
  (`tests/test_ml_isolation.py`), so nothing a visitor sees changed. The rules
  were frozen before any result in `agent/ml/DESIGN-CHOICES.md`; reports go to
  `agent/ml/reports/`. **Decision D2 — the one-time history back-fill — was
  approved on 2026-09-27** ("yes, please do it"): the GPW, once, on the
  server; rehearsed that day on the PC's database. **Since 2026-09-26 the
  jobs run on the server**
  (decision D6 — "my computer is too slow"): `bash deploy/ml-run.sh <job>`
  runs one job at a time in the `ml` service of `docker-compose.prod.yml`
  (the API's image, never started by `up` or a deploy, capped by
  `STOCKPILOT_ML_MEMORY` 1 GB / `STOCKPILOT_ML_CPUS` 1), writing to
  `~/stockpilot/ml` — whose `trials.csv` is now the register of record,
  seeded with the 14 pilot trials. The jobs were made lean to fit the cap
  without moving a result: at the GPW's real back-filled size (1.23 million
  bars, rehearsed on the PC) the dataset build needs 662 MB and training
  735 MB (it was 1,023 MB — at the cap); the pilot re-run reproduces its
  report exactly. Owner's guide: `agent/DEPLOYMENT.md` §10; next steps:
  the "Next phase — TODO" list under `agent/ROADMAP.md` #31. The plan uses
  **meta-labeling**: a locally trained model (logistic regression baseline,
  then LightGBM) scores each VSA V4 / Weinstein firing. Low-odds firings
  become the existing "Watch" markers, and the whole thing ships as one
  registered method, `ai_odds`. It puts an honest test bench first
  (walk-forward with purge and embargo, locked holdout, trial register,
  Deflated Sharpe / PBO, random-filter benchmark) and ~3 months of shadow mode
  before anything is shown. Blocked on owner decisions, chiefly a one-time
  10+ year history back-fill for training.

  **It must always be possible to switch it off**, as the owner asked
  (plan §14): it ships `off`, and there are five kinds of switch — a master
  switch `STOCKPILOT_ML_MODE` (the ceiling), an instant System-page switch, a
  switch per part, an automatic pause, and a per-visitor Settings switch.
  "Off" must stay byte-identical to the app without the ML package; a
  snapshot test enforces it, and the ML libraries are imported lazily. **Read
  `agent/AI-ALGORITHMS-PLAN.md` before building any of it** — Part II
  (§14–§28) is the build specification. Summary in
  `agent/DOCUMENTATION.md` §13.
- **Signal direction test (2026-09-26, measurement only — no app change):**
  Krzysztof asked which VSA method best predicts a rise after a positive
  signal and a fall after a negative one. Measured on every stored stock
  (1,010 companies, 915 above the liquidity floor, 86% of signals from
  2025–26), market-adjusted (beat the median stock of the same market over
  the same sessions; a random pick scores 49.7%), with two-way clustered
  errors and a clean look-ahead check (0 differences over 360 cut-offs).
  **No VSA method predicts direction better than chance** — markers,
  Dashboard verdict, Glinicki V1, V3, V4 all sit at 47–51%, and positive and
  negative signals are followed by almost the same outcomes. Least bad: VSA
  V4 on the GPW at 20–30 sessions (+4.6/+5.8 pp positive-minus-negative, not
  significant, absent abroad). **Spring and V1's Hammer work in reverse**
  (GPW 37–42% beat the market, t ≈ −4). The back-test gate overstates:
  a random GPW day already has +0.62/+1.28 pp "average edge" at 10/30
  sessions, so V4's "passes" is not evidence. Also found: `vsa3.py` was
  relaxed on 2026-09-24 and now completes ~394 times, not the 4 the V3 notes
  above describe. Report: **`agent/SIGNAL-DIRECTION-TEST.md`**; script:
  `agent/signal-direction-test/`.
- **Pocket Pivot (added 2026-09-26):** Krzysztof asked to "find another
  trading method and implement it". The eighth method,
  `backend-python/app/analysis/methods/pocket_pivot.py` (id `pocket_pivot`,
  shown as "Pocket Pivot", order 80) — Gil Morales & Chris Kacher, *Trade Like
  an O'Neil Disciple* (2010), the top entry of the `find-trading-methods`
  shortlist and the first method that buys **inside the base** rather than at
  a breakout above it. Six hard gates: an up day; volume **≥ the heaviest
  down-day volume of the prior ten sessions** (the book's own words; no
  down-day volume = fail closed); close above the 50- and 200-day MAs; the day
  comes up off or through the 10- or 50-day line (low within 2% of it, close
  above); the five sessions before it quieter than the fifty before those; and
  no upward wedge into it. The 2%, the five days and the wedge count are this
  app's readings of words the authors never quantified, and the code says so.
  Chart markers read "Pocket Pivot 10d" / "50d". **Measured, it does not beat
  chance** (same frame as the signal direction test): 49.7% of its firings
  beat the market's median stock over 10 sessions where a random pick scores
  49.6% (n ≈ 2,000, all markets); GPW +0.83 pp at 30 sessions, t 1.2; it fails
  the app's gate at 10 and 30 sessions with less edge than a random GPW day.
  The authors' headline record (which Kacher reports KPMG verified) predates
  the rule, and Kacher says about
  half of pocket pivots fail — the in-app description says it is unproven.
  Frequency: ~5 per ticker-year on GPW. The picker, column, combined score,
  chart layer and analytics summary picked it up from the registry; the only
  frontend change is its fixed chart colour (cyan, formerly the first spare,
  in `lib/chartTheme.ts`). Real example pinned: XTB 2026-07-01, +22.9% ten
  sessions later (`tests/data_xtb_2026.py`). The score is a six-check posture
  read **capped at 50 below the 200-day line** (Kacher's rule 7 — no pocket
  pivot is bought there), so it never leans bullish in the analytics summary
  on such a stock; the cap was added the same day, when writing the article
  showed the first version's docs claimed this without the code enforcing it.
  Its Education article, `/education/pocket-pivot` (PL + EN, the rules, the
  XTB example with two refused days, a failed PZU pivot, the measurements),
  was written together with the Education session. **Code review
  (2026-09-27/28, nine findings, fixed by a subagent):**
  * "Is the close above its average" is now decided in exact integers. The
    float running sums had made a frozen price, such as a suspended stock
    printing 12.35, read as above its averages and score 67.
  * `evaluate` counts recency only from the bars the chart marks, so "fired"
    always has a marker. The second day of a two-day pivot reads "1d ago".
  * The detail says "below 200d MA" when the 50 cap applies.
  * A guard stops a NaN price from raising.
  12 of 22,534 stored chart markers changed, all where a close was exactly
  equal to its 10-day average. Three findings are left for the owner because
  they change the method: rule 4 reads the day's low, so a pivot can close far
  above its line; the quiet-volume baseline is a mean, not a median; and there
  are two spare chart colours instead of three. Tests:
  `tests/test_pocket_pivot.py` (42). Details: `agent/CODEBASE-OVERVIEW.md`
  §3.3a.
- **Known gaps:** the Settings page has only the Appearance (theme) section
  (the action log is API-only — no UI screen yet);
  accounts exist but hold nothing yet — favorites, filter presets and column
  choices are still localStorage-only, so they do not follow a person to
  another device, and the app sends **no e-mail**, so there is no password
  reset (roadmap #30); frontend unit coverage is
  still thin (component/lib tests only, 193 cases); the foreign markets are
  built and verified locally but **not yet switched on in production**
  (`STOCKPILOT_MARKETS` on the VPS); see `agent/ROADMAP.md`.
- **Feature checklist:** `agent/FEATURE-CHECKLIST.md` — done/not-done list of
  all features, incl. planned "popular scanner" additions (2026-07-09).

---
*Last updated: 2026-09-28 (**Pocket Pivot — code review and fixes.** Krzysztof asked for a code review of the Pocket Pivot, with the fixes done by a subagent.

The review found nine things. A subagent fixed six, and three were left as his decisions (see the status entry).

Two of the six were real bugs:
- A frozen price read as bullish. A suspended stock printing 12.35 every day came out as "above its averages", scored 67 and leaned bullish.
- The Dashboard said "fired today" with no chart marker on that bar. This happened on 11% of pivot days.

The other four:
- An untested fail-closed guard, now covered by a test.
- A score cap the detail text did not explain.
- Two overclaims in the docstring.
- Missing type hints in the tests.

The first subagent was cut off twice, by a usage limit and by a session ending. A second one finished. Every step was re-checked here:
- Tests: 42 in `tests/test_pocket_pivot.py`, and the 198 across the five method test files, all green. `ruff check .` is clean.
- Mutation check: removing the fail-closed guard now fails a test.
- Old-vs-new comparison of every chart marker on all 1,010 stored companies: 12 of 22,534 changed, all where a close exactly equalled its 10-day average.

The method-review session made the same "fired = marker" change to Volume Breakout and Weinstein.

PostgreSQL had stopped again and was restarted. Previously 2026-09-27: **AI research jobs moved to the server — decision D6.** Krzysztof asked for the AI to run on the server because his PC is too slow. `bash deploy/ml-run.sh <job>` now runs one job at a time in a new `ml` service of `docker-compose.prod.yml` — the API's own image, never started by `up` or a deploy, capped at 1 GB and one CPU, output in `~/stockpilot/ml`, whose `trials.csv` is now the register of record (seeded with the 14 pilot trials); each job's log ends with one line saying how it ended. To fit the cap without moving a result, the jobs were made lean: on a simulated ten-year GPW history the dataset build peaks at 454 MB (was 678), the bench at 467 MB (715) and training at 575 MB (1,041). Every rank and label is identical, and the Phase-1 pilot re-run reproduces its report number for number. Nothing has run on the server yet — that needs a commit and a deploy — and D2 (the back-fill) is still open. Backend `pytest` **1427 green, whole suite** (112 of them the AI bench's) and `ruff check .` clean; frontend untouched, ESLint and `tsc -b` clean at the time of writing. Guide: `agent/DEPLOYMENT.md` §10; details: `agent/ml/RESEARCH-LOG.md`. Previously 2026-09-27: **Pocket Pivot — score cap and Education article.** Writing the method's Education article showed that the first version's docs claimed a stock under its 200-day line could not lean bullish, while the code let one recovering above its 50-day line score 67–83; the score is now capped at 50 below the 200-day line (Kacher's rule 7), with a test. The article (`/education/pocket-pivot`, PL + EN) was written in parallel by this session and the Education session, which collided once on the two `.md` files; it was settled by message: the Polish structure from here, the final English from there, and every figure checked against the measurements. Also corrected: CODEBASE-OVERVIEW had said "most GPW pivots are on illiquid names" — 56% are on liquid days. Backend 119 method tests green (`test_pocket_pivot`, `test_methods`, `test_analytics_summary`, `test_method_backtest`), Ruff clean on the method; frontend `vitest` **284 green, whole suite**; verified live in both languages, with the Pocket Pivot method card on `/education` linking its article (PostgreSQL had stopped overnight and was restarted to check). Previously 2026-09-26: **Pocket Pivot — a new trading method.** Krzysztof asked to find another trading method and implement it. The research picked Gil Morales & Chris Kacher's pocket pivot — the top-rated volume-first method on the project's shortlist not yet in the app — and it was built as one class (`app/analysis/methods/pocket_pivot.py`) with its own chart colour; see the status entry above. It was measured before shipping and **does not beat chance** on the stored data (the same verdict the signal direction test gave the VSA methods), which the docs and the in-app description say plainly. Backend `pytest` **1422 green, whole suite** (29 new in `tests/test_pocket_pivot.py` — each rule's fixture verified to fail on that rule alone, a real XTB pivot pinned; the rest of the gap over 1249 is other sessions' work in the tree), Ruff clean on the new files; frontend `vitest` **269 green, whole suite**. Verified live against the local PostgreSQL: the method in `/api/stocks/methods`, on all 134 ranked GPW rows (Onde fired on 2026-09-25 at 4.7× the heaviest recent down day), last in the Dashboard's method picker, as a cyan "Pocket Pivot 6" chip on XTB's chart legend, and as a row in the stock page's analytics summary. While verifying, the dev server was down on a syntax error another session had left in `frontend/src/lib/seo.ts` (an apostrophe inside a single-quoted string, in the Education page's SEO entry) — fixed by switching that one string to double quotes, nothing else touched. Whole-tree CI checks were red **before** this work and still are, only in files other sessions touched: `ruff check .` 18 findings, ESLint 2 unused variables (`api/client.ts`, `lib/authToken.ts`) and `tsc -b` 1 — so a push would still skip the deploy. Previously 2026-09-25: **Market overview on the Dashboard — roadmap #5.** The next unbuilt item that needed nothing from the owner: market breadth and the biggest rating movers, as three cards above the Dashboard ranking (see the status entry above). New `GET /api/stocks/market-overview` + `app/services/market_overview.py`, `MarketOverview` / `useMarketOverview` and `overview.*` translations; no new table, no migration, no new download. Verified live on real GPW data (26.1% bullish / 37.3% bearish over 134 stocks; the movers match the ranking's own `ratingChange`), dark and light theme, phone width with no horizontal scroll, no console errors. Backend `pytest` **1249 green, whole suite** (16 new in `tests/test_market_overview.py`), Ruff clean on the new files; frontend `vitest` **243 green** (6 new), ESLint clean, and `tsc -b` still fails only on the unused `getRefreshToken` import in `api/client.ts` that another session has in progress. Previously 2026-09-25: **Live prices every hour while an exchange is open.** Krzysztof asked for the stock data to be downloaded every hour while the market is open. The app deliberately refuses a session still trading (its partial volume reads as a VSA signal), so the request had two readings; asked, he chose **live prices, ratings at the close**. New `app/services/live_prices.py` downloads, at every full hour, each tracked stock's session so far for the served markets that are trading (`Market.open_time` / `session_in_progress`; one small request per stock via `YahooFinanceClient.get_session_quote`, which keeps today's bar apart from the finished ones), holds it in memory and lays it over ranking rows, heatmap tiles and `/signals` as `live` plus today's `lastPrice`/`priceChangePct` — ratings, signals, methods and markers untouched, nothing unfinished stored. The Refresh button ends with the same step, a restart mid-session downloads at once, each run is a `job.live` log entry, and a market's three largest stocks are asked first so a holiday costs three requests. Frontend: a blue dot beside live prices, a note above the lists and the heatmap, a "Today 14:44" chip, today's candle drawn hollow with a grey partial-volume bar, "Last sync" at the hourly time, and pages that reload themselves quietly within ~5 minutes (`hooks/useDataVersion.ts`); the status endpoint those pages poll joined `/health` on the action log's exclusion list, and the two settings are in `docker-compose.prod.yml`, `env.prod.example` and `backend-python/.env.example`. Verified live on 2026-09-25 against the local PostgreSQL with all six markets (the database was off and had to be started — a backend without one schedules nothing, so shows no live prices): 518 US stocks in 31.2 s with no failure, Apple 339.64 USD +1.11% as of 19:20 beside its unchanged finished-session rating, on the Dashboard, the stock page (chip, hollow candle, note), the heatmap, both themes and 375 px; 288 GPW stocks took 18.3 s in the same pass the day before. The **scheduled** 20:00 run then fired by itself (518 US stocks, 36.8 s, no failure), and with a temporary 5-minute cadence an open Dashboard moved from the 21:20 to the 21:25 prices in place (same page, no spinner). That check caught one flaw, fixed: a page opened in a background tab skipped its first status read, so it would have taken a later state as its baseline and missed a run in between — the first read now always happens. Backend `pytest` **1223 green, whole suite** (59 new in `tests/test_live_prices.py`; the rest of the gap over 1177 is other sessions' work in the tree), Ruff clean on everything new; frontend `vitest` **243 green** (27 new; the rest is another session's work in the tree), ESLint clean, `vite build` passes, and `tsc -b` still fails only on the unused import in `api/client.ts` that another session has in progress. Previously 2026-09-25: **Chart signal colours.** Krzysztof could not
tell positive chart signals from negative ones — marker colour named the
method, never the direction — and then asked to keep a colour per method too.
Now the dot says which method (fixed colour per method id) and the label says
good or bad (green / red / grey), with a key under the chart's method chooser;
see the status entry above. Also fixed: method colours were assigned by list
position, so removing VSA 2 had silently recoloured V3, V4 and Weinstein.
Frontend `vitest` 233 green (whole suite; 8 new cases here and 4 updated);
ESLint clean; `tsc -b` still fails only on the unused import in
`api/client.ts` from the sign-in work. Verified live on PKO in both themes and
at 375 px. Previously 2026-09-24: **VSA V4 — the owner's own VSA program, integrated.**
Krzysztof supplied a folder with a new VSA compendium and a Python program, and
asked for a new trading method from the compendium and for the script to be
integrated. The program *is* the compendium's formalisation, so the two became
one piece of work: the program vendored unchanged in `app/analysis/vsa4/`
(proven identical to the original on every stored company), wrapped as the
`vsa4` trading method, its own simulator exposed as the stock page's "Trade
simulation · VSA V4" card, and its CLI runnable on stored tickers via
`scripts/vsa4_run.py`. It passes the GPW back-test gate at both 10 and 30
sessions on ~1,100 firings. See the VSA V4 status entry above. Backend
`pytest` 1177 green (57 new), Ruff clean on everything new; frontend `vitest`
199 green (6 new), Vite build passes. Verified live on PKO in both themes, both
languages and at 375 px. Previously 2026-09-23: **Weinstein Stage 2 — the next trading method from
the to-do list (roadmap #28).** Krzysztof asked to build the next method on the
list; it was Stan Weinstein's Stage 1→2 breakout, the best candidate from the
2026-09-21 research run. One class,
`backend-python/app/analysis/methods/weinstein.py`, and the framework wired up
the rest: **no frontend change at all** — the picker, dashboard column,
combined score, chart overlay layer and analytics-summary row all picked it up
from the registry, and as the sixth non-VSA method it exactly fills the
six-colour overlay palette. It is **the first method that runs on weekly
bars**, because Weinstein's stages, his 30-week moving average and his 2×
volume test are all defined weekly; the candles are aggregated from the stored
daily ones, so nothing new is downloaded, and the **forming week is dropped**
(he buys a weekly close, and a part-built week carries a fifth of a week's
volume — the same reason `compute_weekly_view` drops it).

**What it buys, and the one number that is not Weinstein's own.** Six hard
gates: a tight 20-week base, a close above its top and above the 30-week MA,
that MA having **stopped falling** but **not risen more than 10%** over ten
weeks, and weekly volume at least twice the prior ten weeks'. That last cap is
the method's whole point — rules 1–4 alone also fire on a flat base sitting on
top of a steep advance, i.e. a stock already deep in Stage 2, which is
Bulkowski's late-Stage-2 buy (+4.1%, 57% winners over 116 real trades) rather
than the transition (+13.2%, 69% over 127). On GPW history the cap alone
refuses 4,467 candidate weeks, 37% of everything with a non-falling MA. The
prior decline is deliberately *not* gated: a stock may have based for a year or
more, putting the decline outside the window the app holds.

**Measured** over the whole stored GPW history (292 tickers, ~541
ticker-years): **0.32 firings per ticker-year**, 174 firings on 69 tickers —
selective like VSA 2 (0.20), not near-silent like V3. **On the app's own
back-test gate it passes at the default 10 sessions** (51.0% hit rate, +0.64 pp
edge, R/R 1.27, 98 judged firings), which no shipped method except VSA 2
manages at any horizon; at 30 sessions it earns its biggest edge, **+2.07 pp
with R/R 1.96**, and still *fails*, because the gate tests a >50% hit rate and
this profile wins 45.9% of the time with winners twice the size of losers.

**It also settled an open question.** The roadmap had recorded, as an untested
hypothesis, that Minervini fails on GPW because its template fires while a
stock is *already* in Stage 2 rather than at the transition. Measured
like-for-like on the same universe and engine at 10/30 sessions: Weinstein
+0.64/+2.07 pp, VSA 2 +0.68/+6.69, VSA V1 +0.21/+1.20, VSA rating +0.03/+1.06,
Volume Breakout +0.20/+0.49, Minervini **−0.38/−0.57**. Buying the transition
instead of the established trend turns a negative edge into a positive one at
both horizons.

**Two documentation defects found and fixed while measuring**, both about the
gate rather than the new method: `CODEBASE-OVERVIEW.md` and `ROADMAP.md` 23a
both claimed the gate is "positive expectancy, not a >50% hit rate" — the code
has always been `win_rate > 50% and avg_excess > 0`, as the API contract above
says, and VSA 2 at 10 sessions and Weinstein at 30 are now two worked examples
of the profile that claim promised would not be failed; and the "live GPW
verdicts" both files carried were from 2026-09-02 and no longer hold (Volume
Breakout and VSA were listed as passing; neither does now). Both are corrected,
with the re-measured table, and whether the pass condition *should* become
expectancy-based is left as the open decision it is.

Verified live against the local PostgreSQL with the backend and frontend
running: the method catalogue, 130 GPW ranking rows all carrying it, the
dashboard column with LPP's amber "▲ 5d" chip at score 100, the analytics
summary row, two chart markers on LPP (2025-12-12 and 2026-09-18), the
back-test endpoint, and both themes — the overlay's sixth colour is `#4D7C0F`
on light, 5.4:1 contrast. The roadmap's verified Dom Development example is
pinned on 138 real weekly bars (`tests/data_dom_2022.py`): the week of
2022-12-19 fires at the recorded 6.9× volume and the July 2023 continuation
breakout is refused. Backend `pytest` **1106 green, whole suite** (27 new
here; the tree also carries another session's phase-analysis work, so the
total is not simply 1075 + 27) and Ruff clean. Frontend untouched.
Previously 2026-09-23: **Multi-column sorting on every table.** Krzysztof
asked whether a table could be sorted by one column and then by another, and
for it everywhere if so. It can, and now is. A sort became an ordered list of
up to three **levels** — the first is the visible order, the rest break its
ties — shared by all five list pages through one set of pure rules
(`frontend/src/lib/sorting.ts`) and one hook (`hooks/useTableSort.ts`), which
replaced the `sortBy` + `sortDir` pair and the click handler each page had been
re-implementing. Desktop: plain click sorts by one column as before, shift-click
adds a level, flips it, then removes it; a sorted header shows its position when
there is more than one. The Sort menu was rebuilt into the active levels
(numbered, each with ↑/↓ and a remove ×) above a "Then by" list, and Volume
surge and Investment gained that menu, which they had never had. Backend:
`sortBy`/`sortDir` became comma-separated lists on `ranking`, `volume-surge`
and `capex`, parsed by `_parse_sort_levels` and applied by `_apply_sort` — one
stable sort per level, least-significant first, which is what lets each level
keep its own direction. **A single level is byte-identical to the old request**,
so older clients and bookmarked URLs are untouched; the one contract change is
that an invalid `sortDir` answers `400` instead of `422`, since it can no longer
be a `Literal`. Verified live against the local PostgreSQL on all five pages:
sector+rating and signal+rating two-level sorts returning genuinely regrouped
rows, the full add→flip→remove cycle, the phone menu at 375 px, and the light
theme (the level badge measures 7.7:1 on white).

**Follow-up the same day: "it doesn't work".** It did — the request went out
as `sortBy=priceChangePct,currentRating`, the level badges appeared, no console
errors — but nothing on screen changed, and that is the only thing a user can
judge it by. Two causes compounded. The menu was `lg:hidden`, so on a desktop
the *only* way in was a shift-click that nothing advertises; and the Dashboard
opens sorted by Change %, where the 25 loaded rows held just 4 ties, so even a
correctly-added second level reordered almost nothing. Whether you never found
the gesture or found it and used it on a column with no ties, you saw the same
blank result. Fixed by dropping `lg:hidden` from the `SortMenu` on all five
pages: the control now sits in every toolbar at every width, naming the primary
column, carrying a "+1" when there is a tie-break, and listing the levels and
the "Then by" columns when opened. Verified live at 1440 px: Signal + Rating
grouped every Strong Buy with ratings descending 96, 95, 94, 93, 91, 87, 86, 86
— a list that visibly moved — with the trigger reading "Sygnał +1". Headers and
shift-click are unchanged; nothing about the sort *logic* moved, only its
visibility. One limit worth knowing: the menu lists the columns that are
switched on, so sorting by a hidden column means showing it first. Backend `pytest` **1075 green,
whole suite** — 20 of them new here: 16 in `tests/test_sorting.py` plus four
endpoint cases across `test_api.py`, `test_volume_surge.py` and `test_capex.py`
(the working tree also carries another session's in-progress `test_phase.py`,
so this total is not 1074 + 20) — and Ruff clean;
frontend `vitest` 170 → **193 green** (23 new across `lib/sorting.test.ts`, a
rewritten `components/SortMenu.test.tsx` and `pages/DashboardPage.test.tsx`),
`tsc -b`, ESLint and `npm run build` pass. Previously 2026-09-22: **Sign in — optional user accounts.** Krzysztof
asked for a login on the site, in the main window, with JWT tokens, everyone
able to create an account, and **no e-mails for now** — sending them goes on
the TODO list. Backend: `app/services/auth.py` (bcrypt hashing; two HS256
JWTs — a 30-minute access token and a 30-day refresh token, separated by a
`typ` claim so the long one can never be used as a credential; a `ver` claim =
`users.token_version` so a password change invalidates every earlier token
with no server-side store; a per-address and per-IP sign-in throttle),
`app/routers/auth.py` (6 routes), `app/db/user_repository.py`, the `users`
table (alembic `006`, created automatically at start-up). Frontend: a session
provider, the two tokens in localStorage, a **top-bar control** (Sign in →
initials + menu), a `/login` page carrying both Sign in and Create account
inside the normal app shell, and an **Account** section on Settings with the
only way a password changes today. Errors return `{ code, message }` so the
sign-in screen speaks Polish; "no such account" and "wrong password" answer
identically so the form cannot enumerate who is registered. `api/client.ts`
now attaches the bearer token and silently refreshes once on a 401, sharing
one refresh across concurrent calls. Verified live against the local
PostgreSQL: registered through the UI, avatar and menu, wrong password
(Polish message), sign out, sign in again, password change, the session
surviving a reload, both themes, both languages, and 375 px; the verification
accounts were deleted afterwards, leaving the table empty. Found and fixed
while verifying: the top bar had no stacking order, so the page toolbars
painted over the account menu (`relative z-30`), and the avatar initials read
the whole address, turning `ola.nowak@example.com` into "OC". Follow-up
2026-09-23: this shipped saying "set `STOCKPILOT_JWT_SECRET` on the VPS", and
Krzysztof answered that being signed out is not a problem — so **the secret
stays unset by choice** and the guides stopped calling it a required step
(`agent/DEPLOYMENT.md` is back to three lines to fill in). The public sign-in
page no longer shows an amber warning about a server setting a visitor cannot
act on; it says what it means for them instead, and the backend logs the fact
at INFO. The one caveat is written down where it matters: the secret becomes
required if the API ever runs more than one worker. Backend `pytest` 1024 → **1074 green** (50 new in
`tests/test_auth.py`), Ruff clean. Frontend: **13 new cases** —
`components/UserMenu.test.tsx` (the initials, the token store including
storage being blocked, the signed-out and no-accounts states) and six in
`api/client.test.ts` (the bearer header, the silent refresh and its replay,
giving up when the refresh is refused, and the structured error detail) —
green, as are `tsc -b`, ESLint and `npm run build` for this change. Previously 2026-09-22: **VSA V3.** Krzysztof supplied *Kompendium VSA*,
a transcript-based synthesis of all 34 recordings of the Glinicki course, and
asked for it as a new trading method. New `backend-python/app/analysis/methods/
vsa3.py` runs the course's seven-layer decision loop around Scenario 5, every
layer a hard gate (see the VSA V3 status entry above). Measured on the local
PostgreSQL with all six markets: the full loop completes 4 times in the whole
stored history of 1,014 companies, the three-signal sequence being the binding
layer; shown the numbers, Krzysztof chose this strict reading over two relaxed
ones. Two calibration fixes were made against measurement and are sourced: the
weakness-side Two Bar Reversal needs a rising move into it (it had matched one
bar in fifty), and Supply Coming In is not a veto at the peak (the course: it
"rarely makes the top by itself"). The weekly trend is read as two 13-week
blocks, because weekly swing points called steady advances undecided.
Verified: `evaluate()` and `signals()` agree over 5,628 truncated evaluations
(no look-ahead), no exception over the full history, ~2 ms per stock; live in
the app, the picker, column, chart layer (Orange Polska's 2025-10-08 "Hammer +
Test") and analytics summary all show it with no frontend change. Follow-up
the same day: Krzysztof pointed at Alior Bank's 15.09.2026 Hammer, which V3
"did not see". It did — Hammer + Shakeout at the end of an ABC correction, 5 of
7 layers — and refused it for R/R 2.6:1 and a missing test after the Shakeout,
but said nothing about it anywhere. `evaluate()` now assesses every layer of a
pattern at the low (`_assess`) and names a near miss in `detail` ("Hammer +
Shakeout today, not taken: no 3-signal sequence, R/R 2.6:1"). Asked again —
"I still don't see any pattern on chart" — the same near misses became **chart
markers**: a third `MethodSignal` type `"Watch"`, drawn as a muted square below
the bar and labelled with the reasons, with `MethodSignalItem.type` widened and
the back-test narrowed to judge `"Bullish"` markers only, so a refused pattern
can never become a trade in a statistic. Alior's chart legend went from
"VSA V3 0" to "VSA V3 2" (15.09 and 21.09). Firing, the score and the back-test
are unchanged; the case is pinned on real bars. Live verification caught what
the unit tests could not: the endpoint 500'd until the Pydantic `Literal`
accepted the new type. Backend `pytest` **989 green** (33 new), frontend
`vitest` **157 green**, Ruff, `tsc -b` and `npm run build` clean. Previously 2026-09-21: **"All markets" audit.**
Krzysztof reported that
with every market selected the Dashboard's companies were not all sorted
correctly. The sorting code was sound — every column monotonic — but the money
columns compared raw figures across five currencies, and London quotes in
pence: NVR, the most expensive stock in the list, sat at position 12 behind
nine London lines worth a twentieth of it. Fixed backend-side, only when
markets are pooled (price, volume-as-turnover and the price bounds on a common
złoty scale; figures never converted; a single market unchanged), with an
"≈ N PLN" line under each foreign price so the order is legible. Also fixed:
a pooled list silently mixing two sessions every evening (rows now carry
`lastSession`; a `SessionNote` says so). Left open as `ROADMAP.md` #26/#27:
cross-listed companies with contradictory ratings, and within-market RS
percentiles compared in the Combined column. Verified live against the local
PostgreSQL with all six markets, desktop and phone, both themes (the note's
amber passes AA at 6.3:1 on light). Backend `pytest` 940 → **949 green**, Ruff
clean; frontend `vitest` 142 → **155 green**, `tsc -b`, ESLint and
`npm run build` pass. Previously 2026-09-17: **Foreign markets — roadmap #22.** Krzysztof asked
for stocks from Germany, France, the Netherlands, the UK and the USA (NASDAQ,
S&P 500). Built in seven phases, all recorded in `agent/MULTI-MARKET-PLAN.md`:
a market registry (`app/markets.py`) and per-stock currency floors; 722
verified index members in `app/data/markets/`; a `market` parameter and
`GET /api/stocks/markets` in the API; per-market ingest, caches, rankings and
health, with a second nightly run at 17:15 New York time; a market selector,
market tabs, badges and currency-aware formatting in the frontend. The
heatmap and the method back-test stopped holding years of bars per stock, so
all six markets fit in ~700 MB. Verified end to end against the local
PostgreSQL with every market switched on (see the status entry above). Also
fixed in passing: the Polish refresh caption said "Zaktualizowano today". A
code review of the whole change found two minor bugs, both fixed with tests:
the System page put one nightly run's "running" state and error on the other
run's row (`RefreshService.run_markets` now says which markets a run covers),
and a failed `/api/stocks/markets` request hid the market selector for the
rest of the session instead of being retried. Not
done: production still serves the GPW only until `STOCKPILOT_MARKETS` is set
on the VPS. Backend `pytest` 684 → **940 green**, Ruff clean; frontend
`vitest` 113 → **142 green**, `tsc -b`, ESLint and `npm run build` pass.
Previously 2026-09-16: **System link removed from the sidebar** at the
owner's request — the `/system` page still works when its address is typed in,
and the unused `nav.system` label was dropped from `pl.json`/`en.json`.
Previously 2026-09-14: **VSA 2 audited and corrected** — see the VSA 2 audit
entry above. Previously 2026-09-10: **VSA 2 — a new trading method from the 30-lesson
Glinicki course.** Krzysztof supplied a second, much larger body of VSA
material: a written compendium of Rafał Glinicki's **30-lesson** XTB *Investing
Masters* course (13 h 32 min) and of his four 2018 XTB / VSA-Trader webinars
(8 h 41 min). It is not the five-lesson course behind the existing `glinicki`
method and it does not teach the same thing: its last nine lessons build **one
complete trade setup**, lesson 29's "SCENARIUSZ 5 – (long)" — the only slide in
either course that writes the entry conditions as text and puts a number on
reward-to-risk. New `app/analysis/methods/vsa2.py` (id `vsa2`, "VSA V2") is that
setup, with all six of its conditions as hard gates: a **measured place** (a
38.2 / 41.4 / 50 / 61.8 retracement of the last impulse up — 41.4 is not a
standard Fibonacci level but is written on the lesson-22 slide and repeated as
text in lesson 29 — or a bullish **WFO**, a lower price low on a lower *volume*
low), **no supply at the peak** the pullback fell from, **corrective volume**,
a bullish **candle formation confirmed by a VSA signal of strength** (the
slide's word is *potwierdzona*, so both are required, never either), and a
potential **R/R ≥ 3:1** to that peak with the stop under the formation. The
course's one exactly-computable volume rule — **pink volume**, `V_t < V_{t-1}
AND V_t < V_{t-2}` — is honoured verbatim. Two parts of the slide are
**deliberately not implemented rather than guessed**: the "end of an ABC
correction" route (the course never defines an ABC correction anywhere in 13
hours) and the signal *sequence* (it never says which of its fourteen signals
belong to which of its three categories, and flags that itself as the one
unassigned part of its taxonomy) — instead lesson 21's testing process, the one
sequence the material does pin down, is scored rather than gated. Two detectors
were rewritten after measurement showed them firing once per twenty
ticker-years — the fix is sourced, not tuned: the course's own notes say "the
drawing shows three candles, but nothing says three is a requirement". The whole
feature is three files (a new method, one import, its tests) because the
pluggable framework does what it promised: the method selector, the per-method
column, the combined score, the chart overlay layer, the analytics summary
source and the back-test endpoint all picked it up with **no frontend change at
all** — verified live on GPW data.

**VSA 2 audit and source-fidelity fixes (2026-09-14).** The method above was
audited rule-by-rule against the course compendium and separately for code
correctness. Four rules did not say what the course says, and fixing them
roughly **doubled the measured edge while halving the firings**: (1) there was
no **Buying Climax** test at the peak (lesson 14's K9, "ekstremum wolumenu na
szczycie trendu, po którym cena nie idzie już wyżej") — 19% of firings were
pullbacks bought out of a climactic top, the single thing *brak podaży w
szczycie* exists to refuse, and invisible to the old gate because a climax
arrives on a big **up** bar; (2) the **WFO** compared its low against local lows
from inside the *impulse* rather than the correction, so the whole rally could
stand in for the small bounce lesson 26 draws between the two lows — it was true
on ~45% of legs and was supplying most of the method's places, crowding out the
geometry route the course actually writes down; (3) the **Two Bar Reversal** had
no volume condition at all though lesson 11 draws the pair over two low volume
bars, making it a pure price shape that duplicated a Bullish Engulfing and let
one candle be both the formation *and* the VSA signal that lesson 29 requires to
confirm it; (4) **zero-volume bars satisfied "corrective volume"**, so a trading
halt inside the pullback read as the course's textbook quiet correction and
pushed the method into leaning bullish on a suspended stock. Also corrected:
lesson 3's per-formation stop (the Morning Star's goes under the **middle**
candle, `[Ź]`); formations are tried longest-span-first so a bar completing two
no longer gets the tighter stop and the inflated R/R that follows;
`_stopping_volume` judged its down bar against an average containing that bar;
`_inside_breakout` could measure a break against an inside bar instead of the
real mother bar; the posture score read the WM off a different low than the
setup gate, so a stock could fire and still publish "4/6"; and
`_no_supply_at_peak` now fails closed rather than passing vacuously on an
unauditable window. Measured after the fixes on 292 tickers / 588 ticker-years:
**0.20 firings per ticker-year** (>10× rarer than V1), 59 tickers, funnel 27764
formations → … → **116 firing**. On the app's own gate it is still the **only
shipped method that passes**, now far more convincingly: **+5.27 pp of edge at
30 sessions, 55.6% hit rate over 63 judged firings, R/R 2.53 — the gate's top
`strong` grade** (it was +1.91 pp / 49.3% / *fail* before the fixes, i.e. it did
not actually pass at the horizon the docs had claimed). Versus V1 +1.25 pp /
48.1%, VSA rating +1.21 pp / 44.4%, Volume Breakout +0.50 pp / 44.7% and
Minervini a *negative* −0.34 pp, all failing. Caveats that stay: at the gate's
default 10 sessions VSA 2 still fails (its target is the prior peak, weeks
away), the gate's pass condition is a >50% **hit rate** which is awkward for a
3:1-payoff method (`agent/ROADMAP.md` 23a/25), and 63 judged firings is a thin
sample. Verified clean by the same audits: **no look-ahead bias** (720 grafted
alternative futures, zero verdict changes), `evaluate()` and `signals()` agree
bar-for-bar (~5,800 truncated evaluations), `days_since` is calendar days like
every sibling, ~20 ms per 1,000-bar ticker. Backend `pytest` 680 → **684 green**
(4 new), Ruff clean, frontend untouched (verified live: the method's chip,
chart-overlay layer and analytics-summary row all still render).
Previously (2026-09-09): **Weekly rating on the
stock-detail page.** The
multi-timeframe weekly read shipped on 2026-09-04 for every ranking row, but
the only place it was ever shown was the Dashboard's small "1W ✓/✗" chip — the
stock page, the one screen about a single company, did not show it at all. The
**VSA Rating card** now has a "Weekly (1W)" section under the daily rating: the
weekly rating on a meter, its verdict badge, and one plain sentence saying
whether the higher timeframe confirms the daily call (green) or contradicts it
(rose); under ~30 weeks of history it says why it is blank instead of printing
an invented number. The to-do called this "pure frontend", but the weekly lived
only on the ranking payload — so `GET /api/stocks/{ticker}/signals` gained
`weeklyRating` / `weeklySignal` / `weeklyAgreement`, computed by the same
`app/analysis/weekly.py` over the same capped 52-week window the ranking uses
and folded out of the daily window that endpoint already fetches: no new
request, no new data source, and the card cannot contradict the chip (a test
asserts the two match for the same stock). It stays the **daily** read —
switching the chart to 30m or 1W does not move it, which another test pins.
Verified live on GPW data: AGO 97 daily / 63 weekly Buy → "confirms" in green,
WWL 85 daily / 25 weekly Sell → "contradicts" in rose, in both themes and both
languages. Backend `pytest` **642 green** (4 new), frontend `vitest` 110 →
**113 green** (3 new in the new `pages/ChartsPage.test.tsx`), `tsc -b` and
`npm run build` pass. Previously (2026-09-09): **Observability — error tracking and an ingest
health view (roadmap #19).** The app recorded what it did (the 2026-09-08
action log) but still could not answer the two questions that matter: *did last
night's job run?* and *what is broken?* Both now have a screen. New
`app/services/error_tracker.py` attaches an `ErrorTrackingHandler` to the
**root logger**, so every `logger.error`/`logger.exception` already written
anywhere in the codebase becomes a tracked error — no call site changed —
including failures that never reach an HTTP response. Errors are **grouped** by
error type + app source line + message *template* (digits collapsed), so an
ingest where 290 tickers fail is one row saying ×290 rather than 290 rows that
bury it; groups are mirrored into the action log as `kind="error"` entries
(throttled to one per group per minute, carrying an `occurrences` count, with
not-yet-written hits merged in at read time), which means they persist with
**no new table and no migration**. New `app/services/system_health.py` +
`app/db/health_repository.py` answer the ingest question: the last
`job.refresh`/`job.ingest` outcome measured against the scheduled 18:00
Europe/Warsaw run (`stale` = it came due and nothing happened, 90-minute
grace), cross-checked against what the database actually holds — newest
session, how many of the 288 companies carry it — because a refresh can report
success and still leave the data a week old. Partial coverage *while a refresh
is running* reports `updating`, not `stale`, or the page would cry wolf every
night at 18:00. `GET /api/admin/errors` + `GET /api/admin/health`; the new
**System page** (`/system`, sidebar bottom) shows both plus the recent-actions
table the action log had been missing a UI for — fully PL/EN, both themes,
mobile-safe, `noindex` and out of the sitemap. **Security:** all
`/api/admin/*` now sit behind an optional `STOCKPILOT_ADMIN_TOKEN`
(`X-Admin-Token` header) — unset locally, and `agent/DEPLOYMENT.md` now makes
setting it part of step 5 on the VPS, because these screens carry stack traces,
file paths and visitor IP addresses; the page warns when it is open and takes
the token itself. Verified live against PostgreSQL and real GPW data: a
bootstrap refresh reported 288 fetched / 0 failed / 108,899 bars in 3 min 40 s,
a repeated failing call showed as one group with ×6 read back from the
database, and the page correctly flagged a genuinely missed 18:00 run while the
machine sat idle. Backend `pytest` 642 green (44 new), frontend `vitest` 113
green (7 of them new here), `tsc --noEmit` and `npm run build` pass. **Still open, and the
next thing worth building:** nothing *pushes* a failure to a human — the page
tells whoever opens it (see `agent/ROADMAP.md` #19).
Previously (2026-09-09): **Corporate-action handling — roadmap #18.** The
stored price history now survives splits and dividends on one scale. Yahoo
serves adjusted prices and restates a stock's whole past the moment a corporate
action lands, but the nightly ingest only re-fetches five days — so the database
mixed the two scales, and a 1:10 split read as a 90% one-session crash on heavy
volume, i.e. a VSA selling climax that never happened. New
`backend-python/app/analysis/corporate_actions.py` compares each fresh fetch
against the stored bars it overlaps (0.5% threshold, prices only — Yahoo revises
volume for a day or two after the close and the re-fetch window already absorbs
that); `IngestService` answers a hit by re-downloading that ticker from its
first stored bar rather than topping up, then re-scales its rating snapshots via
two new repository methods (`get_quote_date_range`,
`resync_rating_snapshot_closes`). A failed repair writes **nothing** for the
ticker instead of mixing scales, and retries next run; repairs are counted in
the action log (`adjusted`, `adjustedTickers`). The fetch also widens to regain
overlap when a ticker's stored history ends before the window, and the
single-ticker read path (`_get_quotes`) stops splicing two scales together.
Verified live against the local PostgreSQL on a scratch ticker seeded at the
pre-split scale: 30 bars and 2 rating snapshots rebuilt from 100.00 to 25.00,
ratings untouched, the repair fetching from the first stored bar rather than the
five-day window, and a second run a one-fetch no-op. Backend `pytest` 615 →
**642 green** (27 new in `tests/test_corporate_actions.py`), Ruff clean.
Previously (2026-09-09): **Dashboard favorites filter, icon-only Refresh, and
reorderable ranking columns.** Three owner requests. (1) The Dashboard gained a
star toggle that narrows the ranking to the starred companies — it reuses the
ranking endpoint's `tickers` allow-list the way the Watchlist already did,
because the stars are localStorage-only and a client-side filter would cover
just the rows already scrolled in; an empty favorites list gets its own empty
state rather than "nothing matched your filters". (2) The Refresh button is now
icon-only, its word moved to the tooltip and the `aria-label`. (3) Ranking
columns can be reordered: every row in the **Columns** dropdown carries ▲/▼
arrows, the arrangement is a second localStorage key
(`stockpilot:ranking-column-order:v1`, kept apart from visibility so an
existing choice keeps working), and it is shared by the Dashboard, Watchlist
and Filters — table and phone card list alike. A *shown* column hops over
hidden neighbours in one click (with 8 of 14 columns off by default, stepping
one raw slot would often change nothing on screen); the identity column stays
pinned first, and `normalizeOrder` heals a partial, stale or duplicated stored
list. Verified live on GPW data at 1400 px and 375 px: the order survives a
reload and carries to the Filters page. Frontend `vitest` 88 → **103 green**
(15 new across `lib/rankingColumns.test.ts`, the new
`components/ColumnPicker.test.tsx`, and `pages/DashboardPage.test.tsx`),
`npm run build` passes. Also fixed in passing: `tsc -b` was already failing
before this work — `ChartsPage` imports `SignalVerdict` from
`api/stocksApi`, which only imported the type without re-exporting it.
Previously (2026-09-08): **Customizable ranking columns — roadmap #9.** The
Dashboard, Watchlist and Filters screener stopped hard-coding a table each and
now render from one registry, `frontend/src/lib/rankingColumns.tsx`, with a
**Columns** dropdown (`ColumnPicker`) over 14 columns and the choice shared by
all three pages (`hooks/useRankingColumns.ts`). The
owner asked for it to work on mobile, so the phone/tablet card list renders
from the *same* column list as the wide table — new
`components/RankingTable.tsx` holds both layouts (`RankingTable` +
`RankingCardList`) and places each column by a `mobile` slot — and every page
gained a `SortMenu` built from the visible columns, which the Filters and
Watchlist pages had been missing entirely below `lg`. Two dormant files from an
earlier commit (`ColumnPicker.tsx`, `rankingColumns.tsx`) that nothing imported
were the starting point. Default set is a 945 px table, narrower than any of
the three it replaced; no new requests (every column reads a field the ranking
payload already carried). Verified live on GPW data across all three pages at
1280 px and 375 px. Frontend `vitest` 66 → **88 green** (22 new in
`lib/rankingColumns.test.ts` + `components/RankingTable.test.tsx`),
`tsc -b` and `npm run build` pass. Previously (2026-09-08): **Legal
information page.** The site is public at
stocksignal.pl but carried no disclaimer, terms, privacy policy or publisher
contact — it now has all four. New `/legal` page (`LegalPage.tsx`) written to
the MAR / Reg. 2016/958 checklist for published investment recommendations,
plus the art. 8 UŚUDE regulamin and a GDPR privacy policy; a new `Footer` puts
the short disclaimer, the publisher's contact and the link on every page, and a
`DisclaimerNote` sits under the Dashboard ranking heading and the stock-detail
header. All copy in `pl.json`/`en.json` (`legal.*`); publisher Krzysztof Klich,
kklich97@gmail.com, with `legal.publisher.address` deliberately empty until a
postal address is chosen. Flagged but NOT fixed by this work
(`agent/DOCUMENTATION.md` §12): Yahoo/stooq market data is redistributed
publicly against those providers' terms, which is the app's real legal
exposure. Frontend `vitest` 66 green (6 new), `npm run build` and
`tsc --noEmit` pass. Previously (2026-09-08): **API action logging — an audit
trail.** The app
kept no record of what it did: console output only, gone on restart. Now every
API call and every background job is recorded and saved — new
`app/services/action_log.py` (entry + service + middleware),
`app/db/action_log_repository.py` and the `action_logs` table (alembic `004`),
read back at `GET /api/admin/logs` and `GET /api/admin/logs/summary`
(`app/routers/admin.py`). Each entry is written to a rotating JSON-lines file
(`backend-python/logs/actions.jsonl`), to the database when one is configured
(queued and batched, never on the request path, pruned after 30 days) and to an
in-process buffer so it works stateless too. Requests are grouped by route
template and carry an `X-Request-Id`; the refresh and ingest jobs write their
own started/finished/**failed** entries with counters, so a nightly run that
fetched nothing is no longer silent. The `settings` blob is fingerprinted
rather than stored, `/health` and CORS preflights are excluded. Backend
`pytest` 567 green (42 new); verified live against the running backend with
PostgreSQL attached. Previously (2026-09-07): **Stale GPW symbols.** Three tickers had been
erroring on every scan. CCC S.A. renamed itself Modivo on 2026-02-19 (GPW
ticker CCC → MDV, Yahoo moved the full history to `MDV.WA`), Santander Bank
Polska became Erste Bank Polska and was already tracked as `ebp`, and Wojas was
withdrawn from the Main Market on 2024-11-08 — so `gpw-companies.json` is now
288 companies with `ccc` renamed to `mdv` and `spl`/`woj` dropped. The class of
failure is handled too: a "no data for this ticker" answer is now logged once
and remembered for an hour (`NEGATIVE_CACHE_SECONDS` in
`app/services/cache.py`, applied by the ranking, heatmap and volume-surge
scans) instead of being re-requested and re-logged by every scan, the warning
says "data provider error" rather than mislabelling Yahoo as stooq, and
`yfinance`'s own duplicate ERROR line is silenced in `app/main.py`. Verified
live: MDV, EBP and KGH all rank, and two consecutive scans over a dead symbol
now print one warning instead of six lines. Backend `pytest` 525 green (3 new).
Previously (2026-09-05): **Light and dark themes.** The app gained a second
theme. `frontend/src/index.css` now carries two palettes — the bare `:root`
block is light (the neutral ramp reversed, accents darkened for white) and
`.dark` restates Tailwind's own defaults, so the dark theme is unchanged to
the shade. `src/lib/theme.ts` owns the Light / Dark / System preference
(default dark, stored in `localStorage['stockpilot:theme']`, applied as the
`dark` class on `<html>`), an inline script in `index.html` applies it
before first paint, and `src/lib/chartTheme.ts` re-colours what CSS cannot
reach: the Lightweight-Charts candles, the heatmap tiles and the method
markers. New `ThemeToggle` in the top bar and a real `SettingsPage`
(Appearance) replacing its placeholder. Contrast on white was measured and the
muted steps darkened until they pass WCAG AA. `vitest` 22 → 33 green.
Previously (2026-09-05): **Chart timeframes — 30m / 1H / 4H / 1D / 1W.** The
stock chart was daily-only; it now has a bar-size selector beside the range
buttons. New `app/analysis/timeframe.py` holds the interval table and the
intraday aggregation (grouping never spans the overnight gap, so a GPW session
becomes two 4h bars with the 17:00 auction folded in), `YahooFinanceClient`
gained `get_intraday_history`, and `GET /{ticker}/signals` gained an `interval`
parameter. Daily bars are unchanged and their payload byte-identical; weekly is
aggregated from them; 30m/1h are fetched live from Yahoo (not stored, so capped
at ~60 days / ~2 years) and 4h is built from the hourly bars. The timeframe
changes only the chart: the header rating, price and method overlays stay the
daily read, so the chart can never contradict the dashboard or the summary
cards. Verified live on GPW data (JSW: rating 84 across all five intervals,
30m clamped to 60 days and reported as such). Backend `pytest` 446 green (28
new), frontend `vitest` green (8 new).
Previously (2026-09-04): **VSA Glinicki V1 trading method.** New
`app/analysis/methods/vsa_glinicki.py` (id `glinicki`) mechanises the buying
half of Rafał Glinicki's five-lesson XTB VSA course as the course's own master
algorithm — phase → background → zone → formation → effort-vs-result — with six
bullish formations and all three of its disqualifiers as hard gates. It
self-registers, so it appeared in the method selector, combined score, chart
overlay, analytics summary and back-test endpoint with no other wiring.
Measured on 291 stored GPW tickers: 3.66 firings per ticker-year, 260 tickers
with at least one, available on all 291 (needs only 70 bars). A Hammer
relative-spread floor was added after the data showed 16% of matches were bars
under half a normal day's range. Not yet back-test-proven on the full 4-year
window — its score should not guide money until
`GET /api/stocks/methods/glinicki/backtest` is run. Backend `pytest` 418 green
(20 new tests).
Previously (2026-09-04): **Multi-timeframe weekly analysis — roadmap #8.**
New `app/analysis/weekly.py` resamples stored daily bars into ISO-week candles
and runs the same VSA engine (same user `settings`) over them; every ranking
row now carries `weeklyRating` / `weeklySignal` / `weeklyAgreement`, the
Dashboard shows a "1W ✓ / 1W ✗" chip beside the signal badge, and the ranking
gained a `weeklyConfirms` filter and a `weeklyRating` sort. No new data source,
no extra fetch, daily ratings unchanged; blank below ~30 weekly bars. Verified
against live GPW data (126 ranked: 16 confirm, 5 conflict, 105 neutral).
Backend `pytest` 417 green, frontend `vitest` 22 green. Previously
(2026-09-03): **Trading-method audit + Tier-1/Tier-2 refactor.** Each method was verified against its canonical source (VSA → Tom Williams *Master the Markets*; Minervini → *Trade Like a Stock Market Wizard*; Volume Breakout → O'Neil CANSLIM + Minervini VCP). Tier-1 bug fixes: Volume Breakout's two dead firing rules removed + zero-range strong-close fixed; Minervini's truncated 52-week window + left-edge chart marker fixed; VSA warm-up comment corrected. Tier-2 methodology upgrades (these shift ratings — a data refresh is advisable): VSA trend-context/background gate (`VsaConfig.use_trend_context`, on by default) + SOS resistance-break + climactic-volume reclassification; Minervini rule 8 (universe RS-rank ≥ 70) in the ranking path; Volume Breakout now fires only out of a real, tight base. Backend `pytest` 361 → 381 green. Previously: Generic **GPW back-test gate** — `app/services/method_backtest_service.py` + `GET /api/stocks/methods/{id}/backtest` — proves any trading method on stored GPW history via its `signals()`: judges every long firing's forward return vs the stock's own median move and `passes` when it beat that baseline > 50% of the time with a positive average edge (informational only for now — the ranking does not yet enforce it). Earlier same day: Volume Breakout trading method (`volume_breakout.py`, id `breakout`); single-stock Volume (RVOL) + Investment (capex) cards + `/{ticker}/volume`; consolidated analytics-opinion summary card + `/opinion-summary` — roadmap #24.)*
