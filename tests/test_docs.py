"""Doc-sync gates. `docs/cli.md` covers every command, flag and environment variable, and
names no flag a command lacks; `docs/json.md` and `docs/census.md` list exactly the keys each
document holds, checked against the sample library; `docs/README.md` indexes every doc;
relative links and anchors in `docs/` resolve; `README.md`, which is also the PyPI page,
links only absolutely."""

import argparse
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _sample import build_sample

from kemperrig.cli import build_parser, main

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
_ROW = re.compile(r"^\|\s*`([a-z][a-z-]*)[\s`\[]")
_FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
_KEY_ROW = re.compile(r"^\|\s*`([A-Za-z_][A-Za-z0-9_]*)`")
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_CLI_DIR = ROOT / "src" / "kemperrig" / "cli"
_ENV = sorted({v for f in _CLI_DIR.glob("*.py")
               for v in re.findall(r'"(KEMPERRIG_[A-Z_]+)"', f.read_text())} | {"KEMPERRIG_GOLDEN"})


def _commands() -> dict[str, argparse.ArgumentParser]:
    sub = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return dict(sub.choices)


def _long_flags(parser: argparse.ArgumentParser) -> set[str]:
    return {s for a in parser._actions for s in a.option_strings
            if s.startswith("--") and s != "--help"}


def _rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in (DOCS / "cli.md").read_text().splitlines():
        m = _ROW.match(line)
        if m:
            rows.setdefault(m.group(1), []).append(line)
    return rows


def _sections(path: Path) -> dict[str, set[str]]:
    """Each heading's name (backticks dropped) and the keys its tables list."""
    out: dict[str, set[str]] = {}
    current = None
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            current = line.lstrip("#").strip().replace("`", "")
            out.setdefault(current, set())
        elif current is not None and (m := _KEY_ROW.match(line)):
            out[current].add(m.group(1))
    return out


def _anchor(heading: str) -> str:
    text = heading.lstrip("#").strip().lower()
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", text))


def _anchors(path: Path) -> set[str]:
    return {_anchor(line) for line in path.read_text().splitlines() if line.startswith("#")}


def _doc_files() -> list[Path]:
    return sorted(p for p in DOCS.glob("*.md") if not p.is_symlink())


class CliReferenceTest(unittest.TestCase):
    def test_every_command_has_rows(self):
        missing = sorted(set(_commands()) - set(_rows()))
        self.assertEqual(missing, [])

    def test_every_flag_appears_in_its_commands_rows(self):
        rows = _rows()
        for name, parser in _commands().items():
            text = "\n".join(rows.get(name, []))
            for flag in sorted(_long_flags(parser)):
                with self.subTest(command=name, flag=flag):
                    self.assertRegex(text, rf"(?<![\w-]){re.escape(flag)}(?![\w-])")

    def test_no_row_names_a_flag_its_command_lacks(self):
        commands = _commands()
        for name, lines in _rows().items():
            with self.subTest(command=name):
                self.assertIn(name, commands)
                named = {f for line in lines for f in _FLAG.findall(line)}
                self.assertEqual(sorted(named - _long_flags(commands[name])), [])

    def test_every_environment_variable_is_documented(self):
        text = (DOCS / "cli.md").read_text()
        for name in _ENV:
            with self.subTest(name=name):
                self.assertIn(name, text)


def _cli_json(*argv: str) -> dict:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        main([*argv, "--json"])
    return json.loads(out.getvalue())


class JsonReferenceTest(unittest.TestCase):
    """Every documented key exists, and every key a document holds is documented."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        p = build_sample(tmp / "s")
        b, snaps = str(p.backup), str(p.live / "Backups")
        rig = ["rig", b, "Recto Rhythm"]
        runs = {
            "summary": [["summary", b]],
            "rigs": [["rigs", b], ["rigs", b, "--decode"], ["rigs", b, "--effect", "x"]],
            "rig": [rig],
            "presets": [["presets", b]],
            "performances": [["performances", b]],
            "pages RIG": [["pages", b, "Recto Rhythm"]],
            "pages --all": [["pages", b, "--all"]],
            "shortlist": [["shortlist", b, "--criteria", str(p.criteria)]],
            "analyze": [["analyze", b]],
            "doctor": [["doctor", b]],
            "pack": [["pack", str(p.rigpack), "--against", b], ["pack", str(p.presetpack)]],
            "diff": [["diff", str(p.snapshots[0]), str(p.snapshots[1])]],
            "history": [["history", snaps], ["history", snaps, "--rig", "Recto Lead"]],
            "extract": [["extract", b, "-o", str(tmp / "x1"), "--all"],
                        ["extract", b, "-o", str(tmp / "x2"), "--ir", "v30"]],
        }
        cls.docs = {name: [_cli_json(*argv) for argv in variants]
                    for name, variants in runs.items()}
        decoded = _cli_json(*rig)["decode"]
        rigs = [r for d in cls.docs["rigs"] for r in d["rigs"]]
        cls.nested = {
            "Rig entry": set().union(*(r.keys() for r in rigs)) | set(_cli_json(*rig)),
            "Decode object": set(decoded),
            "Effect": set().union(*(e.keys() for e in decoded["effects"])),
            "Unchecked": set(cls.docs["rigs"][2]["unchecked"]),
            "Preset entry": set(cls.docs["presets"][0]["presets"][0]),
            "Performance entry": set(cls.docs["performances"][0]["performances"][0]),
        }
        main(["summary", b, "--write-golden", str(tmp / "census.json")])
        cls.census = set(json.loads((tmp / "census.json").read_text()))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_every_json_document_is_documented_key_for_key(self):
        """`rig` is one Rig entry, so its section lists only what the entry table does not."""
        sections = _sections(DOCS / "json.md")
        for name, docs in self.docs.items():
            keys = set().union(*(d.keys() for d in docs))
            if name == "rig":
                keys -= self.nested["Rig entry"]
            with self.subTest(document=name):
                self.assertEqual(sections.get(name), keys)

    def test_the_shared_shapes_are_documented_key_for_key(self):
        sections = _sections(DOCS / "json.md")
        for name, keys in self.nested.items():
            with self.subTest(shape=name):
                self.assertEqual(sections.get(name), keys)

    def test_the_census_keys_are_documented(self):
        self.assertEqual(_sections(DOCS / "census.md").get("Keys"), self.census)


class DocsTreeTest(unittest.TestCase):
    def test_the_index_lists_every_doc(self):
        index = (DOCS / "README.md").read_text()
        linked = {Path(t.split("#")[0]).name for t in _LINK.findall(index)}
        missing = [p.name for p in _doc_files() if p.name != "README.md" and p.name not in linked]
        self.assertEqual(missing, [])

    def test_every_relative_link_and_anchor_in_docs_resolves(self):
        bad = []
        for doc in _doc_files():
            for target in _LINK.findall(doc.read_text()):
                if "://" in target or target.startswith("mailto:"):
                    continue
                path, _, frag = target.partition("#")
                dest = (doc.parent / path).resolve() if path else doc
                if not dest.exists() or (frag and dest.suffix == ".md"
                                         and frag not in _anchors(dest)):
                    bad.append(f"{doc.name} -> {target}")
        self.assertEqual(bad, [])

    def test_the_readme_links_only_absolutely(self):
        readme = ROOT / "README.md"
        bad = [t for t in _LINK.findall(readme.read_text())
               if not (t.startswith(("https://", "mailto:"))
                       or (t.startswith("#") and t[1:] in _anchors(readme)))]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
