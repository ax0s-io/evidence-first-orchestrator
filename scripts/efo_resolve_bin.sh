#!/usr/bin/env bash
# Shared trusted executable discovery for the shell adapters.
#
# The launcher owns the resolution rule; this delegates to it rather than
# reimplementing it, so an adapter can never resolve a different binary than
# the one the launcher and preflight checked.

efo_resolve_bin_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

efo_resolve_bin() {
  local name="$1"
  local env_var="$2"
  local program="$3"
  local display="$4"
  local override="${!env_var-}"
  local override_set=0
  local resolved

  if [ -n "$override" ]; then
    override_set=1
  fi

  if resolved="$(python3 - "$name" "$override_set" "$override" "$efo_resolve_bin_dir" 2>/dev/null <<'PY'
import sys

name, override_set, override, script_dir = sys.argv[1:]
sys.path.insert(0, script_dir)
from efo_orchestrate import find_executable, usable_executable

selected = usable_executable(override) if override_set == "1" else find_executable(name)
if selected is None:
    raise SystemExit(1)
print(selected)
PY
  )"; then
    printf '%s\n' "$resolved"
    return 0
  fi

  if [ "$override_set" -eq 1 ]; then
    printf '%s: %s does not name a usable executable: %s\n' \
      "$program" "$env_var" "$override" >&2
  else
    printf "%s: %s not found; set %s to an executable file or install '%s' on PATH\n" \
      "$program" "$display" "$env_var" "$name" >&2
  fi
  return 1
}
