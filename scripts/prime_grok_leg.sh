#!/usr/bin/env bash
# Prime orchestration entrypoint: preserve grok-leg profiles, sandbox, denylist,
# streaming evidence, and watchdog while enabling non-interactive tool calls.
set -euo pipefail

# Always-approved automation is safe only behind an explicit workspace sandbox
# and a bounded profile. Reject the adapter's documented escape hatches here.
args=("$@")
forwarded=()
lane=""
lane_count=0
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[$i]}" in
    --lane=*) echo "prime-grok-leg: use '--lane VALUE', not --lane=VALUE" >&2; exit 2;;
    --lane)
      ((lane_count+=1))
      [ "$lane_count" -eq 1 ] || { echo "prime-grok-leg: --lane may be given only once" >&2; exit 2; }
      lane="${args[$((i+1))]:-}"
      [ -n "$lane" ] || { echo "prime-grok-leg: --lane requires reader or writer" >&2; exit 2; }
      ((i+=1));;
    *) forwarded+=("${args[$i]}");;
  esac
done
[ "$lane_count" -eq 1 ] || { echo "prime-grok-leg: --lane reader|writer is required" >&2; exit 2; }
case "$lane" in
  reader|writer) ;;
  *) echo "prime-grok-leg: invalid --lane '$lane'; expected reader or writer" >&2; exit 2;;
esac
[ -n "${PRIME_ORCHESTRATION_JOB_DIR:-}" ] && [ -d "$PRIME_ORCHESTRATION_JOB_DIR" ] || {
  echo "prime-grok-leg: PRIME_ORCHESTRATION_JOB_DIR must be an existing directory" >&2; exit 2;
}

has_cwd=0
cwd_value=""
profile_value=""
for ((i=0; i<${#forwarded[@]}; i++)); do
  case "${forwarded[$i]}" in
    --cwd) has_cwd=1; cwd_value="${forwarded[$((i+1))]:-}"; ((i+=1));;
    --cwd=*) echo "prime-grok-leg: use '--cwd DIR', not --cwd=DIR" >&2; exit 2;;
    --sandbox)
      next="${forwarded[$((i+1))]:-}"
      [ "$next" != "off" ] || { echo "prime-grok-leg: --sandbox off is forbidden" >&2; exit 2; }
      ((i+=1));;
    --sandbox=off) echo "prime-grok-leg: --sandbox off is forbidden" >&2; exit 2;;
    --sandbox=*) echo "prime-grok-leg: use '--sandbox PROFILE', not --sandbox=PROFILE" >&2; exit 2;;
    --profile)
      next="${forwarded[$((i+1))]:-}"
      [ "$next" != "full" ] || { echo "prime-grok-leg: --profile full is forbidden; use scout/probe/write" >&2; exit 2; }
      profile_value="$next"
      ((i+=1));;
    --profile=full) echo "prime-grok-leg: --profile full is forbidden; use scout/probe/write" >&2; exit 2;;
    --profile=*) echo "prime-grok-leg: use '--profile NAME', not --profile=NAME" >&2; exit 2;;
  esac
done
[ "$has_cwd" = 1 ] || { echo "prime-grok-leg: explicit --cwd is required to bound the workspace sandbox" >&2; exit 2; }
[ -d "$cwd_value" ] || { echo "prime-grok-leg: --cwd must be an existing directory" >&2; exit 2; }
resolved_cwd="$(cd "$cwd_value" && pwd -P)"
resolved_home=""
if [ -n "${HOME:-}" ]; then
  [ -d "$HOME" ] || {
    echo "prime-grok-leg: HOME must name an existing directory when set" >&2; exit 2;
  }
  resolved_home="$(cd "$HOME" && pwd -P)"
fi
[ "$resolved_cwd" != "/" ] && { [ -z "$resolved_home" ] || [ "$resolved_cwd" != "$resolved_home" ]; } || {
  echo "prime-grok-leg: --cwd must be narrower than the filesystem root or home directory" >&2; exit 2;
}
[ "$profile_value" != "write" ] || [ "$lane" = "writer" ] || {
  echo "prime-grok-leg: profile 'write' requires --lane writer, not --lane $lane" >&2; exit 2;
}

# The adapter contract accepts environment defaults; clear them so inline
# assignments cannot bypass this wrapper's argument checks.
unset GROK_LEG_SANDBOX GROK_LEG_PROFILE GROK_LEG_STALL_S
source_path="${BASH_SOURCE[0]}"
while [ -h "$source_path" ]; do
  source_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
  link_target="$(readlink "$source_path")"
  if [[ "$link_target" = /* ]]; then source_path="$link_target"; else source_path="$source_dir/$link_target"; fi
done
script_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
source "$script_dir/prime_resolve_bin.sh"
grok_leg_bin="$(prime_resolve_bin grok-leg PRIME_GROK_LEG_BIN prime-grok-leg grok-leg)" || exit $?
printf 'prime-grok-leg: resolved grok-leg: %s\n' "$grok_leg_bin" >&2
export GROK_LEG_BIN="$script_dir/grok_always_approve_shim.sh"
slot_controller="$script_dir/prime_slot_controller.py"
# Test-only hook: production ignores PRIME_SLOT_CONTROLLER unless explicitly in test mode.
if [ "${PRIME_ORCHESTRATION_TEST:-}" = 1 ] && [[ "${PRIME_SLOT_CONTROLLER:-}" = /* ]]; then
  slot_controller="$PRIME_SLOT_CONTROLLER"
fi
exec python3 "$slot_controller" run --vendor grok --lane "$lane" --label prime-grok-leg -- \
  "$grok_leg_bin" "${forwarded[@]}"
