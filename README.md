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

## Personal portfolios

Signed-in users can open **My portfolio** in the sidebar and create up to 20
private portfolios, each with a name and broker. Record a purchase or sale with
the transaction date, tracked instrument, quantity, price per share and optional
fees. The quote currency is selected from the instrument; London pence are shown
as GBX. Each portfolio supports up to 1,000 transactions.

Positions show remaining quantity, average cost including purchase fees, latest
available price, quote date, market value and unrealized profit/loss. Sales use
FIFO by default, with moving average available per portfolio, and deduct sale
fees from realized profit/loss. Changing the cost method recalculates the ledger
without modifying recorded transactions. Add trades on the same date in execution
order. Backdated changes and transaction deletions
are rejected if they would leave a historical short position. To correct a trade,
delete it and record its replacement; dependent sales may need removing first.

Valuation uses the latest stored closing quotes and newer available intraday
quotes from the existing hourly price service. It does not request a fresh market
download when the page is refreshed. Quote dates are shown separately from the
calculation timestamp. Missing prices leave the complete currency valuation
unavailable rather than displaying a partial total. Each currency has its own
totals; no indicative FX rates are applied. Dividends, corporate actions, cash
balances and tax accounting are not automatically recorded.

The page explains its calculation rules, separates closing and intraday quotes,
and flags quotes older than seven calendar days (an informational threshold,
not a holiday calendar). Its percentage P/L is relative to remaining cost basis;
it is not an annualized or cash-flow-adjusted return. Calculation references:
[IBKR portfolio fields](https://www.ibkrguides.com/ibkrdesktop/account-portfolio.htm),
[Portfolio Performance cost methods](https://help.portfolio-performance.info/en/concepts/cost-methodology/),
[transaction currency and fees](https://help.portfolio-performance.info/en/reference/transaction/buy-sell/).

Portfolios are saved in the account database and reloaded on browser focus and
every minute while visible. Version checks prevent overwriting edits from another
device; unchanged creation and trade requests can be retried without duplicates.
Guests are prompted to sign in. Startup creates the new table; Alembic-managed
deployments should apply revision `013` (`alembic upgrade head`).

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
