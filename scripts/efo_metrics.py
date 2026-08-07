#!/usr/bin/env python3
"""Build deterministic orchestration metrics by replaying slot events."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys


EVENT_TYPES = ("queued", "started", "finished", "pruned", "denied", "state_reset", "state_corrupt")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def build_metrics(job_dir, limits, run_info) -> dict:
    """Return metrics for a job; malformed inputs are represented as warnings."""
    try:
        absolute_job = os.path.abspath(os.fspath(job_dir))
    except Exception as exc:
        absolute_job = str(job_dir)
        path_error = f"invalid job_dir: {type(exc).__name__}: {exc}"
    else:
        path_error = None
    events_path = os.path.join(absolute_job, ".efo-slots", "events.jsonl")
    safe_limits = {
        "max_workers": limits.get("max_workers", 4) if isinstance(limits, dict) else 4,
        "max_writers": limits.get("max_writers", 2) if isinstance(limits, dict) else 2,
        "max_nodes": limits.get("max_nodes", 12) if isinstance(limits, dict) else 12,
    }
    safe_run = {
        "started_at": run_info.get("started_at") if isinstance(run_info, dict) else None,
        "ended_at": run_info.get("ended_at") if isinstance(run_info, dict) else None,
        "wall_time_s": run_info.get("wall_time_s", 0.0) if isinstance(run_info, dict) else 0.0,
    }
    result = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "job_dir": absolute_job,
        "status": "ok",
        "warnings": [],
        "limits": safe_limits,
        "run": safe_run,
        "events": {
            "path": events_path,
            "present": True,
            "total_lines": 0,
            "parsed": 0,
            "malformed": 0,
            "malformed_line_numbers": [],
            "malformed_trailing_only": True,
            "counts_by_type": {name: 0 for name in EVENT_TYPES},
        },
        "nodes": {"started": 0, "completed": 0, "failed": 0, "signaled": 0, "denied": 0, "unterminated": 0},
        "vendors": {
            "codex": {"started": 0, "completed": 0, "failed": 0},
            "grok": {"started": 0, "completed": 0, "failed": 0},
        },
        "lanes": {
            "reader": {"started": 0, "completed": 0, "failed": 0},
            "writer": {"started": 0, "completed": 0, "failed": 0},
        },
        "concurrency": {"peak_total": 0, "peak_total_at": None, "peak_writers": 0, "peak_writers_at": None},
        "queue": {"queued_nodes": 0, "waited_nodes": 0, "total_wait_s": 0.0, "max_wait_s": 0.0, "mean_wait_s": 0.0},
        "provenance": {
            "method": "replay of started/finished/pruned events ordered by ts then line number",
            "peak_total_node_ids": [],
            "peak_writer_node_ids": [],
            "first_event_ts": None,
            "last_event_ts": None,
        },
    }

    def warn(message: str, degraded: bool = False) -> None:
        result["warnings"].append(message)
        if degraded:
            result["status"] = "degraded"
        elif result["status"] == "ok":
            result["status"] = "ok_with_warnings"

    try:
        if path_error:
            warn(path_error, True)
            result["events"]["present"] = False
            return result
        try:
            with open(events_path) as source:
                lines = source.readlines()
        except Exception as exc:
            result["events"]["present"] = False
            warn(f"events.jsonl missing or unreadable: {type(exc).__name__}: {exc}", True)
            return result

        result["events"]["total_lines"] = len(lines)
        parsed: list[tuple[str, int, dict]] = []
        malformed: list[int] = []
        for line_number, line in enumerate(lines, 1):
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("event is not an object")
                ts = event.get("ts")
                if not isinstance(ts, str):
                    raise ValueError("event ts is not a string")
                parsed.append((ts, line_number, event))
                event_type = event.get("event")
                if event_type in result["events"]["counts_by_type"]:
                    result["events"]["counts_by_type"][event_type] += 1
            except Exception:
                malformed.append(line_number)
        result["events"]["parsed"] = len(parsed)
        result["events"]["malformed"] = len(malformed)
        result["events"]["malformed_line_numbers"] = malformed
        trailing_only = bool(malformed) and malformed == [len(lines)]
        result["events"]["malformed_trailing_only"] = trailing_only if malformed else True
        if malformed:
            if trailing_only:
                warn(f"torn trailing write at events.jsonl line {malformed[0]}")
            else:
                warn(f"malformed events.jsonl lines: {malformed}", True)

        parsed.sort(key=lambda item: (item[0], item[1]))
        if parsed:
            result["provenance"]["first_event_ts"] = parsed[0][0]
            result["provenance"]["last_event_ts"] = parsed[-1][0]

        active: dict[str, dict] = {}
        started_ids: set[str] = set()
        terminated_ids: set[str] = set()
        recorded_total = 0
        recorded_writers = 0
        all_waits: list[float] = []
        waits: list[float] = []
        for ts, _line_number, event in parsed:
            event_type = event.get("event")
            node_id = event.get("node_id")
            vendor = event.get("vendor")
            lane = event.get("lane")
            if event_type == "queued":
                result["queue"]["queued_nodes"] += 1
            elif event_type == "started":
                result["nodes"]["started"] += 1
                if isinstance(node_id, str):
                    started_ids.add(node_id)
                    active[node_id] = event
                if vendor in result["vendors"]:
                    result["vendors"][vendor]["started"] += 1
                if lane in result["lanes"]:
                    result["lanes"][lane]["started"] += 1
                try:
                    wait_s = float(event.get("wait_s", 0.0))
                except (TypeError, ValueError):
                    wait_s = 0.0
                if wait_s >= 0:
                    all_waits.append(wait_s)
                if wait_s > 0.001:
                    waits.append(wait_s)
                if isinstance(event.get("active_total"), (int, float)):
                    recorded_total = max(recorded_total, event["active_total"])
                if isinstance(event.get("active_writers"), (int, float)):
                    recorded_writers = max(recorded_writers, event["active_writers"])
                total = len(active)
                writers = sum(1 for held in active.values() if held.get("lane") == "writer")
                if total > result["concurrency"]["peak_total"]:
                    result["concurrency"]["peak_total"] = total
                    result["concurrency"]["peak_total_at"] = ts
                    result["provenance"]["peak_total_node_ids"] = sorted(active)
                if writers > result["concurrency"]["peak_writers"]:
                    result["concurrency"]["peak_writers"] = writers
                    result["concurrency"]["peak_writers_at"] = ts
                    result["provenance"]["peak_writer_node_ids"] = sorted(
                        key for key, held in active.items() if held.get("lane") == "writer"
                    )
            elif event_type == "finished":
                if not isinstance(node_id, str) or node_id not in started_ids:
                    warn(f"finished event for node_id {node_id!r} has no started event", True)
                if isinstance(node_id, str):
                    terminated_ids.add(node_id)
                    active.pop(node_id, None)
                signal_value = event.get("signal")
                rc = event.get("rc")
                if signal_value is not None:
                    result["nodes"]["signaled"] += 1
                    outcome = "failed"
                elif rc == 0:
                    result["nodes"]["completed"] += 1
                    outcome = "completed"
                else:
                    result["nodes"]["failed"] += 1
                    outcome = "failed"
                if vendor in result["vendors"]:
                    result["vendors"][vendor][outcome] += 1
                if lane in result["lanes"]:
                    result["lanes"][lane][outcome] += 1
                if isinstance(event.get("active_total"), (int, float)) and event["active_total"] >= 0:
                    recorded_total = max(recorded_total, event["active_total"])
                if isinstance(event.get("active_writers"), (int, float)) and event["active_writers"] >= 0:
                    recorded_writers = max(recorded_writers, event["active_writers"])
            elif event_type == "pruned":
                stale = event.get("stale_holder")
                stale_id = stale.get("node_id") if isinstance(stale, dict) else node_id
                if isinstance(stale_id, str):
                    terminated_ids.add(stale_id)
                    active.pop(stale_id, None)
                if isinstance(event.get("active_total"), (int, float)):
                    recorded_total = max(recorded_total, event["active_total"])
                if isinstance(event.get("active_writers"), (int, float)):
                    recorded_writers = max(recorded_writers, event["active_writers"])
            elif event_type == "denied":
                result["nodes"]["denied"] += 1
            elif event_type == "state_reset":
                warn(f"slot state was reset: {event.get('detail', 'unknown detail')}")
            elif event_type == "state_corrupt":
                warn(f"slot state is corrupt: {event.get('detail', 'unknown detail')}", True)

        result["nodes"]["unterminated"] = len(started_ids - terminated_ids)
        result["queue"]["waited_nodes"] = len(waits)
        result["queue"]["total_wait_s"] = round(sum(all_waits), 6)
        result["queue"]["max_wait_s"] = round(max(all_waits), 6) if all_waits else 0.0
        result["queue"]["mean_wait_s"] = round(sum(waits) / len(waits), 6) if waits else 0.0

        replay_total = result["concurrency"]["peak_total"]
        replay_writers = result["concurrency"]["peak_writers"]
        if replay_total != recorded_total:
            warn(f"replayed peak_total {replay_total} disagrees with recorded snapshot maximum {recorded_total}")
        if replay_writers != recorded_writers:
            warn(f"replayed peak_writers {replay_writers} disagrees with recorded snapshot maximum {recorded_writers}")
        if replay_total > safe_limits["max_workers"]:
            warn(f"peak_total {replay_total} exceeds max_workers {safe_limits['max_workers']}", True)
        if replay_writers > safe_limits["max_writers"]:
            warn(f"peak_writers {replay_writers} exceeds max_writers {safe_limits['max_writers']}", True)
        if result["nodes"]["started"] > safe_limits["max_nodes"]:
            warn(f"nodes.started {result['nodes']['started']} exceeds max_nodes {safe_limits['max_nodes']}", True)
        if result["nodes"]["unterminated"] > 0:
            warn(f"unterminated nodes: {result['nodes']['unterminated']}", True)
    except Exception as exc:
        warn(f"metrics build failed: {type(exc).__name__}: {exc}", True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    limits_path = os.path.join(os.path.abspath(args.job_dir), "limits.json")
    try:
        with open(limits_path) as source:
            limits = json.load(source)
    except Exception:
        limits = {"max_workers": 4, "max_writers": 2, "max_nodes": 12}
    metrics = build_metrics(args.job_dir, limits, {})
    rendered = json.dumps(metrics, indent=2) + "\n"
    if args.out:
        with open(args.out, "w") as out:
            out.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
