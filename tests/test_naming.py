"""Guard the publishable tree against pre-rename project identifiers."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.test_sanitization import publishable_files, read_lines


REPO = Path(__file__).resolve().parents[1]
OLD_WORD = "pri" + "me"
OLD_ENV_WORD = "PRI" + "ME"
ALLOWED_FILE = "PUBLICATION_CHECKLIST.md"

FORBIDDEN_PATTERNS = (
    ("orchestrator command", re.compile(re.escape(OLD_WORD + "-fable-orchestrat"))),
    ("Codex command", re.compile(re.escape(OLD_WORD + "-codex-leg"))),
    ("Grok command", re.compile(re.escape(OLD_WORD + "-grok-leg"))),
    ("preflight command", re.compile(re.escape(OLD_WORD + "-preflight"))),
    ("orchestrator module", re.compile(re.escape(OLD_WORD + "_fable_orchestrate"))),
    ("Codex module", re.compile(re.escape(OLD_WORD + "_codex_leg"))),
    ("Grok module", re.compile(re.escape(OLD_WORD + "_grok_leg"))),
    ("preflight module", re.compile(re.escape(OLD_WORD + "_preflight"))),
    ("metrics module", re.compile(re.escape(OLD_WORD + "_metrics"))),
    ("slot-controller module", re.compile(re.escape(OLD_WORD + "_slot_controller"))),
    ("binary-resolver module", re.compile(re.escape(OLD_WORD + "_resolve_bin"))),
    ("environment variable", re.compile(OLD_ENV_WORD + r"_[A-Z0-9_]+")),
    ("slot-state directory", re.compile(re.escape("." + OLD_WORD + "-slots"))),
    # Deliberately matches the bare dot-directory name, not just a slash-delimited
    # path: the run root is built from path *components* (Path.home() / ".<old>" /
    # "orchestration-runs"), so a pattern requiring surrounding slashes misses it.
    ("dot directory", re.compile(r"\." + OLD_WORD + r"\b")),
    # The catch-all. The patterns above name the identifiers that existed at
    # rename time; this one covers any legacy-prefixed identifier nobody
    # enumerated, including ones added after the rename by someone working from
    # stale notes. Case-insensitive because the shell, module, and environment
    # spellings differ only in case.
    ("legacy project prefix", re.compile(OLD_WORD + r"[-_]\w", re.IGNORECASE)),
)

POSITIVE_SAMPLES = (
    OLD_WORD + "-fable-orchestrate",
    OLD_WORD + "-codex-leg",
    OLD_WORD + "-grok-leg",
    OLD_WORD + "-preflight",
    OLD_WORD + "_fable_orchestrate",
    OLD_WORD + "_codex_leg",
    OLD_WORD + "_grok_leg",
    OLD_WORD + "_preflight",
    OLD_WORD + "_metrics",
    OLD_WORD + "_slot_controller",
    OLD_WORD + "_resolve_bin",
    OLD_ENV_WORD + "_EXAMPLE_TOKEN",
    "." + OLD_WORD + "-slots",
    "/." + OLD_WORD + "/",
    OLD_WORD.capitalize() + "-Something-Nobody-Enumerated",
)


class LegacyNameGuardTests(unittest.TestCase):
    def test_each_pattern_matches_a_synthetic_positive(self):
        self.assertEqual(len(FORBIDDEN_PATTERNS), len(POSITIVE_SAMPLES))
        for (label, pattern), sample in zip(FORBIDDEN_PATTERNS, POSITIVE_SAMPLES):
            with self.subTest(label=label):
                self.assertRegex(sample, pattern)

    def test_publishable_files_contain_no_legacy_project_names(self):
        findings: list[tuple[str, int, str, str]] = []
        for path in publishable_files():
            relative = path.relative_to(REPO).as_posix()
            if relative == ALLOWED_FILE:
                continue
            candidates = [(0, relative), *enumerate(read_lines(path), 1)]
            for number, text in candidates:
                for label, pattern in FORBIDDEN_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        findings.append((relative, number, label, match.group(0)))
        rendered = "\n".join(
            f"  {path}:{line}: {label}: {token}"
            for path, line, label, token in findings
        )
        self.assertEqual(
            findings,
            [],
            "legacy project identifiers remain outside the sole decision-record "
            f"allowlist entry ({ALLOWED_FILE}):\n{rendered}",
        )


if __name__ == "__main__":
    unittest.main()
