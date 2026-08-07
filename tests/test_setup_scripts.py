"""Preflight and install behavior, exercised hermetically.

Both scripts are diagnostics an operator runs before anything else works, so
they are tested against a synthetic HOME rather than the developer's machine:
no real CLI needs to exist for these to pass.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
PREFLIGHT = SCRIPTS / "efo_preflight.py"
INSTALL = SCRIPTS / "install.sh"

INSTALLED_NAMES = (
    "efo-orchestrate",
    "efo-codex-leg",
    "efo-grok-leg",
    "efo-preflight",
)
LINK_TARGETS = {
    "efo-orchestrate": SCRIPTS / "efo_orchestrate.py",
    "efo-codex-leg": SCRIPTS / "efo_codex_leg.sh",
    "efo-grok-leg": SCRIPTS / "efo_grok_leg.sh",
    "efo-preflight": SCRIPTS / "efo_preflight.py",
}
# Every EFO_* override that would otherwise leak in from the caller.
OVERRIDES = (
    "EFO_CLAUDE_BIN",
    "EFO_CODEX_LEG_BIN",
    "EFO_GROK_LEG_BIN",
    "EFO_GROK_BIN",
    "EFO_ORCHESTRATION_RUN_ROOT",
    "XDG_BIN_HOME",
)


def isolated_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in OVERRIDES:
        env.pop(name, None)
    env["HOME"] = str(home)
    env["PATH"] = "/usr/bin:/bin"
    # Preflight refuses to pass until the operator acknowledges the provider-terms
    # review. Every test below is about some *other* check, so acknowledge here and
    # let ProviderTermsGateTests own the gate itself.
    env["EFO_PROVIDER_TERMS_ACK"] = "1"
    return env


def install(prefix: Path, *flags: str, env: dict[str, str] | None = None):
    return subprocess.run(
        ["/bin/bash", str(INSTALL), "--prefix", str(prefix), *flags],
        capture_output=True,
        text=True,
        env=env,
    )


class ProviderTermsGateTests(unittest.TestCase):
    """Automating a vendor CLI is governed by that vendor's terms and the
    operator's plan, and docs/provider-terms-review.md could not affirmatively
    clear consumer-subscription automation. Preflight cannot detect which plan is
    in use, so it fails closed until the operator acknowledges having checked.
    """

    def run_preflight(self, env: dict[str, str]):
        return subprocess.run(
            [sys.executable, str(PREFLIGHT), "--json"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def working_env(self, home: Path) -> dict[str, str]:
        claude = home / ".local" / "bin" / "claude"
        claude.parent.mkdir(parents=True)
        claude.write_text("#!/bin/sh\nexit 0\n")
        claude.chmod(0o755)
        return isolated_env(home)

    def test_unacknowledged_provider_terms_fail_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            env = self.working_env(Path(td))
            env.pop("EFO_PROVIDER_TERMS_ACK", None)

            result = self.run_preflight(env)

            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "failed")
            check = {c["name"]: c for c in report["checks"]}["provider-terms"]
            self.assertFalse(check["ok"])
            self.assertTrue(check["required"])
            self.assertIn("provider-terms-review.md", check["remediation"])

    def test_acknowledgement_must_be_exactly_one(self):
        """A truthy-looking value is not an acknowledgement; only "1" is."""
        for value in ("", "0", "yes", "true", "TRUE"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as td:
                env = self.working_env(Path(td))
                env["EFO_PROVIDER_TERMS_ACK"] = value

                report = json.loads(self.run_preflight(env).stdout)

                check = {c["name"]: c for c in report["checks"]}["provider-terms"]
                self.assertFalse(check["ok"], f"{value!r} must not acknowledge")

    def test_acknowledgement_lets_an_otherwise_healthy_host_pass(self):
        with tempfile.TemporaryDirectory() as td:
            env = self.working_env(Path(td))

            result = self.run_preflight(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "ok")
            check = {c["name"]: c for c in report["checks"]}["provider-terms"]
            self.assertTrue(check["ok"])


class PreflightTests(unittest.TestCase):
    def run_preflight(self, home: Path, *flags: str, env: dict[str, str] | None = None):
        return subprocess.run(
            [sys.executable, str(PREFLIGHT), *flags],
            capture_output=True,
            text=True,
            env=env if env is not None else isolated_env(home),
            timeout=30,
        )

    def test_missing_claude_fails_cleanly_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            result = self.run_preflight(home, "--json")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "failed")
            checks = {check["name"]: check for check in report["checks"]}
            self.assertFalse(checks["claude"]["ok"])
            self.assertTrue(checks["claude"]["required"])
            self.assertIn("EFO_CLAUDE_BIN", checks["claude"]["remediation"])

    def test_missing_optional_adapters_are_capability_gaps_not_failures(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            claude = home / ".local" / "bin" / "claude"
            claude.parent.mkdir(parents=True)
            claude.write_text("#!/bin/sh\nexit 0\n")
            claude.chmod(0o755)

            result = self.run_preflight(home, "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "ok")
            checks = {check["name"]: check for check in report["checks"]}
            self.assertTrue(checks["claude"]["ok"])
            # Found under HOME even though PATH does not contain it. The
            # resolver reports the canonical path, so compare resolved forms.
            self.assertEqual(checks["claude"]["resolved"], str(claude.resolve()))
            for optional in ("codex-leg", "grok-leg", "grok"):
                self.assertFalse(checks[optional]["required"])
                self.assertFalse(checks[optional]["ok"])
            self.assertEqual(
                report["capabilities"], {"codex_workers": False, "grok_workers": False}
            )

    def test_json_output_is_exactly_one_object(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_preflight(Path(td), "--json")
            self.assertEqual(len(result.stdout.strip().splitlines()), 1)
            report = json.loads(result.stdout)
            self.assertEqual(
                set(report), {"status", "checks", "capabilities", "warnings"}
            )

    def test_unusable_override_is_a_hard_error_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            claude = home / ".local" / "bin" / "claude"
            claude.parent.mkdir(parents=True)
            claude.write_text("#!/bin/sh\nexit 0\n")
            claude.chmod(0o755)
            env = isolated_env(home)
            env["EFO_CLAUDE_BIN"] = str(home / "nonexistent")

            result = self.run_preflight(home, "--json", env=env)

            self.assertEqual(result.returncode, 1, result.stderr)
            checks = {c["name"]: c for c in json.loads(result.stdout)["checks"]}
            self.assertFalse(checks["claude"]["ok"])
            self.assertIn("EFO_CLAUDE_BIN", checks["claude"]["detail"])

    def test_help_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_preflight(Path(td), "--help")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_flag_still_obeys_the_zero_or_one_contract(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_preflight(Path(td), "--not-a-flag")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stderr)


class InstallTests(unittest.TestCase):
    def assert_links(self, prefix: Path) -> None:
        for name in INSTALLED_NAMES:
            link = prefix / name
            self.assertTrue(link.is_symlink(), f"{name} is not a symlink")
            self.assertEqual(Path(os.readlink(link)), LINK_TARGETS[name])

    def test_dry_run_touches_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "bin"
            result = install(prefix, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(prefix.exists(), "--dry-run created the prefix directory")
            self.assertIn("would link", result.stdout)

    def test_install_is_idempotent_and_uninstall_reverses_it(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "bin"
            first = install(prefix)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assert_links(prefix)

            second = install(prefix)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assert_links(prefix)
            self.assertNotIn("linked", second.stdout)

            removal = install(prefix, "--uninstall")
            self.assertEqual(removal.returncode, 0, removal.stderr)
            self.assertEqual(sorted(path.name for path in prefix.iterdir()), [])

    def test_refuses_to_clobber_a_real_file_and_installs_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "bin"
            prefix.mkdir()
            occupied = prefix / "efo-preflight"
            occupied.write_text("do not delete me\n")

            result = install(prefix)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to clobber", result.stderr)
            self.assertEqual(occupied.read_text(), "do not delete me\n")
            # Validation happens before any mutation: no partial install.
            self.assertEqual([path.name for path in prefix.iterdir()], ["efo-preflight"])

            forced = install(prefix, "--force")
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assert_links(prefix)

    def test_uninstall_refuses_to_remove_a_foreign_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "bin"
            self.assertEqual(install(prefix).returncode, 0)
            foreign = prefix / "efo-grok-leg"
            foreign.unlink()
            foreign.symlink_to(Path(td))

            result = install(prefix, "--uninstall")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to remove foreign symlink", result.stderr)
            # Nothing was removed, including the links it would have accepted.
            self.assertEqual(
                sorted(path.name for path in prefix.iterdir()), sorted(INSTALLED_NAMES)
            )

    def test_unknown_flag_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "bin"
            result = install(prefix, "--not-a-flag")
            self.assertEqual(result.returncode, 2)
            self.assertIn("unknown option", result.stderr)
            self.assertFalse(prefix.exists())

    def test_prefix_not_on_path_warns_but_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "bin"
            env = isolated_env(Path(td))
            result = install(prefix, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("is not on PATH", result.stderr)


if __name__ == "__main__":
    unittest.main()
