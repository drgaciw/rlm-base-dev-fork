#!/usr/bin/env python3
"""Unit tests for scripts/lint/check_text_encoding.py (I2, WP-14 AC2).

Self-contained -- no pytest required (matches this repo's lightweight test
convention). Run from the repo root with base Python:

    python tests/test_check_text_encoding.py

Exits 0 when all checks pass, 1 otherwise.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lint"))

import check_text_encoding as C  # noqa: E402

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")


def findings(source):
    """Findings for a fragment of source, as (line, message) pairs."""
    tree_path = Path("fragment.py")
    return [(f.line, f.message) for f in C.check_source(source, tree_path)]


def test_open_flagged_and_cleared():
    check("bare open() with no args flagged",
          len(findings('open("x")')) == 1)
    check("open() with mode='r' flagged",
          len(findings('open("x", "r")')) == 1)
    check("open() with mode='w' flagged",
          len(findings('open("x", mode="w")')) == 1)
    check("open() in binary mode ('rb') NOT flagged",
          findings('open("x", "rb")') == [])
    check("open() in binary mode ('wb') NOT flagged",
          findings('open("x", mode="wb")') == [])
    check("open() with encoding= NOT flagged",
          findings('open("x", "r", encoding="utf-8")') == [])
    check("open() with encoding=\"locale\" NOT flagged",
          findings('open("x", encoding="locale")') == [])
    check("io.open() without encoding= flagged",
          len(findings('io.open("x", "w")')) == 1)
    check("io.open() with encoding= NOT flagged",
          findings('io.open("x", "w", encoding="utf-8")') == [])
    check("open() with **kwargs is not flagged (cannot prove encoding is absent)",
          findings('open("x", **opts)') == [])


def test_path_open_flagged_and_cleared():
    check("Path(...).open() without encoding= flagged",
          len(findings('Path("x").open("w")')) == 1)
    check("some_path.open() without encoding= flagged",
          len(findings('p.open("w")')) == 1)
    check("Path(...).open() with encoding= NOT flagged",
          findings('Path("x").open("w", encoding="utf-8")') == [])
    check("Path(...).open() in binary mode NOT flagged",
          findings('Path("x").open("rb")') == [])


def test_read_write_text():
    check("Path.read_text() with no args flagged",
          len(findings('p.read_text()')) == 1)
    check("Path.read_text(encoding=...) NOT flagged",
          findings('p.read_text(encoding="utf-8")') == [])
    check("Path.read_text(\"utf-8\") positional NOT flagged (covers the slot)",
          findings('p.read_text("utf-8")') == [])
    check("Path.write_text(data) with no encoding flagged",
          len(findings('p.write_text(data)')) == 1)
    check("Path.write_text(data, encoding=...) NOT flagged",
          findings('p.write_text(data, encoding="utf-8")') == [])
    check("Path.write_text(data, \"utf-8\") positional NOT flagged (covers the slot)",
          findings('p.write_text(data, "utf-8")') == [])


def test_subprocess_text_kwargs():
    check("subprocess.run(text=True) without encoding= flagged",
          len(findings('subprocess.run(cmd, text=True)')) == 1)
    check("subprocess.run(universal_newlines=True) without encoding= flagged",
          len(findings('subprocess.run(cmd, universal_newlines=True)')) == 1)
    check("subprocess.run(text=True, encoding=...) NOT flagged",
          findings('subprocess.run(cmd, text=True, encoding="utf-8")') == [])
    check("subprocess.run(text=True, encoding=\"locale\") NOT flagged",
          findings('subprocess.run(cmd, text=True, encoding="locale")') == [])
    check("subprocess.run() with neither text= nor universal_newlines= NOT flagged",
          findings('subprocess.run(cmd, capture_output=True)') == [])
    check("text=False (binary mode requested explicitly) NOT flagged",
          findings('subprocess.run(cmd, text=False)') == [])
    check("a call with an unrelated 'text' kwarg NOT flagged (name shared, not a bool)",
          findings('render(text="hello")') == [])


def test_multiple_findings_and_ordering():
    src = 'open("a")\nopen("b", encoding="utf-8")\nsubprocess.run(c, text=True)\n'
    got = findings(src)
    check("two findings across three calls, in source order",
          [line for line, _ in got] == [1, 3])


def test_syntax_error_reported_not_raised():
    got = findings("def broken(:\n")
    check("a syntax error is reported as a finding, not raised",
          len(got) == 1 and "could not parse" in got[0][1])


def test_iter_python_files_skips_pycache():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "a.cpython-311.pyc.py").write_text("x = 1\n", encoding="utf-8")
        (root / "not_python.txt").write_text("open('x')\n", encoding="utf-8")
        files = C.iter_python_files([root])
        check("only real .py files outside __pycache__ are scanned",
              [p.name for p in files] == ["a.py"])


def test_cli_exit_codes_and_verbose_output():
    with tempfile.TemporaryDirectory() as td:
        clean = Path(td) / "clean.py"
        clean.write_text('open("x", encoding="utf-8")\n', encoding="utf-8")
        dirty = Path(td) / "dirty.py"
        dirty.write_text('open("x")\n', encoding="utf-8")

        clean_proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint" / "check_text_encoding.py"), str(clean)],
            capture_output=True, text=True, encoding="utf-8")
        check("clean file: exit 0", clean_proc.returncode == 0)

        dirty_proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint" / "check_text_encoding.py"), str(dirty)],
            capture_output=True, text=True, encoding="utf-8")
        check("dirty file: exit 1", dirty_proc.returncode == 1)
        check("dirty file without -v: no per-line detail", "dirty.py:1:" not in dirty_proc.stdout)

        verbose_proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint" / "check_text_encoding.py"), "-v", str(dirty)],
            capture_output=True, text=True, encoding="utf-8")
        check("dirty file with -v: exit 1", verbose_proc.returncode == 1)
        check("dirty file with -v: per-line detail present",
              "dirty.py:1:" in verbose_proc.stdout)

        dir_proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "lint" / "check_text_encoding.py"), "-v", str(Path(td))],
            capture_output=True, text=True, encoding="utf-8")
        check("scanning a directory finds the dirty file inside it",
              "dirty.py:1:" in dir_proc.stdout)
        check("scanning a directory does not flag the already-clean file",
              "clean.py:1:" not in dir_proc.stdout)


def main():
    test_open_flagged_and_cleared()
    test_path_open_flagged_and_cleared()
    test_read_write_text()
    test_subprocess_text_kwargs()
    test_multiple_findings_and_ordering()
    test_syntax_error_reported_not_raised()
    test_iter_python_files_skips_pycache()
    test_cli_exit_codes_and_verbose_output()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
