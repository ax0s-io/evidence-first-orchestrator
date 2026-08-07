# External adapter contracts

This is an **interface specification** for the external programs the project
calls. The repository does not bundle, vendor, or redistribute another
project's wrapper implementation. You supply and maintain `codex-leg` and
`grok-leg` yourself. If a program is missing, the corresponding capability
fails closed with an actionable diagnostic — it never silently falls back to a
raw vendor binary or substitutes an API-key code path.

| Adapter | Env override | Name looked up | Needed for |
| --- | --- | --- | --- |
| Claude Code CLI | `EFO_CLAUDE_BIN` | `claude` | Always — it runs the orchestrator session |
| Codex leg wrapper | `EFO_CODEX_LEG_BIN` | `codex-leg` | Codex workers only |
| Grok leg wrapper | `EFO_GROK_LEG_BIN` | `grok-leg` | Grok workers only |
| Grok CLI | `EFO_GROK_BIN` | `grok` | Grok workers only (invoked *through* `grok-leg`) |

Resolution rule, applied identically everywhere:

1. If the override variable is set, it must name an existing **executable
   file**. A set-but-unusable override is a hard error — it is never ignored,
   because silently falling back to `PATH` after an explicit override is how you
   end up running the wrong binary.
2. Otherwise the name is looked up in the user bin directory
   (`$XDG_BIN_HOME`, or `$HOME/.local/bin` when that is unset) — the directory
   `install.sh` links into. A per-user install is a deliberate choice, so a
   system-wide binary of the same name cannot shadow it.
3. Otherwise the name is looked up on `PATH`.
4. If nothing resolves, the caller exits non-zero with a message naming the
   variable, the searched name, and what to install.

The launcher owns this rule; `scripts/efo_resolve_bin.sh` and
`scripts/efo_preflight.py` call into it rather than reimplementing it, so
every entry point resolves the same binary.

Run `scripts/efo_preflight.py` to see exactly what resolves on your machine.

If an adapter drives a consumer-subscription CLI, clearing automated,
headless, and non-interactive use against that provider's specific plan terms
is the operator's responsibility. Silence in provider documentation is not
permission. See [provider-terms-review.md](provider-terms-review.md); it is a
good-faith engineering review, not legal advice, and provider terms win.

---

## Why there is a wrapper layer at all

The vendor CLIs are general-purpose. Handing one directly to an autonomous
orchestrator gives up the three properties this project exists to provide:
a stall watchdog, a bounded tool/sandbox surface, and a durable evidence
stream. The `*-leg` wrappers are where those live.

This repository adds a **slot-controlled layer on top**:

```
orchestrator
  └─ efo-codex-leg --lane reader|writer   (this repo)
       └─ efo_slot_controller.py run …    (this repo — caps + lifecycle events)
            └─ codex-leg …                  (YOUR program — watchdog, sandbox, stream)
                 └─ codex …                 (vendor CLI)
```

`efo-codex-leg` / `efo-grok-leg` validate the lane, verify the job
directory, reject argument shapes that would defeat the sandbox, and then hand
off to the slot controller, which blocks until a slot is available and records
`queued` / `started` / `finished` events. The cap is therefore enforced by a
process the orchestrator cannot talk its way past.

**Bare `codex-leg` / `grok-leg` must never be invoked directly by the
orchestrator** — doing so bypasses the slot controller entirely. The contract
prohibits it and the metrics cross-check catches it after the fact: a final
result claiming workers while the slot controller recorded zero starts is
rejected.

---

## Contract: `codex-leg`

**Role.** Headless, one-shot, non-interactive execution of a brief against the
OpenAI Codex CLI, with a stall watchdog and a JSONL event stream.

**Invocation.** `efo-codex-leg` consumes and strips its own `--lane` flag and
forwards everything else verbatim, in order:

```
<codex-leg> [wrapper flags] -- [codex exec flags]
```

**Expected to be supported by your implementation:**

| Flag | Meaning this project relies on |
| --- | --- |
| `--stream PATH` | Append a JSONL event stream to `PATH`. One path per worker. |
| `--stall-s N` | Kill the run after `N` seconds with no output. |
| `--` | Separator; everything after is passed to the vendor CLI. |
| `-s`/`--sandbox MODE` | Vendor sandbox mode. `read-only` for readers; a writable mode requires `--lane writer`. |
| `-C DIR` | Working directory for the vendor CLI. |
| `-o PATH` | Write the final assistant message to `PATH`. |

**Behavioral requirements:**

- Read the brief from **stdin**; close stdin afterward so nothing can block on
  a prompt.
- Never enter an interactive approval loop. Headless runs cannot answer.
- Exit non-zero on watchdog kill, vendor error, or auth failure.
- Write the stream file incrementally, so a killed run still leaves evidence.
- Do not accept a brief on argv — process listings are visible to other
  processes of the same user.

**Enforced by `efo-codex-leg` before it forwards anything:**

- `--lane reader|writer` exactly once, space-separated (`--lane=writer` is
  rejected so the parse cannot be ambiguous).
- `EFO_ORCHESTRATION_JOB_DIR` set and an existing directory.
- Any sandbox mode other than `read-only` requires `--lane writer`. A reader
  cannot obtain write access by argument shape.

## Contract: `grok-leg`

**Role.** Headless one-shot execution against the xAI Grok CLI with a bounded
tool profile, an explicit sandbox, a stall watchdog, and a JSON stream.

**Expected flags:** `--stream PATH`, `--cwd DIR`, `--profile NAME`,
`--effort low|medium|high`, `--sandbox MODE`, and `GROK_LEG_BIN` respected as
the path to the underlying Grok CLI (this project sets it to a small shim).

**Profiles this project assumes exist**, in ascending capability:

| Profile | Capability | Lane |
| --- | --- | --- |
| `scout` | read + grep only | reader |
| `probe` | read-only shell, enough to run checks | reader |
| `write` | bounded edits | **writer only** |
| `full` | unrestricted | **rejected** |

**Enforced by `efo-grok-leg` before it forwards anything:**

- `--lane reader|writer` exactly once.
- `EFO_ORCHESTRATION_JOB_DIR` set and an existing directory.
- An explicit space-separated `--cwd DIR` is **mandatory**; it must exist and
  resolve to neither `/` nor `$HOME`. The in-repository check does not require
  it to be a descendant of `$HOME` or otherwise prove that it is narrow.
- `--sandbox off` is rejected.
- `--profile full` is rejected.
- `--profile write` requires `--lane writer`.
- `GROK_LEG_SANDBOX`, `GROK_LEG_PROFILE`, and `GROK_LEG_STALL_S` are unset
  before exec, so an inline environment assignment cannot re-open what the
  argument checks just closed.

### The approval shim

`scripts/grok_always_approve_shim.sh` is a small shim that inserts the
Grok CLI's non-interactive approval flag plus a small deny list. It exists
because a headless run cannot answer an approval prompt.

**Understand what you are enabling.** Non-interactive approval means the model
may run allowed tools without asking. The deny list is narrow and is not a
general command filter or a security boundary. The in-repository layer rejects
known escape values and requires a non-root, non-home `--cwd`, but the
user-supplied `grok-leg` and vendor CLI must enforce the actual sandbox and
profile. A hostile or mistaken model can still cause harm within that
authority. Enabling this path is the operator's deliberate decision for each
machine and run. If your `grok-leg` cannot enforce those restrictions, do not
use the shim.

## Contract: `claude`

**Role.** Runs the orchestrator session itself. This must be the official
Claude Code CLI, authenticated the way you normally authenticate it.

The launcher invokes it with `-p`, `--output-format stream-json --verbose`,
`--json-schema`, `--append-system-prompt`, `--permission-mode`,
`--disallowed-tools Agent,Workflow`, `--add-dir <job dir>`, `--model`, and
either `--session-id` or `--resume`. The brief is delivered on **stdin**.

The child process receives a **narrow allowlisted environment**. Provider
API-key variables are deliberately not forwarded, so a worker cannot quietly
switch from your authenticated CLI session to a metered API code path. The
`EFO_*` adapter overrides *are* forwarded, so wrappers spawned by the
orchestrator resolve the same binaries the launcher checked at preflight.

---

## Writing your own adapter

Any program satisfying the flag and behavior contract above works. A minimal
adapter is roughly:

1. Parse `--stream`, `--stall-s`, and your own flags; stop at `--`.
2. Resolve the vendor CLI (respect an env override, else `PATH`); exit non-zero
   with a clear message if absent.
3. Read the brief from stdin.
4. Spawn the vendor CLI in its own process group with the remaining args,
   stdin closed after the brief is written.
5. Tee its output to the stream file, tracking last-output time.
6. Kill the process group on stall or timeout; reap descendants.
7. Exit with the child's status, or a distinct non-zero code on watchdog kill.

Do not add capabilities the profile/sandbox flags are supposed to bound — the
whole safety argument above rests on those being real.
