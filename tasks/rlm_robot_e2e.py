"""Run E2E functional tests via Robot Framework.

Passes the org identifier (username or alias), feature flags, and browser
mode to Robot Framework test suites. Feature flags are read from the CCI
project custom settings and injected as Robot variables so tests can use
``Skip If`` to gate on feature availability.

With ``rerun_failed=true`` (the nightly org job, docs/references/test-plan-2026-09.md
section 4.8) the failed subset is re-run exactly once (``robot --rerunfailed``) and the
two outputs are merged with ``rebot --merge``. A test that failed and then passed is
reported as **flaky**, never as green: ``e2e-summary.json`` in the output directory
carries the per-test ``pass`` / ``flaky`` / ``fail`` / ``skip`` classification.
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# Imported before the CCI try/except below: CumulusCI's import machinery collapses the
# `tasks` namespace package's __path__ once it is loaded, so a same-package
# `from tasks.x import y` done afterwards raises ModuleNotFoundError (the A-C3 ordering
# hazard, see tasks/rlm_sfdmu.py and tests/test_decision_table_tasks.py).
from tasks.robot_utils import check_urllib3_for_robot

try:
    from cumulusci.core.tasks import BaseTask
    from cumulusci.core.exceptions import TaskOptionsError
except ImportError:
    BaseTask = object  # type: ignore
    TaskOptionsError = Exception  # type: ignore

DEFAULT_SUITE = "robot/rlm-base/tests/e2e"
DEFAULT_OUTPUT_DIR = "robot/rlm-base/results"

# Feature flags to pass from project__custom to Robot variables
FEATURE_FLAGS = [
    "qb", "billing", "constraints", "dro", "clm", "rating", "rates",
    "payments", "approvals", "docgen", "prm", "commerce",
    "guidedselling", "tso", "ux",
]


SUMMARY_FILENAME = "e2e-summary.json"
FIRST_OUTPUT = "first.xml"
RERUN_OUTPUT = "rerun.xml"
MERGED_OUTPUT = "output.xml"

# Robot exit codes 1..249 are the number of failed tests; 250+ are framework-level
# conditions (252 invalid arguments / no tests selected, 253 stopped, 255 unexpected
# internal error), none of which a rerun of "the failed tests" can address.
MAX_FAILED_EXIT_CODE = 249


def parse_robot_results(xml_path):
    """Return ``{full test name: PASS|FAIL|SKIP}`` for a Robot ``output.xml``.

    Handles the Robot 6 and 7 schemas (the test's own ``<status>`` is its last direct
    ``<status>`` child in both). Names are the dotted suite path plus test name, so
    two suites that each contain a test of the same name stay distinct.
    """
    results = {}

    def walk(node, prefix):
        for child in node:
            if child.tag == "suite":
                walk(child, prefix + [child.get("name", "")])
            elif child.tag == "test":
                status = None
                for grandchild in child:
                    if grandchild.tag == "status":
                        status = grandchild.get("status")
                name = ".".join(prefix + [child.get("name", "")])
                results[name] = (status or "FAIL").upper()

    root = ET.parse(str(xml_path)).getroot()
    walk(root, [])
    return results


def classify_results(first, rerun=None):
    """Classify each test as pass / flaky / fail / skip.

    ``first`` and ``rerun`` are ``parse_robot_results`` mappings; ``rerun`` is None when
    no rerun happened. flaky = failed the first time and passed on the rerun (the
    definition in test-plan section 7.1). A test that failed and failed again, or failed
    and did not run again, is a plain fail.
    """
    rerun = rerun or {}
    tests = []
    for name, first_status in sorted(first.items()):
        final_status = rerun.get(name, first_status)
        if first_status == "FAIL" and final_status == "PASS":
            result = "flaky"
        elif final_status == "PASS":
            result = "pass"
        elif final_status == "SKIP":
            result = "skip"
        else:
            result = "fail"
        tests.append(
            {"name": name, "first": first_status, "final": final_status, "result": result}
        )
    return tests


def summarize(tests):
    counts = {"pass": 0, "flaky": 0, "fail": 0, "skip": 0}
    for test in tests:
        counts[test["result"]] += 1
    return counts


class RunE2ETests(BaseTask):
    """Run end-to-end Robot Framework tests with org and feature flag context."""

    task_options = {
        "suite": {
            "description": "Path to the Robot test suite or directory.",
            "required": False,
        },
        "outputdir": {
            "description": "Directory for Robot output (log.html, report.html, output.xml).",
            "required": False,
        },
        "headed": {
            "description": (
                "Run Chrome in headed (visible) mode with CDP debugging port 9222. "
                "Default: false (headless)."
            ),
            "required": False,
        },
        "include_tags": {
            "description": "Comma-separated Robot tags to include (--include).",
            "required": False,
        },
        "exclude_tags": {
            "description": "Comma-separated Robot tags to exclude (--exclude).",
            "required": False,
        },
        "rerun_failed": {
            "description": (
                "Re-run the failed tests exactly once (robot --rerunfailed) and merge "
                "both outputs with rebot --merge. A pass-after-rerun is reported as "
                "flaky in e2e-summary.json and the task log, not as a clean pass. "
                "Default: false (no retries)."
            ),
            "required": False,
        },
        "pause_for_recording": {
            "description": (
                "Pause at key steps for DOM inspection via Chrome DevTools. "
                "Only effective when headed=true. Default: false."
            ),
            "required": False,
        },
    }

    def _run_task(self):
        check_urllib3_for_robot(task_name="RunE2ETests")

        org_name = getattr(self.org_config, "username", None)
        if not org_name:
            org_name = getattr(self.org_config, "name", None) or getattr(
                self.org_config, "alias", None
            )
        if not org_name:
            raise TaskOptionsError(
                "RunE2ETests requires an org "
                "(run with --org or set org_config)."
            )

        repo_root = Path(self.project_config.repo_root)
        suite = self.options.get("suite") or DEFAULT_SUITE
        suite_path = repo_root / suite
        if not suite_path.exists():
            raise TaskOptionsError(
                f"Robot suite not found at path: {suite_path}. "
                "Check the 'suite' task option or update the default suite path."
            )

        outputdir = self.options.get("outputdir") or DEFAULT_OUTPUT_DIR
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = repo_root / outputdir / f"e2e_{timestamp}"
        out_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "robot",
            "--variable",
            f"ORG_ALIAS:{org_name}",
        ]

        # Pass headed/debug mode
        headed = str(self.options.get("headed", "false")).lower() == "true"
        if headed:
            cmd.extend(["--variable", "HEADED:true"])
        pause = str(self.options.get("pause_for_recording", "false")).lower() == "true"
        if pause and headed:
            cmd.extend(["--variable", "PAUSE_FOR_RECORDING:true"])
        elif pause and not headed:
            self.logger.warning(
                "pause_for_recording was requested but headed=false; "
                "ignoring PAUSE_FOR_RECORDING to avoid hanging headless/CI runs."
            )

        # Pass feature flags from project custom settings
        custom = getattr(self.project_config, "project__custom", {}) or {}
        for flag in FEATURE_FLAGS:
            raw_value = custom.get(flag, False)
            if isinstance(raw_value, str):
                normalized = raw_value.strip().lower()
                value = normalized in ("true", "1", "yes", "y", "on")
            else:
                value = bool(raw_value)
            robot_value = "true" if value else "false"
            cmd.extend(["--variable", f"{flag.upper()}:{robot_value}"])

        # Tag filtering
        include_tags = self.options.get("include_tags")
        if include_tags:
            for tag in include_tags.split(","):
                tag = tag.strip()
                if tag:
                    cmd.extend(["--include", tag])

        exclude_tags = self.options.get("exclude_tags")
        if exclude_tags:
            for tag in exclude_tags.split(","):
                tag = tag.strip()
                if tag:
                    cmd.extend(["--exclude", tag])

        rerun_failed = (
            str(self.options.get("rerun_failed", "false")).strip().lower() == "true"
        )
        if not rerun_failed:
            self._run_single_pass(cmd, suite_path, out_path, repo_root, org_name)
            return
        self._run_with_rerun(cmd, suite_path, out_path, repo_root, org_name)

    # -- execution helpers ---------------------------------------------------

    def _run_robot(self, cmd, repo_root, label):
        self.logger.info("%s: %s", label, " ".join(cmd))
        return subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _log_output_tails(self, result, tail_lines=50):
        for stream_name, text in (("stdout", result.stdout), ("stderr", result.stderr)):
            if not text:
                continue
            lines = text.splitlines()
            tail = "\n".join(lines[-tail_lines:])
            prefix = (
                f"... (truncated, {len(lines) - tail_lines} lines omitted)\n"
                if len(lines) > tail_lines
                else ""
            )
            self.logger.warning(
                "Robot %s (last %d lines):\n%s%s", stream_name, tail_lines, prefix, tail
            )

    def _run_single_pass(self, cmd, suite_path, out_path, repo_root, org_name):
        """One robot run, no retry (the default): fail the task on any test failure."""
        cmd = cmd + ["--outputdir", str(out_path), str(suite_path)]
        result = self._run_robot(cmd, repo_root, f"Running E2E tests for org {org_name}")
        if result.returncode != 0:
            self._log_output_tails(result)
            raise RuntimeError(
                f"E2E tests failed (exit code {result.returncode}). "
                f"Check {out_path / 'log.html'} for details."
            )
        self.logger.info("E2E tests passed successfully.")

    def _run_with_rerun(self, cmd, suite_path, out_path, repo_root, org_name):
        """Run, re-run the failed subset once, merge, and classify pass / flaky / fail."""
        first_xml = out_path / FIRST_OUTPUT
        rerun_xml = out_path / RERUN_OUTPUT
        rerun_dir = out_path / "rerun"

        # log/report are produced once, from the merged output, by rebot below.
        first_cmd = cmd + [
            "--outputdir", str(out_path),
            "--output", FIRST_OUTPUT, "--log", "NONE", "--report", "NONE",
            str(suite_path),
        ]
        first = self._run_robot(
            first_cmd, repo_root, f"Running E2E tests for org {org_name} (attempt 1)"
        )
        if first.returncode > MAX_FAILED_EXIT_CODE or not first_xml.exists():
            self._log_output_tails(first)
            raise RuntimeError(
                f"E2E run did not complete (robot exit code {first.returncode}); "
                "no rerun attempted. Check the task log above."
            )
        first_results = parse_robot_results(first_xml)

        rerun_results = None
        if first.returncode != 0:
            self.logger.warning(
                "%d E2E test(s) failed; re-running the failed subset once.",
                first.returncode,
            )
            # Own subdirectory: step screenshots are named by a per-run counter and
            # would overwrite the first attempt's evidence in a shared directory.
            rerun_cmd = cmd + [
                "--rerunfailed", str(first_xml),
                "--outputdir", str(rerun_dir),
                "--output", str(rerun_xml.name), "--log", "NONE", "--report", "NONE",
                str(suite_path),
            ]
            rerun = self._run_robot(rerun_cmd, repo_root, "Re-running failed E2E tests")
            rerun_output = rerun_dir / rerun_xml.name
            if rerun.returncode > MAX_FAILED_EXIT_CODE or not rerun_output.exists():
                self._log_output_tails(rerun)
                self.logger.warning(
                    "Rerun did not complete (robot exit code %s); first-attempt "
                    "failures stand.",
                    rerun.returncode,
                )
            else:
                rerun_results = parse_robot_results(rerun_output)

        rebot_cmd = [
            sys.executable, "-m", "robot.rebot",
            "--outputdir", str(out_path),
            "--output", MERGED_OUTPUT, "--log", "log.html", "--report", "report.html",
        ]
        merge_inputs = [str(first_xml)]
        if rerun_results is not None:
            rebot_cmd.append("--merge")
            merge_inputs.append(str(rerun_dir / rerun_xml.name))
        merged = self._run_robot(
            rebot_cmd + merge_inputs, repo_root, "Merging Robot outputs (rebot)"
        )
        if merged.returncode > MAX_FAILED_EXIT_CODE:
            self._log_output_tails(merged)
            raise RuntimeError(
                f"rebot could not merge E2E outputs (exit code {merged.returncode})."
            )

        tests = classify_results(first_results, rerun_results)
        counts = summarize(tests)
        summary = {
            "suite": str(suite_path),
            "org": org_name,
            "rerun_attempted": first.returncode != 0,
            "counts": counts,
            "tests": tests,
        }
        (out_path / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )

        for test in tests:
            if test["result"] == "flaky":
                self.logger.warning(
                    "FLAKY (failed, then passed on rerun): %s", test["name"]
                )
        if counts["fail"]:
            raise RuntimeError(
                f"E2E tests failed after one rerun: {counts['fail']} failed, "
                f"{counts['flaky']} flaky, {counts['pass']} passed. "
                f"Check {out_path / 'log.html'} for details."
            )
        if counts["flaky"]:
            self.logger.warning(
                "E2E tests passed only after a rerun: %d flaky (not a clean pass). "
                "See %s.",
                counts["flaky"],
                out_path / SUMMARY_FILENAME,
            )
        else:
            self.logger.info("E2E tests passed successfully.")
