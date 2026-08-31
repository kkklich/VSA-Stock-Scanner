# Build recipe: add a scanner to StockPilot (file-by-file)

Every touch-point to turn a vetted, EOD-computable trading rule into a full
scanner, mirroring the existing **`/volume-surge`** feature end to end. Do the
phases in order; the frontend can't be built before the endpoint returns data.

> The codebase is the source of truth. Before copying anything here, open the
> current `/volume-surge` files and match their present shape — this recipe
> describes the pattern as of the VSA/GPW app in 2026-08 and may drift.

Naming: pick a short kebab-case route `<name>` (e.g. `momentum`,
`breakout-52w`), a PascalCase model/component base `<Name>`, and a snake_case
service base `<name>`.

## Table of contents
1. [Decide the shape: screen vs ranking column](#1-decide-the-shape)
2. [Backend — indicator (optional)](#2-backend-indicator-optional)
3. [Backend — Pydantic models](#3-backend-models)
4. [Backend — the scan service](#4-backend-service)
5. [Backend — the router endpoint](#5-backend-endpoint)
6. [Backend — tests](#6-backend-tests)
7. [Frontend — API client](#7-frontend-api)
8. [Frontend — data hook](#8-frontend-hook)
9. [Frontend — the page](#9-frontend-page)
10. [Frontend — wiring (route, sidebar, seo)](#10-frontend-wiring)
11. [Docs](#11-docs)
12. [Verify](#12-verify)

---

## 1. Decide the shape

Two shapes exist; pick per method:

- **Dedicated screen (default, mirrors `/volume-surge` and `/capex`).** Scan the
  whole universe, return only the companies that currently match. Best when the
  method is a *setup* (breakout, surge, contraction) that most stocks don't have
  on any given day. This recipe builds this shape.
- **Per-company score / ranking column.** If the method is a *continuous score*
  every stock always has (like the VSA rating, or a momentum rank), it may fit
  better as a new field on `StockRankingItem` computed in `ranking_service.py`,
  exposed as a new sortable/filterable column and added to the column picker
  (`frontend/src/lib/rankingColumns.tsx`, `ColumnPicker.tsx`). Same math, but no
  new page. Ask the user which they want if it's ambiguous.

---

## 2. Backend — indicator (optional)

If the rule needs an indicator the repo doesn't have yet (moving averages, RSI,
momentum, ATR), add a **pure, I/O-free, unit-tested** function under
`backend-python/app/analysis/` — same spirit as `returns.py` and
`statistics.py`. Keep it a plain function over a bar list so the backtest and
the service both call it and the tests are trivial. Reuse `app.analysis`
helpers already there (`median_volume_pln`, etc.) before writing new ones.

---

## 3. Backend — models

In `backend-python/app/models/stocks.py`, add two classes subclassing
`_CamelModel` (it emits camelCase JSON aliases automatically), copying the shape
of `VolumeSurgeItem` / `VolumeSurgeResponse`:

```python
class <Name>Item(_CamelModel):
    """One matching stock in ``GET /api/stocks/<name>``."""
    ticker: str
    name: str
    sector: str | None = None
    last_price: float
    # … the method's own metric fields (snake_case; aliased to camelCase) …
    current_rating: int          # VSA rating, for context (same as ranking)
    last_signal: str             # VSA verdict, for context

class <Name>Response(_CamelModel):
    as_of: date | None = None
    # echo any tunable knobs (windows/thresholds) the scan ran with
    scanned_count: int = 0       # passed pre-filters and had enough history
    total_count: int = 0         # matches before pagination (pager total)
    items: list[<Name>Item] = []
```

Then re-export both names in `backend-python/app/models/__init__.py` — add them
to the import block **and** to `__all__` (the router imports from `app.models`).

---

## 4. Backend — service

Create `backend-python/app/services/<name>_service.py` by mirroring
`volume_surge_service.py`. Keep these load-bearing pieces — they encode the
project's pre-filters and hard-won bug fixes:

- **Constants:** `_HISTORY_DAYS = 120` (analysis window), `_MIN_MEDIAN_VOLUME_PLN
  = 100_000.0`, `_MIN_MARKET_CAP_PLN = 100_000_000`, `_MAX_CONCURRENT = 4`,
  `_MAX_SESSION_LAG_DAYS = 10`. Import `CONTEXT_HISTORY_DAYS` from
  `ranking_service` for the *fetch* window.
- **A frozen dataclass** `<Name>Metrics` holding the pure arithmetic, and a pure
  `compute_<name>_metrics(quotes, **knobs) -> <Name>Metrics | None` that returns
  `None` when history is too short or the setup can't be scored (distinct from
  "no match"). This is the unit-tested core.
- **`async def compute_<name>(companies, stooq, history_cache, history_cache_ttl,
  repo=None, today=None, config=None, **knobs) -> <Name>Response`** that:
  - sets `from_date = today - timedelta(days=CONTEXT_HISTORY_DAYS)` and
    `analysis_from = today - timedelta(days=_HISTORY_DAYS)`;
  - fetches quotes cache → repo → stooq using the **shared** cache key
    `f"history:{ticker}:{from_date}:None"` (identical to the ranking, so scans
    share one warm per-ticker history) and persists any stooq fetch via
    `repo.upsert_quotes`;
  - slices `recent = [q for q in quotes if q.date >= analysis_from]`, skips if
    `len(recent) < 25`;
  - applies pre-filters inside a `try/except` so one malformed stock can't 500
    the scan: market-cap gate, `median_volume_pln(recent) < _MIN_MEDIAN_VOLUME_PLN`;
  - computes metrics, appends `recent[-1].date` to a `session_dates` list, then
    applies the method's threshold;
  - adds VSA context on the same window/settings for the row:
    `signals = detect_signals(recent, config)`, `as_of = recent[-1].date`,
    `rating = compute_rating(signals, as_of)`,
    `verdict, _ = verdict_from_signals(signals, as_of)`;
  - runs all tickers with `asyncio.gather(..., return_exceptions=True)`, then
    **logs every `BaseException` per ticker** (a mid-scan DB failure must not
    return an empty 200 that looks like a quiet market);
  - drops stale listings with the recency filter (`latest_session =
    max(session_dates)`, keep rows within `_MAX_SESSION_LAG_DAYS`);
  - sorts, sets `as_of = max(match dates)`, returns the `<Name>Response`.

---

## 5. Backend — endpoint

In `backend-python/app/routers/stocks.py`:

- Import the models (`<Name>Item`, `<Name>Response`) and the service symbols
  (`compute_<name>`, any `DEFAULT_*` knobs).
- Add a **sort whitelist** `_<NAME>_SORT_KEYS: dict[str, str]` mapping the
  camelCase keys the frontend sends → the item attribute names (copy
  `_SURGE_SORT_KEYS`). The shared helper `_sort_value(item, attr)` already
  handles the mixed string/number/`last_signal` columns.
- Add `_<name>_locks: dict[str, asyncio.Lock] = {}`.
- Add the endpoint, mirroring `get_volume_surge`:

```python
@router.get("/<name>", response_model=<Name>Response, response_model_by_alias=True,
            summary="…")
async def get_<name>(
    # knob Query params with camelCase aliases + ge/le bounds …
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, alias="pageSize")] = 25,
    sort_by: Annotated[str, Query(alias="sortBy")] = "<defaultCol>",
    sort_dir: Annotated[Literal["asc", "desc"], Query(alias="sortDir")] = "desc",
    vsa_settings: Annotated[str | None, Query(alias="settings")] = None,
    companies: Annotated[GpwCompanyService, Depends(get_gpw_company_service)] = ...,
    stooq: Annotated[StooqClient, Depends(get_stooq_client)] = ...,
    cache: Annotated[TTLCache, Depends(get_ranking_cache)] = ...,
    history_cache: Annotated[TTLCache, Depends(get_history_cache)] = ...,
    repo: Annotated[QuoteRepository | None, Depends(get_quote_repository)] = ...,
) -> <Name>Response:
    if sort_by not in _<NAME>_SORT_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="…")
    config = _parse_vsa_settings(vsa_settings)
    cache_key = f"<name>:{…knobs…}{config.cache_suffix()}"
    full = cache.get(cache_key)
    if full is None:
        lock = _<name>_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            full = cache.get(cache_key)
            if full is None:
                generation = cache.generation
                full = await compute_<name>(companies=companies.get_companies(),
                    stooq=stooq, history_cache=history_cache,
                    history_cache_ttl=settings.history_cache_seconds,
                    repo=repo, config=config, **knobs)
                cache.set_if_generation(cache_key, full,
                    settings.history_cache_seconds, generation)  # generation guard
    # cheap per-request sort + slice over the cached full scan
    attr = _<NAME>_SORT_KEYS[sort_by]
    ordered = sorted(full.items, key=lambda i: _sort_value(i, attr),
                     reverse=sort_dir != "asc")
    start = (page - 1) * page_size
    return full.model_copy(update={"items": ordered[start : start + page_size]})
```

The cache lock + `set_if_generation` generation guard keep concurrent cold
requests from double-computing and stop a result computed mid-refresh from being
cached stale.

---

## 6. Backend — tests

Add `backend-python/tests/test_<name>.py` (repo convention: `test_<name>.py`,
see `test_volume_surge.py`). At minimum unit-test the pure
`compute_<name>_metrics` across: not enough history → `None`, a clear match, a
clear non-match, and any boundary of the threshold. An endpoint smoke test
(sort whitelist rejects a bad `sortBy`, pagination slices) is a good extra.

---

## 7. Frontend — API

In `frontend/src/api/stocksApi.ts`, add (copy the volume-surge block):
`Api<Name>Item`, `Api<Name>Response` (with `asOf`, `scannedCount`, `totalCount`,
`items`), a `<Name>SortKey` union matching the backend whitelist, a `<Name>Query`
interface (knobs + `page`/`pageSize`/`sortBy`/`sortDir`/`settings`), and
`fetch<Name>(query)` that builds the `URLSearchParams` and calls
`apiFetch<Api<Name>Response>('/api/stocks/<name>' + qs)`.

## 8. Frontend — hook

Add `frontend/src/hooks/use<Name>.ts` by copying `useVolumeSurge.ts`: infinite
scroll (append on `page > 1`, dedupe by ticker), reset to page 1 when a knob or
sort changes, and pass `settings: settingsQueryValue()` so VSA ratings match the
rest of the app. `hasMore = items.length < meta.totalCount`.

## 9. Frontend — page

Add `frontend/src/pages/<Name>Page.tsx` by copying `VolumeSurgePage.tsx`: a
sortable table of the item fields, the knob controls (persist them with
`usePersistentState`, key `stockpilot:<name>:…`), an IntersectionObserver
sentinel driving `page`, and the shared table/badge components from
`components/ui.tsx`. Reuse the rating/verdict badge styling used elsewhere
(green > 70, red < 30).

## 10. Frontend — wiring

- `frontend/src/App.tsx`: import the page, add `<Route path="<name>"
  element={<<Name>Page />} />`, and add a `titleForPath` branch
  `if (pathname.startsWith('/<name>')) return '…'`.
- `frontend/src/components/Sidebar.tsx`: add a `navItems` entry `{ to: '/<name>',
  label: '…', icon: <LucideIcon>, match: (p) => p.startsWith('/<name>') }` and
  import the icon from `lucide-react`.
- `frontend/src/lib/seo.ts`: add an entry `{ test: (p) =>
  p.startsWith('/<name>'), entry: { title: '…', description: '…' } }`.

## 11. Docs

Project rule — docs live in `agent/` and `CLAUDE.md` stays in sync:
- `CLAUDE.md`: add the endpoint to the **API contract** list and a bullet under
  **Current status**.
- `agent/DOCUMENTATION.md` §5: document the endpoint's params + payload.
- `agent/CODEBASE-OVERVIEW.md`: note the new service + page.
- `agent/ROADMAP.md`: move item #23 (or the specific method) toward **Done**.

## 12. Verify

- Backend: `pytest` + `ruff` using the repo venv python (python isn't on PATH —
  use `backend-python/.venv`; see the memory note on the dev toolchain).
- Frontend: `npm run build` in `frontend/`.
- Optionally run the app (`/run` or `preview_start` with the `.claude/launch.json`
  server) and open `/<name>` to confirm it renders and returns rows.
- Report the backtest number, the new URL, and the sidebar entry to the user.
