# Setup

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.10+ | Uses PEP 604 unions; no third-party packages |
| Bash 4+ | The adapters use arrays and `[[ ]]`; they must not be run as `sh` |
| A POSIX system | Needs `fcntl.flock` and process groups. Linux and macOS are supported; Windows is not (WSL works) |
| Claude Code CLI | Authenticated the way you normally authenticate it |
| `codex-leg` | Only for Codex workers — an external program you supply, see [adapters.md](adapters.md) |
| `grok-leg` + `grok` | Only for Grok workers — same |

No package installation, no network access, and no credentials are required by
this repository itself.

## 2. Preflight

Run this before anything else. It resolves every tool, checks the run root, and
tells you exactly what is missing and how to fix it.

```bash
./scripts/prime_preflight.py
./scripts/prime_preflight.py --json     # machine-readable
```

`claude` is **required**. `codex-leg`, `grok-leg`, and `grok` are **optional**:
if one is missing, preflight still succeeds and reports which worker vendor is
unavailable. Exit status is 0 only when every required check passes.

## 3. Install

```bash
./scripts/install.sh                    # links into ${XDG_BIN_HOME:-$HOME/.local/bin}
./scripts/install.sh --prefix ~/bin
./scripts/install.sh --dry-run          # show actions, change nothing
./scripts/install.sh --uninstall
```

It creates four symlinks — `prime-fable-orchestrate`, `prime-codex-leg`,
`prime-grok-leg`, `prime-preflight` — and makes the linked scripts executable.
It refuses to clobber an existing real file or a symlink pointing outside this
repository unless you pass `--force`, warns if the prefix is not on `PATH`, and
does not touch your shell profile, install packages, or reach the network.

You can skip installation entirely and call `scripts/prime_fable_orchestrate.py`
by path — but the adapters must be reachable *by name* (`prime-codex-leg`,
`prime-grok-leg`) from the orchestrator's `PATH`, because that is how the
orchestrator is instructed to invoke them.

## 4. Configuration

Everything is an environment variable. Nothing is written to a config file, and
there are no hardcoded absolute paths.

### Tool discovery

| Variable | Default | Purpose |
| --- | --- | --- |
| `PRIME_CLAUDE_BIN` | `claude` by name | Claude Code CLI |
| `PRIME_CODEX_LEG_BIN` | `codex-leg` by name | Codex adapter |
| `PRIME_GROK_LEG_BIN` | `grok-leg` by name | Grok adapter |
| `PRIME_GROK_BIN` | `grok` by name | Grok CLI, used by the approval shim |

"By name" means the user bin directory (`$XDG_BIN_HOME`, or `$HOME/.local/bin`
when unset — the directory `install.sh` links into) is searched first, then
`PATH`. See [adapters.md](adapters.md) for the full rule.

An override that is set but does not resolve to a usable executable is a hard
error — it never silently falls back. "Usable" means: resolves through `~` and
symlinks to a canonical absolute path, is a regular file, is executable, is not
world-writable, and does not sit in a world-writable directory unless that
directory has the sticky bit set (so a shared `/tmp` is not disqualified, but
anyone-can-replace-this directories are).

### Run behavior

| Variable | Default | Purpose |
| --- | --- | --- |
| `PRIME_ORCHESTRATION_RUN_ROOT` | `$HOME/.prime/orchestration-runs` | Where job directories are created |
| `PRIME_PRIMARY_MODEL` | `claude-fable-5` | Orchestrator model (also `--model`) |
| `PRIME_FALLBACK_MODEL` | `claude-opus-5` | Availability fallback (also `--fallback-model`) |

### Set by the launcher for its children — do not set these yourself

`PRIME_ORCHESTRATION_JOB_DIR`, `PRIME_MAX_WORKERS`, `PRIME_MAX_WRITERS`,
`PRIME_MAX_NODES`.

### Environment narrowing

The orchestrator child receives an **allowlisted** environment: standard shell
and locale variables, `PATH` as you provided it, the job/cap variables above,
and the `PRIME_*` tool overrides (so wrappers it spawns resolve the same
binaries preflight checked). Provider API-key variables are deliberately **not**
forwarded — a worker should not be able to switch from your authenticated CLI
session to a metered API path without you asking for it.

## 5. Launcher flags

| Flag | Default | Notes |
| --- | --- | --- |
| `--cwd DIR` | cwd | Trusted working directory for the task |
| `--brief-file FILE` | stdin | Brief source |
| `--job-dir DIR` | generated | Must not already exist |
| `--resume SESSION_ID` | — | Continue a prior session; disables cross-model fallback |
| `--session-id UUID` | generated | Pin a new session id |
| `--model` / `--fallback-model` | see above | |
| `--effort` | `high` | `low`…`max` |
| `--permission-mode` | `auto` | `acceptEdits`, `auto`, `dontAsk`, `plan`. No bypass mode is offered |
| `--max-workers` / `--max-writers` / `--max-nodes` | 4 / 2 / 12 | See [architecture.md](architecture.md#caps-and-lanes) |
| `--stall-s` | 1200 | Kill after this long with no output (min 30) |
| `--timeout-s` | 14400 | Wall-clock limit (min 60) |
| `--dry-run` | off | Create the job dir and print the redacted command; run nothing |

Start with `--dry-run` on a new machine: it exercises argument validation,
adapter resolution, and job-directory creation without spending anything.

## 6. Prime Agent skill installation

[SKILL.md](../SKILL.md) is the skill definition. Place this repository where
your Prime Agent installation looks for skills, or symlink it there, then make
sure the four commands above are on the agent's `PATH`. The skill is a thin
wrapper: it tells the agent when to reach for the launcher and how to read the
evidence afterward.

## 7. Verify

```bash
./tests/run-tests.sh
```

Deterministic, offline, hermetic — it uses a fake CLI stub and never calls a
model or opens a socket.

## 8. Provider terms

Confirm that automated, headless use of each vendor CLI is permitted under your
plan before you run anything. That review is your responsibility. See
[security.md](security.md#operator-responsibilities).
