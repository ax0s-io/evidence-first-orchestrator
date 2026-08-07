"""Version source and command-surface tests."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import efo_version
from tests.test_sanitization import publishable_files


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
EXPECTED = "evidence-first-orchestrator 0.1.0"


class VersionCommandTests(unittest.TestCase):
    def assert_version(self, command: list[str]) -> None:
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            env = os.environ.copy()
            env.update(
                PYTHONDONTWRITEBYTECODE="1",
                HOME=str(cwd),
                EFO_CLAUDE_BIN=str(cwd / "no-claude"),
                EFO_CODEX_LEG_BIN=str(cwd / "no-codex-leg"),
                EFO_GROK_LEG_BIN=str(cwd / "no-grok-leg"),
                EFO_GROK_BIN=str(cwd / "no-grok"),
                EFO_ORCHESTRATION_RUN_ROOT=str(cwd / "runs"),
            )
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, EXPECTED + "\n")
            self.assertEqual(result.stderr, "")
            self.assertEqual(list(cwd.iterdir()), [])

    def test_orchestrator_version(self):
        self.assert_version([sys.executable, str(SCRIPTS / "efo_orchestrate.py"), "--version"])

    def test_preflight_version(self):
        self.assert_version([sys.executable, str(SCRIPTS / "efo_preflight.py"), "--version"])

    def test_codex_wrapper_version(self):
        self.assert_version(["/bin/bash", str(SCRIPTS / "efo_codex_leg.sh"), "--version"])

    def test_grok_wrapper_version(self):
        self.assert_version(["/bin/bash", str(SCRIPTS / "efo_grok_leg.sh"), "--version"])

    def test_missing_version_file_fails_clearly(self):
        original = efo_version.VERSION_FILE
        try:
            efo_version.VERSION_FILE = REPO / "does-not-exist"
            with self.assertRaisesRegex(RuntimeError, "cannot read version file"):
                efo_version.read_version()
        finally:
            efo_version.VERSION_FILE = original

    def test_malformed_version_file_fails_clearly(self):
        original = efo_version.VERSION_FILE
        with tempfile.TemporaryDirectory() as td:
            malformed = Path(td) / "VERSION"
            malformed.write_text("not-a-version\n", encoding="utf-8")
            try:
                efo_version.VERSION_FILE = malformed
                with self.assertRaisesRegex(RuntimeError, "expected MAJOR.MINOR.PATCH"):
                    efo_version.read_version()
            finally:
                efo_version.VERSION_FILE = original

    def test_version_literal_is_not_duplicated_in_code(self):
        version_literal = EXPECTED.rsplit(" ", 1)[1]
        findings = []
        for path in publishable_files():
            relative = path.relative_to(REPO).as_posix()
            if relative == "VERSION" or relative.startswith("tests/"):
                continue
            if path.suffix == ".md" and not relative.startswith(("examples/", "references/")):
                continue
            if version_literal in path.read_text(encoding="utf-8", errors="ignore"):
                findings.append(relative)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
