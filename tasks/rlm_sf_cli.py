"""Shared Salesforce CLI executable resolution for tasks/ (TP-13).

On native Windows the Salesforce CLI is installed as `sf.cmd`. `subprocess.run(["sf", ...])`
with list argv and `shell=False` does not consult PATHEXT the way a shell does, so the bare
name raises FileNotFoundError there (A-C2, docs/ARCHITECT_REVIEW.md WP-11). Use
`sf_executable()` as argv[0] for every `sf` subprocess call in this package. It has no
CumulusCI dependency, so it is safe to import before a module's CCI try/except.
"""
import shutil


def sf_executable() -> str:
    """Resolve the `sf` CLI executable path.

    `shutil.which("sf")` performs the PATHEXT-aware lookup and returns the real path
    (e.g. `...\\npm\\sf.cmd`). Falling back to the bare name keeps macOS/Linux unchanged,
    where the bare name resolves normally, and lets the caller's own missing-CLI handling
    (FileNotFoundError) fire when `sf` is genuinely not installed.
    """
    return shutil.which("sf") or "sf"
