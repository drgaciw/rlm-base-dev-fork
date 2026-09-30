#!/usr/bin/env python3
"""Unit tests for scripts/ai/validate_expression_set.py (TP-10b).

The script is a thin CLI over `tasks/expression_set_schema.py` (whose rules are covered by
tests/test_expression_set_schema.py): it picks the validation kind, prints the report and maps the
result onto an exit code that CI and the `apply_expression_set_overlay` pre-flight rely on:

    0 no errors (and no warnings under --strict)   1 validation failed   2 bad invocation

Those exit codes, the kind auto-detection and the unreadable-input paths are what this file pins.
Everything runs offline against hand-built files in a temp directory (plus the committed export
fixture, so a real definition is exercised too); the schema module is stdlib-only, so this suite
needs no third-party package.

Self-contained -- no pytest:

    python tests/test_validate_expression_set.py

Exits 0 when every check passes, 1 otherwise.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai"))

import validate_expression_set as V  # noqa: E402

EXPORT_FIXTURE = REPO_ROOT / "tests" / "data" / "expression_set" / "RLM_DefaultPricingProcedure_export.json"
SCRIPT = REPO_ROOT / "scripts" / "ai" / "validate_expression_set.py"

RESULTS = []


def _ascii(text):
    """stdout may be cp1252 (Windows, PYTHONUTF8 unset); never let a check name crash the run."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(_ascii(f"  [{'PASS' if condition else 'FAIL'}] {name}"
                 + ("" if condition or detail == "" else f": {detail}")))


def write_json(directory, name, data):
    path = Path(directory) / name
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh)
    return str(path)


def run_main(argv):
    """(exit code, stdout, stderr) of V.main(argv) with the streams captured."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = V.main(argv)
    return code, out.getvalue(), err.getvalue()


# An overlay carrying one operation key and nothing the validator objects to.
EMPTY_REMOVE_OVERLAY = {"removeSteps": []}
# No operation keys at all: a no-op overlay, which the schema reports as a WARNING (not an error).
NOOP_OVERLAY = {}
# A definition (has `versions`) that is missing every required top-level key: ERRORS.
BROKEN_DEFINITION = {"versions": []}


def test_kind_and_exit_codes(tmp):
    print("\nkind detection and exit codes")
    clean = write_json(tmp, "clean.overlay.json", EMPTY_REMOVE_OVERLAY)
    code, out, _ = run_main([clean])
    check("an overlay with an operation key is auto-detected as an overlay",
          f"Validating {clean} as overlay:" in out, out)
    check("a file with no errors and no warnings exits 0 and reports OK",
          code == 0 and "OK" in out and "[Error]" not in out and "[Warning]" not in out, f"{code}: {out}")

    broken = write_json(tmp, "broken.definition.json", BROKEN_DEFINITION)
    code, out, _ = run_main([broken])
    check("a payload with a `versions` array is auto-detected as a definition",
          f"Validating {broken} as definition:" in out, out)
    check("validation errors exit 1 and the report names the error",
          code == 1 and "[Error]" in out and "missing required key" in out, f"{code}: {out}")

    noop = write_json(tmp, "noop.json", NOOP_OVERLAY)
    code, out, _ = run_main([noop])
    check("a payload matching neither shape defaults to an overlay", "as overlay:" in out, out)
    check("warnings alone still exit 0 (not --strict)",
          code == 0 and "[Warning]" in out and "no-op" in out, f"{code}: {out}")
    code, _, _ = run_main([noop, "--strict"])
    check("--strict promotes warnings to a failing exit 1", code == 1)

    code, _, _ = run_main([clean, "--strict"])
    check("--strict leaves a warning-free file passing", code == 0)


def test_forced_kind(tmp):
    print("\n--overlay / --definition override detection")
    both = write_json(tmp, "ambiguous.json", {"versions": [], "removeSteps": []})
    _, out, _ = run_main([both])
    check("addSteps-style keys win over `versions` in auto-detection (overlay)", "as overlay:" in out, out)
    code, out, _ = run_main([both, "--definition"])
    check("--definition forces definition validation even when the file looks like an overlay",
          "as definition:" in out and code == 1, f"{code}: {out}")
    only_def = write_json(tmp, "defn.json", BROKEN_DEFINITION)
    _, out, _ = run_main([only_def, "--overlay"])
    check("--overlay forces overlay validation even when the file looks like a definition",
          "as overlay:" in out, out)

    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            V.main([only_def, "--overlay", "--definition"])
            raised = None
        except SystemExit as exc:
            raised = exc.code
    check("--overlay and --definition are mutually exclusive (argparse exit 2)", raised == 2, err.getvalue())


def test_bad_input(tmp):
    print("\nunreadable input exits 2, never a traceback")
    code, out, err = run_main([os.path.join(tmp, "does-not-exist.json")])
    check("a missing file exits 2 with a message on stderr",
          code == 2 and "file not found" in err and out == "", f"{code}: {err}")

    bad = Path(tmp) / "bad.json"
    bad.write_text("{not json", encoding="utf-8", newline="\n")
    code, out, err = run_main([str(bad)])
    check("invalid JSON exits 2 and names the file", code == 2 and "invalid JSON" in err and str(bad) in err,
          f"{code}: {err}")

    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            V.main([])
            raised = None
        except SystemExit as exc:
            raised = exc.code
    check("no file argument is an argparse usage error (exit 2)", raised == 2)


def test_committed_fixtures(tmp):
    print("\ncommitted fixtures")
    code, out, _ = run_main([str(EXPORT_FIXTURE)])
    check("the committed Connect export fixture validates as a definition with no errors",
          code == 0 and "as definition:" in out and "[Error]" not in out, f"{code}: {out[:300]}")
    overlay_dir = REPO_ROOT / "datasets" / "expression_set_overlays"
    for overlay in sorted(overlay_dir.glob("*.json")):
        code, out, _ = run_main([str(overlay)])
        check(f"shipped overlay {overlay.name} validates clean (exit 0, no errors)",
              code == 0 and "[Error]" not in out, f"{code}: {out[:300]}")


def test_script_entry_point(tmp):
    print("\nscript entry point")
    clean = write_json(tmp, "entry.overlay.json", EMPTY_REMOVE_OVERLAY)
    broken = write_json(tmp, "entry.definition.json", BROKEN_DEFINITION)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    ok = subprocess.run([sys.executable, str(SCRIPT), clean], capture_output=True, text=True,
                        encoding="utf-8", env=env)
    bad = subprocess.run([sys.executable, str(SCRIPT), broken], capture_output=True, text=True,
                         encoding="utf-8", env=env)
    missing = subprocess.run([sys.executable, str(SCRIPT), os.path.join(tmp, "nope.json")],
                             capture_output=True, text=True, encoding="utf-8", env=env)
    check("run as a script, `main()`'s return value becomes the process exit code",
          ok.returncode == 0 and bad.returncode == 1 and missing.returncode == 2,
          (ok.returncode, bad.returncode, missing.returncode, ok.stderr[-200:], bad.stderr[-200:]))
    check("the script resolves `tasks/` from the repo root, whatever the cwd",
          "Traceback" not in ok.stderr + bad.stderr + missing.stderr, ok.stderr + bad.stderr)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_kind_and_exit_codes(tmp)
        test_forced_kind(tmp)
        test_bad_input(tmp)
        test_committed_fixtures(tmp)
        test_script_entry_point(tmp)

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
