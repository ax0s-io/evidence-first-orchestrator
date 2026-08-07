#!/usr/bin/env python3
"""Report whether this host can launch evidence-first orchestration jobs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from efo_version import VERSION

try:
    from efo_orchestrate import resolve_executable
except (Exception, SystemExit) as exc:  # Keep a broken local install diagnostic clean.
    resolve_executable = None  # type: ignore[assignment]
    RESOLVER_IMPORT_ERROR: str | None = str(exc) or exc.__class__.__name__
else:
    RESOLVER_IMPORT_ERROR = None

Check = dict[str, Any]


class ArgumentParser(argparse.ArgumentParser):
    """Make invalid invocations obey preflight's 0-or-1 exit contract."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        raise ValueError(message)


def parse_args() -> argparse.Namespace:
    parser = ArgumentParser(description="Check evidence-first launcher prerequisites.")
    parser.add_argument(
        "--version",
        action="version",
        version=f"evidence-first-orchestrator {VERSION}",
    )
    parser.add_argument("--json", action="store_true", help="print one machine-readable JSON object")
    return parser.parse_args()


def make_check(
    name: str,
    required: bool,
    ok: bool,
    detail: str,
    remediation: str | None = None,
    resolved: Path | str | None = None,
) -> Check:
    return {
        "name": name,
        "required": required,
        "ok": ok,
        "detail": detail,
        "remediation": remediation,
        "resolved": str(resolved) if resolved is not None else None,
    }


def python_check() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info >= (3, 10)
    return make_check(
        "python",
        True,
        ok,
        f"Python {version}",
        None if ok else "Install Python 3.10 or newer.",
        sys.executable,
    )


def adapter_check(
    name: str,
    env_var: str,
    required: bool,
    unavailable: str,
) -> Check:
    remediation = (
        f"Install the Claude Code CLI or set {env_var} to an executable file."
        if name == "claude"
        else f"Install {name} or set {env_var} to an executable file; {unavailable}."
    )
    if resolve_executable is None:
        detail = f"efo-preflight: launcher resolver could not be imported: {RESOLVER_IMPORT_ERROR}"
        return make_check(name, required, False, detail, remediation)
    try:
        resolved = resolve_executable(name, env_var, "efo-preflight")
    except SystemExit as exc:
        detail = str(exc)
        if not required:
            detail = f"{detail}; {unavailable}"
        return make_check(name, required, False, detail, remediation)
    except Exception as exc:
        detail = f"efo-preflight: could not resolve {name}: {exc}"
        if not required:
            detail = f"{detail}; {unavailable}"
        return make_check(name, required, False, detail, remediation)
    return make_check(name, required, True, f"resolved to {resolved}", resolved=resolved)


def run_root_check() -> Check:
    configured = os.environ.get("EFO_ORCHESTRATION_RUN_ROOT")
    try:
        root = (
            Path(configured).expanduser()
            if configured
            else Path.home() / ".efo" / "orchestration-runs"
        ).resolve()
        if root.exists():
            if not root.is_dir():
                return make_check(
                    "run root",
                    True,
                    False,
                    f"{root} exists but is not a directory",
                    "Set EFO_ORCHESTRATION_RUN_ROOT to a writable directory.",
                    root,
                )
            writable = os.access(root, os.W_OK | os.X_OK)
            return make_check(
                "run root",
                True,
                writable,
                f"{root} exists and is writable" if writable else f"{root} is not writable",
                None
                if writable
                else "Make the run root writable or set EFO_ORCHESTRATION_RUN_ROOT to a writable directory.",
                root,
            )

        ancestor = root
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        writable = ancestor.is_dir() and os.access(ancestor, os.W_OK | os.X_OK)
        detail = (
            f"{root} does not exist; launcher can create it under writable ancestor {ancestor}"
            if writable
            else f"{root} does not exist and nearest existing ancestor {ancestor} is not writable"
        )
        return make_check(
            "run root",
            True,
            writable,
            detail,
            None
            if writable
            else "Make an ancestor writable or set EFO_ORCHESTRATION_RUN_ROOT to a writable directory.",
            root,
        )
    except (OSError, RuntimeError) as exc:
        return make_check(
            "run root",
            True,
            False,
            f"efo-preflight: could not inspect the run root: {exc}",
            "Set EFO_ORCHESTRATION_RUN_ROOT to a writable directory.",
        )


def platform_check() -> Check:
    ok = os.name == "posix"
    return make_check(
        "platform",
        True,
        ok,
        "POSIX platform" if ok else f"unsupported platform: os.name={os.name}",
        None if ok else "Use a POSIX host; on Windows, run under WSL.",
    )


def bash_check(warnings: list[str]) -> Check:
    found = shutil.which("bash")
    if not found:
        return make_check(
            "bash",
            True,
            False,
            "efo-preflight: bash not found on PATH",
            "Install bash and make it available on PATH.",
        )
    try:
        resolved = Path(found).resolve(strict=True)
    except (OSError, RuntimeError):
        resolved = Path(found)

    try:
        result = subprocess.run(
            [str(resolved), "-c", "echo $BASH_VERSION"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        warning = f"bash version could not be obtained: {exc}"
        warnings.append(warning)
        return make_check("bash", True, True, f"resolved to {resolved}; {warning}", resolved=resolved)

    version = result.stdout.strip()
    if result.returncode != 0 or not version:
        warning = "bash version could not be obtained"
        warnings.append(warning)
        return make_check("bash", True, True, f"resolved to {resolved}; {warning}", resolved=resolved)

    match = re.match(r"(\d+)", version)
    if match and int(match.group(1)) < 4:
        warnings.append(
            f"bash {version} is older than the preferred major version 4; macOS bash 3.2 is supported"
        )
    return make_check("bash", True, True, f"bash {version}", resolved=resolved)


def provider_terms_check() -> Check:
    """Require the operator to acknowledge the provider-terms review.

    Automating a vendor CLI is governed by that vendor's terms and by the
    operator's specific plan. docs/provider-terms-review.md records that we could
    not affirmatively clear automated, consumer-subscription-authenticated use of
    any supported CLI. This project cannot detect which plan or authentication
    method a CLI is using, so it cannot enforce compliance -- it can only refuse
    to be set up silently. The gate is deliberately trivial to satisfy: its
    purpose is informed consent, not obstruction.
    """
    acknowledged = os.environ.get("EFO_PROVIDER_TERMS_ACK", "") == "1"
    return make_check(
        "provider-terms",
        True,
        acknowledged,
        (
            "acknowledged via EFO_PROVIDER_TERMS_ACK=1"
            if acknowledged
            else "not acknowledged"
        ),
        remediation=(
            "read docs/provider-terms-review.md, confirm your own plan's terms "
            "permit automated CLI invocation, then set EFO_PROVIDER_TERMS_ACK=1"
        ),
    )


def collect_report() -> dict[str, Any]:
    warnings: list[str] = []
    checks = [
        provider_terms_check(),
        python_check(),
        adapter_check("claude", "EFO_CLAUDE_BIN", True, "orchestration unavailable"),
        adapter_check("codex-leg", "EFO_CODEX_LEG_BIN", False, "Codex workers unavailable"),
        adapter_check("grok-leg", "EFO_GROK_LEG_BIN", False, "Grok workers unavailable"),
        adapter_check("grok", "EFO_GROK_BIN", False, "Grok workers unavailable"),
        run_root_check(),
        platform_check(),
        bash_check(warnings),
    ]
    by_name = {check["name"]: check for check in checks}
    failed = any(check["required"] and not check["ok"] for check in checks)
    return {
        "status": "failed" if failed else "ok",
        "checks": checks,
        "capabilities": {
            "codex_workers": bool(by_name["codex-leg"]["ok"]),
            "grok_workers": bool(by_name["grok-leg"]["ok"] and by_name["grok"]["ok"]),
        },
        "warnings": warnings,
    }


def print_human(report: dict[str, Any]) -> None:
    checks = report["checks"]
    name_width = max(len("CHECK"), *(len(check["name"]) for check in checks))
    required_width = len("REQUIRED")
    print(f"{'CHECK':<{name_width}}  {'REQUIRED':<{required_width}}  STATUS   DETAIL")
    print(f"{'-' * name_width}  {'-' * required_width}  -------  ------")
    for check in checks:
        status = "OK" if check["ok"] else ("FAIL" if check["required"] else "MISSING")
        required = "yes" if check["required"] else "no"
        print(
            f"{check['name']:<{name_width}}  {required:<{required_width}}  "
            f"{status:<7}  {check['detail']}"
        )
    for check in checks:
        if not check["ok"] and check["remediation"]:
            print(f"efo-preflight: remediation for {check['name']}: {check['remediation']}")
    for warning in report["warnings"]:
        print(f"efo-preflight: warning: {warning}")
    capabilities = report["capabilities"]
    print(
        "Capabilities: "
        f"Codex workers={'available' if capabilities['codex_workers'] else 'unavailable'}, "
        f"Grok workers={'available' if capabilities['grok_workers'] else 'unavailable'}"
    )
    print(f"Overall: {report['status'].upper()}")


def main() -> int:
    try:
        args = parse_args()
    except ValueError as exc:
        print(f"efo-preflight: {exc}", file=sys.stderr)
        return 1
    report = collect_report()
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print_human(report)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as exc:  # A diagnostic command must never emit a traceback.
        if "--json" in sys.argv:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "checks": [],
                        "capabilities": {"codex_workers": False, "grok_workers": False},
                        "warnings": [f"efo-preflight: internal error: {exc}"],
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"efo-preflight: internal error: {exc}", file=sys.stderr)
        exit_code = 1
    raise SystemExit(0 if exit_code == 0 else 1)
