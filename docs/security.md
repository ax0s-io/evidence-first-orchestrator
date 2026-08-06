# Security model and trust boundaries

This document states plainly what this project defends against, what it does
not, and where the trust boundaries are. Read it before pointing the launcher
at anything you care about.

**Top-level framing:** this is an *orchestration harness for agents you have
already decided to run*. It reduces blast radius and makes outcomes auditable.
It is **not** a sandbox, **not** a security boundary against a hostile model,
and **not** a substitute for reviewing what the run changed.

---

## Trust boundaries

```
┌─ TRUSTED ───────────────────────────────────────────────┐
│ The operator (you)                                      │
│ The launcher process, slot controller, adapter scripts  │
│ Your authenticated CLI sessions and their credentials   │
└─────────────────────────────────────────────────────────┘
              │ brief (stdin), narrow allowlisted env
              ▼
┌─ SEMI-TRUSTED ──────────────────────────────────────────┐
│ The orchestrator model session                          │
│  - may run tools in the task cwd                        │
│  - is capped by the slot controller, not by its prompt  │
│  - its self-reported result is NOT trusted              │
└─────────────────────────────────────────────────────────┘
              │ worker briefs
              ▼
┌─ UNTRUSTED ─────────────────────────────────────────────┐
│ Worker models (Codex, Grok)                             │
│ Repository contents, file text, tool output, web pages  │
│ Anything a model produced, including all worker output  │
└─────────────────────────────────────────────────────────┘
```

The single most important line is the second one: **the orchestrator's own
final result is treated as an untrusted claim.** The launcher re-derives what
it can from evidence it recorded itself and rejects or downgrades claims that
do not hold up.

## What is enforced mechanically

These are properties a prompt cannot override, because a separate process
enforces them.

**Concurrency and graph size.** `prime_slot_controller.py` is a distinct
process holding a file-locked state file. It enforces simultaneous workers
(`--max-workers`), simultaneous **writers** (`--max-writers`), and cumulative
starts (`--max-nodes`) across both vendors. On corrupt or unreadable state it
fails closed — it refuses to start work rather than reopening the cap. Stale
holders whose process is gone are pruned, so a crash cannot permanently wedge
the job; a live holder is never pruned.

**Lane discipline.** Every worker declares reader or writer. A reader cannot
obtain a writable sandbox by argument shape: the adapter inspects the forwarded
sandbox/profile flags and refuses. `--max-writers 0` makes writer lanes
mechanically impossible for the whole run.

**Environment narrowing.** The orchestrator child gets an allowlisted
environment. Provider API-key variables are not forwarded. This is a
*correctness and cost* control — it stops a run from silently switching to a
metered API path — and a modest credential-exposure reduction. It is not a
containment mechanism: a shell tool can read your files.

**Brief confidentiality from process listings.** Briefs go over stdin, never
argv, so the task text is not visible in another process's `ps` output.

**Job directory permissions.** The run directory is created `0700` and must not
already exist.

**Evidence integrity.** Cited worker streams and artifacts must exist, be
non-empty, be unique per worker, and live **inside** the job directory. A
result citing `/etc/passwd` or a nonexistent file as evidence is rejected.

**Result integrity.** A success claim contradicted by its own validation items
is deterministically downgraded, not merely annotated. See
[docs/architecture.md](architecture.md#result-validation-and-normalization).

**Side-effect-free fallback only.** Cross-model retry requires proof from the
slot state *and* the full tool-use stream that the first attempt started zero
workers and used only `Read`/`Glob`/`Grep`. `Bash`, `Edit`, `Write`, `Agent`,
`Workflow`, an unknown tool name, or malformed/unreadable evidence all block
the retry. Under `--resume`, cross-model retry is disabled outright.

**Process-group cleanup.** Children are started in their own session and killed
by process group on stall, timeout, or signal, with escalation to `SIGKILL`, so
a detached descendant cannot outlive the run and start writing later.

## What is NOT defended against

Be honest with yourself about these before running it.

- **A malicious or compromised model with tool access.** The orchestrator can
  run shell commands in the task cwd. If it decides to do something harmful
  there, nothing here stops it. Sandboxing is the vendor CLI's job; this
  project only bounds *how many* workers run and *which lane* they hold.
- **Prompt injection.** Repository text, file contents, tool output, web pages,
  and worker results are untrusted input that reaches a model. The contract
  instructs the orchestrator to treat them as data, and instructions are not a
  security control. Assume injection can happen and choose the task cwd
  accordingly.
- **Reading anything the user can read.** No filesystem confinement is imposed
  by this project.
- **Credential theft by a tool-using model.** Your CLI session credentials live
  in your home directory and remain readable.
- **Cost.** Caps bound concurrency and node count, not tokens or dollars. A
  bounded graph can still be expensive.
- **Correctness of worker output.** Cross-vendor refutation reduces
  same-model blind spots; it does not make results correct.
- **Supply chain of the vendor CLIs and adapters.** You are trusting whatever
  the user bin directory and `PATH` resolve. Preflight prints the resolved
  paths — look at them.

## Operator responsibilities

1. **Choose the task cwd deliberately.** Prefer a dedicated worktree or a
   throwaway clone. Never point a writer-enabled run at a directory holding
   credentials, secrets, or unrelated production code.
2. **Commit or stash first.** Writers change files. Have a clean diff to
   review against.
3. **Set `--max-writers 0`** for anything that should be read-only. Do not rely
   on the brief saying "don't edit."
4. **Review the diff.** Passing tests are evidence, not proof.
5. **Read `meta.json`** — specifically `status`, `final_validation_errors`, the
   normalization record, and `metrics_summary` — before believing a summary.
6. **Comply with provider terms.** Automated and headless use may be
   restricted on some plans. Reviewing and complying is your responsibility,
   not this project's. Nothing here avoids fees, evades limits, or grants
   entitlements you do not have.
7. **Understand the Grok approval shim** before enabling Grok workers — see
   [docs/adapters.md](adapters.md#the-approval-shim).

## Reporting a vulnerability

This project is an unpublished draft with no security contact yet. See
[PUBLICATION_CHECKLIST.md](../PUBLICATION_CHECKLIST.md) item 7.
