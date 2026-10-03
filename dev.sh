#!/usr/bin/env bash
# Start the whole app with one command: Postgres, Ollama, backend and frontend.
# Ctrl+C (or closing the backend/frontend) stops all of it again.
#
#   ./dev.sh            start everything and open the browser
#   ./dev.sh --no-open  same, without opening the browser
#   ./dev.sh stop       stop everything (e.g. after closing the terminal window)
#
# Kept bash 3.2 compatible (the version macOS ships): no `wait -n`, no mapfile.
set -euo pipefail

cd "$(dirname "$0")"

API_PORT=8000
WEB_PORT=5173
OLLAMA_PORT=11434
PG_SERVICE=postgresql@16
APP_URL="http://localhost:$WEB_PORT"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

listening_pids() { lsof -nP -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }

# wait_for <label> <seconds> <command...>: poll until the command succeeds.
wait_for() {
  local label=$1 timeout=$2 i
  shift 2
  for ((i = 0; i < timeout; i++)); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  die "$label did not come up within ${timeout}s"
}

# Prefix every line of a process's output, flushing line by line.
prefix() { awk -v p="$1" '{ print p " " $0; fflush() }'; }

stop_all() {
  set +e
  say "Stopping everything..."
  local port pids
  for port in "$API_PORT" "$WEB_PORT"; do
    pids=$(listening_pids "$port")
    [ -n "$pids" ] && echo "$pids" | xargs kill 2>/dev/null
  done
  # Background pipelines started by this script, if any.
  jobs -p | xargs kill 2>/dev/null
  # The Ollama app restarts its server if only the server is killed.
  pkill -f 'Ollama.app/Contents/MacOS/Ollama'
  pkill -f 'ollama serve'
  pkill -f 'llama-server'
  brew services stop "$PG_SERVICE" >/dev/null 2>&1
  say "Stopped backend, frontend, Ollama and Postgres."
}

if [ "${1:-}" = "stop" ]; then
  stop_all
  exit 0
fi

OPEN_BROWSER=true
[ "${1:-}" = "--no-open" ] && OPEN_BROWSER=false

# --- Preflight ---------------------------------------------------------------
command -v brew >/dev/null || die "Homebrew not found (needed for Postgres)."
command -v ollama >/dev/null || die "ollama not found: install it from https://ollama.com"
command -v npm >/dev/null || die "npm not found: install Node.js."
[ -x backend/.venv/bin/uvicorn ] ||
  die "backend/.venv missing: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"
[ -d frontend/node_modules ] || die "frontend/node_modules missing: cd frontend && npm install"

for port in "$API_PORT" "$WEB_PORT"; do
  if [ -n "$(listening_pids "$port")" ]; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN
    die "port $port is already in use (see above). Run ./dev.sh stop, or kill that process."
  fi
done

trap 'exit 130' INT TERM
trap stop_all EXIT

# --- Postgres ----------------------------------------------------------------
say "Starting Postgres..."
brew services start "$PG_SERVICE" >/dev/null
PG_ISREADY="$(brew --prefix "$PG_SERVICE")/bin/pg_isready"
wait_for "Postgres" 30 "$PG_ISREADY" -q -h localhost

# --- Ollama ------------------------------------------------------------------
if [ -z "$(listening_pids "$OLLAMA_PORT")" ]; then
  say "Starting Ollama (log: logs/ollama.log)..."
  mkdir -p logs
  nohup ollama serve >logs/ollama.log 2>&1 &
fi
wait_for "Ollama" 30 curl -sf "http://localhost:$OLLAMA_PORT/api/tags"

MODEL=$(sed -n 's/^OLLAMA_MODEL=//p' backend/.env 2>/dev/null | tail -1)
MODEL=${MODEL:-qwen2.5:7b}
if ! ollama list 2>/dev/null | awk '{ print $1 }' | grep -qxF "$MODEL"; then
  say "Warning: model $MODEL is not pulled yet. Run: ollama pull $MODEL"
fi

# --- Backend -----------------------------------------------------------------
say "Applying database migrations..."
(cd backend && .venv/bin/alembic upgrade head)

say "Starting backend on port $API_PORT..."
(cd backend && exec .venv/bin/uvicorn app.main:app --reload --port "$API_PORT" 2>&1) | prefix "[api]" &
API_PID=$!
wait_for "Backend" 60 curl -sf "http://localhost:$API_PORT/health"

# --- Frontend ----------------------------------------------------------------
say "Starting frontend on port $WEB_PORT..."
(cd frontend && exec npm run dev -- --port "$WEB_PORT" --strictPort 2>&1) | prefix "[web]" &
WEB_PID=$!
wait_for "Frontend" 30 curl -sf "$APP_URL"

say "HugoLingo is running at $APP_URL (Ctrl+C to stop everything)"
if $OPEN_BROWSER && command -v open >/dev/null; then open "$APP_URL"; fi

# Stay in the foreground until Ctrl+C or until the backend or frontend exits.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 2
done
say "The backend or frontend exited."
