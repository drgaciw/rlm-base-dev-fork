#!/usr/bin/env python3
"""Wiring tests for the workflow lint steps (TP-11): pins, baseline file and runbook.

The comparator itself is tested in tests/test_finding_baseline.py. This suite reads the committed
files that make the `actionlint` and `zizmor` steps of the Lint job reproducible, so an edit that
unpins a tool, sneaks an ignore list into `.zizmor.yml`, or leaves a baseline entry without a
reason fails a PR instead of decaying quietly.

Self-contained -- no pytest required. Run from the repo root with base Python:

    python tests/test_workflow_lint.py

Exits 0 when all checks pass, 1 otherwise.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-checks.yml"
BASELINE = REPO_ROOT / ".github" / "zizmor-baseline.json"
CONFIG = REPO_ROOT / ".zizmor.yml"
RUNBOOK = REPO_ROOT / "docs" / "guides" / "ci-runbook.md"

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


def read(path):
    return path.read_text(encoding="utf-8")


def test_baseline_file():
    entries = json.loads(read(BASELINE))["entries"]
    keys = [(e["rule"], e["file"], e.get("message", "")) for e in entries]
    check("committed zizmor baseline is sorted and free of duplicates", keys == sorted(set(keys)))
    check("every entry has a count >= 1 and a reason",
          all(isinstance(e["count"], int) and e["count"] >= 1 and e["reason"].strip() for e in entries))
    check("every baselined file exists under .github/workflows",
          all(e["file"].startswith(".github/workflows/") and (REPO_ROOT / e["file"]).is_file()
              for e in entries))
    check("every excessive-permissions and adhoc-packages entry is labelled SECURITY in its reason",
          all("SECURITY" in e["reason"] for e in entries
              if e["rule"] in ("excessive-permissions", "adhoc-packages")))
    check("no entry baselines unpinned-uses: that is a policy in .zizmor.yml, not a baselined finding",
          all(e["rule"] != "unpinned-uses" for e in entries))


def test_zizmor_config():
    config = read(CONFIG)
    check(".zizmor.yml pins first-party actions by ref and everything else by hash",
          '"actions/*": ref-pin' in config and '"*": hash-pin' in config)
    check(".zizmor.yml carries no ignore list (baselining is by count, in the JSON)",
          not re.search(r"^\s*ignore\s*:", config, re.MULTILINE))


def test_workflow_wiring():
    text = read(WORKFLOW)
    for var in ("ACTIONLINT_VERSION", "SHELLCHECK_PY_VERSION", "ZIZMOR_VERSION"):
        check(f"{var} is an exact version, never latest or a range",
              re.search(rf'^\s*{var}: "\d+(\.\d+){{2,3}}"$', text, re.MULTILINE))
    check("the actionlint tarball is verified against a committed sha256",
          re.search(r'ACTIONLINT_LINUX_AMD64_SHA256: "[0-9a-f]{64}"', text)
          and "sha256sum --check" in text)
    check("zizmor runs pedantic and offline, compared by count against the committed baseline",
          "--pedantic --offline" in text and "finding_baseline.py" in text
          and "--format zizmor" in text and ".github/zizmor-baseline.json" in text)
    check("actionlint runs shellcheck at warning severity, and the runbook documents the choice",
          "SHELLCHECK_OPTS: --severity=warning" in text and "--severity=warning" in read(RUNBOOK))
    check("the workflow steps run only when a workflow, the zizmor files or the comparer changed",
          text.count("steps.workflows.outputs.changed == 'true'") == 3
          and "finding_baseline" in text.split("Detect workflow changes", 1)[1].split("run: |", 1)[1][:400])
    check("the runbook documents the docker-publish ci-smoke dispatch",
          "ci-smoke-" in read(RUNBOOK) and "platforms=linux/amd64" in read(RUNBOOK))


def main():
    test_baseline_file()
    test_zizmor_config()
    test_workflow_wiring()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
