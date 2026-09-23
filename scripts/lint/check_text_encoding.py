#!/usr/bin/env python3
"""AST-based checker for text-mode I/O that relies on the locale encoding (I2).

Flags three call shapes, each only when there is no `encoding=` keyword:

  1. `open(...)` / `io.open(...)` / `<expr>.open(...)` (the builtin and
     `pathlib.Path.open`) in text mode -- no `mode` argument, or a `mode`
     whose string literal does not contain `"b"`.
  2. `Path.read_text(...)` / `Path.write_text(...)` with no `encoding`
     keyword and no positional argument covering that slot.
  3. Any call with a literal `text=True` or `universal_newlines=True`
     keyword (the `subprocess` text-mode switches) and no `encoding=`.

Ruff's preview `PLW1514` (unspecified-encoding) already covers case 1 and 2;
this script exists for case 3, which ruff does not check, and doubles as a
dependency-free, no-ruff-required gate for all three (`pyproject.toml`'s
`extend-select` enables `PLW1514`, but a machine without ruff installed still
needs a way to enforce this before `requirements-dev.txt` is set up).

Both a binary open (`"rb"`/`"wb"`/…) and an `encoding="locale"` call are
intentional and never flagged -- `encoding="locale"` is the documented way to
say "the platform locale is the point" rather than an oversight.

Usage:
  python scripts/lint/check_text_encoding.py [-v] [path ...]

Each `path` may be a `.py` file or a directory (walked recursively for
`*.py`, skipping `__pycache__`). With no paths, scans the whole repository.
Exit 0 with no findings, 1 otherwise. `-v` prints one line per finding
(`path:line: message`); without it, only the summary count is printed.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_OPEN_LIKE_NAMES = {"open"}
_TEXT_METHODS = {"read_text": 0, "write_text": 1}  # attr -> positional index of `encoding`
_SUBPROCESS_TEXT_KWARGS = {"text", "universal_newlines"}


class Finding:
    __slots__ = ("path", "line", "message")

    def __init__(self, path: Path, line: int, message: str):
        self.path = path
        self.line = line
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _kwarg(call: ast.Call, name: str) -> ast.keyword | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw
    return None


def _has_double_star(call: ast.Call) -> bool:
    # `open(path, **opts)` may already supply `encoding` -- can't prove it
    # doesn't, so don't flag rather than risk a false positive.
    return any(kw.arg is None for kw in call.keywords)


def _mode_is_binary(call: ast.Call, mode_index: int) -> bool:
    mode_node = None
    positional = [a for a in call.args if not isinstance(a, ast.Starred)]
    if len(positional) > mode_index:
        mode_node = positional[mode_index]
    else:
        mode_kw = _kwarg(call, "mode")
        if mode_kw is not None:
            mode_node = mode_kw.value
    if mode_node is None:
        return False
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return "b" in mode_node.value
    # Non-literal mode (a variable, an f-string, ...): can't prove binary,
    # so treat conservatively as text (i.e. still eligible to flag).
    return False


def _open_call_mode_index(call: ast.Call) -> int | None:
    """The positional index of the `mode` argument for this open-like call,
    or None if `call` isn't one.

    The builtin `open(file, mode=...)` and `io.open(file, mode=...)` take
    `mode` at index 1 (after `file`). A bound `.open()` method --
    `Path(...).open(mode=...)` or `some_path.open(mode=...)` -- has no `file`
    argument (the object it's called on IS the file), so `mode` is index 0
    there instead.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return 1 if func.id in _OPEN_LIKE_NAMES else None
    if isinstance(func, ast.Attribute):
        if func.attr != "open":
            return None
        return 1 if isinstance(func.value, ast.Name) and func.value.id == "io" else 0
    return None


def _is_text_method_call(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _TEXT_METHODS:
        return func.attr
    return None


def _has_subprocess_text_kwarg(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg in _SUBPROCESS_TEXT_KWARGS and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


def _check_call(call: ast.Call, path: Path) -> Finding | None:
    if _has_double_star(call):
        return None
    if _kwarg(call, "encoding") is not None:
        return None

    mode_index = _open_call_mode_index(call)
    if mode_index is not None:
        if _mode_is_binary(call, mode_index):
            return None
        return Finding(path, call.lineno,
                        "text-mode open() without encoding= (add encoding=\"utf-8\", "
                        "or encoding=\"locale\" if the locale is intended)")

    text_method = _is_text_method_call(call)
    if text_method is not None:
        encoding_index = _TEXT_METHODS[text_method]
        positional = [a for a in call.args if not isinstance(a, ast.Starred)]
        if len(positional) > encoding_index:
            return None  # encoding passed positionally
        return Finding(path, call.lineno,
                        f"Path.{text_method}() without encoding= (add encoding=\"utf-8\", "
                        "or encoding=\"locale\" if the locale is intended)")

    if _has_subprocess_text_kwarg(call):
        return Finding(path, call.lineno,
                        "subprocess call with text=True/universal_newlines=True but no "
                        "encoding= (add encoding=\"utf-8\", or encoding=\"locale\" if the "
                        "locale is intended)")
    return None


def check_source(source: str, path: Path) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [Finding(path, exc.lineno or 1, f"could not parse: {exc.msg}")]
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            finding = _check_call(node, path)
            if finding is not None:
                findings.append(finding)
    findings.sort(key=lambda f: f.line)
    return findings


def check_file(path: Path) -> list[Finding]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    return check_source(source, path)


def iter_python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_file():
            if p.suffix == ".py":
                files.append(p)
        elif p.is_dir():
            for candidate in sorted(p.rglob("*.py")):
                if "__pycache__" in candidate.parts:
                    continue
                files.append(candidate)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=["."],
                     help="files or directories to scan (default: repo root)")
    ap.add_argument("-v", "--verbose", action="store_true",
                     help="print one line per finding, not just the summary")
    args = ap.parse_args(argv)

    roots = []
    for raw in args.paths:
        p = Path(raw)
        roots.append(p if p.is_absolute() else (REPO_ROOT / p))

    all_findings: list[Finding] = []
    for path in iter_python_files(roots):
        all_findings.extend(check_file(path))

    if args.verbose:
        for finding in all_findings:
            try:
                rel = finding.path.relative_to(REPO_ROOT)
            except ValueError:
                rel = finding.path
            print(f"{rel}:{finding.line}: {finding.message}")

    if all_findings:
        print(f"{len(all_findings)} text-mode I/O call(s) without an explicit encoding "
              f"(rerun with -v for details)")
        return 1
    print("0 findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
