#!/usr/bin/env bash
set -euo pipefail


BROKER="${BROKER:-127.0.0.1}"
PORT="${PORT:-1883}"
COUNT="${COUNT:-3}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-5000}"
PYTHON_BIN="${PYTHON_BIN:-}"
WITH_BACKEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --broker)
      BROKER="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --count)
      COUNT="$2"
      shift 2
      ;;
    --web-host)
      WEB_HOST="$2"
      shift 2
      ;;
    --web-port)
      WEB_PORT="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --with-backend)
      WITH_BACKEND=1
      shift
      ;;
    -h|--help)
      cat <<'HELP'
Usage: ./run_demo.sh [options]

Options:
  --broker <host>      MQTT broker host (default: 127.0.0.1)
  --port <port>        MQTT broker port (default: 1883)
  --count <n>          Number of simulated devices (default: 3, use 0 to disable simulator)
  --web-host <host>    Dashboard host (default: 127.0.0.1)
  --web-port <port>    Dashboard port (default: 5000)
  --python <path>      Python executable to use
  --with-backend       Also start backend.py in background (default: off)

Environment variable alternatives:
  BROKER, PORT, COUNT, WEB_HOST, WEB_PORT, PYTHON_BIN

By default, only the simulator and dashboard are started. Use --with-backend if you want backend.py running in background for extra logging or CLI testing.
HELP
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1"
      exit 1
      ;;
  esac
done

if [[ -f ".demo/pids.env" ]]; then
  echo "[ERROR] Existing demo appears to be running (.demo/pids.env found)."
  echo "        Run ./stop_demo.sh first, then retry."
  exit 1
fi

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "venv/bin/python" ]]; then
    PYTHON_BIN="venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[ERROR] Python executable not found: $PYTHON_BIN"
  exit 1
fi

if ! [[ "$COUNT" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] --count must be a non-negative integer (0, 1, 2, ...)."
  exit 1
fi

mkdir -p .demo/logs

echo "[INFO] Starting demo using: $PYTHON_BIN"
echo "[INFO] MQTT broker: $BROKER:$PORT"
echo "[INFO] Simulator device count: $COUNT"


SIM_PID=""
BACKEND_PID=""
if (( COUNT > 0 )); then
  "$PYTHON_BIN" simulator.py \
    --broker "$BROKER" \
    --port "$PORT" \
    --count "$COUNT" \
    > .demo/logs/simulator.log 2>&1 &
  SIM_PID=$!
else
  echo "[INFO] Simulator disabled (--count 0). Waiting for real ESP32 publishers."
fi

if (( WITH_BACKEND )); then
  "$PYTHON_BIN" backend.py \
    --broker "$BROKER" \
    --port "$PORT" \
    --no-cli \
    > .demo/logs/backend.log 2>&1 &
  BACKEND_PID=$!
fi

"$PYTHON_BIN" dashboard.py \
  --broker "$BROKER" \
  --port "$PORT" \
  --host "$WEB_HOST" \
  --web-port "$WEB_PORT" \
  > .demo/logs/dashboard.log 2>&1 &
DASH_PID=$!


cat > .demo/pids.env <<EOF
SIM_PID=$SIM_PID
BACKEND_PID=$BACKEND_PID
DASH_PID=$DASH_PID
BROKER=$BROKER
PORT=$PORT
WEB_HOST=$WEB_HOST
WEB_PORT=$WEB_PORT
EOF

sleep 1


PIDS_TO_CHECK=("$DASH_PID")
if (( WITH_BACKEND )) && [[ -n "$BACKEND_PID" ]]; then
  PIDS_TO_CHECK=("$BACKEND_PID" "${PIDS_TO_CHECK[@]}")
fi
if [[ -n "$SIM_PID" ]]; then
  PIDS_TO_CHECK+=("$SIM_PID")
fi

for pid in "${PIDS_TO_CHECK[@]}"; do
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "[ERROR] One or more processes failed to start."
    echo "[INFO] Logs:"
    if [[ -n "$SIM_PID" ]]; then
      echo "  .demo/logs/simulator.log"
    fi
    if (( WITH_BACKEND )); then
      echo "  .demo/logs/backend.log"
    fi
    echo "  .demo/logs/dashboard.log"
    ./stop_demo.sh >/dev/null 2>&1 || true
    exit 1
  fi
done

echo "[OK] Demo started."
echo "[INFO] Dashboard URL: http://$WEB_HOST:$WEB_PORT"
echo "[INFO] Logs:"
if [[ -n "$SIM_PID" ]]; then
  echo "  tail -f .demo/logs/simulator.log"
fi
if (( WITH_BACKEND )); then
  echo "  tail -f .demo/logs/backend.log"
fi
echo "  tail -f .demo/logs/dashboard.log"
echo "[INFO] Stop all services: ./stop_demo.sh"
