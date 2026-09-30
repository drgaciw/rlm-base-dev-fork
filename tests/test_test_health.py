#!/usr/bin/env python3
"""Unit tests for scripts/ai/test_health.py (TP-12).

Self-contained, stdlib only, no pytest required (this repo's lightweight test convention), so it
also runs in the Windows stdlib tier. Run from the repo root with base Python:

    python tests/test_test_health.py

Exits 0 when all checks pass, 1 otherwise.
"""
import contextlib
import io
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai"))

import test_health as H  # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
    if detail and not condition:
        print(f"         {detail}")
    if "pytest" in sys.modules:
        assert condition, f"{name} {detail}"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def cli_split(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = H.main([str(a) for a in argv])
    return rc, out.getvalue(), err.getvalue()


def cli(*argv):
    """(exit code, stdout + stderr): most checks do not care which stream a line is on."""
    rc, out, err = cli_split(*argv)
    return rc, out + err


def raises_health(func, *args):
    try:
        func(*args)
    except H.HealthError as exc:
        return exc.problems
    return None


HEADER = "| Test | Owner | Issue | Root cause | Added | Expires | Evidence |\n|---|---|---|---|---|---|---|\n"


def register(*rows):
    return "# Robot quarantine\n\n## Active quarantine\n\n" + HEADER + "".join(r + "\n" for r in rows)


ROBOT_ROW = ("| robot/rlm-base/tests/e2e/quote_to_order.robot::Quote To Order | @qa | #7 | timing | "
             "2026-09-20 | 2026-10-02 | https://example.test/log |")


def entry(**over):
    row = {"test": "tests/test_x.py::test_a", "layer": "python", "owner": "@dev", "issue": "#1",
           "root_cause": "timing", "added": "2026-09-20", "expires": "2026-10-01", "evidence": "run 9"}
    row.update(over)
    return row


def registry(*entries):
    return json.dumps({"entries": list(entries)})


# ---- the committed sources ---------------------------------------------------------------


def test_committed_sources_are_valid():
    problems = raises_health(H.load_quarantine)
    check("the committed robot/QUARANTINE.md and tests/quarantine/registry.json load and validate",
          problems is None)
    check("the committed registry is the valid empty registry",
          H.parse_json_registry((REPO_ROOT / "tests/quarantine/registry.json").read_text(encoding="utf-8")) == [])
    check("the committed Robot register still has a table the parser recognises",
          isinstance(H.parse_robot_register((REPO_ROOT / "robot/QUARANTINE.md").read_text(encoding="utf-8")), list))


# ---- Robot markdown register -------------------------------------------------------------


def test_robot_register():
    rows = H.parse_robot_register(register(ROBOT_ROW))
    check("a Robot row becomes one Entry with layer robot and parsed dates",
          len(rows) == 1 and rows[0].layer == "robot" and rows[0].added == date(2026, 9, 20)
          and rows[0].expires == date(2026, 10, 2) and rows[0].test.endswith("::Quote To Order")
          and rows[0].root_cause == "timing")
    check("a header with no rows is a valid empty register", H.parse_robot_register(register()) == [])
    check("the register with only the 'No quarantined tests' placeholder line and a header is empty",
          H.parse_robot_register(register() + "\n_No quarantined tests._\n") == [])

    no_header = "# Robot quarantine\n\n_No quarantined tests._\n"
    problems = raises_health(H.parse_robot_register, no_header)
    check("no table header is a parse error, never 'no entries'", problems and "no table" in problems[0])
    renamed = register(ROBOT_ROW).replace("Root cause", "Cause")
    check("a renamed column is a parse error", raises_health(H.parse_robot_register, renamed) is not None)
    reordered = register(ROBOT_ROW).replace("| Owner | Issue |", "| Issue | Owner |")
    check("a reordered column is a parse error", raises_health(H.parse_robot_register, reordered) is not None)
    check("a row with too few cells is an error",
          "cells" in " ".join(raises_health(H.parse_robot_register, register("| a | b | c |")) or []))
    empty_cell = ROBOT_ROW.replace("@qa", " ")
    check("an empty cell (here the owner) is an error",
          "empty cell" in " ".join(raises_health(H.parse_robot_register, register(empty_cell)) or []))
    bad_date = ROBOT_ROW.replace("2026-09-20", "20/09/2026")
    check("a non-ISO date in a Robot row is an error",
          "ISO date" in " ".join(raises_health(H.parse_robot_register, register(bad_date)) or []))
    escaped = ROBOT_ROW.replace("Quote To Order", r"A \| B")
    parsed = H.parse_robot_register(register(escaped))
    check("an escaped pipe stays inside its cell", parsed and parsed[0].test.endswith("::A | B"))


# ---- JSON registry: strict validation ----------------------------------------------------


def test_json_registry():
    check('{"entries": []} is a valid empty registry', H.parse_json_registry('{"entries": []}') == [])
    parsed = H.parse_json_registry(registry(entry()))
    check("a JSON entry becomes one Entry with its layer",
          len(parsed) == 1 and parsed[0].layer == "python" and parsed[0].expires == date(2026, 10, 1))

    def error_of(text):
        return " ".join(raises_health(H.parse_json_registry, text) or ["<no error>"])

    extra = entry()
    extra["severity"] = "high"
    check("an unknown key is an error", "unknown key" in error_of(registry(extra)))
    missing = entry()
    del missing["evidence"]
    check("a missing required key is an error", "missing key" in error_of(registry(missing)))
    check("a non-ISO date is an error", "ISO date" in error_of(registry(entry(added="29/09/2026"))))
    check("a compact ISO 8601 date is not accepted (only YYYY-MM-DD)",
          "ISO date" in error_of(registry(entry(added="20260920"))))
    check("a date that does not exist is an error", "real date" in error_of(registry(entry(expires="2026-02-30"))))
    check("a non-string date is an error", "non-empty string" in error_of(registry(entry(added=20260920))))
    check("an empty value is an error", "non-empty" in error_of(registry(entry(owner=" "))))
    check("layer robot is rejected in the JSON registry", "layer" in error_of(registry(entry(layer="robot"))))
    check("layer must be one of python, apex, lwc, flow", "layer" in error_of(registry(entry(layer="other"))))
    for layer in H.JSON_LAYERS:
        check(f"layer {layer} is accepted", len(H.parse_json_registry(registry(entry(layer=layer)))) == 1)
    check("an unknown top-level key is an error", "exactly one key" in error_of('{"entries": [], "x": 1}'))
    check("a top-level list is an error", "exactly one key" in error_of("[]"))
    check("entries that is not a list is an error", "exactly one key" in error_of('{"entries": {}}'))
    check("invalid JSON is an error, not an empty registry", "not valid JSON" in error_of("{"))
    check("an entry that is not an object is an error", "not an object" in error_of('{"entries": [1]}'))
    both = registry(extra, entry(added="nope", test="tests/other.py::t"))
    check("every problem is reported, not just the first", len(raises_health(H.parse_json_registry, both) or []) >= 2)


# ---- cross-source rules ------------------------------------------------------------------


def load(robot_text, registry_text, tmp):
    return H.load_quarantine(write(tmp / "QUARANTINE.md", robot_text), write(tmp / "registry.json", registry_text))


def test_rules():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        def problems(entries):
            return " ".join(H.rule_problems(entries))

        def json_entries(**over):
            return H.parse_json_registry(registry(entry(**over)))

        check("a 14-day window is accepted", problems(json_entries(added="2026-09-20", expires="2026-10-04")) == "")
        check("a 15-day window is an error, not a warning",
              "1..14 days" in problems(json_entries(added="2026-09-20", expires="2026-10-05")))
        check("expires equal to added is an error", "1..14 days" in problems(json_entries(expires="2026-09-20")))
        check("expires before added is an error", "1..14 days" in problems(json_entries(expires="2026-09-01")))
        check("a product-bug is rejected", "product-bug" in problems(json_entries(root_cause="product-bug")))
        check("an unknown root cause is rejected", "not in" in problems(json_entries(root_cause="cosmic-rays")))
        check("issue must be a URL or #N", "issue must be" in problems(json_entries(issue="see chat")))
        check("an https issue URL is accepted", problems(json_entries(issue="https://github.com/o/r/issues/3")) == "")

        dup_id = "robot/rlm-base/tests/e2e/quote_to_order.robot::Quote To Order"
        errors = raises_health(load, register(ROBOT_ROW), registry(entry(test=dup_id)), tmp)
        check("a duplicate id across the two sources is an error", errors and "duplicate id" in " ".join(errors))
        errors = raises_health(load, register(), registry(entry(), entry()), tmp)
        check("a duplicate id inside the JSON registry is an error", errors and "duplicate id" in " ".join(errors))
        errors = raises_health(load, register(ROBOT_ROW, ROBOT_ROW), registry(), tmp)
        check("a duplicate id inside the Robot register is an error", errors and "duplicate id" in " ".join(errors))

        errors = raises_health(H.load_quarantine, tmp / "missing.md", tmp / "registry.json")
        check("a missing source is an error, never 'no entries'", errors and "cannot read" in " ".join(errors))
        errors = raises_health(load, "no table here", registry(entry(added="bad")), tmp)
        check("problems from both sources are reported together",
              errors and any("no table" in e for e in errors) and any("ISO date" in e for e in errors))


# ---- expiry ------------------------------------------------------------------------------


def test_expiry_and_cli():
    entries = H.parse_json_registry(registry(entry(added="2026-09-20", expires="2026-10-01")))
    check("an entry is still valid on its expires date", H.expired_entries(entries, date(2026, 10, 1)) == [])
    check("an entry is expired the day after its expires date",
          len(H.expired_entries(entries, date(2026, 10, 2))) == 1)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        robot = write(tmp / "QUARANTINE.md", register(ROBOT_ROW))
        reg = write(tmp / "registry.json", registry(entry()))
        args = ["check-quarantine", "--robot", robot, "--registry", reg]
        rc, out = cli(*args, "--today", "2026-09-30")
        check("check-quarantine exits 0 while every entry is inside its window", rc == 0 and "0 expired" in out)
        rc, out = cli(*args, "--today", "2026-10-02")
        check("an expired JSON entry (registry, expires 2026-10-01) fails with exit 1",
              rc == 1 and "::error::quarantine entry expired 2026-10-01" in out and "1 expired" in out)
        rc, out = cli(*args, "--today", "2026-10-03")
        check("an expired entry in EITHER source fails: both are reported on 2026-10-03",
              rc == 1 and "2 expired" in out and "quote_to_order.robot" in out)
        reg_ok = write(tmp / "registry-ok.json", registry())
        rc, out = cli("check-quarantine", "--robot", robot, "--registry", reg_ok, "--today", "2026-10-03")
        check("an expired Robot row alone also fails", rc == 1 and "1 expired" in out)

        rc, out, err = cli_split(*args, "--today", "2026-10-02")
        check("annotations go to stderr and stdout stays clean markdown for the job summary",
              "::error::" in err and "::error::" not in out and out.startswith("## Quarantine check"))
        write(reg, registry(entry(added="soon")))
        rc, out = cli(*args, "--today", "2026-09-30")
        check("a rule break exits 2, not 1 and not 0", rc == 2 and "::error::quarantine:" in out)
        write(robot, "# nothing here\n")
        write(reg, registry())
        rc, out = cli(*args, "--today", "2026-09-30")
        check("an unparseable Robot register exits 2 loudly", rc == 2 and "no table" in out)
        rc, _ = cli("check-quarantine", "--robot", robot, "--registry", reg, "--today", "yesterday")
        check("a bad --today exits 2", rc == 2)


# ---- the merged table --------------------------------------------------------------------


def test_merged_table():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        merged = load(register(ROBOT_ROW),
                      registry(entry(test="tests/test_b.py::late", added="2026-09-22", expires="2026-10-06"),
                               entry(test="tests/test_a.py::early", added="2026-09-19", expires="2026-10-01")),
                      tmp)
    check("both sources merge into one list sorted by expires",
          [e.test.split("::")[-1] for e in merged] == ["early", "Quote To Order", "late"]
          and [e.layer for e in merged] == ["python", "robot", "python"])
    table = H.quarantine_table(merged, date(2026, 10, 2))
    expected = [
        "| Test | Layer | Owner | Issue | Root cause | Added | Expires | Age (d) | Days left | Status |",
        "|---|---|---|---|---|---|---|---|---|---|",
        "| tests/test_a.py::early | python | @dev | #1 | timing | 2026-09-19 | 2026-10-01 | 13 | -1 | **EXPIRED** |",
        "| robot/rlm-base/tests/e2e/quote_to_order.robot::Quote To Order | robot | @qa | #7 | timing | "
        "2026-09-20 | 2026-10-02 | 12 | 0 | expires today |",
        "| tests/test_b.py::late | python | @dev | #1 | timing | 2026-09-22 | 2026-10-06 | 10 | 4 | ok |",
    ]
    check("the merged robot + JSON pair renders the expected combined table", table == expected)
    check("an empty merge renders the placeholder", H.quarantine_table([], date(2026, 10, 2)) == ["_No quarantined tests._"])


# ---- artifact aggregation ----------------------------------------------------------------

JUNIT = """<testsuite name="apex"><testcase classname="A" name="t1"/>{second}</testsuite>"""
ROBOT_XML = ('<robot><suite name="Setup"><suite name="Docs"><test name="Enable"><status status="{s}"/></test>'
             "</suite></suite><statistics/></robot>")


def e2e_summary(**tests):
    return json.dumps({"counts": {}, "tests": [{"name": n, "first": "", "final": "", "result": r}
                                               for n, r in tests.items()]})


def e2e_run_dir(run_id):
    """The real producer's per-invocation directory (tasks/rlm_robot_e2e.py): e2e_%Y%m%d_%H%M%S, which
    differs on every run, so a key built from it would never correlate across runs."""
    n = int(run_id) % 100
    return f"e2e_202609{20 + n:02d}_03{n:02d}00"


def build_run(root, run_id, second, t1, t2, t3=None, verify="PASS"):
    run = root / run_id
    fail = "<failure/>" if second == "fail" else ""
    write(run / f"verify-org-{run_id}" / "test-results" / "apex" / "a.xml", JUNIT.format(second=f'<testcase classname="A" name="t2">{fail}</testcase>'))
    write(run / f"verify-org-{run_id}" / "robot" / "verify" / "docs" / "output.xml", ROBOT_XML.format(s=verify))
    stage = run / f"e2e-org-{run_id}" / "robot" / "e2e" / "2-robot_e2e" / e2e_run_dir(run_id)
    tests = {"Suite.T1": t1, "Suite.T2": t2}
    if t3:
        tests["Suite.T3"] = t3
    write(stage / "e2e-summary.json", e2e_summary(**tests))
    for name in ("first.xml", "output.xml"):  # must not be double counted
        write(stage / name, ROBOT_XML.format(s="FAIL"))
    write(stage / "rerun" / "rerun.xml", ROBOT_XML.format(s="FAIL"))


def test_report():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        art = tmp / "artifacts"
        build_run(art, "101", "fail", "pass", "fail")
        build_run(art, "102", "pass", "flaky", "pass", "fail")
        build_run(art, "103", "pass", "pass", "pass", "fail")
        write(art / "103" / "verify-org-103" / "test-results" / "apex" / "broken.xml", "<testsuite>")
        write(art / "103" / "verify-org-103" / "test-results" / "coverage.xml", "<coverage/>")
        runs = tmp / "runs.json"
        write(runs, json.dumps([
            {"id": 101, "created_at": "2026-09-22T03:00:00Z", "conclusion": "failure", "workflow": "nightly"},
            {"id": 102, "created_at": "2026-09-23T03:00:00Z", "conclusion": "failure", "workflow": "nightly"},
            {"id": 103, "created_at": "2026-09-24T03:00:00Z", "conclusion": "failure", "workflow": "nightly"},
            {"id": 104, "created_at": "2026-09-25T03:00:00Z", "conclusion": "cancelled", "workflow": "nightly"}]))
        robot = write(tmp / "QUARANTINE.md", register(ROBOT_ROW))
        reg = write(tmp / "registry.json", registry())
        rc, out = cli("report", "--artifacts", art, "--runs", runs, "--robot", robot, "--registry", reg,
                      "--today", "2026-09-30")
        check("report exits 0", rc == 0)
        check("4 runs are analysed, 3 with results, dated 2026-09-22 to 2026-09-25",
              "Runs analysed: **4** (3 with test results, 2026-09-22 to 2026-09-25" in out and "1 cancelled" in out)
        check("e2e: first.xml/output.xml/rerun.xml are not double counted; pass, flaky, fail rates are exact",
              "| robot-e2e | 8 | 4 | 1 | 3 | 0 | 50.0% | 12.5% |" in out)
        check("apex JUnit rates are exact", "| apex | 6 | 5 | 0 | 1 | 0 | 83.3% | 0.0% |" in out)
        check("Robot setup (output.xml) is read", "| robot-setup | 3 | 3 | 0 | 0 | 0 | 100.0% | 0.0% |" in out)
        check("the flaky test is listed with its count", "| robot-e2e: e2e-org/2-robot_e2e::Suite.T1 | 1 |" in out
              or "Suite.T1 | 1 |" in out)
        check("MTTR is the mean of the two 1-day recoveries", "Mean time to recovery: **1.0 d**" in out
              and "over 2 recovered" in out)
        check("a test failing since run 102 is listed as still failing with its age",
              "Suite.T3 | 2026-09-23 | 2.0 d |" in out)
        check("an unreadable and a foreign XML file are noted under data quality, not dropped silently",
              "### Data quality" in out and "broken.xml" in out and "neither JUnit nor Robot" in out)
        check("the quarantine section carries the merged table", "quote_to_order.robot::Quote To Order" in out)

        rc, out = cli("report", "--artifacts", tmp / "nothing", "--robot", robot, "--registry", reg,
                      "--today", "2026-09-30")
        check("no artifacts at all is reported as such, exit 0", rc == 0 and "No test results found" in out)
        write(runs, "not json")
        rc, out = cli("report", "--artifacts", art, "--runs", runs, "--robot", robot, "--registry", reg,
                      "--today", "2026-09-30")
        check("an unreadable runs file is stated, and MTTR is n/a rather than invented",
              rc == 0 and "runs file unreadable" in out and "MTTR: **n/a**" in out)
        write(robot, "nothing")
        rc, out = cli("report", "--artifacts", art, "--robot", robot, "--registry", reg, "--today", "2026-09-30")
        check("invalid quarantine sources are shown in the report; the check job carries the failure",
              rc == 0 and "Quarantine sources are invalid" in out)


def test_report_e2e_quarantine_stage_and_recovery_rules():
    with tempfile.TemporaryDirectory() as d:
        art = Path(d) / "a"
        # Real depth: <outputdir>/e2e_<timestamp>/e2e-summary.json, outputdir = .../e2e-quarantine.
        write(art / "1" / "e2e-o-1" / "e2e-quarantine" / "e2e_20260922_030000" / "e2e-summary.json",
              e2e_summary(**{"S.Q": "fail"}))
        write(art / "2" / "e2e-o-2" / "e2e-quarantine" / "e2e_20260923_030000" / "e2e-summary.json",
              e2e_summary(**{"S.Q": "skip"}))
        runs, _ = H.load_runs(art, None)
        counts = H.stage_counts(runs)
        check("results under e2e-quarantine are their own stage", set(counts) == {"robot-e2e-quarantine"})
        keys = {key for r in runs for _, key, _ in r.results}
        check("the key drops the e2e_<timestamp> directory: one stable key across two runs",
              keys == {"e2e-o/e2e-quarantine::S.Q"}, str(keys))
        closed, still_open = H.outages(runs)
        check("a skip neither recovers nor extends a failure", not closed and len(still_open) == 1)
        check("without a runs file runs are ordered by id and carry no time", [r.run_id for r in runs] == ["1", "2"]
              and all(r.time is None for r in runs))


def test_e2e_key_is_stable_across_timestamped_run_dirs():
    """Regression: the key used the summary's parent directory, which is e2e_<timestamp>, so a failure
    and its recovery on the next run were two unrelated tests and the outage never closed."""
    check("the fixture's timestamped run directories differ between runs (else this test proves nothing)",
          e2e_run_dir("101") != e2e_run_dir("102") and H.E2E_RUN_DIR.match(e2e_run_dir("101")))
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        art = tmp / "artifacts"
        build_run(art, "101", "pass", "pass", "fail")
        build_run(art, "102", "pass", "pass", "pass")
        runs_file = write(tmp / "runs.json", json.dumps([
            {"id": 101, "created_at": "2026-09-22T03:00:00Z", "conclusion": "failure", "workflow": "nightly"},
            {"id": 102, "created_at": "2026-09-22T15:00:00Z", "conclusion": "success", "workflow": "nightly"}]))
        runs, _ = H.load_runs(art, runs_file)
        e2e_keys = [{k for stage, k, _ in r.results if stage == "robot-e2e"} for r in runs]
        check("the same e2e test has the same key in both runs",
              e2e_keys[0] == e2e_keys[1] and "e2e-org/2-robot_e2e::Suite.T2" in e2e_keys[0], str(e2e_keys))
        closed, still_open = H.outages(runs)
        e2e_closed = [k for k in closed if k.startswith("robot-e2e: ")]
        check("a failure followed by a same-day recovery closes the outage (12 h) and is not still open",
              e2e_closed == ["robot-e2e: e2e-org/2-robot_e2e::Suite.T2"]
              and not [k for k in still_open if k.startswith("robot-e2e: ")], f"{closed} {still_open}")
        robot = write(tmp / "QUARANTINE.md", register())
        reg = write(tmp / "registry.json", registry())
        rc, out = cli("report", "--artifacts", art, "--runs", runs_file, "--robot", robot, "--registry", reg,
                      "--today", "2026-09-30")
        check("the report shows the recovery and no still-failing e2e test",
              rc == 0 and "Mean time to recovery" in out and "Still failing" not in out)


def test_gaps_are_recorded():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        gaps = write(tmp / "gaps.txt", "run 7: e2e-org-7 (download failed)\nrun 8: verify-org-8 (download failed)\n")
        robot = write(tmp / "QUARANTINE.md", register())
        reg = write(tmp / "registry.json", registry())
        rc, out = cli("report", "--artifacts", tmp / "none", "--gaps", gaps, "--robot", robot, "--registry", reg,
                      "--today", "2026-09-30")
        check("artifacts that failed to download are named under data quality, not silently dropped",
              rc == 0 and "2 artifact(s) could not be downloaded" in out and "e2e-org-7" in out
              and "verify-org-8" in out)
        rc, out = cli("report", "--artifacts", tmp / "none", "--gaps", tmp / "absent.txt", "--robot", robot,
                      "--registry", reg, "--today", "2026-09-30")
        check("no gaps file (nothing failed) adds no note", rc == 0 and "could not be downloaded" not in out)


# ---- zizmor drift audit ------------------------------------------------------------------


def zfinding(rule, path, message="", row=0, ignored=False):
    location = {"symbolic": {"kind": "Primary", "key": {"Local": {"verbatim_path": path}}},
                "concrete": {"location": {"start_point": {"row": row, "column": 0}}}}
    return {"ident": rule, "desc": message or f"{rule} desc", "ignored": ignored, "locations": [location]}


def baseline_json(*entries):
    return json.dumps({"description": "x", "entries": [
        {"rule": r, "file": f, "message": m, "count": c, "reason": why} for r, f, m, c, why in entries]})


def test_zizmor_audit():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        findings = write(tmp / "z.json", json.dumps([
            zfinding("unpinned-uses", ".github\\workflows\\a.yml", "unpinned action reference", 4),
            zfinding("unpinned-uses", ".github/workflows/a.yml", "unpinned action reference", 9),
            zfinding("anonymous-definition", ".github/workflows/a.yml", "no name", 0),
            zfinding("anonymous-definition", ".github/workflows/a.yml", "no name", 1, ignored=True)]))
        baseline = write(tmp / "b.json", baseline_json(
            ("unpinned-uses", ".github/workflows/a.yml", "unpinned action reference", 1, "tag pin, accepted"),
            ("adhoc-packages", ".github/workflows/gone.yml", "ad-hoc", 2, "fixed since")))
        rc, out = cli("zizmor-audit", "--findings", findings, "--baseline", baseline, "--zizmor-version", "1.30.1")
        check("audit exits 0 (non-gating)", rc == 0)
        check("an inline-ignored finding is not counted; 3 findings in 2 groups", "Findings: **3** in 2" in out)
        check("1 accepted by the baseline, 2 not in it", "Accepted by the baseline: **1**" in out
              and "Not in the baseline: **2**" in out)
        check("a per-rule table splits baselined from not baselined",
              "| unpinned-uses | 2 | 1 | 1 |" in out and "| anonymous-definition | 1 | 0 | 1 |" in out)
        check("the baselined finding is listed with its reason", "tag pin, accepted" in out)
        check("the unbaselined finding is listed with its location",
              "`.github/workflows/a.yml:1`" in out or ".github/workflows/a.yml:1" in out)
        check("a stale baseline entry is reported as able to shrink",
              "Baseline entries that can shrink: **1**" in out and "gone.yml" in out and "found 0" in out)
        check("the zizmor version is in the title", "zizmor 1.30.1" in out)

        rc, out = cli("zizmor-audit", "--findings", findings, "--baseline", tmp / "absent.json")
        check("a missing baseline is reported, not an error (TP-11 not merged)",
              rc == 0 and "Baseline not found" in out and "Not in the baseline: **3**" in out)
        write(baseline, "{ not json")
        rc, out = cli("zizmor-audit", "--findings", findings, "--baseline", baseline)
        check("an unreadable baseline is a tool error (exit 2)", rc == 2 and "Tool error" in out)
        write(baseline, baseline_json())
        rc, out = cli("zizmor-audit", "--findings", tmp / "nofile.json", "--baseline", baseline)
        check("an unreadable findings file is a tool error (exit 2)", rc == 2)
        write(findings, "[]")
        rc, out = cli("zizmor-audit", "--findings", findings, "--baseline", baseline)
        check("no findings renders a clean audit", rc == 0 and "Findings: **0** in 0" in out)


def test_cli_surface():
    rc, out = cli("check-quarantine", "--today", "2026-09-29")
    check("the committed registers pass the CLI end to end", rc == 0)
    source = (REPO_ROOT / "scripts/ai/test_health.py").read_text(encoding="utf-8")
    io_lines = [ln for ln in source.splitlines() if ".read_text(" in ln or ".write_text(" in ln]
    check("scripts/ai/test_health.py has no shell=True and every text read/write names its encoding",
          "shell=True" not in source and io_lines and all("encoding=" in ln for ln in io_lines))


def main():
    test_committed_sources_are_valid()
    test_robot_register()
    test_json_registry()
    test_rules()
    test_expiry_and_cli()
    test_merged_table()
    test_report()
    test_report_e2e_quarantine_stage_and_recovery_rules()
    test_e2e_key_is_stable_across_timestamped_run_dirs()
    test_gaps_are_recorded()
    test_zizmor_audit()
    test_cli_surface()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
