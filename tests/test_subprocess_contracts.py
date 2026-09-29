#!/usr/bin/env python3
"""Contract tests for every `sf` subprocess site in tasks/ (TP-03, test plan 4.1 rule 2).

On native Windows the Salesforce CLI is installed as `sf.cmd`. `subprocess.run(["sf", ...])`
with list argv and `shell=False` does not consult PATHEXT the way a shell does, so a bare
`"sf"` as argv[0] raises FileNotFoundError there (A-C2). `tasks/rlm_sf_cli.py::sf_executable`
(TP-13) is the one resolver in the tree: `shutil.which("sf") or "sf"`.

Three things are pinned here, offline and without CumulusCI or a Salesforce org:

1. **Positive leg** - every `sf` subprocess site in `tasks/rlm_sfdmu.py` is driven with
   `shutil.which` patched to a `.cmd` shim path and `subprocess.run` recorded: argv[0] is the
   shim, argv is a list of strings, `shell` is never truthy. A registry check fails when a new
   subprocess site appears in the module without being added here.
2. **Gap accounting** - `KNOWN_GAPS` maps each module that still passes a bare `"sf"` to its
   EXACT number of bare-`sf` sites (counts, not line numbers, so unrelated edits do not churn
   it). It is empty since TP-13; it stays as the allowlist mechanism so a future exception is
   explicit. Detection is AST-based (a list/tuple literal whose first element is the string
   `"sf"`), so a fix or a regression cannot slip past a string match. The comparison is exact in
   both directions: a count that goes UP (a new bare site, in a listed module or not) fails as a
   new gap, and a count that goes DOWN fails as stale until the entry is lowered or deleted, so a
   partial fix shows up site by site.
3. **`run_sf_json` is a fix point** - `tasks/rlm_agents_common.run_sf_json` resolves argv[0]
   itself, so its callers' `"sf"` literals are not gaps and a behavioural check proves it
   (tests/test_rlm_sf_cli.py pins the rest of the argv). If it ever stops resolving, each
   caller's literal becomes a gap again and must be listed or fixed.

No `shell=True` (or `os.system`) is allowed anywhere in `tasks/`.

Run: `python tests/test_subprocess_contracts.py`  (also collectable by pytest).
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "tasks"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tasks.rlm_sfdmu as rlm_sfdmu  # noqa: E402

SHIM = r"C:\Users\dev\AppData\Roaming\npm\sf.cmd"
FAKE_TOKEN = "00Dxx0000001gABEAY!AQFAKEACCESSTOKENVALUE1234567890ABCDE"

# module (tasks/<name>.py) -> (exact number of bare-'sf' sites, why). Empty since TP-13 applied the
# shared tasks/rlm_sf_cli.py::sf_executable() to every module and to run_sf_json. Do not add an
# entry to silence a new bare 'sf': resolve the executable instead. Counts are compared exactly:
# lower the number in the same change that fixes a site, delete the entry when it reaches zero.
KNOWN_GAPS: dict = {}

# Every module that calls run_sf_json. A new caller has to be added here on purpose, which is
# the prompt to check that its argv resolves the executable.
RUN_SF_JSON_CALLERS = frozenset(
    {"rlm_activate_agents", "rlm_deactivate_agents", "rlm_publish_agents", "rlm_test_agents"}
)

_SUBPROCESS_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}


# --------------------------------------------------------------------------------------
# AST helpers
# --------------------------------------------------------------------------------------


def _parse(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _parents(tree: ast.AST) -> dict:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _enclosing_function(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def _is_bare_sf_literal(node) -> bool:
    return (
        isinstance(node, (ast.List, ast.Tuple))
        and bool(node.elts)
        and isinstance(node.elts[0], ast.Constant)
        and node.elts[0].value == "sf"
    )


def _callee_name(call: ast.Call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _lists_passed_to(func_node, helper_name: str) -> set:
    """List/tuple nodes that reach `helper_name(...)` as its first argument in `func_node`,
    directly or through a local name assigned from the literal."""
    if func_node is None:
        return set()
    assigned = {}
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
    passed = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call) and _callee_name(node) == helper_name and node.args:
            first = node.args[0]
            if isinstance(first, (ast.List, ast.Tuple)):
                passed.add(first)
            elif isinstance(first, ast.Name):
                passed.update(assigned.get(first.id, []))
    return passed


def _run_sf_json_resolves_executable(tree: ast.AST) -> bool:
    """True when `run_sf_json` itself resolves the CLI (shutil.which / an sf_executable helper)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_sf_json":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Attribute) and inner.attr == "which":
                    return True
                if isinstance(inner, (ast.Name, ast.Attribute)):
                    ident = inner.id if isinstance(inner, ast.Name) else inner.attr
                    if "sf_executable" in ident:
                        return True
    return False


def bare_sf_sites(tree: ast.AST, run_sf_json_resolves: bool):
    """[(lineno, via_run_sf_json)] for every bare-`sf` argv literal that is still a gap."""
    parents = _parents(tree)
    sites = []
    for node in ast.walk(tree):
        if not _is_bare_sf_literal(node):
            continue
        func = _enclosing_function(node, parents)
        via_helper = node in _lists_passed_to(func, "run_sf_json")
        if via_helper and run_sf_json_resolves:
            continue
        sites.append((node.lineno, via_helper))
    return sorted(sites)


def _run_sf_json_callers(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call) and _callee_name(node) == "run_sf_json"
        for node in ast.walk(tree)
    )


def _task_modules():
    return sorted(p for p in TASKS_DIR.glob("*.py") if p.name != "__init__.py")


def _current_gaps():
    """{module: [(lineno, via_run_sf_json), ...]} for tasks/ as it is on disk."""
    resolves = _run_sf_json_resolves_executable(_parse(TASKS_DIR / "rlm_agents_common.py"))
    gaps = {}
    for path in _task_modules():
        sites = bare_sf_sites(_parse(path), resolves)
        if sites:
            gaps[path.stem] = sites
    return gaps


def _gap_counts():
    """{module: number of bare-'sf' sites} - the quantity KNOWN_GAPS pins exactly."""
    return {module: len(sites) for module, sites in _current_gaps().items()}


def _load_by_path(name):
    """Load tasks/<name>.py by file path, not `from tasks import x`: once CumulusCI is loaded the
    `tasks` namespace package's `__path__` collapses to `[]` and a second `tasks.*` import fails
    (see tests/test_decision_table_tasks.py::load_task_module). Not registered in sys.modules."""
    spec = importlib.util.spec_from_file_location(f"_tp03_{name}", TASKS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_run_sf_json_uses_resolved_executable(testcase, module):
    """Behavioural proof that `module.run_sf_json` swaps a bare 'sf' for shutil.which('sf')."""
    seen = []

    def fake_run(argv, **kwargs):
        seen.append(argv)
        return mock.Mock(returncode=0, stdout=json.dumps({"status": 0}), stderr="")

    with mock.patch.object(shutil, "which", return_value=SHIM), mock.patch.object(
        module.subprocess, "run", side_effect=fake_run
    ):
        module.run_sf_json(["sf", "agent", "activate"], timeout=5, label="x")
    testcase.assertEqual(len(seen), 1)
    testcase.assertEqual(seen[0][0], SHIM, "run_sf_json passed the bare 'sf' through")


# --------------------------------------------------------------------------------------
# 2 + 3. Gap accounting (AST) and run_sf_json coverage
# --------------------------------------------------------------------------------------


class TestKnownGaps(unittest.TestCase):
    def test_no_stale_known_gap_entries(self):
        counts = _gap_counts()
        stale = {
            module: {"listed": listed, "measured": counts.get(module, 0)}
            for module, (listed, _reason) in KNOWN_GAPS.items()
            if counts.get(module, 0) < listed
        }
        self.assertEqual(
            stale,
            {},
            f"KNOWN_GAPS lists more bare 'sf' sites than tasks/ still has: {stale}. A site was "
            "fixed - lower the count (delete the entry at zero) so a regression cannot hide "
            "behind the old number.",
        )

    def test_no_new_bare_sf_gaps(self):
        counts = _gap_counts()
        gaps = _current_gaps()
        new = {
            module: {
                "listed": KNOWN_GAPS.get(module, (0, ""))[0],
                "measured": count,
                "sites": gaps[module],
            }
            for module, count in counts.items()
            if count > KNOWN_GAPS.get(module, (0, ""))[0]
        }
        self.assertEqual(
            new,
            {},
            f"tasks/ has more bare 'sf' argv[0] sites than KNOWN_GAPS allows: {new}. On native "
            "Windows this raises FileNotFoundError (A-C2). Resolve the executable with "
            "shutil.which('sf') or 'sf' (see tasks/rlm_sfdmu.py::_sf_executable).",
        )

    def test_known_gap_counts_are_positive(self):
        for module, (count, _reason) in KNOWN_GAPS.items():
            self.assertGreater(count, 0, f"{module}: delete the entry instead of listing zero")

    def test_known_gap_reasons_name_the_follow_up(self):
        for module, (_count, reason) in KNOWN_GAPS.items():
            self.assertIn("TP-13", reason, module)

    def test_sfdmu_is_the_resolved_reference_implementation(self):
        self.assertNotIn("rlm_sfdmu", _current_gaps())
        self.assertNotIn("rlm_sfdmu", KNOWN_GAPS)


class TestRunSfJsonCoverage(unittest.TestCase):
    def test_callers_of_run_sf_json_are_exactly_the_reviewed_set(self):
        callers = {
            p.stem
            for p in _task_modules()
            if p.stem != "rlm_agents_common" and _run_sf_json_callers(_parse(p))
        }
        self.assertEqual(
            callers,
            set(RUN_SF_JSON_CALLERS),
            "the set of run_sf_json callers changed - check the new caller's argv[0] resolves "
            "the sf executable, then update RUN_SF_JSON_CALLERS",
        )

    def test_run_sf_json_is_not_a_fix_point_unless_it_resolves_the_executable(self):
        resolves = _run_sf_json_resolves_executable(_parse(TASKS_DIR / "rlm_agents_common.py"))
        if not resolves:
            # Not a fix point: every caller's literal is its own gap and must be listed.
            self.assertTrue(RUN_SF_JSON_CALLERS <= set(KNOWN_GAPS), sorted(RUN_SF_JSON_CALLERS - set(KNOWN_GAPS)))
            return
        # TP-13 landed: prove it behaviourally rather than trusting the AST heuristic.
        _assert_run_sf_json_uses_resolved_executable(self, _load_by_path("rlm_agents_common"))

    def test_behavioural_check_control(self):
        """The branch above is only live once TP-13 lands, so pin the helper it relies on now:
        it must pass for a resolving run_sf_json and fail for one that passes argv through."""
        resolving = types.ModuleType("resolving")
        resolving.subprocess = subprocess

        def resolving_run_sf_json(cmd, *, timeout, label):
            cmd = [shutil.which("sf") or "sf"] + list(cmd[1:])
            return resolving.subprocess.run(cmd, timeout=timeout)

        resolving.run_sf_json = resolving_run_sf_json
        _assert_run_sf_json_uses_resolved_executable(self, resolving)

        passthrough = types.ModuleType("passthrough")
        passthrough.subprocess = subprocess
        passthrough.run_sf_json = lambda cmd, *, timeout, label: passthrough.subprocess.run(
            cmd, timeout=timeout
        )
        with self.assertRaises(AssertionError):
            _assert_run_sf_json_uses_resolved_executable(self, passthrough)


class TestNoShell(unittest.TestCase):
    def test_no_shell_true_or_os_system_anywhere_in_tasks(self):
        offenders = []
        for path in _task_modules():
            for node in ast.walk(_parse(path)):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg == "shell" and not (
                        isinstance(kw.value, ast.Constant) and kw.value.value is False
                    ):
                        offenders.append(f"{path.name}:{node.lineno} shell=")
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr in ("system", "popen")
                ):
                    offenders.append(f"{path.name}:{node.lineno} os.{func.attr}")
        self.assertEqual(offenders, [], offenders)


class TestDetectorControls(unittest.TestCase):
    """The detector must catch what it claims to: a control per shape, so a vacuous pass
    (an AST walk that matches nothing) fails here instead of hiding a real gap."""

    def _sites(self, source, resolves=False):
        return bare_sf_sites(ast.parse(source), resolves)

    def test_detects_a_literal_list_argument(self):
        self.assertEqual(self._sites("def f():\n    subprocess.run(['sf', 'org', 'list'])\n"), [(2, False)])

    def test_detects_a_list_bound_to_a_variable(self):
        src = "def f():\n    cmd = [\n        'sf', 'data', 'query',\n    ]\n    subprocess.run(cmd)\n"
        self.assertEqual(len(self._sites(src)), 1)

    def test_detects_a_tuple(self):
        self.assertEqual(len(self._sites("x = ('sf', 'config')\n")), 1)

    def test_ignores_a_resolved_executable(self):
        self.assertEqual(self._sites("def f():\n    subprocess.run([_sf_executable(), 'org', 'list'])\n"), [])
        self.assertEqual(self._sites("def f():\n    subprocess.run([sf, 'org', 'list'])\n"), [])

    def test_ignores_other_binaries_and_similar_names(self):
        self.assertEqual(self._sites("a = ['sfdmu', 'run']\nb = ['sf-cli']\nc = ['git', 'sf']\n"), [])

    def test_helper_route_is_a_gap_until_the_helper_resolves(self):
        src = "def f():\n    cmd = ['sf', 'agent', 'activate']\n    run_sf_json(cmd, timeout=1, label='x')\n"
        self.assertEqual(self._sites(src, resolves=False), [(2, True)])
        self.assertEqual(self._sites(src, resolves=True), [])

    def test_helper_flag_does_not_hide_a_direct_bare_call_in_the_same_function(self):
        src = (
            "def f():\n"
            "    a = ['sf', 'agent', 'test', 'create']\n"
            "    run_sf_json(a, timeout=1, label='x')\n"
            "    subprocess.run(['sf', 'agent', 'test', 'run'])\n"
        )
        self.assertEqual(self._sites(src, resolves=True), [(4, False)])

    def test_run_sf_json_resolution_detector(self):
        resolving = "def run_sf_json(cmd):\n    cmd = [shutil.which('sf') or 'sf'] + cmd[1:]\n"
        helper_call = "def run_sf_json(cmd):\n    cmd = [sf_executable()] + cmd[1:]\n"
        plain = "def run_sf_json(cmd):\n    subprocess.run(cmd)\n"
        self.assertTrue(_run_sf_json_resolves_executable(ast.parse(resolving)))
        self.assertTrue(_run_sf_json_resolves_executable(ast.parse(helper_call)))
        self.assertFalse(_run_sf_json_resolves_executable(ast.parse(plain)))


# --------------------------------------------------------------------------------------
# 1. Positive leg: rlm_sfdmu with an sf.cmd shim
# --------------------------------------------------------------------------------------


class _RecordingLogger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class _FakeOrgConfig:
    def __init__(self, username="user@example.com"):
        self.access_token = FAKE_TOKEN
        self.instance_url = "https://fake.my.salesforce.com"
        self.username = username
        self.name = "fake"


def _result(stdout=""):
    return mock.Mock(returncode=0, stdout=stdout, stderr="")


_RECORDS = json.dumps({"result": {"records": [{"Name": "Admin User", "cnt": 3}]}})


class TestSfdmuUsesResolvedExecutable(unittest.TestCase):
    """Each driver exercises one subprocess site in tasks/rlm_sfdmu.py. Keys are
    'Class.method' and must equal the set of functions that contain a subprocess call
    (minus the exemptions below), so a new site cannot be added without a driver."""

    # sys.executable, not sf.
    EXEMPT = {"run_post_process_script"}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_subprocess_contracts_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        with open(os.path.join(self.tmp, rlm_sfdmu.EXPORT_JSON_FILENAME), "w", encoding="utf-8") as fh:
            json.dump({"objectSets": [{"objects": []}]}, fh)
        self.out = tempfile.mkdtemp(prefix="test_subprocess_contracts_out_")
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)
        self.calls = []

    def _new(self, cls, **options):
        task = cls.__new__(cls)
        task.org_config = _FakeOrgConfig()
        task.logger = _RecordingLogger()
        task.project_config = None
        task.keychain = None
        task.options = {"pathtoexportjson": self.tmp, "org": True, **options}
        task.accesstoken = FAKE_TOKEN
        task.instanceurl = "https://fake.my.salesforce.com"
        return task

    def _record(self, args, **kwargs):
        self.calls.append((args[0], kwargs))
        return _result(_RECORDS)

    def _drive(self, driver):
        self.calls = []
        with mock.patch.object(rlm_sfdmu.shutil, "which", return_value=SHIM), mock.patch.object(
            rlm_sfdmu.subprocess, "run", side_effect=lambda *a, **k: self._record(a, **k)
        ):
            driver()

    def _assert_shim_argv(self, name):
        self.assertTrue(self.calls, f"{name}: no subprocess call was made")
        for argv, kwargs in self.calls:
            self.assertIsInstance(argv, list, name)
            self.assertTrue(all(isinstance(a, str) for a in argv), f"{name}: {argv}")
            self.assertEqual(argv[0], SHIM, f"{name}: argv[0] is not the resolved sf.cmd")
            self.assertFalse(kwargs.get("shell", False), f"{name}: shell must not be set")
            self.assertNotIn(FAKE_TOKEN, " ".join(argv), f"{name}: token in argv")

    def _drivers(self):
        load, extract, idem = (
            rlm_sfdmu.LoadSFDMUData,
            rlm_sfdmu.ExtractSFDMUData,
            rlm_sfdmu.TestSFDMUIdempotency,
        )
        apex = os.path.join(self.tmp, "post.apex")
        with open(apex, "w", encoding="utf-8") as fh:
            fh.write("System.debug(1);")

        def loader(**options):
            return self._new(load, targetusername="my-alias", **options)

        def idempotency(**options):
            return self._new(idem, targetusername="my-alias", **options)

        def extractor(**options):
            return self._new(extract, sourceusername="my-alias", **options)

        return {
            "LoadSFDMUData._get_target_org_user_name": (
                lambda: self._new(load, targetusername="user@example.com")._get_target_org_user_name()
            ),
            "LoadSFDMUData._set_project_defaults": (
                lambda: self._new(load)._set_project_defaults("https://fake.my.salesforce.com")
            ),
            "LoadSFDMUData._run_task": lambda: loader()._run_task(),
            "TestSFDMUIdempotency._get_record_counts": lambda: idempotency()._get_record_counts(["Account"]),
            "TestSFDMUIdempotency._run_load_once": lambda: idempotency()._run_load_once(self.tmp),
            "TestSFDMUIdempotency._run_extract_once": lambda: idempotency()._run_extract_once(self.tmp),
            "TestSFDMUIdempotency._run_post_load_apex_if_configured": (
                lambda: idempotency(run_after_each_load_apex=apex)._run_post_load_apex_if_configured()
            ),
            "ExtractSFDMUData._run_task": (
                lambda: extractor(output_dir=self.out, run_post_process=False)._run_task()
            ),
            "ExtractSFDMUData._sf_query_records": (
                lambda: extractor()._sf_query_records("SELECT Id FROM Account")
            ),
        }

    def test_every_sf_subprocess_site_gets_the_resolved_executable(self):
        for name, driver in self._drivers().items():
            with self.subTest(site=name):
                self._drive(driver)
                self._assert_shim_argv(name)

    def test_falls_back_to_bare_sf_where_which_finds_nothing(self):
        # macOS/Linux path: nothing to resolve, the bare name is correct there.
        self.calls = []
        task = self._new(rlm_sfdmu.LoadSFDMUData)
        with mock.patch.object(rlm_sfdmu.shutil, "which", return_value=None), mock.patch.object(
            rlm_sfdmu.subprocess, "run", side_effect=lambda *a, **k: self._record(a, **k)
        ):
            task._set_project_defaults("https://fake.my.salesforce.com")
        self.assertEqual(self.calls[0][0][0], "sf")

    def test_driver_registry_matches_the_subprocess_sites_in_the_module(self):
        tree = _parse(TASKS_DIR / "rlm_sfdmu.py")
        parents = _parents(tree)
        found = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _SUBPROCESS_FUNCS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                func = _enclosing_function(node, parents)
                owner = parents.get(func)
                qualified = f"{owner.name}.{func.name}" if isinstance(owner, ast.ClassDef) else func.name
                found.add(qualified)
        self.assertEqual(
            found - self.EXEMPT,
            set(self._drivers()),
            "a subprocess site was added to (or removed from) tasks/rlm_sfdmu.py - add or "
            "drop its driver so the sf.cmd argv contract keeps covering every site",
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
