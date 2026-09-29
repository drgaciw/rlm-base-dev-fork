#!/usr/bin/env python3
"""Coverage ratchet for the Python suites (TP-10, docs/references/test-plan-2026-09.md 4.1).

`coverage-floor.json` holds one floor per package. A floor only ever goes up:

  * `check`  fails when a package's measured coverage is below its floor, and -- with
    `--base-ref` -- when the PR lowers or drops a floor that the base branch already committed.
    Coverage above the floor is reported as a notice, never a failure: raising the floor is a
    deliberate commit, not something a green build should be able to trip over.
  * `update` rewrites the file so each floor equals the measured value (rounded *down* to one
    decimal). It never lowers a floor and never touches `target`. Raising floors is always a
    manual `update` run and a commit; CI never does it.
  * Lowering a floor is possible only by saying why: the file's top-level `reason` field must gain
    a line `coverage-floor-lowered: <reason>` that the base branch's copy did not have.

`target` (scripts/ai 85, tasks 60 per the plan) is recorded for reference and never gates.

The measure is coverage.py's own combined statement+branch figure,
`(covered_lines + covered_branches) / (num_statements + num_branches)`, summed over every file
under the package prefix, so a package's number is not an average of per-file percentages.

`measure` produces the JSON report: it runs the whole gate (`pr_gate.py --all`, i.e. every T1+T2
suite and the agent-layer checks -- never a path-selected subset, or the numbers would swing per PR)
under `coverage run --branch`. A gate check that reports MISSING-DEP makes the run an "incomplete
measurement" (exit 2), never a coverage drop. It lives here rather than in the workflow so the CI
job never names the gate script itself -- tests/test_pr_gate.py requires that exactly one job runs
it. `check`/`update` read that JSON; only `measure` needs coverage.py installed.

Usage:
  python scripts/lint/coverage_ratchet.py measure [--json coverage/python-coverage.json]
  python scripts/lint/coverage_ratchet.py check  --report coverage/python-coverage.json
        [--floor coverage-floor.json] [--base-ref origin/main] [--summary FILE]
  python scripts/lint/coverage_ratchet.py update --report coverage/python-coverage.json

Exit codes follow scripts/ai/pr_gate.py: 0 pass, 1 verdict (a floor was breached or lowered, or the
gate failed under `measure`), 2 tool error (unreadable report, package with no measured files,
incomplete measurement). `--summary` defaults to `$GITHUB_STEP_SUMMARY` when that is set.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FLOOR = REPO_ROOT / "coverage-floor.json"
# Under coverage/, which .gitignore already covers (LWC Jest reports), so local runs leave no untracked files.
DEFAULT_REPORT = REPO_ROOT / "coverage" / "python-coverage.json"
GATE = REPO_ROOT / "scripts" / "ai" / "pr_gate.py"

# One decimal is the resolution of the committed floors, so a floor is `measured` rounded down to it.
# Rounded down, never to nearest: a floor above the measured value would fail the very run that set it.
DECIMALS = 1
# A package is only "raisable" once it clears its floor by at least one step of that resolution.
STEP = 10 ** -DECIMALS
# Guards float noise in `measured >= floor` when both sides are the same one-decimal number.
EPSILON = 1e-9
# Files under this percent are listed per package, so the aggregate cannot hide them.
LOW_FILE_PERCENT = 20.0
LOWERED_MARKER = "coverage-floor-lowered:"


class ToolError(Exception):
    """No verdict could be reached (exit 2), as opposed to a floor being breached (exit 1)."""


def round_down(value: float) -> float:
    scale = 10 ** DECIMALS
    return math.floor(value * scale + EPSILON) / scale


def load_json(path: Path, what: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        raise ToolError(f"cannot read {what} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ToolError(f"{what} {path} is not valid JSON: {exc}") from exc


def validate_floor_doc(doc, source: str) -> dict:
    """Return `doc["packages"]`, insisting on the shape every other function relies on."""
    packages = doc.get("packages") if isinstance(doc, dict) else None
    if not isinstance(packages, dict) or not packages:
        raise ToolError(f"{source}: expected a non-empty 'packages' object")
    for name, entry in packages.items():
        floor = entry.get("floor") if isinstance(entry, dict) else None
        if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not 0 <= floor <= 100:
            raise ToolError(f"{source}: package {name!r} needs a numeric 'floor' between 0 and 100")
    return packages


def norm(path: str) -> str:
    return path.replace("\\", "/")


def package_percent(report: dict, prefix: str) -> tuple[float, int]:
    """(percent, file count) for every file under `prefix`, from a `coverage json` report."""
    files = report.get("files")
    if not isinstance(files, dict):
        raise ToolError("report has no 'files' object; is this a `coverage json` report?")
    prefix = prefix.strip("/") + "/"
    covered = total = count = 0
    for path, info in files.items():
        if not norm(path).startswith(prefix):
            continue
        summary = info.get("summary", {})
        if "num_branches" not in summary:
            # Without branch data the figure would silently be statement-only, and a floor set from
            # it would be compared against a different measure than the one it was set with.
            raise ToolError(f"{path} has no branch data; run coverage with branch = true")
        covered += summary["covered_lines"] + summary["covered_branches"]
        total += summary["num_statements"] + summary["num_branches"]
        count += 1
    if count == 0:
        raise ToolError(f"no measured files under {prefix} -- the run did not measure this package "
                        "(wrong [tool.coverage.run] source, or no suite executed?)")
    percent = 100.0 if total == 0 else 100.0 * covered / total
    return percent, count


def low_coverage_files(report: dict, prefix: str) -> list[tuple[str, float]]:
    """(path, percent) for files under `prefix` below LOW_FILE_PERCENT, lowest first.

    Listed in the summary so a package's aggregate cannot blend a module nothing runs into a
    respectable-looking number: these are the cheapest places to add a first test. Files with no
    statements are skipped (an empty `__init__.py` is not a gap).
    """
    prefix = prefix.strip("/") + "/"
    out = []
    for path, info in report.get("files", {}).items():
        summary = info.get("summary", {})
        if not norm(path).startswith(prefix) or summary.get("num_statements", 0) == 0:
            continue
        total = summary["num_statements"] + summary.get("num_branches", 0)
        percent = 100.0 * (summary.get("covered_lines", 0) + summary.get("covered_branches", 0)) / total
        if percent < LOW_FILE_PERCENT:
            out.append((norm(path), percent))
    return sorted(out, key=lambda item: (item[1], item[0]))


def measure_packages(report: dict, packages: dict) -> dict:
    return {name: package_percent(report, name) for name in packages}


def floor_at_ref(ref: str, floor_path: Path) -> dict | None:
    """The whole committed floor document at `ref`, or None when that ref has no floor file yet."""
    try:
        rel = floor_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = floor_path.name
    try:
        proc = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=REPO_ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ToolError(f"could not run git: {exc}") from exc
    if proc.returncode != 0:
        # Distinguish "the file is not at that ref" (first PR to add it) from "the ref is bad",
        # which would otherwise read as a free pass on the whole no-lowering rule.
        verify = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                                cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
        if verify.returncode != 0:
            raise ToolError(f"base ref {ref!r} does not resolve to a commit")
        return None
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError(f"{ref}:{rel} is not valid JSON: {exc}") from exc
    validate_floor_doc(doc, f"{ref}:{rel}")
    return doc


def lowering_reason(head_doc: dict, base_doc: dict) -> str | None:
    """The `coverage-floor-lowered: <reason>` text this PR added to `reason`, or None.

    A line the base already carried does not count: otherwise one justified lowering would license
    every later one.
    """
    def marked(doc):
        reason = doc.get("reason")
        lines = reason.splitlines() if isinstance(reason, str) else []
        return {ln.strip() for ln in lines if ln.strip().startswith(LOWERED_MARKER)}

    for line in sorted(marked(head_doc) - marked(base_doc)):
        text = line[len(LOWERED_MARKER):].strip()
        if text:
            return text
    return None


def lowered_floors(head: dict, base: dict) -> list[str]:
    problems = []
    for name, entry in base.items():
        if name not in head:
            problems.append(f"{name}: package dropped from the floor file (base floor {entry['floor']})")
        elif head[name]["floor"] < entry["floor"]:
            problems.append(f"{name}: floor lowered {entry['floor']} -> {head[name]['floor']}")
    return problems


def render_summary(rows: list[dict], problems: list[str]) -> str:
    lines = ["## Python coverage ratchet", ""]
    for row in rows:
        color = "brightgreen" if row["status"] == "ok" else "red"
        label = row["name"].replace("/", "%2F")
        lines.append(f"![coverage {row['name']}](https://img.shields.io/badge/coverage%20{label}"
                     f"-{row['measured']:.1f}%25-{color})")
    lines += ["", "| Package | Files | Measured | Floor | Target | Status |", "|---|---:|---:|---:|---:|---|"]
    for row in rows:
        target = "" if row["target"] is None else f"{row['target']:.1f}%"
        lines.append(f"| `{row['name']}` | {row['files']} | {row['measured']:.2f}% | "
                     f"{row['floor']:.1f}% | {target} | {row['note']} |")
    for row in rows:
        if row["low"]:
            lines += ["", f"<details><summary>{len(row['low'])} file(s) in <code>{row['name']}</code> "
                          f"under {LOW_FILE_PERCENT:.0f}% covered</summary>", "",
                      *[f"- `{f}` {pct:.1f}%" for f, pct in row["low"]], "", "</details>"]
    if problems:
        lines += ["", "**Failing:**", *[f"- {p}" for p in problems]]
    lines += ["", "Measure: branch mode, `(covered lines + covered branches) / (statements + branches)`, "
              "the whole gate every run. Floors live in `coverage-floor.json`; raise them with "
              "`python scripts/lint/coverage_ratchet.py measure` then `... update`.", ""]
    return "\n".join(lines)


def coverage_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", "coverage", *args]


def cmd_measure(args) -> int:
    """Run the gate under coverage and write the JSON report; exit with the gate's own status.

    The report is written even when the gate fails, so `check` can still say what the numbers
    were, but a failing gate means suites did not all run: the figure is then a lower bound and
    the non-zero exit stops it being mistaken for a clean measurement.
    """
    try:
        probe = subprocess.run(coverage_cmd("--version"), cwd=REPO_ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ToolError(f"could not run {sys.executable}: {exc}") from exc
    if probe.returncode != 0:
        raise ToolError("coverage.py is not installed for this interpreter (pip install coverage>=7.10)")
    if subprocess.run(coverage_cmd("erase"), cwd=REPO_ROOT).returncode != 0:
        raise ToolError("coverage erase failed")
    # Streamed, not captured whole: the gate takes minutes and CI should show progress. PYTHONIOENCODING
    # so a check's non-ASCII output cannot crash the echo on a cp1252 console.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    missing = []
    with subprocess.Popen(coverage_cmd("run", str(GATE), "--all"), cwd=REPO_ROOT, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          encoding="utf-8", errors="replace") as gate:
        for line in gate.stdout:
            print(line, end="")
            if line.startswith("[MISSING-DEP"):
                missing.append(line.split("]", 1)[1].split()[0])
    args.json.parent.mkdir(parents=True, exist_ok=True)
    for step in (coverage_cmd("combine", "--quiet"), coverage_cmd("json", "-o", str(args.json), "--quiet")):
        if subprocess.run(step, cwd=REPO_ROOT).returncode != 0:
            raise ToolError(f"coverage {step[3]} failed: no coverage data was written "
                            "(did the gate reach any suite?)")
    print(f"coverage_ratchet: wrote {args.json} (gate exit {gate.returncode})")
    if missing:
        # Before the gate's own status: a check that never ran contributed no coverage, so the figure is
        # a lower bound for a reason unrelated to the change, and reporting it as a drop would be a lie.
        raise ToolError("incomplete measurement: gate check(s) blocked on a missing dependency: "
                        + ", ".join(missing) + " (install requirements-dev.txt)")
    return gate.returncode


def cmd_check(args) -> int:
    doc = load_json(args.floor, "floor file")
    packages = validate_floor_doc(doc, str(args.floor))
    report = load_json(args.report, "coverage report")
    measured = measure_packages(report, packages)

    problems, rows = [], []
    for name, entry in packages.items():
        percent, files = measured[name]
        floor = float(entry["floor"])
        target = entry.get("target")
        if percent + EPSILON < floor:
            status, note = "fail", f"below floor by {floor - percent:.2f} points"
            problems.append(f"{name}: measured {percent:.2f}% is below the floor {floor:.1f}%")
        elif round_down(percent) >= floor + STEP - EPSILON:
            status, note = "ok", f"floor can be raised to {round_down(percent):.1f}"
            print(f"::notice title=coverage floor can be raised::{name} measured {percent:.2f}% "
                  f"vs floor {floor:.1f}%; run `python scripts/lint/coverage_ratchet.py update`.")
        else:
            status, note = "ok", "at floor"
        rows.append(dict(name=name, files=files, measured=percent, floor=floor,
                         target=None if target is None else float(target), status=status, note=note,
                         low=low_coverage_files(report, name)))

    if args.base_ref:
        base_doc = floor_at_ref(args.base_ref, args.floor)
        if base_doc is None:
            print(f"coverage_ratchet: {args.base_ref} has no floor file yet; nothing to compare against.")
        else:
            lowered = lowered_floors(packages, base_doc["packages"])
            reason = lowering_reason(doc, base_doc) if lowered else None
            if lowered and reason:
                print(f"coverage_ratchet: floor lowering accepted with reason: {reason}")
                for line in lowered:
                    print(f"  {line}")
            else:
                problems += [f"{line} (say why with a new '{LOWERED_MARKER} <reason>' line in the "
                             "file's `reason` field)" for line in lowered]

    for row in rows:
        print(f"{row['name']:12} {row['measured']:6.2f}%  floor {row['floor']:5.1f}%  "
              f"({row['files']} files)  {row['note']}")
        if row["low"]:
            print(f"  under {LOW_FILE_PERCENT:.0f}% covered: "
                  + ", ".join(f"{f} ({pct:.0f}%)" for f, pct in row["low"]))
    summary_path = args.summary or os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(render_summary(rows, problems))
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    return 1 if problems else 0


def cmd_update(args) -> int:
    doc = load_json(args.floor, "floor file")
    packages = validate_floor_doc(doc, str(args.floor))
    measured = measure_packages(load_json(args.report, "coverage report"), packages)
    changed = False
    for name, entry in packages.items():
        candidate = round_down(measured[name][0])
        if candidate > entry["floor"] + EPSILON:
            print(f"{name}: floor {entry['floor']} -> {candidate}")
            entry["floor"] = candidate
            changed = True
        else:
            print(f"{name}: floor {entry['floor']} kept (measured {measured[name][0]:.2f}%)")
    if changed:
        # Insertion order kept, so the hand-written `_comment`/`reason`/`target` layout survives.
        with open(args.floor, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    measure = sub.add_parser("measure", help="run the gate under coverage and write the JSON report")
    measure.add_argument("--json", type=Path, default=DEFAULT_REPORT, help="report path (default: %(default)s)")
    for name in ("check", "update"):
        p = sub.add_parser(name)
        p.add_argument("--report", type=Path, default=DEFAULT_REPORT,
                       help="`coverage json` output (default: %(default)s)")
        p.add_argument("--floor", type=Path, default=DEFAULT_FLOOR, help="floor file (default: %(default)s)")
        if name == "check":
            p.add_argument("--base-ref", help="fail if the floor file lowers a floor committed at this ref")
            p.add_argument("--summary", help="append a markdown summary here (default: $GITHUB_STEP_SUMMARY)")
    args = ap.parse_args(argv)
    try:
        return {"measure": cmd_measure, "check": cmd_check, "update": cmd_update}[args.command](args)
    except ToolError as exc:
        print(f"coverage_ratchet: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
