# Setup

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.10+ | Uses PEP 604 unions; no third-party packages |
| Bash 3.2+ | Bash 4+ is preferred; macOS Bash 3.2 is supported. The adapters must not be run as `sh` |
| A POSIX system | Needs `fcntl.flock` and process groups. Linux and macOS are supported; Windows is not (WSL works) |
| Claude Code CLI | Authenticated the way you normally authenticate it |
| `codex-leg` | Only for Codex workers — an external program you supply, see [adapters.md](adapters.md) |
| `grok-leg` + `grok` | Only for Grok workers — same |

No package installation, no network access, and no credentials are required by
this repository itself.

Obtain the working tree and enter its root before running the commands below:

```bash
git clone https://github.com/ax0s-io/evidence-first-orchestrator.git
cd evidence-first-orchestrator
```

Install and authenticate each official vendor CLI under the terms of the plan
you intend to use. This repository does not install those CLIs or authenticate
provider accounts. Supply `codex-leg` or `grok-leg` only if you want the
corresponding worker type; their interface is documented in
[adapters.md](adapters.md).

## 2. Preflight

Run this before anything else. It resolves every tool, checks the run root and
the platform, requires the provider-terms acknowledgement, and tells you exactly
what is missing and how to fix it.

```bash
./scripts/efo_preflight.py
./scripts/efo_preflight.py --json     # machine-readable
```

Required checks: `provider-terms`, `python`, `claude`, `run root`, `platform`,
`bash`. `codex-leg`, `grok-leg`, and `grok` are **optional**: if one is missing,
preflight still succeeds and reports which worker vendor is unavailable. Exit
status is 0 only when every required check passes.

### The provider-terms check

`provider-terms` fails until you set `EFO_PROVIDER_TERMS_ACK=1`:

```bash
EFO_PROVIDER_TERMS_ACK=1 ./scripts/efo_preflight.py
```

Read [provider-terms-review.md](provider-terms-review.md) first. That review
could not affirmatively clear automated invocation of a consumer-subscription-
authenticated CLI for any supported vendor, so whether this tool may drive your
CLI depends on your own plan and your own reading of your provider's terms.

The check records **your acknowledgement, not compliance**. This project cannot
see which plan or authentication method a CLI is using, so it cannot verify
anything — it only refuses to be set up silently. Export the variable in your
shell profile once you have made that determination.

## 3. Install

```bash
./scripts/install.sh                    # links into ${XDG_BIN_HOME:-$HOME/.local/bin}
./scripts/install.sh --prefix ~/bin
./scripts/install.sh --dry-run          # show actions, change nothing
./scripts/install.sh --uninstall
```

It creates four symlinks — `efo-orchestrate`, `efo-codex-leg`,
`efo-grok-leg`, `efo-preflight` — and makes the linked scripts executable.
It refuses to clobber an existing real file or a symlink pointing outside this
repository unless you pass `--force`, warns if the prefix is not on `PATH`, and
does not touch your shell profile, install packages, or reach the network.

You can skip installation entirely and call `scripts/efo_orchestrate.py`
by path — but the adapters must be reachable *by name* (`efo-codex-leg`,
`efo-grok-leg`) from the orchestrator's `PATH`, because that is how the
orchestrator is instructed to invoke them.

The root [VERSION](../VERSION) file is the release version source. Each
installed entry point reports it without starting a model or worker:

```bash
efo-orchestrate --version
efo-preflight --version
efo-codex-leg --version
efo-grok-leg --version
```

For this release each command prints `evidence-first-orchestrator 0.1.0`.

## 4. Configuration

Everything is an environment variable. Nothing is written to a config file, and
there are no hardcoded absolute paths.

### Tool discovery

| Variable | Default | Purpose |
| --- | --- | --- |
| `EFO_CLAUDE_BIN` | `claude` by name | Claude Code CLI |
| `EFO_CODEX_LEG_BIN` | `codex-leg` by name | Codex adapter |
| `EFO_GROK_LEG_BIN` | `grok-leg` by name | Grok adapter |
| `EFO_GROK_BIN` | `grok` by name | Grok CLI, used by the approval shim |

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
| `EFO_PROVIDER_TERMS_ACK` | unset | Must be exactly `1` for preflight to pass; see [the provider-terms check](#the-provider-terms-check) |
| `EFO_ORCHESTRATION_RUN_ROOT` | `$HOME/.efo/orchestration-runs` | Where job directories are created |
| `EFO_PRIMARY_MODEL` | `claude-fable-5` | Orchestrator model (also `--model`) |
| `EFO_FALLBACK_MODEL` | `claude-opus-5` | Availability fallback (also `--fallback-model`) |

### Set by the launcher for its children — do not set these yourself

`EFO_ORCHESTRATION_JOB_DIR`, `EFO_MAX_WORKERS`, `EFO_MAX_WRITERS`,
`EFO_MAX_NODES`.

### Environment narrowing

The orchestrator child receives an **allowlisted** environment: standard shell
and locale variables, `PATH` as you provided it, the job/cap variables above,
and the `EFO_*` tool overrides (so wrappers it spawns resolve the same
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
launcher resolution, and job-directory creation without starting a model.

## 6. Agent skill installation

[SKILL.md](../SKILL.md) is an agent skill definition. If your supervising agent
supports local skills, place or symlink this skill directory wherever that
agent looks for them. Then ensure the four installed `efo-*` commands are on
the agent process's `PATH`. The skill tells an agent when to invoke the launcher
and how to inspect the evidence; it is not required for a human operator to run
the launcher directly.

## 7. Verify

```bash
./tests/run-tests.sh
```

Deterministic, offline, hermetic — it uses a fake CLI stub and never calls a
model or opens a socket.

## 8. Provider terms

Automated, headless, or non-interactive use may be restricted or prohibited by
a provider or specific plan. Verify your own terms before running; silence in
provider documentation is not permission. See the operator responsibilities in
[security.md](security.md#operator-responsibilities) and the good-faith
engineering review in
[provider-terms-review.md](provider-terms-review.md), which is not legal advice.
If provider terms conflict with this documentation, the provider terms win.
