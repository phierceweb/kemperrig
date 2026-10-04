"""The package stays dependency-light: stdlib plus one pf_core helper, nothing else.

The README promises a stdlib-only core; this is what keeps that true. A new third-party
import has to be a deliberate choice made here, not something that arrives with a patch.
"""

import ast
import os
import sys
import unittest

_SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "src", "kemperrig"))
_ALLOWED_THIRD_PARTY = {"pf_core"}


def _py_files() -> list[str]:
    return [os.path.join(d, f)
            for d, _, files in os.walk(_SRC)
            for f in files if f.endswith(".py") and "__pycache__" not in d]


def _top_level_imports(path: str) -> set[str]:
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module.split(".")[0])
    return out


class DependencyBoundaryTest(unittest.TestCase):
    def test_source_tree_is_present(self):
        self.assertTrue(_py_files(), f"no python files under {_SRC}")

    def test_only_stdlib_and_declared_dependencies(self):
        offenders = []
        for path in _py_files():
            for mod in _top_level_imports(path):
                if (mod in sys.stdlib_module_names or mod == "kemperrig"
                        or mod in _ALLOWED_THIRD_PARTY):
                    continue
                offenders.append(f"{os.path.relpath(path, _SRC)} -> {mod}")
        self.assertEqual(sorted(offenders), [], "undeclared third-party import")

    def test_pf_core_surface_stays_small(self):
        """Two symbols, and each only where it belongs.

        Pinning the symbols alone let a pf_core import land in any core module and still pass,
        so the module is pinned too: the CLI boundary and the three writers, nowhere else.
        """
        used = set()
        for path in _py_files():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            where = os.path.relpath(path, _SRC).replace(os.sep, "/")
            for node in ast.walk(tree):
                if (isinstance(node, ast.ImportFrom) and node.module
                        and node.module.startswith("pf_core")):
                    used.update(f"{where}: {node.module}.{a.name}" for a in node.names)
        self.assertEqual(used, {
            "services/edit.py: pf_core.utils.io.atomic_write_bytes",   # the three writers
            "services/extract.py: pf_core.utils.io.atomic_write_bytes",
            "services/census.py: pf_core.utils.io.atomic_write_bytes",
            "cli/__init__.py: pf_core.utils.env.resolve_str",          # CLI boundary only
            "cli/_curation.py: pf_core.utils.env.resolve_str",
        })


if __name__ == "__main__":
    unittest.main()
