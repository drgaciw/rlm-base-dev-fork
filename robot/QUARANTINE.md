# Robot quarantine

Register of Robot tests that are known to be flaky and are quarantined. Policy:
[docs/references/test-plan-2026-09.md](../docs/references/test-plan-2026-09.md) section 7.

A test is **flaky** when it fails and then passes on a rerun of the same commit with no
code change. The nightly e2e stage (`.github/workflows/prepare-rlm-org.yml`, "Robot e2e"
steps) reruns failed tests exactly once and reports a pass-after-rerun as *flaky*, not
green; a repeat offender is quarantined here.

## How quarantine works

1. Tag the test case `flaky` (`[Tags]    e2e    flaky`) **and** add a row below in the same
   PR. `tests/test_rlm_robot_e2e.py` fails when a `flaky`-tagged test has no row, or a row
   names a test that is not tagged.
2. Tagged tests are excluded from the blocking e2e steps (`--exclude flaky`) and run in a
   separate, non-blocking "Robot e2e quarantine" step, so they keep producing evidence.
3. Every row needs an **owner**, an **issue** link, a **root-cause label**, the date
   **added** and an **expires** date at most **14 days** after it. The static check
   validates the shape; the weekly health check (TP-12) fails a row that outlives
   `expires`. Renew by fixing the test and deleting the row, or by re-triaging in the issue
   and updating both dates, never by silently editing `expires`.
4. Root-cause labels: `timing`, `data-dependency`, `environment`, `product-bug`. Timing
   flakes are fixed by replacing a fixed wait with a condition, never by a longer timeout
   alone; data flakes by making the suite reset its own state (the `reset_account.robot`
   pattern); environment flakes at the infrastructure level.
5. Do not quarantine a `product-bug`: file the defect and keep the test blocking.

## Active quarantine

`Test` is `<path>::<test case name>`. Dates are ISO `YYYY-MM-DD`.

| Test | Owner | Issue | Root cause | Added | Expires | Evidence |
|---|---|---|---|---|---|---|

_No quarantined tests._
