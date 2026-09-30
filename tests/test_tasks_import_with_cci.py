#!/usr/bin/env python3
"""The 12 task modules whose `tasks.*` imports TP-13b moved above their `cumulusci` import still
import in a fresh interpreter WITH CumulusCI installed (TP-13b).

Why this exists next to the AST rule (tests/test_rlm_sf_cli.py::TestTasksImportOrder): the rule pins
the source order, this proves the outcome. Once CumulusCI is loaded the `tasks` namespace package's
`__path__` collapses, so a `tasks.*` import that runs after it raises ImportError/ModuleNotFoundError.
Ten of these modules then failed to import outright, and two (`rlm_diff_ux`, `rlm_writeback_ux`)
imported "fine" but swallowed the error in `except ImportError: AssembleAndDeployUX = None`, silently
losing the class. Each module is imported in its own fresh interpreter, because a shared one already
has CumulusCI loaded, which is exactly the condition under test - so "import cumulusci, then the
module" in one process cannot discriminate.

Needs `cumulusci` and `requests` (two of the modules import it at module level). Deliberately NOT a
skip-on-missing-import suite: it is registered in scripts/ai/pr_gate.py with
`deps=["cumulusci", "requests"]`, so a missing dependency is MISSING-DEP = FAIL, and the
CumulusCI-less half lives in the stdlib tier (tests/test_rlm_sf_cli.py). Run with the CCI venv:

    <cci-venv-python> tests/test_tasks_import_with_cci.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The 12 modules TP-13b fixed. Mirrored in tests/test_rlm_sf_cli.py (_FIXED_IMPORT_ORDER_MODULES).
MODULES = (
    "rlm_analytics",
    "rlm_configure_core_pricing_setup",
    "rlm_configure_product_discovery_settings",
    "rlm_configure_revenue_settings",
    "rlm_diff_ux",
    "rlm_enable_constraints_settings",
    "rlm_enable_document_builder_toggle",
    "rlm_enable_timeline",
    "rlm_expression_set_connect",
    "rlm_reorder_app_launcher",
    "rlm_retrieve_ux",
    "rlm_writeback_ux",
)

_CHILD = r"""
import importlib, importlib.util, pathlib, sys
root, module, mode = sys.argv[1:4]
sys.path.insert(0, root)
if mode == "pkg":
    m = importlib.import_module("tasks." + module)
else:  # file-path load, as tests do to dodge the collapsed namespace package
    spec = importlib.util.spec_from_file_location("_p_" + module, pathlib.Path(root) / "tasks" / (module + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
# CumulusCI really is in play, not silently replaced by the module's fallbacks.
assert "cumulusci.core.tasks" in sys.modules, "cumulusci was not loaded"
# A tolerated ImportError must not have swallowed a tasks.* helper.
if module in ("rlm_diff_ux", "rlm_writeback_ux"):
    assert m.AssembleAndDeployUX is not None, "tasks.rlm_ux_assembly import was swallowed"
if module in ("rlm_retrieve_ux", "rlm_writeback_ux"):
    assert m.resolve_flexipage_sources.__module__.endswith("rlm_ux_utils"), m.resolve_flexipage_sources.__module__
"""


class TestTasksImportWithCumulusci(unittest.TestCase):
    def test_cumulusci_and_requests_are_installed(self):
        """A missing dependency fails here by name instead of as twelve ImportErrors."""
        import cumulusci.core.tasks  # noqa: F401
        import requests  # noqa: F401

    def test_each_module_imports_in_a_fresh_interpreter(self):
        for mode in ("pkg", "file"):
            for module in MODULES:
                with self.subTest(module=module, mode=mode):
                    result = subprocess.run(
                        [sys.executable, "-c", _CHILD, str(ROOT), module, mode],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.strip().splitlines()[-1:] or result.stdout)

    def test_module_list_matches_the_stdlib_tier(self):
        """One list, two files: drift between them would silently shrink one half's coverage."""
        import ast

        src = (ROOT / "tests" / "test_rlm_sf_cli.py").read_text(encoding="utf-8")
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_FIXED_IMPORT_ORDER_MODULES" for t in node.targets
            ):
                self.assertEqual(tuple(ast.literal_eval(node.value)), MODULES)
                return
        self.fail("_FIXED_IMPORT_ORDER_MODULES not found in tests/test_rlm_sf_cli.py")


if __name__ == "__main__":
    unittest.main(verbosity=1)
