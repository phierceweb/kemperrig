"""The tracked tree is fit to be public: no home-directory paths, no links into gitignored
files, no symlink that dangles on a fresh clone. Needs a git checkout; an sdist skips."""

import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_HOME_PATH = re.compile(r"(?:/Users|/home)/[A-Za-z0-9][A-Za-z0-9._-]*")
_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _checkout() -> bool:
    top = _git("rev-parse", "--show-toplevel")
    return top.returncode == 0 and Path(top.stdout.strip()).resolve() == ROOT


@unittest.skipUnless(_checkout(), "not a git checkout (an sdist, say) — these checks read git")
class RepoHygieneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tracked = [ROOT / f for f in _git("ls-files").stdout.splitlines()]
        cls.links = [ROOT / line.split("\t", 1)[1]
                     for line in _git("ls-files", "-s").stdout.splitlines()
                     if line.startswith("120000")]

    def _text_files(self):
        for p in self.tracked:
            if p.is_file() and not p.is_symlink():
                try:
                    yield p, p.read_text()
                except UnicodeDecodeError:
                    continue

    def test_no_tracked_file_holds_a_home_directory_path(self):
        found = [f"{p.relative_to(ROOT)}: {m}" for p, text in self._text_files()
                 for m in _HOME_PATH.findall(text)]
        self.assertEqual(found, [])

    def test_every_relative_link_in_markdown_reaches_a_tracked_file(self):
        bad = []
        for p, text in self._text_files():
            if p.suffix != ".md":
                continue
            for target in _LINK.findall(text):
                path = target.split("#", 1)[0]
                if not path or "://" in path or path.startswith("mailto:"):
                    continue
                dest = (p.parent / path).resolve()
                ignored = _git("check-ignore", "-q", str(dest)).returncode == 0
                if not dest.exists() or ignored:
                    bad.append(f"{p.relative_to(ROOT)} -> {target}")
        self.assertEqual(bad, [])

    def test_every_tracked_symlink_resolves_inside_the_repo(self):
        bad = [str(link.relative_to(ROOT)) for link in self.links
               if not link.exists() or not Path(os.path.realpath(link)).is_relative_to(ROOT)]
        self.assertTrue(self.links)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
