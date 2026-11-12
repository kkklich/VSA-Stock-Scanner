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

Stock list URLs remember search, filters, favorites-only mode and sorting
(including multiple sort levels). For example,
`/?sortBy=priceChangePct&sortDir=desc&favorites=1` opens the dashboard sorted
by change with favorites only. The dashboard, Filters, Volume surge, Investment
and Long-term pages restore these choices on refresh and browser Back/Forward.
Favorites-only links use the viewer's own saved stocks; they do not share private
watchlist contents.

Sign in and use **New list** on the dashboard to create named
watchlists. The active list is shared by the ranking, stock-detail star and
long-term watchlist filter. Stars add/remove a company in that list; the same
company can belong to multiple lists. Use the dashboard ranking to browse and
add other companies.

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

## Saved filter presets

On **Filters**, set the criteria, choose **Save preset**, and give it a name.
Signed-in users can apply or delete their presets on any device using the same
account. The list refreshes when you return to the tab and periodically while
it is open.

Guests save presets in the current browser. After signing in, choose **Copy
browser presets** to add existing local presets to your account. The browser
keeps its copies for guest use. Each account can store up to 100 presets.
For Alembic-managed databases, apply revision `015` with `alembic upgrade head`.

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
calculation timestamp. The all-wallet overview lists holdings with missing quotes
and shows the available subtotal by quote currency and in PLN using NBP rates.
The one-day and seven-day changes use positions that can be valued at both ends
of the period, with purchases and sales included. Dividends, corporate actions,
cash balances and tax accounting are excluded from the ledger.

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
Guests are prompted to sign in. Alembic-managed deployments should apply the
latest portfolio migrations with `alembic upgrade head`.

### Importing XTB account history

Open **Import from XTB** on **My portfolio**, choose an `.xlsx`, `.xls` or `.csv`
file (up to 5 MiB) and click **Preview import**. The importer checks the XTB account
number for an existing wallet. Choose the destination explicitly for older files
without account details when you want to update a saved wallet. Review the
destination, recognized trades, duplicates, warnings and rejected rows before
confirming. The whole batch is saved atomically after confirmation.

Export the full **Cash Operations** history from xStation, including operation
IDs, execution dates, tickers and execution comments. English and Polish column
names are recognized, with headers up to row 40. A CSV of executed trades can
instead contain `ID, Type, Time, Symbol, Quantity, Price, Currency, Commission`.
Use an unambiguous date (`YYYY-MM-DD HH:MM:SS` or `DD.MM.YYYY HH:MM:SS`). Extract
ZIP reports before uploading. Cash Operations takes precedence when the same
account also has position sheets. A position snapshot can initialize an empty
wallet. Use execution history for later trade updates.

Each XTB account wallet has one account currency. A holding can trade in a
different currency. Original operation IDs and trade
sides identify repeated imports, independently of filenames and row order.
Overlapping reports and retrying an uncertain save do not duplicate imported
trades. Conflicting data for an existing reference blocks the batch. Similar
manual transactions are flagged for review rather than silently matched.
Imported fills retain their reported execution times; manual date-only entries
are processed first on the same date. Include enough purchase history to cover
every sale. A batch that would create a historical short position is rejected.

Only tracked instruments are supported. Unsupported or invalid rows are listed;
skipping them requires an explicit choice. Cash, dividends, taxes, separate fees
and corporate actions are not imported. Missing inline commissions are shown as
zero with a warning. Prices come from execution fields/comments, never from an
account-currency cash amount. Foreign-currency commission conversion requires
manual reconciliation; the exact GBP/GBX unit conversion is supported when the
price currency is explicit. Nothing is downloaded from XTB or sent to a third
party during parsing, and the uploaded file is not stored.

Deploy the updated backend and frontend together.
The bundled Nginx configurations allow 5 MiB uploads. On an existing VPS, also
set `client_max_body_size 5m;` in the active host Nginx site and reload Nginx
after a successful `nginx -t`; otherwise its default 1 MiB limit may reject
larger reports before they reach the application.

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
