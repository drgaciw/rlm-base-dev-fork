#!/usr/bin/env python3
"""Repair skill-discovery links that checked out as text stubs (A3).

`.claude/skills/*` and `.agents/skills/*` are git symlinks (mode 120000)
pointing at the canonical skill directories under `.cursor/skills/`. On a
Windows checkout with `core.symlinks=false` -- the default without Developer
Mode or an elevated `git clone` -- git checks each one out as a 30-45-byte
text file containing the link target instead of a real directory. Claude
Code and Codex then see zero of the repo's skills: an empty file with no
`SKILL.md` inside doesn't register as anything.

Real symlinks would need admin rights (or Developer Mode) to create on
Windows. Directory **junctions** (`mklink /J`) do not: `--fix` replaces each
stub with a junction on Windows and a real symlink everywhere else, then
marks the path `git update-index --skip-worktree` so the working-tree
directory doesn't show as a modification against the symlink git still
records in its index. That skip-worktree bit is local to this checkout --
it doesn't change what gets committed, and a fresh clone starts stubbed
again until it too runs `--fix`.

skip-worktree only covers the ~64 link entries themselves (mode-120000 paths
git already tracks); it says nothing about the files a junction's *target*
makes visible underneath it. Those are the canonical `.cursor/skills/**`
files reached through a second path, and to git's working-tree walk they
look like 168 brand-new untracked files (A-H2) -- `git add -A` could stage
duplicate copies of every skill. `--fix` also appends `EXCLUDE_ENTRIES` to
this checkout's local, never-committed `.git/info/exclude` (idempotently --
safe to run repeatedly) so those contents are excluded from `git status`
without touching what git tracks as the 64 real symlink entries.

`--check` reports any stub still present (exit 1) or confirms every
discovery entry resolves to a real directory (exit 0), without touching the
working tree. It is safe to run repeatedly and is what the SessionStart
hook uses to nudge a stale checkout -- it never blocks the session.

Usage:
  python scripts/ai/link_skills.py --check
  python scripts/ai/link_skills.py --fix
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DISCOVERY_DIRS = (".claude/skills", ".agents/skills")

# A-H2: excludes a junction's *contents* from `git status`, without touching the
# tracked 120000 symlink entries themselves (those are handled by skip-worktree,
# above). Written verbatim to `.git/info/exclude`.
EXCLUDE_ENTRIES = ("/.claude/skills/*/**", "/.agents/skills/*/**")


class ToolError(Exception):
    """A git invocation failed -- distinct from a stub finding."""


def _run(args, check=True, cwd=None):
    # cwd looked up at call time, not bound as a default -- a default of
    # `cwd=REPO_ROOT` would freeze in the value REPO_ROOT held when this module
    # was first imported, so a test that reassigns `link_skills.REPO_ROOT` to a
    # scratch repo would still run git against the real one.
    try:
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                              cwd=cwd or REPO_ROOT)
    except OSError as exc:
        raise ToolError(f"could not run {args[0]!r}: {exc}") from exc
    if check and proc.returncode != 0:
        raise ToolError(f"{' '.join(args)}\n{proc.stderr.strip()}")
    return proc.stdout


def discovery_links():
    """Repo-relative paths git records as symlinks (mode 120000) under the
    two discovery directories, in a stable sorted order.

    Sourced from git, not `os.listdir`, so an untracked sibling -- the
    GitNexus skill catalog at `.claude/skills/gitnexus/`, which is a real,
    already-a-directory entry and never a stub -- is never mistaken for one.
    """
    existing = [d for d in DISCOVERY_DIRS if os.path.isdir(os.path.join(REPO_ROOT, d))]
    if not existing:
        return []
    out = _run(["git", "ls-files", "-s", *existing])
    links = []
    for line in out.splitlines():
        mode, _, rest = line.partition(" ")
        if mode != "120000":
            continue
        path = rest.split("\t", 1)[1]
        links.append(path)
    return sorted(links)


def is_stub(rel_path):
    """True if `rel_path` checked out as a plain file rather than a directory."""
    return not os.path.isdir(os.path.join(REPO_ROOT, rel_path))


def _read_target(abs_path):
    with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read().strip()


def _link(abs_stub, abs_target):
    if os.name == "nt":
        # mklink is a cmd.exe builtin with DOS-style /switches, and it reads any
        # unquoted "/" in a path -- not just a leading one -- as a switch marker.
        # `.agents/skills/...` (git always uses forward slashes) trips this as
        # "Invalid switch - "skills"." normpath backslash-ifies it on Windows.
        abs_stub = os.path.normpath(abs_stub)
        abs_target = os.path.normpath(abs_target)
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", abs_stub, abs_target],
            capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            raise ToolError(
                f"mklink /J {abs_stub} {abs_target} failed:\n{proc.stdout}{proc.stderr}")
    else:
        os.symlink(abs_target, abs_stub, target_is_directory=True)


def fix(rel_path):
    """Replace one stub with a junction/symlink and mark it skip-worktree.

    Returns a one-line status. Raises ToolError if the stub's recorded
    target isn't a real directory -- creating a link to nothing would trade
    a loud, obvious failure (an empty stub file) for a silent one (a link
    that resolves to nothing).
    """
    abs_stub = os.path.join(REPO_ROOT, rel_path)
    target = _read_target(abs_stub)
    abs_target = os.path.normpath(os.path.join(os.path.dirname(abs_stub), target))
    if not os.path.isdir(abs_target):
        raise ToolError(
            f"{rel_path}: stub points at {target!r}, which resolves to "
            f"{abs_target}, not a directory -- not fixing")
    # The stub has to be removed before a junction/symlink can take its place --
    # there's no atomic swap. If linking then fails, restore the stub from git
    # rather than leaving the path missing entirely for whatever ran --fix next.
    os.remove(abs_stub)
    try:
        _link(abs_stub, abs_target)
    except ToolError:
        _run(["git", "checkout", "--", rel_path])
        raise
    _run(["git", "update-index", "--skip-worktree", rel_path])
    return f"{rel_path} -> {target}"


def _exclude_path():
    """This checkout's `.git/info/exclude`, resolved via git rather than a
    literal `.git/info/exclude` join under REPO_ROOT -- a worktree's `.git` is
    a *file* pointing at the real gitdir elsewhere, and `--git-common-dir`
    resolves through that to the one `info/exclude` shared by the whole repo.
    """
    git_dir = _run(["git", "rev-parse", "--git-common-dir"]).strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(REPO_ROOT, git_dir)
    return os.path.join(git_dir, "info", "exclude")


def _read_lines(path):
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [ln.rstrip("\n") for ln in fh]


def exclude_entries_present():
    """True if every EXCLUDE_ENTRIES pattern already exists as its own line."""
    lines = _read_lines(_exclude_path())
    return all(entry in lines for entry in EXCLUDE_ENTRIES)


def ensure_exclude_entries():
    """Idempotently append any missing EXCLUDE_ENTRIES line to `.git/info/exclude`.

    Returns True if the file was changed, False if every entry was already
    present. Never removes or reorders anything already there -- a developer's
    own local excludes are untouched.
    """
    path = _exclude_path()
    lines = _read_lines(path)
    missing = [entry for entry in EXCLUDE_ENTRIES if entry not in lines]
    if not missing:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        if lines and lines[-1] != "":
            fh.write("\n")
        fh.write("# rlm-base: skill-discovery junction contents (link_skills.py --fix, A-H2)\n")
        for entry in missing:
            fh.write(entry + "\n")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="report stub links; exit 1 if any remain")
    group.add_argument("--fix", action="store_true",
                       help="replace stubs with junctions/symlinks")
    args = ap.parse_args(argv)

    try:
        links = discovery_links()
    except ToolError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    if not links:
        print("no skill-discovery links found under "
              f"{', '.join(DISCOVERY_DIRS)}; nothing to do")
        return 0

    stubs = [p for p in links if is_stub(p)]

    if args.check:
        if not exclude_entries_present():
            print("warning: .git/info/exclude is missing the skill-discovery junction "
                  f"pattern(s) {', '.join(EXCLUDE_ENTRIES)} -- run --fix to add them, or "
                  "`git status -uall` may report every file inside a junction as untracked.")
        if not stubs:
            print(f"{len(links)}/{len(links)} skill-discovery links resolve to real directories")
            return 0
        for p in stubs:
            print(f"  stub  {p}")
        print(f"\n{len(stubs)} of {len(links)} skill-discovery links are text stubs, not "
              "directories -- Claude Code and other agents see zero content for them.")
        print("Fix: python scripts/ai/link_skills.py --fix")
        return 1

    if ensure_exclude_entries():
        print(f"  updated .git/info/exclude with {', '.join(EXCLUDE_ENTRIES)}")

    if not stubs:
        print(f"{len(links)}/{len(links)} skill-discovery links already resolve; nothing to fix")
        return 0

    failures = []
    for p in stubs:
        try:
            print(f"  fixed  {fix(p)}")
        except ToolError as exc:
            failures.append(str(exc))
            sys.stderr.write(f"  error: {exc}\n")

    fixed = len(stubs) - len(failures)
    print(f"\n{fixed}/{len(stubs)} stub(s) fixed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
