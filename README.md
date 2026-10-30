# StockPilot — VSA Stock Scanner (GPW)

Volume Spread Analysis scanner for the Warsaw Stock Exchange. Ranks GPW-listed
stocks by a computed VSA Rating (0–100), charts them with signal overlays
(Spring, Upthrust, Test, SOS, SOW, No Demand), and refreshes once daily after
the GPW close.

## Layout

| Path | What it is |
|------|------------|
| `frontend/` | React + TypeScript + Vite app (dashboard, charts, screener, heatmap) |
| `backend-python/` | Python 3.12 + FastAPI API, PostgreSQL, the VSA engine (`app/analysis/`) |
| `deploy/` | VPS setup, deploy and backup scripts + the host Nginx site |
| `.github/workflows/` | CI (lint, tests, builds) and SSH deploy |
| `agent/` | All project documentation & reference material (gitignored) |

## Run locally (Windows)

Double-click **`run-all.bat`** — it starts the API on
<http://localhost:5111> (docs at `/docs`) and the web app on
<http://localhost:5173>. `run-backend-python.bat` and `run-frontend.bat` start
one half each. Requires Node.js LTS and Python 3.11+.

```powershell
cd backend-python; .\.venv\Scripts\python.exe -m pytest -q   # backend tests
cd frontend; npm run build                                    # frontend build
```

## Account watchlists

Sign in and use **New list** on the dashboard or Watchlist page to create named
watchlists. The active list is shared by the ranking, stock-detail star and
long-term watchlist filter. Stars add/remove a company in that list; the same
company can belong to multiple lists. Switch off **Active list only** on the
Watchlist page to browse and add other companies.

Lists are private to the account and stored in the database (up to 20 lists,
500 companies each). They refresh when the browser tab regains focus and every
minute while visible. The selected list is remembered per account in each
browser. Rename and delete controls are beside the list selector; at least one
list is retained.

Guests keep their existing browser-local favorites. After signing in, **Copy
browser favorites** merges them into the active account list without removing
the local copy or overwriting other saved companies. Signing out returns to the
guest favorites. Account-list errors are shown explicitly; failed writes are
not presented as saved.

The database table is created by normal startup schema initialization. Deployments
managed with Alembic should apply revision `010` (`alembic upgrade head`).

## Observation journal

Signed-in users can save an observation from a stock's chart page and find all
their entries under **Observation journal** in the sidebar. Notes, confirmation
and invalidation conditions are private to the account, alongside a frozen copy
of the completed chart candles, visible signal layers and method scores. The
snapshot stores chart data, not a screenshot: it can be viewed interactively
without fetching or recalculating its historical evidence. It retains up to the
last 5,000 loaded candles; unfinished live candles are excluded. Score-session
dates are shown separately from the chart interval and observation creation time.

The original scenario and snapshot are immutable. Users can update the outcome
(observing, confirmed, invalidated, closed), add conclusions, compare the frozen
chart with current data, or explicitly delete the entry. Concurrent outcome edits
require reloading rather than overwriting a newer version. Repeating an uncertain
creation request uses the same entry ID to avoid duplicate observations.

Journal data is stored only in the account database, with a limit of 500 entries.
The new table is created at backend startup; Alembic-managed deployments should
apply revision `011`. Guests are prompted to sign in and do not get a local diary.

## Deploy to production

Full owner's walkthrough (DNS, SSH, TLS, updates, troubleshooting):
**`agent/DEPLOYMENT.md`**. Short version, on an Ubuntu VPS:

```bash
sudo bash deploy/vps-setup.sh        # once: Docker, Nginx, Certbot, firewall
cp .env.prod.example .env.prod       # set DOMAIN and POSTGRES_PASSWORD
bash deploy/deploy.sh                # build + start (db, api, web)
sudo certbot --nginx -d YOURDOMAIN   # after installing deploy/nginx/stockpilot.conf
```

Updates afterwards are `bash deploy/deploy.sh`, or automatic on push to `main`
once the `VPS_HOST` / `VPS_USER` / `VPS_SSH_KEY` GitHub secrets are set.
