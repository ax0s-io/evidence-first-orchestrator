# Provenance audit

> Historical, self-reported textual-overlap check from August 2026. It was not
> repeated for the November documentation review: the private reference files
> are not supplied here. Exact-line and shingle matching cannot establish
> originality or licensing, or detect arbitrary renamed or rewritten logic.

**Audit date: 2026-08-07.** Performed against the working tree immediately
before the 0.1.0 release commit.

## What this audit is for

This repository was extracted from a private codebase. That codebase contains
hardened `codex-leg` and `grok-leg` wrapper implementations and routing doctrine
which are **not licensed for redistribution and are not included here**. See
[../ATTRIBUTION.md](../ATTRIBUTION.md).

The risk this audit addresses is specific: that extraction quietly carried
private implementation code into a repository about to be published under MIT.
A written assurance is not evidence, so this is a mechanical check whose method
and results are recorded here for anyone to re-run.

## What is in this repository, and what it is not

This project calls `codex-leg` and `grok-leg`; it does not contain them.

- `scripts/efo_codex_leg.sh` and `scripts/efo_grok_leg.sh` are **thin
  slot-controlled layers** that acquire a concurrency slot, enforce the declared
  lane, and then `exec` the operator's own adapter. They are original code
  written for this project. They implement the *caller* side of the interface
  documented in [adapters.md](adapters.md).
- The adapters themselves — the watchdog, sandbox, profile, and tool-denial
  behaviour described in `adapters.md` — are an **interface specification**. The
  operator supplies the implementation. If it is absent, the corresponding
  capability fails closed with a diagnostic.
- No file in this repository is a copy, translation, or derivative of a private
  wrapper implementation.

## Method

A deterministic line- and shingle-similarity comparison between every text file
in this repository and the private reference wrappers as installed locally at
`$HOME/.local/bin/codex-leg` and `$HOME/.local/bin/grok-leg`.

The reference files were opened **read-only**. Nothing was copied from them into
this repository, and neither their contents nor any excerpt of them appears in
this document — only statistics and this repository's own line numbers.

Normalization before comparison: strip leading and trailing whitespace, collapse
internal whitespace runs to a single space, drop blank lines and whole-line
comments. This is deliberately aggressive — it removes the formatting
differences that a copy-and-rename would introduce, so it *over*-reports
similarity rather than under-reporting it.

Three measures per (repository file, reference file) pair:

1. **Shared normalized lines** — how many of this file's normalized lines appear
   anywhere in the reference.
2. **Jaccard similarity over 5-line shingles** — the structural measure. Copied
   sequences can produce overlap; isolated identical lines do not. Renaming
   identifiers or rewriting logic can defeat this exact-text measure.
3. **Longest run of consecutive matching normalized lines** — the upper bound on
   a lifted block. Note the exact semantics: it is the longest run of
   consecutive lines *in this repository* each of which appears *somewhere* in
   the reference, not a block that is contiguous in both files. That is
   deliberately the looser test. It over-reports — unrelated adjacent lines that
   each happen to occur in the reference still count — but it cannot
   under-report, so a lifted block of length N always produces a run of at least
   N. A small number here therefore rules a lifted block out; a large one only
   means "look manually".

Flagging threshold: any pair with shingle Jaccard above 0.02, or a matching run
of 6 or more consecutive normalized lines, is reported for manual review.

The audit script is not committed. It is only useful against files that are not
public, so shipping it would add surface without adding value. It is reproduced
below in full so the audit can be re-run exactly.

### Reproducing this audit

Save the script below as `provenance_overlap.py` **outside this repository** and
run:

```bash
python3 provenance_overlap.py . "$HOME/.local/bin/codex-leg" "$HOME/.local/bin/grok-leg"
```

<details>
<summary>provenance_overlap.py</summary>

```python
#!/usr/bin/env python3
"""Deterministic overlap audit between this repository and private reference files.

Reports, for every (repo file, reference file) pair: identical-normalized-line
count, Jaccard similarity over 5-line shingles, and the longest run of
consecutive matching normalized lines. Prints only statistics and the repo-side
line numbers of any long run -- never the content of the private reference.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

WS = re.compile(r"\s+")
SHINGLE = 5
RUN_REPORT_THRESHOLD = 6


def normalize(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = WS.sub(" ", raw.strip())
        if not line or line.startswith("#"):
            continue
        out.append((number, line))
    return out


def shingles(lines: list[str], size: int = SHINGLE) -> set[str]:
    return {
        hashlib.sha256("\n".join(lines[i : i + size]).encode()).hexdigest()
        for i in range(max(0, len(lines) - size + 1))
    }


def longest_run(a: list[tuple[int, str]], b_set: set[str]) -> tuple[int, int]:
    """Longest run of consecutive normalized repo lines that all appear in b."""
    best = best_start = run = run_start = 0
    for number, line in a:
        if line in b_set:
            if run == 0:
                run_start = number
            run += 1
            if run > best:
                best, best_start = run, run_start
        else:
            run = 0
    return best, best_start


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    repo = Path(sys.argv[1]).resolve()
    references = [Path(p).expanduser().resolve() for p in sys.argv[2:]]

    repo_files = sorted(
        p
        for p in repo.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and "__pycache__" not in p.parts
        and p.suffix in {".sh", ".py", ".md", ".json", ".yml", ".yaml"}
    )

    for ref in references:
        norm = normalize(ref)
        print(f"- {ref.name}: sha256={digest(ref)} normalized={len(norm)}")

    for ref in references:
        ref_norm = normalize(ref)
        ref_lines = [line for _, line in ref_norm]
        ref_set = set(ref_lines)
        ref_sh = shingles(ref_lines)
        for path in repo_files:
            norm = normalize(path)
            lines = [line for _, line in norm]
            if not lines:
                continue
            shared = sum(1 for line in lines if line in ref_set)
            sh = shingles(lines)
            union = len(sh | ref_sh)
            jaccard = (len(sh & ref_sh) / union) if union else 0.0
            run, at = longest_run(norm, ref_set)
            print(
                f"{str(path.relative_to(repo)):44} {ref.name:12} "
                f"{shared:>4}/{len(lines):<4} {jaccard:>8.4f} {run:>5} {at:>6}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

## Reference files compared against

Identified by hash so a future re-run can tell whether the reference itself
changed. These files are private and are not distributed with this project.

| Reference | SHA-256 | Lines | Normalized lines |
| --- | --- | --- | --- |
| `codex-leg` | `9f9f954220f31b906943f6c1001293107033c19e968d4b4b8d2795314de6701d` | 489 | 334 |
| `grok-leg` | `2462e0571011fc4bdfb0cf5798402b7b1205557ce0ffa394938ffddc9efbd0b7` | 502 | 284 |

`ATTRIBUTION.md` cites no source other than this wrapper lineage, so no
additional reference was in scope.

## Results

**No pair was flagged.** Across every repository file against both references:

- **Shingle Jaccard: 0.0000 for every pair.** Not one 5-line normalized sequence
  in this repository appears in either private wrapper. This is the measure that
  would detect copied logic, and it is empty.
- **Longest matching run: 4 normalized lines** by the upper-bound measure above,
  in two places, both inspected manually and both generic. Because the measure
  cannot under-report, no lifted block longer than 4 normalized lines exists
  anywhere in this repository:
  - `references/result-schema.json` around line 155 — JSON structural closers
    (`"type": "array"`, `"items": {`, `"type": "string"`, closing braces).
  - `scripts/install.sh` around line 45 — the standard `case`-based option
    parser tail: `echo "$prog: unknown option: $1" >&2`, `usage >&2`, `exit 2`,
    `;;`.

  Both are shell and JSON boilerplate that any independent implementation
  produces. Neither carries logic, structure, or a design decision.
- Isolated shared lines (for example 55 of `install.sh`'s 201 normalized lines)
  are single-line matches such as `fi`, `done`, `esac`, `exit 1`, `shift`, and
  `set -eu` that appear in essentially every POSIX shell script. With a longest
  consecutive run of 4 and zero shingle overlap, they carry no provenance
  signal.

The two shell adapters most at risk of resembling their upstream counterparts —
`scripts/efo_codex_leg.sh` (76 normalized lines) and `scripts/efo_grok_leg.sh`
(99) — show 19 and 18 isolated shared lines respectively, longest run 2, Jaccard
0.0000, against references of 334 and 284 normalized lines.

## Conclusion

The bundled code is **original, and interface-only with respect to the private
wrappers**. No material verbatim overlap beyond generic shell and JSON
boilerplate was found. The extraction did not carry private implementation code
into this repository.

This audit measures textual overlap against the two named reference files. It is
not a general originality proof, and it says nothing about files it did not
compare against.

## Re-running before a future release

Re-run the script above whenever the adapters or the reference wrappers change,
compare the reference hashes in the table, and update this document with the new
date and results. Treat any flagged pair as a release blocker until it is
explained — and if material overlap ever appears, the correct response is to
obtain a license or rewrite the file, never to reword it.
