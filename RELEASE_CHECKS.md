# Release checks — version 0.1.0

> Historical release record from August 2026, not a current certification.
> The November documentation review does not re-run the private-reference
> comparison, model review, or provider calls described here. Offline test
> results do not establish current provider compatibility or plan permission.

**Run date:** 2026-08-07
**Scope:** complete publishable working tree and all pre-release Git history
**Result:** passed, subject to the provider-plan limitation documented below

This file records commands and outcomes, not model assertions. The authoritative
suite is deterministic and offline. Provider-plan compatibility is not something
a test can prove; see `docs/provider-terms-review.md`.

## Authoritative and hermetic tests

```bash
./tests/run-tests.sh
```

Result: **67 tests passed** in approximately 21 seconds.

The same suite was run with an empty synthetic home and a minimal path containing
no vendor CLI:

```bash
env -i HOME="$TMP/home" PATH=/usr/bin:/bin TMPDIR="$TMP" LANG=C   /absolute/path/to/python3 -m unittest discover -s tests -t .
```

Result: **67 tests passed**. The suite did not contact a network, invoke a model,
or require Claude, Codex, or Grok.

## Preflight and version surface

```bash
EFO_PROVIDER_TERMS_ACK=1 ./scripts/efo_preflight.py
./scripts/efo_orchestrate.py --version
./scripts/efo_preflight.py --version
EFO_ORCHESTRATION_JOB_DIR=/tmp ./scripts/efo_codex_leg.sh --version
EFO_ORCHESTRATION_JOB_DIR=/tmp ./scripts/efo_grok_leg.sh --version
```

Result: preflight `Overall: OK`; all four entry points printed
`evidence-first-orchestrator 0.1.0`.

Without `EFO_PROVIDER_TERMS_ACK=1`, preflight intentionally fails. The variable
records that the operator read the terms review; it does not certify compliance
or provider approval.

## Install lifecycle

A fresh temporary prefix was used:

```bash
./scripts/install.sh --prefix "$TMP/bin"
"$TMP/bin/efo-orchestrate" --version
./scripts/install.sh --prefix "$TMP/bin" --uninstall
```

Result: exactly four links were installed (`efo-orchestrate`, `efo-preflight`,
`efo-codex-leg`, `efo-grok-leg`), version output was correct, and uninstall left
zero entries. The automated suite also covers dry-run purity, idempotency,
foreign-link refusal, clobber refusal, forced replacement, and unknown flags.

## Syntax, imports, links, and filesystem hygiene

```bash
find scripts tests -type f -name '*.sh' -print0 |   while IFS= read -r -d '' file; do bash -n "$file"; done
python3 -m compileall -q scripts tests
python3 -m unittest tests.test_docs -q
find . -path ./.git -prune -o -type l -print
git diff --check
```

Results:

- all shell files passed `bash -n`;
- all Python files compiled;
- every local Markdown link target exists;
- zero symlinks exist in the repository tree, so no symlink can escape it;
- no whitespace errors.

## Naming and sanitization

The authoritative suite includes positive-controlled gates that scan every
tracked or untracked, non-ignored publishable file:

- no old project, command, module, environment-variable, or dot-directory name
  outside the sole decision-record exception;
- a catch-all rejects any newly invented legacy-prefixed identifier;
- no personal home-directory path or private hostname;
- names and the organization slug occur only where attribution, licensing,
  consent, or security contact is the subject matter;
- every allowlist entry must contain a legitimate match, preventing unused
  exemptions from becoming blind spots.

Result: all naming and sanitization tests passed.

A separate text review found no framing that promises subscription savings,
avoids API fees, evades limits, or grants provider entitlements. Public wording
is provider-neutral and links prominently to `docs/provider-terms-review.md`.

## Secret scanning — working tree and Git history

Gitleaks was installed from the Homebrew release and run in both modes:

```bash
gitleaks dir . --no-banner --redact --exit-code 1
gitleaks git . --no-banner --redact --log-opts='--all' --exit-code 1
```

Tool: **Gitleaks 8.30.1**.
Result before the release commit: **no leaks found** in the complete working
tree and all three existing commits. The history scan was repeated after the
release commit before push; it remained clean.

No token, credential, cookie, private key, account identifier, private endpoint,
or session identifier was found. Gitleaks output was redacted by command even
though there were no findings.

## Private-wrapper provenance

The read-only audit in `docs/provenance.md` compared every publishable text file
against the locally installed private `codex-leg` and `grok-leg` references,
identified by SHA-256. It used aggressively normalized lines, five-line shingles,
and a conservative matching-run upper bound.

Result: five-line shingle Jaccard **0.0000 for every pair**; longest upper-bound
matching run **4 generic shell/JSON lines**. No material private implementation
was copied. The repository contains original slot-controlled caller layers and
interface documentation, not the private adapter implementations.

## Independent cross-vendor refutation

After implementation, one bounded read-only Grok pass attempted to falsify the
release claims. It confirmed these defects:

1. this release-check evidence file was cited before it existed;
2. setup docs initially omitted the required provider-terms acknowledgement;
3. the name allowlist was broader than necessary;
4. the legacy-name test needed a catch-all rather than enumerating only known
   old names;
5. provenance prose overstated what its conservative matching-run measure meant;
6. renamed deletions had not yet been staged, and stale bytecode remained local.

Repairs:

- created this file from centrally re-run commands;
- documented `EFO_PROVIDER_TERMS_ACK=1` in README and setup, with its exact
  acknowledgement-only semantics;
- reduced the name allowlist and added a test requiring every exemption;
- added the catch-all naming guard and positive controls;
- corrected provenance terminology without weakening the test;
- staged the rename as a unit and removed ignored bytecode before the release
  commit.

The complete 67-test gate, hermetic gate, preflight, Gitleaks scans, syntax
checks, install lifecycle, and local-link test were run centrally after those
repairs. The implementers did not certify themselves.

## Provider terms limitation

Official-source review found documented headless CLI features but could not
affirmatively clear automated consumer-subscription authentication for any of
the three providers. Publication therefore makes no plan-level permission
claim. Runtime preflight requires the operator to acknowledge that uncertainty.
This is a disclosed use-time condition, not a failed software test and not legal
advice.
