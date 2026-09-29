#!/usr/bin/env python3
"""
Offline invariants for tasks/rlm_robot_e2e.RunE2ETests (TP-08).

    python tests/test_rlm_robot_e2e.py

No org, no browser and no CumulusCI install required. Two layers:

1. Contract checks with `subprocess.run` replaced by a fake that writes Robot
   `output.xml` files -- they assert the argv of the first run, the single
   `--rerunfailed` pass, the `rebot --merge` call, and the pass / flaky / fail
   classification written to `e2e-summary.json`.
2. One integration check that runs REAL Robot (BuiltIn + OperatingSystem only, no
   browser) on a two-attempt fixture suite. It is skipped, and says so, when the
   interpreter has no Robot Framework; the CI nightly image has it.

Why this file exists
--------------------
The nightly org job (docs/references/test-plan-2026-09.md section 4.8) needs exactly
one automatic rerun of failed Robot tests and a report that never presents a
pass-after-rerun as green (section 7.3). Whether a test was flaky is decided here,
from two output files, so a bug in this logic would silently launder real failures
into "flaky" or flaky tests into "pass". The checks assert on the classification,
not on the task's exit code.
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tasks import rlm_robot_e2e as e2e  # noqa: E402

RESULTS = []
SKIPPED = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def robot_xml(tests):
    """A minimal Robot 7 output.xml: `tests` is {suite-name: [(test, status), ...]}."""
    suites = []
    for suite, cases in tests.items():
        body = "".join(
            f'<test id="s1-t{i}" name="{name}"><status status="{status}"/></test>'
            for i, (name, status) in enumerate(cases, 1)
        )
        suites.append(f'<suite id="s1" name="{suite}">{body}<status status="PASS"/></suite>')
    return '<?xml version="1.0"?><robot><suite name="E2E">' + "".join(suites) + "</suite></robot>"


def make_task(out_dir, options=None, custom=None):
    task = e2e.RunE2ETests.__new__(e2e.RunE2ETests)
    task.options = dict(options or {})
    task.org_config = types.SimpleNamespace(username="test@example.com.scratch")
    task.project_config = types.SimpleNamespace(
        repo_root=str(REPO_ROOT), project__custom=custom or {}
    )
    task.logger = types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    task.options.setdefault("outputdir", str(out_dir))
    return task


class FakeRobot:
    """Stands in for subprocess.run; scripted per invocation kind."""

    def __init__(self, first, rerun=None, first_rc=None, rerun_rc=None):
        self.first, self.rerun = first, rerun
        self.first_rc, self.rerun_rc = first_rc, rerun_rc
        self.calls = []

    @staticmethod
    def _arg(cmd, flag):
        return cmd[cmd.index(flag) + 1]

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        completed = types.SimpleNamespace(stdout="", stderr="", returncode=0)
        outdir = Path(self._arg(cmd, "--outputdir"))
        outdir.mkdir(parents=True, exist_ok=True)
        if "robot.rebot" in cmd:
            (outdir / self._arg(cmd, "--output")).write_text("<robot/>", encoding="utf-8")
            (outdir / "log.html").write_text("log", encoding="utf-8")
            return completed
        if "--rerunfailed" in cmd:
            (outdir / self._arg(cmd, "--output")).write_text(
                robot_xml(self.rerun), encoding="utf-8"
            )
            completed.returncode = (
                self.rerun_rc
                if self.rerun_rc is not None
                else sum(s == "FAIL" for c in self.rerun.values() for _, s in c)
            )
            return completed
        (outdir / self._arg(cmd, "--output")).write_text(
            robot_xml(self.first), encoding="utf-8"
        )
        failed = sum(s == "FAIL" for cases in self.first.values() for _, s in cases)
        completed.returncode = self.first_rc if self.first_rc is not None else failed
        return completed


def run_task(fake, options=None):
    """Run the task under the fake; return (summary dict | None, error | None, out_dir)."""
    with tempfile.TemporaryDirectory() as tmp:
        task = make_task(tmp, options={"rerun_failed": "true", **(options or {})})
        saved = (e2e.subprocess.run, e2e.check_urllib3_for_robot)
        e2e.subprocess.run = fake
        e2e.check_urllib3_for_robot = lambda **kw: None
        error = None
        try:
            task._run_task()
        except RuntimeError as exc:
            error = str(exc)
        finally:
            e2e.subprocess.run, e2e.check_urllib3_for_robot = saved
        summaries = list(Path(tmp).rglob(e2e.SUMMARY_FILENAME))
        summary = json.loads(summaries[0].read_text(encoding="utf-8")) if summaries else None
        return summary, error


def by_result(summary):
    return {t["name"]: t["result"] for t in summary["tests"]}


# ---- pure helpers -----------------------------------------------------------------


def check_parse_uses_dotted_suite_path_and_keeps_duplicates_apart(_):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "output.xml"
        path.write_text(
            robot_xml({"A": [("Same Name", "PASS")], "B": [("Same Name", "FAIL")]}),
            encoding="utf-8",
        )
        got = e2e.parse_robot_results(path)
    check(
        "parse_keeps_same_named_tests_in_different_suites_apart",
        got == {"E2E.A.Same Name": "PASS", "E2E.B.Same Name": "FAIL"},
        str(got),
    )


def check_classification_matrix(_):
    first = {"a": "PASS", "b": "FAIL", "c": "FAIL", "d": "SKIP", "e": "FAIL"}
    rerun = {"b": "PASS", "c": "FAIL"}  # e failed and never ran again
    got = {t["name"]: t["result"] for t in e2e.classify_results(first, rerun)}
    check(
        "classify_pass_flaky_fail_skip",
        got == {"a": "pass", "b": "flaky", "c": "fail", "d": "skip", "e": "fail"},
        str(got),
    )
    got = {t["name"]: t["result"] for t in e2e.classify_results({"a": "PASS", "b": "FAIL"})}
    check(
        "classify_without_rerun_never_reports_flaky",
        got == {"a": "pass", "b": "fail"},
        str(got),
    )


# ---- contract: argv and reporting ---------------------------------------------------


def check_all_green_runs_once_and_does_not_rerun(_):
    fake = FakeRobot(first={"S": [("t1", "PASS"), ("t2", "PASS")]})
    summary, error = run_task(fake)
    kinds = ["rerun" if "--rerunfailed" in c else "rebot" if "robot.rebot" in c else "robot"
             for c in fake.calls]
    check("green_run_has_no_error", error is None, str(error))
    check(
        "green_run_is_robot_then_rebot_only",
        kinds == ["robot", "rebot"],
        str(kinds),
    )
    check(
        "green_run_has_no_merge_flag",
        not any("--merge" in c for c in fake.calls),
        "",
    )
    check(
        "green_run_counts",
        summary and summary["counts"] == {"pass": 2, "flaky": 0, "fail": 0, "skip": 0}
        and summary["rerun_attempted"] is False,
        str(summary and summary["counts"]),
    )


def check_pass_after_rerun_is_flaky_not_green(_):
    fake = FakeRobot(
        first={"S": [("t1", "PASS"), ("t2", "FAIL")]},
        rerun={"S": [("t2", "PASS")]},
    )
    summary, error = run_task(fake)
    check("flaky_run_does_not_fail_the_task", error is None, str(error))
    check(
        "flaky_run_classifies_the_rerun_pass_as_flaky",
        summary and by_result(summary) == {"E2E.S.t1": "pass", "E2E.S.t2": "flaky"},
        str(summary and by_result(summary)),
    )
    check(
        "flaky_run_counts",
        summary and summary["counts"] == {"pass": 1, "flaky": 1, "fail": 0, "skip": 0},
        str(summary and summary["counts"]),
    )
    rerun = [c for c in fake.calls if "--rerunfailed" in c]
    check("exactly_one_rerun", len(rerun) == 1, f"{len(rerun)} rerun calls")
    first_xml = fake._arg(rerun[0], "--rerunfailed")
    check(
        "rerun_reads_the_first_attempt_output",
        os.path.basename(first_xml) == e2e.FIRST_OUTPUT,
        first_xml,
    )
    rebot = [c for c in fake.calls if "robot.rebot" in c][0]
    check(
        "rebot_merges_first_then_rerun",
        "--merge" in rebot
        and [os.path.basename(a) for a in rebot[-2:]] == [e2e.FIRST_OUTPUT, e2e.RERUN_OUTPUT],
        " ".join(rebot[-4:]),
    )
    check(
        "rerun_uses_its_own_output_directory",
        fake._arg(rerun[0], "--outputdir") != fake._arg(fake.calls[0], "--outputdir"),
        "screenshots of attempt 1 must not be overwritten",
    )


def check_fail_after_rerun_fails_the_task(_):
    fake = FakeRobot(
        first={"S": [("t1", "FAIL"), ("t2", "FAIL")]},
        rerun={"S": [("t1", "PASS"), ("t2", "FAIL")]},
    )
    summary, error = run_task(fake)
    check("still_failing_test_raises", error is not None and "failed after one rerun" in error, str(error))
    check(
        "fail_after_rerun_summary_still_written",
        summary and summary["counts"] == {"pass": 0, "flaky": 1, "fail": 1, "skip": 0},
        str(summary and summary["counts"]),
    )
    check(
        "no_second_rerun",
        sum("--rerunfailed" in c for c in fake.calls) == 1,
        "",
    )


def check_framework_error_is_not_retried(_):
    fake = FakeRobot(first={"S": [("t1", "PASS")]}, first_rc=252)
    summary, error = run_task(fake)
    check(
        "robot_exit_252_is_reported_not_rerun",
        error is not None and "did not complete" in error
        and not any("--rerunfailed" in c for c in fake.calls),
        str(error),
    )


def check_rerun_filters_match_first_run(_):
    fake = FakeRobot(
        first={"S": [("t1", "FAIL")]}, rerun={"S": [("t1", "PASS")]}
    )
    run_task(fake, options={"exclude_tags": "flaky", "include_tags": "e2e"})
    rerun = [c for c in fake.calls if "--rerunfailed" in c][0]
    check(
        "rerun_keeps_include_and_exclude_tags",
        "--include" in rerun and "e2e" in rerun and "--exclude" in rerun and "flaky" in rerun,
        " ".join(rerun),
    )
    check(
        "headless_by_default",
        not any("HEADED:true" in a for c in fake.calls for a in c),
        "",
    )


def check_default_mode_is_unchanged(_):
    """Without rerun_failed there is one plain robot call and no summary / rebot."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        Path(cmd[cmd.index("--outputdir") + 1]).mkdir(parents=True, exist_ok=True)
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    with tempfile.TemporaryDirectory() as tmp:
        task = make_task(tmp)
        saved = (e2e.subprocess.run, e2e.check_urllib3_for_robot)
        e2e.subprocess.run = fake_run
        e2e.check_urllib3_for_robot = lambda **kw: None
        try:
            task._run_task()
        finally:
            e2e.subprocess.run, e2e.check_urllib3_for_robot = saved
    check(
        "default_mode_is_one_plain_robot_call",
        len(calls) == 1
        and "--output" not in calls[0]
        and "--rerunfailed" not in calls[0]
        and "robot.rebot" not in calls[0],
        str(calls),
    )


# ---- quarantine register (robot/QUARANTINE.md) ------------------------------------------

QUARANTINE_TAG = "flaky"
ROOT_CAUSES = {"timing", "data-dependency", "environment", "product-bug"}
MAX_QUARANTINE_DAYS = 14


def _split_cells(line):
    return [c for c in re.split(r"\s{2,}|\t", line.strip()) if c]


def flaky_tests_in(text, rel_path):
    """`{path::Test Name}` for every test case tagged `flaky`; file-level tags are errors."""
    tagged, file_level = set(), False
    in_tests, current = False, None
    for line in text.splitlines():
        if line.startswith("***"):
            in_tests = "test case" in line.lower()
            current = None
            continue
        cells = _split_cells(line)
        if not cells:
            continue
        head = cells[0].lower().replace(" ", "")
        if head in ("testtags", "forcetags", "defaulttags") and not line[0].isspace():
            file_level |= QUARANTINE_TAG in [c.lower() for c in cells[1:]]
        if in_tests and not line[0].isspace() and not line.lstrip().startswith("#"):
            current = cells[0]
        elif in_tests and current and head == "[tags]":
            if QUARANTINE_TAG in [c.lower() for c in cells[1:]]:
                tagged.add(f"{rel_path}::{current}")
    return tagged, file_level


def parse_quarantine(text):
    """Rows of the register table as lists of cells (header and separator skipped)."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == "Test" or (cells[0] and set(cells[0]) <= {"-", " "}):
            continue
        rows.append(cells)
    return rows


def quarantine_problems(rows, tagged, today=None):
    problems = []
    listed = set()
    for cells in rows:
        if len(cells) != 7 or not all(cells):
            problems.append(f"row needs 7 non-empty cells: {cells}")
            continue
        test, owner, issue, cause, added, expires, evidence = cells
        listed.add(test)
        if cause not in ROOT_CAUSES:
            problems.append(f"{test}: root cause {cause!r} not in {sorted(ROOT_CAUSES)}")
        if cause == "product-bug":
            problems.append(f"{test}: a product-bug is filed and kept blocking, not quarantined")
        if not re.match(r"^(https://\S+|#\d+)$", issue):
            problems.append(f"{test}: issue must be a URL or #N, got {issue!r}")
        try:
            added_d, expires_d = date.fromisoformat(added), date.fromisoformat(expires)
        except ValueError:
            problems.append(f"{test}: added/expires must be ISO dates")
            continue
        if not 0 < (expires_d - added_d).days <= MAX_QUARANTINE_DAYS:
            problems.append(f"{test}: expires must be 1..{MAX_QUARANTINE_DAYS} days after added")
    for test in sorted(tagged - listed):
        problems.append(f"{test}: tagged {QUARANTINE_TAG!r} but has no row in robot/QUARANTINE.md")
    for test in sorted(listed - tagged):
        problems.append(f"{test}: has a row but is not tagged {QUARANTINE_TAG!r}")
    return problems


def check_quarantine_register_matches_flaky_tags(_):
    tagged, file_level = set(), []
    for path in sorted((REPO_ROOT / "robot").rglob("*.robot")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        t, fl = flaky_tests_in(path.read_text(encoding="utf-8"), rel)
        tagged |= t
        if fl:
            file_level.append(rel)
    register = (REPO_ROOT / "robot" / "QUARANTINE.md").read_text(encoding="utf-8")
    problems = quarantine_problems(parse_quarantine(register), tagged)
    problems += [f"{f}: tag `{QUARANTINE_TAG}` per test, not file-wide" for f in file_level]
    check("quarantine_register_matches_flaky_tags", not problems, "; ".join(problems))


def check_quarantine_validator_catches_bad_rows(_):
    good = (
        "| Test | Owner | Issue | Root cause | Added | Expires | Evidence |\n"
        "|---|---|---|---|---|---|---|\n"
        "| robot/a.robot::T | @dev | #12 | timing | 2026-09-01 | 2026-09-10 | log |\n"
    )
    tagged = {"robot/a.robot::T"}
    check(
        "validator_accepts_a_complete_row",
        quarantine_problems(parse_quarantine(good), tagged) == [],
        str(quarantine_problems(parse_quarantine(good), tagged)),
    )
    too_long = good.replace("2026-09-10", "2026-09-30")
    check(
        "validator_rejects_expiry_over_14_days",
        any("days after added" in p for p in quarantine_problems(parse_quarantine(too_long), tagged)),
        "",
    )
    check(
        "validator_flags_tag_without_row_and_row_without_tag",
        len(quarantine_problems(parse_quarantine(good), {"robot/b.robot::U"})) == 2,
        "",
    )
    text = "*** Test Cases ***\nA\n    [Tags]    e2e    Flaky\n    Log    x\nB\n    [Tags]    e2e\n    Log    y\n"
    check(
        "tag_scan_finds_only_the_flaky_test",
        flaky_tests_in(text, "p.robot") == ({"p.robot::A"}, False),
        str(flaky_tests_in(text, "p.robot")),
    )


# ---- integration with real Robot ------------------------------------------------------

FIXTURE = """\
*** Settings ***
Library    OperatingSystem

*** Variables ***
${ORG_ALIAS}    ${EMPTY}

*** Test Cases ***
Always Passes
    Log    ok

Flaky Once
    ${seen}=    Run Keyword And Return Status    File Should Exist    %{RLM_E2E_TEST_MARKER}
    Create File    %{RLM_E2E_TEST_MARKER}    seen
    Run Keyword If    not ${seen}    Fail    first attempt fails on purpose

Always Fails
    Fail    never passes
"""


def check_real_robot_rerun_and_merge(_):
    real = importlib.util.find_spec("robot.rebot") is not None
    if not real:
        SKIPPED.append("real_robot_rerun_and_merge (Robot Framework not installed)")
        return
    with tempfile.TemporaryDirectory() as tmp:
        suite = Path(tmp) / "fixture.robot"
        suite.write_text(FIXTURE, encoding="utf-8")
        marker = Path(tmp) / "marker"
        rel_suite = os.path.relpath(suite, REPO_ROOT) if os.name != "nt" else str(suite)
        task = make_task(Path(tmp) / "out", options={"rerun_failed": "true", "suite": str(suite)})
        saved = e2e.check_urllib3_for_robot
        e2e.check_urllib3_for_robot = lambda **kw: None
        os.environ["RLM_E2E_TEST_MARKER"] = str(marker)
        error = None
        try:
            task._run_task()
        except RuntimeError as exc:
            error = str(exc)
        finally:
            e2e.check_urllib3_for_robot = saved
            os.environ.pop("RLM_E2E_TEST_MARKER", None)
        out_dirs = list((Path(tmp) / "out").glob("e2e_*"))
        summary_path = out_dirs[0] / e2e.SUMMARY_FILENAME if out_dirs else None
        summary = (
            json.loads(summary_path.read_text(encoding="utf-8"))
            if summary_path and summary_path.exists()
            else None
        )
        merged = out_dirs[0] / e2e.MERGED_OUTPUT if out_dirs else None
        merged_status = (
            e2e.parse_robot_results(merged) if merged and merged.exists() else {}
        )
        has_reports = bool(out_dirs) and (out_dirs[0] / "log.html").exists() and (
            out_dirs[0] / "report.html"
        ).exists()
    got = by_result(summary) if summary else {}
    check(
        "real_robot_classifies_pass_flaky_fail",
        {k.split(".")[-1]: v for k, v in got.items()}
        == {"Always Passes": "pass", "Flaky Once": "flaky", "Always Fails": "fail"},
        str(got),
    )
    check(
        "real_robot_task_fails_because_one_test_still_fails",
        error is not None and "1 failed, 1 flaky, 1 passed" in error,
        str(error),
    )
    check(
        "real_robot_merged_output_takes_the_rerun_result",
        {k.split(".")[-1]: v for k, v in merged_status.items()}
        == {"Always Passes": "PASS", "Flaky Once": "PASS", "Always Fails": "FAIL"},
        str(merged_status),
    )
    check("real_robot_writes_merged_log_and_report", has_reports, "")


def main():
    checks = [
        check_parse_uses_dotted_suite_path_and_keeps_duplicates_apart,
        check_classification_matrix,
        check_all_green_runs_once_and_does_not_rerun,
        check_pass_after_rerun_is_flaky_not_green,
        check_fail_after_rerun_fails_the_task,
        check_framework_error_is_not_retried,
        check_rerun_filters_match_first_run,
        check_default_mode_is_unchanged,
        check_quarantine_register_matches_flaky_tags,
        check_quarantine_validator_catches_bad_rows,
        check_real_robot_rerun_and_merge,
    ]
    for fn in checks:
        try:
            fn(None)
        except Exception as exc:  # a check that blows up is a failure, not a crash
            check(
                fn.__name__.replace("check_", ""),
                False,
                f"check raised {type(exc).__name__}: {exc}",
            )

    width = max(len(n) for n, _, _ in RESULTS)
    failed = 0
    print("rlm_robot_e2e task invariants\n" + "=" * (width + 60))
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail if not ok else ''}")
        failed += 0 if ok else 1
    for skipped in SKIPPED:
        print(f"  SKIP  {skipped}")
    print("=" * (width + 60))
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed, {len(SKIPPED)} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
