#!/usr/bin/env bash
# StockPilot — dump the PostgreSQL database to a compressed file.
#
#   bash deploy/backup-db.sh                 # writes ./backups/stockpilot-YYYY-MM-DD.sql.gz
#
# Keeps the 14 most recent dumps and deletes older ones.
#
# To run it automatically every night at 03:00, add a cron entry on the VPS
# (`crontab -e`), using the absolute path to your checkout:
#   0 3 * * * cd /home/YOURUSER/stockpilot && bash deploy/backup-db.sh >> backups/backup.log 2>&1
#
# To RESTORE a dump into an empty database:
#   gunzip -c backups/stockpilot-2026-07-22.sql.gz | \
#     docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db psql -U stockpilot stockpilot

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
KEEP=14

[[ -f "$ENV_FILE" ]] || { echo "ERROR: $ENV_FILE is missing." >&2; exit 1; }

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
DB_USER="${POSTGRES_USER:-stockpilot}"
DB_NAME="${POSTGRES_DB:-stockpilot}"

mkdir -p backups
OUT="backups/stockpilot-$(date +%F).sql.gz"

echo "Dumping database '$DB_NAME' → $OUT"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T db \
  pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$OUT"

echo "Wrote $(du -h "$OUT" | cut -f1)"

# Delete all but the newest $KEEP dumps.
ls -1t backups/stockpilot-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
  echo "Removing old backup $old"
  rm -f "$old"
done
