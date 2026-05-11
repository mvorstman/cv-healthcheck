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

# Stop any running instance
echo "[start] stopping existing instance..."
pkill -TERM -f "python run.py" 2>/dev/null || true
pkill -TERM -f "flask run" 2>/dev/null || true
sleep 1

# Generate a fresh secret key for this session
export CV_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "[start] secret key generated"

# Log level - default INFO, override via first argument
export CV_LOG_LEVEL="${1:-INFO}"
echo "[start] log level: $CV_LOG_LEVEL"

# Activate virtualenv
source venv/bin/activate
echo "[start] virtualenv activated"

# Ensure required runtime directories exist
mkdir -p logs data/catalog data/labreadiness
echo "[start] runtime directories ready"

# Configure Flask runtime
export FLASK_APP="cvhealthcheck.web.app"
export FLASK_ENV="production"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export CV_WEB_HOST="${CV_WEB_HOST:-0.0.0.0}"
export CV_WEB_PORT="${CV_WEB_PORT:-5000}"

# Start the app
echo "[start] starting cv-healthcheck on ${CV_WEB_HOST}:${CV_WEB_PORT}..."
flask run --host="${CV_WEB_HOST}" --port="${CV_WEB_PORT}"
