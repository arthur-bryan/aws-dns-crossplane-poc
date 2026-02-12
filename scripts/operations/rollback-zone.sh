#!/bin/bash
# Rollback zone changes to previous Git commit

set -e

ZONE_FILE="$1"
COMMITS="${2:-1}"

if [ -z "$ZONE_FILE" ]; then
  echo "Usage: $0 <zone-yaml-file> [commits-back]"
  echo ""
  echo "Arguments:"
  echo "  zone-yaml-file  Path to zone YAML (e.g., gitops/dev/infradev.hml.dock.tech.yaml)"
  echo "  commits-back    Number of commits to rollback [default: 1]"
  echo ""
  echo "Examples:"
  echo "  $0 gitops/dev/infradev.hml.dock.tech.yaml"
  echo "  $0 gitops/dev/infradev.hml.dock.tech.yaml 2"
  echo ""
  echo "Recent changes:"
  git log --oneline --follow -10 gitops/
  exit 1
fi

if [ ! -f "$ZONE_FILE" ]; then
  echo "Error: File not found: $ZONE_FILE"
  exit 1
fi

BACKUP_FILE="${ZONE_FILE}.backup-$(date +%Y%m%d-%H%M%S)"

echo "Rollback: $ZONE_FILE"
echo "Commits back: $COMMITS"
echo ""

echo "Current version:"
git log --oneline --follow -1 "$ZONE_FILE"
echo ""

echo "Target version:"
git log --oneline --follow --skip="$COMMITS" -1 "$ZONE_FILE"
echo ""

cp "$ZONE_FILE" "$BACKUP_FILE"
echo "Backed up current version to: $BACKUP_FILE"
echo ""

git show "HEAD~${COMMITS}:${ZONE_FILE}" > "$ZONE_FILE"

echo "Changes:"
git diff "$BACKUP_FILE" "$ZONE_FILE" || true
echo ""

echo "Next steps:"
echo "  1. Review changes above"
echo "  2. If correct, commit:"
echo "     git add $ZONE_FILE"
echo "     git commit -m \"Rollback $ZONE_FILE to $COMMITS commits ago\""
echo "     git push origin main"
echo "     ./scripts/operations/sync-gitops.sh"
echo ""
echo "  3. If incorrect, restore backup:"
echo "     mv $BACKUP_FILE $ZONE_FILE"
echo ""
echo "Backup: $BACKUP_FILE"
