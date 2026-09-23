#!/usr/bin/env python3
"""Offline fixtures for `check_no_gitnexus_injection` (I1, wave 2, A-L6/B10).

GitNexus's `analyze` command injects a skill-discovery block into
CLAUDE.md/AGENTS.md and copies its own skill catalog into
`.claude/skills/gitnexus/` unless told not to (`--skip-agents-md
--skip-skills`, or the committed root `.gitnexusrc`). This suite drives the
analyzer's backstop check directly against synthetic git repos -- never this
checkout's real CLAUDE.md/AGENTS.md/.claude/skills/, which stay clean only
because `.gitnexusrc` is honored, not because the check enforces it in this
process.

Run: `python tests/test_gitnexus_guard.py` (offline, no org; needs `git` on PATH).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "ai"))
import analyze_agent_tooling as analyzer  # noqa: E402

_passed = 0
_failed: list[str] = []


def check(name, condition, detail=""):
    global _passed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed.append(f"{name}: {detail}")
        print(f"  [FAIL] {name}  {detail}")


def _git(root, *args):
    proc = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def _repo(claude_body="@AGENTS.md\n", agents_body="# Agent instructions\n",
          gitnexus_skill_file=None):
    """A throwaway git repo with CLAUDE.md/AGENTS.md and, optionally, a
    tracked file under `.claude/skills/gitnexus/` (the injected-and-committed
    shape the check must catch).
    """
    root = Path(tempfile.mkdtemp(prefix="gitnexus_guard_test_"))
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "CLAUDE.md").write_text(claude_body, encoding="utf-8")
    (root / "AGENTS.md").write_text(agents_body, encoding="utf-8")
    _git(root, "add", "CLAUDE.md", "AGENTS.md")
    if gitnexus_skill_file is not None:
        target = root / ".claude" / "skills" / "gitnexus" / gitnexus_skill_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("injected content\n", encoding="utf-8")
        _git(root, "add", str(target.relative_to(root)))
    _git(root, "commit", "-q", "-m", "seed")
    return root


def main() -> int:
    print("=" * 100)

    print("-- a clean repo (no injection) passes")
    root = _repo()
    result = analyzer.check_no_gitnexus_injection(root)
    check("clean CLAUDE.md/AGENTS.md and no tracked gitnexus skill dir passes",
          result.ok, result.detail)
    check("...and the detail names both things it checked",
          "gitnexus:start" in result.detail and ".claude/skills/gitnexus" in result.detail,
          result.detail)

    print("\n-- an injected block in CLAUDE.md fails")
    root = _repo(claude_body="@AGENTS.md\n\n<!-- gitnexus:start -->\nstuff\n<!-- gitnexus:end -->\n")
    result = analyzer.check_no_gitnexus_injection(root)
    check("CLAUDE.md carrying the marker fails", not result.ok, result.detail)
    check("...and the failure names CLAUDE.md", "CLAUDE.md" in result.detail, result.detail)

    print("\n-- an injected block in AGENTS.md fails")
    root = _repo(agents_body="# Agent instructions\n\ngitnexus:start\nstuff\n")
    result = analyzer.check_no_gitnexus_injection(root)
    check("AGENTS.md carrying the marker fails", not result.ok, result.detail)
    check("...and the failure names AGENTS.md", "AGENTS.md" in result.detail, result.detail)

    print("\n-- a tracked file under .claude/skills/gitnexus/ fails")
    root = _repo(gitnexus_skill_file="SKILL.md")
    result = analyzer.check_no_gitnexus_injection(root)
    check("a tracked gitnexus skill file fails", not result.ok, result.detail)
    check("...and the failure names the tracked path",
          ".claude/skills/gitnexus" in result.detail, result.detail)
    check("...and it gives a remediation pointing at .gitnexusrc",
          ".gitnexusrc" in result.detail, result.detail)

    print("\n-- an UNTRACKED gitnexus skill dir (a local `gitnexus analyze` run, "
          "never staged) is not a finding")
    root = _repo()
    untracked = root / ".claude" / "skills" / "gitnexus" / "SKILL.md"
    untracked.parent.mkdir(parents=True, exist_ok=True)
    untracked.write_text("local, never committed\n", encoding="utf-8")
    result = analyzer.check_no_gitnexus_injection(root)
    check("an untracked local gitnexus skill catalog does not fail the check",
          result.ok, result.detail)

    print("\n" + "=" * 100)
    total = _passed + len(_failed)
    if _failed:
        for label in _failed:
            print(f"FAILED: {label}")
        print(f"\n{_passed}/{total} checks passed")
        return 1
    print(f"{total}/{total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
