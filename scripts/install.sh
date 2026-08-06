#!/usr/bin/env bash
# Link this repository's launch commands only. This script never edits shell
# profiles, installs packages, or makes network calls.
set -euo pipefail

prog="install.sh"

usage() {
  cat <<'EOF'
Usage: install.sh [--prefix DIR] [--dry-run] [--uninstall] [--force]

Create or remove the Prime Fable launcher symlinks.

Options:
  --prefix DIR  Install into DIR (default: ${XDG_BIN_HOME:-$HOME/.local/bin})
  --dry-run     Print actions without changing the filesystem
  --uninstall   Remove this repository's installed symlinks
  --force       Replace conflicting files during installation
  -h, --help    Show this help
EOF
}

prefix=""
dry_run=0
uninstall=0
force=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      [ "$#" -ge 2 ] && [ -n "$2" ] || {
        echo "$prog: --prefix requires a directory" >&2
        usage >&2
        exit 2
      }
      prefix="$2"
      shift 2
      ;;
    --dry-run) dry_run=1; shift ;;
    --uninstall) uninstall=1; shift ;;
    --force) force=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "$prog: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$prefix" ]; then
  if [ -n "${XDG_BIN_HOME:-}" ]; then
    prefix="$XDG_BIN_HOME"
  else
    [ -n "${HOME:-}" ] || { echo "$prog: HOME is unset; use --prefix DIR" >&2; exit 2; }
    prefix="$HOME/.local/bin"
  fi
fi
case "$prefix" in
  /*) ;;
  *) prefix="$PWD/$prefix" ;;
esac
[ ! -e "$prefix" ] || [ -d "$prefix" ] || {
  echo "$prog: prefix is not a directory: $prefix" >&2
  exit 1
}

source_path="${BASH_SOURCE[0]}"
while [ -h "$source_path" ]; do
  source_dir="$(cd -P "$(dirname "$source_path")" && pwd)"
  link_target="$(readlink "$source_path")"
  case "$link_target" in
    /*) source_path="$link_target" ;;
    *) source_path="$source_dir/$link_target" ;;
  esac
done
script_dir="$(cd -P "$(dirname "$source_path")" && pwd)"

names=(
  prime-fable-orchestrate
  prime-codex-leg
  prime-grok-leg
  prime-preflight
)
targets=(
  "$script_dir/prime_fable_orchestrate.py"
  "$script_dir/prime_codex_leg.sh"
  "$script_dir/prime_grok_leg.sh"
  "$script_dir/prime_preflight.py"
)

resolved_link_target() {
  existing_link="$1"
  raw_target="$(readlink "$existing_link")"
  case "$raw_target" in
    /*) candidate="$raw_target" ;;
    *) candidate="$(dirname "$existing_link")/$raw_target" ;;
  esac
  candidate_dir="$(dirname "$candidate")"
  if [ -d "$candidate_dir" ]; then
    candidate_dir="$(cd -P "$candidate_dir" && pwd)"
  fi
  printf '%s/%s\n' "$candidate_dir" "$(basename "$candidate")"
}

prefix_on_path=0
path_entries=()
IFS=: read -r -a path_entries <<< "${PATH:-}"
for path_entry in "${path_entries[@]}"; do
  [ -n "$path_entry" ] || path_entry="."
  case "$path_entry" in
    /*) ;;
    *) path_entry="$PWD/$path_entry" ;;
  esac
  if [ "$path_entry" = "$prefix" ]; then
    prefix_on_path=1
    break
  fi
done

if [ "$uninstall" -eq 1 ]; then
  # Validate the complete set before removing any link.
  i=0
  while [ "$i" -lt "${#names[@]}" ]; do
    link="$prefix/${names[$i]}"
    target="${targets[$i]}"
    if [ -L "$link" ]; then
      actual="$(resolved_link_target "$link")"
      [ "$actual" = "$target" ] || {
        echo "$prog: refusing to remove foreign symlink: $link" >&2
        exit 1
      }
    elif [ -e "$link" ]; then
      echo "$prog: refusing to remove real file: $link" >&2
      exit 1
    fi
    i=$((i + 1))
  done

  i=0
  while [ "$i" -lt "${#names[@]}" ]; do
    link="$prefix/${names[$i]}"
    if [ -L "$link" ]; then
      if [ "$dry_run" -eq 1 ]; then
        echo "$prog: would remove $link"
      else
        rm -f "$link"
        echo "$prog: removed $link"
      fi
    fi
    i=$((i + 1))
  done
else
  # Validate the complete set before chmod, mkdir, removal, or linking.
  i=0
  while [ "$i" -lt "${#names[@]}" ]; do
    link="$prefix/${names[$i]}"
    target="${targets[$i]}"
    [ -f "$target" ] || { echo "$prog: linked script is missing: $target" >&2; exit 1; }
    if [ -L "$link" ]; then
      actual="$(resolved_link_target "$link")"
      if [ "$actual" != "$target" ] && [ "$force" -ne 1 ]; then
        echo "$prog: refusing to clobber foreign symlink: $link (use --force)" >&2
        exit 1
      fi
    elif [ -d "$link" ]; then
      echo "$prog: refusing to clobber directory: $link" >&2
      exit 1
    elif [ -e "$link" ] && [ "$force" -ne 1 ]; then
      echo "$prog: refusing to clobber existing file: $link (use --force)" >&2
      exit 1
    fi
    i=$((i + 1))
  done

  i=0
  while [ "$i" -lt "${#targets[@]}" ]; do
    if [ "$dry_run" -eq 1 ]; then
      echo "$prog: would chmod +x ${targets[$i]}"
    else
      chmod +x "${targets[$i]}"
    fi
    i=$((i + 1))
  done

  if [ ! -d "$prefix" ]; then
    if [ "$dry_run" -eq 1 ]; then
      echo "$prog: would create directory $prefix"
    else
      mkdir -p "$prefix"
      echo "$prog: created directory $prefix"
    fi
  fi

  i=0
  while [ "$i" -lt "${#names[@]}" ]; do
    link="$prefix/${names[$i]}"
    target="${targets[$i]}"
    already_correct=0
    if [ -L "$link" ] && [ "$(resolved_link_target "$link")" = "$target" ]; then
      already_correct=1
    fi
    if [ "$already_correct" -eq 0 ]; then
      if [ "$dry_run" -eq 1 ]; then
        if [ -e "$link" ] || [ -L "$link" ]; then
          echo "$prog: would remove $link"
        fi
        echo "$prog: would link $link -> $target"
      else
        if [ -e "$link" ] || [ -L "$link" ]; then
          rm -f "$link"
        fi
        ln -s "$target" "$link"
        echo "$prog: linked $link -> $target"
      fi
    fi
    i=$((i + 1))
  done
fi

if [ "$prefix_on_path" -ne 1 ]; then
  echo "$prog: warning: $prefix is not on PATH" >&2
fi
