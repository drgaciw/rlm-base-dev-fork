#!/usr/bin/env python3
"""Credential-handling tests for tasks/rlm_sfdmu.py (WP-07 security fixes).

Verifies, offline and without CumulusCI installed:
  1. No accessToken (or other token-shaped value) is ever emitted to the logger.
  2. `sf` CLI invocations never receive the raw access token as an org alias — the
     access-token-as-username fallback is removed; a missing alias raises instead.
  3. subprocess.run is always called with list argv, never a shell string / shell=True.
  4. export.json is only ever written with live credentials into a temp copy; the
     tracked plan directory (standing in for datasets/sfdmu/...) is left untouched.

Run: `python tests/test_rlm_sfdmu_redaction.py`
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tasks.rlm_sfdmu as rlm_sfdmu  # noqa: E402

FAKE_TOKEN = "00Dxx0000001gABEAY!AQFAKEACCESSTOKENVALUE1234567890ABCDE"


class _RecordingLogger:
    """Minimal logger stand-in that records every message passed to it."""

    def __init__(self):
        self.messages = []

    def _record(self, msg):
        self.messages.append(str(msg))

    def info(self, msg, *a, **k):
        self._record(msg)

    def warning(self, msg, *a, **k):
        self._record(msg)

    def error(self, msg, *a, **k):
        self._record(msg)

    def debug(self, msg, *a, **k):
        self._record(msg)

    def all_text(self) -> str:
        return "\n".join(self.messages)


class _FakeOrgConfig:
    """Stand-in for a CCI non-scratch org_config: token-only, no CLI username."""

    def __init__(self, access_token, instance_url, username=None, name="fake"):
        self.access_token = access_token
        self.instance_url = instance_url
        self.username = username
        self.name = name


def _write_plan(plan_dir: str, export_json: dict) -> None:
    with open(os.path.join(plan_dir, rlm_sfdmu.EXPORT_JSON_FILENAME), "w", encoding="utf-8") as f:
        json.dump(export_json, f)


def _ok_result(**kw):
    defaults = {"returncode": 0, "stdout": "", "stderr": ""}
    defaults.update(kw)
    return mock.Mock(**defaults)


class TestResolveCliOrgAlias(unittest.TestCase):
    def test_never_falls_back_to_access_token(self):
        org_config = _FakeOrgConfig(access_token=FAKE_TOKEN, instance_url="https://fake.my.salesforce.com")
        with self.assertRaises(rlm_sfdmu.TaskOptionsError):
            rlm_sfdmu._resolve_cli_org_alias(org_config, {}, "targetusername")

    def test_uses_option_alias_when_given(self):
        org_config = _FakeOrgConfig(access_token=FAKE_TOKEN, instance_url="https://fake.my.salesforce.com")
        alias = rlm_sfdmu._resolve_cli_org_alias(org_config, {"targetusername": "my-alias"}, "targetusername")
        self.assertEqual(alias, "my-alias")
        self.assertNotEqual(alias, FAKE_TOKEN)

    def test_uses_org_config_username_when_no_option(self):
        org_config = _FakeOrgConfig(access_token=FAKE_TOKEN, instance_url="https://fake.my.salesforce.com",
                                     username="user@example.com")
        alias = rlm_sfdmu._resolve_cli_org_alias(org_config, {}, "targetusername")
        self.assertEqual(alias, "user@example.com")

    def test_scratch_org_uses_username_even_with_option_set(self):
        # A-C3 (docs/ARCHITECT_REVIEW.md WP-11): with real CumulusCI installed,
        # ScratchOrgConfig.username is a read-only @property with no setter
        # (SfdxOrgConfig.username reads self.config.get("username")), so
        # `self.username = ...` in a subclass __init__ raises AttributeError.
        # A spec'd Mock intercepts attribute get/set itself — bypassing the real
        # property entirely — and still satisfies isinstance(..., ScratchOrgConfig)
        # via the spec, so it works identically with or without CumulusCI installed.
        fake_scratch = mock.Mock(spec=rlm_sfdmu.ScratchOrgConfig)
        fake_scratch.username = "scratch-alias"
        fake_scratch.access_token = FAKE_TOKEN

        alias = rlm_sfdmu._resolve_cli_org_alias(fake_scratch, {}, "targetusername")
        self.assertEqual(alias, "scratch-alias")


class TestRedactExportJsonForLog(unittest.TestCase):
    def test_masks_access_token_without_mutating_input(self):
        export_json = {"orgs": [{"name": "x", "accessToken": FAKE_TOKEN, "instanceUrl": "https://fake"}]}
        redacted = rlm_sfdmu._redact_export_json_for_log(export_json)
        self.assertNotIn(FAKE_TOKEN, json.dumps(redacted))
        self.assertEqual(export_json["orgs"][0]["accessToken"], FAKE_TOKEN)


class TestSfExecutableResolution(unittest.TestCase):
    """A-C2 (docs/ARCHITECT_REVIEW.md WP-11): on native Windows `sf` is installed
    as `sf.cmd`, and subprocess.run(["sf", ...]) with shell=False does not consult
    PATHEXT the way a shell does, so the bare name raises FileNotFoundError there.
    Every `sf` argv must resolve through shutil.which("sf") so it locates the real
    `sf.cmd` shim. Simulates that shim by monkeypatching shutil.which.
    """

    def test_resolves_cmd_shim_when_which_finds_it(self):
        with mock.patch.object(
            rlm_sfdmu.shutil, "which", return_value=r"C:\Users\dev\AppData\Roaming\npm\sf.cmd"
        ):
            self.assertEqual(rlm_sfdmu._sf_executable(), r"C:\Users\dev\AppData\Roaming\npm\sf.cmd")

    def test_falls_back_to_bare_name_when_which_finds_nothing(self):
        with mock.patch.object(rlm_sfdmu.shutil, "which", return_value=None):
            self.assertEqual(rlm_sfdmu._sf_executable(), "sf")

    def test_load_command_args_uses_resolved_executable(self):
        with mock.patch.object(rlm_sfdmu.shutil, "which", return_value=r"C:\tools\sf.cmd"):
            cmd = rlm_sfdmu._load_command_args("my-alias", "/plan/dir", "fake.my.salesforce.com")
        self.assertEqual(cmd[0], r"C:\tools\sf.cmd")

    def test_extract_command_args_uses_resolved_executable(self):
        with mock.patch.object(rlm_sfdmu.shutil, "which", return_value=r"C:\tools\sf.cmd"):
            cmd = rlm_sfdmu._extract_command_args("my-alias", "/work/dir")
        self.assertEqual(cmd[0], r"C:\tools\sf.cmd")


class TestCommandArgsAreLists(unittest.TestCase):
    def test_load_command_args_is_a_list_without_shell_metacharacters_risk(self):
        cmd = rlm_sfdmu._load_command_args("my-alias", "/plan/dir", "fake.my.salesforce.com")
        self.assertIsInstance(cmd, list)
        self.assertIn("my-alias", cmd)
        self.assertNotIn(FAKE_TOKEN, cmd)

    def test_extract_command_args_is_a_list(self):
        cmd = rlm_sfdmu._extract_command_args("my-alias", "/work/dir")
        self.assertIsInstance(cmd, list)
        self.assertIn("my-alias", cmd)
        self.assertNotIn(FAKE_TOKEN, cmd)


class TestLoadSFDMUDataNoTokenLeak(unittest.TestCase):
    def setUp(self):
        self.plan_dir = tempfile.mkdtemp(prefix="test_plan_")
        self.addCleanup(shutil.rmtree, self.plan_dir, ignore_errors=True)
        _write_plan(self.plan_dir, {"objectSets": [{"objects": []}]})

    def _make_task(self, targetusername=None):
        task = rlm_sfdmu.LoadSFDMUData.__new__(rlm_sfdmu.LoadSFDMUData)
        task.org_config = _FakeOrgConfig(access_token=FAKE_TOKEN, instance_url="https://fake.my.salesforce.com")
        task.logger = _RecordingLogger()
        task.options = {"pathtoexportjson": self.plan_dir, "org": True}
        if targetusername:
            task.options["targetusername"] = targetusername
        task.project_config = None
        task.keychain = None
        return task

    def test_missing_alias_raises_instead_of_using_token(self):
        task = self._make_task()
        with self.assertRaises(rlm_sfdmu.TaskOptionsError):
            task._prep_runtime()

    def test_run_task_never_logs_or_execs_the_token(self):
        task = self._make_task(targetusername="my-alias")
        with mock.patch.object(rlm_sfdmu.subprocess, "run", return_value=_ok_result()) as mock_run:
            task._run_task()

        call_args, call_kwargs = mock_run.call_args
        cmd = call_args[0]
        self.assertIsInstance(cmd, list)
        self.assertFalse(call_kwargs.get("shell", False))
        for arg in cmd:
            self.assertNotIn(FAKE_TOKEN, arg)
        self.assertIn("my-alias", cmd)
        self.assertNotIn(FAKE_TOKEN, task.logger.all_text())

    def test_credentials_never_written_to_tracked_plan_dir(self):
        task = self._make_task(targetusername="my-alias")
        with mock.patch.object(rlm_sfdmu.subprocess, "run", return_value=_ok_result()):
            task._run_task()

        tracked_export_path = os.path.join(self.plan_dir, rlm_sfdmu.EXPORT_JSON_FILENAME)
        with open(tracked_export_path, encoding="utf-8") as f:
            tracked_raw = f.read()
        self.assertNotIn(FAKE_TOKEN, tracked_raw)
        tracked = json.loads(tracked_raw)
        self.assertEqual(tracked.get("orgs", []), [])

        # the staged temp copy is cleaned up after the run
        self.assertIsNotNone(task._temp_plan_dir)
        self.assertFalse(os.path.isdir(task._temp_plan_dir))

    def test_sync_objectset_source_to_source_never_writes_tracked_plan_dir(self):
        # A-C16 (docs/ARCHITECT_REVIEW.md WP-11): _sync_objectset_source_to_source
        # used to run BEFORE staging, so it wrote source/*.csv straight into the
        # tracked plan_dir under datasets/sfdmu/. Staging must happen first so the
        # sync only ever touches the temp copy.
        os.makedirs(os.path.join(self.plan_dir, "objectset_source", "object-set-1"))
        with open(
            os.path.join(self.plan_dir, "objectset_source", "object-set-1", "Foo.csv"),
            "w", encoding="utf-8",
        ) as f:
            f.write("Id,Name\n1,a\n")

        task = self._make_task(targetusername="my-alias")
        task.options["sync_objectset_source_to_source"] = True
        with mock.patch.object(rlm_sfdmu.subprocess, "run", return_value=_ok_result()):
            task._prep_runtime()

        self.assertFalse(
            os.path.isdir(os.path.join(self.plan_dir, "source")),
            "sync_objectset_source_to_source wrote into the tracked plan_dir",
        )
        self.assertNotEqual(task._temp_plan_dir, self.plan_dir)
        self.assertTrue(
            os.path.isfile(os.path.join(task._temp_plan_dir, "source", "Foo_source.csv"))
        )
        shutil.rmtree(task._temp_plan_dir, ignore_errors=True)


class TestExtractSFDMUDataNoTokenLeak(unittest.TestCase):
    def setUp(self):
        self.plan_dir = tempfile.mkdtemp(prefix="test_extract_plan_")
        self.addCleanup(shutil.rmtree, self.plan_dir, ignore_errors=True)
        _write_plan(self.plan_dir, {"objectSets": [{"objects": []}]})
        # An explicit output_dir, because the default is <plan_dir>/../../extractions — and
        # plan_dir is a mkdtemp() directly under the temp root, so that resolves to
        # /extractions. On a CI runner (non-root) that is a PermissionError; run as root it
        # silently litters the filesystem root.
        self.output_dir = tempfile.mkdtemp(prefix="test_extract_out_")
        self.addCleanup(shutil.rmtree, self.output_dir, ignore_errors=True)

    def _make_task(self, sourceusername=None):
        task = rlm_sfdmu.ExtractSFDMUData.__new__(rlm_sfdmu.ExtractSFDMUData)
        task.org_config = _FakeOrgConfig(access_token=FAKE_TOKEN, instance_url="https://fake.my.salesforce.com")
        task.logger = _RecordingLogger()
        task.options = {
            "pathtoexportjson": self.plan_dir,
            "output_dir": self.output_dir,
            "org": True,
            "run_post_process": False,
        }
        if sourceusername:
            task.options["sourceusername"] = sourceusername
        task.project_config = None
        task.keychain = None
        return task

    def test_missing_alias_raises_instead_of_using_token(self):
        task = self._make_task()
        with self.assertRaises(rlm_sfdmu.TaskOptionsError):
            task._run_task()

    def test_run_task_never_logs_or_execs_the_token(self):
        task = self._make_task(sourceusername="my-alias")
        with mock.patch.object(rlm_sfdmu.subprocess, "run", return_value=_ok_result()) as mock_run:
            task._run_task()

        call_args, call_kwargs = mock_run.call_args
        cmd = call_args[0]
        self.assertIsInstance(cmd, list)
        self.assertFalse(call_kwargs.get("shell", False))
        for arg in cmd:
            self.assertNotIn(FAKE_TOKEN, arg)
        self.assertIn("my-alias", cmd)
        self.assertNotIn(FAKE_TOKEN, task.logger.all_text())


class TestIdempotencyNoTokenLeak(unittest.TestCase):
    def setUp(self):
        self.plan_dir = tempfile.mkdtemp(prefix="test_idem_plan_")
        self.addCleanup(shutil.rmtree, self.plan_dir, ignore_errors=True)
        _write_plan(self.plan_dir, {"objectSets": [{"objects": []}]})

    def _make_task(self, targetusername=None):
        task = rlm_sfdmu.TestSFDMUIdempotency.__new__(rlm_sfdmu.TestSFDMUIdempotency)
        task.org_config = _FakeOrgConfig(access_token=FAKE_TOKEN, instance_url="https://fake.my.salesforce.com")
        task.logger = _RecordingLogger()
        task.options = {"pathtoexportjson": self.plan_dir, "org": True}
        if targetusername:
            task.options["targetusername"] = targetusername
        task.accesstoken = FAKE_TOKEN
        task.instanceurl = "https://fake.my.salesforce.com"
        return task

    def test_get_org_for_cli_never_falls_back_to_token(self):
        task = self._make_task()
        with self.assertRaises(rlm_sfdmu.TaskOptionsError):
            task._get_org_for_cli()

    def test_run_load_once_does_not_write_credentials_into_passed_plan_dir(self):
        # A-C9 (docs/ARCHITECT_REVIEW.md WP-11): the tracked plan_dir's export.json
        # never had an "orgs" key to begin with (_write_plan writes
        # {"objectSets": [...]}), so asserting against it AFTER the run always
        # passes -- even if temp staging were completely broken -- because
        # `.get("orgs", [])` trivially returns [] for a key that was never there.
        # Assert from inside the subprocess.run side effect instead, at the moment
        # SFDMU would actually run: this is the one point where, if _run_load_once
        # regressed to writing credentials into the passed-in plan_dir instead of a
        # temp copy, the tracked file would actually contain them.
        tracked_export_path = os.path.join(self.plan_dir, rlm_sfdmu.EXPORT_JSON_FILENAME)
        observed = {}

        def _capture_tracked_file_state(*args, **kwargs):
            with open(tracked_export_path, encoding="utf-8") as f:
                observed["raw"] = f.read()
            return _ok_result()

        task = self._make_task(targetusername="my-alias")
        with mock.patch.object(
            rlm_sfdmu.subprocess, "run", side_effect=_capture_tracked_file_state
        ) as mock_run:
            task._run_load_once(self.plan_dir)

        call_args, call_kwargs = mock_run.call_args
        cmd = call_args[0]
        self.assertIsInstance(cmd, list)
        self.assertFalse(call_kwargs.get("shell", False))
        for arg in cmd:
            self.assertNotIn(FAKE_TOKEN, arg)
        self.assertNotIn(FAKE_TOKEN, task.logger.all_text())

        self.assertIn("raw", observed, "subprocess.run side effect never ran")
        self.assertNotIn(FAKE_TOKEN, observed["raw"])
        self.assertEqual(json.loads(observed["raw"]).get("orgs", []), [])


if __name__ == "__main__":
    unittest.main()
