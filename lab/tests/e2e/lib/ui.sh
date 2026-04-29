red()    { printf '\033[0;31m%s\033[0m' "$1"; }
green()  { printf '\033[0;32m%s\033[0m' "$1"; }
yellow() { printf '\033[0;33m%s\033[0m' "$1"; }
bold()   { printf '\033[1m%s\033[0m'   "$1"; }

step()   { printf '\n=== %s ===\n' "$(bold "$1")"; }
info()   { printf '  %s %s\n' "$(yellow '[info]')" "$1"; }
ok()     { printf '  %s %s\n' "$(green '[ok]')"  "$1"; }
fail()   { printf '  %s %s\n' "$(red '[fail]')" "$1"; }

pause_for_merge() {
  local pr_url="$1"
  printf '\n'
  printf '  %s\n' "$(bold 'ACTION REQUIRED — merge this PR, then return to this terminal:')"
  printf '    %s\n' "$pr_url"
  printf '\n'
  printf '  %s ' "$(bold 'press ENTER once the PR is merged ')"
  read -r _
}

require_cmds() {
  local missing=()
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    fail "missing required tools: ${missing[*]}"
    exit 1
  fi
}
