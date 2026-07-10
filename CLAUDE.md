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
frontend/   React + TypeScript (Vite)   → src/{api,components,hooks,types}
backend/    Python + FastAPI Web API     → app/{routers,schemas,services,db,jobs,data}, alembic/, tests/
.github/workflows/   CI/CD
agent/      ALL project documentation & reference material lives here:
              - DOCUMENTATION.md   Full project specification
              - Blueprint (.docx), VSA source text (.pdf), reference images
            (gitignored — do not commit)
```

> Documentation home: the `agent/` folder is the single source of truth for everything written about this app. New docs go here, not in the repo root.

## API contract (do not change without updating DOCUMENTATION.md)

- `GET /api/stocks/ranking` — dashboard feed. Returns ranked `StockRankingItem[]`. Supports `page`, `pageSize` (≤ 500), `settings`, plus server-side sorting/filtering: `sortBy` (one of ticker, name, lastPrice, priceChangePct, currentRating, ratingChange, lastSignal, daysSinceSignal, volume, sector, aiConfidence; default `currentRating`), `sortDir` (`asc`|`desc`, default `desc`), `q` (search ticker/name), `minRating` (0–100), `signal` (verdict filter), `tickers` (comma-separated allow-list, e.g. favorites). The count of all matching rows before pagination is returned in the `X-Total-Count` response header (exposed via CORS). Cached in-process per settings hash, recomputed after daily ingestion.
- `GET /api/stocks/{ticker}/signals` — chart feed. Returns `{ ticker, history[], vsaSignals[] }`. Supports `fromDate`, `toDate` (default last 12 months), `settings`.
- `GET /api/stocks/scanner/stats` — back-test effectiveness per signal type. Supports `settings`.
- `GET /api/stocks/{ticker}/fundamentals` — company description + financial ratios + quarterly reports.
- `GET /api/stocks/{ticker}/ai-analysis` — AI insight: second opinion on the rule-detected signals, computed **locally** by the built-in expert-system engine (`app/analysis/ai_insight.py`) — no external AI services or API keys. Returns `{ ticker, asOf, verdict, confidence, summary, signalAssessments[], keyObservations[], engine }`. Supports `settings`.
- `POST /api/stocks/refresh` — starts the **data-refresh pipeline** in the background (Yahoo ingest → ranking recompute with DEFAULT settings → daily rating snapshots saved to DB); returns 202 + status. This and the nightly 18:00 job are the ONLY triggers that pull fresh data from Yahoo. `GET /api/stocks/refresh/status` — same payload `{ state, lastStartedAt, lastRefreshAt, lastError, stocksRanked, dbEnabled }` for polling.
- `GET /api/stocks/{ticker}/rating-history` — stored daily rating snapshots `{ ticker, points[{date, rating, verdict, close}], source }` (the "attractiveness over time" chart). Supports `fromDate`, `toDate` (default last 12 months). Snapshots always use DEFAULT engine settings; when none exist yet the history is computed on the fly (`source: "computed"`).
- `settings` (optional, on the four analysis endpoints) — URL-encoded JSON with the user's per-signal VSA thresholds/toggles from the Scanner page (see `agent/CODEBASE-OVERVIEW.md` §3.1).

Mandatory ranking pre-filters: 20-session median turnover > 100,000 PLN; market cap > 100M PLN (applied when known from `company-details.json`).

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
  app runs stateless without it). Yahoo is queried **only** by the nightly
  18:00 refresh or the UI Refresh button (`RefreshService`,
  `app/services/refresh_service.py`); requests are served from DB/cache.
- **VSA engine is configurable:** the Scanner page's toggles + per-signal
  sliders are the real engine configuration, sent via the `settings` query
  parameter and applied by `app/analysis/vsa.py` (`VsaConfig`). Ranking,
  chart overlays and back-test stats all follow the user's settings.
- **Fundamentals:** the stock-detail page shows live market cap / P/E / EPS /
  dividend yield via `GET /api/stocks/{ticker}/fundamentals`.
- **Rating history (added 2026-07-10):** every refresh stores one VSA rating
  per (ticker, day) in `rating_snapshots`; the stock-detail page charts it
  ("Rating history" card) so the owner can see attractiveness change over time.
- **Tests:** backend `pytest` — 143 passing; frontend `npm run build` passes.
  Layout is responsive (sidebar drawer below `lg`, card lists below `md`).
- **Known gaps:** Filters & Settings pages are placeholders; favorites are
  localStorage-only; no frontend unit tests; see `agent/ROADMAP.md`.
- **Feature checklist:** `agent/FEATURE-CHECKLIST.md` — done/not-done list of
  all features, incl. planned "popular scanner" additions (2026-07-09).

---
*Last updated: 2026-07-10.*
