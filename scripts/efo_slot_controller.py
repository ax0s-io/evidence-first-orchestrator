#!/usr/bin/env python3
"""Job-scoped cross-process worker slot controller."""
from __future__ import annotations

import argparse
import atexit
import datetime as dt
import errno
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import uuid


EMPTY_STATE = {"schema_version": 1, "nodes_started": 0, "holders": []}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _paths(job_dir: str) -> tuple[str, str, str, str]:
    state_dir = os.path.join(job_dir, ".efo-slots")
    return (
        state_dir,
        os.path.join(state_dir, "state.lock"),
        os.path.join(state_dir, "state.json"),
        os.path.join(state_dir, "events.jsonl"),
    )


def _write_state(path: str, state: dict) -> None:
    temp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(json.dumps(state, separators=(",", ":")) + "\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def _append_event(path: str, event: dict) -> None:
    with open(path, "a") as out:
        out.write(json.dumps(event, separators=(",", ":")) + "\n")
        out.flush()
        os.fsync(out.fileno())


def init_job(job_dir: str | os.PathLike[str]) -> None:
    """Create slot state for an existing job directory without clobbering it."""
    job_dir = os.fspath(job_dir)
    if not os.path.isdir(job_dir):
        raise ValueError(f"job directory does not exist: {job_dir}")
    state_dir, lock_path, state_path, events_path = _paths(job_dir)
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    os.chmod(state_dir, 0o700)
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        event_fd = os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.close(event_fd)
        if not os.path.exists(state_path):
            _write_state(state_path, dict(EMPTY_STATE))
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _load_state(state_path: str) -> tuple[dict | None, str | None]:
    try:
        with open(state_path) as source:
            state = json.load(source)
        if (
            not isinstance(state, dict)
            or state.get("schema_version") != 1
            or not isinstance(state.get("nodes_started"), int)
            or isinstance(state.get("nodes_started"), bool)
            or state["nodes_started"] < 0
            or not isinstance(state.get("holders"), list)
        ):
            raise ValueError("invalid state shape")
        return state, None
    except Exception as exc:
        return None, f"state.json is corrupt or unavailable ({type(exc).__name__}: {exc})"


def _pid_alive(value: object) -> bool:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return False
    try:
        os.kill(value, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except OSError as exc:
        return exc.errno == errno.EPERM


def _active_writers(holders: list[dict]) -> int:
    return sum(1 for holder in holders if holder.get("lane") == "writer")


def _limits_from_env() -> dict[str, int]:
    def integer(name: str, default: int, label: str) -> int:
        raw = os.environ.get(name, str(default))
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"{label} must be an integer, got {raw!r}") from None

    workers = integer("EFO_MAX_WORKERS", 4, "max_workers")
    writers = integer("EFO_MAX_WRITERS", 2, "max_writers")
    nodes = integer("EFO_MAX_NODES", 12, "max_nodes")
    if not 1 <= workers <= 12:
        raise ValueError(f"max_workers must be in 1..12, got {workers}")
    if not 0 <= writers <= workers:
        raise ValueError(f"max_writers must be in 0..{workers}, got {writers}")
    if not workers <= nodes <= 100:
        raise ValueError(f"max_nodes must be in {workers}..100, got {nodes}")
    return {"max_workers": workers, "max_writers": writers, "max_nodes": nodes}


def _positive_float(name: str, default: float, label: str) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{label} must be a number, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{label} must be greater than zero, got {value}")
    return value


def _common(node_id: str, vendor: str, lane: str, label: str, pid: int) -> dict:
    return {
        "ts": utc_now(),
        "node_id": node_id,
        "vendor": vendor,
        "lane": lane,
        "label": label,
        "pid": pid,
    }


class SlotRun:
    def __init__(self, job_dir: str, vendor: str, lane: str, label: str, limits: dict[str, int]):
        self.job_dir = job_dir
        self.vendor = vendor
        self.lane = lane
        self.label = label
        self.limits = limits
        self.node_id = uuid.uuid4().hex[:12]
        self.pid = os.getpid()
        self.requested_wall = utc_now()
        self.requested = time.monotonic()
        self.acquired = False
        self.released = False
        self.child_rc = 1
        self.child_signal: int | None = None
        self.started_child_at: float | None = None
        _, self.lock_path, self.state_path, self.events_path = _paths(job_dir)

    def _event(self, event_type: str, **extra: object) -> dict:
        event = _common(self.node_id, self.vendor, self.lane, self.label, self.pid)
        event["event"] = event_type
        event.update(extra)
        return event

    def acquire(self, queue_timeout: float, poll_s: float) -> int | None:
        lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            _append_event(self.events_path, self._event("queued", requested_at=self.requested_wall))
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

        while True:
            lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                state, corrupt_detail = _load_state(self.state_path)
                if corrupt_detail:
                    detail = f"{corrupt_detail}; admission denied and state preserved for manual recovery"
                    _append_event(self.events_path, self._event("state_corrupt", detail=detail))
                    print(f"efo-slot-controller: {detail}", file=sys.stderr)
                    return 70
                assert state is not None

                retained: list[dict] = []
                stale_holders: list[dict] = []
                for holder in state["holders"]:
                    if isinstance(holder, dict) and _pid_alive(holder.get("pid")):
                        retained.append(holder)
                        continue
                    stale = holder if isinstance(holder, dict) else {"invalid_holder": holder}
                    stale_holders.append(stale)
                remaining = list(state["holders"])
                for stale in stale_holders:
                    for index, holder in enumerate(remaining):
                        if holder is stale or holder == stale:
                            remaining.pop(index)
                            break
                    state["holders"] = remaining
                    _write_state(self.state_path, state)
                    stale_event = _common(
                        str(stale.get("node_id", self.node_id)),
                        str(stale.get("vendor", self.vendor)),
                        str(stale.get("lane", self.lane)),
                        str(stale.get("label", self.label)),
                        stale.get("pid") if isinstance(stale.get("pid"), int) else self.pid,
                    )
                    stale_event.update({
                        "event": "pruned",
                        "stale_holder": stale,
                        "active_total": len(remaining),
                        "active_writers": _active_writers([h for h in remaining if isinstance(h, dict)]),
                    })
                    _append_event(self.events_path, stale_event)
                state["holders"] = retained

                wait_s = time.monotonic() - self.requested
                if state["nodes_started"] >= self.limits["max_nodes"]:
                    _append_event(
                        self.events_path,
                        self._event("denied", reason="node_cap", wait_s=round(wait_s, 6), limits=self.limits),
                    )
                    print(
                        f"efo-slot-controller: cumulative node cap {self.limits['max_nodes']} reached",
                        file=sys.stderr,
                    )
                    return 78

                holders = state["holders"]
                if (
                    len(holders) < self.limits["max_workers"]
                    and (self.lane != "writer" or _active_writers(holders) < self.limits["max_writers"])
                ):
                    holder = {
                        "node_id": self.node_id,
                        "pid": self.pid,
                        "vendor": self.vendor,
                        "lane": self.lane,
                        "label": self.label,
                        "acquired_at": utc_now(),
                        "wait_s": round(wait_s, 6),
                    }
                    holders.append(holder)
                    state["nodes_started"] += 1
                    _write_state(self.state_path, state)
                    self.acquired = True
                    _append_event(
                        self.events_path,
                        self._event(
                            "started",
                            wait_s=round(wait_s, 6),
                            active_total=len(holders),
                            active_writers=_active_writers(holders),
                            nodes_started=state["nodes_started"],
                            limits=self.limits,
                        ),
                    )
                    return None

                if wait_s >= queue_timeout:
                    _append_event(
                        self.events_path,
                        self._event("denied", reason="queue_timeout", wait_s=round(wait_s, 6), limits=self.limits),
                    )
                    print(
                        f"efo-slot-controller: slot queue timed out after {wait_s:.3f}s",
                        file=sys.stderr,
                    )
                    return 75
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            time.sleep(poll_s)

    def release(self) -> None:
        if not self.acquired or self.released:
            return
        self.released = True
        duration = 0.0 if self.started_child_at is None else time.monotonic() - self.started_child_at
        deadline = time.monotonic() + 10
        try:
            lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:
            try:
                _append_event(
                    self.events_path,
                    self._event(
                        "finished",
                        rc=self.child_rc,
                        signal=self.child_signal,
                        duration_s=round(duration, 6),
                        active_total=-1,
                        active_writers=-1,
                        release_degraded=True,
                    ),
                )
            except OSError:
                pass
            return
        locked = False
        try:
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    time.sleep(0.05)
            if not locked:
                _append_event(
                    self.events_path,
                    self._event(
                        "finished",
                        rc=self.child_rc,
                        signal=self.child_signal,
                        duration_s=round(duration, 6),
                        active_total=-1,
                        active_writers=-1,
                        release_degraded=True,
                    ),
                )
                return
            state, corrupt_detail = _load_state(self.state_path)
            if corrupt_detail:
                detail = f"{corrupt_detail}; release degraded and state preserved for manual recovery"
                _append_event(self.events_path, self._event("state_corrupt", detail=detail))
                _append_event(
                    self.events_path,
                    self._event(
                        "finished",
                        rc=self.child_rc,
                        signal=self.child_signal,
                        duration_s=round(duration, 6),
                        active_total=-1,
                        active_writers=-1,
                        release_degraded=True,
                    ),
                )
                return
            assert state is not None
            state["holders"] = [h for h in state["holders"] if h.get("node_id") != self.node_id]
            _write_state(self.state_path, state)
            _append_event(
                self.events_path,
                self._event(
                    "finished",
                    rc=self.child_rc,
                    signal=self.child_signal,
                    duration_s=round(duration, 6),
                    active_total=len(state["holders"]),
                    active_writers=_active_writers(state["holders"]),
                ),
            )
        except Exception:
            try:
                _append_event(
                    self.events_path,
                    self._event(
                        "finished",
                        rc=self.child_rc,
                        signal=self.child_signal,
                        duration_s=round(duration, 6),
                        active_total=-1,
                        active_writers=-1,
                        release_degraded=True,
                    ),
                )
            except OSError:
                pass
        finally:
            if locked:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def run_child(args: argparse.Namespace) -> int:
    job_dir = args.job_dir or os.environ.get("EFO_ORCHESTRATION_JOB_DIR")
    if not job_dir:
        print("efo-slot-controller: --job-dir or EFO_ORCHESTRATION_JOB_DIR is required", file=sys.stderr)
        return 2
    job_dir = os.path.abspath(os.path.expanduser(job_dir))
    if not os.path.isdir(job_dir):
        print(f"efo-slot-controller: job directory does not exist: {job_dir}", file=sys.stderr)
        return 2
    if not getattr(args, "command_separator_present", False):
        print("efo-slot-controller: child command must follow --", file=sys.stderr)
        return 2
    if not args.command:
        print("efo-slot-controller: child command after -- is required", file=sys.stderr)
        return 2
    try:
        limits = _limits_from_env()
        queue_timeout = _positive_float("EFO_SLOT_QUEUE_TIMEOUT_S", 1800, "queue_timeout_s")
        poll_s = _positive_float("EFO_SLOT_POLL_S", 0.25, "poll_s")
        state_dir, _, _, _ = _paths(job_dir)
        if not os.path.isdir(state_dir):
            init_job(job_dir)
        else:
            os.chmod(state_dir, 0o700)
    except (ValueError, OSError) as exc:
        print(f"efo-slot-controller: {exc}", file=sys.stderr)
        return 2

    label = args.label or os.path.basename(args.command[0])
    slot = SlotRun(job_dir, args.vendor, args.lane, label, limits)
    atexit.register(slot.release)
    denial = slot.acquire(queue_timeout, poll_s)
    if denial is not None:
        return denial

    proc: subprocess.Popen | None = None
    forwarded_signal: int | None = None
    forwarded_at: float | None = None

    def handle_signal(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal, forwarded_at
        if forwarded_signal is None:
            forwarded_signal = signum
            forwarded_at = time.monotonic()
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signum)
            except (ProcessLookupError, PermissionError):
                pass

    previous = {sig: signal.signal(sig, handle_signal) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        slot.started_child_at = time.monotonic()
        proc = subprocess.Popen(args.command, start_new_session=True)
        if forwarded_signal is not None:
            try:
                os.killpg(proc.pid, forwarded_signal)
            except (ProcessLookupError, PermissionError):
                pass
        while True:
            try:
                rc = proc.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if forwarded_at is not None and time.monotonic() - forwarded_at >= 10:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    forwarded_at = None
        slot.child_rc = rc
        slot.child_signal = forwarded_signal if forwarded_signal is not None else (-rc if rc < 0 else None)
    except BaseException:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait()
        raise
    finally:
        slot.release()
        for sig, old_handler in previous.items():
            signal.signal(sig, old_handler)

    if rc < 0:
        child_signal = -rc
        signal.signal(child_signal, signal.SIG_DFL)
        os.kill(os.getpid(), child_signal)
        os._exit(128 + child_signal)
    return rc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="efo-slot-controller")
    subparsers = parser.add_subparsers(dest="action", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--job-dir", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--job-dir", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--vendor", required=True, choices=["codex", "grok"])
    run_parser.add_argument("--lane", required=True, choices=["reader", "writer"])
    run_parser.add_argument("--job-dir")
    run_parser.add_argument("--label")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.action == "run":
        args.command_separator_present = bool(args.command and args.command[0] == "--")
        if args.command_separator_present:
            args.command = args.command[1:]
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.action == "run":
        return run_child(args)
    job_dir = os.path.abspath(os.path.expanduser(args.job_dir))
    if not os.path.isdir(job_dir):
        print(f"efo-slot-controller: job directory does not exist: {job_dir}", file=sys.stderr)
        return 2
    try:
        init_job(job_dir)
        if args.action == "status":
            _, lock_path, state_path, _ = _paths(job_dir)
            lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                with open(state_path) as source:
                    print(json.dumps(json.load(source), separators=(",", ":")))
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"efo-slot-controller: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
