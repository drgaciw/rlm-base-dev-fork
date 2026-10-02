#!/usr/bin/env python3
"""Unit tests for scripts/ci/junit_counts.py and scripts/ci/summary.py (TP-15).

Self-contained, stdlib only, no pytest required (this repo's lightweight test convention), so it
also runs in the Windows stdlib tier. Run from the repo root with base Python:

    python tests/test_ci_scripts.py

Exits 0 when all checks pass, 1 otherwise.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import junit_counts as J  # noqa: E402
import summary as S  # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
    if detail and not condition:
        print(f"         {detail}")
    if "pytest" in sys.modules:
        assert condition, f"{name} {detail}"


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def quiet(func, *args, **kwargs):
    """(result, captured stdout): the ::error:: annotations are part of the contract."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        result = func(*args, **kwargs)
    return result, buf.getvalue()


CASES = (
    '<testsuite>'
    '<testcase name="ok"/>'
    '<testcase name="fail"><failure message="x"/></testcase>'
    '<testcase name="err"><error message="x"/></testcase>'
    '<testcase name="skip"><skipped/></testcase>'
    '<testcase name="flaky"><rerunFailure message="x"/></testcase>'
    '<testcase name="both"><failure/><skipped/></testcase>'
    '</testsuite>'
)

with tempfile.TemporaryDirectory() as tmp:
    print("junit_counts: one report")
    p = write(tmp, "a.xml", CASES)
    c = J.junit_counts(p)
    check("failures and errors count as failed, a skipped child as skipped, a failure wins over skipped",
          (c.total, c.failed, c.skipped) == (6, 3, 1), str(c))
    check("a rerun record is counted as a rerun and the rerun-then-passed case is neither failed nor skipped",
          c.reruns == 1, str(c))
    check("nested testsuites/testsuite roots are walked",
          J.junit_counts(write(tmp, "n.xml", "<testsuites><testsuite><testcase/></testsuite>"
                                             "<testsuite><testcase><failure/></testcase></testsuite></testsuites>"))[:3] == (2, 1, 0))
    check("an empty testsuite is zero tests, not an error",
          J.junit_counts(write(tmp, "e.xml", "<testsuite/>")) == J.Counts())

    print("junit_counts: aggregation and CLI")
    counts, files = J.aggregate(os.path.join(tmp, "*.xml"))
    check("aggregate sums every matching report", len(files) == 3 and counts.total == 6 + 2 + 0, str(counts))
    d = os.path.join(tmp, "cli")
    write(d, "r.xml", CASES)
    rc, out = quiet(J.main, [os.path.join(d, "*.xml")])
    check("CLI on a populated report exits 0 and prints the counts",
          rc == 0 and "tests=6 failed=3 skipped=1 reruns=1 files=1" in out, out)
    rc, out = quiet(J.main, [os.path.join(tmp, "missing", "*.xml")])
    check("CLI on a pattern that matches nothing exits 1 and says so, never tests=0 as success",
          rc == 1 and "no report" in out and "::error::" in out, out)
    e = os.path.join(tmp, "emptycli")
    write(e, "r.xml", "<testsuite/>")
    rc, out = quiet(J.main, [os.path.join(e, "*.xml")])
    check("CLI on an empty report exits 1 with an error annotation", rc == 1 and "no testcases" in out, out)
    m = os.path.join(tmp, "badcli")
    write(m, "good.xml", CASES)
    write(m, "bad.xml", "<testsuite><testcase")
    rc, out = quiet(J.main, [os.path.join(m, "*.xml")])
    check("CLI on malformed XML exits 2 even when another report is fine", rc == 2 and "malformed" in out, out)
    rc, _ = quiet(J.main, [])
    check("CLI with no pattern is a usage error (2)", rc == 2)
    try:
        J.junit_counts(os.path.join(tmp, "nope.xml"))
        raised = False
    except J.MalformedReport:
        raised = True
    check("an unreadable file is reported as malformed, not skipped", raised)

    print("summary: verify")
    root = os.path.join(tmp, "verify")
    write(root, "test-results/apex/a.xml", CASES)
    write(root, "robot/rlm-base/results/verify/x/output.xml",
          '<robot><statistics><total><stat pass="5" fail="1" skip="2">All</stat></total></statistics></robot>')
    ok_env = {"OUTCOME_AGENT_PERMSETS": "success", "OUTCOME_APEX": "success",
              "OUTCOME_IDEMPOTENCY": "success", "OUTCOME_ROBOT": "success"}

    def run(fn, env, root, name):
        target = os.path.join(root, name + ".md")
        rc, out = quiet(fn, dict(env, GITHUB_STEP_SUMMARY=target), root)
        text = Path(target).read_text(encoding="utf-8") if os.path.exists(target) else ""
        return rc, out, text

    rc, out, text = run(S.verify, ok_env, root, "s1")
    check("verify: counts from JUnit and Robot output land in the table",
          "| Apex tests | success | 6 | 3 | 1 |" in text and "| Robot setup suites | success | 8 | 1 | 2 |" in text, text)
    check("verify: stages without counters keep the dash cells",
          "| Agent permission-set grants | success | - | - | - |" in text)
    check("verify: every stage succeeded and reports exist, exit 0 (counted failures do not by themselves flip a green stage)",
          rc == 0, out)
    rc, out, text = run(S.verify, dict(ok_env, OUTCOME_APEX="failure"), root, "s2")
    check("verify: a failed stage exits 1 with the stage named", rc == 1 and "Apex tests" in out, out)
    rc, out, text = run(S.verify, {k: v for k, v in ok_env.items() if k != "OUTCOME_ROBOT"}, root, "s3")
    check("verify: an unset outcome reads as skipped and fails", rc == 1 and "| Robot setup suites | skipped |" in text)

    bare = os.path.join(tmp, "bare")
    Path(bare).mkdir()
    rc, out, text = run(S.verify, ok_env, bare, "s4")
    check("verify: a green stage with no report says 'no report' and fails, it is never 0/0 green",
          rc == 1 and "| Apex tests | success | no report | - | - |" in text and "no report" in out, text + out)
    empty = os.path.join(tmp, "empty")
    write(empty, "test-results/apex/a.xml", "<testsuite/>")
    write(empty, "robot/rlm-base/results/verify/x/output.xml", "<robot><statistics><total/></statistics></robot>")
    rc, out, text = run(S.verify, ok_env, empty, "s5")
    check("verify: empty JUnit and Robot reports are named as empty and fail",
          rc == 1 and text.count("0 (empty report)") == 2, text)
    bad = os.path.join(tmp, "bad")
    write(bad, "test-results/apex/a.xml", "<testsuite><testcase")
    write(bad, "robot/rlm-base/results/verify/x/output.xml",
          '<robot><statistics><total><stat pass="1" fail="0" skip="0">All</stat></total></statistics></robot>')
    rc, out, text = run(S.verify, ok_env, bad, "s6")
    check("verify: malformed XML exits 2 and the table says so",
          rc == 2 and "| Apex tests | success | malformed report | - | - |" in text, text)

    print("summary: leg")
    leg_env = {"SHAPE": "default", "ORG_ALIAS": "gha-1", "OUTCOME_VALIDATE": "success",
               "OUTCOME_BUILD": "success", "OUTCOME_APEX": "success"}
    rc, out, text = run(S.leg, leg_env, root, "l1")
    check("leg: PASS with counts and committed defaults, exit 0",
          rc == 0 and "Result: **PASS**" in text and "| Apex tests (`run_tests`) | success | 6 | 3 | 1 |" in text
          and "- Flags: committed defaults" in text, text)
    rc, out, text = run(S.leg, dict(leg_env, SHAPE="tfid-pde"), root, "l2")
    check("leg: the tfid-pde shape states the runtime flag override", "`pde=true`, `billing_ui=false`" in text)
    rc, out, text = run(S.leg, dict(leg_env, OUTCOME_APEX=""), root, "l3")
    check("leg: a stage that did not run is INCOMPLETE and fails the leg",
          rc == 1 and "INCOMPLETE (not run: Apex tests (`run_tests`))" in text, text)
    rc, out, text = run(S.leg, dict(leg_env, OUTCOME_BUILD="failure"), root, "l4")
    check("leg: a failed stage is FAIL and fails the leg", rc == 1 and "FAIL: Build (`prepare_rlm_org`)" in text, text)
    rc, out, text = run(S.leg, leg_env, bare, "l5")
    check("leg: a green Apex stage without a report is FAIL (no report), never PASS",
          rc == 1 and "FAIL: Apex tests (`run_tests`) (no report)" in text and "PASS" not in text, text)
    rc, out, text = run(S.leg, leg_env, bad, "l6")
    check("leg: a malformed Apex report exits 2 (the inline step used to skip it silently)",
          rc == 2 and "malformed report" in text, text)
    rc, out, text = run(S.leg, leg_env, empty, "l7")
    check("leg: an empty Apex report is FAIL (empty report)", rc == 1 and "FAIL: Apex tests (`run_tests`) (empty report)" in text, text)

    print("summary: e2e")

    def summ(counts, tests=()):
        return json.dumps({"counts": counts, "tests": list(tests)})

    e2e_root = os.path.join(tmp, "e2e")
    base = "robot/rlm-base/results"
    write(e2e_root, f"{base}/e2e/one/e2e-summary.json",
          summ({"pass": 3, "flaky": 1, "fail": 0, "skip": 0}, [{"name": "T1", "result": "flaky"}]))
    write(e2e_root, f"{base}/e2e/two/sub/e2e-summary.json", summ({"pass": 2, "flaky": 0, "fail": 0, "skip": 1}))
    e2e_env = {"OUTCOME_E2E": "success", "OUTCOME_QUARANTINE": "success"}
    rc, out, text = run(S.e2e, e2e_env, e2e_root, "e1")
    check("e2e: totals, flaky list and the no-quarantine line, flaky is warned but not failed",
          rc == 0 and "| **total** | 5 | 1 | 0 | 1 |" in text and "- `T1`" in text
          and "no quarantined tests ran (step success)" in text and "::warning::Flaky e2e test" in out, text + out)
    rc, out, text = run(S.e2e, dict(e2e_env, OUTCOME_E2E="failure"), e2e_root, "e2")
    check("e2e: a non-success step outcome fails", rc == 1 and "e2e step outcome was failure" in out)
    none = os.path.join(tmp, "none")
    Path(none).mkdir()
    rc, out, text = run(S.e2e, e2e_env, none, "e3")
    check("e2e: no results at all fails explicitly ('no e2e results were produced')",
          rc == 1 and "no e2e results were produced" in out)
    (Path(e2e_root) / base / "e2e" / "three").mkdir()
    rc, out, text = run(S.e2e, e2e_env, e2e_root, "e4")
    check("e2e: a suite dir with no summary is 'did not complete' and fails",
          rc == 1 and "| three | - | - | - | did not complete |" in text and "suites without a summary: three" in out, text + out)
    write(e2e_root, f"{base}/e2e/four/e2e-summary.json",
          summ({"pass": 0, "flaky": 0, "fail": 1, "skip": 0}, [{"name": "T9", "result": "fail"}]))
    write(e2e_root, f"{base}/e2e-quarantine/q/e2e-summary.json", summ({"pass": 1, "flaky": 0, "fail": 1, "skip": 0}))
    rc, out, text = run(S.e2e, e2e_env, e2e_root, "e5")
    check("e2e: failures after rerun are listed and counted; quarantine totals are reported",
          "**Failed after the rerun:**" in text and "- `T9`" in text and "1 test(s) failed after the rerun" in out
          and "Quarantine (non-blocking, step success): pass 1, flaky 0, fail 1, skip 0." in text, text + out)
    write(e2e_root, f"{base}/e2e/five/e2e-summary.json", "{not json")
    rc, out, text = run(S.e2e, e2e_env, e2e_root, "e6")
    check("e2e: a malformed summary file exits 2", rc == 2 and "malformed e2e summary" in out, out)

    settle_root = os.path.join(tmp, "e2e_settle")
    settle_dir = f"{base}/e2e/1-robot_e2e"
    write(settle_root, f"{settle_dir}/e2e-summary.json", summ({"pass": 1, "flaky": 0, "fail": 0, "skip": 0}))
    rc, out, text = run(S.e2e, e2e_env, settle_root, "e7")
    check("e2e: no per-attempt outputs -> no SETTLE_TIMEOUT section (nothing to count)",
          rc == 0 and "SETTLE_TIMEOUT" not in text, text)
    warn = ('<msg time="2026-09-29T10:00:00.000000" level="WARN">SETTLE_TIMEOUT caller={} waited=15s</msg>')
    # Robot writes every WARN twice: in the keyword body and again in <errors>; only the latter counts.
    first_xml = ("<robot><suite><test><kw>" + warn.format("Save Modal:dialog-changed") + "</kw></test></suite>"
                 "<errors>" + warn.format("Save Modal:dialog-changed") + warn.format("Save Modal:dialog-changed")
                 + warn.format("Navigate To App") + "</errors></robot>")
    write(settle_root, f"{settle_dir}/first.xml", first_xml)
    write(settle_root, f"{settle_dir}/rerun/rerun.xml",
          "<robot><errors>" + warn.format("Click Browse Catalogs") + "</errors></robot>")
    write(settle_root, f"{settle_dir}/output.xml", first_xml + first_xml)  # merged output is never read
    rc, out, text = run(S.e2e, e2e_env, settle_root, "e8")
    check("e2e: SETTLE_TIMEOUT is counted per attempt and caller (names with spaces, <errors> copy only)",
          rc == 0 and "first attempt 3, rerun 1." in text and "- first attempt: `Save Modal:dialog-changed` x2" in text
          and "- first attempt: `Navigate To App` x1" in text and "- rerun: `Click Browse Catalogs` x1" in text, text)
    check("e2e: a first-attempt SETTLE_TIMEOUT is warned, not failed",
          "::warning::3 e2e best-effort wait(s) timed out on the first attempt" in out and rc == 0, out)
    write(settle_root, f"{settle_dir}/first.xml", "<robot><errors></errors></robot>")
    (Path(settle_root) / settle_dir / "rerun" / "rerun.xml").unlink()
    rc, out, text = run(S.e2e, e2e_env, settle_root, "e9")
    check("e2e: outputs with no SETTLE_TIMEOUT report 0 and no warning",
          rc == 0 and "first attempt 0, rerun 0." in text and "::warning::" not in out, text + out)

    print("summary: report (gh injected)")
    calls = []

    def fake_gh(*args, check=True):
        calls.append(args)
        if args[0] == "api":
            return "\n".join(json.dumps(j) for j in [
                {"name": "flow-matrix (default)", "conclusion": "failure", "html_url": "http://job/1",
                 "steps": [{"name": "Build", "conclusion": "failure"}, {"name": "Setup", "conclusion": "success"}]},
                {"name": "flow-matrix (tfid-pde)", "conclusion": "success"},
                {"name": "flow-matrix (billing)", "conclusion": "timed_out"},
            ])
        if args[:2] == ("issue", "list"):
            return json.dumps([{"number": 7, "title": "Flow matrix failure: default"}])
        if args[:2] == ("issue", "create"):
            return "http://issue/8\n"
        return ""

    renv = {"REPO": "o/r", "RUN_ID": "1", "RUN_ATTEMPT": "2", "RUN_URL": "http://run", "SHA": "abc"}
    target = os.path.join(tmp, "report.md")
    rc, out = quiet(S.report, dict(renv, GITHUB_STEP_SUMMARY=target), ".", fake_gh)
    text = Path(target).read_text(encoding="utf-8")
    check("report: an existing open issue gets a comment, a new failed shape gets an issue, a passing leg is ignored",
          rc == 0 and "- `default`: commented on #7" in text and "- `billing`: opened http://issue/8" in text
          and "tfid-pde" not in text, text)
    check("report: the issue body names the failed step",
          any(a[:2] == ("issue", "comment") and "Failed step(s): Build" in a[-1] for a in calls))
    check("report: label creation is best effort (check=False)",
          any(a[:2] == ("label", "create") for a in calls))

    print("summary: CLI dispatch")
    rc, _ = quiet(S.main, ["nope"], {})
    check("summary.py with an unknown subcommand is a usage error (2)", rc == 2)
    rc, _ = quiet(S.main, [], {})
    check("summary.py with no subcommand is a usage error (2)", rc == 2)
    check("every documented subcommand is registered", set(S.COMMANDS) == {"verify", "e2e", "leg", "report"})

    print("workflows call the scripts")
    wf = {n: (REPO_ROOT / ".github" / "workflows" / n).read_text(encoding="utf-8")
          for n in ("prepare-rlm-org.yml", "flow-matrix.yml")}
    check("no inline python heredoc is left in either workflow",
          all("python - <<" not in t and "def junit_counts" not in t for t in wf.values()))
    check("each summary step calls scripts/ci/summary.py",
          all(f"python scripts/ci/summary.py {sub}" in wf[f] for f, sub in
              [("prepare-rlm-org.yml", "verify"), ("prepare-rlm-org.yml", "e2e"),
               ("flow-matrix.yml", "leg"), ("flow-matrix.yml", "report")]))

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
sys.exit(1 if failed else 0)
