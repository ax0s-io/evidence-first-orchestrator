#!/usr/bin/env bash
# Prime slot-controlled layer over the documented codex-leg adapter contract.
set -euo pipefail

args=("$@")
forwarded=()
lane=""
lane_count=0
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[$i]}" in
    --lane=*)
      echo "prime-codex-leg: use '--lane VALUE', not --lane=VALUE" >&2
      exit 2
      ;;
    --lane)
      ((lane_count+=1))
      [ "$lane_count" -eq 1 ] || { echo "prime-codex-leg: --lane may be given only once" >&2; exit 2; }
      lane="${args[$((i+1))]:-}"
      [ -n "$lane" ] || { echo "prime-codex-leg: --lane requires reader or writer" >&2; exit 2; }
      ((i+=1))
      ;;
    *) forwarded+=("${args[$i]}") ;;
  esac
done
[ "$lane_count" -eq 1 ] || { echo "prime-codex-leg: --lane reader|writer is required" >&2; exit 2; }
case "$lane" in
  reader|writer) ;;
  *) echo "prime-codex-leg: invalid --lane '$lane'; expected reader or writer" >&2; exit 2 ;;
esac
[ -n "${PRIME_ORCHESTRATION_JOB_DIR:-}" ] && [ -d "$PRIME_ORCHESTRATION_JOB_DIR" ] || {
  echo "prime-codex-leg: PRIME_ORCHESTRATION_JOB_DIR must be an existing directory" >&2
  exit 2
}

sandbox=""
for ((i=0; i<${#forwarded[@]}; i++)); do
  case "${forwarded[$i]}" in
    -s|--sandbox) sandbox="${forwarded[$((i+1))]:-}"; ((i+=1)) ;;
    --sandbox=*) sandbox="${forwarded[$i]#--sandbox=}" ;;
    -s?*) sandbox="${forwarded[$i]#-s}" ;;
  esac
done
if [ -n "$sandbox" ] && [ "$sandbox" != "read-only" ] && [ "$lane" != "writer" ]; then
  echo "prime-codex-leg: sandbox '$sandbox' requires --lane writer, not --lane $lane" >&2
  exit 2
fi

source_path="${BASH_SOURCE[0]}"
while [ -h "$source_path" ]; do
  source_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
  link_target="$(readlink "$source_path")"
  if [[ "$link_target" = /* ]]; then source_path="$link_target"; else source_path="$source_dir/$link_target"; fi
done
script_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
source "$script_dir/prime_resolve_bin.sh"
codex_leg_bin="$(prime_resolve_bin codex-leg PRIME_CODEX_LEG_BIN prime-codex-leg codex-leg)" || exit $?
printf 'prime-codex-leg: resolved codex-leg: %s\n' "$codex_leg_bin" >&2
slot_controller="$script_dir/prime_slot_controller.py"
# Test-only hook: production ignores PRIME_SLOT_CONTROLLER unless explicitly in test mode.
if [ "${PRIME_ORCHESTRATION_TEST:-}" = 1 ] && [[ "${PRIME_SLOT_CONTROLLER:-}" = /* ]]; then
  slot_controller="$PRIME_SLOT_CONTROLLER"
fi
exec python3 "$slot_controller" run --vendor codex --lane "$lane" --label prime-codex-leg -- \
  "$codex_leg_bin" "${forwarded[@]}"
