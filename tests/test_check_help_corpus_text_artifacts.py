#!/usr/bin/env python3
"""Unit tests for scripts/ai/check_help_corpus_text_artifacts.py (TP-10b).

The script spot-checks the captured Salesforce Help corpus (`docs/salesforce/*/help/articles/*.md`)
for a link-intro verb glued to the next word ("SeeCreate a Constant Resource"). It is a spot check,
not a gate -- a hit means "go look" -- so what matters is that the pattern flags what it should,
does NOT flag the identifiers its comment says it must spare ("AddGroup", "CreateRampSchedule"),
reports real line numbers, scans every release's corpus, and always exits 0.

The corpus is rebuilt in a temp directory and `REPO_ROOT` is pointed at it, so the checks neither
depend on nor are disturbed by whatever the committed snapshots contain.

Self-contained -- no pytest:

    python tests/test_check_help_corpus_text_artifacts.py

Exits 0 when every check passes, 1 otherwise.
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai"))

import check_help_corpus_text_artifacts as C  # noqa: E402

RESULTS = []


def _ascii(text):
    """stdout may be cp1252 (Windows, PYTHONUTF8 unset); never let a check name crash the run."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(_ascii(f"  [{'PASS' if condition else 'FAIL'}] {name}"
                 + ("" if condition or detail == "" else f": {detail}")))


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def run_main(root):
    """(exit code, stdout) of C.main() with REPO_ROOT pointed at `root`."""
    saved = C.REPO_ROOT
    C.REPO_ROOT = Path(root)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = C.main()
    finally:
        C.REPO_ROOT = saved
    return code, out.getvalue()


def snippets(text):
    return [m.group(0) for m in C.GLUED_LINK_RE.finditer(text)]


def test_pattern():
    print("\nGLUED_LINK_RE: what is and is not flagged")
    check("each link-intro verb glued to a capitalised word is flagged",
          snippets("SeeCreate a rating. ClickSave. SelectOption. ViewDetails.")
          == ["SeeCreate", "ClickSave", "SelectOption", "ViewDetails"],
          snippets("SeeCreate a rating. ClickSave. SelectOption. ViewDetails."))
    check("'Refer to' glued to the next word is flagged, keeping the multi-word verb",
          snippets("Refer toCreate a Constant Resource.") == ["Refer toCreate"])
    check("a correctly spaced link intro is not flagged",
          snippets("See Create a Constant Resource. Click Save. Refer to Create.") == [])
    check("the API identifiers the docstring says to spare are not flagged",
          snippets("AddGroup CreateRampSchedule UseCase EnableFlag") == [])
    check("a verb inside a longer word is not flagged (word boundary before the verb)",
          snippets("Foresee ReselectOption Preview") == [])
    check("a lower-case continuation is ordinary prose, not a glue artifact",
          snippets("Seeing Selection Viewer Clicking") == [])


def test_find_artifacts():
    print("\nfind_artifacts: line numbers and files")
    with tempfile.TemporaryDirectory() as tmp:
        one = write(tmp, "one.md", "line one\nsecond line: SeeCreate a rating\n\nClickSave now\n")
        two = write(tmp, "two.md", "all clean here\n")
        found = C.find_artifacts([one, two])
    check("every hit is (path, 1-based line, matched text) in file order",
          found == [(one, 2, "SeeCreate"), (one, 4, "ClickSave")], found)
    check("a clean file contributes nothing", all(p != two for p, _, _ in found))
    check("no paths is no findings", C.find_artifacts([]) == [])
    with tempfile.TemporaryDirectory() as tmp:
        blank = write(tmp, "blank.md", "")
        check("an empty file is fine", C.find_artifacts([blank]) == [])
        crlf = write(tmp, "crlf.md", "a\r\nb SeeCreate\r\n")
        check("CRLF text still counts lines correctly", C.find_artifacts([crlf])[0][1] == 2)


def test_main_no_corpus():
    print("\nmain(): nothing to scan")
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "docs/salesforce/264/help/other/not-an-article.md", "SeeCreate\n")
        code, out = run_main(tmp)
    check("no matching corpus files exits 0 and says which glob matched nothing",
          code == 0 and f"No corpus files matched {C.CORPUS_GLOB}" in out, out)
    check("only docs/salesforce/*/help/articles/*.md is scanned",
          "not-an-article" not in out)


def test_main_clean():
    print("\nmain(): a clean corpus")
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "docs/salesforce/264/help/articles/a.md", "See Create a rating.\n")
        write(tmp, "docs/salesforce/264/help/articles/b.md", "Nothing to see.\n")
        code, out = run_main(tmp)
    check("a clean corpus exits 0 and reports the article count",
          code == 0 and "Scanned 2 article(s); 0 glued-link artifacts found." in out, out)


def test_main_findings():
    print("\nmain(): hits are reported, never failed")
    with tempfile.TemporaryDirectory() as tmp:
        write(tmp, "docs/salesforce/264/help/articles/rating.md", "intro\nSeeCreate a Constant Resource.\n")
        write(tmp, "docs/salesforce/262/help/articles/old.md", "ClickSave the file\n")
        write(tmp, "docs/salesforce/264/help/articles/fine.md", "See Create.\n")
        code, out = run_main(tmp)
    check("a corpus with hits still exits 0 (spot-check, not a gate)", code == 0, out)
    check("the report counts articles and findings",
          "Scanned 3 article(s); 2 glued-link artifact(s) found:" in out, out)
    check("each hit is listed as a repo-relative path:line with the matched text",
          "docs/salesforce/264/help/articles/rating.md:2: 'SeeCreate'" in out.replace("\\", "/")
          and "docs/salesforce/262/help/articles/old.md:1: 'ClickSave'" in out.replace("\\", "/"), out)
    check("frozen releases are scanned too, and the closing guidance says not to hand-fix them",
          "docs/salesforce/262" in out.replace("\\", "/") and "frozen snapshots" in out, out)
    lines = [ln for ln in out.replace("\\", "/").splitlines() if ln.startswith("  docs/")]
    check("hits come out sorted by path (262 before 264)", lines == sorted(lines), lines)


def test_real_corpus_glob():
    print("\ncommitted corpus")
    articles = sorted(REPO_ROOT.glob(C.CORPUS_GLOB))
    check("the glob still matches the committed Help snapshot layout (else the spot-check goes blind)",
          len(articles) > 0, C.CORPUS_GLOB)
    code, out = run_main(REPO_ROOT)
    check("running it against the real corpus exits 0", code == 0, out[-300:])


def main():
    test_pattern()
    test_find_artifacts()
    test_main_no_corpus()
    test_main_clean()
    test_main_findings()
    test_real_corpus_glob()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
