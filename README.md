# prime-fable-orchestrator

> **Status: draft. Not released.** Both authors approved the MIT license and
> attribution on 2026-08-06. Publication remains blocked on the remaining items
> in [PUBLICATION_CHECKLIST.md](PUBLICATION_CHECKLIST.md).

A bounded, evidence-first orchestration skill for [Prime Agent](https://github.com/PrimeIntellect-ai).
It lets a top-level Claude Code session decompose a hard task, dispatch a small
number of external workers to **other vendors' official CLIs**, and return a
structured result that the launcher independently validates against recorded
evidence before it is allowed to claim success.

The point is not "run many agents." The point is that a multi-agent run should
be **mechanically bounded** and **unable to lie about its own outcome**.

---

## What this is

`prime-fable-orchestrator` is a Prime Agent skill plus a launcher process:

```
Prime Agent (thin supervisor)
        │
        ▼
prime-fable-orchestrate            ← this repo: launcher, caps, evidence, validation
        │  spawns one Claude Code session as the orchestrator
        ▼
 Claude orchestrator ("Fable" lane)
        │  dispatches workers only through slot-controlled adapters
        ├── prime-codex-leg  --lane reader|writer  →  codex-leg   → OpenAI Codex CLI
        └── prime-grok-leg   --lane reader|writer  →  grok-leg    → xAI Grok CLI
                │
                ▼
        prime_slot_controller.py   ← job-wide concurrency + cumulative node caps
```

Everything the run does lands in a per-run **job directory** as inspectable
evidence: the brief, the contract, the exact argv, per-attempt streams, slot
lifecycle events, per-worker streams and artifacts, metrics, the raw model
result, the normalized result, and the list of validation errors.

## Why it exists

Multi-agent orchestration tends to fail in four specific ways. This repo
targets each one with a mechanism rather than a prompt:

| Failure mode | Mechanism |
| --- | --- |
| Unbounded fan-out burns quota and clobbers files | A separate slot-controller process enforces job-wide concurrency, a **separate writer cap**, and a cumulative node cap. Caps are enforced in the adapter, not requested in a prompt. |
| Agents claim success they cannot support | The launcher re-derives fan-in counts, checks every cited evidence path exists and is non-empty and inside the job directory, and **deterministically downgrades** a success claim contradicted by its own validation items. |
| A retry silently repeats side effects | Cross-model fallback runs only after proving from slot state and the tool-use stream that the first attempt started zero workers and used only `Read`/`Glob`/`Grep`. Anything else fails closed. |
| An implementer grades its own homework | The contract requires a bounded cross-vendor refutation pass and one central validation gate owned by the orchestrator. |

## Core concepts

**Reader and writer lanes.** Every external worker declares `--lane reader` or
`--lane writer`. Readers may not use a writable sandbox. Writers are capped
separately and much lower than total concurrency (default 2), because
concurrent writers are the thing that actually corrupts a worktree.

**Three independent caps.** `--max-workers` bounds *simultaneous* workers
across all vendors, `--max-writers` bounds simultaneous writers, and
`--max-nodes` bounds *cumulative starts* over the whole run. Graph size is not
concurrency. `--max-writers 0` gives a mechanically read-only run.

**Evidence artifacts.** Workers must write streams and final artifacts under
`$PRIME_ORCHESTRATION_JOB_DIR`. The launcher rejects a final result whose
worker evidence paths are missing, empty, duplicated, or outside the job
directory — so "I ran a verifier" is checkable.

**Safe no-side-effect fallback.** If the primary model reports a quota, credit,
overload, or availability error, the launcher may retry once on a fallback
model — but only after proving the first attempt was side-effect free. Under
`--resume` it never retries across models; it returns `blocked` instead.

**Deterministic result normalization.** A result that says `completed` while
any validation item says `failed` is not merely flagged: `final.json` is
rewritten to the normalized status, the raw model claim is preserved
separately in `final-raw.json`, and the process exits non-zero. Normalization
only ever downgrades.

## Requirements

You bring your own CLIs. This repository ships **no** vendor client and **no**
credentials.

| Component | Required | Notes |
| --- | --- | --- |
| Python 3.10+ and Bash | yes | Launcher, slot controller, adapters |
| Claude Code CLI (`claude`) | yes | The orchestrator session |
| `codex-leg` adapter | only for Codex workers | External program you supply — see [docs/adapters.md](docs/adapters.md) |
| `grok-leg` adapter | only for Grok workers | External program you supply — see [docs/adapters.md](docs/adapters.md) |
| Grok CLI (`grok`) | only for Grok workers | Invoked through `grok-leg` |

Every executable is resolved from `PATH`, or from an explicit environment
variable override. There are no hardcoded absolute paths and no assumption
about where your home directory or your package manager lives.

> **`codex-leg` and `grok-leg` are contracts, not bundled code.** This repo
> defines the interface it expects and fails closed with an actionable
> diagnostic when an adapter is absent. It does not vendor anyone else's
> wrapper implementation. See [docs/adapters.md](docs/adapters.md) for the full
> contract and a minimal reference shape you can implement yourself.

### On provider terms

This project drives **official, authenticated vendor CLIs** using whatever
entitlement you have already been granted, exactly as if you had typed the
command yourself. It is not a proxy, not a relay, and not a way to obtain
capacity you are not entitled to.

- You are responsible for reading and complying with the terms of service,
  acceptable use policy, and automation rules of every provider whose CLI you
  point this at.
- Automated or headless invocation may be restricted or prohibited under some
  plans. Check before you run it.
- Nothing here should be read as a claim that CLI routing avoids API fees,
  circumvents rate limits, or grants entitlements you do not have. If a
  provider's terms conflict with a workflow described here, the provider's
  terms win — don't run it.

## Install (draft)

```bash
git clone <this-repo> prime-fable-orchestrator
cd prime-fable-orchestrator

# 1. Check that your environment can actually run a job.
./scripts/prime_preflight.py

# 2. Link the launcher and adapters onto PATH.
./scripts/install.sh                     # or: ./scripts/install.sh --prefix /custom/bin
```

`install.sh` only creates symlinks into a directory you choose. It writes
nothing to your shell profile, installs no packages, and contacts no network.
Full detail in [docs/setup.md](docs/setup.md).

## Run a task

```bash
prime-fable-orchestrate --cwd /absolute/path/to/worktree <<'BRIEF'
Add retry-with-backoff to the HTTP client in src/net/, keep the public API
unchanged, and prove it with tests. Do not touch anything outside src/net/.
Acceptance: `make test` passes and a new test covers the backoff schedule.
BRIEF
```

Widen the graph explicitly when a task earns it:

```bash
prime-fable-orchestrate --cwd /abs/worktree \
  --max-workers 8 --max-writers 2 --max-nodes 24 <<'BRIEF'
...
BRIEF
```

The launcher prints one compact JSON object and writes full evidence under the
run root (default `$HOME/.prime/orchestration-runs/<timestamp>-<id>/`, override
with `PRIME_ORCHESTRATION_RUN_ROOT` or `--job-dir`):

```
brief.md  contract.md  command.json  limits.json  result-schema.json  session-id
claude-fable-stream.jsonl     claude-fable-stderr.log      (the primary attempt)
claude-opus-stream.jsonl      claude-opus-stderr.log       (only if fallback ran)
.prime-slots/events.jsonl     .prime-slots/state.json
<worker streams and artifacts written by the orchestrator>
final-raw.json  final.json  final-validation-errors.json
orchestration-metrics.json   meta.json
```

Read `meta.json` first: it carries the overall status, per-attempt model and
usage evidence, the normalization record, and the validation error list.

A worked end-to-end example is in [examples/example-brief.md](examples/example-brief.md).

## Documentation

| Document | What's in it |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Process model, caps, lanes, evidence layout, validation pipeline, fallback state machine |
| [docs/security.md](docs/security.md) | Trust boundaries, threat model, what is and is not defended |
| [docs/adapters.md](docs/adapters.md) | The `claude`, `codex-leg`, and `grok-leg` external contracts |
| [docs/setup.md](docs/setup.md) | Install, configuration variables, preflight |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Diagnostics by symptom |
| [SKILL.md](SKILL.md) | The Prime Agent skill definition |
| [references/orchestration-contract.md](references/orchestration-contract.md) | The system prompt appended to the orchestrator session |
| [references/result-schema.json](references/result-schema.json) | The enforced final-result schema |

## Tests

```bash
./tests/run-tests.sh
```

The suite is deterministic, offline, and hermetic: it uses a fake CLI stub, so
it never calls a model, never opens a socket, and never spends quota. It is the
authoritative gate — run it before proposing any change.

## Attribution and independence

See [ATTRIBUTION.md](ATTRIBUTION.md). Developed by **Aaron Dyson** and
**Chris Blaschke** at **ax0s**; both authors approved the listed attribution on
2026-08-06.

This is an **independent community integration**. It is not affiliated with,
sponsored by, or endorsed by Prime Intellect, Anthropic, OpenAI, or xAI. All
product names and trademarks belong to their respective owners and are used
only to describe interoperability.

## License and contributing

The code is licensed under the [MIT License](LICENSE), approved by both named
authors on 2026-08-06. The repository remains a private publication draft while
provider-terms, naming, security-contact, and release checks are completed.
Contributions are not open yet; see
[PUBLICATION_CHECKLIST.md](PUBLICATION_CHECKLIST.md).
