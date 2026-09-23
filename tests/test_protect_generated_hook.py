#!/usr/bin/env python3
"""Offline fixtures for `.claude/hooks/protect_generated.py` (A-M4, wave 2).

Drives the hook's `main()` with a synthetic stdin payload -- the same JSON
shape claude-code-action sends a PreToolUse hook -- covering the path
spellings the prior implementation's repo-relative computation got wrong:
a relative `file_path`, an absolute one, a `cwd` that is a subdirectory of
the repo root (or absent entirely), `c:` vs `C:` drive-letter case, and an
MSYS/Git-Bash style `/c/Users/...` path.

Run: `python tests/test_protect_generated_hook.py` (offline, stdlib only).
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "hooks" / "protect_generated.py"

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


def load_module():
    spec = importlib.util.spec_from_file_location("protect_generated", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = load_module()


def run_hook(monkeypatch_input, monkeypatch_env=None):
    """Run `main()` with `monkeypatch_input` (a dict, or a raw string for the
    malformed-JSON case) fed as stdin, returning (exit_code, stderr_text).
    """
    old_stdin, old_stderr = sys.stdin, sys.stderr
    old_environ = dict(H.os.environ)
    try:
        payload = (monkeypatch_input if isinstance(monkeypatch_input, str)
                   else json.dumps(monkeypatch_input))
        sys.stdin = io.StringIO(payload)
        sys.stderr = io.StringIO()
        if monkeypatch_env is not None:
            H.os.environ.clear()
            H.os.environ.update(monkeypatch_env)
        rc = H.main()
        return rc, sys.stderr.getvalue()
    finally:
        sys.stdin, sys.stderr = old_stdin, old_stderr
        H.os.environ.clear()
        H.os.environ.update(old_environ)


def payload(file_path, cwd=None):
    d = {"tool_input": {"file_path": file_path}}
    if cwd is not None:
        d["cwd"] = cwd
    return d


# ---------------------------------------------------------------------------
# run_python.sh launcher (WP-17, wave 3)
# ---------------------------------------------------------------------------

LAUNCHER = REPO / ".claude" / "hooks" / "run_python.sh"
SETTINGS = REPO / ".claude" / "settings.json"


def find_bash():
    """Return (bash, tool_dir) for a POSIX bash, or None to skip.

    On Windows, deliberately use Git Bash (found relative to git.exe) rather
    than `shutil.which("bash")`, which can resolve to System32\\bash.exe --
    the WSL launcher, a different OS entirely. `tool_dir` supplies `dirname`
    to the restricted PATH the launcher runs under.
    """
    if os.name == "nt":
        git = shutil.which("git")
        if not git:
            return None
        # git.exe lives in <Git>/cmd or, on Git Bash's own PATH, <Git>/mingw64/bin.
        for root in Path(git).resolve().parents:
            bash = root / "bin" / "bash.exe"
            tools = root / "usr" / "bin"
            if bash.is_file() and tools.is_dir():
                return str(bash), str(tools)
        return None
    bash = shutil.which("bash")
    return (bash, "/usr/bin:/bin") if bash else None


def make_stub(directory, name, body):
    path = Path(directory) / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)


def run_launcher(bash, tool_dir, stub_dir, mode, stdin_text=""):
    env = dict(os.environ)
    # Stubs first so they shadow any real interpreter. Git Bash converts a
    # Windows-style `;` PATH to POSIX form on startup.
    env["PATH"] = os.pathsep.join([stub_dir, tool_dir])
    env["CLAUDE_PROJECT_DIR"] = str(REPO)
    proc = subprocess.run(
        [bash, str(LAUNCHER), "protect_generated.py", mode],
        input=stdin_text, capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def launcher_checks():
    print("\n-- settings.json wires both hooks through run_python.sh (shell form)")
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = [h for event in ("PreToolUse", "SessionStart")
             for group in settings["hooks"][event] for h in group["hooks"]]
    check("both hooks use shell form (no `args`: exec form needs a real .exe on Windows)",
          all("args" not in h for h in hooks), hooks)
    check("both hooks pin shell=bash",
          all(h.get("shell") == "bash" for h in hooks), hooks)
    check("both hooks go through run_python.sh",
          all("run_python.sh" in h["command"] for h in hooks), hooks)
    pre = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    start = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    check("PreToolUse uses `error` mode (visible hook error when no Python)",
          pre.endswith("protect_generated.py error"), pre)
    check("SessionStart uses `warn` mode (warning into context, never blocks)",
          start.endswith("session_start_skill_check.py warn"), start)

    found = find_bash()
    if not found:
        print("  [SKIP] launcher interpreter probing: no POSIX bash (Git Bash on Windows) found")
        return
    bash, tool_dir = found
    real = sys.executable.replace("\\", "/")
    works = f'exec "{real}" "$@"'
    broken = "exit 9009"  # what the Microsoft Store alias does when Store Python is absent
    blocked = json.dumps(payload("unpackaged/post_ux/foo.xml"))

    layouts = {
        "python3 only (stock macOS/Linux)": {"python3": works},
        "broken python3 alias + python (python.org on Windows)": {"python3": broken, "python": works},
        "only the py launcher (python.org, python not on PATH)": {
            "python3": broken, "python": broken,
            "py": f'[ "$1" = "-3" ] || exit 7\nshift\n{works}'},
    }
    print("\n-- run_python.sh finds a working interpreter in each layout")
    for label, stubs in layouts.items():
        with tempfile.TemporaryDirectory() as d:
            for name, body in stubs.items():
                make_stub(d, name, body)
            rc, out, err = run_launcher(bash, tool_dir, d, "error", blocked)
            check(f"{label}: the protect hook runs and blocks (exit 2)", rc == 2, (rc, out, err))

    print("\n-- run_python.sh with no working interpreter is visible, never blocking")
    with tempfile.TemporaryDirectory() as d:
        for name in ("python3", "python", "py"):
            make_stub(d, name, broken)
        rc, out, err = run_launcher(bash, tool_dir, d, "error", blocked)
        check("error mode exits 1 (a hook error, not a block)", rc == 1, (rc, out, err))
        check("...and says on stderr that the protect hook is INACTIVE", "INACTIVE" in err, err)
        rc, out, err = run_launcher(bash, tool_dir, d, "warn")
        check("warn mode exits 0", rc == 0, (rc, out, err))
        check("...and prints a WARNING on stdout for Claude's context",
              out.startswith("WARNING:") and "INACTIVE" in out, out)


def main() -> int:
    print("=" * 100)

    print("-- absolute Windows paths")
    rc, err = run_hook(payload(r"C:\Users\dev\rlm-base-dev-fork\unpackaged\post_ux\foo.xml"))
    check("absolute backslash path under unpackaged/post_ux is blocked", rc == 2, (rc, err))
    check("...and the reason names assemble_and_deploy_ux",
          "assemble_and_deploy_ux" in err, err)
    rc, err = run_hook(payload("C:/Users/dev/rlm-base-dev-fork/unpackaged/post_ux/foo.xml"))
    check("absolute forward-slash path under unpackaged/post_ux is blocked", rc == 2, (rc, err))

    print("\n-- drive-letter case (c: vs C:)")
    rc, err = run_hook(payload(r"c:\users\dev\rlm-base-dev-fork\unpackaged\post_ux\foo.xml"))
    check("lowercase drive letter still resolves and blocks", rc == 2, (rc, err))

    print("\n-- MSYS/Git-Bash style path")
    rc, err = run_hook(payload("/c/Users/dev/rlm-base-dev-fork/unpackaged/post_ux/foo.xml"))
    check("MSYS /c/... path is blocked", rc == 2, (rc, err))

    print("\n-- relative file_path + cwd")
    rc, err = run_hook(payload("unpackaged/post_ux/foo.xml",
                               cwd=r"C:\Users\dev\rlm-base-dev-fork"))
    check("relative path with cwd = repo root is blocked", rc == 2, (rc, err))

    print("\n-- relative file_path + a SUBDIRECTORY cwd")
    rc, err = run_hook(payload("unpackaged/post_ux/foo.xml",
                               cwd=r"C:\Users\dev\rlm-base-dev-fork\some\subdir"))
    check("relative path with a subdirectory cwd still resolves and blocks",
          rc == 2, (rc, err))

    print("\n-- relative file_path with NO cwd in the payload (CLAUDE_PROJECT_DIR fallback)")
    rc, err = run_hook(payload("unpackaged/post_ux/foo.xml"),
                       monkeypatch_env={"CLAUDE_PROJECT_DIR": r"C:\Users\dev\rlm-base-dev-fork"})
    check("CLAUDE_PROJECT_DIR is used when cwd is absent", rc == 2, (rc, err))

    print("\n-- relative file_path with NEITHER cwd NOR CLAUDE_PROJECT_DIR")
    rc, err = run_hook(payload("unpackaged/post_ux/foo.xml"), monkeypatch_env={})
    check("still blocks on the bare relative path (segments are still present)",
          rc == 2, (rc, err))

    print("\n-- the other two protected prefixes")
    rc, err = run_hook(payload(r"C:\repo\datasets\bre\export.json"))
    check("datasets/bre is blocked", rc == 2, (rc, err))
    check("...and the reason names export_bre_rule_library",
          "export_bre_rule_library" in err, err)
    rc, err = run_hook(payload(r"C:\repo\datasets\dx\extract.csv"))
    check("datasets/dx is blocked", rc == 2, (rc, err))

    print("\n-- case-insensitive segment matching")
    rc, err = run_hook(payload(r"C:\repo\Unpackaged\Post_UX\foo.xml"))
    check("mixed-case path segments still match", rc == 2, (rc, err))

    print("\n-- a path that merely CONTAINS the word is not a false positive")
    rc, err = run_hook(payload(r"C:\repo\my-unpackaged-notes\readme.md"))
    check("a directory named similarly but not exactly is not blocked", rc == 0, (rc, err))

    print("\n-- ordinary, unprotected paths are never blocked")
    rc, err = run_hook(payload(r"C:\repo\tasks\rlm_sfdmu.py"))
    check("an ordinary tracked source file is not blocked", rc == 0, (rc, err))

    print("\n-- malformed or missing input fails open (exit 0), never closed")
    rc, err = run_hook("not valid json{{{")
    check("malformed JSON on stdin exits 0", rc == 0, (rc, err))
    rc, err = run_hook({"tool_input": {}})
    check("a payload with no file_path exits 0", rc == 0, (rc, err))
    rc, err = run_hook({})
    check("a payload with no tool_input at all exits 0", rc == 0, (rc, err))

    launcher_checks()

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
