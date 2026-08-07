# Publication checklist

**This repository is a draft and is not published.** Nothing here may be
pushed to a public host, announced, submitted to a registry or skill index, or
shared outside the authors until every item below is resolved and recorded.

An MIT `LICENSE` file names Aaron Dyson and Chris Blaschke as copyright
holders. Both authors approved the license and attribution on 2026-08-06;
Chris approved in person while with Aaron, and Aaron recorded that approval
here.

---

## 1. License — COMPLETE

- [x] Choose the license: **MIT** (selected by Aaron Dyson on 2026-08-06).
- [x] Both authors approved licensing their contributions under MIT on
      2026-08-06; Chris Blaschke approved in person while with Aaron Dyson.
- [x] Add the standard MIT `LICENSE` text; no `NOTICE` is required.
- [x] Both authors confirmed the copyright holder line: “Aaron Dyson and Chris
      Blaschke.”
- [x] No per-file license headers are required for this release.

## 2. Third-party code provenance — BLOCKING

The private fleet this repository was extracted from contains hardened
`codex-leg`, `grok-leg`, and `prime-leg` wrapper implementations and routing
doctrine. **That upstream work is not licensed for redistribution and is not
included here.**

- [ ] Confirm with a written statement that no upstream wrapper implementation,
      routing doctrine text, or private fleet configuration has been copied
      into this repository.
- [ ] Re-run the sanitization test (`tests/`) and a fresh manual diff review
      immediately before release; treat any new upstream paste as a blocker.
- [ ] Confirm that `docs/adapters.md` describes only an *interface* that this
      project calls, and does not reproduce an upstream implementation.
- [ ] If any upstream code is ever to be included, obtain explicit written
      permission and a compatible license from its owner first.

## 3. Author consent and attribution — CONTACT STILL BLOCKING

- [x] **Chris Blaschke approved** publication of this extraction, being named
      in `ATTRIBUTION.md`, and the exact role language on 2026-08-06. Approval
      was given in person while with Aaron Dyson and recorded by Aaron here.
- [x] **Aaron Dyson approved** the same on 2026-08-06.
- [x] Both founders approved use of the ax0s organizational attribution.
- [x] Final agreed role language is recorded in `ATTRIBUTION.md`.
- [x] Both authors chose to publish their personal names with the ax0s name.
- [ ] Decide the maintainer contact / security contact address, and confirm
      whoever owns it agrees to receive reports.

## 4. Provider terms review — BLOCKING

This project automates official vendor CLIs. Automation and headless use are
governed by each provider's terms.

- [ ] Review Anthropic's Consumer/Commercial Terms and Usage Policy for
      automated Claude Code invocation on the plan(s) this targets.
- [ ] Review OpenAI's terms for automated Codex CLI invocation.
- [ ] Review xAI's terms for automated Grok CLI invocation.
- [ ] Confirm no document in this repository frames CLI routing as a way to
      avoid API fees, evade rate limits, or obtain entitlements not granted by
      the provider. Remove any such framing entirely, including implications.
- [ ] Confirm the always-approve / non-interactive approval path for Grok is
      described accurately, with its risks stated, and that it is presented as
      the operator's decision.
- [ ] Confirm no documentation instructs users to violate a provider's
      acceptable use policy, and that the responsibility statement in
      `README.md` and `docs/security.md` is accurate and prominent.

## 5. Trademark and naming review — BLOCKING

- [ ] Review use of **"Prime" / "Prime Agent" / "Prime Intellect"** — the
      current repository name, launcher name (`prime-fable-orchestrate`), and
      environment variable prefix (`PRIME_*`) all use it. Confirm nominative
      fair use, or rename.
- [ ] Review use of **"Fable"**, **"Claude"**, **"Opus"** (Anthropic),
      **"Codex"** (OpenAI), and **"Grok"** (xAI).
- [ ] Confirm the project name does not imply affiliation or endorsement. If
      it might, rename before release.
- [ ] Confirm the independence disclaimer appears in `README.md`,
      `ATTRIBUTION.md`, and `SKILL.md`.
- [ ] Add no badge, logo, or wordmark implying endorsement, certification,
      partnership, or official listing.
- [ ] Check name collisions on the intended package/registry namespace.

## 6. Content and secret hygiene — BLOCKING

- [ ] Re-run the sanitization test suite; it must find zero person names,
      org slugs, home-directory absolute paths, or private hostnames in code,
      tests, docs, or workflows.
- [ ] Scan the **entire git history**, not just the working tree — the history
      of this draft is not yet suitable for publication. Plan to publish from a
      **fresh, squashed initial commit** rather than the extraction history.
- [ ] Confirm no credential, token, cookie, session id, account identifier, or
      private endpoint appears anywhere, including example output.
- [ ] Confirm example evidence paths and job directories are generic.
- [ ] Review `docs/` for any residual private operational policy that is not
      needed to use the project.

## 7. Release engineering — before tagging

- [ ] Decide the public repository host, name, and visibility.
- [ ] `tests/run-tests.sh` green locally and in CI on a clean checkout.
- [ ] CI workflow contains no badge asserting publication, certification, or
      endorsement.
- [ ] `SECURITY.md` with a reporting address (see item 3).
- [ ] `CONTRIBUTING.md` and a contribution-licensing decision (DCO vs. CLA vs.
      inbound=outbound), added only after item 1 closes.
- [ ] `CHANGELOG.md` and an initial version number.
- [ ] Decide the support posture explicitly (maintained / best-effort /
      archived-on-arrival) and say so in `README.md`.
- [ ] Final read-through of `README.md` by someone who has never seen the
      private fleet, to confirm it is usable without it.

## Sign-off

Publication requires all remaining BLOCKING sections to close. The repository
is MIT-licensed with both authors’ recorded approval, but stays private until
provider-terms, naming, provenance, security-contact, and release checks pass.

| Item | Owner | Date | Evidence |
| --- | --- | --- | --- |
| License chosen | Aaron Dyson + Chris Blaschke | 2026-08-06 | MIT `LICENSE`; both approved |
| Provenance confirmed | | | |
| Aaron Dyson consent | Aaron Dyson | 2026-08-06 | Approved in this session |
| Chris Blaschke consent | Chris Blaschke | 2026-08-06 | Approved in person while with Aaron; recorded by Aaron |
| Provider terms reviewed | | | |
| Trademark review | | | |
| Secret/history scan | | | |
