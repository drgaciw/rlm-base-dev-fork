#!/usr/bin/env python3
"""CI job summaries for the scratch-org workflows (TP-15). Stdlib only.

One entry point for the four summary/report steps that lived inline in
`.github/workflows/prepare-rlm-org.yml` and `.github/workflows/flow-matrix.yml`:

    python scripts/ci/summary.py verify   # prepare-rlm-org: "Verification summary"
    python scripts/ci/summary.py e2e      # prepare-rlm-org: "Robot e2e summary"
    python scripts/ci/summary.py leg      # flow-matrix: "Leg summary"
    python scripts/ci/summary.py report   # flow-matrix: "Open or update failure issues"

Stage outcomes and run metadata come from the environment exactly as the inline steps read
them. Markdown goes to $GITHUB_STEP_SUMMARY (stdout when unset). Exit 0 = every stage
succeeded, 1 = a stage failed or produced no usable results, 2 = a report or summary file
was not well-formed. A missing, empty or unparseable report is spelled out in the table and
fails the step; it is never rendered as 0 tests on a green stage.
"""
import glob
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import junit_counts as J  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_MALFORMED = 0, 1, 2
KEYS = ("pass", "flaky", "fail", "skip")
NO_COUNTS = ("-", "-", "-")


class Malformed(Exception):
    """A results file exists but cannot be read; carries the message for the summary."""


def robot_counts(path):
    try:
        stat = ET.parse(path).getroot().find("./statistics/total/stat")
    except (ET.ParseError, OSError) as exc:
        raise J.MalformedReport(path, str(exc)) from exc
    if stat is None:
        return J.Counts()
    p, f, s = (int(stat.get(k, 0)) for k in ("pass", "fail", "skip"))
    return J.Counts(p + f + s, f, s)


def stage_counts(pattern, counter):
    """(cells, problem, malformed) for one stage's result files.

    cells is the Tests/Failed/Skipped triple for the table. problem is None or a short reason
    ("no report", "empty report", "malformed report"); a stage outcome of `success` with a
    problem is still a failure of the step."""
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        return ("no report", "-", "-"), "no report", False
    total = J.Counts()
    try:
        for f in files:
            total += counter(f)
    except J.MalformedReport as exc:
        print(f"::error::malformed results file {exc}")
        return ("malformed report", "-", "-"), "malformed report", True
    if total.total == 0:
        return ("0 (empty report)", "-", "-"), "empty report", False
    return (total.total, total.failed, total.skipped), None, False


def write_summary(lines, env):
    text = "\n".join(lines) + "\n"
    target = env.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def verify(env, root="."):
    """prepare-rlm-org.yml "Verification summary"."""
    lines = [
        "## Nightly verification",
        "",
        "| Stage | Outcome | Tests | Failed | Skipped |",
        "|---|---|---|---|---|",
    ]
    stages = [
        ("Agent permission-set grants", "OUTCOME_AGENT_PERMSETS", None),
        ("Apex tests", "OUTCOME_APEX", ("test-results/apex/*.xml", J.junit_counts)),
        ("QB data idempotency", "OUTCOME_IDEMPOTENCY", None),
        ("Robot setup suites", "OUTCOME_ROBOT", ("robot/rlm-base/results/verify/**/output.xml", robot_counts)),
    ]
    failed_stages, malformed = [], False
    for label, var, counter in stages:
        outcome = env.get(var, "") or "skipped"
        if outcome != "success":
            failed_stages.append(label)
        cells = NO_COUNTS
        if counter:
            cells, problem, bad = stage_counts(os.path.join(root, counter[0]), counter[1])
            malformed = malformed or bad
            if problem and outcome == "success":
                failed_stages.append(f"{label} ({problem})")
        lines.append(f"| {label} | {outcome} | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines += ["", "These stages do not retry. Robot e2e results, with pass-after-rerun reported as flaky, are in the separate e2e summary."]
    write_summary(lines, env)
    if failed_stages or malformed:
        print("::error::Verification stage(s) not successful: " + ", ".join(failed_stages))
    return EXIT_MALFORMED if malformed else (EXIT_FAIL if failed_stages else EXIT_OK)


def _load_e2e(root):
    """{suite dir: summary or None} for every stage directory under root."""
    found = {}
    for d in sorted(glob.glob(root + "/*/")):
        files = glob.glob(d + "**/e2e-summary.json", recursive=True)
        try:
            summary = json.load(open(files[0], encoding="utf-8")) if files else None
        except (ValueError, OSError) as exc:
            raise Malformed(f"{files[0]}: {exc}") from exc
        found[os.path.basename(os.path.normpath(d))] = summary
    return found


def e2e(env, root="."):
    """prepare-rlm-org.yml "Robot e2e summary"."""
    results = os.path.join(root, "robot/rlm-base/results")
    try:
        blocking = _load_e2e(results + "/e2e")
        quarantine = _load_e2e(results + "/e2e-quarantine")
    except Malformed as exc:
        print(f"::error::malformed e2e summary {exc}")
        write_summary(["## Robot e2e", "", f"e2e summary file is not valid JSON: {exc}"], env)
        return EXIT_MALFORMED

    lines = ["## Robot e2e", ""]
    totals = dict.fromkeys(KEYS, 0)
    flaky, failed, missing = [], [], []
    lines += ["| Suite | Pass | Flaky | Fail | Skip |", "|---|---|---|---|---|"]
    for name, summary in blocking.items():
        if summary is None:
            missing.append(name)
            lines.append(f"| {name} | - | - | - | did not complete |")
            continue
        counts = summary["counts"]
        for k in KEYS:
            totals[k] += counts[k]
        flaky += [t["name"] for t in summary["tests"] if t["result"] == "flaky"]
        failed += [t["name"] for t in summary["tests"] if t["result"] == "fail"]
        lines.append(f"| {name} | {counts['pass']} | {counts['flaky']} | {counts['fail']} | {counts['skip']} |")
    lines.append(f"| **total** | {totals['pass']} | {totals['flaky']} | {totals['fail']} | {totals['skip']} |")
    if flaky:
        lines += ["", "**Flaky (failed, then passed on the single rerun) - not green:**"]
        lines += [f"- `{n}`" for n in flaky]
        lines += ["", "Repeat offenders go in robot/QUARANTINE.md (owner, issue, expiry <= 14 days)."]
        for n in flaky:
            print(f"::warning::Flaky e2e test (passed only after rerun): {n}")
    if failed:
        lines += ["", "**Failed after the rerun:**"] + [f"- `{n}`" for n in failed]

    q = env.get("OUTCOME_QUARANTINE", "") or "skipped"
    if quarantine:
        qt = dict.fromkeys(KEYS, 0)
        for summary in quarantine.values():
            for k in KEYS:
                qt[k] += (summary or {"counts": {}})["counts"].get(k, 0)
        lines += ["", f"Quarantine (non-blocking, step {q}): pass {qt['pass']}, flaky {qt['flaky']}, fail {qt['fail']}, skip {qt['skip']}."]
    else:
        lines += ["", f"Quarantine (non-blocking): no quarantined tests ran (step {q})."]

    outcome = env.get("OUTCOME_E2E", "") or "skipped"
    lines += ["", f"e2e step outcome: {outcome}."]
    write_summary(lines, env)

    problems = []
    if outcome != "success":
        problems.append(f"e2e step outcome was {outcome}")
    if not blocking:
        problems.append("no e2e results were produced")
    if missing:
        problems.append("suites without a summary: " + ", ".join(missing))
    if totals["fail"]:
        problems.append(f"{totals['fail']} test(s) failed after the rerun")
    if problems:
        print("::error::Robot e2e: " + "; ".join(problems))
        return EXIT_FAIL
    return EXIT_OK


def leg(env, root="."):
    """flow-matrix.yml "Leg summary"."""
    shape = env["SHAPE"]
    flags = (
        "`pde=true`, `billing_ui=false` (runtime override by `scripts/build_pde_dev_r1.sh`)"
        if shape == "tfid-pde"
        else "committed defaults"
    )
    apex_cells, apex_problem, malformed = stage_counts(
        os.path.join(root, "test-results/apex/*.xml"), J.junit_counts
    )
    stages = [
        ("Validate setup", "OUTCOME_VALIDATE", NO_COUNTS),
        ("Build (`prepare_rlm_org`)", "OUTCOME_BUILD", NO_COUNTS),
        ("Apex tests (`run_tests`)", "OUTCOME_APEX", apex_cells),
    ]
    lines = [
        f"## Flow matrix: {shape}",
        "",
        f"- Scratch alias: `{env['ORG_ALIAS']}` (deleted at the end of the job)",
        f"- Flags: {flags}",
        "",
        "| Stage | Outcome | Tests | Failed | Skipped |",
        "|---|---|---|---|---|",
    ]
    failed_stages, not_run = [], []
    for label, var, cells in stages:
        outcome = env.get(var, "") or "skipped"
        if outcome == "skipped":
            not_run.append(label)
        elif outcome != "success":
            failed_stages.append(label)
        elif var == "OUTCOME_APEX" and apex_problem:
            failed_stages.append(f"{label} ({apex_problem})")
        lines.append(f"| {label} | {outcome} | {cells[0]} | {cells[1]} | {cells[2]} |")
    if failed_stages:
        result = "FAIL: " + ", ".join(failed_stages)
    elif not_run:
        result = "INCOMPLETE (not run: " + ", ".join(not_run) + ")"
    else:
        result = "PASS"
    lines += [
        "",
        f"Result: **{result}**",
        "",
        "No automatic retry: a failed stage is reported as failed.",
    ]
    write_summary(lines, env)
    # Any stage that is not a success (failed or not run) fails the leg.
    if failed_stages or not_run or malformed:
        print("::error::Flow matrix leg " + shape + " not successful: " + result)
    return EXIT_MALFORMED if malformed else (EXIT_FAIL if failed_stages or not_run else EXIT_OK)


def gh(*args, check=True):
    return subprocess.run(
        ["gh", *args], check=check, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def report(env, root=".", gh=gh):
    """flow-matrix.yml "Open or update failure issues"."""
    repo = env["REPO"]
    jobs_raw = gh(
        "api", "--paginate",
        f"repos/{repo}/actions/runs/{env['RUN_ID']}/attempts/{env['RUN_ATTEMPT']}/jobs",
        "--jq", '.jobs[] | select(.name | startswith("flow-matrix ("))',
    )
    failed = []
    for line in jobs_raw.splitlines():
        job = json.loads(line)
        m = re.fullmatch(r"flow-matrix \((.+)\)", job["name"])
        if m and job.get("conclusion") in ("failure", "timed_out"):
            steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"]
            failed.append((m.group(1), job.get("html_url", env["RUN_URL"]), steps))

    summary = ["## Flow matrix failures", ""]
    if not failed:
        summary.append("No failed legs found in the Actions API (nothing to report).")
    gh("label", "create", "flow-matrix", "--repo", repo, "--color", "d93f0b",
       "--description", "Weekly CCI flow-matrix failure", check=False)
    for shape, url, steps in failed:
        title = f"Flow matrix failure: {shape}"
        body = (
            f"The weekly flow matrix leg for shape `{shape}` failed.\n\n"
            f"- Run: {env['RUN_URL']} (attempt {env['RUN_ATTEMPT']})\n"
            f"- Leg job: {url}\n"
            f"- Commit: {env['SHA']}\n"
            f"- Failed step(s): {', '.join(steps) if steps else 'see the job log'}\n\n"
            "See the leg's job summary and the `flow-matrix-" + shape + "-*` artifact. "
            "No automatic retry was attempted."
        )
        existing = json.loads(gh(
            "issue", "list", "--repo", repo, "--state", "open", "--label", "flow-matrix",
            "--limit", "100", "--json", "number,title",
        ) or "[]")
        match = next((i["number"] for i in existing if i["title"] == title), None)
        if match is not None:
            gh("issue", "comment", str(match), "--repo", repo, "--body", body)
            summary.append(f"- `{shape}`: commented on #{match}")
        else:
            out = gh("issue", "create", "--repo", repo, "--title", title,
                     "--label", "flow-matrix", "--body", body).strip()
            summary.append(f"- `{shape}`: opened {out}")
    write_summary(summary, env)
    return EXIT_OK


COMMANDS = {"verify": verify, "e2e": e2e, "leg": leg, "report": report}


def main(argv=None, env=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print("usage: summary.py {" + "|".join(COMMANDS) + "}", file=sys.stderr)
        return EXIT_MALFORMED
    return COMMANDS[argv[0]](os.environ if env is None else env)


if __name__ == "__main__":
    sys.exit(main())
