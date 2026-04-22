#!/usr/bin/env bash
# Start Backstage detached in the background.
# Idempotent: no-op if already running.
#
# Reads GITHUB_TOKEN from env or `gh auth token`.
# Resolves Node 22 via nvm. Verifies node_modules present.
# Writes pid and log under lab/backstage/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$LAB_DIR/backstage/ape-lab"
PIDFILE="$LAB_DIR/backstage/backstage.pid"
LOGFILE="$LAB_DIR/backstage/backstage.log"

# ---- fast-path: already running? ------------------------------------------
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo ">>> backstage already running (pid $(cat "$PIDFILE"))"
  echo ">>> http://localhost:3000   log: $LOGFILE"
  exit 0
fi
# Orphan check by listening port (avoids argv self-match from pgrep -f)
for port in 3000 7007; do
  if command -v lsof >/dev/null 2>&1 && [ -n "$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1)" ]; then
    echo "ERROR: port $port already in use. Run: make -C lab backstage-down"
    exit 1
  fi
done

# ---- app present? ---------------------------------------------------------
if [ ! -d "$APP_DIR" ]; then
  echo "ERROR: $APP_DIR not found. Did you run 'make -C lab up' yet?"
  exit 1
fi
if [ ! -d "$APP_DIR/node_modules" ]; then
  echo "ERROR: $APP_DIR/node_modules missing."
  echo "Run: cd $APP_DIR && yarn install"
  exit 1
fi

# ---- Node 22 via nvm ------------------------------------------------------
if [ -s "$HOME/.nvm/nvm.sh" ]; then
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh"
  nvm use 22 >/dev/null 2>&1 || {
    echo "ERROR: Node 22 not installed in nvm. Run: nvm install 22"
    exit 1
  }
fi
NODE_VER="$(node --version 2>/dev/null || echo none)"
case "$NODE_VER" in
  v22.*|v24.*) ;;
  *)
    echo "ERROR: Backstage requires Node 22 or 24 (found: $NODE_VER)."
    echo "Install nvm + Node 22, or ensure node22 is on PATH."
    exit 1
    ;;
esac

# ---- GITHUB_TOKEN ---------------------------------------------------------
if [ -z "${GITHUB_TOKEN:-}" ]; then
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
  fi
fi
if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "ERROR: no GitHub auth available."
  echo "Either:  gh auth login   (recommended)"
  echo "Or:      export GITHUB_TOKEN=ghp_..."
  exit 1
fi
export GITHUB_TOKEN

# ---- app-config.local.yaml ------------------------------------------------
if [ ! -f "$APP_DIR/app-config.local.yaml" ]; then
  echo ">>> app-config.local.yaml missing — copying from template"
  cp "$LAB_DIR/backstage/app-config.example.yaml" "$APP_DIR/app-config.local.yaml"
fi

# ---- launch detached ------------------------------------------------------
cd "$APP_DIR"
: > "$LOGFILE"
nohup yarn start </dev/null >>"$LOGFILE" 2>&1 &
BSPID=$!
disown "$BSPID" 2>/dev/null || true
echo "$BSPID" > "$PIDFILE"

echo ">>> backstage started (pid $BSPID)"
echo ">>> log: tail -f $LOGFILE"
echo ">>> http://localhost:3000 ready in ~60-90s (cold start, Rspack bundle)"
