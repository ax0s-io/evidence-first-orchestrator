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

These checks apply when work goes through the provided launcher and adapters.
They do not prevent an orchestrator with shell access from bypassing them.

**Concurrency and graph size.** `efo_slot_controller.py` is a distinct
process holding a file-locked state file. It enforces simultaneous workers
(`--max-workers`), simultaneous **writers** (`--max-writers`), and cumulative
starts (`--max-nodes`) across both vendors. On corrupt or unreadable state it
fails closed — it refuses to start work rather than reopening the cap. Stale
holders whose process is gone are pruned, so a crash cannot permanently wedge
the job; a live holder is never pruned.

**Lane discipline.** Every worker declares reader or writer. The in-repository
adapters inspect recognized sandbox/profile flags and reject explicit writable
modes on a reader lane. They do not create a filesystem sandbox and cannot
guarantee the defaults of a user-supplied wrapper. `--max-writers 0` makes
writer-lane starts mechanically impossible, but does not itself confine reader
processes.

**Environment narrowing.** The orchestrator child gets an allowlisted
environment. Provider API-key variables are not forwarded. This preserves the
intended authenticated-CLI route and modestly reduces credential exposure. It
is not a containment mechanism: a shell tool can read your files.

**Brief confidentiality from process listings.** Briefs go over stdin, never
argv, so the task text is not visible in another process's `ps` output.

**Job directory permissions.** The run directory is created `0700` and must not
already exist.

**Evidence integrity.** Cited worker streams and artifacts must exist, be
non-empty, and live **inside** the job directory. Stream paths must be unique;
artifact paths are not checked for uniqueness. Contents remain untrusted. A
result citing `/etc/passwd` or a nonexistent file as worker evidence is rejected.
Validation-item `evidence` fields need only be nonempty strings. The launcher
does not open those strings as files or re-run the validation commands.

**Result integrity.** A success claim contradicted by its own validation items
is deterministically downgraded, not merely annotated. See
[docs/architecture.md](architecture.md#result-validation-and-normalization).

**Fallback after recorded-state and trace checks.** Cross-model retry is
permitted when the recorded slot state and events show no started workers or
remaining holders, and the parsed trace shows no potentially mutating tools.
Only `Read`/`Glob`/`Grep` are allowed. `Bash`, `Edit`, `Write`, `Agent`,
`Workflow`, an unknown tool name, or malformed/unreadable evidence block the
retry. Empty event and trace files can pass these checks. Trace completeness
and truthful tool behavior are assumptions, not guarantees of these checks.
Under `--resume`, cross-model retry is disabled outright.

**Process-group cleanup.** Children are started in their own session and killed
by process group on stall, timeout, or signal, with escalation to `SIGKILL`.
This cleans up members that remain in that process group; it is not a defense
against a hostile process that deliberately creates a new session or otherwise
escapes the group.

## What is NOT defended against

Be honest with yourself about these before running it.

- **A malicious or compromised model with tool access.** The orchestrator can
  run shell commands in the task cwd. If it decides to do something harmful
  there, nothing here stops it. Sandboxing is the vendor CLI's job; this
  project only bounds *how many* workers run and *which lane* they hold.
- **Prompt injection.** The user brief, repository text, file contents, tool
  output, web pages, and worker results are untrusted input that reaches a
  model. They are data, not instructions that may expand the operator's
  authorization. The contract says so, but a prompt is not a security control.
  Assume injection can happen and choose the task cwd accordingly.
- **Reading anything the user can read.** No filesystem confinement is imposed
  by this project.
- **Credential theft by a tool-using model.** Your CLI session credentials live
  in your home directory and remain readable.
- **Resource consumption.** Caps bound concurrency and node count, not token
  consumption. A bounded graph can still consume substantial provider usage.
- **Correctness of worker output.** Cross-vendor refutation reduces
  same-model blind spots; it does not make results correct.
- **Supply chain of the vendor CLIs and adapters.** You are trusting whatever
  the user bin directory and `PATH` resolve. Preflight prints the resolved
  paths — look at them.

## Operator responsibilities

The orchestrator can execute tools requested by untrusted model output. Its
tool calls do not become trustworthy merely because the launcher later checks
its final claim.

1. **Choose the task cwd deliberately.** Prefer a dedicated worktree or a
   throwaway clone. Never point a writer-enabled run at a directory holding
   credentials, secrets, or unrelated production code.
2. **Commit or stash first.** Writers change files. Have a clean diff to
   review against.
3. **Set `--max-writers 0`** to block writer-lane starts, and use external
   filesystem confinement for read-only work. Neither the lane cap nor a brief
   saying "don't edit" prevents arbitrary writes.
4. **Review the diff.** Passing tests are evidence, not proof.
5. **Read `meta.json`** — specifically `status`, `final_validation_errors`, the
   normalization record, and `metrics_summary` — before believing a summary.
6. **Comply with provider terms.** Automated, headless, or non-interactive use
   may be restricted or prohibited by a provider or specific plan. Verify your
   own terms before running; silence in provider documentation is not
   permission. The review in
   [provider-terms-review.md](provider-terms-review.md) is a good-faith
   engineering review, not legal advice. Provider terms win.
7. **Treat non-interactive approval as a deliberate risk decision.** The Grok
   approval shim allows the worker model to run allowed tools without asking.
   Its short deny list is not a general command filter, and the sandbox,
   profile, and `--cwd` restrictions are not a security boundary against a
   hostile model. Enable that path only after accepting its risk for the
   selected worktree; see [adapters.md](adapters.md#the-approval-shim).

## Reporting a vulnerability

Use the private reporting process in [SECURITY.md](../SECURITY.md). Do not file
a public issue for an exploitable vulnerability.
