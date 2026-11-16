# evidence-first-orchestrator

> **Status: historical v0.1.0. Current provider compatibility is unverified.**
> This release is for existing users maintaining its adapter contracts and for
> readers studying bounded execution and evidence checks, not a recommended
> new orchestration stack. The last recorded release checks are from
> 2026-08-07. The code defaults to `claude-fable-5` with `claude-opus-5` as its
> fallback; the release records no exact Claude, Codex or Grok CLI versions.
> Passing the offline tests does not test those models or live provider calls.
>
> **Execution limits and evidence checks are not sandboxing.** They apply to
> work routed through the adapters. The orchestrator can run shell commands;
> evidence files and model claims are not proof of correctness. External
> adapters and vendor CLIs must enforce filesystem and tool restrictions.
> Read [docs/security.md](docs/security.md) before use.
>
> Chris moved to [Pi](https://github.com/earendil-works/pi) with
> [T3 Code](https://github.com/pingdotgg/t3code), both public MIT projects.
> These are alternatives to investigate, not a tested replacement for this
> launcher's evidence contract. No public drop-in migration or implementation
> of the required external adapters is provided here. Provider-plan
> compatibility remains your responsibility; the
> [terms review](docs/provider-terms-review.md) records August 2026 findings,
> not current legal clearance.

An evidence-first launcher and orchestration contract for bounded,
cross-vendor work. A supervising agent or human operator can invoke it to start
one Claude Code session as the orchestrator. That session may decompose a hard
task and dispatch a small number of external workers through other vendors'
official CLIs. The launcher then checks result structure, worker evidence
paths, and consistency of reported fields before it may report success.
Validation-item evidence strings are not opened or re-run.

The launcher checks configured worker limits and looks for contradictions
between the reported outcome and recorded evidence. It cannot establish that
an arbitrary model claim is true.

---

## What this is

`evidence-first-orchestrator` is a launcher plus an agent skill definition and
an orchestration contract:

```
supervising agent or human operator
              │
              ▼
efo-orchestrate              ← this repo: launcher, caps, evidence, validation
        │  spawns one Claude Code session as the orchestrator
        ▼
 Claude orchestrator ("Fable" lane)
        │  dispatches workers only through slot-controlled adapters
        ├── efo-codex-leg  --lane reader|writer  →  codex-leg   → OpenAI Codex CLI
        └── efo-grok-leg   --lane reader|writer  →  grok-leg    → xAI Grok CLI
                │
                ▼
        efo_slot_controller.py ← job-wide concurrency + cumulative node caps
```

The launcher records a per-run **job directory** of inspectable evidence.
The contract asks workers to put their evidence there too. The expected contents
are the brief, the contract, the exact argv, per-attempt streams, slot
lifecycle events, per-worker streams and artifacts, metrics, the raw model
result, the normalized result, and the list of validation errors.

## Why it exists

The launcher targets three failure modes with code checks. The contract
also asks for independent verification, which remains a prompt instruction:

| Failure mode | Mechanism |
| --- | --- |
| Unbounded fan-out burns quota and clobbers files | A separate slot controller enforces concurrency, a writer cap and a cumulative node cap for workers using the adapters. These are not token budgets or a sandbox. |
| Agents claim success they cannot support | The launcher re-derives fan-in counts, checks cited worker evidence paths and deterministically downgrades a success claim contradicted by its own validation items. It does not independently re-run the claimed checks. |
| A retry silently repeats side effects | Cross-model fallback requires recorded slot state with zero worker starts and a tool-use stream containing only `Read`/`Glob`/`Grep`. Unknown or malformed evidence blocks replay. This assumes the trace and tools are trustworthy. |
| An implementer grades its own homework | The contract asks for a bounded cross-vendor refutation pass and one central validation gate. The launcher does not independently enforce who performed them. |

## Core concepts

**Reader and writer lanes.** Every external worker declares `--lane reader` or
`--lane writer`. The in-repository adapters reject recognized writable modes
on reader lanes; the user-supplied wrapper and vendor CLI must enforce the
actual sandbox. Writers are capped separately and much lower than total
concurrency (default 2), because concurrent writers are the thing that actually
corrupts a worktree.

**Three independent caps.** `--max-workers` bounds *simultaneous* workers
across all vendors, `--max-writers` bounds simultaneous writers, and
`--max-nodes` bounds *cumulative starts* over the whole run. Graph size is not
concurrency. `--max-writers 0` mechanically prevents writer-lane starts; it is
not a substitute for filesystem confinement of reader processes.

**Evidence artifacts.** Workers must write streams and final artifacts under
`$EFO_ORCHESTRATION_JOB_DIR`. The launcher rejects cited worker evidence paths
that are missing, empty or outside the job directory, and rejects duplicate stream paths. It does not
require artifact paths to be unique or establish that the contents are true.

**Checked fallback.** If the primary model reports a quota, credit,
overload, or availability error, the launcher may retry once on a fallback
model, but only when recorded slot state and tool use pass its replay checks.
Under `--resume` it never retries across models; it returns `blocked` instead.

**Deterministic result normalization.** A result that says `completed` while
any validation item says `failed` is not merely flagged: `final.json` is
rewritten to the normalized status, the raw model claim is preserved
separately in `final-raw.json`, and the process exits non-zero. Normalization
only ever downgrades.

## Requirements

The examples and default model IDs below belong to the August 2026 release.
Confirm model access and CLI compatibility separately before any live run.

You bring your own CLIs. This repository ships **no** vendor client and **no**
credentials.

| Component | Required | Notes |
| --- | --- | --- |
| Python 3.10+ and Bash | yes | Launcher, slot controller, adapters |
| Claude Code CLI (`claude`) | yes | The orchestrator session |
| `codex-leg` adapter | only for Codex workers | External program you supply; see [docs/adapters.md](docs/adapters.md) |
| `grok-leg` adapter | only for Grok workers | External program you supply; see [docs/adapters.md](docs/adapters.md) |
| Grok CLI (`grok`) | only for Grok workers | Invoked through `grok-leg` |

Every executable is resolved from an explicit environment override, the user
bin directory, or `PATH`, in that order. There are no hardcoded absolute paths
and no assumption about where a package manager lives.

> **`codex-leg` and `grok-leg` are contracts, not bundled code.** This repo
> defines the interface it expects and fails closed with an actionable
> diagnostic when an adapter is absent. It does not vendor anyone else's
> wrapper implementation. See [docs/adapters.md](docs/adapters.md) for the full
> contract and a minimal reference shape you can implement yourself.

### On provider terms

This project is intended for use with **official, authenticated vendor CLIs**.
It ships no credentials and is not a proxy or relay. It does not verify that a
chosen executable is official, or that an account permits a particular use.

Automated, headless, or non-interactive invocation may be restricted or
prohibited depending on the provider and the specific plan. You must verify
your own plan's terms before running this project. Silence in a provider's
documentation is not permission.

The reviewed official sources and the limits of that review are recorded in
[docs/provider-terms-review.md](docs/provider-terms-review.md). That document
is a good-faith engineering review, not legal advice. If a provider's terms
conflict with anything described here, the provider's terms win.

`efo-preflight` will not pass until you set `EFO_PROVIDER_TERMS_ACK=1`. That
gate records your acknowledgement; it cannot and does not verify compliance.
The launcher does not enforce this gate itself; run preflight separately.

## Install for existing users

```bash
git clone https://github.com/ax0s-io/evidence-first-orchestrator.git
cd evidence-first-orchestrator

# 1. Read docs/provider-terms-review.md, decide whether your own plan permits
#    automated CLI invocation, then acknowledge that you have done so.
export EFO_PROVIDER_TERMS_ACK=1

# 2. Check that your environment can actually run a job.
./scripts/efo_preflight.py

# 3. Link the launcher and adapters onto PATH.
./scripts/install.sh                     # or: ./scripts/install.sh --prefix /custom/bin
```

`install.sh` creates four symlinks in a directory you choose and ensures their
target scripts are executable. It writes nothing to your shell profile,
installs no packages, and contacts no network. Full detail in
[docs/setup.md](docs/setup.md).

The root [VERSION](VERSION) file is the release source of truth. After
installation, confirm the installed launcher with:

```bash
efo-orchestrate --version
```

For version 0.1.0 this prints `evidence-first-orchestrator 0.1.0`.

## Run a task

```bash
efo-orchestrate --cwd /absolute/path/to/worktree <<'BRIEF'
Add retry-with-backoff to the HTTP client in src/net/, keep the public API
unchanged, and prove it with tests. Do not touch anything outside src/net/.
Acceptance: `make test` passes and a new test covers the backoff schedule.
BRIEF
```

Widen the graph explicitly when a task earns it:

```bash
efo-orchestrate --cwd /abs/worktree \
  --max-workers 8 --max-writers 2 --max-nodes 24 <<'BRIEF'
...
BRIEF
```

The launcher prints one compact JSON object and writes full evidence under the
run root (default `$HOME/.efo/orchestration-runs/<timestamp>-<id>/`, override
with `EFO_ORCHESTRATION_RUN_ROOT` or `--job-dir`):

```
brief.md  contract.md  command.json  limits.json  result-schema.json  session-id
claude-fable-stream.jsonl     claude-fable-stderr.log      (the primary attempt)
claude-opus-stream.jsonl      claude-opus-stderr.log       (only if fallback ran)
.efo-slots/events.jsonl     .efo-slots/state.json
<worker streams and artifacts written by the orchestrator>
final-raw.json  final.json  final-validation-errors.json
orchestration-metrics.json   meta.json
```

Read `meta.json` first: it carries the overall status, per-attempt model and
usage evidence, the normalization record, and the validation error list.

An illustrative, not recorded, end-to-end example is in [examples/example-brief.md](examples/example-brief.md).

## Documentation

| Document | What's in it |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Process model, caps, lanes, evidence layout, validation pipeline, fallback state machine |
| [docs/security.md](docs/security.md) | Trust boundaries, threat model, what is and is not defended |
| [docs/adapters.md](docs/adapters.md) | The `claude`, `codex-leg`, and `grok-leg` external contracts |
| [docs/setup.md](docs/setup.md) | Install, configuration variables, preflight |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Diagnostics by symptom |
| [docs/provider-terms-review.md](docs/provider-terms-review.md) | Good-faith review of official provider terms sources |
| [docs/provenance.md](docs/provenance.md) | Provenance audit for the public release |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting, supported versions, and scope |
| [CONTRIBUTING.md](CONTRIBUTING.md) | DCO, licensing, tests, and review posture |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [SKILL.md](SKILL.md) | Agent skill definition |
| [references/orchestration-contract.md](references/orchestration-contract.md) | The system prompt appended to the orchestrator session |
| [references/result-schema.json](references/result-schema.json) | The enforced final-result schema |

## Tests

```bash
./tests/run-tests.sh
```

The suite uses fake CLI stubs and makes no model calls or provider requests.
Some concurrency assertions depend on timing. Run it before proposing a
change, but do not treat a pass as proof of live provider compatibility.

## Attribution and independence

See [ATTRIBUTION.md](ATTRIBUTION.md). Developed by **Aaron Dyson** and
**Chris Blaschke** at **ax0s**; both authors approved the listed attribution on
2026-08-06.

This is an **independent community integration**. It is not affiliated with,
sponsored by, or endorsed by Anthropic, OpenAI, or xAI. All
product names and trademarks belong to their respective owners and are used
only to describe interoperability.

## License and contributing

The code is licensed under the [MIT License](LICENSE), approved by both named
authors on 2026-08-06. Contributions use inbound=outbound MIT licensing, require
DCO sign-off on every commit, and require no CLA. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the full policy.

## Support

Aaron Dyson and Chris Blaschke maintain this small project on a best-effort
basis. There is no SLA or guaranteed response time, and maintainership does not
imply a commitment to accept contributions. Report exploitable security issues
privately as described in [SECURITY.md](SECURITY.md).
