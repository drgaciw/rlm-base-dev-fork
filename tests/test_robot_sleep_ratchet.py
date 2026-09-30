#!/usr/bin/env python3
"""
Static ratchet on fixed-duration waits in the Robot tree (TP-08, TP-08b).

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
is zero. Replacements land in follow-up packages and lower the pins below in the same PR.
TP-08b took the e2e path (E2ECommon.robot, tests/e2e/*) to zero; those files are no longer
pinned, so a new Sleep there fails as "new file with Sleep". The setup suites and
SetupToggles.robot stay pinned until the nightly has a stable history.

TP-08b also guards the best-effort settle helpers that replaced the e2e Sleeps
(`Wait Until Page Is Settled` and the keywords that end in it):
* they may appear only in resources/E2ECommon.robot and tests/e2e/* (never in setup suites);
* every call must be anchored by a strict wait or assertion -- the next click/input after it
  must be preceded by a strict wait, and a settle that ends a keyword needs a strict wait
  earlier in that keyword -- so a settle timeout (a logged SETTLE_TIMEOUT warning, not a
  failure) can never be the last thing standing between a click and the page it needs;
* the structured warning text the e2e stage summary greps for must stay in one place.

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
    "robot/rlm-base/resources/SetupToggles.robot": 15,
    "robot/rlm-base/tests/setup/configure_core_pricing_setup.robot": 2,
    "robot/rlm-base/tests/setup/configure_product_discovery_settings.robot": 6,
    "robot/rlm-base/tests/setup/configure_revenue_settings.robot": 24,
    "robot/rlm-base/tests/setup/enable_constraints_settings.robot": 22,
    "robot/rlm-base/tests/setup/enable_document_builder.robot": 3,
    "robot/rlm-base/tests/setup/enable_timeline.robot": 1,
}

E2E_FILES = ("robot/rlm-base/resources/E2ECommon.robot",)
E2E_DIR = "robot/rlm-base/tests/e2e/"

# Keywords that end in the best-effort settle. Their own bodies are the definitions and are
# exempt from the anchoring rule; every call to them is checked.
# `_Wait Best Effort` is the same warn-only SETTLE_TIMEOUT mechanism, so a direct call is a settle
# call too and needs an anchor. `Run Keyword And Ignore Error`, `... Warn On Failure` and
# `Run Keyword And Return Status` swallow a failure, so they never count as strict.
SETTLE_NAMES = ("Wait Until Page Is Settled", "Wait For Dialog To Change", "Wait For Action Dialog", "_Wait Best Effort")
SETTLE_USERS = re.compile(r"\b(?:%s)\b" % "|".join(SETTLE_NAMES))
SOFT_WRAPPERS = ("Run Keyword And Ignore Error", "Run Keyword And Warn On Failure", "Run Keyword And Return Status")
STRICT = re.compile(
    r"^(?:Wait Until .*|Wait For (?!Dialog To Change$|Action Dialog$).*|.*Should .*|Verify .*|Fail|Textfield Value Should Be)$"
)
ACTION = re.compile(
    r"^(?:Click Element|Click Button|Click Link|Input Text|Press Keys|Select From List.*|Mouse Over|Go To|"
    r"Save Modal|Confirm Modal Action|Add Product By Name|Fill Modal Field|Select Modal Picklist Value|"
    r"Select Lookup Value|_Press Enter On Search Input)$"
)
CONTROL = ("IF", "ELSE IF", "ELSE", "END", "FOR", "WHILE", "TRY", "EXCEPT", "FINALLY", "RETURN", "BREAK", "CONTINUE", "GROUP")
ASSIGNMENT = re.compile(r"^[$@&]\{[^}]*\}=?$")
SETTLE_WARN = "Log    SETTLE_TIMEOUT caller=${caller} waited=${timeout}    WARN"

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


def keyword_bodies(text):
    """{keyword or test name: [(indent, step cells), ...]} -- continuation lines are joined to their
    step, [Settings] and their continuations are dropped."""
    bodies, steps, in_setting = {}, None, False
    section = ""
    for raw in text.splitlines():
        if raw.startswith("***"):
            section, steps = raw.strip("* ").lower(), None
            continue
        if section not in ("keywords", "test cases") or not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            steps = bodies.setdefault(raw.strip(), [])
            in_setting = False
            continue
        if steps is None:
            continue
        cells = [c for c in CELL_SPLIT.split(raw.strip()) if c]
        if cells[0].startswith("["):
            in_setting = True
        elif cells[0] == "...":
            if not in_setting and steps:
                steps[-1][1].extend(cells[1:])
        else:
            in_setting = False
            steps.append((len(raw) - len(raw.lstrip()), cells))
    return bodies


def classify(cells):
    """settle | strict | action | soft | other for one step."""
    cells = list(cells)
    while cells and ASSIGNMENT.match(cells[0]):
        cells.pop(0)
    if not cells or cells[0] in CONTROL:
        return "other"
    name = cells[0]
    if name in SETTLE_NAMES:
        return "settle"
    if name in SOFT_WRAPPERS:
        return "soft"
    if name == "Run Keyword And Expect Error" and len(cells) > 1:
        inner = classify(cells[1:])
        return inner if inner in ("strict", "action") else "other"
    if STRICT.match(name):
        return "strict"
    if ACTION.match(name):
        return "action"
    return "other"


def settle_violations(text, label):
    problems = []
    for name, steps in keyword_bodies(text).items():
        if name in SETTLE_NAMES:
            continue
        kinds = [classify(cells) for _, cells in steps]
        for i, kind in enumerate(kinds):
            if kind != "settle":
                continue
            indent = steps[i][0]
            nxt = None
            for j in range(i + 1, len(steps)):
                # a RETURN at the settle's own level (or shallower) ends the keyword; a nested early
                # RETURN is only one branch, so the scan continues past it
                if steps[j][1][0] == "RETURN" and steps[j][0] <= indent:
                    break
                if kinds[j] in ("strict", "action"):
                    nxt = kinds[j]
                    break
            if nxt == "action":
                problems.append(f"{label}: '{name}' step {i + 1} settles, then clicks/types before any strict wait")
            elif nxt is None and not any(k in ("strict", "action") for k in kinds[:i]):
                # a direct click/input before the settle already fails the test if it did not work,
                # so it anchors a settle that ends the keyword just as a strict wait does
                problems.append(f"{label}: '{name}' step {i + 1} settles with no strict wait before or after it")
    return problems


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


def check_settle_anchoring_analyzer(_):
    good = "\n".join(
        [
            "*** Keywords ***",
            "Tail After Strict",
            "    Wait Until Element Is Visible    css:a    timeout=5s",
            "    Wait Until Page Is Settled    caller=Tail After Strict",
            "Strict Follows",
            "    Click Element    css:a",
            "    Wait For Dialog To Change    ${before}",
            "    Page Should Contain Element    css:b",
            "    Click Element    css:b",
            "Nested Return Ends At Its Own Level",
            "    Click Element    css:a",
            "    IF    ${x}",
            "        Wait For Action Dialog",
            "        RETURN",
            "    END",
            "    Click Element    css:c",
        ]
    )
    bad_action = "\n".join(
        ["*** Keywords ***", "Click Right After", "    Wait Until Page Is Settled", "    Click Element    css:a"]
    )
    bad_tail = "\n".join(["*** Keywords ***", "Bare Tail", "    Log    x", "    Wait For Action Dialog"])
    soft_only = "\n".join(
        [
            "*** Keywords ***",
            "Soft Is Not Strict",
            "    Run Keyword And Ignore Error",
            "    ...    Wait Until Keyword Succeeds    5s    1s    Foo",
            "    Wait Until Page Is Settled",
        ]
    )
    return_status_only = "\n".join(
        [
            "*** Keywords ***",
            "Return Status Never Fails",
            "    ${ok}=    Run Keyword And Return Status    Wait Until Element Is Visible    css:a",
            "    Wait Until Page Is Settled",
        ]
    )
    direct_best_effort_then_click = "\n".join(
        [
            "*** Keywords ***",
            "Direct Best Effort",
            "    Wait Until Element Is Visible    css:a",
            "    _Wait Best Effort    x    5s    1s    Foo",
            "    Click Element    css:b",
        ]
    )
    direct_best_effort_bare_tail = "\n".join(
        ["*** Keywords ***", "Direct Bare Tail", "    _Wait Best Effort    x    5s    1s    Foo"]
    )
    nested_return_does_not_hide_click = "\n".join(
        [
            "*** Keywords ***",
            "Nested Return",
            "    Wait Until Element Is Visible    css:a",
            "    Wait Until Page Is Settled",
            "    IF    ${x}",
            "        RETURN",
            "    END",
            "    Click Element    css:b",
        ]
    )
    check("anchoring_accepts_strict_before_or_after", settle_violations(good, "good") == [], str(settle_violations(good, "good")))
    check("anchoring_rejects_settle_then_click", len(settle_violations(bad_action, "bad")) == 1, "")
    check("anchoring_rejects_unanchored_tail_settle", len(settle_violations(bad_tail, "bad")) == 1, "")
    check("anchoring_does_not_count_soft_waits_as_strict", len(settle_violations(soft_only, "bad")) == 1, "")
    check(
        "anchoring_does_not_count_return_status_as_strict",
        len(settle_violations(return_status_only, "bad")) == 1,
        "",
    )
    check(
        "anchoring_treats_direct_best_effort_wait_as_a_settle",
        len(settle_violations(direct_best_effort_then_click, "bad")) == 1
        and len(settle_violations(direct_best_effort_bare_tail, "bad")) == 1,
        "",
    )
    check(
        "anchoring_nested_return_does_not_hide_a_later_click",
        len(settle_violations(nested_return_does_not_hide_click, "bad")) == 1,
        "",
    )


def check_settle_is_confined_to_the_e2e_path(_):
    stray = []
    for path in sorted(ROBOT_DIR.rglob("*")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if path.suffix not in (".robot", ".resource") or rel in E2E_FILES or rel.startswith(E2E_DIR):
            continue
        if SETTLE_USERS.search(path.read_text(encoding="utf-8")):
            stray.append(rel)
    check("settle_helpers_only_on_the_e2e_path", not stray, ", ".join(stray) + " (setup suites must use strict waits)")


def check_e2e_settle_calls_are_anchored(_):
    problems = []
    for rel in list(E2E_FILES) + sorted(p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / E2E_DIR).glob("*.robot")):
        problems += settle_violations((REPO_ROOT / rel).read_text(encoding="utf-8"), rel)
    check("e2e_settle_calls_are_anchored_by_strict_waits", not problems, "; ".join(problems))


def check_settle_warning_has_one_structured_source(_):
    text = (REPO_ROOT / E2E_FILES[0]).read_text(encoding="utf-8")
    check("settle_warning_text_defined_once", text.count("SETTLE_TIMEOUT caller=") == 1 and SETTLE_WARN in text, "")


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
        check_settle_anchoring_analyzer,
        check_settle_is_confined_to_the_e2e_path,
        check_e2e_settle_calls_are_anchored,
        check_settle_warning_has_one_structured_source,
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
