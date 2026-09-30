#!/usr/bin/env python3
"""Unit tests for scripts/ai/bump_api_version.py (TP-10b).

The release-cutover tool rewrites every Salesforce API pin in the tree at once, so its failure modes
are silent ones: a rule that stopped matching reports "already at target"; a provenance line
("verified on v67.0") that gets rewritten turns a recorded observation into a false claim; an
exclusion keyed on a line number that drifted shields the wrong line. These tests pin the guards
against each of those, plus the mechanics (dry run writes nothing, --apply writes, --check exits 1
while anything is off-target).

Everything runs against a throwaway tree: `REPO_ROOT` is pointed at a temp directory and
`tracked_files()` (normally `git ls-files`) is replaced with the temp tree's file list, so no git
repo, org or network is involved and the real checkout is never touched. A few checks run the
script's own self-tests (`validate_rules`, `validate_excluded_lines`) against the real repo, since
those are what `--check` relies on.

Self-contained -- no pytest:

    python tests/test_bump_api_version.py

Exits 0 when every check passes, 1 otherwise.
"""
import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai"))

import bump_api_version as B  # noqa: E402

RESULTS = []


def _ascii(text):
    """stdout may be cp1252 (Windows, PYTHONUTF8 unset); never let a check name crash the run."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(_ascii(f"  [{'PASS' if condition else 'FAIL'}] {name}"
                 + ("" if condition or detail == "" else f": {detail}")))


# rel path -> content. Every pin class the rules know, one provenance line, one floor, one null.
TREE = {
    "sfdx-project.json": '{\n  "sourceApiVersion": "66.0"\n}\n',
    "cumulusci.yml": 'project:\n  package:\n    api_version: "66.0"\ntasks:\n  t:\n    options:\n'
                     '      api_version: null\n',
    "force-app/main/x-meta.xml": "<a><apiVersion>65.0</apiVersion></a>\n",
    "datasets/plan/export.json": '{"apiVersion": "66.0"}\n',
    "tasks/t.py": 'API_VERSION = "v66.0"\nOTHER = "66.0"\nMIN_API_VERSION = "58.0"\n'
                  'NOTE = "v66.0"  # verified on 262\n',
    "scripts/s.py": 'url = "/services/data/v66.0/sobjects/Account"\nkeep = "/services/data/v66.0/x"'
                    '  # live-verified v66.0\n',
    "unpackaged/post_utils/classes/A.cls": "String path = '/services/data/v66.0/query';\n",
    # Excluded by prefix / by file: must stay byte-identical.
    "docs/salesforce/264/help-meta.xml": "<apiVersion>60.0</apiVersion>\n",
    "docs/erds/erd-data.json": '{"apiVersion": "66.0"}\n',
    "unpackaged/post_mcp/y-meta.xml": "<apiVersion>60.0</apiVersion>\n",
    # Not a tracked file: must never be read.
    "untracked/z-meta.xml": "<apiVersion>60.0</apiVersion>\n",
}
UNTRACKED = {"untracked/z-meta.xml"}


class Tree:
    """A temp tree wired into the module: REPO_ROOT, tracked_files and an empty EXCLUDED_LINES."""

    def __init__(self, files=None, excluded_lines=None):
        self.files = dict(TREE if files is None else files)
        self.excluded_lines = {} if excluded_lines is None else excluded_lines
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for rel, text in self.files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        tracked = frozenset(r for r in self.files if r not in UNTRACKED)
        self._stack = contextlib.ExitStack()
        self._stack.enter_context(mock.patch.object(B, "REPO_ROOT", str(self.root)))
        self._stack.enter_context(mock.patch.object(B, "tracked_files", lambda: tracked))
        self._stack.enter_context(mock.patch.object(B, "EXCLUDED_LINES", self.excluded_lines))

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def snapshot(self):
        return {rel: self.read(rel) for rel in self.files}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._stack.close()
        self._tmp.cleanup()


def run_main(argv):
    """(exit code, stdout, stderr) of B.main() with sys.argv=argv."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", ["bump_api_version.py", *argv]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = B.main()
    return code, out.getvalue(), err.getvalue()


def test_small_helpers():
    print("\nexcluded_reason / next_version")
    check("a path under an excluded prefix is excluded with its reason",
          "frozen" in (B.excluded_reason("docs/salesforce/264/x.md") or "")
          and B.excluded_reason("unpackaged/post_mcp/a/b-meta.xml") is not None)
    check("an individually excluded file is excluded", B.excluded_reason("docs/erds/erd-data.json") is not None)
    check("an ordinary path is in scope", B.excluded_reason("force-app/main/x-meta.xml") is None)
    check("the tracked private artifacts tree is excluded (retargeted by hand)",
          B.excluded_reason(".agents/context/project-memory.json") is not None)
    check("next_version steps one release", B.next_version("68.0") == "69.0" and B.next_version("99.0") == "100.0")
    check("an unparseable target falls back to the probe ceiling", B.next_version("abc") == f"{B.PROBE_CEILING}.0")


def test_rule_self_tests():
    print("\nvalidate_rules: a rule that went blind must be reported")
    rules = B.build_rules()
    check("every shipped rule has a probe and survives its own self-test at 68.0",
          B.validate_rules(rules, "68.0") == [], B.validate_rules(rules, "68.0"))
    check("the self-test holds at the other end of the range too (no capped ranges)",
          B.validate_rules(B.build_rules(), "60.0") == [] and B.validate_rules(B.build_rules(), "98.0") == [])

    blind = B.build_rules()
    blind[0].pattern = re.compile(r"NEVER-MATCHES-(?P<ver>\d+\.\d+)")
    problems = B.validate_rules(blind, "68.0")
    check("a pattern that no longer matches its own probe is named as gone blind",
          any(p.startswith("sfdx-project:") and "gone blind" in p for p in problems), problems)

    capped = B.build_rules()
    py_rule = next(r for r in capped if r.name == "python")
    py_rule.pattern = re.compile(r"""(?P<q>['"])(?P<v>v?)(?P<ver>6[0-7]\.0)(?P=q)""")
    problems = B.validate_rules(capped, "68.0")
    check("a range capped below the target is caught at the target probe",
          any(p.startswith("python:") for p in problems), problems)

    no_probe = B.build_rules()
    no_probe[1].probe = ""
    check("a rule with no probe is reported (--check cannot verify it)",
          any("no probe defined" in p for p in B.validate_rules(no_probe, "68.0")))

    bad_replace = B.build_rules()
    bad_replace[2].replace = lambda m, t: m.group(0)
    check("a rule that matches but rewrites to the wrong text is reported",
          any(p.startswith("meta-xml:") and "instead of" in p for p in B.validate_rules(bad_replace, "68.0")))


def test_provenance_grammar():
    print("\nprovenance guard")
    check("every documented provenance form is spared", B.validate_provenance_grammar() == [])
    for line in ("# live-verified v67.0", "x = 1  # verified on 262 / v67.0", "# as of v67.0",
                 "MIN_API_VERSION = '50.0'", "observed at 262 v67.0"):
        check(f"provenance line is recognised: {line!r}", B.PROVENANCE_LINE_RE.search(line) is not None)
    check("an ordinary pin line is not provenance", B.PROVENANCE_LINE_RE.search('API = "v67.0"') is None)
    with mock.patch.object(B, "PROVENANCE_LINE_RE", re.compile(r"live-verified")):
        problems = B.validate_provenance_grammar()
    check("a guard that lost forms names each one it no longer spares",
          any("'verified on'" in p for p in problems) and not any("'live-verified'" in p for p in problems),
          problems)


def test_excluded_lines():
    print("\nvalidate_excluded_lines: keys that drifted")
    files = {"a.cls": "line one\n// dataPath semantics verified on v67.0\nline three\n"}
    with Tree(files) as t:
        ok = {("a.cls", 2): ("why", "dataPath semantics")}
        check("an entry pointing at its marker line is clean", _validate(ok) == [])
        check("a marker that moved is reported as drifted (the exclusion would shield another line)",
              any("has drifted" in p for p in _validate({("a.cls", 1): ("why", "dataPath semantics")})))
        check("a line number past the end is reported out of range",
              any("out of range" in p for p in _validate({("a.cls", 9): ("why", "x")})))
        check("a deleted file is reported", any("no longer exists" in p
                                                for p in _validate({("gone.cls", 1): ("why", "x")})))
        check("a marker line with no version no longer protects anything",
              any("no API version" in p for p in _validate({("a.cls", 3): ("why", "line three")})))
    problems = B.validate_excluded_lines()
    check("the real EXCLUDED_LINES still point at their marker lines in this checkout", problems == [], problems)


def _validate(entries):
    with mock.patch.object(B, "EXCLUDED_LINES", entries):
        return B.validate_excluded_lines()


def test_process():
    print("\nprocess: per-rule rewriting")
    with Tree() as t:
        before = t.snapshot()
        rules = {r.name: r for r in B.build_rules()}
        changed, hits, skipped = B.process(rules["sfdx-project"], "68.0", False, False)
        check("a dry run counts the hit but writes nothing",
              (changed, hits) == (1, 1) and t.snapshot() == before)
        for name in ("sfdx-project", "cumulusci", "meta-xml", "sfdmu", "python", "python-service-path", "apex"):
            B.process(rules[name], "68.0", True, False)
        check("sfdx-project, cumulusci (quoted only), meta-xml and sfdmu pins are rewritten",
              '"68.0"' in t.read("sfdx-project.json")
              and 'api_version: "68.0"' in t.read("cumulusci.yml")
              and "<apiVersion>68.0</apiVersion>" in t.read("force-app/main/x-meta.xml")
              and '"apiVersion": "68.0"' in t.read("datasets/plan/export.json"))
        check("`api_version: null` overrides stay null", "api_version: null" in t.read("cumulusci.yml"))
        py = t.read("tasks/t.py")
        check("a Python vNN.0 literal keeps its quote style and v prefix",
              'API_VERSION = "v68.0"' in py and 'OTHER = "68.0"' in py, py)
        check("a floor (MIN_API_VERSION) and a `verified on` line keep their version",
              'MIN_API_VERSION = "58.0"' in py and 'NOTE = "v66.0"  # verified on 262' in py, py)
        s = t.read("scripts/s.py")
        check("a /services/data/vNN.0/ path is rewritten but a live-verified line is spared",
              'url = "/services/data/v68.0/sobjects/Account"' in s and "v66.0/x" in s, s)
        check("Apex REST paths are rewritten",
              "/services/data/v68.0/query" in t.read("unpackaged/post_utils/classes/A.cls"))
        check("excluded prefixes/files and untracked files are byte-identical",
              all(t.read(r) == before[r] for r in ("docs/salesforce/264/help-meta.xml", "docs/erds/erd-data.json",
                                                   "unpackaged/post_mcp/y-meta.xml", "untracked/z-meta.xml")))
        again = [B.process(rules[n], "68.0", True, False)[1] for n in rules]
        check("a second --apply finds nothing left to change (idempotent)", sum(again) == 0, again)
        _, _, skipped = B.process(rules["meta-xml"], "68.0", False, False)
        check("excluded files are reported in the skip counter",
              sum(skipped.values()) >= 2 and any("frozen" in k for k in skipped), dict(skipped))

    with Tree({"a.cls": "x\nv66.0 // dataPath\ny v66.0\n"}, {("a.cls", 2): ("recorded at 262", "dataPath")}) as t:
        rule = next(r for r in B.build_rules() if r.name == "apex")
        _, hits, skipped = B.process(rule, "68.0", True, False)
        check("an EXCLUDED_LINES entry spares its exact line and counts it, while other lines still change",
              hits == 1 and t.read("a.cls") == "x\nv66.0 // dataPath\ny v68.0\n"
              and skipped["recorded at 262"] == 1, (t.read("a.cls"), dict(skipped)))

    with Tree({"a-meta.xml": "<apiVersion>66.0</apiVersion>\n"}) as t:
        rule = next(r for r in B.build_rules() if r.name == "meta-xml")
        rule.skip_file_if = lambda text: True
        _, hits, skipped = B.process(rule, "68.0", True, False)
        check("a per-file veto skips the file and says so", hits == 0 and skipped["per-file veto"] == 1
              and "66.0" in t.read("a-meta.xml"))
        (t.root / "a-meta.xml").write_bytes(b"\xff\xfe\x00bad")
        rule.skip_file_if = None
        _, hits, _ = B.process(rule, "68.0", True, False)
        check("an undecodable file is skipped rather than crashing the run", hits == 0)

    with Tree({"a-meta.xml": "<apiVersion>66.0</apiVersion>\n"}) as t:
        rule = next(r for r in B.build_rules() if r.name == "meta-xml")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            B.process(rule, "68.0", False, True)
        check("--verbose prints each change as path:line with its - and + lines",
              "a-meta.xml:1" in out.getvalue() and "- <apiVersion>66.0" in out.getvalue()
              and "+ <apiVersion>68.0" in out.getvalue(), out.getvalue())

    with Tree({"sfdx-project.json": '{"sourceApiVersion": "68.0"}\n'}) as t:
        rule = next(r for r in B.build_rules() if r.name == "sfdx-project")
        check("a pin already at the target is a no-op", B.process(rule, "68.0", True, False)[:2] == (0, 0))


def test_main():
    print("\nmain(): modes and exit codes")
    with Tree() as t:
        before = t.snapshot()
        code, out, _ = run_main([])
        check("the default is a dry run: exit 0, banner says so, nothing written",
              code == 0 and "[DRY RUN]" in out and "Dry run only" in out and t.snapshot() == before, out)
        check("the total and the skip report are printed", "Total:" in out and "Deliberately skipped" in out, out)

        code, out, err = run_main(["--check"])
        check("--check exits 1 while pins are off-target and names the count",
              code == 1 and "check: FAIL" in err and "not at 68.0" in err and t.snapshot() == before, err)

        code, out, err = run_main(["--apply", "--check"])
        check("--apply --check is a dry run and the banner says CHECK, not APPLY",
              "CHECK (dry run)" in out and "[APPLY]" not in out and t.snapshot() == before and code == 1, out)

        code, out, _ = run_main(["--apply"])
        check("--apply writes the pins", code == 0 and "[APPLY]" in out
              and "<apiVersion>68.0</apiVersion>" in t.read("force-app/main/x-meta.xml"), out)
        code, out, _ = run_main(["--check"])
        check("after --apply, --check passes", code == 0 and "check: PASS" in out, out)
        code, out, _ = run_main(["--to", "69.0", "--check"])
        check("--to retargets: the same tree is off-target for the next release", code == 1)
        code, out, _ = run_main(["--only", "sfdx-project", "--to", "69.0", "--apply"])
        check("--only limits the run to the named rule",
              code == 0 and '"69.0"' in t.read("sfdx-project.json")
              and "<apiVersion>68.0</apiVersion>" in t.read("force-app/main/x-meta.xml"), out)

    with Tree() as t:
        for bad in ("68.1", "68", "abc", "6８.0", "100.0", "v68.0"):
            code, _, err = run_main(["--to", bad])
            check(f"--to {bad!r} is rejected (must look like NN.0), exit 2", code == 2 and "NN.0" in err, err)
        code, _, err = run_main(["--only", "nope"])
        check("an unknown --only rule is rejected with exit 2", code == 2 and "unknown rule(s): nope" in err, err)
        with mock.patch.object(B, "validate_excluded_lines", lambda: ["a.cls:2 - drifted"]):
            code, _, err = run_main([])
        check("stale EXCLUDED_LINES abort the run with exit 2 before anything is rewritten",
              code == 2 and "a.cls:2 - drifted" in err)
        with mock.patch.object(B, "validate_rules", lambda rules, target: ["sfdx-project: gone blind"]):
            code, _, err = run_main(["--check"])
        check("--check with a blind rule is a tooling failure (exit 2), reported before any verdict",
              code == 2 and "rule self-test failed" in err and "gone blind" in err, err)


def test_tracked_files():
    print("\ntracked_files")
    B.tracked_files.cache_clear()
    files = B.tracked_files()
    check("scope is git-tracked files only (repo-relative, non-empty, includes this script)",
          "scripts/ai/bump_api_version.py" in files and all("\0" not in f for f in files))
    B.tracked_files.cache_clear()


def main():
    test_small_helpers()
    test_rule_self_tests()
    test_provenance_grammar()
    test_excluded_lines()
    test_process()
    test_main()
    test_tracked_files()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
