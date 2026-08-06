# Publication checklist

**This repository is a draft and is not published.** Nothing here may be
pushed to a public host, announced, submitted to a registry or skill index, or
shared outside the authors until every item below is resolved and recorded.

There is deliberately **no `LICENSE` file**. Absent a license, no use,
copying, modification, or redistribution rights are granted to anyone. That is
the intended state until item 1 is closed.

---

## 1. License — BLOCKING

- [ ] Choose the license (candidates: Apache-2.0 for the patent grant and
      NOTICE conventions, or MIT for minimalism).
- [ ] Confirm every author agrees to license their contributions under it.
- [ ] Add `LICENSE`, and `NOTICE` if Apache-2.0 is chosen.
- [ ] Add the copyright holder line (individual authors vs. an ax0s entity —
      decide deliberately; it affects who can enforce and relicense).
- [ ] Add per-file headers only if the chosen license expects them.

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

## 3. Author consent and attribution — BLOCKING

- [ ] **Chris Blaschke's explicit written consent** to publish this extraction,
      to be named in `ATTRIBUTION.md`, and to the exact role language used.
- [ ] **Aaron Dyson's explicit written consent** to the same.
- [ ] Confirm the ax0s organizational attribution is accurate and that whoever
      controls the ax0s name approves its use here.
- [ ] Replace the "pending approval" markers in `ATTRIBUTION.md` with the
      agreed final language.
- [ ] Decide whether personal names appear at all, or only an org name and
      contact address.
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

Publication requires all BLOCKING sections closed and both authors' recorded
approval. Until then this repository stays private and unlicensed.

| Item | Owner | Date | Evidence |
| --- | --- | --- | --- |
| License chosen | | | |
| Provenance confirmed | | | |
| Aaron Dyson consent | | | |
| Chris Blaschke consent | | | |
| Provider terms reviewed | | | |
| Trademark review | | | |
| Secret/history scan | | | |
