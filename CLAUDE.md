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

- `GET /api/stocks/ranking` — dashboard feed. Returns ranked `StockRankingItem[]`. Supports `page`, `pageSize`. Cached in-process (`cachetools` TTL), recomputed after daily ingestion.
- `GET /api/stocks/{ticker}/signals` — chart feed. Returns `{ ticker, history[], vsaSignals[] }`. Supports `fromDate`, `toDate` (default last 6–12 months).

Mandatory ranking pre-filters: 20-session median volume > 100,000 PLN; market cap (Close × shares outstanding) > 100M PLN.

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

Frontend layout scaffolded (mock-first). The Vite React+TS app now renders the
three core screens from the `agent/` mockups against local mock data:

- **Sidebar + top bar** shell (`components/Sidebar.tsx`, `components/TopBar.tsx`) with strict dark mode, market status, and last-EOD-sync label.
- **Watchlist** (`pages/WatchlistPage.tsx`) — ranking table: symbol/star, name, price + change, VSA rating meter, signal badge, days-since-signal, sparkline; search + pagination.
- **Stock detail / Charts** (`pages/ChartsPage.tsx`) — Siła/Słabość-rynku signal checklist, detection-settings strip, TradingView Lightweight Charts candlestick + volume + VSA markers (`components/StockChart.tsx`), and Dane podstawowe / Ocena VSA / Watchlista cards.
- **Scanner GPW** (`pages/ScannerPage.tsx`) — Silnik VSA rule toggles, signal tuner sliders, effectiveness donut + table.

Styling via **Tailwind CSS v4** (`@tailwindcss/vite`); icons via `lucide-react`; mock data in `src/data/mockData.ts`; shared types in `src/types/index.ts`. Navigation is state-based in `App.tsx` (swap for a router later). `npm run build` passes.

The layout is **responsive**: the sidebar collapses into a hamburger-toggled drawer below `lg`, and the watchlist table switches to stacked cards below `md`; pages use `p-4 sm:p-6` and the chart scales down on phones.

**Backends (two, same JSON contract):**

- `backend/` — ASP.NET Core / .NET 8 (the original). Endpoints: `GET /api/stocks`, `GET /api/stocks/{ticker}/history`. Runs on port 5123. Launch: `run-backend.bat`.
- `backend-python/` — **Python / FastAPI port** (added 2026-06-29). Same two endpoints, same payloads, same stooq.pl proof-of-work client, 6h in-memory TTL cache. Runs on port 5111 (so both backends can run side by side). Launch: `run-backend-python.bat`. Tests: `pytest` (11 passing). Future **statistics** and **VSA calculation** modules live in `backend-python/app/analysis/` (`statistics.py`, `vsa.py` — documented stubs today), kept isolated from the web/data layers for easy unit testing. See `backend-python/README.md`.

Next planned step: implement the `app/analysis/` statistics + VSA logic and add the `/api/stocks/ranking` and `/api/stocks/{ticker}/signals` endpoints, then wire the frontend `api/` layer to replace the mock data.

---
*Last updated: 2026-06-29.*
