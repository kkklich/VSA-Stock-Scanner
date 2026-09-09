#!/usr/bin/env bash
# StockPilot — deploy (or update) the app on the VPS.
#
# Run from the project folder on the server:
#   bash deploy/deploy.sh
#
# What it does: pull the newest code, rebuild the containers, start them, wait
# for the API to report healthy, then delete the images the update orphaned.
# Existing market data in the `pgdata` volume is never touched.

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || die "$ENV_FILE is missing. Copy it from .env.prod.example and fill in DOMAIN + POSTGRES_PASSWORD."

compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

# --skip-pull is for deploying local edits that aren't pushed to git yet.
if [[ "${1:-}" != "--skip-pull" ]] && [[ -d .git ]]; then
  say "Pulling the latest code"
  git pull --ff-only
fi

say "Preparing the action-log folder (./logs)"
# Where the API writes its record of every call and every background job:
# ./logs/actions.jsonl on THIS server, bind-mounted into the container.
# The container runs as uid 10001 (a non-root user created in its Dockerfile),
# which is not this account, so the folder has to be writable by that uid.
# chown needs root, so try it and fall back to a permissive mode when this
# script is not run with sudo. Files inside end up 0644 — readable by you,
# writable only by the app. If neither works the app just logs to the database
# and its in-memory buffer instead; it never fails to start over this.
mkdir -p logs
if chown 10001:10001 logs 2>/dev/null || sudo -n chown 10001:10001 logs 2>/dev/null; then
  chmod 0755 logs
  echo "logs/ is owned by the API container's user."
else
  chmod 0777 logs
  echo "Could not change the owner of logs/ (needs root) — made it writable instead."
fi

say "Building images (first run downloads a lot — expect several minutes)"
compose build

say "Starting containers"
compose up -d --remove-orphans

say "Waiting for the API to become healthy"
for i in $(seq 1 60); do
  if compose exec -T api python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5111/health', timeout=4).status == 200 else 1)" \
      >/dev/null 2>&1; then
    echo "API is healthy."
    break
  fi
  [[ $i -eq 60 ]] && die "API did not become healthy in 5 minutes. Check: docker compose -f $COMPOSE_FILE logs api"
  sleep 5
done

say "Removing images left over from previous builds"
docker image prune -f

say "Current status"
compose ps

cat <<'DONE'

Deployed. The site is served by the host Nginx on your domain.

Useful commands (run from this folder):
  tail -f logs/actions.jsonl                                                    # what the app is doing (saved; survives restarts)
  docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f api    # live backend console (lost on restart)
  docker compose -f docker-compose.prod.yml --env-file .env.prod restart api    # restart backend
  docker compose -f docker-compose.prod.yml --env-file .env.prod down           # stop everything (data kept)

The first start pulls ~400 GPW tickers from Yahoo Finance in the background;
the dashboard fills in over the following few minutes.
DONE
