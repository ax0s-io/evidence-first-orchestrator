from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
CONTROLLER = SCRIPTS / "prime_slot_controller.py"
METRICS = SCRIPTS / "prime_metrics.py"
LAUNCHER = SCRIPTS / "prime_fable_orchestrate.py"
CODEX_WRAPPER = SCRIPTS / "prime_codex_leg.sh"
GROK_WRAPPER = SCRIPTS / "prime_grok_leg.sh"
sys.path.insert(0, str(SCRIPTS))
from prime_metrics import build_metrics  # noqa: E402
from prime_fable_orchestrate import (  # noqa: E402
    USAGE_CREDIT_RESULT,
    assess_fallback_safety,
    detect_availability_error,
    is_usage_credit_result,
    validate_final_result,
)


LIMITS = {"max_workers": 4, "max_writers": 2, "max_nodes": 12}


def read_events(job: Path) -> list[dict]:
    path = job / ".prime-slots" / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


def wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def controller_cmd(job: Path, lane: str = "reader", command: list[str] | None = None) -> list[str]:
    return [
        sys.executable,
        str(CONTROLLER),
        "run",
        "--vendor",
        "codex",
        "--lane",
        lane,
        "--job-dir",
        str(job),
        "--",
        *(command or ["/bin/sh", "-c", "exit 0"]),
    ]


class SlotControllerTests(unittest.TestCase):
    def test_slot_acquisition_records_lifecycle_and_releases(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            result = subprocess.run(controller_cmd(job), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            events = read_events(job)
            self.assertEqual([e["event"] for e in events], ["queued", "started", "finished"])
            state = json.loads((job / ".prime-slots" / "state.json").read_text())
            self.assertEqual(state["holders"], [])
            self.assertEqual(state["nodes_started"], 1)

    def test_child_exit_status_is_propagated(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(controller_cmd(Path(td), command=["/bin/sh", "-c", "exit 7"]))
            self.assertEqual(result.returncode, 7)

    def test_combined_worker_cap_queues_third_process(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            env = os.environ.copy()
            env.update(PRIME_MAX_WORKERS="2", PRIME_MAX_WRITERS="2", PRIME_MAX_NODES="6", PRIME_SLOT_POLL_S="0.02")
            first = subprocess.Popen(controller_cmd(job, command=["/bin/sh", "-c", "sleep 1"]) , env=env)
            second = subprocess.Popen(controller_cmd(job, command=["/bin/sh", "-c", "sleep 1"]), env=env)
            self.assertTrue(wait_for(lambda: sum(e["event"] == "started" for e in read_events(job)) == 2))
            third = subprocess.Popen(controller_cmd(job, command=["/bin/sh", "-c", "sleep 0.05"]), env=env)
            self.assertTrue(wait_for(lambda: sum(e["event"] == "queued" for e in read_events(job)) == 3))
            time.sleep(0.1)
            self.assertEqual(sum(e["event"] == "started" for e in read_events(job)), 2)
            for proc in (first, second, third):
                self.assertEqual(proc.wait(timeout=4), 0)
            metrics = build_metrics(job, {"max_workers": 2, "max_writers": 2, "max_nodes": 6}, {})
            self.assertLessEqual(metrics["concurrency"]["peak_total"], 2)

    def test_writer_cap_serializes_writers_but_allows_reader(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            env = os.environ.copy()
            env.update(PRIME_MAX_WORKERS="4", PRIME_MAX_WRITERS="1", PRIME_MAX_NODES="6", PRIME_SLOT_POLL_S="0.02")
            writer_one = subprocess.Popen(controller_cmd(job, "writer", ["/bin/sh", "-c", "sleep 0.8"]), env=env)
            self.assertTrue(wait_for(lambda: sum(e["event"] == "started" for e in read_events(job)) == 1))
            writer_two = subprocess.Popen(controller_cmd(job, "writer", ["/bin/sh", "-c", "sleep 0.05"]), env=env)
            reader = subprocess.Popen(controller_cmd(job, "reader", ["/bin/sh", "-c", "sleep 0.2"]), env=env)
            self.assertTrue(wait_for(lambda: any(e["event"] == "started" and e["lane"] == "reader" for e in read_events(job))))
            events = read_events(job)
            self.assertEqual(sum(e["event"] == "started" and e["lane"] == "writer" for e in events), 1)
            for proc in (writer_one, writer_two, reader):
                self.assertEqual(proc.wait(timeout=4), 0)
            metrics = build_metrics(job, {"max_workers": 4, "max_writers": 1, "max_nodes": 6}, {})
            self.assertEqual(metrics["concurrency"]["peak_writers"], 1)
            self.assertGreaterEqual(metrics["concurrency"]["peak_total"], 2)

    def test_zero_writer_cap_allows_reader_and_times_out_writer(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            reader_marker = job / "reader-ran"
            writer_marker = job / "writer-ran"
            env = os.environ.copy()
            env.update(
                PRIME_MAX_WORKERS="2",
                PRIME_MAX_WRITERS="0",
                PRIME_MAX_NODES="4",
                PRIME_SLOT_QUEUE_TIMEOUT_S="0.08",
                PRIME_SLOT_POLL_S="0.01",
            )
            reader = subprocess.run(
                controller_cmd(job, "reader", ["/usr/bin/touch", str(reader_marker)]),
                env=env,
                capture_output=True,
                text=True,
            )
            writer = subprocess.run(
                controller_cmd(job, "writer", ["/usr/bin/touch", str(writer_marker)]),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(reader.returncode, 0, reader.stderr)
            self.assertEqual(writer.returncode, 75, writer.stderr)
            self.assertTrue(reader_marker.exists())
            self.assertFalse(writer_marker.exists())
            events = read_events(job)
            self.assertEqual(sum(e["event"] == "started" and e["lane"] == "reader" for e in events), 1)
            self.assertFalse(any(e["event"] == "started" and e["lane"] == "writer" for e in events))
            self.assertTrue(any(e.get("event") == "denied" and e.get("reason") == "queue_timeout" and e.get("lane") == "writer" for e in events))

    def test_cumulative_node_cap_denies_third_sequential_start(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            env = os.environ.copy()
            env.update(PRIME_MAX_WORKERS="2", PRIME_MAX_WRITERS="1", PRIME_MAX_NODES="2")
            for _ in range(2):
                self.assertEqual(subprocess.run(controller_cmd(job), env=env).returncode, 0)
            started = time.monotonic()
            result = subprocess.run(controller_cmd(job), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 78)
            self.assertLess(time.monotonic() - started, 5)
            self.assertTrue(any(e.get("event") == "denied" and e.get("reason") == "node_cap" for e in read_events(job)))

    def test_corrupt_state_fails_closed_without_reopening_node_cap_or_running_child(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            env = os.environ.copy()
            env.update(PRIME_MAX_WORKERS="1", PRIME_MAX_WRITERS="1", PRIME_MAX_NODES="1")
            self.assertEqual(subprocess.run(controller_cmd(job), env=env).returncode, 0)
            state_path = job / ".prime-slots" / "state.json"
            corrupt_bytes = b'{"schema_version":1,"nodes_started":'
            state_path.write_bytes(corrupt_bytes)
            child_marker = job / "child-ran"

            result = subprocess.run(
                controller_cmd(job, command=["/usr/bin/touch", str(child_marker)]),
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 70, result.stderr)
            self.assertIn("admission denied", result.stderr)
            self.assertFalse(child_marker.exists())
            self.assertEqual(state_path.read_bytes(), corrupt_bytes)
            events = read_events(job)
            self.assertEqual(sum(event.get("event") == "started" for event in events), 1)
            warning = events[-1]
            self.assertEqual(warning.get("event"), "state_corrupt")
            self.assertIn("state preserved", warning.get("detail", ""))

    def test_missing_state_after_init_fails_closed_and_is_not_recreated(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            subprocess.run([sys.executable, str(CONTROLLER), "init", "--job-dir", str(job)], check=True)
            state_path = job / ".prime-slots" / "state.json"
            state_path.unlink()

            result = subprocess.run(controller_cmd(job), capture_output=True, text=True)

            self.assertEqual(result.returncode, 70, result.stderr)
            self.assertFalse(state_path.exists())
            self.assertFalse(any(event.get("event") == "started" for event in read_events(job)))

    def test_release_preserves_state_corruption_and_records_degraded_finish(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            release_marker = job / "release-child"
            command = ["/bin/sh", "-c", f"while [ ! -e '{release_marker}' ]; do sleep 0.02; done"]
            controller = subprocess.Popen(controller_cmd(job, command=command))
            self.assertTrue(wait_for(lambda: any(e.get("event") == "started" for e in read_events(job))))
            state_path = job / ".prime-slots" / "state.json"
            corrupt_bytes = b"not-json\n"
            state_path.write_bytes(corrupt_bytes)
            release_marker.touch()

            self.assertEqual(controller.wait(timeout=5), 0)
            self.assertEqual(state_path.read_bytes(), corrupt_bytes)
            events = read_events(job)
            self.assertEqual(events[-2].get("event"), "state_corrupt")
            self.assertEqual(events[-1].get("event"), "finished")
            self.assertTrue(events[-1].get("release_degraded"))
            self.assertEqual(events[-1].get("active_total"), -1)

    def test_stale_holder_is_pruned_before_acquisition(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            subprocess.run([sys.executable, str(CONTROLLER), "init", "--job-dir", str(job)], check=True)
            dead = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
            dead_pid = dead.pid
            dead.wait()
            stale = {
                "node_id": "stale-node",
                "pid": dead_pid,
                "vendor": "grok",
                "lane": "reader",
                "label": "stale",
                "acquired_at": "2026-01-01T00:00:00Z",
                "wait_s": 0.0,
            }
            state_path = job / ".prime-slots" / "state.json"
            state_path.write_text(json.dumps({"schema_version": 1, "nodes_started": 0, "holders": [stale]}))
            env = os.environ.copy()
            env.update(PRIME_MAX_WORKERS="1", PRIME_MAX_WRITERS="1", PRIME_MAX_NODES="2")
            result = subprocess.run(controller_cmd(job), env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(any(e.get("event") == "pruned" and e.get("stale_holder", {}).get("node_id") == "stale-node" for e in read_events(job)))

    def test_signal_cleanup_kills_child_group_and_releases_holder(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            child_pid_path = job / "child.pid"
            command = ["/bin/sh", "-c", f"echo $$ > '{child_pid_path}'; exec sleep 30"]
            controller = subprocess.Popen(controller_cmd(job, command=command))
            self.assertTrue(wait_for(lambda: any(e["event"] == "started" for e in read_events(job))))
            self.assertTrue(wait_for(child_pid_path.exists))
            child_pid = int(child_pid_path.read_text())
            controller.send_signal(signal.SIGTERM)
            self.assertEqual(controller.wait(timeout=15), -signal.SIGTERM)
            self.assertTrue(wait_for(lambda: not self._pid_alive(child_pid), timeout=2))
            state = json.loads((job / ".prime-slots" / "state.json").read_text())
            self.assertEqual(state["holders"], [])
            self.assertTrue(any(e["event"] == "finished" for e in read_events(job)))

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def test_environment_limit_validation_rejects_bad_values(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            cases = [
                {"PRIME_MAX_WORKERS": "0"},
                {"PRIME_MAX_WORKERS": "13"},
                {"PRIME_MAX_WORKERS": "nope"},
                {"PRIME_MAX_WORKERS": "2", "PRIME_MAX_WRITERS": "3"},
            ]
            for updates in cases:
                with self.subTest(updates=updates):
                    env = os.environ.copy()
                    env.update(PRIME_MAX_WORKERS="4", PRIME_MAX_WRITERS="2", PRIME_MAX_NODES="12")
                    env.update(updates)
                    result = subprocess.run(controller_cmd(job), env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("prime-slot-controller:", result.stderr)


class MetricsTests(unittest.TestCase):
    @staticmethod
    def event(ts: str, event: str, node: str, vendor: str, lane: str, **extra) -> dict:
        value = {"ts": ts, "event": event, "node_id": node, "vendor": vendor, "lane": lane, "label": node, "pid": 100}
        value.update(extra)
        return value

    def test_metrics_calculation_for_known_interleaving(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            slots = job / ".prime-slots"
            slots.mkdir()
            events = [
                self.event("2026-01-01T00:00:00Z", "queued", "a", "codex", "reader"),
                self.event("2026-01-01T00:00:01Z", "started", "a", "codex", "reader", wait_s=0.0, active_total=1, active_writers=0),
                self.event("2026-01-01T00:00:02Z", "queued", "b", "grok", "writer"),
                self.event("2026-01-01T00:00:03Z", "started", "b", "grok", "writer", wait_s=0.1, active_total=2, active_writers=1),
                self.event("2026-01-01T00:00:04Z", "started", "c", "codex", "writer", wait_s=0.3, active_total=3, active_writers=2),
                self.event("2026-01-01T00:00:05Z", "finished", "a", "codex", "reader", rc=0, signal=None, active_total=2, active_writers=2),
                self.event("2026-01-01T00:00:06Z", "finished", "b", "grok", "writer", rc=2, signal=None, active_total=1, active_writers=1),
                self.event("2026-01-01T00:00:07Z", "finished", "c", "codex", "writer", rc=-15, signal=15, active_total=0, active_writers=0),
            ]
            (slots / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
            metrics = build_metrics(job, LIMITS, {"started_at": "x", "ended_at": "y", "wall_time_s": 7})
            self.assertEqual(metrics["concurrency"]["peak_total"], 3)
            self.assertEqual(metrics["concurrency"]["peak_writers"], 2)
            self.assertEqual(metrics["nodes"], {"started": 3, "completed": 1, "failed": 1, "signaled": 1, "denied": 0, "unterminated": 0})
            self.assertEqual(metrics["vendors"]["codex"], {"started": 2, "completed": 1, "failed": 1})
            self.assertEqual(metrics["vendors"]["grok"], {"started": 1, "completed": 0, "failed": 1})
            self.assertEqual(metrics["lanes"]["reader"], {"started": 1, "completed": 1, "failed": 0})
            self.assertEqual(metrics["lanes"]["writer"], {"started": 2, "completed": 0, "failed": 2})
            self.assertEqual(metrics["queue"], {"queued_nodes": 2, "waited_nodes": 2, "total_wait_s": 0.4, "max_wait_s": 0.3, "mean_wait_s": 0.2})

    def test_empty_events_produce_ok_all_zero_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            slots = job / ".prime-slots"
            slots.mkdir()
            (slots / "events.jsonl").write_text("")
            metrics = build_metrics(job, LIMITS, {})
            self.assertEqual(metrics["status"], "ok")
            self.assertEqual(metrics["warnings"], [])
            self.assertTrue(all(value == 0 for value in metrics["nodes"].values()))
            self.assertEqual(metrics["concurrency"]["peak_total"], 0)

    def test_metrics_degraded_and_torn_trailing_cases(self):
        with tempfile.TemporaryDirectory() as td:
            missing = build_metrics(Path(td), LIMITS, {})
            self.assertEqual(missing["status"], "degraded")
            self.assertFalse(missing["events"]["present"])
        with tempfile.TemporaryDirectory() as td:
            job = Path(td); slots = job / ".prime-slots"; slots.mkdir()
            valid = self.event("2026-01-01T00:00:00Z", "queued", "a", "codex", "reader")
            (slots / "events.jsonl").write_text(json.dumps(valid) + "\nnot-json\n" + json.dumps(valid) + "\n")
            self.assertEqual(build_metrics(job, LIMITS, {})["status"], "degraded")
        with tempfile.TemporaryDirectory() as td:
            job = Path(td); slots = job / ".prime-slots"; slots.mkdir()
            valid = self.event("2026-01-01T00:00:00Z", "queued", "a", "codex", "reader")
            (slots / "events.jsonl").write_text(json.dumps(valid) + "\n{")
            torn = build_metrics(job, LIMITS, {})
            self.assertEqual(torn["status"], "ok_with_warnings")
            self.assertIn("torn trailing write", torn["warnings"][0])
        with tempfile.TemporaryDirectory() as td:
            job = Path(td); slots = job / ".prime-slots"; slots.mkdir()
            finished = self.event("2026-01-01T00:00:00Z", "finished", "a", "codex", "reader", rc=0, signal=None, active_total=0, active_writers=0)
            (slots / "events.jsonl").write_text(json.dumps(finished) + "\n")
            self.assertEqual(build_metrics(job, LIMITS, {})["status"], "degraded")
        with tempfile.TemporaryDirectory() as td:
            job = Path(td); slots = job / ".prime-slots"; slots.mkdir()
            starts = [self.event(f"2026-01-01T00:00:0{i}Z", "started", str(i), "codex", "reader", wait_s=0, active_total=i, active_writers=0) for i in range(1, 3)]
            finishes = [self.event(f"2026-01-01T00:00:1{i}Z", "finished", str(i), "codex", "reader", rc=0, signal=None, active_total=2-i, active_writers=0) for i in range(1, 3)]
            (slots / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in starts + finishes))
            metrics = build_metrics(job, {"max_workers": 1, "max_writers": 1, "max_nodes": 2}, {})
            self.assertEqual(metrics["status"], "degraded")
            self.assertEqual(metrics["concurrency"]["peak_total"], 2)


class WrapperTests(unittest.TestCase):
    def run_rejection(self, wrapper: Path, args: list[str], job: Path | None, prefix: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        with tempfile.TemporaryDirectory() as path_dir:
            env["PATH"] = path_dir
            if job is None:
                env.pop("PRIME_ORCHESTRATION_JOB_DIR", None)
            else:
                env["PRIME_ORCHESTRATION_JOB_DIR"] = str(job)
            result = subprocess.run(["/bin/bash", str(wrapper), *args], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, (args, result.stderr))
        self.assertTrue(result.stderr.startswith(prefix), result.stderr)
        return result

    def test_wrapper_argument_rejections_never_reach_canonical_binaries(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            nonexistent = job / "missing"
            common = [
                ([], job),
                (["--lane=writer"], job),
                (["--lane", "bogus"], job),
                (["--lane", "reader", "--lane", "writer"], job),
                (["--lane", "reader"], None),
                (["--lane", "reader"], nonexistent),
            ]
            for wrapper, prefix in ((CODEX_WRAPPER, "prime-codex-leg:"), (GROK_WRAPPER, "prime-grok-leg:")):
                for args, selected_job in common:
                    with self.subTest(wrapper=wrapper.name, args=args, job=selected_job):
                        self.run_rejection(wrapper, args, selected_job, prefix)
            grok_cases = [
                ["--lane", "reader"],
                ["--lane", "reader", "--cwd", "/"],
                ["--lane", "reader", "--cwd", str(Path.home())],
                ["--lane", "reader", "--cwd", str(job), "--sandbox", "off"],
                ["--lane", "reader", "--cwd", str(job), "--profile", "full"],
                ["--lane", "reader", "--cwd", str(job), "--profile", "write"],
            ]
            for args in grok_cases:
                with self.subTest(grok=args):
                    self.run_rejection(GROK_WRAPPER, args, job, "prime-grok-leg:")
            self.run_rejection(CODEX_WRAPPER, ["--lane", "reader", "-s", "workspace-write"], job, "prime-codex-leg:")

    def test_lane_is_stripped_and_forwarded_argument_order_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = root / "job"; job.mkdir()
            stub = root / "slot_stub.py"
            output = root / "argv.json"
            stub.write_text("import json, os, sys\nopen(os.environ['STUB_OUT'], 'w').write(json.dumps(sys.argv[1:]))\n")
            # Stub the canonical adapters too, so the suite stays hermetic on a
            # runner where codex-leg/grok-leg are not installed.
            codex_leg = root / "codex-leg"
            grok_leg = root / "grok-leg"
            for adapter in (codex_leg, grok_leg):
                adapter.write_text("#!/bin/sh\nexit 0\n")
                adapter.chmod(0o755)
            env = os.environ.copy()
            env.update(
                PRIME_ORCHESTRATION_JOB_DIR=str(job),
                PRIME_ORCHESTRATION_TEST="1",
                PRIME_SLOT_CONTROLLER=str(stub),
                STUB_OUT=str(output),
                PRIME_CODEX_LEG_BIN=str(codex_leg),
                PRIME_GROK_LEG_BIN=str(grok_leg),
            )
            codex_args = ["--stream", "one", "--lane", "writer", "--stall-s", "9", "--", "-s", "workspace-write", "brief"]
            result = subprocess.run(["/bin/bash", str(CODEX_WRAPPER), *codex_args], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = json.loads(output.read_text())
            canonical = recorded.index(str(codex_leg.resolve()))
            self.assertEqual(recorded[canonical + 1 :], ["--stream", "one", "--stall-s", "9", "--", "-s", "workspace-write", "brief"])
            grok_args = ["--lane", "reader", "--profile", "scout", "--cwd", str(job), "--stream", "two"]
            result = subprocess.run(["/bin/bash", str(GROK_WRAPPER), *grok_args], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = json.loads(output.read_text())
            canonical = recorded.index(str(grok_leg.resolve()))
            self.assertEqual(recorded[canonical + 1 :], ["--profile", "scout", "--cwd", str(job), "--stream", "two"])


class LauncherTests(unittest.TestCase):
    def test_completed_with_warnings_with_failed_validation_item_is_rejected_and_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            value = {
                "status": "completed_with_warnings",
                "summary": "claimed success despite a failed check",
                "fan_in": {"expected": 0, "received": 0, "complete": True},
                "workers": [],
                "validation": [
                    {"command": "check-one", "status": "passed", "evidence": "ok"},
                    {"command": "check-two", "status": "failed", "evidence": "failed"},
                ],
                "changed_files": [],
                "risks": [],
                "next_actions": [],
            }
            errors = validate_final_result(value, Path(td), 12)
            self.assertIn(
                "success status cannot coexist with a failed validation item",
                errors,
            )

    def run_launcher(self, parent: Path, extra: list[str]) -> subprocess.CompletedProcess:
        job = parent / "job"
        # A dry run resolves the CLI without executing it, so a stub is enough.
        # Pointing at one keeps these cases hermetic: they must fail on the flag
        # or succeed on the dry run, never on whether this machine has `claude`.
        stub = parent / "claude"
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o700)
        env = os.environ.copy()
        env["PRIME_CLAUDE_BIN"] = str(stub)
        return subprocess.run(
            [sys.executable, str(LAUNCHER), "--dry-run", "--job-dir", str(job), "--cwd", str(SKILL_DIR), *extra],
            input="test brief\n",
            capture_output=True,
            text=True,
            env=env,
        )

    @staticmethod
    def completed_result() -> dict:
        return {
            "type": "result",
            "is_error": False,
            "structured_output": {
                "status": "completed",
                "summary": "stub completed",
                "fan_in": {"expected": 0, "received": 0, "complete": True},
                "workers": [],
                "validation": [
                    {"command": "stub", "status": "passed", "evidence": "stub"}
                ],
                "changed_files": [],
                "risks": [],
                "next_actions": [],
            },
            "modelUsage": {"claude-opus-5": {"inputTokens": 1, "outputTokens": 1}},
        }

    @staticmethod
    def quota_result() -> dict:
        return {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": USAGE_CREDIT_RESULT,
            "modelUsage": {"claude-fable-5": {"inputTokens": 1, "outputTokens": 1}},
        }

    def run_stub_launcher(
        self,
        parent: Path,
        fable_events: list[dict],
        *,
        fable_rc: int = 0,
        opus_events: list[dict] | None = None,
        opus_rc: int = 0,
        extra: list[str] | None = None,
    ) -> tuple[subprocess.CompletedProcess, Path, list[dict]]:
        job = parent / "job"
        calls_path = parent / "claude-calls.jsonl"
        stub = parent / "claude-stub.py"
        source = f"""#!/usr/bin/env python3
import json
from pathlib import Path
import sys
args = sys.argv[1:]
model = args[args.index('--model') + 1]
if '--session-id' in args:
    session_id = args[args.index('--session-id') + 1]
else:
    session_id = args[args.index('--resume') + 1]
with Path({str(calls_path)!r}).open('a') as out:
    out.write(json.dumps({{'model': model, 'session_id': session_id, 'argv': args}}) + '\\n')
events = {fable_events!r} if model == 'claude-fable-5' else {(opus_events or [])!r}
for original in events:
    event = dict(original)
    if event.get('type') == 'result':
        event.setdefault('session_id', session_id)
    print(json.dumps(event), flush=True)
raise SystemExit({fable_rc!r} if model == 'claude-fable-5' else {opus_rc!r})
"""
        stub.write_text(source)
        stub.chmod(0o700)
        env = os.environ.copy()
        env.update(PRIME_FABLE_ORCHESTRATION_TEST="1", PRIME_CLAUDE_BIN=str(stub))
        result = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--job-dir",
                str(job),
                "--cwd",
                str(SKILL_DIR),
                *(extra or []),
            ],
            input="test brief\n",
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
        return result, job, calls

    def test_launcher_flag_validation_names_invalid_flag(self):
        cases = [
            (["--max-workers", "0"], "--max-workers"),
            (["--max-workers", "13"], "--max-workers"),
            (["--max-workers", "4", "--max-writers", "5"], "--max-writers"),
            (["--max-workers", "4", "--max-nodes", "3"], "--max-nodes"),
            (["--max-nodes", "101"], "--max-nodes"),
        ]
        for args, flag in cases:
            with tempfile.TemporaryDirectory() as td, self.subTest(args=args):
                result = self.run_launcher(Path(td), args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(flag, result.stderr)

    def test_launcher_dry_run_persists_limits_command_and_dynamic_schema(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            result = self.run_launcher(parent, ["--max-workers", "6", "--max-writers", "2", "--max-nodes", "20"])
            self.assertEqual(result.returncode, 0, result.stderr)
            job = parent / "job"
            limits = {"max_workers": 6, "max_writers": 2, "max_nodes": 20}
            self.assertEqual(json.loads((job / "limits.json").read_text()), limits)
            command = json.loads((job / "command.json").read_text())
            self.assertEqual(command["limits"], limits)
            self.assertEqual(command["env_exported"]["PRIME_MAX_NODES"], "20")
            self.assertEqual(command["env_exported"]["PRIME_ORCHESTRATION_JOB_DIR"], str(job.resolve()))
            self.assertEqual(json.loads((job / "meta.json").read_text())["limits"], limits)
            schema = json.loads((job / "result-schema.json").read_text())
            self.assertEqual(schema["properties"]["workers"]["maxItems"], 20)
            self.assertFalse((job / ".prime-slots").exists())

    def test_launcher_dry_run_allows_zero_writers(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            result = self.run_launcher(parent, ["--max-workers", "6", "--max-writers", "0", "--max-nodes", "20"])
            self.assertEqual(result.returncode, 0, result.stderr)
            job = parent / "job"
            limits = {"max_workers": 6, "max_writers": 0, "max_nodes": 20}
            self.assertEqual(json.loads((job / "limits.json").read_text()), limits)
            command = json.loads((job / "command.json").read_text())
            self.assertEqual(command["limits"], limits)
            self.assertEqual(command["env_exported"]["PRIME_MAX_WRITERS"], "0")

    def test_quota_after_only_safe_read_retries_fresh_opus_and_records_attempt_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            safe_event = {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}},
                        {"type": "tool_use", "name": "Glob", "input": {"pattern": "*.py"}},
                        {"type": "tool_use", "name": "Grep", "input": {"pattern": "x"}},
                    ]
                },
            }
            result, job, calls = self.run_stub_launcher(
                Path(td), [safe_event, self.quota_result()], opus_events=[self.completed_result()]
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [call["model"] for call in calls], ["claude-fable-5", "claude-opus-5"]
            )
            self.assertNotEqual(calls[0]["session_id"], calls[1]["session_id"])
            self.assertNotIn("--resume", calls[1]["argv"])
            expected_files = {
                "claude-fable-stream.jsonl",
                "claude-fable-stderr.log",
                "claude-opus-stream.jsonl",
                "claude-opus-stderr.log",
            }
            self.assertTrue(all((job / name).is_file() for name in expected_files))
            self.assertFalse((job / "claude-stream.jsonl").exists())
            meta = json.loads((job / "meta.json").read_text())
            self.assertTrue(meta["fallback_triggered"])
            self.assertEqual(meta["fallback_reason"], "usage_credits_exhausted")
            self.assertIsNone(meta["fallback_blocked_reason"])
            self.assertIsNone(meta["next_action"])
            self.assertEqual([attempt["returncode"] for attempt in meta["attempts"]], [0, 0])
            self.assertEqual(
                meta["attempts"][0]["fallback_safety"]["tool_names_observed"],
                ["Read", "Glob", "Grep"],
            )
            command = json.loads((job / "command.json").read_text())
            self.assertEqual(
                [attempt["model"] for attempt in command["attempts"]],
                ["claude-fable-5", "claude-opus-5"],
            )
            self.assertNotIn("--fallback-model", command["argv"])

    def test_quota_after_bash_blocks_retry(self):
        with tempfile.TemporaryDirectory() as td:
            bash_event = {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "true"}}
                    ]
                },
            }
            result, job, calls = self.run_stub_launcher(Path(td), [bash_event, self.quota_result()])

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual([call["model"] for call in calls], ["claude-fable-5"])
            meta = json.loads((job / "meta.json").read_text())
            self.assertEqual(meta["status"], "blocked")
            self.assertFalse(meta["fallback_triggered"])
            self.assertIn("Bash", meta["fallback_blocked_reason"])
            self.assertIn("Inspect", meta["next_action"])
            self.assertFalse((job / "claude-opus-stream.jsonl").exists())

    def test_generic_failure_does_not_retry(self):
        with tempfile.TemporaryDirectory() as td:
            generic = {"type": "result", "is_error": True, "result": "ordinary task failure"}
            result, job, calls = self.run_stub_launcher(Path(td), [generic], fable_rc=1)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(len(calls), 1)
            meta = json.loads((job / "meta.json").read_text())
            self.assertIsNone(meta["fallback_reason"])
            self.assertIsNone(meta["fallback_blocked_reason"])
            self.assertFalse(meta["fallback_triggered"])

    def test_resume_availability_error_blocks_cross_model_retry(self):
        with tempfile.TemporaryDirectory() as td:
            resume_sid = "fable-session-existing"
            result, job, calls = self.run_stub_launcher(
                Path(td), [self.quota_result()], extra=["--resume", resume_sid]
            )

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(len(calls), 1)
            self.assertIn("--resume", calls[0]["argv"])
            self.assertEqual(calls[0]["session_id"], resume_sid)
            meta = json.loads((job / "meta.json").read_text())
            self.assertEqual(meta["status"], "blocked")
            self.assertEqual(meta["session_id"], resume_sid)
            self.assertIn("--resume", meta["fallback_blocked_reason"])
            self.assertIn("without --resume", meta["next_action"])
            self.assertFalse(meta["fallback_triggered"])
            self.assertFalse((job / "claude-opus-stream.jsonl").exists())

    def test_explicit_overloaded_unavailable_and_quota_errors_are_classified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stream = root / "stream.jsonl"
            stderr = root / "stderr.log"
            stderr.write_text("")
            cases = [
                ("The model is currently overloaded", "model_overloaded"),
                ("This model is temporarily unavailable", "model_unavailable"),
                ("usage limit exceeded", "quota_exhausted"),
                ("ordinary task failure", None),
            ]
            for message, expected in cases:
                with self.subTest(message=message):
                    stream.write_text(
                        json.dumps({"type": "result", "is_error": True, "result": message})
                        + "\n"
                    )
                    self.assertEqual(detect_availability_error(stream, stderr), expected)

    def test_model_overloaded_after_no_tools_retries_fresh_opus(self):
        with tempfile.TemporaryDirectory() as td:
            overloaded = {
                "type": "result",
                "is_error": True,
                "result": "The model is currently overloaded; please retry later.",
            }
            result, job, calls = self.run_stub_launcher(
                Path(td), [overloaded], opus_events=[self.completed_result()]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [call["model"] for call in calls], ["claude-fable-5", "claude-opus-5"]
            )
            self.assertNotEqual(calls[0]["session_id"], calls[1]["session_id"])
            meta = json.loads((job / "meta.json").read_text())
            self.assertEqual(meta["fallback_reason"], "model_overloaded")
            self.assertTrue(meta["fallback_triggered"])

    def test_unknown_tool_blocks_availability_retry(self):
        with tempfile.TemporaryDirectory() as td:
            unknown_event = {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "FutureTool", "input": {}}
                    ]
                },
            }
            result, job, calls = self.run_stub_launcher(
                Path(td), [unknown_event, self.quota_result()]
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual([call["model"] for call in calls], ["claude-fable-5"])
            meta = json.loads((job / "meta.json").read_text())
            self.assertIn("FutureTool", meta["fallback_blocked_reason"])
            self.assertFalse(meta["fallback_triggered"])

    def test_corrupt_slot_state_cannot_prove_replay_safe(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            slots = job / ".prime-slots"
            slots.mkdir()
            (slots / "state.json").write_text("{not-json")
            (slots / "events.jsonl").write_text("")
            stream = job / "claude-fable-stream.jsonl"
            stream.write_text(json.dumps(self.quota_result()) + "\n")

            safe, detail, started, tools = assess_fallback_safety(job, stream)
            self.assertFalse(safe)
            self.assertIn("cannot prove zero starts", detail)
            self.assertEqual(started, 0)
            self.assertEqual(tools, [])

    def test_usage_credit_classifier_is_deliberately_narrow(self):
        event = {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "terminal_reason": "api_error",
            "api_error_status": 429,
            "result": USAGE_CREDIT_RESULT,
        }
        self.assertTrue(is_usage_credit_result(event))
        for field, value in (
            ("type", "assistant"),
            ("subtype", "error"),
            ("is_error", False),
            ("terminal_reason", "max_turns"),
            ("api_error_status", 500),
            ("result", "You're out of usage credits."),
        ):
            with self.subTest(field=field):
                changed = dict(event)
                changed[field] = value
                self.assertFalse(is_usage_credit_result(changed))
        self.assertFalse(is_usage_credit_result(None))

    @staticmethod
    def install_fake_claude(home: Path, scenario: str) -> None:
        binary = home / ".local" / "bin" / "claude"
        binary.parent.mkdir(parents=True)
        script = f'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

scenario = {scenario!r}
args = sys.argv[1:]
job = Path(os.environ["PRIME_ORCHESTRATION_JOB_DIR"])
calls_path = job / "fake-claude-calls.jsonl"
model = args[args.index("--model") + 1]
session_flag = "--resume" if "--resume" in args else "--session-id"
session_id = args[args.index(session_flag) + 1]
with calls_path.open("a") as calls:
    calls.write(json.dumps({{"argv": args, "model": model, "session_flag": session_flag, "session_id": session_id}}) + "\\n")
sys.stdin.read()

final = {{
    "status": "completed",
    "summary": "fake success",
    "fan_in": {{"expected": 0, "received": 0, "complete": True}},
    "workers": [],
    "validation": [{{"command": "fake-check", "status": "passed", "evidence": "fake evidence"}}],
    "changed_files": [],
    "risks": [],
    "next_actions": [],
}}
credit = {{
    "type": "result", "subtype": "success", "is_error": True,
    "terminal_reason": "api_error", "api_error_status": 429,
    "result": {USAGE_CREDIT_RESULT!r}, "session_id": session_id,
    "modelUsage": {{}},
}}
failure = {{
    "type": "result", "subtype": "error", "is_error": True,
    "terminal_reason": "api_error", "api_error_status": 500,
    "result": "generic failure", "session_id": session_id,
    "modelUsage": {{model: {{}}}},
}}
success = {{
    "type": "result", "subtype": "success", "is_error": False,
    "structured_output": final, "session_id": session_id,
    "modelUsage": {{model: {{}}}},
}}
if scenario == "worker_credit" and model == "claude-fable-5":
    events = job / ".prime-slots" / "events.jsonl"
    with events.open("a") as stream:
        stream.write(json.dumps({{"event": "started", "node_id": "fake-worker", "vendor": "codex", "lane": "reader"}}) + "\\n")
if model == "claude-fable-5" and scenario in ("fallback_success", "worker_credit", "opus_failure"):
    event = credit
elif model == "claude-fable-5" and scenario == "generic_failure":
    event = failure
elif model == "claude-opus-5" and scenario == "opus_failure":
    event = failure
else:
    event = success
print(json.dumps(event), flush=True)
'''
        binary.write_text(script)
        binary.chmod(0o755)

    def run_fake_launcher(
        self, parent: Path, scenario: str, extra: list[str] | None = None
    ) -> tuple[subprocess.CompletedProcess, Path, list[dict], dict]:
        home = parent / "home"
        self.install_fake_claude(home, scenario)
        job = parent / "job"
        env = os.environ.copy()
        # The launcher must find the CLI the operator installed under HOME.
        # Clear the two variables that would otherwise point it elsewhere.
        env.pop("XDG_BIN_HOME", None)
        env.pop("PRIME_CLAUDE_BIN", None)
        env["HOME"] = str(home)
        result = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--job-dir", str(job),
                "--cwd", str(SKILL_DIR),
                "--stall-s", "30",
                "--timeout-s", "60",
                *(extra or []),
            ],
            input="fake integration brief\n",
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        calls_path = job / "fake-claude-calls.jsonl"
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
        meta = json.loads((job / "meta.json").read_text())
        return result, job, calls, meta

    def test_fake_claude_primary_success_uses_fable_once(self):
        with tempfile.TemporaryDirectory() as td:
            result, job, calls, meta = self.run_fake_launcher(Path(td), "success")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([call["model"] for call in calls], ["claude-fable-5"])
            self.assertNotIn("--fallback-model", calls[0]["argv"])
            self.assertFalse(meta["fallback_triggered"])
            self.assertIsNone(meta["fallback_reason"])
            self.assertEqual(meta["selected_model"], "claude-fable-5")
            self.assertEqual(len(meta["attempts"]), 1)
            self.assertTrue((job / "claude-fable-stream.jsonl").is_file())
            self.assertFalse((job / "claude-opus-stream.jsonl").exists())

    def test_fake_claude_credit_result_retries_opus_once_with_fresh_session(self):
        with tempfile.TemporaryDirectory() as td:
            result, job, calls, meta = self.run_fake_launcher(Path(td), "fallback_success")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [call["model"] for call in calls], ["claude-fable-5", "claude-opus-5"]
            )
            self.assertNotEqual(calls[0]["session_id"], calls[1]["session_id"])
            for call in calls:
                self.assertEqual(call["session_flag"], "--session-id")
                self.assertNotIn("--fallback-model", call["argv"])
            self.assertTrue(meta["fallback_triggered"])
            self.assertEqual(meta["fallback_reason"], "usage_credits_exhausted")
            self.assertEqual(meta["selected_model"], "claude-opus-5")
            self.assertEqual(meta["session_id"], calls[1]["session_id"])
            self.assertEqual(len(meta["attempts"]), 2)
            self.assertEqual(
                json.loads((job / "final.json").read_text())["summary"], "fake success"
            )
            self.assertTrue((job / "claude-fable-stream.jsonl").is_file())
            self.assertTrue((job / "claude-opus-stream.jsonl").is_file())
            self.assertNotEqual(meta["attempts"][0]["stream"], meta["attempts"][1]["stream"])

    def test_fake_claude_resume_availability_error_is_blocked(self):
        resume_sid = "9f3c1e3e-81e8-49b6-90f1-f9a0a73cc0ad"
        with tempfile.TemporaryDirectory() as td:
            result, _job, calls, meta = self.run_fake_launcher(
                Path(td), "fallback_success", ["--resume", resume_sid]
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual([call["session_flag"] for call in calls], ["--resume"])
            self.assertEqual([call["session_id"] for call in calls], [resume_sid])
            self.assertEqual(meta["session_id"], resume_sid)
            self.assertEqual(meta["status"], "blocked")
            self.assertFalse(meta["fallback_triggered"])
            self.assertIn("--resume", meta["fallback_blocked_reason"])

    def test_fake_claude_generic_failure_does_not_retry(self):
        with tempfile.TemporaryDirectory() as td:
            result, _job, calls, meta = self.run_fake_launcher(Path(td), "generic_failure")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual([call["model"] for call in calls], ["claude-fable-5"])
            self.assertFalse(meta["fallback_triggered"])
            self.assertEqual(meta["selected_model"], "claude-fable-5")

    def test_fake_claude_worker_start_blocks_credit_retry(self):
        with tempfile.TemporaryDirectory() as td:
            result, job, calls, meta = self.run_fake_launcher(Path(td), "worker_credit")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual([call["model"] for call in calls], ["claude-fable-5"])
            self.assertFalse(meta["fallback_triggered"])
            self.assertEqual(meta["status"], "blocked")
            self.assertIn("started node", meta["fallback_blocked_reason"])
            self.assertFalse((job / "claude-opus-stream.jsonl").exists())

    def test_fake_claude_opus_failure_is_selected_without_another_retry(self):
        with tempfile.TemporaryDirectory() as td:
            result, job, calls, meta = self.run_fake_launcher(Path(td), "opus_failure")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                [call["model"] for call in calls], ["claude-fable-5", "claude-opus-5"]
            )
            self.assertEqual(meta["selected_model"], "claude-opus-5")
            self.assertTrue(meta["fallback_triggered"])
            self.assertEqual(json.loads((job / "final.json").read_text()), "generic failure")


if __name__ == "__main__":
    unittest.main()
