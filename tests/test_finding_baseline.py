#!/usr/bin/env python3
"""Unit tests for scripts/lint/finding_baseline.py (TP-11a).

Self-contained -- no pytest required (matches this repo's lightweight test
convention). Run from the repo root with base Python:

    python tests/test_finding_baseline.py

Exits 0 when all checks pass, 1 otherwise.
"""
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "lint" / "finding_baseline.py"
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lint"))

import finding_baseline as B  # noqa: E402

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


def zizmor_finding(rule, path, row=0, ignored=False, desc=None):
    """The subset of `zizmor --format json` the adapter reads."""
    location = {"symbolic": {"kind": "Primary", "key": {"Local": {"verbatim_path": path}}},
                "concrete": {"location": {"start_point": {"row": row, "column": 0}}}}
    related = {"symbolic": {"kind": "Related", "key": {"Local": {"verbatim_path": "other.yml"}}}}
    return {"ident": rule, "desc": desc or f"{rule} desc", "ignored": ignored,
            "locations": [related, location]}


def test_compare():
    allowed = Counter({("r", "a.yml", ""): 2, ("s", "b.yml", "m"): 1})
    regressions, improvements = B.compare(dict(allowed), allowed)
    check("equal counts: no regression, nothing to shrink", not regressions and not improvements)
    regressions, _ = B.compare(Counter({("r", "a.yml", ""): 3, ("s", "b.yml", "m"): 1}), allowed)
    check("one more finding of a listed rule in a listed file is a regression",
          regressions == [(("r", "a.yml", ""), 2, 3)])
    regressions, _ = B.compare(Counter({**allowed, ("r", "c.yml", ""): 1}), allowed)
    check("a listed rule in an unlisted file is a regression",
          regressions == [(("r", "c.yml", ""), 0, 1)])
    regressions, _ = B.compare(Counter({**allowed, ("t", "a.yml", ""): 1}), allowed)
    check("an unlisted rule in a listed file is a regression",
          regressions == [(("t", "a.yml", ""), 0, 1)])
    regressions, _ = B.compare(Counter({("r", "a.yml", ""): 2, ("s", "b.yml", "other"): 1}), allowed)
    check("the message is part of the key: the same rule and file with a new message is a regression",
          regressions == [(("s", "b.yml", "other"), 0, 1)])
    regressions, improvements = B.compare(Counter({("r", "a.yml", ""): 1}), allowed)
    check("fewer findings is an improvement, never a regression",
          not regressions
          and improvements == [(("r", "a.yml", ""), 2, 1), (("s", "b.yml", "m"), 1, 0)])


def test_pairs_adapter():
    found = B.pairs_findings([["r", ".\\x\\a.yml"], ["r", "a.yml", "m"], ["r", "a.yml", "m", "a.yml:3"]])
    check("pairs rows accept 2, 3 or 4 elements and normalise paths",
          found == [("r", "x/a.yml", "", ""), ("r", "a.yml", "m", ""), ("r", "a.yml", "m", "a.yml:3")])
    for bad in ({"not": "a list"}, [["only-rule"]], [["a", "b", "c", "d", "e"]], ["not-a-row"]):
        try:
            B.pairs_findings(bad)
            raised = False
        except ValueError:
            raised = True
        check(f"pairs input {bad!r} is a tool error", raised)


def test_zizmor_adapter():
    data = [zizmor_finding("r", ".github\\workflows\\a.yml", row=4, desc="overly broad"),
            zizmor_finding("r", "./.github/workflows/a.yml", row=9, desc="overly broad"),
            zizmor_finding("s", ".github/workflows/b.yml", ignored=True)]
    found = B.zizmor_findings(data)
    check("primary location is used and paths are normalised to forward slashes",
          [(r, f) for r, f, _, _ in found] == [("r", ".github/workflows/a.yml")] * 2)
    check("findings suppressed by an inline comment are skipped", all(r != "s" for r, _, _, _ in found))
    check("message is the rule description, with no location in it",
          [m for _, _, m, _ in found] == ["overly broad"] * 2)
    check("where carries the 1-based line for humans, apart from the key",
          [w for _, _, _, w in found] == [".github/workflows/a.yml:5", ".github/workflows/a.yml:10"])
    for bad in ([{"ident": "r", "locations": []}], {"not": "a list"}):
        try:
            B.zizmor_findings(bad)
            raised = False
        except ValueError:
            raised = True
        check(f"zizmor input {str(bad)[:30]!r} is a tool error, not a silent skip", raised)


def run_cli(tmp, findings, baseline, *extra, fmt="pairs"):
    findings_path = Path(tmp) / "findings.json"
    findings_path.write_text(json.dumps(findings), encoding="utf-8")
    baseline_path = Path(tmp) / "baseline.json"
    if baseline is None:
        baseline_path.unlink(missing_ok=True)
    else:
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--baseline", str(baseline_path), "--format", fmt,
         *extra, str(findings_path)],
        capture_output=True, text=True, encoding="utf-8", check=False)
    return proc, baseline_path


def test_cli():
    baseline = {"entries": [{"rule": "r", "file": "a.yml", "count": 1, "reason": "why"}]}
    with tempfile.TemporaryDirectory() as tmp:
        proc, _ = run_cli(tmp, [["r", "a.yml"]], baseline)
        check("CLI: findings within the baseline exit 0", proc.returncode == 0)
        proc, _ = run_cli(tmp, [["r", "a.yml", "", "a.yml:3"], ["r", "a.yml", "", "a.yml:9"]], baseline)
        check("CLI: a regression exits 1 and names the rule and file",
              proc.returncode == 1 and "r in a.yml: 2 found, baseline allows 1" in proc.stdout)
        check("CLI: a regression prints each finding's location so the new one can be found",
              "a.yml:3" in proc.stdout and "a.yml:9" in proc.stdout)
        proc, _ = run_cli(tmp, [], baseline)
        check("CLI: fixing a finding exits 0 and says to shrink the baseline",
              proc.returncode == 0 and "can shrink" in proc.stdout)
        proc, _ = run_cli(tmp, {"not": "pairs"}, baseline)
        check("CLI: malformed input is exit 2 (tool error), not a verdict",
              proc.returncode == 2 and "tool error" in proc.stderr)
        proc, _ = run_cli(tmp, [], None)
        check("CLI: a missing baseline is exit 2", proc.returncode == 2)
        proc, _ = run_cli(tmp, [], {"entries": [{"rule": "r", "file": "a.yml", "count": 0}]})
        check("CLI: a zero-count baseline entry is rejected (delete the entry instead)", proc.returncode == 2)
        proc, _ = run_cli(tmp, [], {"entries": baseline["entries"] * 2})
        check("CLI: a duplicated baseline entry is rejected", proc.returncode == 2)
        keyed = {"entries": [{"rule": "r", "file": "a.yml", "message": "m", "count": 1}]}
        proc, _ = run_cli(tmp, [["r", "a.yml", "m"]], keyed)
        check("CLI: an entry with a message matches findings with that message", proc.returncode == 0)
        proc, _ = run_cli(tmp, [["r", "a.yml", "changed"]], keyed)
        check("CLI: a changed message is a regression and names the message",
              proc.returncode == 1 and "(changed)" in proc.stdout)


def test_write_keeps_reasons():
    baseline = {"entries": [{"rule": "r", "file": "a.yml", "message": "m", "count": 1, "reason": "why"}]}
    with tempfile.TemporaryDirectory() as tmp:
        proc, path = run_cli(tmp, [["r", "a.yml", "m"], ["r", "a.yml", "m"], ["s", "b.yml"]],
                             baseline, "--write")
        written = json.loads(path.read_text(encoding="utf-8"))
        entries = {(e["rule"], e["file"], e.get("message", "")): e for e in written["entries"]}
        check("--write exits 0 and records the new counts",
              proc.returncode == 0 and entries[("r", "a.yml", "m")]["count"] == 2
              and ("s", "b.yml", "") in entries)
        check("--write keeps the reason of an entry that already existed",
              entries[("r", "a.yml", "m")]["reason"] == "why")
        check("--write omits an empty message and sorts entries so diffs stay small",
              "message" not in entries[("s", "b.yml", "")]
              and [(e["rule"], e["file"], e.get("message", "")) for e in written["entries"]]
              == sorted(entries))
        raw = path.read_bytes()
        check("--write output is LF-terminated with a trailing newline, on every OS",
              b"\r" not in raw and raw.endswith(b"\n"))
        proc, _ = run_cli(tmp, [["r", "a.yml", "m"], ["r", "a.yml", "m"], ["s", "b.yml"]], written)
        check("what --write recorded then passes the comparison", proc.returncode == 0)


def test_registry():
    check("FORMATS registers the pairs and zizmor parsers; a new linter adds one entry",
          set(B.FORMATS) == {"pairs", "zizmor"} and all(callable(p) for p in B.FORMATS.values()))


def main():
    test_compare()
    test_pairs_adapter()
    test_zizmor_adapter()
    test_cli()
    test_write_keeps_reasons()
    test_registry()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
