#!/usr/bin/env bash
# This widens approval only. Sandbox, profile, and cwd restrictions come from
# the outer wrapper.
set -euo pipefail

source_path="${BASH_SOURCE[0]}"
while [ -h "$source_path" ]; do
  source_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
  link_target="$(readlink "$source_path")"
  if [[ "$link_target" = /* ]]; then source_path="$link_target"; else source_path="$source_dir/$link_target"; fi
done
script_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
source "$script_dir/prime_resolve_bin.sh"
grok_bin="$(prime_resolve_bin grok PRIME_GROK_BIN grok-approve-shim grok)" || exit $?
printf 'grok-approve-shim: resolved grok: %s\n' "$grok_bin" >&2
exec "$grok_bin" \
  --always-approve \
  --deny 'Bash(rm -rf *)' \
  --deny 'Bash(sudo *)' \
  --deny 'Bash(git push --force *)' \
  "$@"
