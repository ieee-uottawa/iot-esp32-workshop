#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f ".demo/pids.env" ]]; then
  echo "[INFO] No active demo found (.demo/pids.env missing)."
  exit 0
fi

# shellcheck source=/dev/null
source .demo/pids.env

PIDS=("${SIM_PID:-}" "${BACKEND_PID:-}" "${DASH_PID:-}")

for pid in "${PIDS[@]}"; do
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
done

# Give processes a moment to exit gracefully.
sleep 0.5

for pid in "${PIDS[@]}"; do
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
done

rm -f .demo/pids.env

echo "[OK] Demo stopped. Logs kept in .demo/logs/."
