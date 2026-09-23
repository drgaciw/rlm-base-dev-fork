# Windows Developer Setup

Setting up a native Windows checkout of **rlm-base-dev** to run this repo's
Python test suites and `pr_gate.py` locally, without CumulusCI, `sf` CLI, or
a live org already installed. For the macOS/Linux equivalent, see the
[developer environment setup guide](dev-environment-setup.md); for the very
first install steps on any platform, see the
[local installation guide](local-installation.md).

This is a native Windows setup (PowerShell/cmd, no WSL). It exists because a
stock Windows checkout hits four things macOS/Linux do not:

1. Git checks skill symlinks out as text stubs instead of directories.
2. The default console codepage (cp1252, not UTF-8) crashes some
   `print()`/`subprocess` calls that assume UTF-8.
3. Nothing installs this repo's Python dev dependencies for you.
4. Claude Code's project hooks need Git Bash and a Python 3 that Git Bash
   can find (section 6).

---

## 1. Fix skill discovery (symlinks)

`.claude/skills/*` and `.agents/skills/*` are git symlinks pointing at the
canonical skill directories under `.cursor/skills/`. Git checks a tracked
symlink out as a real symlink only when both the repo and the checkout allow
it; on Windows that needs **either**:

- **Developer Mode** (Settings → Privacy & Security → For developers →
  Developer Mode) turned on *before* the clone, plus a `git clone`/`git config
  core.symlinks true` — real symlinks, no further steps needed — **or**
- **`python scripts/ai/link_skills.py --fix`** after any clone (no admin
  rights or Developer Mode needed). This replaces each stub with a directory
  **junction** (`mklink /J`) instead of a real symlink, and marks the path
  `git update-index --skip-worktree` so the working tree doesn't show as
  modified against the symlink git still records in its index.

Run `python scripts/ai/link_skills.py --check` first to confirm whether your
checkout needs it — see the "Claude Code specifics" section of `CLAUDE.md`.
If Claude Code or Codex reports zero skills, this is almost always why. A
fresh clone starts stubbed again until `--fix` runs there too.

---

## 2. Force UTF-8 mode

Set `PYTHONUTF8=1` in your shell (or persist it with `setx PYTHONUTF8 1` in a
new terminal) before running any of this repo's Python scripts or tests:

```powershell
$env:PYTHONUTF8 = "1"
```

```bash
# Git Bash
export PYTHONUTF8=1
```

Without it, Python's stdio and default text-mode file I/O fall back to the
Windows console codepage (cp1252 on most US/EU installs), not UTF-8. Several
of this repo's scripts and tests print or read non-ASCII characters (arrows,
warning signs, em-dashes, non-English sample data); under cp1252 those raise
`UnicodeDecodeError`/`UnicodeEncodeError` instead of running.
`PYTHONUTF8=1` is the same fix `scripts/lint/check_text_encoding.py` and
`pyproject.toml`'s `PLW1514` lint rule push individual `open()`/subprocess
calls toward doing explicitly (`encoding="utf-8"`); this env var covers what
isn't (or can't be) an explicit call, such as `print()` to the console.

---

## 3. Create a Python 3.11+ virtual environment

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
```

`py -3.11` (the Windows [`py` launcher](https://docs.python.org/3/using/windows.html#the-python-launcher-for-windows))
picks the 3.11 interpreter regardless of what `python` resolves to on `PATH`.
3.11+ is required: `pyproject.toml`'s `[tool.build_harness]` pins it
(`enum.StrEnum`), and `scripts/ai/analyze_agent_tooling.py` needs
`sys.stdlib_module_names` (3.10+).

---

## 4. Install dev dependencies

```powershell
pip install -r requirements-dev.txt
```

This installs CumulusCI, `setuptools` (pinned ahead of CumulusCI — see the
comment in `requirements-dev.txt` for why the order matters), `pytest`,
`textual`, `PyYAML`, and `ruff`, all pinned to the same versions CI and the
Docker build use.

---

## 5. Run the gate

```powershell
python scripts/ai/pr_gate.py --all
```

**Expected result once `requirements-dev.txt` is installed: 0 MISSING-DEP.**
Before this install step, `pr_gate.py --all` reports MISSING-DEP for every
check whose `deps` need a package from `scripts/ai/pr_gate.py`'s `DEPS` table
(`PyYAML`, `cumulusci`, `pytest`, `textual`, `requests` — the last comes in
transitively with CumulusCI) — that is expected on a bare checkout and is
**not** a FAIL. Wave-2 exit criterion ([architect review](../references/architect-review-2026-09.md) §6.C):
`pr_gate.py --all` reports 0 FAIL, with MISSING-DEP acceptable only on a
machine that has not run this guide's step 4.

A FAIL after installing `requirements-dev.txt` is a real regression, not a
missing-dependency artifact — see `REVIEW.md` and
`.cursor/skills/audit-review/merge-and-review-procedures.md` for how to
triage it.

---

## 6. Claude Code hooks: Git Bash and a Python 3 interpreter

`.claude/settings.json` registers two project hooks:

| Hook | Script | What it does |
|------|--------|--------------|
| `PreToolUse` (`Edit\|Write`) | `.claude/hooks/protect_generated.py` | Blocks hand-edits to generated output (`unpackaged/post_ux/`, `datasets/bre/`, `datasets/dx/`) |
| `SessionStart` | `.claude/hooks/session_start_skill_check.py` | One-line nudge when skill links are still stubs (section 1) |

Both run through `.claude/hooks/run_python.sh` in shell form with
`"shell": "bash"`, so on Windows they need **Git Bash**, which Git for
Windows installs by default. The launcher runs the first working
interpreter out of `python3`, `python`, and `py -3`, and tests that each
one actually starts before it uses it. That covers every common setup:

- **Microsoft Store Python** ships a `python3.exe` alias.
- **python.org installs** have no `python3.exe`, only `python.exe` (if you
  ticked "Add to PATH") and `py.exe`.
- **The Store `python3` alias with Store Python not installed** exits 9009
  instead of running, so the launcher skips it.

The launcher does not use exec form (`"command": "python3", "args": [...]`).
On Windows, exec form needs `command` to resolve to a real `.exe`, and
`python3.exe` exists only as the Store alias.

**If no interpreter works**, the protection is off, and Claude Code says so:

- Every Edit/Write shows a `PreToolUse hook error` notice saying the
  protect hook is **INACTIVE**.
- The session starts with a `WARNING:` line to the same effect.

Neither case blocks your work. To fix it, install Python 3 (step 3 is
enough if `python` is on `PATH` in Git Bash) or make sure `py.exe` is
reachable. Then check it from Git Bash:

```bash
echo '{"tool_input":{"file_path":"unpackaged/post_ux/x.xml"}}' \
  | bash .claude/hooks/run_python.sh protect_generated.py error; echo "exit=$?"
# expected: "Blocked: ..." and exit=2
```
