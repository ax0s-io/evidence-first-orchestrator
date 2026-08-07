"""Read and validate the project version from the repository root."""
from __future__ import annotations

from pathlib import Path
import re


VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def read_version() -> str:
    try:
        contents = VERSION_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read version file {VERSION_FILE}: {exc}") from exc
    version = contents[:-1] if contents.endswith("\n") else contents
    if VERSION_PATTERN.fullmatch(version) is None:
        raise RuntimeError(
            f"malformed version in {VERSION_FILE}: expected MAJOR.MINOR.PATCH"
        )
    return version


VERSION = read_version()
