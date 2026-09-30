# Quarantine registry (python, apex, lwc, flow)

Register of tests outside Robot that are known to be flaky and are quarantined. Robot tests
have their own register, [`robot/QUARANTINE.md`](../../robot/QUARANTINE.md), which stays a
markdown table next to the `flaky` tag it pairs with. Policy:
[docs/references/test-plan-2026-09.md](../../docs/references/test-plan-2026-09.md) section 7.

`scripts/ai/test_health.py` reads **both** files into one record type and prints one merged
table sorted by `expires`. Weekly (`.github/workflows/test-health.yml`) and on demand:

```bash
python scripts/ai/test_health.py check-quarantine
```

| Exit | Meaning |
|---|---|
| 0 | every entry is valid and none has passed its `expires` date |
| 1 | at least one entry has passed `expires` (an entry is still valid on its `expires` date) |
| 2 | a source cannot be read or breaks a rule below; never treated as "no entries" |

## Format

`registry.json` is an object with exactly one key, `entries`. An empty registry is
`{"entries": []}`. Every entry has exactly these keys (the names mirror the columns of
`robot/QUARANTINE.md`, plus `layer`); an unknown key, a missing key or an empty value is an error:

| Key | Value |
|---|---|
| `test` | The id, unique across **both** registers: `<path>::<test name>` (Apex: `Class.method`). |
| `layer` | `python`, `apex`, `lwc` or `flow`. Robot tests belong in `robot/QUARANTINE.md`. |
| `owner` | Who fixes it. |
| `issue` | The tracking issue: an `https://` URL or `#N`. |
| `root_cause` | `timing`, `data-dependency` or `environment`. A `product-bug` is filed and stays blocking; it is rejected here. |
| `added` | ISO date `YYYY-MM-DD`. |
| `expires` | ISO date, 1 to **14** days after `added`. A longer window is an error, not a warning. |
| `evidence` | A log or screenshot link, or the run URL that showed the flake. |

```json
{
  "entries": [
    {
      "test": "tests/test_example.py::test_retries_on_429",
      "layer": "python",
      "owner": "@drgaciw",
      "issue": "#123",
      "root_cause": "timing",
      "added": "2026-09-29",
      "expires": "2026-10-13",
      "evidence": "https://github.com/drgaciw/rlm-base-dev-fork/actions/runs/1"
    }
  ]
}
```

## Rules

1. Quarantined tests **still run**, in a separate non-blocking job; quarantine hides a failure
   from the gate, not from the report.
2. Renew by fixing the test and deleting the entry, or by re-triaging in the issue and updating
   **both** dates. Do not edit `expires` alone.
3. Nothing in a PR gate is quarantined: a flaky test in `pr_gate.py`, Lint or the Windows leg is
   fixed or moved to nightly within 2 working days (test plan section 7.2).
4. The expiry check runs in the weekly test-health workflow, not in the PR gate, so an entry that
   expires never blocks an unrelated PR. `tests/test_test_health.py` validates the shape of the
   committed registers on every PR.
