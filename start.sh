#!/bin/bash
# start.sh - cv-healthcheck startup script
# Usage: ./start.sh [loglevel]
# Example: ./start.sh DEBUG

cd "$(dirname "$0")" || exit 1

# Load local lab settings when present
if [ -f "$HOME/.cv-healthcheck-env" ]; then
  source "$HOME/.cv-healthcheck-env"
  echo "[start] environment loaded: $HOME/.cv-healthcheck-env"
fi

# Configure Flask runtime
export FLASK_APP="cvhealthcheck.web.app"
# Dev auto-reload is enabled below via `flask run --debug` (Python reloader +
# Jinja template auto-reload). FLASK_ENV is removed — it's ignored in Flask 3.x.
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export CV_WEB_HOST="${CV_WEB_HOST:-0.0.0.0}"
export CV_WEB_PORT="${CV_WEB_PORT:-5001}"

find_port_pid() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:${CV_WEB_PORT}" 2>/dev/null
    return
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser "${CV_WEB_PORT}/tcp" 2>/dev/null | tr ' ' '\n' | sed '/^$/d'
  fi
}

# Stop any running instance bound to the target port
PORT_PIDS="$(find_port_pid)"
if [ -n "$PORT_PIDS" ]; then
  echo "Stopping existing Flask process on port 5001..."
  echo "$PORT_PIDS" | xargs kill 2>/dev/null || true
  sleep 1

  REMAINING_PIDS="$(find_port_pid)"
  if [ -n "$REMAINING_PIDS" ]; then
    echo "$REMAINING_PIDS" | xargs kill -KILL 2>/dev/null || true
    sleep 1
  fi
fi

# Session secret: PERSISTED across restarts (D5 session-amplifier fix — the
# old per-start key invalidated every session cookie on restart, silently
# reverting the active customer/project context to the Default fallback).
# An env-provided CV_SECRET_KEY (e.g. from ~/.cv-healthcheck-env) wins;
# otherwise the key is generated once into data/.secret_key (mode 600,
# gitignored) and reused.
if [ -z "${CV_SECRET_KEY:-}" ]; then
  SECRET_FILE="data/.secret_key"
  mkdir -p data
  if [ ! -s "$SECRET_FILE" ]; then
    old_umask=$(umask)
    umask 177
    python3 -c "import secrets; print(secrets.token_hex(32))" > "$SECRET_FILE"
    umask "$old_umask"
    echo "[start] secret key generated and persisted to $SECRET_FILE"
  else
    echo "[start] secret key loaded from $SECRET_FILE"
  fi
  chmod 600 "$SECRET_FILE" 2>/dev/null || true
  CV_SECRET_KEY="$(cat "$SECRET_FILE")"
  export CV_SECRET_KEY
else
  echo "[start] secret key from environment"
fi

# Log level - default INFO, override via first argument
export CV_LOG_LEVEL="${1:-INFO}"
echo "[start] log level: $CV_LOG_LEVEL"

# Activate virtualenv
source venv/bin/activate
echo "[start] virtualenv activated"

# Ensure required runtime directories exist
mkdir -p logs data/catalog data/labreadiness
echo "[start] runtime directories ready"

# Start the app
echo "Starting cv-healthcheck..."
echo "[start] starting cv-healthcheck on ${CV_WEB_HOST}:${CV_WEB_PORT}..."
flask run --debug --no-debugger --host="${CV_WEB_HOST}" --port="${CV_WEB_PORT}"
