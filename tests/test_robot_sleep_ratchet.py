#!/usr/bin/env python3
"""
Static ratchet on fixed-duration waits in the Robot tree (TP-08).

    python tests/test_robot_sleep_ratchet.py                  # check
    python tests/test_robot_sleep_ratchet.py --print-baseline # regenerate the pins

Stdlib only; reads `robot/**` as text, so no Robot Framework, browser or org needed.

Why this file exists
--------------------
docs/references/test-plan-2026-09.md section 6 (TP-08) asks that no `Sleep` remain in
robot/rlm-base. There are ~120 of them today, in setup suites that run mid-way through
the production `prepare_rlm_org` build, and they cannot be replaced with condition
waits without a live scratch org to prove the replacement (AGENTS.md DO NOT #7). The
agreed shape is therefore a ratchet: the count per file may never go UP, and the target
is zero. Replacements land in follow-up packages (TP-08b for the e2e path) and lower
the pins below in the same PR.

What counts
-----------
* a Robot step cell that is exactly `Sleep` (case-insensitive, optionally `BuiltIn.`
  prefixed) -- this includes `Run Keyword If ...    Sleep    0.5s` and `AND    Sleep`;
  free-text mentions such as `Sleep 5s ensures ...` in [Documentation] do not count;
* `time.sleep(` calls in `robot/**/*.py` helper libraries (comments excluded).

A decrease is not a failure: it prints "lower the baseline" so the pin is tightened and
the win cannot silently regress later.
"""
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROBOT_DIR = REPO_ROOT / "robot"

# Regenerate with --print-baseline after replacing Sleeps; only ever lower a value.
BASELINE = {
    "robot/rlm-base/resources/AnalyticsSetupHelper.py": 1,
    "robot/rlm-base/resources/E2ECommon.robot": 47,
    "robot/rlm-base/resources/SetupToggles.robot": 15,
    "robot/rlm-base/tests/e2e/reset_account.robot": 1,
    "robot/rlm-base/tests/setup/configure_core_pricing_setup.robot": 2,
    "robot/rlm-base/tests/setup/configure_product_discovery_settings.robot": 6,
    "robot/rlm-base/tests/setup/configure_revenue_settings.robot": 24,
    "robot/rlm-base/tests/setup/enable_constraints_settings.robot": 22,
    "robot/rlm-base/tests/setup/enable_document_builder.robot": 3,
    "robot/rlm-base/tests/setup/enable_timeline.robot": 1,
}

RESULTS = []
NOTES = []

CELL_SPLIT = re.compile(r"\s{2,}|\t")
PY_SLEEP = re.compile(r"^[^#\n]*\btime\.sleep\s*\(", re.MULTILINE)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def count_robot_sleeps(text):
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for cell in CELL_SPLIT.split(stripped):
            if cell.strip().lower() in ("sleep", "builtin.sleep"):
                count += 1
    return count


def count_py_sleeps(text):
    return len(PY_SLEEP.findall(text))


def current_counts():
    counts = {}
    for path in sorted(ROBOT_DIR.rglob("*")):
        if not path.is_file() or "results" in path.relative_to(ROBOT_DIR).parts:
            continue
        if path.suffix not in (".robot", ".resource", ".py"):
            continue
        text = path.read_text(encoding="utf-8")
        n = count_py_sleeps(text) if path.suffix == ".py" else count_robot_sleeps(text)
        if n:
            counts[path.relative_to(REPO_ROOT).as_posix()] = n
    return counts


# ---- the counter itself ---------------------------------------------------------------


def check_counter_recognises_real_sleeps_and_ignores_prose(_):
    sample = "\n".join(
        [
            "*** Keywords ***",
            "Example",
            "    [Documentation]    Sleep 5s ensures the handler is wired.",
            "    ...    Used in place of an unconditional sleep.",
            "    # Sleep    9s    commented out",
            "    Sleep    3s    reason=render",
            "    sleep    1s",
            "    BuiltIn.Sleep    1s",
            "    Run Keyword If    not ${x}    Sleep    0.5s",
            "    Wait Until Keyword Succeeds    15s    2s    Log    Sleep",
            "    ...    AND    Sleep    ${MANUAL_LOGIN_WAIT}",
        ]
    )
    # Real: Sleep 3s, sleep 1s, BuiltIn.Sleep, Run Keyword If ... Sleep, AND Sleep = 5.
    # The `Log    Sleep` cell is a step argument that happens to read "Sleep": it is
    # counted (the counter cannot tell arguments from keywords without a Robot parser).
    # A wait-helper that logs the word is the price of a parser-free, stdlib-only guard;
    # the pin absorbs it, and it can only ever be lowered.
    check("counter_counts_step_cells_named_sleep", count_robot_sleeps(sample) == 6, str(count_robot_sleeps(sample)))
    py = "import time\ntime.sleep(5)\n# time.sleep(9)\nx = 1\n"
    check("counter_counts_python_time_sleep_not_comments", count_py_sleeps(py) == 1, str(count_py_sleeps(py)))


def growth(baseline, now):
    """`{file: (pinned, now)}` for every file whose count exceeds its pin (0 if unpinned)."""
    return {f: (baseline.get(f, 0), n) for f, n in now.items() if n > baseline.get(f, 0)}


def check_ratchet_logic_rejects_growth_and_new_files(_):
    base = {"a.robot": 3, "b.robot": 2}
    check("ratchet_rejects_an_increase", growth(base, {"a.robot": 4, "b.robot": 2}) == {"a.robot": (3, 4)}, "")
    check("ratchet_rejects_a_new_file_with_sleep", growth(base, {"c.robot": 1}) == {"c.robot": (0, 1)}, "")
    check("ratchet_allows_equal_and_lower", growth(base, {"a.robot": 3, "b.robot": 0}) == {}, "")


# ---- the ratchet ------------------------------------------------------------------------


def check_no_file_exceeds_its_pin(_):
    now = current_counts()
    grew = growth(BASELINE, now)
    check(
        "sleep_count_never_increases",
        not grew,
        "; ".join(
            f"{f}: pinned {old}, now {new}"
            + (" (new file with Sleep: use a condition wait)" if old == 0 else "")
            for f, (old, new) in sorted(grew.items())
        ),
    )
    for f, pinned in sorted(BASELINE.items()):
        n = now.get(f, 0)
        if n < pinned:
            NOTES.append(f"lower the baseline: {f} has {n} Sleep(s), pinned at {pinned}")


def main():
    if "--print-baseline" in sys.argv:
        print("BASELINE = {")
        for f, n in current_counts().items():
            print(f'    "{f}": {n},')
        print("}")
        return 0
    checks = [
        check_counter_recognises_real_sleeps_and_ignores_prose,
        check_ratchet_logic_rejects_growth_and_new_files,
        check_no_file_exceeds_its_pin,
    ]
    for fn in checks:
        try:
            fn(None)
        except Exception as exc:  # a check that blows up is a failure, not a crash
            check(fn.__name__.replace("check_", ""), False, f"check raised {type(exc).__name__}: {exc}")

    width = max(len(n) for n, _, _ in RESULTS)
    failed = 0
    print("robot Sleep ratchet\n" + "=" * (width + 60))
    for name, ok, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail if not ok else ''}")
        failed += 0 if ok else 1
    for note in NOTES:
        # In GitHub Actions a workflow command surfaces the note as an annotation on the run
        # instead of burying it in the log of a passing check.
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Sleep ratchet::{note}")
        else:
            print(f"  NOTE  {note}")
    total = sum(current_counts().values())
    print("=" * (width + 60))
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed; {total} Sleep(s) remain (target 0)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
