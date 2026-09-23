#!/usr/bin/env python3
"""SessionStart hook: nudge a stale Windows checkout without ever blocking.

Delegates the real check to `scripts/ai/link_skills.py --check` and reduces
whatever it finds to a single line. SessionStart hook stdout becomes
additionalContext loaded into every session (hooks docs), so dumping that
script's full per-link listing -- 64 lines on this repo -- into every
session before a stale checkout has run `--fix` once would be pure token
waste for what has a one-command remedy.

Always exits 0, regardless of `--check`'s own exit code (1 when stubs
remain) or of the script being missing entirely. A stale skill link is a
convenience nudge, not a reason to interrupt anyone's session -- only the
PreToolUse hook in this package is meant to block anything.
"""
from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    script = os.path.join(project_dir, "scripts", "ai", "link_skills.py")
    if not os.path.isfile(script):
        return 0
    try:
        proc = subprocess.run([sys.executable, script, "--check"],
                               capture_output=True, text=True, encoding="utf-8",
                               cwd=project_dir)
    except OSError:
        return 0
    if proc.returncode != 0:
        print("Skill links are stubs on this checkout (Windows symlink limitation) -- "
              "run `python scripts/ai/link_skills.py --fix` to see the repo's skills.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
