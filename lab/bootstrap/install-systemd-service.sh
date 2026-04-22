#!/usr/bin/env bash
# Install the ape-backstage systemd user service so Backstage auto-starts
# after WSL restart / PC boot.
#
# Idempotent: running twice is safe. Uses sudo for `loginctl enable-linger`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAB_DIR/.." && pwd)"

SERVICE_NAME="ape-backstage.service"
TEMPLATE="$LAB_DIR/systemd/$SERVICE_NAME"
TARGET_DIR="$HOME/.config/systemd/user"
TARGET="$TARGET_DIR/$SERVICE_NAME"

mkdir -p "$TARGET_DIR"

# Substitute __REPO__ placeholder with the actual repo path.
sed "s|__REPO__|${REPO_ROOT}|g" "$TEMPLATE" > "$TARGET"
echo ">>> wrote $TARGET"

# Enable lingering so the service auto-starts when systemd-user starts,
# without needing an interactive WSL login session.
if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]; then
  echo ">>> enabling linger for $USER (requires sudo)"
  sudo loginctl enable-linger "$USER"
fi

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl --user restart "$SERVICE_NAME"

echo ">>> $SERVICE_NAME enabled + started"
echo ">>> logs: tail -f $LAB_DIR/backstage/backstage.log"
echo ">>> status: systemctl --user status $SERVICE_NAME"
