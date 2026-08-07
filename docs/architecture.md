# Architecture

Three processes, one job directory, and a validation gate that does not trust
the model it just ran.

```
efo-orchestrate  (launcher)
│  creates the job dir, writes brief/contract/schema/limits,
│  spawns ONE Claude Code session, supervises it, validates the result
│
├── claude -p ... --json-schema ... --append-system-prompt <contract>
│   │  the orchestrator session; brief arrives on stdin
│   │
│   ├── efo-codex-leg --lane reader|writer -- <codex-leg args>
│   └── efo-grok-leg  --lane reader|writer  --cwd DIR ...
│         │  adapter: validates lane + argument shape, then
│         └── efo_slot_controller.py run --vendor V --lane L -- <adapter>
│               │  blocks until a slot is available; logs queued/started/finished
│               └── codex-leg | grok-leg   (external, yours)
│
└── efo_metrics.py — reduces slot events into run metrics
```

## Components

**`scripts/efo_orchestrate.py` — the launcher.** Owns the job
directory, argument and cap validation, adapter resolution, the narrowed child
environment, the supervision loop (stall + wall-clock, process-group kill), the
fallback state machine, result validation and normalization, and the final
`meta.json`.

**`scripts/efo_slot_controller.py` — the cap enforcer.** A separate process
per worker. Takes a file lock over `.efo-slots/state.json`, waits until the
worker's lane has room, records `started`, execs the adapter as a process-group
leader, then records `finished` and releases. Because the cap lives in a lock
file held by a process outside the model's control, no prompt can raise it.

**`scripts/efo_codex_leg.sh`, `scripts/efo_grok_leg.sh` — the adapters.**
Thin argument-validating shims. They strip `--lane`, verify the job directory,
reject argument shapes that would escape the intended sandbox, and forward
everything else verbatim to the external `*-leg` program through the slot
controller. See [adapters.md](adapters.md).

**`scripts/efo_metrics.py` — the reducer.** Turns the slot event log into
node counts, peak concurrency (total and writers), and queue-wait statistics.
It reports `degraded` when the event log is torn or internally inconsistent,
and a degraded reduction is itself a validation error.

**`references/orchestration-contract.md`** is appended to the orchestrator's
system prompt. **`references/result-schema.json`** is passed as
`--json-schema`, with `workers.maxItems` patched to the run's `--max-nodes`.

## Caps and lanes

Three orthogonal limits, all enforced in the slot controller:

| Flag | Bounds | Default | Range |
| --- | --- | --- | --- |
| `--max-workers` | simultaneous workers, both vendors | 4 | 1–12 |
| `--max-writers` | simultaneous **writer-lane** workers | 2 | 0–max-workers |
| `--max-nodes` | **cumulative** worker starts for the run | 12 | max-workers–100 |

`--max-workers` bounds width; `--max-nodes` bounds total spend. A run with
`--max-workers 4 --max-nodes 24` may execute 24 workers, never more than 4 at
once. `--max-writers 0` makes writer lanes impossible while readers still run.

Lane semantics: the in-repository adapter rejects recognized writable modes
when a **reader** requests them. The user-supplied external adapter and vendor
CLI must enforce the sandbox itself; the lane label is not filesystem
confinement. A **writer** may edit files, which is why its cap is separate and
low — concurrent writers on overlapping files is the failure mode that
actually destroys work. The contract additionally requires concurrent workers
to own disjoint file sets, with shared config and the central validator
reserved to the orchestrator.

Failure behavior is closed, not open: corrupt or unreadable slot state refuses
new starts rather than assuming zero. Stale holders — recorded holders whose
process no longer exists — are pruned so a crash cannot permanently wedge the
job, but a live holder is never pruned.

## The job directory

Created `0700`, must not already exist, and is the only place workers may write
evidence. It is passed to the orchestrator as `$EFO_ORCHESTRATION_JOB_DIR`
and via `--add-dir`.

| File | Contents |
| --- | --- |
| `brief.md` | The task brief as received |
| `contract.md` | The exact contract text appended to the system prompt |
| `result-schema.json` | The schema as enforced for this run |
| `limits.json` | The three caps |
| `command.json` | Redacted argv, exported env, fallback policy, per-attempt records |
| `session-id` | Session id, for `--resume` |
| `claude-<model>-stream.jsonl` / `-stderr.log` | One pair per attempt, byte-for-byte, named for the model that ran — `claude-fable-*` for the default primary, `claude-opus-*` for the default fallback |
| `.efo-slots/state.json` | Live cap state |
| `.efo-slots/events.jsonl` | Append-only slot lifecycle log |
| *worker streams/artifacts* | Written by the orchestrator, one path per worker |
| `final-raw.json` | The model's result exactly as claimed |
| `final.json` | The **normalized** result — what consumers should read |
| `final-validation-errors.json` | Every invariant violation found |
| `orchestration-metrics.json` | Reduced slot metrics |
| `meta.json` | Overall status, attempts, models, usage, normalization record |

The brief travels on **stdin**, never argv, so task text is not exposed in
process listings.

## Result validation and normalization

The orchestrator returns a structured result. The launcher treats it as a
**claim** and checks it against evidence it recorded itself.

### Structural and semantic checks

- Exact top-level field set; no extras, no omissions.
- `fan_in.expected` must equal the worker record count; `fan_in.received` must
  equal the number of workers with status `completed`; `complete` must equal
  `expected == received`. A success status requires `complete == true` and no
  failed, stalled, or skipped worker.
- Every worker id is unique; every stream path is unique.
- Completed workers must cite both a stream and an artifact, and each cited
  path must exist, be non-empty, and resolve **inside** the job directory.
- Worker record count must not exceed `--max-nodes`.
- `validation` must be a non-empty array of well-formed items.
- A success status requires at least one `passed` validation item.

### Cross-checks against independently recorded evidence

- A success claiming workers while the slot controller recorded **zero**
  started nodes is rejected. You cannot invent workers.
- Claiming more completed workers than the metrics recorded is rejected.
- A `degraded` metrics reduction is a validation error.

### Deterministic normalization

Rejecting a bad claim is not enough — an artifact on disk still asserting
success is itself a defect. So the launcher writes the raw claim to
`final-raw.json` and a **normalized** result to `final.json`.

Normalization is a pure function that only ever **downgrades**, taking the
maximum severity over `completed < completed_with_warnings < blocked < failed`:

| Rule | Condition (only when the claim is a success status) | Floor |
| --- | --- | --- |
| R1 | any validation item is `failed` | `failed` |
| R2 | `validation` is missing, empty, not a list, or contains a malformed item | `failed` |
| R3 | any validation item is `not_run` | `completed_with_warnings` |
| R4 | fan-in is incomplete | `completed_with_warnings` |
| R5 | any worker is not `completed` | `completed_with_warnings` |

R2 is fail-closed on purpose: a run that cannot verify its own validation list
has not verified anything. Whenever normalization fires, its reasons are
appended to the validation errors, which forces a non-zero exit — so a
downgraded run can never be reported as a success by exit code either.

`meta.json` records `reported_status`, `normalized_status`, and the full
`result_normalization` record, so the disagreement between what the model
claimed and what the evidence supports is preserved rather than erased.

## Availability fallback

The launcher may retry once on a fallback model, and only for an **explicit
availability condition** — quota exhausted, credits exhausted, overloaded, or
model unavailable — classified from the result event and stderr by narrow
patterns. An ordinary task failure never retries.

Before retrying, it must **prove the first attempt had no side effects**:

1. `.efo-slots/state.json` parses, has the expected shape, records
   `nodes_started == 0`, and holds no holders.
2. `.efo-slots/events.jsonl` parses fully and contains no `started` event.
3. The entire first-attempt stream parses, and every tool use in it is `Read`,
   `Glob`, or `Grep`.

Any `Bash`, `Edit`, `Write`, `NotebookEdit`, `Agent`, `Workflow`, unknown tool
name, or unreadable/malformed evidence blocks the retry. The run returns
`blocked` with the exact reason and the next action, rather than risking a
duplicated side effect.

Under `--resume`, cross-model retry is disabled outright: a session started on
one model is never resumed as another. Both attempts stay inside one job with
distinct stream and stderr files, distinct session ids, and per-attempt model,
return-code, and usage evidence.

## Supervision

The child runs in its own session (`start_new_session=True`) so the whole
process group can be killed. A monitor loop tracks last-output time and kills
on `--stall-s` (default 1200) or `--timeout-s` (default 14400), escalating
`SIGTERM` → `SIGKILL` after a grace period, and reaping the group even if the
leader already exited. `SIGTERM`/`SIGINT`/`SIGHUP` handlers are installed
*before* the child is created, so no signal window can orphan it. Only parsed
terminal result events and a bounded stderr tail are held in memory; the full
streams live on disk.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Normalized status is `completed` or `completed_with_warnings` |
| 1 | Failed: bad return code, error result, or validation errors |
| 2 | Blocked (e.g. a refused fallback) |
| 96 | Killed by the stall watchdog |
| 124 | Killed by the wall-clock timeout |
| 128+n | Terminated by signal *n* |
