# Provider terms review

**Retrieval date: 2026-08-07.** Reviewed by the maintainers as an engineering
exercise before the first public release. This is an August 2026 record, not
current plan-level clearance; re-check the linked sources before use.

> **This is not legal advice.** It is a good-faith reading of official provider
> documents by software engineers, recorded so that readers can check the same
> sources themselves. Terms change without notice. You are responsible for
> reading the current terms for **your own plan** and deciding whether what you
> intend to do is permitted. If this document and a provider's current terms
> disagree, the provider's terms win.

## Why this document exists

This project starts official, authenticated vendor CLIs as child processes and
drives them non-interactively. That is automation. Whether automation is
permitted is decided by each provider's terms and by the specific plan the
operator is on — not by this project, and not by us.

Scope of this review: **official provider sources only** — terms of service,
usage/acceptable-use policies, and first-party product documentation. No blog
posts, no community summaries, no third-party interpretations. Where we could
not retrieve a source directly, we say so rather than paraphrasing something we
did not read.

**We do not treat silence as permission.** A provider that does not mention a
practice has not allowed it.

---

## Retrieval method and its limits

Some official legal pages refused automated retrieval (HTTP 403) from the
tooling used for this review. That is itself worth noting, and it constrains
what this document can claim.

| Source | URL | Retrieval |
| --- | --- | --- |
| Anthropic Consumer Terms of Service | https://www.anthropic.com/legal/consumer-terms | Fetched directly |
| Anthropic Usage Policy | https://www.anthropic.com/legal/aup | Fetched directly |
| Anthropic Commercial Terms of Service | https://www.anthropic.com/legal/commercial-terms | Fetched directly |
| Claude Code — programmatic/headless docs | https://code.claude.com/docs/en/headless | Fetched directly |
| OpenAI Terms of Use (ROW) | https://openai.com/policies/row-terms-of-use/ | **HTTP 403 to a direct fetch.** Clause text below was surfaced by a search tool reading that official page; it was not verified byte-for-byte by us |
| OpenAI Usage Policies | https://openai.com/policies/usage-policies/ | **HTTP 403. Not retrieved.** No claim is made about its contents |
| OpenAI Codex CLI documentation | https://learn.chatgpt.com/docs/codex/cli (redirect target of https://developers.openai.com/codex/cli) | Fetched directly |
| xAI Acceptable Use Policy | https://x.ai/legal/acceptable-use-policy | **HTTP 403 to a direct fetch.** Clause text below was surfaced by a search tool reading that official page; not verified byte-for-byte by us |
| xAI Terms of Service — Consumer | https://x.ai/legal/terms-of-service | **HTTP 403 to a direct fetch.** Only an archived prior version was reachable |
| Grok CLI — headless & scripting docs | https://docs.x.ai/build/cli/headless-scripting | Fetched directly |

**Consequence:** for OpenAI and xAI, the legal-page quotations below are
second-hand retrievals of first-party pages. Before relying on them, open the
URLs yourself. This is exactly why the conclusion of this review is *"verify
your own plan"* and not *"you are cleared."*

---

## 1. Officially supported CLI authentication

All three vendors ship an official CLI and document more than one way to
authenticate it. This part is not in doubt.

**Anthropic — Claude Code.** Non-interactive operation is a documented,
first-party feature. From the official headless documentation:

> "To run Claude Code in non-interactive mode, pass `-p` with your prompt"

> "The [Agent SDK] is available as a CLI for scripts and CI/CD"

The same page distinguishes two authentication paths, and this distinction is
the single most important finding in this review:

> "Set `ANTHROPIC_API_KEY` before running it, because bare mode doesn't use your
> subscription login"

> "In bare mode, Claude Code never reads OAuth credentials or the system keychain."

> "`--bare` is the recommended mode for scripted and SDK calls, and will become
> the default for `-p` in a future release."

So Anthropic's documented, recommended path for scripted and CI invocation is
**API-key authentication**, explicitly *not* the subscription login.

**OpenAI — Codex CLI.** Non-interactive operation is likewise documented:

> "Use Codex interactively or call `codex exec` from repeatable workflows and
> pipelines."

The quickstart describes signing in with ChatGPT "or another available sign-in
method." The pages we retrieved do **not** state which ChatGPT plans may be used
in automated contexts.

**xAI — Grok CLI.** Headless mode is documented for machine use:

> "Use headless mode for scripts, bots, or other machine-friendly tasks."

The documentation contemplates either a locally authenticated CLI or an API key
— "the example below assumes `grok` is already authenticated locally, or
`XAI_API_KEY` is set" — and gives CI-specific advice ("pass `--no-auto-update`").

## 2. Automation and headless use: restriction and unresolved uncertainty

This is where the picture stops being clean.

**Anthropic Consumer Terms of Service** (effective 2025-10-08) list among things
you may not do:

> "Except when you are accessing our Services via an Anthropic API Key or where
> we otherwise explicitly permit it, to access the Services through automated or
> non-human means, whether through a bot, script, or otherwise."

Read it carefully. Automated access is prohibited **except** (a) via an API key,
or (b) where Anthropic explicitly permits it. Driving a subscription-authenticated
Claude Code session from a script is automated access that is not via an API key.
It is therefore permitted only if it falls under "where we otherwise explicitly
permit it."

Does publishing headless documentation constitute that explicit permission? We
cannot answer that, and we will not guess. The argument in favour is that
Anthropic documents `claude -p` as a product feature. The argument against is
that the very same page routes scripted and CI use to `--bare` with
`ANTHROPIC_API_KEY` and states plainly that bare mode "doesn't use your
subscription login." **We treat this as unresolved.**

The Anthropic Commercial Terms of Service (effective 2025-06-17) contain no
equivalent automation clause that we found; they state that the customer "is
responsible for all activity under its account." Commercial/enterprise
arrangements may therefore sit differently — but that is between the operator
and Anthropic.

**OpenAI Terms of Use.** The "What you cannot do" section prohibits (as
retrieved indirectly, see the caveat above) automatically or programmatically
extracting data or Output from the Services, and prohibits interfering with the
Services, including circumventing rate limits or restrictions or bypassing
protective measures. Whether invoking OpenAI's own documented `codex exec`
entrypoint constitutes "programmatic extraction of Output" is not something the
retrieved text settles. **Unresolved.**

**xAI Acceptable Use Policy.** As retrieved indirectly, the policy prohibits:

> "Accessing the Services through automated or non-human means, whether through
> a bot, script, or otherwise."

We did **not** find an API-key carve-out in the text we were able to retrieve —
unlike Anthropic's clause, which contains one explicitly. That leaves a direct
tension with xAI's own CLI documentation, which tells users to use headless mode
"for scripts, bots, or other machine-friendly tasks." We cannot reconcile those
two statements from public sources. **Unresolved, and of the three, the least
clear.**

An archived prior version of the xAI consumer terms restricted automated means
that "send more request messages to the servers running the Service than a human
can reasonably produce in the same period of time by using a conventional
on-line web browser" — a volume-based test rather than a blanket prohibition.
We could not retrieve the current consumer terms to confirm whether that
framing survives.

### What this adds up to

**We could not affirmatively clear automated, consumer-subscription-authenticated
use of any of the three CLIs.** Not one of the three vendors states that a
third-party program may drive its subscription-authenticated CLI. Two of the
three explicitly route scripted use toward API-key authentication instead.

We are not claiming the opposite either — we are not asserting that this is
prohibited on your plan. We are saying the question is open, and it is the
operator's to close.

## 3. Behaviour that is prohibited without ambiguity

These we treat as settled, and this project must never do them or encourage
them:

- **Circumventing rate limits, usage limits, protective measures, or safety
  mitigations.** Prohibited by OpenAI's terms and xAI's AUP in the text
  retrieved; contrary to the spirit of Anthropic's Usage Policy.
- **Sharing account credentials or making an account available to others.**
  Anthropic Consumer Terms: "You may not share your Account login information,
  Anthropic API key, or Account credentials with anyone else. You also may not
  make your Account available to anyone else."
- **Coordinating activity across multiple accounts to avoid detection or
  circumvent guardrails**, and **using automation in account creation**
  (Anthropic Usage Policy, effective 2025-09-15).
- **Circumventing a ban** by using a different account (Anthropic Usage Policy).
- **Reverse-engineering the services or models**; **model scraping or
  distillation** without authorization (Anthropic Usage Policy; xAI AUP).
- **Jailbreaking or prompt-injecting a product's guardrails** to produce harmful
  output without prior authorization (Anthropic Usage Policy).

## 4. Our design response

Each of these is a property of the code and documentation in this repository,
not an aspiration.

1. **No entitlement claim, anywhere.** This project is not positioned as a way
   to avoid API fees, stretch a subscription, reduce provider cost, evade a rate
   limit, or obtain capacity you were not granted. Any such framing is a
   documentation bug — report it. The repository states no provider permission
   that we do not have.

2. **Provider-neutral positioning.** The project drives *official, authenticated
   vendor CLIs*, whichever authentication the operator has configured. It is not
   a proxy, relay, credential broker, or account-sharing mechanism. It ships no
   vendor client and no credentials, and it never reads, stores, forwards, or
   inspects provider credentials.

3. **The operator must verify their own plan.** README, `docs/setup.md`, and
   `docs/adapters.md` state that automated or headless invocation may be
   restricted or prohibited depending on the provider and plan, and that the
   operator must check before running. This document is linked from each.

4. **Preflight acknowledgement.** `efo-preflight`
   fails until the operator acknowledges this review by setting
   `EFO_PROVIDER_TERMS_ACK=1`. There is no way to reach a green preflight
   without passing that acknowledgement, and the check names this file. The gate
   is deliberately trivial to satisfy — its purpose is informed consent, not
   obstruction, and we do not pretend it enforces compliance. The launcher
   does not enforce this acknowledgement; operators must run preflight.

5. **No rate-limit or quota circumvention machinery.** The project has no
   retry-until-allowed loop, no key rotation, no account rotation, no
   multi-account coordination, no backoff-defeating behaviour, and no
   ban-evasion capability. Its concurrency controls are *ceilings* that reduce
   load, never floors that sustain it. The single cross-model fallback path
   triggers on a quota or availability error by switching to a **different model
   on the same account** once, and only after proving the first attempt had no
   side effects — it does not retry the exhausted entitlement.

6. **Nominative naming only.** Vendor and model names appear solely to describe
   interoperability, alongside a non-affiliation disclaimer. See
   `ATTRIBUTION.md`.

7. **Adapters are interfaces, not bundled vendor code.** The `codex-leg` and
   `grok-leg` adapters are supplied by the operator. Clearing an adapter that
   drives a consumer-subscription CLI against that plan's terms is the
   operator's responsibility. See `docs/adapters.md` and `docs/provenance.md`.

## 5. Open questions we cannot answer

These need an answer from the provider, not from us. None is resolved by this
release, and this section should be updated — not deleted — when one is.

1. **Anthropic:** does documenting `claude -p` constitute the "explicitly
   permit[ted]" exception in Consumer Terms clause 3.7 for automation that uses
   a subscription login rather than an API key? The headless documentation
   pointing scripted use at `--bare` with `ANTHROPIC_API_KEY` suggests the
   safest reading is no.
2. **OpenAI:** does driving `codex exec` from another program count as
   "automatically or programmatically extract[ing] data or Output"? Which
   ChatGPT plans permit automated `codex exec`?
3. **xAI:** how does the AUP prohibition on "accessing the Services through
   automated or non-human means" coexist with official Grok CLI documentation
   recommending headless mode "for scripts, bots, or other machine-friendly
   tasks"? Is there an API-key carve-out we could not retrieve?
4. **All three:** does a *human-initiated* single automated run differ from a
   scheduled or unattended one under these terms?

We have not contacted any provider about these questions, and no provider has
reviewed, approved, or endorsed this project or this document.

## How to re-run this review

Open every URL in the table above, check the effective date at the top of each
document, and re-read sections 2 and 3 against it. Update the retrieval date
and this document's conclusions when they change. If a provider's terms move
against the design, change the code — not the summary.
