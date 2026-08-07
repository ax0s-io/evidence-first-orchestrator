#!/usr/bin/env python3
"""Evidence-first CLI orchestrator with safe cross-model fallback and run evidence."""
from __future__ import annotations

import argparse
from collections import deque
import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from efo_metrics import build_metrics
from efo_slot_controller import init_job
from efo_version import VERSION

SKILL_DIR = SCRIPT_DIR.parent
CONTRACT_PATH = SKILL_DIR / "references" / "orchestration-contract.md"
SCHEMA_PATH = SKILL_DIR / "references" / "result-schema.json"
DEFAULT_PRIMARY_MODEL = "claude-fable-5"
DEFAULT_FALLBACK_MODEL = "claude-opus-5"
SAFE_REPLAY_TOOLS = {"Read", "Glob", "Grep"}
USAGE_CREDIT_RESULT = (
    # This literal is provider CLI output matched for compatibility, not policy.
    "You're out of usage credits. Run /usage-credits to keep using Fable 5 "
    "or /model to switch models."
)
AVAILABILITY_PATTERNS = (
    ("usage_credits_exhausted", re.compile(r"\bout of usage credits\b", re.IGNORECASE)),
    (
        "usage_credits_exhausted",
        re.compile(r"\busage credits? (?:are )?(?:exhausted|depleted)\b", re.IGNORECASE),
    ),
    (
        "quota_exhausted",
        re.compile(r"\b(?:quota|usage limit) (?:exceeded|reached|exhausted)\b", re.IGNORECASE),
    ),
    (
        "model_overloaded",
        re.compile(r"\b(?:model|service)[^\n]{0,80}\boverloaded\b", re.IGNORECASE),
    ),
    ("model_overloaded", re.compile(r"\boverloaded_error\b", re.IGNORECASE)),
    (
        "model_unavailable",
        re.compile(
            r"\b(?:model|service)[^\n]{0,80}\b(?:temporarily )?unavailable\b",
            re.IGNORECASE,
        ),
    ),
    ("model_unavailable", re.compile(r"\btemporarily unavailable\b", re.IGNORECASE)),
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def model_evidence_prefix(model: str) -> str:
    """Name attempt evidence after the model that ran, not its role in the run.

    'claude-fable-5' becomes 'claude-fable'. Trailing version components are
    dropped so a model bump does not rename the files operators grep for, and
    the result is reduced to [a-z0-9-] so a model argument can never steer the
    write outside the job directory.
    """
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", model.lower()) if part]
    while len(parts) > 1 and parts[-1].isdigit():
        parts.pop()
    return "-".join(parts) if parts else "model"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the primary model through Claude CLI with automatic Opus fallback."
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"evidence-first-orchestrator {VERSION}",
    )
    p.add_argument("--cwd", default=os.getcwd(), help="Trusted working directory for the task")
    p.add_argument("--brief-file", help="Read the task brief from this file instead of stdin")
    p.add_argument("--job-dir", help="Explicit evidence directory")
    p.add_argument(
        "--model",
        default=os.environ.get("EFO_PRIMARY_MODEL") or DEFAULT_PRIMARY_MODEL,
        help="Primary model (default: EFO_PRIMARY_MODEL or claude-fable-5)",
    )
    p.add_argument(
        "--fallback-model",
        default=os.environ.get("EFO_FALLBACK_MODEL") or DEFAULT_FALLBACK_MODEL,
        help="Availability fallback model (default: EFO_FALLBACK_MODEL or claude-opus-5)",
    )
    p.add_argument("--resume", help="Resume a prior Claude CLI session id")
    p.add_argument("--session-id", help="Pin a new session UUID (generated when omitted)")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default="high")
    p.add_argument("--permission-mode", choices=["acceptEdits", "auto", "dontAsk", "plan"], default="auto")
    p.add_argument("--stall-s", type=int, default=1200, help="Kill after this many seconds with no stdout/stderr")
    p.add_argument("--timeout-s", type=int, default=14400, help="Absolute wall-clock timeout")
    p.add_argument("--max-workers", type=int, default=4, help="Combined concurrent external workers (1..12)")
    p.add_argument("--max-writers", type=int, default=2, help="Concurrent writer workers (0..max-workers; 0 forbids writers)")
    p.add_argument("--max-nodes", type=int, default=12, help="Cumulative external worker starts (max-workers..100)")
    p.add_argument("--dry-run", action="store_true", help="Create run files and print redacted command without executing")
    return p.parse_args()


def read_brief(args: argparse.Namespace) -> str:
    if args.brief_file:
        text = Path(args.brief_file).expanduser().read_text()
    else:
        if sys.stdin.isatty():
            raise SystemExit("Task brief required on stdin or with --brief-file")
        text = sys.stdin.read()
    if not text.strip():
        raise SystemExit("Task brief cannot be blank")
    return text.strip() + "\n"


def make_job_dir(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=False)
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        configured_root = os.environ.get("EFO_ORCHESTRATION_RUN_ROOT")
        run_root = Path(configured_root).expanduser() if configured_root else Path.home() / ".efo" / "orchestration-runs"
        path = run_root.resolve() / f"{stamp}-{uuid.uuid4().hex[:8]}"
        path.mkdir(parents=True, exist_ok=False)
    path.chmod(0o700)
    return path


def usable_executable(value: str | os.PathLike[str]) -> Path | None:
    """Return the canonical executable path when it passes trust checks."""
    try:
        path = Path(value).expanduser().resolve(strict=True)
        file_mode = path.stat().st_mode
        directory_mode = path.parent.stat().st_mode
    except (OSError, RuntimeError):
        return None
    if not path.is_file() or not os.access(path, os.X_OK):
        return None
    if file_mode & stat.S_IWOTH:
        return None
    if directory_mode & stat.S_IWOTH and not directory_mode & stat.S_ISVTX:
        return None
    return path


def _search_dirs() -> list[Path]:
    """User bin directory first, then PATH.

    install.sh links these commands into ${XDG_BIN_HOME:-$HOME/.local/bin}, and a
    per-user install is the one the operator chose deliberately. Searching it
    first means a system-wide binary of the same name cannot shadow it.
    """
    dirs: list[Path] = []
    xdg_bin_home = os.environ.get("XDG_BIN_HOME")
    home = os.environ.get("HOME")
    if xdg_bin_home:
        dirs.append(Path(xdg_bin_home))
    elif home:
        dirs.append(Path(home) / ".local" / "bin")
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        if entry:
            dirs.append(Path(entry))
    return [directory for directory in dirs if directory.is_absolute()]


def find_executable(name: str) -> Path | None:
    for directory in _search_dirs():
        resolved = usable_executable(directory / name)
        if resolved is not None:
            return resolved
    return None


def resolve_executable(name: str, env_var: str, program: str) -> Path:
    """Resolve a trusted executable from an authoritative override, else by name."""
    override = os.environ.get(env_var)
    if override:
        resolved = usable_executable(override)
        if resolved is None:
            raise SystemExit(
                f"{program}: {env_var} does not name a usable executable: {override}"
            )
        return resolved
    resolved = find_executable(name)
    if resolved is None:
        display = "Claude CLI" if name == "claude" else name
        raise SystemExit(
            f"{program}: {display} not found; set {env_var} to an executable file "
            f"or install '{name}' on PATH"
        )
    return resolved


def is_usage_credit_result(event: object) -> bool:
    """Return true only for the provider CLI's synthetic credit terminal event."""
    return bool(
        isinstance(event, dict)
        and event.get("type") == "result"
        and event.get("is_error") is True
        and event.get("terminal_reason") == "api_error"
        and event.get("api_error_status") == 429
        and event.get("subtype") == "success"
        and event.get("result") == USAGE_CREDIT_RESULT
    )


def _strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _strings(nested)


def detect_availability_error(stream_path: Path, stderr_path: Path) -> str | None:
    """Classify explicit quota/availability errors, excluding ordinary structured results."""
    candidates: list[str] = []
    try:
        candidates.append(stderr_path.read_text(errors="replace"))
    except OSError:
        pass
    try:
        lines = stream_path.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            result = event.get("result")
            if isinstance(result, str) and event.get("structured_output") is None:
                candidates.append(result)
            if event.get("is_error"):
                candidates.extend(_strings(event))
        elif event.get("type") == "error" or "error" in event:
            candidates.extend(_strings(event.get("error", event)))
    text = "\n".join(candidates)
    for reason, pattern in AVAILABILITY_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def _tool_names(value: object, names: list[str | None]) -> None:
    if isinstance(value, dict):
        kind = value.get("type")
        if isinstance(kind, str) and (kind == "tool_use" or kind.endswith("_tool_use")):
            name = value.get("name")
            names.append(name if isinstance(name, str) and name else None)
        for nested in value.values():
            _tool_names(nested, names)
    elif isinstance(value, list):
        for nested in value:
            _tool_names(nested, names)


def assess_fallback_safety(job_dir: Path, stream_path: Path) -> tuple[bool, str, int, list[str]]:
    """Prove that retry cannot duplicate worker starts or mutating Claude tool effects."""
    state_path = job_dir / ".efo-slots" / "state.json"
    try:
        state = json.loads(state_path.read_text())
        state_started = state.get("nodes_started") if isinstance(state, dict) else None
        holders = state.get("holders") if isinstance(state, dict) else None
        if (
            not isinstance(state, dict)
            or state.get("schema_version") != 1
            or not isinstance(state_started, int)
            or isinstance(state_started, bool)
            or state_started < 0
            or not isinstance(holders, list)
        ):
            raise ValueError("invalid slot state shape")
        if holders:
            raise ValueError("slot state still contains holders")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return False, f"slot state cannot prove zero starts ({type(exc).__name__}: {exc})", 0, []
    if state_started:
        return False, f"slot state records {state_started} started node(s)", state_started, []

    events_path = job_dir / ".efo-slots" / "events.jsonl"
    try:
        event_lines = events_path.read_text().splitlines()
    except OSError as exc:
        return False, f"slot evidence is unreadable ({type(exc).__name__}: {exc})", 0, []
    started = 0
    for line_number, line in enumerate(event_lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False, f"slot evidence line {line_number} is malformed", started, []
        if not isinstance(event, dict):
            return False, f"slot evidence line {line_number} is not an object", started, []
        if event.get("event") == "started":
            started += 1
    if started:
        return False, f"slot controller recorded {started} started node(s)", started, []

    names: list[str | None] = []
    try:
        stream_lines = stream_path.read_text(errors="replace").splitlines()
    except OSError as exc:
        return False, f"primary stream is unreadable ({type(exc).__name__}: {exc})", started, []
    for line_number, line in enumerate(stream_lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False, f"primary stream line {line_number} is malformed", started, []
        if not isinstance(event, dict):
            return False, f"primary stream line {line_number} is not an object", started, []
        _tool_names(event, names)
    rendered_names = [name if name is not None else "<unknown>" for name in names]
    unsafe = sorted({name for name in rendered_names if name not in SAFE_REPLAY_TOOLS})
    if unsafe:
        return (
            False,
            f"potentially mutating or unknown tool use observed: {', '.join(unsafe)}",
            started,
            rendered_names,
        )
    return True, "no started nodes and only Read/Glob/Grep tool use", started, rendered_names


SUCCESS_STATUSES = {"completed", "completed_with_warnings"}
KNOWN_STATUSES = SUCCESS_STATUSES | {"blocked", "failed"}
STATUS_SEVERITY = {
    "completed": 0,
    "completed_with_warnings": 1,
    "blocked": 2,
    "failed": 3,
}
VALIDATION_STATUSES = {"passed", "failed", "not_run"}
VALIDATION_FIELDS = {"command", "status", "evidence"}


def _well_formed_validation_item(item: object) -> bool:
    return bool(
        isinstance(item, dict)
        and set(item) == VALIDATION_FIELDS
        and all(isinstance(item.get(key), str) for key in VALIDATION_FIELDS)
        and bool(item.get("command", "").strip())
        and bool(item.get("evidence", "").strip())
        and item.get("status") in VALIDATION_STATUSES
    )


def normalize_final_result(value: object) -> tuple[object, dict]:
    """Downgrade unsupported success claims without mutating model output."""
    normalized = copy.deepcopy(value)
    reported = value.get("status") if isinstance(value, dict) else None
    reported_status = reported if isinstance(reported, str) else None
    record = {
        "applied": False,
        "reported_status": reported_status,
        "normalized_status": reported_status,
        "reasons": [],
    }
    if not isinstance(value, dict) or reported_status not in KNOWN_STATUSES:
        return normalized, record
    if reported_status not in SUCCESS_STATUSES:
        return normalized, record

    target = reported_status
    validations = value.get("validation")
    well_formed = (
        [item for item in validations if _well_formed_validation_item(item)]
        if isinstance(validations, list)
        else []
    )
    if any(item.get("status") == "failed" for item in well_formed):
        record["reasons"].append("validation contains a failed item")
        target = max((target, "failed"), key=STATUS_SEVERITY.__getitem__)
    if (
        not isinstance(validations, list)
        or not validations
        or len(well_formed) != len(validations)
    ):
        record["reasons"].append(
            "validation is missing, empty, not a list, or contains a malformed item"
        )
        target = max((target, "failed"), key=STATUS_SEVERITY.__getitem__)
    if any(item.get("status") == "not_run" for item in well_formed):
        record["reasons"].append("validation contains a not_run item")
        target = max(
            (target, "completed_with_warnings"), key=STATUS_SEVERITY.__getitem__
        )
    fan_in = value.get("fan_in")
    if (
        not isinstance(fan_in, dict)
        or fan_in.get("complete") is not True
        or fan_in.get("expected") != fan_in.get("received")
    ):
        record["reasons"].append(
            "fan-in is incomplete or expected does not equal received"
        )
        target = max(
            (target, "completed_with_warnings"), key=STATUS_SEVERITY.__getitem__
        )
    workers = value.get("workers")
    if isinstance(workers, list) and any(
        not isinstance(worker, dict) or worker.get("status") != "completed"
        for worker in workers
    ):
        record["reasons"].append("one or more workers are not completed")
        target = max(
            (target, "completed_with_warnings"), key=STATUS_SEVERITY.__getitem__
        )

    normalized["status"] = target
    record["normalized_status"] = target
    record["applied"] = target != reported_status
    return normalized, record



def validate_final_result(value: object, job_dir: Path, max_nodes: int) -> list[str]:
    """Validate structure plus orchestration invariants the JSON schema cannot express."""
    errors: list[str] = []
    required = {"status", "summary", "fan_in", "workers", "validation", "changed_files", "risks", "next_actions"}
    if not isinstance(value, dict):
        return ["final result is not a JSON object"]
    missing = required - set(value)
    extra = set(value) - required
    if missing:
        errors.append(f"missing top-level fields: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected top-level fields: {sorted(extra)}")
    status = value.get("status")
    if status not in KNOWN_STATUSES:
        errors.append(f"invalid status: {status!r}")
    if not isinstance(value.get("summary"), str):
        errors.append("summary must be a string")

    fan = value.get("fan_in")
    expected = received = None
    complete = None
    if not isinstance(fan, dict) or set(fan) != {"expected", "received", "complete"}:
        errors.append("fan_in must contain exactly expected, received, complete")
    else:
        expected, received, complete = fan.get("expected"), fan.get("received"), fan.get("complete")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
            errors.append("fan_in.expected must be a non-negative integer")
        if not isinstance(received, int) or isinstance(received, bool) or received < 0:
            errors.append("fan_in.received must be a non-negative integer")
        if not isinstance(complete, bool):
            errors.append("fan_in.complete must be boolean")
        if isinstance(expected, int) and isinstance(received, int) and isinstance(complete, bool):
            if received > expected:
                errors.append("fan_in.received exceeds expected")
            if complete != (expected == received):
                errors.append("fan_in.complete contradicts expected/received counts")

    workers = value.get("workers")
    completed_workers = 0
    if not isinstance(workers, list):
        errors.append("workers must be an array")
        workers = []
    if len(workers) > max_nodes:
        errors.append(f"worker record count {len(workers)} exceeds --max-nodes {max_nodes}")
    ids: set[str] = set()
    evidence_paths: set[str] = set()
    worker_required = {"id", "vendor", "role", "status", "stream", "artifact", "summary"}
    for index, worker in enumerate(workers):
        prefix = f"workers[{index}]"
        if not isinstance(worker, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if set(worker) != worker_required:
            errors.append(f"{prefix} fields must be exactly {sorted(worker_required)}")
        wid = worker.get("id")
        if not isinstance(wid, str) or not wid:
            errors.append(f"{prefix}.id must be a non-empty string")
        elif wid in ids:
            errors.append(f"duplicate worker id: {wid}")
        else:
            ids.add(wid)
        if worker.get("vendor") not in {"codex", "grok"}:
            errors.append(f"{prefix}.vendor is invalid")
        if worker.get("status") not in {"completed", "failed", "stalled", "skipped"}:
            errors.append(f"{prefix}.status is invalid")
        if worker.get("status") == "completed":
            completed_workers += 1
        for field in ("role", "summary"):
            if not isinstance(worker.get(field), str):
                errors.append(f"{prefix}.{field} must be a string")
        for field in ("stream", "artifact"):
            evidence = worker.get(field)
            if evidence is not None and not isinstance(evidence, str):
                errors.append(f"{prefix}.{field} must be a string or null")
                continue
            if worker.get("status") == "completed" and not evidence:
                errors.append(f"{prefix}.{field} is required for completed workers")
                continue
            if evidence:
                evidence_path = Path(evidence).expanduser().resolve()
                try:
                    evidence_path.relative_to(job_dir.resolve())
                except ValueError:
                    errors.append(f"{prefix}.{field} is outside the job directory")
                if not evidence_path.is_file():
                    errors.append(f"{prefix}.{field} does not exist: {evidence_path}")
                elif evidence_path.stat().st_size == 0:
                    errors.append(f"{prefix}.{field} is empty: {evidence_path}")
                key = str(evidence_path)
                if field == "stream" and key in evidence_paths:
                    errors.append(f"duplicate worker stream path: {key}")
                if field == "stream":
                    evidence_paths.add(key)
    if isinstance(expected, int) and expected != len(workers):
        errors.append("fan_in.expected does not equal worker record count")
    if isinstance(received, int) and received != completed_workers:
        errors.append("fan_in.received does not equal completed worker count")
    if status in {"completed", "completed_with_warnings"} and complete is not True:
        errors.append("successful status requires complete fan-in")
    if status in {"completed", "completed_with_warnings"} and completed_workers != len(workers):
        errors.append("successful status cannot contain failed/stalled/skipped workers")

    validations = value.get("validation")
    if not isinstance(validations, list) or not validations:
        errors.append("validation must be a non-empty array")
        validations = []
    validation_statuses = []
    malformed_validation = False
    for index, item in enumerate(validations):
        validation_statuses.append(item.get("status") if isinstance(item, dict) else None)
        if not isinstance(item, dict) or set(item) != {"command", "status", "evidence"}:
            errors.append(f"validation[{index}] must contain exactly command, status, evidence")
            malformed_validation = True
            continue
        if not all(isinstance(item.get(k), str) for k in ("command", "status", "evidence")):
            errors.append(f"validation[{index}] fields must be strings")
            malformed_validation = True
        elif not item.get("command").strip() or not item.get("evidence").strip():
            errors.append(f"validation[{index}] command/evidence must be non-empty")
            malformed_validation = True
        if item.get("status") not in {"passed", "failed", "not_run"}:
            errors.append(f"validation[{index}].status is invalid")
            malformed_validation = True
    if status in SUCCESS_STATUSES and "failed" in validation_statuses:
        errors.append("success status cannot coexist with a failed validation item")
    if status in SUCCESS_STATUSES and malformed_validation:
        errors.append("success status requires every validation item to be well-formed")
    if status == "completed" and validation_statuses and any(s != "passed" for s in validation_statuses):
        errors.append("completed status requires every validation item to pass")
    if status in {"completed", "completed_with_warnings"} and "passed" not in validation_statuses:
        errors.append("successful status requires at least one passed validation item")

    for field in ("changed_files", "risks", "next_actions"):
        items = value.get(field)
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            errors.append(f"{field} must be an array of strings")
    return errors

def main() -> int:
    args = parse_args()
    if not 1 <= args.max_workers <= 12:
        raise SystemExit(f"--max-workers {args.max_workers} is outside the allowed range 1..12")
    if not 0 <= args.max_writers <= args.max_workers:
        raise SystemExit(
            f"--max-writers {args.max_writers} is outside the allowed range 0..{args.max_workers}"
        )
    if not args.max_workers <= args.max_nodes <= 100:
        raise SystemExit(
            f"--max-nodes {args.max_nodes} is outside the allowed range {args.max_workers}..100"
        )
    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise SystemExit(f"--cwd is not a directory: {cwd}")
    claude_bin = resolve_executable(
        "claude", "EFO_CLAUDE_BIN", "efo-orchestrate"
    )
    if not CONTRACT_PATH.is_file() or not SCHEMA_PATH.is_file():
        raise SystemExit(f"Skill contract/schema missing under {SKILL_DIR}")
    if args.stall_s < 30 or args.timeout_s < 60:
        raise SystemExit("--stall-s must be >=30 and --timeout-s >=60")

    brief = read_brief(args)
    job_dir = make_job_dir(args.job_dir)
    limits = {
        "max_workers": args.max_workers,
        "max_writers": args.max_writers,
        "max_nodes": args.max_nodes,
    }
    env_exported = {
        "EFO_MAX_WORKERS": str(args.max_workers),
        "EFO_MAX_WRITERS": str(args.max_writers),
        "EFO_MAX_NODES": str(args.max_nodes),
        "EFO_ORCHESTRATION_JOB_DIR": str(job_dir),
    }
    for variable in (
        "EFO_CLAUDE_BIN",
        "EFO_CODEX_LEG_BIN",
        "EFO_GROK_LEG_BIN",
        "EFO_GROK_BIN",
    ):
        if variable in os.environ:
            env_exported[variable] = os.environ[variable]
    contract = CONTRACT_PATH.read_text()
    schema = json.loads(SCHEMA_PATH.read_text())
    schema["properties"]["workers"]["maxItems"] = args.max_nodes
    schema_text = json.dumps(schema, indent=2)
    (job_dir / "brief.md").write_text(brief)
    (job_dir / "contract.md").write_text(contract)
    (job_dir / "result-schema.json").write_text(schema_text + "\n")
    (job_dir / "limits.json").write_text(json.dumps(limits, separators=(",", ":")) + "\n")

    new_session_id = None if args.resume else (args.session_id or str(uuid.uuid4()))
    if new_session_id:
        try:
            uuid.UUID(new_session_id)
        except ValueError as exc:
            raise SystemExit(f"--session-id must be a UUID: {exc}")

    run_header = f"""\
ORCHESTRATION RUN
Job directory: {job_dir}
Trusted task cwd: {cwd}

All external worker streams and artifacts must be written beneath the job directory. Follow the appended orchestration contract. Execute the task below; do not merely propose a plan unless the task explicitly requests planning only.

TASK
{brief}"""

    base_cmd = [
        str(claude_bin), "-p",
        "--effort", args.effort,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", args.permission_mode,
        "--disallowed-tools", "Agent,Workflow",
        "--add-dir", str(job_dir),
        "--append-system-prompt", contract,
        "--json-schema", schema_text,
    ]

    def command_for(name: str, model: str, session_id: str, resume: bool = False) -> list[str]:
        cmd = [*base_cmd, "--model", model, "--name", f"efo-{name}-{job_dir.name}"]
        cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
        return cmd

    session_hint = args.resume or new_session_id
    assert session_hint is not None
    primary_cmd = command_for("primary", args.model, session_hint, bool(args.resume))

    # The brief is sent over stdin, not argv, so same-user process listings do
    # not expose task content while the run is active.
    safe_cmd = primary_cmd + ["<task-brief-via-stdin>"]
    command_record = {
        "argv": safe_cmd,
        "limits": limits,
        "env_exported": env_exported,
        "fallback_policy": {
            "primary_model": args.model,
            "fallback_model": args.fallback_model,
            "explicit_retry": True,
            "resume_cross_model_retry": False,
            "safe_tools": sorted(SAFE_REPLAY_TOOLS),
        },
        "attempts": [],
        "resolved_executables": {"claude": str(claude_bin)},
    }
    (job_dir / "command.json").write_text(json.dumps(command_record, indent=2) + "\n")
    (job_dir / "session-id").write_text(session_hint + "\n")

    if args.dry_run:
        payload = {
            "status": "dry_run",
            "job_dir": str(job_dir),
            "session_id": session_hint,
            "command": safe_cmd,
            "limits": limits,
            "attempts": [],
            "selected_model": args.model,
            "fallback_triggered": False,
            "fallback_reason": None,
            "fallback_blocked_reason": None,
            "next_action": None,
        }
        (job_dir / "meta.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload))
        return 0

    init_job(job_dir)

    # Pass a narrow runtime environment. In particular, do not forward API-key
    # variables that could bypass the intended CLI authentication route.
    keep_env = {
        "HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "LC_ALL",
        "TERM", "COLORTERM", "NO_COLOR", "FORCE_COLOR", "SSH_AUTH_SOCK",
        "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
        "EFO_CLAUDE_BIN", "EFO_CODEX_LEG_BIN", "EFO_GROK_LEG_BIN",
        "EFO_GROK_BIN",
    }
    env = {key: value for key, value in os.environ.items() if key in keep_env}
    env["PATH"] = env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    env["EFO_ORCHESTRATION_JOB_DIR"] = str(job_dir)
    env["EFO_ORCHESTRATION"] = "1"
    env["EFO_MAX_WORKERS"] = str(args.max_workers)
    env["EFO_MAX_WRITERS"] = str(args.max_writers)
    env["EFO_MAX_NODES"] = str(args.max_nodes)

    started = time.monotonic()
    started_utc = utc_now()
    activity_lock = threading.Lock()
    termination = None
    signal_number = None
    proc = None
    attempts: list[dict] = []

    def handle_signal(signum, _frame) -> None:
        nonlocal termination, signal_number
        termination = "signaled"
        signal_number = signum

    # Install handlers before creating the detached child so no signal window
    # can orphan a newly-created Claude process group.
    old_handlers = {
        sig: signal.signal(sig, handle_signal) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    }

    def terminate_group() -> None:
        if proc is None:
            return
        pgid = proc.pid
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except (ProcessLookupError, PermissionError):
                return
            time.sleep(0.2)
        # Kill the group even if its leader exited; descendants may remain.
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def run_attempt(
        name: str,
        model: str,
        session_id: str,
        stream_name: str,
        stderr_name: str,
        resume: bool = False,
    ) -> dict:
        nonlocal proc, termination
        attempt_started = time.monotonic()
        attempt_started_utc = utc_now()
        last_activity = [attempt_started]
        # Retain only parsed terminal results and a bounded stderr tail in RAM.
        # Full byte-for-byte streams live in distinct per-attempt files.
        result_events: deque[dict] = deque(maxlen=5)
        stderr_lines: deque[str] = deque(maxlen=200)
        cmd = command_for(name, model, session_id, resume)

        def drain(pipe, output_path: Path, capture_results: bool) -> None:
            with output_path.open("w") as out:
                for line in iter(pipe.readline, ""):
                    out.write(line)
                    out.flush()
                    if capture_results:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            event = None
                        if isinstance(event, dict) and event.get("type") == "result":
                            result_events.append(event)
                    else:
                        stderr_lines.append(line[-8192:])
                    with activity_lock:
                        last_activity[0] = time.monotonic()
            pipe.close()

        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        try:
            proc.stdin.write(run_header)
            proc.stdin.close()
        except BrokenPipeError:
            pass

        t_out = threading.Thread(
            target=drain, args=(proc.stdout, job_dir / stream_name, True), daemon=True
        )
        t_err = threading.Thread(
            target=drain, args=(proc.stderr, job_dir / stderr_name, False), daemon=True
        )
        t_out.start()
        t_err.start()

        while proc.poll() is None:
            now = time.monotonic()
            with activity_lock:
                idle = now - last_activity[0]
            if termination == "signaled":
                terminate_group()
                break
            if now - started > args.timeout_s:
                termination = "timeout"
            elif idle > args.stall_s:
                termination = "stalled"
            if termination:
                terminate_group()
                break
            time.sleep(1)

        # Clean up detached descendants before another model attempt can start.
        terminate_group()
        rc = proc.wait()
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        result_event = result_events[-1] if result_events else None
        model_usage = result_event.get("modelUsage") if isinstance(result_event, dict) else None
        model_usage = model_usage if isinstance(model_usage, dict) else {}
        actual_session = (
            result_event.get("session_id") if isinstance(result_event, dict) else None
        ) or session_id
        return {
            "name": name,
            "model": model,
            "requested_session_id": session_id,
            "session_id": actual_session,
            "stream": str(job_dir / stream_name),
            "stderr": str(job_dir / stderr_name),
            "started_at": attempt_started_utc,
            "ended_at": utc_now(),
            "elapsed_s": round(time.monotonic() - attempt_started, 3),
            "returncode": rc,
            "termination": termination,
            "result_event_found": result_event is not None,
            "result_is_error": bool(result_event and result_event.get("is_error")),
            "models_observed": list(model_usage),
            "model_usage": model_usage,
            "argv": cmd + ["<task-brief-via-stdin>"],
            "_result_event": result_event,
        }

    fallback_triggered = False
    fallback_reason: str | None = None
    fallback_blocked_reason: str | None = None
    next_action: str | None = None

    # Distinct evidence files per attempt, named for the model. Two models that
    # reduce to the same prefix still get separate files.
    primary_prefix = model_evidence_prefix(args.model)
    fallback_prefix = model_evidence_prefix(args.fallback_model)
    if fallback_prefix == primary_prefix:
        fallback_prefix = f"{fallback_prefix}-fallback"

    def published_attempt(attempt: dict, include_argv: bool = False) -> dict:
        return {
            key: value
            for key, value in attempt.items()
            if key != "_result_event" and (include_argv or key != "argv")
        }

    try:
        primary = run_attempt(
            "primary",
            args.model,
            session_hint,
            f"{primary_prefix}-stream.jsonl",
            f"{primary_prefix}-stderr.log",
            resume=bool(args.resume),
        )
        attempts.append(primary)
        fallback_reason = detect_availability_error(
            Path(primary["stream"]), Path(primary["stderr"])
        )
        if fallback_reason and termination is None:
            if args.resume:
                fallback_blocked_reason = (
                    "automatic fallback is disabled for --resume because a primary session "
                    "cannot be resumed across models"
                )
                next_action = "Start a fresh job without --resume to allow a new fallback session."
            else:
                safe, detail, started_nodes, tool_names = assess_fallback_safety(
                    job_dir, Path(primary["stream"])
                )
                primary["fallback_safety"] = {
                    "safe": safe,
                    "detail": detail,
                    "slot_nodes_started": started_nodes,
                    "tool_names_observed": tool_names,
                }
                if safe and time.monotonic() - started <= args.timeout_s:
                    fallback_triggered = True
                    fallback_session_id = str(uuid.uuid4())
                    attempts.append(
                        run_attempt(
                            "fallback",
                            args.fallback_model,
                            fallback_session_id,
                            f"{fallback_prefix}-stream.jsonl",
                            f"{fallback_prefix}-stderr.log",
                        )
                    )
                elif safe:
                    termination = "timeout"
                else:
                    fallback_blocked_reason = f"automatic fallback refused: {detail}"
                    next_action = (
                        "Inspect the primary evidence and side effects, then explicitly start a fresh "
                        "run if replay is safe."
                    )
    finally:
        terminate_group()
        for sig, previous in old_handlers.items():
            signal.signal(sig, previous)

    ended_utc = utc_now()

    if fallback_blocked_reason:
        print(f"efo-orchestrate: {fallback_blocked_reason}. {next_action}", file=sys.stderr)

    command_record["attempts"] = [published_attempt(attempt, True) for attempt in attempts]
    command_record["fallback_triggered"] = fallback_triggered
    command_record["fallback_reason"] = fallback_reason
    command_record["fallback_blocked_reason"] = fallback_blocked_reason
    command_record["next_action"] = next_action
    (job_dir / "command.json").write_text(json.dumps(command_record, indent=2) + "\n")

    selected_attempt = attempts[-1]
    result_event = selected_attempt["_result_event"]
    rc = selected_attempt["returncode"]
    actual_session = selected_attempt["session_id"]
    if actual_session:
        (job_dir / "session-id").write_text(str(actual_session) + "\n")

    raw_final_value = None
    if result_event:
        raw_final_value = result_event.get("structured_output")
        if raw_final_value is None:
            raw_final_value = result_event.get("result")
            if isinstance(raw_final_value, str):
                try:
                    raw_final_value = json.loads(raw_final_value)
                except json.JSONDecodeError:
                    pass
    final_value, result_normalization = normalize_final_result(raw_final_value)
    (job_dir / "final-raw.json").write_text(
        json.dumps(raw_final_value, indent=2, ensure_ascii=False) + "\n"
    )
    (job_dir / "final.json").write_text(
        json.dumps(final_value, indent=2, ensure_ascii=False) + "\n"
    )
    final_validation_errors = validate_final_result(raw_final_value, job_dir, args.max_nodes)
    if result_normalization["applied"]:
        final_validation_errors.append(
            "final result status normalized from "
            f"'{result_normalization['reported_status']}' to "
            f"'{result_normalization['normalized_status']}': "
            + "; ".join(result_normalization["reasons"])
        )
    if fallback_blocked_reason:
        final_validation_errors.append(fallback_blocked_reason)

    wall_time_s = round(time.monotonic() - started, 3)
    metrics = build_metrics(
        job_dir,
        limits,
        {"started_at": started_utc, "ended_at": ended_utc, "wall_time_s": wall_time_s},
    )
    metrics_path = job_dir / "orchestration-metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    if metrics.get("status") == "degraded":
        warnings = metrics.get("warnings") if isinstance(metrics.get("warnings"), list) else []
        final_validation_errors.append(f"orchestration metrics degraded: {'; '.join(map(str, warnings))}")
    if isinstance(final_value, dict):
        workers = final_value.get("workers")
        workers = workers if isinstance(workers, list) else []
        if (
            final_value.get("status") in {"completed", "completed_with_warnings"}
            and workers
            and metrics.get("nodes", {}).get("started") == 0
        ):
            final_validation_errors.append(
                f"final result reports {len(workers)} workers but no slot-controller node starts were recorded"
            )
        completed_workers = sum(
            1 for worker in workers if isinstance(worker, dict) and worker.get("status") == "completed"
        )
        metrics_completed = metrics.get("nodes", {}).get("completed", 0)
        if completed_workers > metrics_completed:
            final_validation_errors.append(
                f"final result reports {completed_workers} completed workers but metrics recorded "
                f"{metrics_completed} completed nodes"
            )
    (job_dir / "final-validation-errors.json").write_text(
        json.dumps(final_validation_errors, indent=2) + "\n"
    )

    models: list[str] = []
    for attempt in attempts:
        for model in attempt["models_observed"]:
            if model not in models:
                models.append(model)
    child_error = bool(result_event and result_event.get("is_error"))
    orchestration_status = (
        raw_final_value.get("status") if isinstance(raw_final_value, dict) else None
    )
    normalized_status = final_value.get("status") if isinstance(final_value, dict) else None
    if termination:
        status = termination
    elif fallback_blocked_reason:
        status = "blocked"
    elif rc != 0 or child_error or result_event is None or final_validation_errors:
        status = "failed"
    elif normalized_status in KNOWN_STATUSES:
        status = normalized_status
    else:
        status = "completed"
    meta = {
        "status": status,
        "job_dir": str(job_dir),
        "cwd": str(cwd),
        "session_id": actual_session,
        "requested_model": args.model,
        "fallback_model": args.fallback_model,
        "resolved_executables": {"claude": str(claude_bin)},
        "attempts": [published_attempt(attempt) for attempt in attempts],
        "selected_model": selected_attempt["model"],
        "fallback_triggered": fallback_triggered,
        "fallback_reason": fallback_reason,
        "fallback_blocked_reason": fallback_blocked_reason,
        "next_action": next_action,
        "models_observed": models,
        "limits": limits,
        "started_at": started_utc,
        "ended_at": ended_utc,
        "elapsed_s": wall_time_s,
        "returncode": rc,
        "termination": termination,
        "signal_number": signal_number,
        "result_event_found": result_event is not None,
        "result_is_error": child_error,
        "orchestration_status": orchestration_status,
        "reported_status": orchestration_status,
        "normalized_status": normalized_status,
        "result_normalization": result_normalization,
        "final_validation_errors": final_validation_errors,
        "metrics_status": metrics.get("status"),
        "metrics_path": str(metrics_path),
        "metrics_summary": {
            "nodes_started": metrics.get("nodes", {}).get("started", 0),
            "nodes_completed": metrics.get("nodes", {}).get("completed", 0),
            "nodes_failed": metrics.get("nodes", {}).get("failed", 0),
            "peak_total": metrics.get("concurrency", {}).get("peak_total", 0),
            "peak_writers": metrics.get("concurrency", {}).get("peak_writers", 0),
            "max_wait_s": metrics.get("queue", {}).get("max_wait_s", 0.0),
        },
    }
    (job_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta))
    if status in {"completed", "completed_with_warnings"}:
        return 0
    if termination == "stalled":
        return 96
    if termination == "timeout":
        return 124
    if termination == "signaled":
        return 128 + (signal_number or signal.SIGTERM)
    return 2 if status == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
