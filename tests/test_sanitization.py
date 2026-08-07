"""Publication sanitization gate.

This repository is an extraction from a private fleet. Nothing in it may carry
a person's name, an organization slug, a home-directory absolute path, or a
private hostname out of that fleet — see PUBLICATION_CHECKLIST.md item 6.

The forbidden tokens are assembled from fragments on purpose: a scanner that
spelled them out would match itself, and exempting the scanner from its own
scan would leave exactly the hole this test exists to close.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Names and organization slugs, split so this file contains no literal token.
PERSON_NAMES = ("Aa" + "ron", "Dy" + "son", "Chr" + "is", "Blasch" + "ke")
ORG_SLUGS = ("ax" + "0s",)

# Contact, credit, consent, and audit records legitimately discuss the names
# as their subject matter. Nowhere else may carry them. Keep this set minimal:
# a file listed here is unscanned, so an entry that does not need to be here is
# a hole. `test_every_allowlisted_file_actually_needs_the_exemption` enforces
# that by failing on any entry that carries no name at all.
NAME_ALLOWED_FILES = frozenset(
    {
        "ATTRIBUTION.md",
        "LICENSE",
        "PUBLICATION_CHECKLIST.md",
        "README.md",
        "SECURITY.md",
    }
)

NAME_PATTERNS = tuple(
    (token, re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE))
    for token in PERSON_NAMES + ORG_SLUGS
)

# The public clone URL necessarily contains the organization slug. Permit only
# this exact reference, not the entire file containing it. Assemble it from
# fragments so the scanner continues to scan itself without a self-match.
PUBLIC_REFERENCE_ALLOWLIST = (
    "https://github.com/" + ORG_SLUGS[0] + "-io/evidence-first-orchestrator.git",
)

# An absolute path into somebody's home directory: a home root followed by a
# username. `$HOME/...` and `~/...` are fine — those are portable. The
# lookbehind requires the leading slash to start the path, so an ordinary
# relative path with a `home/` or `root/` component is not a finding.
HOME_ROOTS = ("Users", "home", "root", "var/root")
HOME_PATH_PATTERN = re.compile(
    r"(?<![\w.-])/(?:" + "|".join(HOME_ROOTS) + r")/[A-Za-z0-9._-]+"
)

# A hostname on a private network, i.e. a label followed by one of the
# private-network suffixes below. The lookarounds exclude the three things that
# look like one but are not: a dotfile directory such as `$HOME/.local/bin`
# (no label before the dot), a longer public FQDN such as `x.internal.example.com`,
# and a word that merely starts with a suffix, such as `x.locale`. A trailing
# `/` or `:` is allowed, so hostnames inside URLs are still caught.
PRIVATE_HOST_SUFFIXES = ("local", "lan", "internal", "localdomain")
PRIVATE_HOST_PATTERN = re.compile(
    r"(?<![\w.-])[a-z0-9][a-z0-9-]*\.(?:"
    + "|".join(PRIVATE_HOST_SUFFIXES)
    + r")(?![\w-])(?!\.[A-Za-z0-9])",
    re.IGNORECASE,
)

# Files that are data rather than prose/code, or that git already ignores.
SKIP_SUFFIXES = frozenset({".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico"})


def publishable_files() -> list[Path]:
    """Every file that would ship: tracked plus untracked-and-not-ignored."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        # Fail loudly rather than skip: a silently unenforced sanitization gate
        # is the exact failure mode this suite exists to prevent.
        raise RuntimeError(
            "the sanitization scan needs a git checkout to know which files "
            f"would ship; run it from a clone, not an unpacked archive ({exc})"
        ) from exc
    files = []
    for line in result.stdout.splitlines():
        path = REPO / line
        if path.suffix in SKIP_SUFFIXES or not path.is_file():
            continue
        files.append(path)
    return files


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def render(findings: list[tuple[str, int, str]]) -> str:
    return "\n".join(
        f"  {relative}:{number}: {token}" for relative, number, token in findings
    )


class SanitizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = publishable_files()

    def test_the_scan_actually_covers_the_repository(self):
        """A scan over zero files would pass every other test in this class."""
        names = {path.relative_to(REPO).as_posix() for path in self.files}
        self.assertGreater(len(names), 15, "publishable file list is implausibly short")
        for expected in ("README.md", "SKILL.md", "scripts/efo_orchestrate.py"):
            self.assertIn(expected, names)

    def test_the_patterns_actually_match_what_they_are_looking_for(self):
        """A pattern that silently matches nothing would pass every scan below.

        The samples are assembled from fragments for the same reason the tokens
        are: spelled out, they would be findings in this very file.
        """
        for token, pattern in NAME_PATTERNS:
            self.assertRegex(f"credit to {token} here", pattern)
        for sample in ("/Us" + "ers/someone/x", "/ho" + "me/someone", "/ro" + "ot/.ssh"):
            self.assertRegex(sample, HOME_PATH_PATTERN)
        for sample in ("nas." + "local", "http://box." + "local/x", "host." + "internal:22"):
            self.assertRegex(sample, PRIVATE_HOST_PATTERN)
        # Portable forms and lookalikes stay clean.
        for sample in ("$HOME/.local/bin", "~/.local/share", "x.locale"):
            self.assertNotRegex(sample, PRIVATE_HOST_PATTERN)
        for sample in ("$HOME/x", "docs/home/index.md"):
            self.assertNotRegex(sample, HOME_PATH_PATTERN)

    def test_every_allowlisted_file_actually_needs_the_exemption(self):
        """An allowlist entry is unscanned surface, so keep it earned.

        A file listed but carrying no name is either dead (someone removed the
        content but left the exemption) or speculative (someone widened the
        allowlist in advance). Either way it is a place a name could later be
        planted without this suite noticing.
        """
        unnecessary = []
        for relative in sorted(NAME_ALLOWED_FILES):
            path = REPO / relative
            if not path.exists():
                unnecessary.append(f"{relative} (missing)")
                continue
            text = "\n".join(read_lines(path))
            if not any(pattern.search(text) for _, pattern in NAME_PATTERNS):
                unnecessary.append(f"{relative} (contains no name)")
        self.assertEqual(
            unnecessary,
            [],
            "NAME_ALLOWED_FILES entries that do not need the exemption; remove "
            f"them so the scan covers those files: {unnecessary}",
        )

    def test_no_person_names_or_org_slugs_outside_the_attribution_files(self):
        findings: list[tuple[str, int, str]] = []
        for path in self.files:
            relative = path.relative_to(REPO).as_posix()
            if relative in NAME_ALLOWED_FILES:
                continue
            for number, line in enumerate(read_lines(path), 1):
                scanned = line
                for allowed in PUBLIC_REFERENCE_ALLOWLIST:
                    scanned = scanned.replace(allowed, "<public-repository-url>")
                for token, pattern in NAME_PATTERNS:
                    if pattern.search(scanned):
                        findings.append((relative, number, token))
        self.assertEqual(
            findings,
            [],
            "person names and organization slugs are permitted only in "
            f"{sorted(NAME_ALLOWED_FILES)}:\n{render(findings)}",
        )

    def test_no_home_directory_absolute_paths(self):
        findings: list[tuple[str, int, str]] = []
        for path in self.files:
            relative = path.relative_to(REPO).as_posix()
            for number, line in enumerate(read_lines(path), 1):
                for match in HOME_PATH_PATTERN.finditer(line):
                    findings.append((relative, number, match.group(0)))
        self.assertEqual(
            findings,
            [],
            "hardcoded home-directory paths are not portable and leak a "
            f"username; use $HOME, ~, or a temporary directory:\n{render(findings)}",
        )

    def test_no_private_hostnames(self):
        findings: list[tuple[str, int, str]] = []
        for path in self.files:
            relative = path.relative_to(REPO).as_posix()
            for number, line in enumerate(read_lines(path), 1):
                for match in PRIVATE_HOST_PATTERN.finditer(line):
                    findings.append((relative, number, match.group(0)))
        self.assertEqual(
            findings,
            [],
            f"private hostnames must not appear in a public repository:\n{render(findings)}",
        )


if __name__ == "__main__":
    unittest.main()
