---
name: evidence-first-orchestrator
description: Runs a complex task through a bounded multi-vendor orchestration graph using authenticated provider CLIs. A top-level Claude Code session decomposes the task and dispatches Codex and Grok workers through slot-controlled adapters with reader/writer lanes and hard concurrency caps; the launcher checks result structure, worker evidence paths, and consistency of reported fields, without opening validation-item evidence strings or re-running commands. Use for substantial multi-agent coding, research, implementation, or verification. Keep simple tasks inline.
---

# Bounded multi-vendor orchestration

> Historical v0.1.0 skill from August 2026, not a current routing recommendation.
> Read [repository status](README.md) first. Current provider integration is
> unverified, external wrappers are required, and these checks are not sandboxing.

This agent skill definition is suitable when a task genuinely benefits from
decomposition, external workers, and cross-vendor verification — substantial
implementation, wide research, or a correctness claim that needs independent
refutation. A task that fits in a few tool calls should stay inline; the setup
overhead is real.

Requires a POSIX system with Python 3.10+, an authenticated Claude Code CLI,
and — only if you want those workers — the external `codex-leg` and `grok-leg`
adapters. Run `efo-preflight` to see what resolves. Full setup in
`docs/setup.md`; adapter contracts in `docs/adapters.md`.

## Routing rules

- Codex workers go through `efo-codex-leg`; Grok workers through
  `efo-grok-leg`. Both require `--lane reader|writer` and enforce job-wide
  caps through a separate slot-controller process.
- Bare `codex-leg` / `grok-leg`, direct vendor CLIs, API-key code paths, and
  nested agent/workflow tools are prohibited for workers — each bypasses the
  slot controller, which makes the caps fictional.
- The fallback model is an **availability** fallback only, never a routing
  choice.
- The supervising agent keeps user interaction, process supervision, and final
  evidence inspection. The orchestrator session owns decomposition, worker
  routing, and synthesis. Do not build the same plan twice.

The launcher appends `references/orchestration-contract.md` as instructions, constrains output
with `references/result-schema.json`, and checks structure, fan-in, worker
evidence paths, and consistency of reported validation fields before reporting
success. It does not open validation-item evidence strings or re-run commands.

## Start a run

```bash
efo-orchestrate --cwd /absolute/trusted/worktree <<'BRIEF'
<self-contained objective, relevant context, constraints, authorization
boundary, and mechanically checkable acceptance criteria>
BRIEF
```

Set the caps to the shape of the work with `--max-workers` (default 4, 1–12),
`--max-writers` (default 2, 0–max-workers), and `--max-nodes` (default 12,
max-workers–100). `--max-writers 0` mechanically prevents writer-lane starts;
reader lanes still run, so their user-supplied adapters must enforce read-only
sandboxing.

```bash
efo-orchestrate --cwd /abs/worktree \
  --max-workers 8 --max-writers 2 --max-nodes 24 <<'BRIEF'
...
BRIEF
```

A worked example, including worker briefs and how to read the result, is in
`examples/example-brief.md`.

## Evidence

The launcher prints one compact JSON object and writes everything under a
unique job directory (default `$HOME/.efo/orchestration-runs/`, override with
`EFO_ORCHESTRATION_RUN_ROOT` or `--job-dir`):

- `brief.md`, `contract.md`, `command.json`, `limits.json`, `session-id`
- `claude-fable-stream.jsonl` / `-stderr.log`, and the `claude-opus-*` pair
  when the availability fallback runs — each attempt's evidence is named for
  the model that produced it
- `.efo-slots/events.jsonl`, `.efo-slots/state.json`
- worker streams and artifacts
- `final-raw.json`, `final.json`, `final-validation-errors.json`,
  `orchestration-metrics.json`, `meta.json`

`final.json` is the **normalized** result and is the file to read.
`final-raw.json` preserves what the orchestrator originally claimed.

## Resume

```bash
efo-orchestrate --cwd /abs/worktree \
  --resume "$(cat "$JOB/session-id")" <<'BRIEF'
<distilled follow-up; do not replay the transcript>
BRIEF
```

Prefer one session per complex task and resume it for bounded follow-ups.
Cross-model fallback is disabled under `--resume`; a session is never resumed
on a different model. If a resumed run hits an availability error the launcher
returns `blocked` — start a fresh run if a fallback attempt is appropriate.

## Supervision checklist

1. Confirm the target cwd, git state, and authorization boundary before launch.
   Prefer a dedicated worktree; commit or stash first.
2. Pass a distilled brief. Name in-scope and out-of-scope files explicitly.
3. Let the orchestrator own the graph. Do not run a second worker graph beside
   it.
4. On completion read `meta.json` and `final.json`: status, the normalization
   record, fan-in completeness, worker evidence paths, changed files, and
   validation results.
5. Independently run or inspect the project's own gate. Model assertions are
   not proof, and neither is a green summary.
6. Review the diff.

## Safety and usage

- Default permission mode is `auto`, which allows routine adapter dispatch and
  validation while retaining the CLI's own safety behavior. No bypass mode is
  offered.
- Grok automation uses non-interactive approval **only** inside
  `efo-grok-leg`. The contract requires a narrow profile and workspace sandbox;
  the in-repository layer requires an explicit space-separated `--cwd DIR`
  that resolves to neither `/` nor `$HOME`, clears adapter environment
  defaults, and rejects `--sandbox off` and `--profile full`. The user-supplied
  `grok-leg` must enforce the actual profile and sandbox. Understand this
  before enabling Grok workers — see `docs/adapters.md`.
- Nested agent and workflow tools are disabled in the launcher so provider
  routing stays explicit through the adapters.
- The child environment is allowlisted; provider API-key variables are not
  forwarded.
- Default watchdogs kill a run after 20 minutes of output inactivity or four
  hours wall time. Raise them only for a known long silent step.
- Default concurrency is four workers with at most two writers. Widen readers
  for research; keep writers low.
- Retry one failed node once on the same vendor, then switch vendor, then stop
  and surface the blocker. Never synthesize partial fan-in as complete.
- A result claiming success while any validation item failed is deterministically
  downgraded and the run exits non-zero.
- This project drives official, authenticated vendor CLIs using an entitlement
  already granted to the user. It ships no credentials and is not a proxy or
  relay. Automated, headless, or non-interactive invocation may be restricted
  or prohibited depending on the provider and specific plan. The operator must
  verify the applicable terms; silence in provider documentation is not
  permission. See `docs/provider-terms-review.md` for a good-faith engineering
  review, not legal advice. Provider terms win if they conflict with this skill.

## Independence

This is an independent community integration, not affiliated with or endorsed
by Anthropic, OpenAI, or xAI. See `ATTRIBUTION.md`.

Run `tests/run-tests.sh` as the deterministic, offline validation gate after
changing this skill.
