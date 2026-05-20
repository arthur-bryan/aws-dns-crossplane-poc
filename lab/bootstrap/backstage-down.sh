#!/usr/bin/env bash
# Stop the detached Backstage process.
# Idempotent: no-op if nothing running.
#
# Strategy: kill by PID file first, then by LISTEN port (3000 / 7007). This
# avoids `pgrep -f <pattern>` which matches any shell whose argv contains the
# pattern string (e.g. the test runner that invoked this script).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDFILE="$LAB_DIR/backstage/backstage.pid"
GP_PIDFILE="$LAB_DIR/backstage/git-pull.pid"

stopped_any=0

kill_tree() {
  local pid="$1"
  [ -z "$pid" ] && return 0
  # kill the process group (parent and all children). Negative PID = process group.
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    stopped_any=1
  fi
}

# 1. PID file
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  kill_tree "$PID"
  rm -f "$PIDFILE"
fi

# 1b. git-pull poller PID file
if [ -f "$GP_PIDFILE" ]; then
  GPPID="$(cat "$GP_PIDFILE" 2>/dev/null || true)"
  kill_tree "$GPPID"
  rm -f "$GP_PIDFILE"
fi

# 2. Port-based sweep (covers orphans + children). Needs lsof (always installed
#    with the lab scripts' other deps) or falls back to /proc parsing.
pids_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
  else
    # fallback: /proc scan
    for f in /proc/[0-9]*/net/tcp; do
      awk -v port=$(printf '%04X' "$port") '$2 ~ ":" port "$" && $4 == "0A" {print $10}' "$f" 2>/dev/null || true
    done | sort -u
  fi
}

for port in 3000 7007; do
  while read -r pid; do
    [ -n "$pid" ] || continue
    kill_tree "$pid"
  done < <(pids_on_port "$port")
done

# 3. Wait up to 10s for ports to close
for _ in 1 2 3 4 5; do
  still=""
  for port in 3000 7007; do
    p=$(pids_on_port "$port" | head -1 || true)
    [ -n "$p" ] && still="1"
  done
  [ -z "$still" ] && break
  sleep 2
done

# 4. Second sweep with SIGKILL if anything is still listening
for port in 3000 7007; do
  while read -r pid; do
    [ -n "$pid" ] || continue
    kill -KILL "$pid" 2>/dev/null || true
  done < <(pids_on_port "$port")
done

if [ "$stopped_any" = "1" ]; then
  echo ">>> backstage stopped"
else
  echo ">>> backstage was not running"
fi
