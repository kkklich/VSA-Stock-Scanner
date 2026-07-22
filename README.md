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
