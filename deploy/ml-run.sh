#!/usr/bin/env bash
# StockPilot — run one of the AI layer's research jobs on this server.
#
# Run from the project folder on the server (~/stockpilot):
#
#   bash deploy/ml-run.sh <job> [options]
#
# Jobs, in the order you normally use them:
#   backfill-dry   what the history back-fill WOULD do — downloads nothing
#   backfill       download long price history for training (decision D2).
#                  GPW by default; add  --markets all  for every market.
#                  Stops by itself if Yahoo starts refusing, and can be
#                  re-run: it continues where it stopped.
#   dataset        build the training datasets from the stored bars
#   bench          the test-bench report (needs `dataset` first)
#   train          fit and judge the models — every run is RECORDED as trials,
#                  so it asks before starting (add --yes to skip the question)
#   status         is a job running, how much memory it uses, its last lines
#   latest         print the newest report
#   stop           stop the running job
#
# A job runs in its own container (the `ml` service in docker-compose.prod.yml),
# capped at STOCKPILOT_ML_MEMORY (default 1g) and STOCKPILOT_ML_CPUS (default 1)
# from .env.prod, at low priority, in the background — you can close the SSH
# window and it keeps going. Only one job runs at a time.
#
#   Its console output:  ml-logs/<job>-<time>.log  (the last line says how it ended)
#   Its results:         ml/data, ml/reports, ml/trials.csv

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
LOG_DIR="ml-logs"
# Left by `stop` so the job's last log line says "stopped by hand" rather than
# guessing from the exit code (both a hand stop and the memory cap end in a kill).
STOP_MARK="$LOG_DIR/.stop-requested"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }
compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

usage() {
  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

running() {
  docker ps -q \
    --filter "label=com.docker.compose.project=stockpilot" \
    --filter "label=com.docker.compose.service=ml"
}

latest_log() { ls -t "$LOG_DIR"/*.log 2>/dev/null | head -n 1 || true; }

[[ -f "$ENV_FILE" ]] || die "$ENV_FILE is missing — run this from the project folder on the server."

job="${1:-}"
[[ -n "$job" ]] || usage 2
shift

case "$job" in
  -h|--help|help) usage 0 ;;

  status)
    ids="$(running)"
    if [[ -n "$ids" ]]; then
      echo "A job is running:"
      # shellcheck disable=SC2086
      docker stats --no-stream --format '  memory {{.MemUsage}}   cpu {{.CPUPerc}}' $ids || true
    else
      echo "No job is running."
    fi
    log="$(latest_log)"
    if [[ -n "$log" ]]; then
      say "Last lines of $log"
      tail -n 25 "$log"
    fi
    exit 0 ;;

  latest)
    report="$(ls -t ml/reports/*.md 2>/dev/null | head -n 1 || true)"
    [[ -n "$report" ]] || die "No report yet — run  bash deploy/ml-run.sh bench  (after  dataset)."
    say "$report"
    cat "$report"
    exit 0 ;;

  stop)
    ids="$(running)"
    [[ -n "$ids" ]] || { echo "No job is running."; exit 0; }
    mkdir -p "$LOG_DIR"
    touch "$STOP_MARK"
    # shellcheck disable=SC2086
    docker stop $ids >/dev/null
    echo "Stopped. A stopped back-fill continues where it stopped the next time you start it."
    exit 0 ;;

  backfill-dry) cmd=(python -m scripts.ml_backfill_history --dry-run) ;;
  backfill)     cmd=(python -m scripts.ml_backfill_history) ;;
  dataset)      cmd=(python -m scripts.ml_build_dataset) ;;
  bench)        cmd=(python -m scripts.ml_report) ;;
  train)        cmd=(python -m scripts.ml_train) ;;
  *) echo "Unknown job: $job"; usage 2 ;;
esac

[[ -z "$(running)" ]] || die "A job is already running — see  bash deploy/ml-run.sh status  (or stop it)."

args=()
yes=false
for a in "$@"; do
  if [[ "$a" == "--yes" ]]; then yes=true; else args+=("$a"); fi
done

if [[ "$job" == "train" && "$yes" != true ]]; then
  echo "Training is RECORDED: every run adds its variants to ml/trials.csv, and the"
  echo "statistics that judge the models get stricter with every run (that is on purpose)."
  read -r -p "Start a recorded training run now? Type yes: " answer
  [[ "$answer" == "yes" ]] || { echo "Not started."; exit 0; }
fi

if [[ "$job" == "backfill" ]]; then
  # The site's own refresh talks to Yahoo at 18:00 and ~23:15 (Warsaw) on
  # weekdays, and for live prices every hour while markets are open. A weekend
  # run keeps the back-fill out of their way.
  dow="$(date +%u)"
  if [[ "$dow" -le 5 ]]; then
    echo "Note: it is a weekday. The back-fill is gentle (a pause between companies, and"
    echo "it stops by itself if Yahoo starts refusing), but a weekend run is kinder to"
    echo "the site's own downloads. Continuing."
  fi
fi

mkdir -p "$LOG_DIR"
rm -f "$STOP_MARK"

if [[ "$job" == "backfill-dry" ]]; then
  # Quick and read-only: run it in the foreground.
  compose run --rm -T ml nice -n 10 "${cmd[@]}" "${args[@]}"
  exit 0
fi

log="$LOG_DIR/${job}-$(date +%Y%m%d-%H%M%S).log"
say "Starting '$job' in the background"
# nohup keeps the job alive when the SSH window closes. The small wrapper
# around it adds one plain line at the end of the log saying how the job
# ended: a job the memory cap kills would otherwise just stop mid-sentence.
nohup bash -c '
  compose_file=$1 env_file=$2 stop_mark=$3
  shift 3
  docker compose -f "$compose_file" --env-file "$env_file" run --rm -T ml nice -n 10 "$@"
  code=$?
  echo
  if [[ -f "$stop_mark" ]]; then
    rm -f "$stop_mark"
    echo "[ml-run] Stopped by hand (bash deploy/ml-run.sh stop)."
  else
    case $code in
      0)   echo "[ml-run] Finished." ;;
      3)   echo "[ml-run] Paused: Yahoo refused 8 downloads in a row. Start the same job again later (a weekend is best); it continues where it stopped." ;;
      137) echo "[ml-run] Stopped: it needed more memory than STOCKPILOT_ML_MEMORY in .env.prod allows. See agent/DEPLOYMENT.md §10." ;;
      *)   echo "[ml-run] Ended with an error (exit code $code). The lines above say why." ;;
    esac
  fi
  exit $code
' ml-run "$COMPOSE_FILE" "$ENV_FILE" "$STOP_MARK" "${cmd[@]}" "${args[@]}" >"$log" 2>&1 &
sleep 2
echo "Started. You can close this window; the job keeps running."
echo
echo "  Follow it:      tail -f $log"
echo "  Is it running:  bash deploy/ml-run.sh status"
echo "  Stop it:        bash deploy/ml-run.sh stop"
