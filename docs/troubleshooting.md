# Troubleshooting

Start here every time:

```bash
./scripts/efo_preflight.py              # is the environment sane?
cat "$JOB/meta.json"                    # what did the run actually conclude?
cat "$JOB/final-validation-errors.json" # which invariant broke?
```

`$JOB` is the `job_dir` printed by the launcher.

---

## Startup failures

### `Claude CLI not found; set EFO_CLAUDE_BIN ...`

`claude` is in neither the user bin directory (`$XDG_BIN_HOME`, or
`$HOME/.local/bin` when unset) nor on `PATH`, and `EFO_CLAUDE_BIN` is unset.
Either install the Claude Code CLI or point the variable at it:

```bash
EFO_CLAUDE_BIN=/opt/tools/claude ./scripts/efo_preflight.py
```

### `EFO_<TOOL>_BIN does not name a usable executable: <value>`

The override is set but the target is missing, not a regular file, not
executable, or world-writable (or sits in a world-writable directory that has
no sticky bit — a sticky `/tmp` is accepted). This is
deliberately fatal — after an explicit override, silently falling back to
`PATH` would run a different binary than you asked for.

```bash
ls -l "$EFO_CODEX_LEG_BIN"; chmod 755 "$EFO_CODEX_LEG_BIN"
```

### `codex-leg not found` / `grok-leg not found`

These are **external programs you supply** — this repository does not ship
them. See [adapters.md](adapters.md) for the contract and a minimal shape.
Until one exists, that vendor's workers are unavailable; the rest still works.

### `--cwd is not a directory` / `--job-dir` already exists

The job directory must be new — the launcher never writes into an existing one,
so evidence can't be silently mixed between runs. Pass a fresh path.

### `--max-nodes N is outside the allowed range M..100`

`--max-nodes` must be at least `--max-workers`: you cannot allow more
simultaneous workers than total starts.

### `Task brief required on stdin or with --brief-file`

Nothing was piped in. Use a heredoc or `--brief-file`.

### `ModuleNotFoundError: efo_metrics` when run through a symlink

The launcher must add its own resolved directory to `sys.path`. If you see
this, you are on an old copy, or the symlink points somewhere the sibling
modules are not.

---

## Worker dispatch failures

### `efo-codex-leg: --lane reader|writer is required`

Every worker declares a lane. It must be space-separated (`--lane writer`);
`--lane=writer` is rejected so the argument parse cannot be ambiguous.

### `sandbox '<mode>' requires --lane writer`

A reader asked for a writable sandbox. Either make it a writer (and accept the
writer cap) or use a read-only sandbox.

### `EFO_ORCHESTRATION_JOB_DIR must be an existing directory`

An adapter was invoked outside a launcher-managed run. Adapters are only
callable from inside a job.

### `efo-grok-leg: explicit --cwd is required` / `must be narrower than ...`

The in-repository layer rejects a `--cwd` that resolves to `/` or exactly
`$HOME`; it does not prove that every other directory is narrow. Point `--cwd`
at the specific worktree, and rely on the user-supplied adapter for actual
filesystem confinement.

### `--sandbox off is forbidden` / `--profile full is forbidden`

These escape hatches are unavailable by design. If the work genuinely needs
them, it does not belong in a Grok worker on this path.

### Workers queue and never start

Expected when a cap is saturated — check `.efo-slots/events.jsonl` for
`queued` events without a matching `started`, and `orchestration-metrics.json`
for `queue.max_wait_s`. If nothing is running at all, look for a `denied` event
citing the cumulative node cap: the run has spent `--max-nodes`.

### Workers refuse to start after a crash

Slot state fails closed when it cannot be parsed. Inspect
`.efo-slots/state.json`. Stale holders whose process is gone are pruned
automatically; a corrupt file is not "repaired" by guessing. Start a new job.

---

## Result rejected

### `final result status normalized from 'X' to 'Y': ...`

The run claimed more than its evidence supported and was **downgraded**. The
reasons name the rule that fired:

| Reason mentions | Meaning | What to do |
| --- | --- | --- |
| a `failed` validation item | It said success while reporting a failing check | Read the item's `evidence`; the run genuinely did not pass |
| a malformed validation item | The validation list couldn't be verified, so it fails closed | The orchestrator emitted a bad item — usually a truncated or hand-edited result |
| `not_run` | Something was skipped | Decide whether the skipped check mattered |
| fan-in incomplete | Fewer results than dispatched | A worker failed or stalled — check its stream |
| a worker not `completed` | Same | Same |

`final-raw.json` preserves the original claim; `final.json` holds the
normalized one. The disagreement is intentional evidence, not corruption.

### `<field> does not exist` / `is empty` / `is outside the job directory`

The result cited evidence that isn't there. All worker streams and artifacts
must be written **under** `$EFO_ORCHESTRATION_JOB_DIR`, one stream path per
worker, and must be non-empty. This is what makes "I verified it" checkable.

### `reports N workers but no slot-controller node starts were recorded`

The result described workers that never ran through the slot controller. Either
they were fabricated, or something invoked a bare `codex-leg` / `grok-leg`
directly, bypassing the cap. Both are contract violations.

### `fan_in.expected does not equal worker record count`

The counts are self-inconsistent. `expected` must equal the number of worker
records; `received` must equal the number with status `completed`.

### `orchestration metrics degraded: ...`

The slot event log is torn or internally inconsistent — usually a hard kill
mid-write. Treat the metrics as unreliable; the streams are still intact.

---

## Run terminated

| Exit | Cause | Next step |
| --- | --- | --- |
| 96 | No output for `--stall-s` | Raise it only if a long silent step is genuinely expected; otherwise read the stream tail for where it hung |
| 124 | Wall clock exceeded `--timeout-s` | Split the task; a single run should not need hours |
| 128+n | Signal *n* | Usually your own Ctrl-C. The process group was cleaned up |
| 2 | Blocked | Read `fallback_blocked_reason` and `next_action` in `meta.json` |

## Fallback

### `automatic fallback refused: <detail>`

The primary hit an availability error, but the evidence could not prove that
the run had no side effects, so it was not replayed. Details map to:

- *slot state records N started node(s)* — workers already ran; replaying would
  duplicate them.
- *potentially mutating or unknown tool use observed: ...* — the attempt used a
  tool that may have changed something.
- *slot state cannot prove zero starts* / *stream is unreadable* /
  *line N is malformed* — evidence is untrustworthy, so it fails closed.

Inspect the stream and the working tree, then start a **fresh** run
deliberately if replay is safe.

### `automatic fallback is disabled for --resume`

A session is never resumed on a different model. Start a fresh run without
`--resume`.

### The fallback never triggers on a real quota error

Classification is deliberately narrow — only explicit quota, credit, overload,
and unavailability wording. A generic task failure must not trigger a retry. If
your provider's wording differs, that is a compatibility gap; capture the exact
stderr text from the primary attempt's `claude-<model>-stderr.log` (by default
`claude-fable-stderr.log`).

---

## Tests

### A concurrency test fails on a loaded machine

The suite is deterministic in logic but a few assertions involve timing.
Re-run on an idle machine before investigating. If it reproduces, the queue or
cleanup behavior genuinely changed.

### `tests/test_sanitization.py` fails

Some file reintroduced a personal name, an organization slug, or a hardcoded
home path. The failure message names file, line, and token. Author and
organization names are permitted **only** in `ATTRIBUTION.md`,
`PUBLICATION_CHECKLIST.md`, and `README.md`.

---

## Diagnostic recipes

```bash
# what did each attempt actually do?
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") | .name' \
  "$JOB/claude-fable-stream.jsonl" | sort | uniq -c

# worker lifecycle
jq -r '[.ts,.vendor,.lane,.event] | @tsv' "$JOB/.efo-slots/events.jsonl"

# the four things worth reading first
jq '{status,reported_status,normalized_status,result_normalization,
     final_validation_errors,metrics_summary}' "$JOB/meta.json"
```
