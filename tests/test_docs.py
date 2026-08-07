from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


class DocumentationLinksTests(unittest.TestCase):
    def test_local_markdown_targets_exist(self) -> None:
        broken: list[str] = []
        for doc in sorted(ROOT.rglob("*.md")):
            if ".git" in doc.parts:
                continue
            text = doc.read_text(encoding="utf-8")
            for raw in LINK.findall(text):
                target = raw.strip().split(maxsplit=1)[0].strip("<>")
                if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path_part = unquote(target.split("#", 1)[0])
                if path_part and not (doc.parent / path_part).resolve().exists():
                    broken.append(f"{doc.relative_to(ROOT)} -> {target}")
        self.assertEqual([], broken, "broken local Markdown links:\n" + "\n".join(broken))


if __name__ == "__main__":
    unittest.main()
