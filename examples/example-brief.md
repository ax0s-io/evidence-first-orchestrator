# Example: a bounded multi-vendor run

A worked example of what a good brief looks like, what the orchestrator does
with it, and how to read the evidence afterward.

## The task

> A Python service has an HTTP client with no retry logic. Add
> retry-with-backoff, keep the public API unchanged, and prove it.

## 1. Prepare an isolated worktree

Never point a writer-enabled run at your main checkout.

```bash
git -C ~/src/myservice worktree add /tmp/wt-retry -b feature/http-retry
cd /tmp/wt-retry && git status --porcelain      # must be clean
```

## 2. Write the brief

A brief is a contract, not a wish. State the goal, the exact files in scope,
what must not change, the acceptance criteria, and the authorization boundary.

```bash
efo-orchestrate --cwd /tmp/wt-retry \
  --max-workers 4 --max-writers 1 --max-nodes 10 <<'BRIEF'
GOAL
Add retry-with-backoff to the HTTP client in src/myservice/http/client.py.

IN SCOPE
  src/myservice/http/client.py
  src/myservice/http/retry.py        (new)
  tests/test_http_retry.py           (new)

OUT OF SCOPE — do not modify
  The public signature of HttpClient.request(); any other package; any
  dependency pin; any CI configuration.

REQUIREMENTS
- Retry only idempotent methods (GET, HEAD, PUT, DELETE) and only on
  connection errors, timeouts, 429, and 5xx.
- Exponential backoff with full jitter, capped at 30s, max 4 attempts.
- Honour Retry-After when present, preferring it over computed backoff.
- Total time bounded by the caller's existing timeout — never exceed it.
- Retries and final failures must be observable through the existing logger.

ACCEPTANCE
- `python -m pytest tests/ -q` passes with zero failures.
- New tests cover: the backoff schedule, the Retry-After path, the
  non-idempotent-method skip, and the max-attempts exit.
- `git diff --stat` touches only the in-scope files.

AUTHORIZATION
Edit files in this worktree only. Do NOT commit, push, tag, install packages,
or make network calls.
BRIEF
```

Why these caps: one writer, because a single file set is being edited and
concurrent writers on overlapping files is the failure mode that destroys work.
Four workers, because the reader-lane scouting and verification can overlap.
Ten nodes, because this needs roughly six workers with retry headroom.

## 3. What the orchestrator does

A sensible graph for this task, in waves:

| Wave | Worker | Vendor | Lane | Job |
| --- | --- | --- | --- | --- |
| 1 | `scout-client` | codex | reader | Map the client, its timeout handling, logger, and existing tests |
| 1 | `scout-conventions` | grok | reader | Find retry/backoff patterns already used elsewhere in the repo |
| 2 | `impl-retry` | codex | **writer** | Implement to spec, using wave-1 findings |
| 3 | `verify-behavior` | grok | reader | Independently read the diff and run the suite; refute the claims |
| 3 | `verify-scope` | grok | reader | Confirm the diff touches only in-scope files |

Wave 1 runs concurrently (two readers). Wave 2 is a single writer. Wave 3 is
the **cross-vendor refutation pass** — a different vendor than the implementer,
because an implementer never certifies its own work. Then the orchestrator runs
the authoritative gate itself: per-worker test results are advisory, the
central run is the evidence.

Every worker writes its stream and final artifact under
`$EFO_ORCHESTRATION_JOB_DIR`, which is what makes the result checkable.

## 4. Read the result

```bash
JOB=$(jq -r .job_dir <<<"$LAUNCHER_OUTPUT")

jq '{status, reported_status, normalized_status, result_normalization,
     final_validation_errors, metrics_summary}' "$JOB/meta.json"
jq '{status, fan_in, validation, changed_files}' "$JOB/final.json"
```

A healthy run:

```json
{
  "status": "completed",
  "fan_in": { "expected": 5, "received": 5, "complete": true },
  "validation": [
    { "command": "python -m pytest tests/ -q",
      "status": "passed",
      "evidence": "34 passed in 2.11s (exit 0)" },
    { "command": "git diff --stat",
      "status": "passed",
      "evidence": "3 files changed, 148 insertions(+), 6 deletions(-)" }
  ],
  "changed_files": [
    "src/myservice/http/client.py",
    "src/myservice/http/retry.py",
    "tests/test_http_retry.py"
  ]
}
```

An unhealthy one, showing normalization at work:

```json
{ "reported_status": "completed_with_warnings",
  "normalized_status": "failed",
  "result_normalization": {
    "applied": true,
    "reasons": ["validation item 1 reports status 'failed'"] } }
```

The orchestrator claimed partial success while reporting a failing check. The
launcher downgraded it, `final.json` carries `failed`, `final-raw.json`
preserves the original claim, and the process exits non-zero.

## 5. Review before you trust it

Green tests are evidence, not proof.

```bash
git -C /tmp/wt-retry diff
jq -r '.workers[] | [.id,.vendor,.role,.status,.stream] | @tsv' "$JOB/final.json"
```

Read the refutation worker's stream in particular — it is the part of the run
whose job was to disagree.

## Variations

**Read-only investigation.** Mechanically forbid edits; widen readers:

```bash
efo-orchestrate --cwd /tmp/wt-retry \
  --max-workers 8 --max-writers 0 --max-nodes 16 <<'BRIEF'
Explain how request timeouts propagate from HttpClient to the socket layer.
Cite file:line for every claim. Produce a report only — change nothing.
BRIEF
```

**Bounded follow-up.** Reuse the session instead of paying fresh-context cost:

```bash
efo-orchestrate --cwd /tmp/wt-retry --resume "$(cat "$JOB/session-id")" <<'BRIEF'
The Retry-After parser rejects the HTTP-date form. Fix it and extend the test.
Nothing else changes.
BRIEF
```

Cross-model fallback is disabled under `--resume`.

## Writing good briefs

- **Name the files.** "In scope" and "out of scope" beat any amount of prose.
- **Make acceptance mechanically checkable.** A command with an expected exit
  code is a criterion; "works well" is not.
- **State the authorization boundary explicitly.** Commits, pushes, installs,
  and network calls are off unless you turn them on.
- **Set caps to the shape of the work,** not to the maximum allowed. One writer
  for one file set.
- **Send context, not transcripts.** Distilled findings and paths, never a
  pasted conversation.
