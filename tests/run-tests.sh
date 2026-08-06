#!/usr/bin/env bash
set -euo pipefail
skill_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec python3 -m unittest discover -s "$skill_dir/tests" -t "$skill_dir" -v
