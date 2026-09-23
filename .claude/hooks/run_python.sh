#!/usr/bin/env bash
# Portable Python launcher for this directory's hooks (WP-17, wave 3).
#
# Usage (from .claude/settings.json, shell form with "shell": "bash"):
#   bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/run_python.sh" <hook.py> [error|warn]
#
# Why not exec form (`"command": "python3", "args": [...]`): on Windows, exec
# form requires `command` to resolve to a real .exe (code.claude.com hooks
# docs, "Exec form and shell form"). `python3.exe` exists only as the
# Microsoft Store alias; python.org installers ship `python.exe` and `py.exe`
# instead, and stock macOS/Linux often ship only `python3`. No single
# executable name works everywhere, so this script probes candidates in order.
#
# Each candidate is *run* (not just looked up) before it is trusted: the Store
# alias `python3` exists on PATH even when Store Python is not installed, and
# then exits 9009 instead of running anything.
#
# If nothing works, the failure is made visible rather than silent:
#   error (default, PreToolUse) -> message on stderr, exit 1: the transcript
#                                  shows a "<hook> hook error" notice.
#   warn  (SessionStart)        -> WARNING on stdout, exit 0: SessionStart
#                                  stdout is added to Claude's context.
# Neither mode exits 2, so a missing interpreter never blocks an edit.

hook_script="$(dirname "$0")/$1"
on_missing="${2:-error}"

for candidate in python3 python "py -3"; do
  # Intentional word-splitting: "py -3" becomes the command plus its flag.
  # shellcheck disable=SC2086
  set -- $candidate
  if command -v "$1" >/dev/null 2>&1 &&
     "$@" -c 'import sys; sys.exit(sys.version_info < (3, 8))' </dev/null >/dev/null 2>&1; then
    exec "$@" "$hook_script"
  fi
done

msg="no working Python 3 interpreter (tried python3, python, py -3) on PATH -- the protect_generated PreToolUse hook is INACTIVE, so do not hand-edit unpackaged/post_ux/, datasets/bre/ or datasets/dx/. See docs/guides/windows-dev-setup.md."
if [ "$on_missing" = "warn" ]; then
  echo "WARNING: $msg"
  exit 0
fi
echo "$msg" >&2
exit 1
