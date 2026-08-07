# Publication checklist

**Release decision record for version 0.1.0.** All publication gates that the
maintainers can close are complete. Provider-plan compatibility remains a
use-time condition enforced by preflight acknowledgement, not a claim of
provider approval.

This file is the decision record for the release. It is also the one file
allowed to name the project's pre-release identifiers, so the rename can be
audited — see section 5.

An MIT `LICENSE` file names Aaron Dyson and Chris Blaschke as copyright holders.
Both authors approved the license and attribution on 2026-08-06; Chris approved
in person while with Aaron, and Aaron recorded that approval here.

**Status as of 2026-08-07: approved for public release as a provider-neutral
open-source tool.** Sections 1–7 are closed with evidence. Section 4 does not
claim that consumer-subscription automation is permitted; operational use stays
conditional on the operator reviewing their own plan and setting the explicit
preflight acknowledgement.

---

## 1. License — COMPLETE

- [x] Choose the license: **MIT** (selected by Aaron Dyson on 2026-08-06).
- [x] Both authors approved licensing their contributions under MIT on
      2026-08-06; Chris Blaschke approved in person while with Aaron Dyson.
- [x] Add the standard MIT `LICENSE` text; no `NOTICE` is required.
- [x] Both authors confirmed the copyright holder line: "Aaron Dyson and Chris
      Blaschke."
- [x] No per-file license headers are required for this release.
- [x] Contribution licensing decided: inbound = outbound MIT, DCO sign-off, no
      CLA. Recorded in `CONTRIBUTING.md`.

## 2. Third-party code provenance — CLOSED

The private fleet this repository was extracted from contains hardened
`codex-leg`, `grok-leg`, and related wrapper implementations and routing
doctrine. **That upstream work is not licensed for redistribution and is not
included here.**

- [x] Confirmed by mechanical audit, not assertion, that no upstream wrapper
      implementation, routing doctrine text, or private fleet configuration was
      copied into this repository. Evidence: `docs/provenance.md` — deterministic
      line and 5-line-shingle comparison against both private reference wrappers,
      identified by SHA-256. **Shingle Jaccard 0.0000 for every file pair**;
      longest matching run 4 normalized lines, in two places, both manually
      inspected and both generic shell/JSON boilerplate.
- [x] Sanitization suite re-run immediately before the release commit; see
      `RELEASE_CHECKS.md`.
- [x] Confirmed `docs/adapters.md` describes only an *interface* that this
      project calls. The bundled `scripts/efo_codex_leg.sh` and
      `scripts/efo_grok_leg.sh` are original slot-controlled caller-side layers,
      not upstream implementations.
- [x] Standing rule recorded: including any upstream code requires explicit
      written permission and a compatible license first. Restated in
      `CONTRIBUTING.md` and `docs/provenance.md`.

## 3. Author consent, attribution, and contact — CLOSED

- [x] **Chris Blaschke approved** publication of this extraction, being named in
      `ATTRIBUTION.md`, and the exact role language on 2026-08-06. Approval was
      given in person while with Aaron Dyson and recorded by Aaron here.
- [x] **Aaron Dyson approved** the same on 2026-08-06.
- [x] Both founders approved use of the ax0s organizational attribution.
- [x] Final agreed role language is recorded in `ATTRIBUTION.md`.
- [x] Both authors chose to publish their personal names with the ax0s name.
- [x] Maintainer / security contact decided: **chris@ax0s.io** primary,
      **aaron@ax0s.io** backup. Both are business addresses, both owners agree to
      receive reports, and both were approved for public documentation on
      2026-08-07. Recorded in `SECURITY.md`.
- [x] Support posture decided and stated in `README.md` and `SECURITY.md`:
      best-effort, maintained by the two named authors, no SLA, no guaranteed
      response or remediation timeline, no bug bounty.

## 4. Provider terms review — PUBLICATION CLEARED; USE CONDITIONAL

This project automates official vendor CLIs. Automation and headless use are
governed by each provider's terms and by the operator's specific plan.

- [x] Reviewed Anthropic's Consumer Terms, Usage Policy, and Commercial Terms,
      plus the official Claude Code headless documentation.
- [x] Reviewed OpenAI's Terms of Use restrictions and the official Codex CLI
      documentation.
- [x] Reviewed xAI's Acceptable Use Policy, consumer terms, and the official
      Grok CLI headless documentation.
- [x] Findings recorded with stable official URLs, effective dates, retrieval
      date 2026-08-07, and an explicit record of which pages could **not** be
      retrieved directly: `docs/provider-terms-review.md`.
- [x] Confirmed no document in this repository frames CLI routing as a way to
      avoid API fees, save subscription cost, evade rate limits, or obtain
      entitlements not granted by the provider. Scanned and verified; see
      `RELEASE_CHECKS.md`.
- [x] Confirmed the non-interactive approval path for the Grok worker is
      described accurately, with its risks stated, and presented as the
      operator's deliberate decision (`docs/security.md`, `SECURITY.md`).
- [x] Confirmed no documentation instructs users to violate an acceptable use
      policy, and that the responsibility statement in `README.md` and
      `docs/security.md` is accurate and prominent.

- [x] **Publication decision recorded:** automated,
      consumer-subscription-authenticated CLI use could not be affirmatively
      cleared for any of the three providers. That uncertainty does not prevent
      publication of a provider-neutral tool, but it prevents any claim that a
      particular plan permits operation. Runtime use remains conditional.
      Summary of why:
  - Anthropic's Consumer Terms prohibit automated or non-human access "[e]xcept
    when you are accessing our Services via an Anthropic API Key or where we
    otherwise explicitly permit it." The official headless documentation routes
    scripted and CI use to `--bare` with `ANTHROPIC_API_KEY` and states that bare
    mode "doesn't use your subscription login." Whether documenting `claude -p`
    constitutes the "explicitly permit[ted]" exception for subscription-login
    automation is unresolved.
  - OpenAI's Terms of Use prohibit programmatically extracting Output and
    circumventing rate limits, while OpenAI's own documentation describes calling
    `codex exec` "from repeatable workflows and pipelines." Plan-level clearance
    is not stated.
  - xAI's Acceptable Use Policy prohibits "[a]ccessing the Services through
    automated or non-human means, whether through a bot, script, or otherwise,"
    with no API-key carve-out found in the retrievable text, while xAI's own CLI
    documentation recommends headless mode "for scripts, bots, or other
    machine-friendly tasks." These are in direct tension.

  Because of this, the design response is in the code and docs, not in a claim:
  positioning is provider-neutral ("official, authenticated vendor CLIs"), the
  operator is told they must verify their own plan, and `efo-preflight` **fails
  closed** until the operator sets `EFO_PROVIDER_TERMS_ACK=1` after reading
  `docs/provider-terms-review.md`. No provider has reviewed or approved this
  project, and none was contacted.

## 5. Trademark and naming review — CLOSED

- [x] Reviewed use of **"Prime" / "Prime Agent" / "Prime Intellect"**. Resolved
      by renaming rather than by relying on nominative fair use: the project,
      its commands, and its environment variables no longer use the mark at all.
- [x] Reviewed use of **"Fable"**, **"Claude"**, **"Opus"** (Anthropic),
      **"Codex"** (OpenAI), and **"Grok"** (xAI). These remain **only** as
      nominative interoperability references — model IDs the operator passes to a
      vendor CLI, evidence files named after the model that ran, and prose
      describing what this project interoperates with. No vendor mark appears in
      the project name, a command name, or an environment variable.
- [x] Rename executed and mechanically enforced:

  | Was | Is |
  | --- | --- |
  | `prime-fable-orchestrator` (project) | `evidence-first-orchestrator` |
  | `prime-fable-orchestrate` | `efo-orchestrate` |
  | `prime-codex-leg` | `efo-codex-leg` |
  | `prime-grok-leg` | `efo-grok-leg` |
  | `prime-preflight` | `efo-preflight` |
  | `PRIME_*` (17 variables) | `EFO_*` |
  | `.prime-slots/` | `.efo-slots/` |
  | `$HOME/.prime/orchestration-runs` | `$HOME/.efo/orchestration-runs` |

- [x] No backward aliases and no migration note: this is a pre-release rename,
      so the legacy names were removed outright rather than deprecated.
- [x] `tests/test_naming.py` fails the build if any legacy project, command,
      module, environment-variable, or dot-directory identifier reappears in a
      publishable file or path. This file is its only allowlisted exception,
      because it is the decision record above. The guard verifies each of its own
      patterns against a synthetic positive so a typo cannot silently pass.
- [x] Confirmed the project name does not imply affiliation or endorsement.
- [x] Confirmed the independence disclaimer appears in `README.md`,
      `ATTRIBUTION.md`, and `SKILL.md`.
- [x] No badge, logo, or wordmark implying endorsement, certification,
      partnership, or official listing appears anywhere, including CI.
- [x] Name collisions checked on 2026-08-07 (read-only queries):
      **PyPI** `evidence-first-orchestrator` — HTTP 404, free.
      **npm** `evidence-first-orchestrator` — HTTP 404, free.
      **GitHub** — an unrelated repository `heosanghun/evidence-first-orchestrator`
      already exists. GitHub repository names are owner-scoped, so this does not
      block publication under our own account, but it is recorded because it
      affects discoverability and search. No registry name has been claimed.

## 6. Content and secret hygiene — CLOSED

- [x] Sanitization suite re-run: zero person names, organization slugs,
      home-directory absolute paths, or private hostnames outside the files where
      credit and contact are the subject matter.
- [x] **Entire git history scanned**, not just the working tree: all 50 objects
      across all commits, for credential patterns, home-directory paths, private
      hostnames, and names outside the permitted files. **Clean.** Because the
      history is clean, squashing to a fresh initial commit is *not* required for
      sanitization reasons. It remains an option for a tidier public history.
- [x] Confirmed no credential, token, cookie, session id, account identifier, or
      private endpoint appears anywhere, including example output.
- [x] Confirmed example evidence paths and job directories are generic.
- [x] Reviewed `docs/` for residual private operational policy; none remains.
- [x] Verified no symlink in the tree escapes the repository.

Exact commands and results: `RELEASE_CHECKS.md`.

## 7. Release engineering — CLOSED

- [x] `tests/run-tests.sh` green locally and hermetically without vendor CLIs:
      **67 tests**.
- [x] CI runs on a clean `ubuntu-latest` runner: test suite, `bash -n` shell
      syntax checks, and `python -m compileall`. No network beyond checkout and
      Python setup, no secrets, no vendor CLI.
- [x] CI workflow contains no badge asserting publication, certification, or
      endorsement.
- [x] `SECURITY.md` with both reporting addresses, scope, and honest response
      expectations.
- [x] `CONTRIBUTING.md` with DCO sign-off, inbound = outbound MIT, and no CLA.
- [x] `CHANGELOG.md` with the initial `0.1.0 - 2026-08-07` entry.
- [x] Version source of truth: root `VERSION` file, read by `scripts/efo_version.py`.
      `--version` prints `evidence-first-orchestrator 0.1.0` from all four entry
      points, and a test asserts the version literal is not duplicated in code.
- [x] Support posture stated in `README.md`.
- [x] Install and preflight documentation rewritten for a first-time user on a
      clean machine; install/uninstall lifecycle verified end to end.
- [x] Documentation corrected where it overstated the implementation — see the
      accuracy fixes listed in `RELEASE_CHECKS.md`.

- [x] Public host selected: GitHub organization `ax0s-io`, repository
      `evidence-first-orchestrator`, public visibility.
- [x] Independent outside read-through completed during the bounded Grok
      refutation pass. Its confirmed documentation defects were fixed and the
      complete gate was re-run centrally.

## 8. Sign-off

Both maintainers approve version 0.1.0 for public release at
`https://github.com/ax0s-io/evidence-first-orchestrator`.

This approval does **not** assert that Anthropic, OpenAI, or xAI permits
consumer-subscription automation on any specific plan. It approves publishing
the code, disclosures, and fail-closed acknowledgement gate. Every operator
must verify their own provider terms before use.

| Item | Owner | Date | Evidence |
| --- | --- | --- | --- |
| License chosen | Aaron Dyson + Chris Blaschke | 2026-08-06 | MIT `LICENSE`; both approved |
| Provenance confirmed | Orchestrated audit | 2026-08-07 | `docs/provenance.md`; Jaccard 0.0000, longest run 4 generic lines |
| Author consent | Aaron Dyson + Chris Blaschke | 2026-08-06 | Approved and recorded in this file |
| Security contact agreed | Chris Blaschke + Aaron Dyson | 2026-08-07 | `SECURITY.md` |
| Provider terms reviewed | Orchestrated review | 2026-08-07 | `docs/provider-terms-review.md`; runtime use conditional |
| Trademark review + rename | Orchestrated implementation | 2026-08-07 | `tests/test_naming.py`; rename table in section 5 |
| Secret/history scan | Central release gate | 2026-08-07 | `RELEASE_CHECKS.md`; Gitleaks 8.30.1 clean |
| Cross-vendor refutation | Independent Grok reviewer | 2026-08-07 | Findings and repairs in `RELEASE_CHECKS.md` |
| Public host | Aaron Dyson + Chris Blaschke | 2026-08-07 | GitHub `ax0s-io/evidence-first-orchestrator`, public |
| Outside README read-through | Independent Grok reviewer | 2026-08-07 | Confirmed defects repaired; 67 tests green |
| Plan-level provider clearance | Each operator | At use time | Required `EFO_PROVIDER_TERMS_ACK=1`; not provider endorsement |
