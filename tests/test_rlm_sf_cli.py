#!/usr/bin/env python3
"""Tests for tasks/rlm_sf_cli.py and its migration across tasks/ (TP-13).

On native Windows the Salesforce CLI is `sf.cmd`; `subprocess.run(["sf", ...])` with list argv
and `shell=False` does not consult PATHEXT, so the bare name raises FileNotFoundError.
`sf_executable()` returns `shutil.which("sf") or "sf"`. Offline, stdlib-only (no CumulusCI, no
`requests`, no org, no CLI), so it runs on the Windows leg where this fix matters.

What is pinned:

1. **The helper** - `which` patched to a `.cmd` shim and to None.
2. **argv pin table (`PINS`)** - every argv literal in tasks/ whose first element is the bare
   `"sf"` or `sf_executable()` / `_sf_executable()`, keyed by `module::Class.method#ordinal`
   (ordinal = position of the sf argv within that function, so unrelated edits elsewhere in a
   file do not move it) -> `ast.unparse` of `argv[1:]`. The migration changed argv[0] only; this
   table is what makes "argv[1:] is unchanged" a standing CI check instead of a one-off.
   The set of keys is EXHAUSTIVE: a new, removed or edited site fails the test with the keys
   named. Intentional change: `python tests/test_rlm_sf_cli.py --write-pins` (rewrites only the
   table between the BEGIN/END markers; never run in CI) and justify the diff in the PR.
3. **Sites whose argv is not one literal** are listed in `INCREMENTAL` and each has a
   behavioural test that patches `subprocess.run` and asserts the FULL argv:
   - `rlm_create_persona_user::CreatePersonaUser._create_scratch_user#0` - `--set-unique-username`
     is appended after the literal (`TestIncrementalSites`).
   - `rlm_sfdmu::_load_command_args#0` / `_extract_command_args#0` - return their argv for callers
     to extend; driven by tests/test_subprocess_contracts.py::TestSfdmuUsesResolvedExecutable.
   The detector flags any literal bound to a name that is later mutated (`+=`, `.append`,
   `.extend`, `.insert`) or that is returned, so a new such site must be added to `INCREMENTAL`.
4. **`run_sf_json`** resolves argv[0] itself, so its callers keep the literal `"sf"`.
5. **One resolver** - `tasks/rlm_sfdmu.py` aliases the shared helper and has no `which("sf")`.
   Checked on the AST because importing the module needs `requests`.

6. **Import order** - in every `tasks/*.py`, no module-level `tasks.*` import may follow a
   `cumulusci` import (`TestTasksImportOrder`). Once CumulusCI is loaded the `tasks` namespace
   package's `__path__` collapses, so the later import fails when the module is imported directly
   (architect review A-C3); this broke the first push of TP-13. `LEGACY_IMPORT_ORDER` was the exact
   list of the 12 modules that already broke the rule before TP-13; TP-13b fixed them and the list
   is now empty. A new violation AND a stale entry both fail, so it can only shrink.

Run: `python tests/test_rlm_sf_cli.py`  (also collectable by pytest).
"""
from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "tasks"
THIS_FILE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(ROOT))

# `tasks.rlm_sf_cli` and `tasks.rlm_agents_common` are imported normally and FIRST: they are the
# modules the others resolve through `from tasks.rlm_sf_cli import ...`, and importing them
# registers them in sys.modules. The remaining task modules are loaded by file path, because once
# CumulusCI is loaded (it is installed in CI) the `tasks` namespace package's `__path__` collapses
# and every later `import tasks.<x>` fails - see tests/test_rest_contracts.py::_load.
import tasks.rlm_sf_cli as rlm_sf_cli  # noqa: E402
import tasks.rlm_agents_common as rlm_agents_common  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_tp13_{name}", TASKS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rlm_create_persona_user = _load("rlm_create_persona_user")
rlm_test_agents = _load("rlm_test_agents")
rlm_validate_setup = _load("rlm_validate_setup")

SHIM = r"C:\Users\dev\AppData\Roaming\npm\sf.cmd"

# --------------------------------------------------------------------------------------
# argv pin table. Generated: `python tests/test_rlm_sf_cli.py --write-pins`.
# --------------------------------------------------------------------------------------
# BEGIN PINS
PINS: dict = {
    'rlm_activate_agents::ActivateAgents._activate#0':
        "'agent', 'activate', '--api-name', api_name, '--target-org', target, '--json'",
    'rlm_agents_common::run_sf_json#0':
        '*cmd[1:]',
    'rlm_apex_file::FileBasedAnonymousApexTask._run_sf_apex#0':
        "'apex', 'run', '--target-org', org_alias, '--file', apex_file_path, '--json'",
    'rlm_bre::ExportBRE._do_retrieve_metadata#0':
        "'project', 'retrieve', 'start', '--manifest', manifest_path, '--target-org', username, '--target-metadata-dir', mdapi_dir",
    'rlm_bre::ExportBRE._do_retrieve_metadata#1':
        "'project', 'convert', 'mdapi', '--root-dir', mdapi_dir, '--output-dir', source_dir",
    'rlm_create_persona_user::CreatePersonaUser._create_scratch_user#0':
        "'org', 'create', 'user', '--definition-file', definition_file, '--set-alias', alias, '--target-org', self.org_config.username",
    'rlm_create_persona_user::CreatePersonaUser._find_existing_user#0':
        "'data', 'query', '--query', soql, '--json', '--target-org', self.org_config.username",
    'rlm_create_persona_user::CreatePersonaUser._resolve_profile_id#0':
        "'data', 'query', '--query', soql, '--json', '--target-org', self.org_config.username",
    'rlm_deactivate_agents::DeactivateAgents._deactivate#0':
        "'agent', 'deactivate', '--api-name', api_name, '--target-org', target, '--json'",
    'rlm_publish_agents::PublishAgents._publish_bundle#0':
        "'agent', 'publish', 'authoring-bundle', '--api-name', api_name, '--target-org', target, '--json'",
    'rlm_repair_pricing_schedules::EnsurePricingSchedules._deploy_settings#0':
        "'project', 'deploy', 'start', '--source-dir', settings_path, '--target-org', target_org, '--json'",
    'rlm_sfdmu::ExtractSFDMUData._sf_query_records#0':
        "'data', 'query', '--target-org', org, '-q', soql, '--json'",
    'rlm_sfdmu::LoadSFDMUData._get_target_org_user_name#0':
        "'data', 'query', '-q', query, '-o', org_for_cli, '--json'",
    'rlm_sfdmu::LoadSFDMUData._set_project_defaults#0':
        "'config', 'set', f'instanceUrl={instanceurl}'",
    'rlm_sfdmu::TestSFDMUIdempotency._get_record_counts#0':
        "'data', 'query', '-q', f'SELECT COUNT(Id) cnt FROM {sobject}', '-o', org_alias, '--json'",
    'rlm_sfdmu::TestSFDMUIdempotency._run_post_load_apex_if_configured#0':
        "'apex', 'run', '--target-org', org, '--file', path",
    'rlm_sfdmu::_extract_command_args#0':
        "'sfdmu', 'run', '--sourceusername', sourceusername, '--targetusername', 'CSVFILE', '-p', pathtoexportjson, '--noprompt', '--verbose'",
    'rlm_sfdmu::_load_command_args#0':
        "'sfdmu', 'run', '--sourceusername', 'CSVFILE', '--targetusername', targetusername, '-p', pathtoexportjson, '--canmodify', instanceurl, '--noprompt', '--verbose'",
    'rlm_stamp_commit::StampGitCommit._deploy#0':
        "'project', 'deploy', 'start', '--source-dir', 'force-app', '--target-org', org_username, '--ignore-conflicts', '--wait', str(DEPLOY_WAIT_MINUTES), '--json'",
    'rlm_test_agents::TestAgents._create#0':
        "'agent', 'test', 'create', '--spec', str(spec), '--api-name', api_name, '--force-overwrite', '--target-org', target, '--json'",
    'rlm_test_agents::TestAgents._run_and_evaluate#0':
        "'agent', 'test', 'run', '--api-name', api_name, '--wait', str(self.RUN_WAIT_MINUTES), '--result-format', 'json', '--json', '--target-org', target",
    'rlm_ux_assembly::AssembleAndDeployUX._deploy#0':
        "'project', 'deploy', 'start', '--source-dir', str(output_path), '--target-org', username, '--ignore-conflicts', '--json'",
    'rlm_validate_setup::ValidateSetup._check_sf_cli#0':
        "'--version'",
    'rlm_validate_setup::ValidateSetup._get_sfdmu_version#0':
        "'plugins', '--json'",
    'rlm_validate_setup::ValidateSetup._get_sfdmu_version#1':
        "'plugins'",
    'rlm_validate_setup::ValidateSetup._install_or_update_sfdmu#0':
        "'plugins', 'install', 'sfdmu'",
}
# END PINS

# Sites whose argv is not a single literal handed straight to subprocess: key -> where the full
# argv is asserted. Local entries name a test method on TestIncrementalSites.
INCREMENTAL = {
    "rlm_create_persona_user::CreatePersonaUser._create_scratch_user#0": "test_scratch_user_argv",
    "rlm_sfdmu::_extract_command_args#0": "tests/test_subprocess_contracts.py::TestSfdmuUsesResolvedExecutable",
    "rlm_sfdmu::_load_command_args#0": "tests/test_subprocess_contracts.py::TestSfdmuUsesResolvedExecutable",
}

_RESOLVER_NAMES = {"sf_executable", "_sf_executable"}

# Empty: TP-13b fixed the 12 modules that put a `tasks.*` import after a `cumulusci` import before
# TP-13. A new violation fails `test_no_new_import_order_violations`; the fix is to move the import
# above the `try: from cumulusci...` block, not to list the module here. Kept as a name -> reason
# mapping so `test_no_stale_legacy_entries` still guards any entry that is ever added.
LEGACY_IMPORT_ORDER: dict = {}


# --------------------------------------------------------------------------------------
# AST collection
# --------------------------------------------------------------------------------------


def _is_sf_argv(node) -> bool:
    if not (isinstance(node, (ast.List, ast.Tuple)) and node.elts):
        return False
    first = node.elts[0]
    if isinstance(first, ast.Constant) and first.value == "sf":
        return True
    return (
        isinstance(first, ast.Call)
        and isinstance(first.func, ast.Name)
        and first.func.id in _RESOLVER_NAMES
        and not first.args
    )


def _scope(node, parents):
    """(qualname, function node or None) for the function/class chain enclosing `node`."""
    names, func = [], None
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(cur.name)
            if func is None and not isinstance(cur, ast.ClassDef):
                func = cur
    return ".".join(reversed(names)) or "<module>", func


def _mutated_after_binding(func, name) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
            and node.func.attr in ("append", "extend", "insert")
        ):
            return True
    return False


def collect_sites(path: pathlib.Path):
    """[(key, tail, is_incremental)] for every sf argv literal in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found = {}
    for node in ast.walk(tree):
        if not _is_sf_argv(node):
            continue
        qualname, func = _scope(node, parents)
        parent = parents.get(node)
        incremental = isinstance(parent, ast.Return)
        if (
            func is not None
            and isinstance(parent, ast.Assign)
            and len(parent.targets) == 1
            and isinstance(parent.targets[0], ast.Name)
        ):
            incremental = _mutated_after_binding(func, parent.targets[0].id)
        found.setdefault(qualname, []).append((node.lineno, node.col_offset, node, incremental))
    sites = []
    for qualname, items in found.items():
        for ordinal, (_, _, node, incremental) in enumerate(sorted(items, key=lambda i: i[:2])):
            tail = ", ".join(ast.unparse(e) for e in node.elts[1:])
            sites.append((f"{path.stem}::{qualname}#{ordinal}", tail, incremental))
    return sites


def collect_all():
    pins, incremental = {}, set()
    for path in sorted(TASKS_DIR.glob("*.py")):
        for key, tail, inc in collect_sites(path):
            pins[key] = tail
            if inc:
                incremental.add(key)
    return pins, incremental


def render_pins(pins: dict) -> str:
    lines = ["PINS: dict = {"]
    lines += [f"    {key!r}:\n        {tail!r}," for key, tail in sorted(pins.items())]
    lines.append("}")
    return "\n".join(lines)


def write_pins() -> None:
    pins, _ = collect_all()
    src = THIS_FILE.read_text(encoding="utf-8")
    new = re.sub(
        r"(# BEGIN PINS\n).*?(\n# END PINS)",
        lambda m: m.group(1) + render_pins(pins) + m.group(2),
        src,
        count=1,
        flags=re.S,
    )
    THIS_FILE.write_text(new, encoding="utf-8", newline="")
    print(f"wrote {len(pins)} pins to {THIS_FILE.name}")


# --------------------------------------------------------------------------------------
# 1. helper
# --------------------------------------------------------------------------------------


class TestSfExecutable(unittest.TestCase):
    def test_returns_the_which_result_for_a_cmd_shim(self):
        with mock.patch.object(rlm_sf_cli.shutil, "which", return_value=SHIM) as which:
            self.assertEqual(rlm_sf_cli.sf_executable(), SHIM)
        which.assert_called_once_with("sf")

    def test_falls_back_to_the_bare_name_when_which_finds_nothing(self):
        with mock.patch.object(rlm_sf_cli.shutil, "which", return_value=None):
            self.assertEqual(rlm_sf_cli.sf_executable(), "sf")

    def test_empty_which_result_also_falls_back(self):
        with mock.patch.object(rlm_sf_cli.shutil, "which", return_value=""):
            self.assertEqual(rlm_sf_cli.sf_executable(), "sf")

    def test_resolves_on_every_call_rather_than_caching(self):
        with mock.patch.object(rlm_sf_cli.shutil, "which", side_effect=[None, SHIM]):
            self.assertEqual(rlm_sf_cli.sf_executable(), "sf")
            self.assertEqual(rlm_sf_cli.sf_executable(), SHIM)


# --------------------------------------------------------------------------------------
# 2. argv pin table (exhaustive)
# --------------------------------------------------------------------------------------


class TestArgvPins(unittest.TestCase):
    HINT = (
        "If the change is intentional, run `python tests/test_rlm_sf_cli.py --write-pins` "
        "(it only rewrites the PINS table) and justify the diff in the PR."
    )

    def test_pin_table_matches_every_sf_argv_in_tasks(self):
        current, _ = collect_all()
        added = sorted(set(current) - set(PINS))
        removed = sorted(set(PINS) - set(current))
        changed = sorted(k for k in set(PINS) & set(current) if PINS[k] != current[k])
        self.assertEqual(
            (added, removed, changed),
            ([], [], []),
            f"sf argv sites drifted from PINS. added={added} removed={removed} "
            f"changed={[(k, PINS[k], current[k]) for k in changed]}. {self.HINT}",
        )

    def test_table_is_not_vacuous(self):
        self.assertGreaterEqual(len(PINS), 20, "PINS is empty or truncated - run --write-pins")
        modules = {key.split("::", 1)[0] for key in PINS}
        for expected in (
            "rlm_activate_agents", "rlm_apex_file", "rlm_bre", "rlm_create_persona_user",
            "rlm_deactivate_agents", "rlm_publish_agents", "rlm_repair_pricing_schedules",
            "rlm_stamp_commit", "rlm_test_agents", "rlm_ux_assembly", "rlm_validate_setup",
            "rlm_agents_common", "rlm_sfdmu",
        ):
            self.assertIn(expected, modules)

    def test_incremental_sites_are_exactly_the_reviewed_set(self):
        _, incremental = collect_all()
        self.assertEqual(
            sorted(incremental),
            sorted(INCREMENTAL),
            "a sf argv that is built up (append/+=/extend) or returned was added or removed. "
            "Give it a behavioural test that asserts the full argv, then update INCREMENTAL.",
        )

    def test_local_incremental_tests_exist(self):
        for key, where in INCREMENTAL.items():
            if "::" not in where:
                self.assertTrue(hasattr(TestIncrementalSites, where), f"{key}: no test {where}")

    def test_no_shell_true_added(self):
        offenders = []
        for path in sorted(TASKS_DIR.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call):
                    for kw in node.keywords:
                        if kw.arg == "shell" and not (
                            isinstance(kw.value, ast.Constant) and kw.value.value is False
                        ):
                            offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_detector_controls(self):
        """The collector must see each shape, so an AST walk that matches nothing fails here."""

        def sites(src):
            tree = ast.parse(src)
            parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
            out = []
            for node in ast.walk(tree):
                if _is_sf_argv(node):
                    out.append((_scope(node, parents)[0], ast.unparse(node)))
            return out

        self.assertEqual(len(sites("def f():\n    run(['sf', 'org', 'list'])\n")), 1)
        self.assertEqual(len(sites("def f():\n    run([sf_executable(), 'org'])\n")), 1)
        self.assertEqual(len(sites("def f():\n    run([_sf_executable(), 'org'])\n")), 1)
        self.assertEqual(len(sites("x = ('sf', 'config')\n")), 1)
        self.assertEqual(sites("a = ['sfdmu']\nb = ['git', 'sf']\nc = [sf]\n"), [])
        self.assertEqual(sites("def f():\n    run([which('sf'), 'org'])\n"), [])


# --------------------------------------------------------------------------------------
# 3. behavioural tests: run_sf_json, incremental sites, cheap sites
# --------------------------------------------------------------------------------------


class _Logger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class _Org:
    username = "user@example.com"


def _completed(stdout="", returncode=0, stderr=""):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestRunSfJsonResolvesArgv0(unittest.TestCase):
    def _run(self, cmd, which):
        seen = []

        def fake_run(argv, **kwargs):
            seen.append((argv, kwargs))
            return _completed(json.dumps({"status": 0}))

        with mock.patch.object(rlm_sf_cli.shutil, "which", return_value=which), mock.patch.object(
            rlm_agents_common.subprocess, "run", side_effect=fake_run
        ):
            rlm_agents_common.run_sf_json(cmd, timeout=5, label="x")
        return seen

    def test_bare_sf_becomes_the_cmd_shim_and_the_tail_is_unchanged(self):
        cmd = ["sf", "agent", "activate", "--api-name", "A", "--target-org", "u@x.com", "--json"]
        argv, kwargs = self._run(list(cmd), SHIM)[0]
        self.assertEqual(argv[0], SHIM)
        self.assertEqual(argv[1:], cmd[1:])
        self.assertFalse(kwargs.get("shell", False))

    def test_falls_back_to_bare_sf_where_which_finds_nothing(self):
        self.assertEqual(self._run(["sf", "agent", "publish", "--json"], None)[0][0], ["sf", "agent", "publish", "--json"])

    def test_does_not_mutate_the_callers_list(self):
        cmd = ["sf", "agent", "activate", "--json"]
        self._run(cmd, SHIM)
        self.assertEqual(cmd, ["sf", "agent", "activate", "--json"])

    def test_leaves_a_non_sf_argv0_alone(self):
        self.assertEqual(self._run(["/opt/tools/sf", "org", "list"], SHIM)[0][0], ["/opt/tools/sf", "org", "list"])

    def test_missing_cli_still_raises_a_command_exception(self):
        with mock.patch.object(rlm_sf_cli.shutil, "which", return_value=None), mock.patch.object(
            rlm_agents_common.subprocess, "run", side_effect=FileNotFoundError("sf")
        ):
            with self.assertRaises(rlm_agents_common.CommandException) as ctx:
                rlm_agents_common.run_sf_json(["sf", "x"], timeout=5, label="sf x")
        self.assertIn("'sf') was not found", str(ctx.exception))


class TestIncrementalSites(unittest.TestCase):
    def _task(self, cls, **attrs):
        task = object.__new__(cls)
        task.logger = _Logger()
        task.org_config = _Org()
        for k, v in attrs.items():
            setattr(task, k, v)
        return task

    def _capture(self, fn, which=SHIM):
        seen = []

        def fake_run(argv, **kwargs):
            seen.append((argv, kwargs))
            return _completed("{}")

        with mock.patch.object(rlm_sf_cli.shutil, "which", return_value=which), mock.patch.object(
            rlm_create_persona_user.subprocess, "run", side_effect=fake_run
        ):
            fn()
        return seen

    def test_scratch_user_argv(self):
        task = self._task(rlm_create_persona_user.CreatePersonaUser)
        base = ["org", "create", "user", "--definition-file", "def.json", "--set-alias", "qb", "--target-org", "user@example.com"]
        for set_unique, tail in ((True, ["--set-unique-username"]), (False, [])):
            with self.subTest(set_unique=set_unique):
                seen = self._capture(lambda: task._create_scratch_user("def.json", "qb", set_unique))
                argv, kwargs = seen[0]
                self.assertEqual(argv, [SHIM, *base, *tail])
                self.assertFalse(kwargs.get("shell", False))

    def test_scratch_user_falls_back_to_bare_sf(self):
        task = self._task(rlm_create_persona_user.CreatePersonaUser)
        seen = self._capture(lambda: task._create_scratch_user("d.json", "a", False), which=None)
        self.assertEqual(seen[0][0][0], "sf")


class TestCheapSitesUseTheResolvedExecutable(unittest.TestCase):
    """Sites that are one literal handed to subprocess.run: assert the full argv end to end."""

    def _validate_setup(self):
        task = object.__new__(rlm_validate_setup.ValidateSetup)
        task.logger = _Logger()
        return task

    def _capture(self, module, fn, stdout="", which=SHIM):
        seen = []

        def fake_run(argv, **kwargs):
            seen.append((argv, kwargs))
            return _completed(stdout)

        with mock.patch.object(rlm_sf_cli.shutil, "which", return_value=which), mock.patch.object(
            module.subprocess, "run", side_effect=fake_run
        ):
            fn()
        return seen

    def test_validate_setup_version_check(self):
        task = self._validate_setup()
        seen = self._capture(rlm_validate_setup, task._check_sf_cli, "@salesforce/cli/2.60.1 win32-x64\n")
        self.assertEqual(seen[0][0], [SHIM, "--version"])

    def test_validate_setup_plugin_queries(self):
        task = self._validate_setup()
        # `plugins --json` returns nothing parseable -> falls through to the plain-text query.
        seen = self._capture(rlm_validate_setup, task._get_sfdmu_version, "not json")
        self.assertEqual([argv for argv, _ in seen], [[SHIM, "plugins", "--json"], [SHIM, "plugins"]])

    def test_validate_setup_plugin_install(self):
        task = self._validate_setup()
        seen = self._capture(rlm_validate_setup, lambda: task._install_or_update_sfdmu("SFDMU"), "")
        self.assertEqual(seen[0][0], [SHIM, "plugins", "install", "sfdmu"])

    def test_agent_test_run_argv(self):
        task = object.__new__(rlm_test_agents.TestAgents)
        task.logger = _Logger()
        payload = json.dumps({"result": {"testCases": []}})
        spec = pathlib.Path("specs") / "a.yaml"
        seen = self._capture(rlm_test_agents, lambda: task._run_and_evaluate(spec, "My_Agent", "u@x.com"), payload)
        self.assertEqual(
            seen[0][0],
            [SHIM, "agent", "test", "run", "--api-name", "My_Agent", "--wait", "15",
             "--result-format", "json", "--json", "--target-org", "u@x.com"],
        )

    def test_every_direct_site_falls_back_to_bare_sf_without_which(self):
        task = self._validate_setup()
        seen = self._capture(rlm_validate_setup, task._check_sf_cli, "@salesforce/cli/2.60.1\n", which=None)
        self.assertEqual(seen[0][0], ["sf", "--version"])


# --------------------------------------------------------------------------------------
# 6. import order: no `tasks.*` import after a `cumulusci` import
# --------------------------------------------------------------------------------------


def _import_roots(tree: ast.AST):
    """[(lineno, imported module)] for module-level imports (including those inside top-level
    try/except/if/with blocks), in source order. Function/class bodies and lambdas are excluded:
    they run later, not at import time."""
    found = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Import):
                found.extend((child.lineno, alias.name) for alias in child.names)
            elif isinstance(child, ast.ImportFrom) and child.level == 0 and child.module:
                found.append((child.lineno, child.module))
            visit(child)

    visit(tree)
    return sorted(found)


def _is_pkg(module: str, root: str) -> bool:
    return module == root or module.startswith(root + ".")


def late_tasks_imports(tree: ast.AST):
    """[(lineno, module)] of `tasks.*` imports that come after the first `cumulusci` import."""
    imports = _import_roots(tree)
    cci = [line for line, mod in imports if _is_pkg(mod, "cumulusci")]
    if not cci:
        return []
    first = min(cci)
    return [(line, mod) for line, mod in imports if _is_pkg(mod, "tasks") and line > first]


def _violating_modules():
    out = {}
    for path in sorted(TASKS_DIR.glob("*.py")):
        late = late_tasks_imports(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if late:
            out[path.stem] = late
    return out


class TestTasksImportOrder(unittest.TestCase):
    HINT = (
        "Move the `tasks.*` import above the `try: from cumulusci...` block (see the note in "
        "tasks/rlm_sfdmu.py). Do not add a module to LEGACY_IMPORT_ORDER."
    )

    def test_no_new_import_order_violations(self):
        new = {m: late for m, late in _violating_modules().items() if m not in LEGACY_IMPORT_ORDER}
        self.assertEqual(new, {}, f"tasks.* import after a cumulusci import: {new}. {self.HINT}")

    def test_no_stale_legacy_entries(self):
        stale = sorted(set(LEGACY_IMPORT_ORDER) - set(_violating_modules()))
        self.assertEqual(
            stale,
            [],
            f"LEGACY_IMPORT_ORDER lists modules that no longer violate the rule: {stale}. "
            "The order was fixed - delete the entry so it cannot come back unnoticed.",
        )

    def test_every_legacy_entry_carries_its_reason(self):
        for module, reason in LEGACY_IMPORT_ORDER.items():
            self.assertTrue(reason.strip(), module)
            self.assertTrue((TASKS_DIR / f"{module}.py").is_file(), f"{module}: no such module")

    def test_the_sf_resolver_importers_are_not_legacy(self):
        """The modules this PR touches must be clean: they are the ones the shared helper reaches."""
        importers = set()
        for path in sorted(TASKS_DIR.glob("*.py")):
            for _, mod in _import_roots(ast.parse(path.read_text(encoding="utf-8"))):
                if mod in ("tasks.rlm_sf_cli", "tasks.rlm_agents_common"):
                    importers.add(path.stem)
        self.assertTrue(importers, "expected importers of the shared helper")
        self.assertEqual(sorted(importers & set(LEGACY_IMPORT_ORDER)), [])
        self.assertEqual(sorted(importers & set(_violating_modules())), [])

    def test_negative_controls(self):
        """The detector must flag each violating shape and spare each clean one."""

        def late(source):
            return late_tasks_imports(ast.parse(source))

        # from-import after a cci import inside try/except (the real-world shape)
        violating = (
            "try:",
            "    from cumulusci.core.tasks import BaseTask",
            "except ImportError:",
            "    BaseTask = object",
            "from tasks.rlm_agents_common import run_sf_json",
        )
        self.assertEqual(late("\n".join(violating)), [(5, "tasks.rlm_agents_common")])
        # plain `import tasks.x`, and a tasks import nested in a later top-level try
        self.assertEqual(len(late("import cumulusci\nimport tasks.rlm_sf_cli\n")), 1)
        nested = ("import cumulusci", "try:", "    from tasks import x", "except ImportError:", "    x = 1")
        self.assertEqual(len(late("\n".join(nested))), 1)
        # correct order, function/class-level imports, other packages and lookalike names are clean
        self.assertEqual(late("from tasks.rlm_sf_cli import f\nimport cumulusci\n"), [])
        self.assertEqual(late("import cumulusci\ndef g():\n    from tasks import x\n"), [])
        self.assertEqual(late("import cumulusci\nclass C:\n    from tasks import x\n"), [])
        self.assertEqual(late("from tasks import x\n"), [])
        self.assertEqual(late("import cumulusci\nimport mytasks\nfrom tasksfoo import y\n"), [])
        self.assertEqual(late("import cumulusci_extras\nfrom tasks import x\n"), [])


# Imports one task module in a FRESH interpreter with the `cumulusci` package made unimportable, which
# is the case the `except ImportError` fallbacks exist for. The CumulusCI-installed half of the same
# check lives in tests/test_tasks_import_with_cci.py (it needs cumulusci + requests, this tier has
# neither). `requests` is stubbed only when absent: two of the modules import it at module level and
# the import ORDER, not requests itself, is what is under test.
_IMPORT_BLOCKED_CCI_CHILD = r"""
import importlib, importlib.util, pathlib, sys, types
root, module, mode = sys.argv[1:4]
sys.path.insert(0, root)
class _Block:
    def find_spec(self, name, path=None, target=None):
        if name == "cumulusci" or name.startswith("cumulusci."):
            raise ImportError("cumulusci blocked by test")
sys.meta_path.insert(0, _Block())
try:
    import requests  # noqa: F401
except ImportError:
    sys.modules["requests"] = types.ModuleType("requests")
if mode == "pkg":
    m = importlib.import_module("tasks." + module)
else:
    spec = importlib.util.spec_from_file_location("_p_" + module, pathlib.Path(root) / "tasks" / (module + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
if module in ("rlm_diff_ux", "rlm_writeback_ux"):
    assert m.AssembleAndDeployUX is not None, "tasks.rlm_ux_assembly import was swallowed"
"""

# The 12 modules TP-13b fixed. Mirrored in tests/test_tasks_import_with_cci.py.
_FIXED_IMPORT_ORDER_MODULES = (
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


class TestFixedModulesImportWithoutCumulusci(unittest.TestCase):
    """The AST rule pins the order; this proves the outcome for the 12 modules TP-13b fixed."""

    def test_each_module_imports_in_a_fresh_interpreter_without_cumulusci(self):
        import subprocess

        for mode in ("pkg", "file"):
            for module in _FIXED_IMPORT_ORDER_MODULES:
                with self.subTest(module=module, mode=mode):
                    result = subprocess.run(
                        [sys.executable, "-c", _IMPORT_BLOCKED_CCI_CHILD, str(ROOT), module, mode],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.strip().splitlines()[-1:] or result.stdout)


# --------------------------------------------------------------------------------------
# 5. one resolver
# --------------------------------------------------------------------------------------


class TestSingleResolver(unittest.TestCase):
    def test_sfdmu_aliases_the_shared_helper_and_has_no_resolver_of_its_own(self):
        src = (TASKS_DIR / "rlm_sfdmu.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        self.assertIn("from tasks.rlm_sf_cli import sf_executable", src)
        aliases = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_sf_executable" for t in n.targets)
            and isinstance(n.value, ast.Name) and n.value.id == "sf_executable"
        ]
        self.assertEqual(len(aliases), 1)
        self.assertFalse(
            [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_sf_executable"],
            "rlm_sfdmu grew its own _sf_executable() again - use tasks/rlm_sf_cli.py::sf_executable",
        )

    def test_which_sf_appears_only_in_the_shared_helper(self):
        offenders = []
        for path in sorted(TASKS_DIR.glob("*.py")):
            if path.name == "rlm_sf_cli.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "which"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "sf"
                ):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [], "a second `sf` resolver - use tasks/rlm_sf_cli.py::sf_executable")


if __name__ == "__main__":
    if "--write-pins" in sys.argv:
        write_pins()
    else:
        unittest.main(verbosity=1)
