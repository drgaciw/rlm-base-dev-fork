#!/usr/bin/env python3
"""Does `link_skills.py` find stubs, fix them, and stay idempotent (WP-03 #9)?

Builds a throwaway git repo per case -- never the real checkout -- with a
skill-discovery entry registered as a git symlink (mode 120000) via
`git hash-object` / `git update-index --cacheinfo`, exactly as `.claude/skills/*`
is recorded here, but checked out as a plain stub *file*, exactly what a
Windows clone with `core.symlinks=false` produces regardless of the actual
`core.symlinks` value on the machine running this test. That's the shape A3
describes and the one `--fix` exists to repair.

Run: `python tests/test_link_skills.py` (offline, no org; needs `git` on PATH).
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "ai" / "link_skills.py"


def load_module():
    spec = importlib.util.spec_from_file_location("link_skills", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = load_module()


def _git(root, *args):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def _init_repo(root):
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")


def _register_stub(root, rel_link, rel_target):
    """Record `rel_link` as a git symlink (mode 120000) pointing at `rel_target`,
    then check it out as a plain stub file -- the Windows shape -- regardless
    of this machine's own core.symlinks. Mirrors what `git hash-object -w` /
    `git update-index --cacheinfo` do for a real symlink blob, without ever
    calling `os.symlink` (which `core.symlinks=false` would silently downgrade
    on checkout anyway, masking the very case under test).
    """
    link_abs = pathlib.Path(root) / rel_link
    link_abs.parent.mkdir(parents=True, exist_ok=True)
    link_abs.write_text(rel_target, encoding="utf-8")
    sha = _git(root, "hash-object", "-w", "--stdin", "--path", rel_link).strip()
    # A prior write_text() above lets `git hash-object --path` infer text mode
    # consistently across platforms; the recorded blob content is `rel_target`
    # either way since hash-object reads the file we just wrote.
    _git(root, "update-index", "--add", "--cacheinfo", f"120000,{sha},{rel_link}")


def _make_repo(with_target=True):
    root = tempfile.mkdtemp(prefix="link_skills_test_")
    _init_repo(root)
    os.makedirs(os.path.join(root, ".claude", "skills"), exist_ok=True)
    if with_target:
        target_dir = os.path.join(root, ".cursor", "skills", "widget-skill")
        os.makedirs(target_dir, exist_ok=True)
        pathlib.Path(target_dir, "SKILL.md").write_text(
            "---\nname: widget-skill\n---\n", encoding="utf-8")
    _register_stub(root, ".claude/skills/widget-skill", "../../.cursor/skills/widget-skill")
    # Committed, not left staged: in the real repo these links are already part
    # of history, and skip-worktree only hides a worktree-vs-index difference --
    # an uncommitted "A " (added) status would remain regardless of it.
    _git(root, "commit", "--quiet", "-m", "register widget-skill stub")
    return root


def _cleanup(root):
    shutil.rmtree(root, ignore_errors=True)


def _discovery_case(fn):
    root = _make_repo()
    try:
        L.REPO_ROOT = root
        return fn(root)
    finally:
        L.REPO_ROOT = str(REPO)
        _cleanup(root)


DISCOVERY = [
    ("discovery_links() finds the registered mode-120000 entry",
     [".claude/skills/widget-skill"],
     _discovery_case(lambda root: L.discovery_links())),
    ("a freshly checked-out registration is a stub (plain file, not a dir)",
     True,
     _discovery_case(lambda root: L.is_stub(".claude/skills/widget-skill"))),
]

CHECK_EXIT = [
    ("--check exits 1 when a stub is present",
     1,
     _discovery_case(lambda root: L.main(["--check"]))),
]


def _fix_then(fn):
    def run(root):
        fixed = L.fix(".claude/skills/widget-skill")
        return fn(root, fixed)
    return _discovery_case(run)


FIX_AND_IDEMPOTENCY = [
    ("fix() turns the stub into a real, resolving directory",
     False,
     _fix_then(lambda root, fixed: L.is_stub(".claude/skills/widget-skill"))),
    ("...and the linked directory's content is reachable through it",
     True,
     _fix_then(lambda root, fixed: os.path.isfile(
         os.path.join(root, ".claude/skills/widget-skill", "SKILL.md")))),
    ("...and fix()'s return value names the link and its target",
     True,
     _fix_then(lambda root, fixed: "widget-skill" in fixed and "->" in fixed)),
    ("--check is idempotent: exits 0 once every entry resolves",
     0,
     _fix_then(lambda root, fixed: L.main(["--check"]))),
    ("--fix is idempotent: a second run finds nothing left to fix",
     0,
     _fix_then(lambda root, fixed: L.main(["--fix"]))),
    ("skip-worktree is set after fix(), so git sees no working-tree diff",
     "",
     _fix_then(lambda root, fixed: _git(root, "status", "--porcelain",
                                       ".claude/skills/widget-skill").strip())),
]


def _broken_target_case(fn):
    root = tempfile.mkdtemp(prefix="link_skills_test_")
    try:
        _init_repo(root)
        os.makedirs(os.path.join(root, ".claude", "skills"), exist_ok=True)
        # No .cursor/skills/widget-skill directory is created -- the stub
        # names a target that does not exist.
        _register_stub(root, ".claude/skills/widget-skill", "../../.cursor/skills/widget-skill")
        _git(root, "commit", "--quiet", "-m", "register widget-skill stub")
        L.REPO_ROOT = root
        return fn(root)
    finally:
        L.REPO_ROOT = str(REPO)
        _cleanup(root)


def _fix_missing_target(root):
    """Attempt fix() against a stub whose target doesn't exist.

    Returns (raised_tool_error, stub_still_present_afterward).
    """
    try:
        L.fix(".claude/skills/widget-skill")
        raised = False
    except L.ToolError:
        raised = True
    still_there = os.path.isfile(os.path.join(root, ".claude/skills/widget-skill"))
    return raised, still_there


_MISSING_TARGET_RESULT = _broken_target_case(_fix_missing_target)

MISSING_TARGET = [
    ("fix() refuses to link a stub whose target directory does not exist",
     True, _MISSING_TARGET_RESULT[0]),
    ("...and leaves the stub file in place rather than deleting it with nothing to replace it",
     True, _MISSING_TARGET_RESULT[1]),
]


def _exclude_case(fn):
    """Like `_discovery_case`, but git-initialized only -- no widget-skill stub
    needed, since EXCLUDE_ENTRIES behavior is independent of any registered link.
    """
    root = tempfile.mkdtemp(prefix="link_skills_test_")
    try:
        _init_repo(root)
        os.makedirs(os.path.join(root, ".claude", "skills"), exist_ok=True)
        target_dir = os.path.join(root, ".cursor", "skills", "widget-skill")
        os.makedirs(target_dir, exist_ok=True)
        pathlib.Path(target_dir, "SKILL.md").write_text(
            "---\nname: widget-skill\n---\n", encoding="utf-8")
        _register_stub(root, ".claude/skills/widget-skill", "../../.cursor/skills/widget-skill")
        _git(root, "commit", "--quiet", "-m", "register widget-skill stub")
        L.REPO_ROOT = root
        return fn(root)
    finally:
        L.REPO_ROOT = str(REPO)
        _cleanup(root)


def _exclude_lines(root):
    exclude_path = os.path.join(root, ".git", "info", "exclude")
    if not os.path.isfile(exclude_path):
        return []
    return pathlib.Path(exclude_path).read_text(encoding="utf-8").splitlines()


EXCLUDE_ENTRIES = [
    ("exclude_entries_present() is False before --fix has ever run",
     False, _exclude_case(lambda root: L.exclude_entries_present())),
    ("--fix appends both EXCLUDE_ENTRIES patterns to .git/info/exclude",
     True, _exclude_case(lambda root: (L.main(["--fix"]), L.exclude_entries_present())[1])),
    ("...and every configured pattern is a line in the file, verbatim",
     True, _exclude_case(lambda root: (
         L.main(["--fix"]),
         all(entry in _exclude_lines(root) for entry in L.EXCLUDE_ENTRIES))[1])),
    ("a second --fix does not duplicate the lines (idempotent)",
     1, _exclude_case(lambda root: (
         L.main(["--fix"]), L.main(["--fix"]),
         _exclude_lines(root).count(L.EXCLUDE_ENTRIES[0]))[2])),
    ("ensure_exclude_entries() reports False (no change) once entries already exist",
     False, _exclude_case(lambda root: (
         L.ensure_exclude_entries(), L.ensure_exclude_entries())[1])),
    ("a pre-existing, unrelated exclude line survives --fix untouched",
     True, _exclude_case(lambda root: (
         pathlib.Path(root, ".git", "info", "exclude").write_text(
             "/some-local-scratch/\n", encoding="utf-8"),
         L.main(["--fix"]),
         "/some-local-scratch/" in _exclude_lines(root))[2])),
]


def _empty_repo_check():
    root = tempfile.mkdtemp(prefix="link_skills_test_")
    try:
        _init_repo(root)  # no .claude/skills or .agents/skills at all
        L.REPO_ROOT = root
        return L.main(["--check"])
    finally:
        L.REPO_ROOT = str(REPO)
        _cleanup(root)


NO_DISCOVERY_DIRS = [
    ("main() with no .claude/skills or .agents/skills present exits 0 (nothing to do)",
     0, _empty_repo_check()),
]


def main() -> int:
    failures = []
    all_cases = [
        ("discovery_links() and is_stub() read a freshly checked-out registration", DISCOVERY),
        ("--check reports the stub", CHECK_EXIT),
        ("fix() links a stub and stays idempotent", FIX_AND_IDEMPOTENCY),
        ("fix() refuses a stub whose target is missing", MISSING_TARGET),
        ("--fix appends the junction-content exclude patterns (A-H2)", EXCLUDE_ENTRIES),
        ("main() is a no-op when neither discovery dir exists", NO_DISCOVERY_DIRS),
    ]
    print("=" * 100)
    for group, cases in all_cases:
        print(f"-- {group}")
        for label, expected, actual in cases:
            ok = actual == expected
            if not ok:
                failures.append(label)
            print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
            if not ok:
                print(f"         expected={expected!r}, got={actual!r}")
    print("=" * 100)
    total = sum(len(c) for _, c in all_cases)
    if failures:
        for label in failures:
            print(f"FAILED: {label}")
        print(f"\n{total - len(failures)}/{total} checks passed")
        return 1
    print(f"{total}/{total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
