#!/usr/bin/env python3
"""Unit tests for scripts/lint/coverage_ratchet.py (TP-10).

Self-contained -- no pytest and no coverage.py required (matches this repo's lightweight test
convention). Run from the repo root with base Python:

    python tests/test_coverage_ratchet.py

The ratchet is exercised end to end through `main()` against hand-built `coverage json`
reports and, for `--base-ref`, a throwaway git repository. Exits 0 when all checks pass, 1
otherwise.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lint"))

import coverage_ratchet as R  # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + ("" if condition or detail == "" else f": {detail}"))


def file_entry(lines, covered, branches=0, covered_branches=0):
    return {"summary": {"num_statements": lines, "covered_lines": covered,
                        "num_branches": branches, "covered_branches": covered_branches}}


def report(files):
    return {"files": files}


def floor_doc(**floors):
    return {"version": 1, "packages": {name: {"floor": floor, "target": 90.0}
                                        for name, floor in floors.items()}}


def write_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh)


def run_main(argv):
    """(exit code, stdout, stderr) of main(argv) with the streams captured."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = R.main(argv)
    return code, out.getvalue(), err.getvalue()


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8")


def test_measure():
    check("round_down truncates instead of rounding to nearest", R.round_down(84.99) == 84.9)
    check("round_down keeps an exact one-decimal value", R.round_down(85.0) == 85.0)
    check("round_down survives float noise (0.1 * 3)", R.round_down(30.000000000000004 - 0.0) == 30.0)

    rep = report({
        "scripts/ai/a.py": file_entry(10, 10, 2, 2),    # 12/12
        "scripts/ai/b.py": file_entry(90, 0, 0, 0),     # 0/90
        "scripts\\ai\\c.py": file_entry(0, 0, 0, 0),    # backslash path, empty file
        "tasks/x.py": file_entry(4, 1, 4, 1),           # 2/8
        "scripts/aix/z.py": file_entry(100, 100, 0, 0),  # prefix must not match scripts/ai
    })
    percent, count = R.package_percent(rep, "scripts/ai")
    check("percent is summed over files, not averaged per file (12 of 102)",
          abs(percent - 100.0 * 12 / 102) < 1e-9, percent)
    check("a Windows-style separator still counts toward its package", count == 3, count)
    check("a directory prefix does not match a sibling that merely starts with it",
          R.package_percent(rep, "tasks")[1] == 1)
    check("branches are part of the figure (2 of 8 = 25%)",
          abs(R.package_percent(rep, "tasks")[0] - 25.0) < 1e-9)

    low = report({"scripts/ai/dead.py": file_entry(5, 0, 2, 0),        # 0%
                  "scripts/ai/thin.py": file_entry(8, 1, 2, 0),        # 1/10 = 10%
                  "scripts/ai/edge.py": file_entry(8, 2, 2, 0),        # 2/10 = 20%, not under
                  "scripts/ai/live.py": file_entry(5, 5, 0, 0),
                  "scripts/ai/empty.py": file_entry(0, 0, 0, 0),
                  "tasks/dead2.py": file_entry(3, 0, 0, 0)})
    got = R.low_coverage_files(low, "scripts/ai")
    check("files under 20% are called out per package, lowest first, 20% itself excluded",
          got == [("scripts/ai/dead.py", 0.0), ("scripts/ai/thin.py", 10.0)], got)
    check("an empty file is not a gap", all("empty" not in path for path, _ in got))

    for label, bad, message in [
        ("a package with no measured files", report({"tasks/x.py": file_entry(1, 1, 0, 0)}), "no measured files"),
        ("a report without branch data", report({"scripts/ai/a.py": {"summary": {
            "num_statements": 1, "covered_lines": 1}}}), "branch"),
        ("a document that is not a coverage report", {"nope": 1}, "'files'"),
    ]:
        try:
            R.package_percent(bad, "scripts/ai")
            check(f"{label} is a tool error", False, "no exception")
        except R.ToolError as exc:
            check(f"{label} is a tool error", message in str(exc), str(exc))


def test_floor_validation():
    for label, doc in [("an empty packages object", {"packages": {}}),
                       ("a missing packages key", {}),
                       ("a non-numeric floor", {"packages": {"a": {"floor": "80"}}}),
                       ("a boolean floor", {"packages": {"a": {"floor": True}}}),
                       ("a floor above 100", {"packages": {"a": {"floor": 101}}}),
                       ("a negative floor", {"packages": {"a": {"floor": -1}}})]:
        try:
            R.validate_floor_doc(doc, "fixture")
            check(f"{label} is rejected", False, "no exception")
        except R.ToolError:
            check(f"{label} is rejected", True)
    check("a 0 floor is valid (the initial state of an unmeasured package)",
          R.validate_floor_doc({"packages": {"a": {"floor": 0}}}, "fixture") == {"a": {"floor": 0}})


def test_committed_floor_file():
    """The real coverage-floor.json must be well-formed and hold the plan's two packages."""
    doc = json.loads((REPO_ROOT / "coverage-floor.json").read_text(encoding="utf-8"))
    packages = R.validate_floor_doc(doc, "coverage-floor.json")
    check("coverage-floor.json names scripts/ai and tasks", sorted(packages) == ["scripts/ai", "tasks"],
          sorted(packages))
    check("the plan's targets are recorded (scripts/ai 85, tasks 60)",
          packages["scripts/ai"].get("target") == 85.0 and packages["tasks"].get("target") == 60.0)
    check("no floor exceeds its target", all(p["floor"] <= p.get("target", 100) for p in packages.values()))
    check("the file carries a `reason` field (where a lowering must be justified)",
          isinstance(doc.get("reason"), str))


def test_check_and_update():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        rep_path, floor_path = td / "cov.json", td / "floor.json"
        # scripts/ai 90/100 = 90.0 ; tasks 3/8 = 37.5
        write_json(rep_path, report({"scripts/ai/a.py": file_entry(80, 72, 20, 18),
                                     "tasks/x.py": file_entry(4, 2, 4, 1)}))

        def argv(cmd, *extra):
            return [cmd, "--report", str(rep_path), "--floor", str(floor_path), *extra]

        write_json(floor_path, floor_doc(**{"scripts/ai": 90.0, "tasks": 37.5}))
        code, out, _ = run_main(argv("check", "--summary", str(td / "sum.md")))
        check("measured == floor passes", code == 0, out)
        summary = (td / "sum.md").read_text(encoding="utf-8")
        check("the summary carries a table row and a badge per package",
              "| `scripts/ai` |" in summary and "img.shields.io" in summary and "| `tasks` |" in summary)
        check("a package with no file under 20% has no call-out block", "covered</summary>" not in summary)

        write_json(rep_path, report({"scripts/ai/a.py": file_entry(80, 72, 20, 18),
                                     "scripts/ai/dead.py": file_entry(0, 0, 0, 0),
                                     "tasks/x.py": file_entry(4, 2, 4, 1),
                                     "tasks/never.py": file_entry(1, 0, 0, 0)}))
        write_json(floor_path, floor_doc(**{"scripts/ai": 1.0, "tasks": 1.0}))
        code, out, _ = run_main(argv("check", "--summary", str(td / "sum2.md")))
        check("an under-20% file is named on stdout and in the summary block",
              code == 0 and "tasks/never.py" in out
              and "1 file(s) in <code>tasks</code> under 20% covered" in (td / "sum2.md").read_text(encoding="utf-8"),
              out)
        write_json(rep_path, report({"scripts/ai/a.py": file_entry(80, 72, 20, 18),
                                     "tasks/x.py": file_entry(4, 2, 4, 1)}))

        write_json(floor_path, floor_doc(**{"scripts/ai": 90.1, "tasks": 37.5}))
        code, _, err = run_main(argv("check"))
        check("measured below floor fails with exit 1 and names the package",
              code == 1 and "scripts/ai" in err, (code, err))

        write_json(floor_path, floor_doc(**{"scripts/ai": 80.0, "tasks": 30.0}))
        before = floor_path.read_text(encoding="utf-8")
        code, out, _ = run_main(argv("check"))
        check("coverage above the floor passes and only suggests raising it",
              code == 0 and "floor can be raised" in out, (code, out))
        check("check never rewrites the floor file", floor_path.read_text(encoding="utf-8") == before)

        code, out, _ = run_main(argv("update"))
        after = json.loads(floor_path.read_text(encoding="utf-8"))["packages"]
        check("update raises each floor to the measured value rounded down",
              code == 0 and after["scripts/ai"]["floor"] == 90.0 and after["tasks"]["floor"] == 37.5, after)
        check("update leaves target alone", after["scripts/ai"]["target"] == 90.0)

        write_json(floor_path, floor_doc(**{"scripts/ai": 95.0, "tasks": 37.5}))
        run_main(argv("update"))
        check("update never lowers a floor",
              json.loads(floor_path.read_text(encoding="utf-8"))["packages"]["scripts/ai"]["floor"] == 95.0)

        write_json(rep_path, report({"tasks/x.py": file_entry(4, 2, 4, 1)}))
        code, _, err = run_main(argv("check"))
        check("a package the run did not measure is exit 2, not a pass and not a floor breach",
              code == 2 and "no measured files" in err, (code, err))

        (td / "bad.json").write_text("{", encoding="utf-8")
        code, _, _ = run_main(["check", "--report", str(td / "bad.json"), "--floor", str(floor_path)])
        check("an unreadable report is exit 2", code == 2)
        code, _, _ = run_main(["check", "--report", str(rep_path), "--floor", str(td / "missing.json")])
        check("a missing floor file is exit 2", code == 2)


def test_base_ref_no_lowering():
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "t@example.com")
        git(repo, "config", "user.name", "t")
        git(repo, "config", "commit.gpgsign", "false")
        (repo / "seed.txt").write_text("x", encoding="utf-8")
        git(repo, "add", "seed.txt")
        git(repo, "commit", "-q", "-m", "seed")
        floor_path = repo / "coverage-floor.json"
        rep_path = repo / "cov.json"
        write_json(rep_path, report({"scripts/ai/a.py": file_entry(10, 10, 0, 0),
                                     "tasks/x.py": file_entry(10, 5, 0, 0)}))

        original_root = R.REPO_ROOT
        R.REPO_ROOT = repo
        try:
            def run(*extra):
                return run_main(["check", "--report", str(rep_path), "--floor", str(floor_path), *extra])

            write_json(floor_path, floor_doc(**{"scripts/ai": 90.0, "tasks": 40.0}))
            code, out, _ = run("--base-ref", "main")
            check("a base ref with no floor file yet is not a failure (the PR that introduces it)",
                  code == 0 and "no floor file yet" in out, (code, out))

            git(repo, "add", "coverage-floor.json")
            git(repo, "commit", "-q", "-m", "floors")

            code, _, _ = run("--base-ref", "main")
            check("floors equal to the base pass", code == 0)

            write_json(floor_path, floor_doc(**{"scripts/ai": 90.0, "tasks": 30.0}))
            code, _, err = run("--base-ref", "main")
            check("a PR that lowers one floor fails even though coverage still clears it",
                  code == 1 and "tasks: floor lowered 40.0 -> 30.0" in err, (code, err))

            write_json(floor_path, floor_doc(**{"scripts/ai": 90.0}))
            code, _, err = run("--base-ref", "main")
            check("a PR that drops a package from the file fails",
                  code == 1 and "dropped" in err, (code, err))

            write_json(floor_path, floor_doc(**{"scripts/ai": 100.0, "tasks": 50.0}))
            code, _, _ = run("--base-ref", "main")
            check("raising floors passes the no-lowering rule", code == 0)

            lowered = floor_doc(**{"scripts/ai": 90.0, "tasks": 30.0})
            lowered["reason"] = "coverage-floor-lowered: tasks/rlm_x.py was split into two modules"
            write_json(floor_path, lowered)
            code, out, _ = run("--base-ref", "main")
            check("a lowering with a new 'coverage-floor-lowered: <reason>' line is accepted and echoed",
                  code == 0 and "split into two modules" in out, (code, out))

            lowered["reason"] = "coverage-floor-lowered:   "
            write_json(floor_path, lowered)
            code, _, _ = run("--base-ref", "main")
            check("a marker with no reason text does not license a lowering", code == 1)

            lowered["reason"] = "the tasks floor is too high"
            write_json(floor_path, lowered)
            code, _, err = run("--base-ref", "main")
            check("a reason without the marker does not license a lowering, and the failure says how to fix it",
                  code == 1 and "coverage-floor-lowered:" in err, (code, err))

            # A marker line the base already carries must not license the *next* lowering.
            with_marker = floor_doc(**{"scripts/ai": 90.0, "tasks": 40.0})
            with_marker["reason"] = "coverage-floor-lowered: an old, already-merged justification"
            write_json(floor_path, with_marker)
            git(repo, "add", "coverage-floor.json")
            git(repo, "commit", "-q", "-m", "floors with a reason")
            again = floor_doc(**{"scripts/ai": 90.0, "tasks": 35.0})
            again["reason"] = with_marker["reason"]
            write_json(floor_path, again)
            code, _, _ = run("--base-ref", "main")
            check("a reason line the base already has does not license another lowering", code == 1)

            code, _, err = run("--base-ref", "no-such-ref")
            check("an unresolvable base ref is exit 2, not a free pass",
                  code == 2 and "does not resolve" in err, (code, err))
        finally:
            R.REPO_ROOT = original_root


STUB = r"""
import json, os, sys
args = sys.argv[1:]
mode = os.environ["STUB_MODE"]
if args[:1] == ["--version"]:
    sys.exit(1 if mode == "no-coverage" else 0)
if args[:1] == ["run"]:
    print("[PASS       ] agent_tooling   1.0s")
    if mode == "missing-dep":
        print("[MISSING-DEP] harness_suites       missing: textual")
    sys.exit(1 if mode == "gate-red" else 0)
if args[:1] == ["json"]:
    out = args[args.index("-o") + 1]
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"files": {}}, fh)
sys.exit(0)
"""


def test_measure_command():
    """`measure` against a stub in place of coverage.py: the exit-code contract, not coverage itself."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        stub = td / "fake_coverage.py"
        stub.write_text(STUB, encoding="utf-8")
        target = td / "out" / "cov.json"
        original = R.coverage_cmd
        R.coverage_cmd = lambda *a: [sys.executable, str(stub), *a]
        previous = os.environ.get("STUB_MODE")
        try:
            def run(mode):
                os.environ["STUB_MODE"] = mode
                return run_main(["measure", "--json", str(target)])

            code, out, _ = run("ok")
            check("measure passes when the gate passes and writes the report (creating its directory)",
                  code == 0 and target.exists() and "gate exit 0" in out, (code, out))
            code, out, _ = run("gate-red")
            check("a red gate is exit 1 (a lower bound is not a clean measurement) but still writes the report",
                  code == 1 and target.exists(), (code, out))
            target.unlink()
            code, out, err = run("missing-dep")
            check("a MISSING-DEP check is exit 2 'incomplete measurement', never a coverage verdict, "
                  "and names the check",
                  code == 2 and "incomplete measurement" in err and "harness_suites" in err, (code, err))
            code, _, err = run("no-coverage")
            check("coverage.py not installed is exit 2 with an install hint",
                  code == 2 and "pip install" in err, (code, err))
        finally:
            R.coverage_cmd = original
            if previous is None:
                os.environ.pop("STUB_MODE", None)
            else:
                os.environ["STUB_MODE"] = previous


def test_summary_env_default():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        write_json(td / "cov.json", report({"scripts/ai/a.py": file_entry(10, 10, 0, 0)}))
        write_json(td / "floor.json", floor_doc(**{"scripts/ai": 50.0}))
        summary = td / "step-summary.md"
        previous = os.environ.get("GITHUB_STEP_SUMMARY")
        os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
        try:
            code, _, _ = run_main(["check", "--report", str(td / "cov.json"), "--floor", str(td / "floor.json")])
        finally:
            if previous is None:
                del os.environ["GITHUB_STEP_SUMMARY"]
            else:
                os.environ["GITHUB_STEP_SUMMARY"] = previous
        check("--summary defaults to $GITHUB_STEP_SUMMARY",
              code == 0 and summary.exists() and "Python coverage ratchet" in summary.read_text(encoding="utf-8"))


def main():
    test_measure()
    test_floor_validation()
    test_committed_floor_file()
    test_check_and_update()
    test_base_ref_no_lowering()
    test_measure_command()
    test_summary_env_default()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
