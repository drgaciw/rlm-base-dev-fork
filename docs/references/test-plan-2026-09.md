# Test Plan — rlm-base-dev-fork (2026-09)

| | |
|---|---|
| Repo / commit | [drgaciw/rlm-base-dev-fork](https://github.com/drgaciw/rlm-base-dev-fork), `main` @ `3bb71562` |
| Author | ARCHITECT (Claude Code) |
| Inputs | (A) the wave 1–3 architecture work in [architect-review-2026-09.md](architect-review-2026-09.md) and direct inspection of `tests/`, `robot/`, `jest.config.js`, `scripts/ai/pr_gate.py`, `.github/workflows/*.yml`, `cumulusci.yml`, plus GitNexus `context`/`cypher`; (B) six Perplexity research queries (§8); (C) a 12-thought Sequential Thinking chain with one revision (Appendix A) |
| Status | Proposal. Nothing here is implemented yet; §6 shapes the work as packages. |

## 1. Purpose and scope

This plan says what the fork must be able to prove about itself, what proves it today, where the holes are, and in what order to close them.

**What the fork must guarantee** (from the Sequential Thinking scope step, ordered by blast radius):

1. `prepare_rlm_org` and its sibling flows build a working org from a fresh scratch org of each supported shape.
2. SFDMU data loads are idempotent and never leak credentials (wave 1 rewrote `tasks/rlm_sfdmu.py`).
3. Apex and LWC metadata deploys and behaves. Wave 1 gave 16 Apex classes explicit sharing or `USER_MODE`; that is still **unverified against any org**.
4. The ~85k lines of Python in `tasks/` and `scripts/` keep working. Wave 1 shipped a guaranteed `TypeError` (A-C1) because the test mocked the unit under test.
5. The CI gates stay green *and* meaningful.
6. The agent-layer config (`CLAUDE.md` import, rules sync, hooks, skill junctions) works on Windows and POSIX.
7. No security regressions: token logging, passwords, workflow secrets.

**In scope:** every automated check that runs, or should run, in CI or on a developer machine. **Out of scope:** manual demo rehearsals, release-enablement content review, PMOS cross-repo integration.

## 2. Test inventory today

| Layer | Location | Runner | Count | CI-gated? |
|---|---|---|---|---|
| Python, stdlib-only offline suites | `tests/test_*.py` (53 files) | `python tests/x.py`, selected by `pr_gate.py` (`STDLIB_SUITES` = 22 files, plus named checks) | 53 files; `test_pr_gate.py` alone runs 723 checks | **Yes**: `pr-checks.yml` "Mechanical checks" on `pull_request` and `merge_group` |
| Python, dependency suites | same dir; `deps=` in `pr_gate.py` | `requests_offline_suites` (3), `yaml_offline_suites`, `doc_build_steps` + `extend_stdctx_recovery` (need `cumulusci`) | 31 registered checks in total | Yes; a missing dep is **MISSING-DEP = fail**, never skip |
| Python, pytest packages | `tests/build_harness/` (11 files), `tests/txn_data_harness/` (22 files), `tests/test_docgen_helpers.py`, `tests/test_billing_portal_config.py` | `python -m pytest` via `harness_suites`, `docgen_suite`, `billing_portal_suites` | 3 gate checks | Yes, when `pytest`/`textual` are installed (CI installs `requirements-dev.txt`) |
| Agent-layer config | `analyze_agent_tooling.py check` (14 checks), `skill_manifest.py --check`, `sync_claude_rules.py --check`, `link_skills.py`, `test_protect_generated_hook.py` (30 checks incl. 3 interpreter layouts), `test_gitnexus_guard.py` | gate checks `agent_tooling`, `skill_manifest`, `claude_rules_sync`, `link_skills_suite`, `stdlib_offline_suites` | 6 checks | Yes |
| Encoding / Windows portability | `scripts/lint/check_text_encoding.py`, ruff `PLW1514` (preview, `explicit-preview-rules`), `test_check_text_encoding.py` | `text_encoding_gate`, `check_text_encoding_suite`, Lint job | 3 | Yes, **on Linux only** |
| Data plans | `scripts/validate_sfdmu_v5_datasets.py`, `test_sfdmu_csv_expectation.py` (217 checks), `test_sfdmu_export.py`, plan-README checks | gate checks `sfdmu_datasets`, `sfdmu_csv_expectation`, `sfdmu_export_parser`, `plan_readme_*` | 6 | Yes (static only; no org) |
| Lint | ruff (baseline select + PLW1514), ESLint (LWC config), Prettier (changed non-Apex files), ruff per-file-ignores grandfather old code | `pr-checks.yml` "Lint (changed files)" | 1 job | Yes |
| Docker | `config/tool-versions.env` vs Dockerfile ARG defaults | `pr-checks.yml` "Docker ARG defaults" | 1 job | Yes |
| Apex | 73 classes, **47 test classes** (48 `@isTest` files) under `force-app/` and `unpackaged/*` | `run_tests` task is defined (`required_org_code_coverage_percent: 75`) but **appears in no flow**; no workflow runs `sf apex run test` | 47 test classes | **No** |
| LWC | 51 bundles under `force-app/**/lwc` and `unpackaged/**/lwc` | `sfdx-lwc-jest` via `npm test` | **0 tests**; `npm test` exits 1 | **No** |
| Robot Framework | `robot/rlm-base/tests/setup/` (8 org-configuration suites), `tests/e2e/` (4 behavioral suites), 2 resources, 2 variable files | CCI tasks `robot`, `robot_e2e`, `robot_setup_quote`, `robot_order_from_quote`, `robot_reset_account` (`tasks/rlm_robot_e2e.py`, headless by default) | 12 suites | **No** (never invoked by any workflow) |
| Org build (integration) | `prepare_rlm_org` (34 steps) and 45 other flows; 18 scratch shapes in `cumulusci.yml` `orgs:` | `prepare-rlm-org.yml` runs `validate_setup` + `cci flow run prepare_rlm_org` | 1 flow exercised | **Label-gated only** (`ci:prepare-org`) or manual dispatch; no schedule |
| Workflow YAML | 7 workflows | `actionlint` run locally by WP-13/WP-14 workers | — | **No** CI step |

**Coverage of `tasks/` by tests.** GitNexus `cypher` (tests → `IMPORTS` → `tasks/*`) resolves 12 of 61 task modules as imported by a test: `expression_set_schema`, `rlm_apex_file`, `rlm_cml`, `rlm_community`, `rlm_expression_set_connect`, `rlm_extend_stdctx`, `rlm_fix_scratch_identity`, `rlm_manage_fulfillment_scope_cnfg`, `rlm_sfdmu`, `rlm_snapshot_dev_guide`, `rlm_snapshot_help`, `rlm_validate_keys`. Tests that load modules via `importlib.util` (e.g. `test_rlm_context_service.py`) are invisible to that edge, so the true figure is a little higher, but the wave-1 finding stands: most of `tasks/` has no unit test. The GitNexus FTS index is still missing, so `query()` returns nothing; `context()` and `cypher()` work.

## 3. Risk-based priorities

| Rank | Risk | Why now | Detectability today |
|---|---|---|---|
| **P0** | Wave-1 Apex changes (WP-07/WP-11): explicit sharing on 13 classes, `USER_MODE` + allowlist in `RLM_AI_UpdateRecordFieldsService`, `RLM_AssetInfoUtility` `without sharing` justification | Shipped and merged, verified only by compile-free review; only `RLM_AI_UpdateRecordFieldsServiceTest` exists among the 16 changed classes; the Quinn agent demo and the tax adapters sit on this code | **None**: nothing runs Apex |
| **P0** | `set_scratch_org_password` via `%%%PARAM_1%%%` and the random-password policy fix; `SetupToggles.robot` password variable | Same PR; a bad value bricks a demo org login | None |
| **P0** | F2: `cumulusci==4.8.1` declares `selenium<4`; `robot/requirements.txt` needs `>=4.49`. Resolving both is **unsatisfiable**; CI works only because `prepare-rlm-org.yml:130-132` installs them in separate `pip` calls | A "fix the pip warning" change would downgrade selenium to 3.x and break every Robot suite | None: nothing asserts the final environment |
| **P1** | Python REST/subprocess wrappers (`rlm_rest_base`, `_make_request` in 5 modules, `_load_command_args`) | A-C1 shipped a 100% failure of every context-extension step because `test_extend_stdctx.py:91-99` faked `_make_request`; A-C2 broke `sf` on Windows | Partial: wave 2 added contract tests for `rlm_extend_stdctx`, `rlm_sfdmu`; the pattern is not enforced |
| **P1** | Windows portability (encoding, junctions, hook launcher) | 338 locale-dependent I/O sites were found; the fixes are covered by tests that **only run on Linux CI** | Regressions surface on laptops |
| **P1** | Data-load idempotency | WP-07/WP-11 changed the SFDMU staging path; `run_qb_idempotency_tests` (14 steps) exists but never runs in CI | None |
| **P2** | LWC (51 bundles, 0 tests), Robot e2e (4 suites, never run) | Customer-visible, but stable code | None |
| **P2** | CCI flow matrix across shapes (`dev`, `ent`, `tfid-pde`) | Flag-driven `when:` guards (`pde`, `trial`, edition) are only ever exercised one shape at a time by humans | None |
| **P3** | Coverage measurement, workflow-YAML linting in CI, flaky-test tooling | Hygiene | — |

## 4. Test strategy per layer

### 4.1 Python (unit, contract, integration)

Three tiers, selected by `pr_gate.py` as today:

| Tier | What | Runs where | Entry criteria | Exit criteria |
|---|---|---|---|---|
| T1 stdlib-only | `STDLIB_SUITES`, agent-layer, encoding, data-plan static checks | every PR, **ubuntu + windows-latest** (new) | file is stdlib-only and runs under `python tests/x.py` **and** `python -m pytest tests/x.py` | 0 FAIL on both OSes |
| T2 dependency | `requests_*`, `yaml_*`, `cumulusci`-importing, pytest packages | every PR on ubuntu with `requirements-dev.txt` | suite passes **with and without** `cumulusci` importable (A-C3) | 0 FAIL, 0 MISSING-DEP |
| T3 org-backed | tasks executed against a scratch org | nightly job (§4.8), label on demand | — | see §4.8 |

**Rules that would have caught the wave-1 regressions** (make them a checklist in `REVIEW.md`'s "defect classes" section):

1. **Never mock the unit under test.** Every `_make_request` / `request()` wrapper gets a *contract test* that patches `requests.request` (or `requests.Session.request`) and asserts method, URL, headers and **exactly one** `timeout` kwarg. Template: the wave-2 test added for `rlm_extend_stdctx` (A-C1).
2. **Every subprocess wrapper gets an argv test** with `shutil.which` patched to a `.cmd` path and with `shell=False` asserted (A-C2). Template: `tests/test_rlm_sfdmu_redaction.py::test_resolves_cmd_shim_when_which_finds_it`.
3. **Every credential path gets a log-capture assertion**: run the task with a fake token and assert it appears in neither `caplog`/logger output nor the argv (X1).
4. **Import-order tests** for modules that import CumulusCI: the test must pass both with CCI installed (CCI sets `tasks.__path__ = []`) and without.
5. **Encoding**: no new `open()`/`read_text()`/`subprocess(text=True)` without `encoding=`; enforced by `PLW1514` + `check_text_encoding.py` already.

Concrete backlog (owner: WP-08's successor, see TP-03):
- Contract tests for `_make_request` in `rlm_context_service`, `rlm_cml`, `rlm_manage_fulfillment_scope_cnfg`, `rlm_modify_context`, `rlm_manage_transaction_processing_types`; for `rlm_rest_base.request` retry/timeout semantics; for every `subprocess.run(["sf", …])` site.
- Unit tests for the three largest untested modules: `rlm_ux_assembly` (1,522 lines: `_find_elem` has 20 callers per GitNexus), `rlm_writeback_ux` (1,458), `rlm_apply_procedure_plan_overlay` (845). Start with pure functions (XML element finders, overlay merges), not the CCI task classes.
- Parity/property tests: `expression_set_schema` vs the vendored copy already has one; add a golden-file test for `generate_cci_reference.py` output (it is regenerated by the gate anyway).

**Commands:**
```bash
python scripts/ai/pr_gate.py --base origin/main      # PR selection
python scripts/ai/pr_gate.py --all                   # full, 31 checks
python -m pytest -q tests/build_harness tests/txn_data_harness
python -m coverage run --branch -m pytest -q && python -m coverage report -m   # after TP-10
```

**Coverage targets (coverage.py, branch mode; TP-10):** `scripts/ai/**` 85% (gate code must be trustworthy), `tasks/**` 60% within two phases from a measured baseline, ratcheted (never decreasing) via a committed threshold file. No coverage gate on `scripts/` legacy utilities until they have owners.

### 4.2 Apex

**Design decision (Sequential Thinking thought 5, revising 4):** Apex needs an org. Per-PR scratch orgs are too slow (30+ min build) and burn quota, so:

| Stage | Trigger | Command | Test level | Gate |
|---|---|---|---|---|
| Static | every PR touching `*.cls`/`*.trigger` | `sf code-analyzer run --rule-selector "Security,ErrorProne" --workspace <changed files>` (PMD Apex security rules) | n/a | Lint job, blocking after a baseline |
| Focused | PR with label `ci:apex` | `sf apex run test --target-org <ci-org> --test-level RunSpecifiedTests --tests <derived list> --code-coverage --result-format junit --wait 30` | RunSpecifiedTests | must pass; **per-class ≥ 75%** for deployed classes (the platform rule for this level) |
| Full | nightly, after the org build | `cci task run run_tests --org <ci-org>` (uses `required_org_code_coverage_percent: 75`) or `sf apex run test --test-level RunLocalTests --code-coverage --result-format junit` | RunLocalTests | org-wide ≥ 75%, new/changed classes ≥ 80%; JUnit + coverage JSON uploaded as artifacts |
| Release | before tagging | `sf project deploy validate --source-dir <package dirs> --test-level RunLocalTests --wait 60` on a fresh org built from the release branch | RunLocalTests | validate job id recorded |

**Immediate backlog of test classes** (only one of the 16 wave-1 classes has a test):

| Class | Test to add | Key assertion |
|---|---|---|
| `RLM_AI_UpdateRecordFieldsService` (exists: `…ServiceTest`) | extend | as a non-admin `System.runAs` user with the post_agents permission set: allowed object updates succeed, a disallowed sObject is rejected, a field without FLS raises the controlled exception (USER_MODE), and `quote` (lower case) is accepted |
| `RLM_AssetInfoUtility` (`without sharing`, `@InvocableMethod`) | new | `System.runAs` a Partner Community user who owns no Assets: assert the invocable returns the intended elevated data (documents the `without sharing` decision) |
| `RLM_CalculateTaxService`, `RLM_AvalaraAdapter`, `RLM_MockTaxAdapter`, `RLM_MockAppAdapter`, `RLM_InvalidAdapter` | new, one class | route to mock adapter, assert tax lines; `RLM_InvalidAdapter` throws; callout via `HttpCalloutMock` |
| `RLM_PlaceQuoteModel`, `RLM_PlaceOrderModel`, `RLM_QuoteModelUtility` | new | pure serialization round-trips; bulk list of 200 |
| `RLM_DetermineDROSourceType`, `RLM_DFOTenantProvisioningCallout`, `RLM_AA_Submit_Approval`, `RLM_DocumentGenerationMerge`, `RLM_ReturnPDFDocument` | new | one happy path + one failure path each; sharing asserted with `runAs` where the class is `with sharing` |

Test-data rules: one `RLM_TestDataFactory` (Account, Product2, PricebookEntry, Quote, QuoteLineItem, Asset), `@TestSetup` only for shared baseline data, no `SeeAllData`, bulk (200) for anything DML-facing, both success and failure paths.

**One-off P0 verification** (until the nightly exists), to be run by a human with a dev-hub login and recorded in the PR:
```bash
cci org scratch dev tp-verify --days 1 && cci flow run prepare_rlm_org --org tp-verify
sf project deploy validate --target-org rlm-base__tp-verify \
  --source-dir force-app/main/default/classes --source-dir unpackaged/pre/4_tax \
  --source-dir unpackaged/post_agents/classes --source-dir unpackaged/post_approvals/classes \
  --source-dir unpackaged/post_docgen/classes --source-dir unpackaged/post_guidedselling/omniScripts \
  --test-level RunSpecifiedTests --tests RLM_AI_UpdateRecordFieldsServiceTest --wait 30
cci task run set_scratch_org_password --org tp-verify        # must succeed; must refuse on a sandbox alias
cci task run robot --org tp-verify -o suites robot/rlm-base/tests/setup   # SetupToggles.robot path
```

### 4.3 LWC / Jest

Today: 51 bundles, 0 tests, `npm test` exits 1. Plan (TP-07), following Salesforce's guidance to keep tests in each bundle's `__tests__` and to start a zero-test repo with a pass gate before any coverage gate:

1. `jest.config.js`: add explicit `roots` for `force-app/main/default` and every `unpackaged/*/main/default` that contains `lwc/` (generate the list once from `sfdx-project.json` `packageDirectories`), `collectCoverageFrom` on `**/lwc/**/*.js` excluding `__tests__`/`__mocks__`, `clearMocks: true`.
2. Generate one **smoke test per bundle**: `createElement` + `appendChild` renders without throwing; for bundles that `@wire` Apex, register the adapter with `registerTestWireAdapter` and emit `[]` and an error. Mock imperative Apex per bundle under `__mocks__/@salesforce/apex/`.
3. CI: a `lwc-tests` job in `pr-checks.yml` on changes to `**/lwc/**`, `jest.config.js`, `package.json`: `npm ci` (requires committing `package-lock.json`, the C7 follow-up) then `npm run test:coverage`; upload `coverage/`.
4. Thresholds: none in the first PR; after the smoke tranche, `coverageThreshold.global = {statements: 50, branches: 40, functions: 50, lines: 50}`; ratchet +5 points per quarter, never lower. New or materially changed bundles need behavioral tests (render, empty state, wire error, one user interaction and dispatched event).

Entry: `npm test` exits 0. Exit for Phase 2: every bundle has ≥1 test; global thresholds enforced.

### 4.4 Robot Framework (setup automation and e2e)

The repo already splits **setup suites** (org configuration through the UI, e.g. `enable_document_builder.robot`) from **behavioral e2e** (`quote_to_order.robot`). Keep that split and treat them differently:

| Suite set | When | How | Exit criteria |
|---|---|---|---|
| `tests/setup/*` (8) | nightly, as the last step of the org build | `cci task run robot --org <ci-org> -o suites robot/rlm-base/tests/setup -o options '{"outputdir":"robot/rlm-base/results"}'` (headless Chrome; `rlm_robot_e2e.py` defaults to headless) | 100% pass; `--dryrun` is explicitly **not** evidence (AGENTS.md DO NOT #7) |
| `tests/e2e/*` (4) | nightly after setup; weekly full | `cci task run robot_e2e --org <ci-org>` then `robot_setup_quote`, `robot_order_from_quote`; `reset_account.robot` before each behavioral suite | quote-to-order path green weekly; one automatic `--rerunfailed` pass, merged with `rebot --merge`; a pass-after-rerun is reported as **flaky**, not green |

Stabilization rules (from the Perplexity Robot research and this repo's own `robot-tests` rule): locate by accessible name/label or a `data-testid` the repo owns; no `nth-child` or SLDS class selectors; no `Sleep`, only `Wait Until …` with a condition; shadow-DOM traversal isolated in one Python keyword. Browser provisioning: rely on Selenium Manager (selenium ≥ 4.11 bundles it) and keep `webdriver-manager` only as the documented fallback, since ubuntu runners ship Chrome. Artifacts: `output.xml`, `log.html`, `report.html`, screenshots, always uploaded. Parallelism: none until the suites are parallel-safe; `pabot --processes 2` at most, never for setup suites.

### 4.5 Data-plan validation (SFDMU)

Static (every PR, exists): `validate_sfdmu_v5_datasets.py`, `test_sfdmu_csv_expectation.py`, `test_sfdmu_export.py`, plan-README consistency. Add: an `export.json` **JSON-schema** validation against a vendored copy of SFDMU's published schema (pin it; do not fetch at build time), and an external-ID preflight (missing/blank/duplicate external IDs in the CSVs) inside `validate_sfdmu_v5_datasets.py`.

Dynamic (nightly): run `cci flow run run_qb_idempotency_tests --org <ci-org>` after the build. It loads each QB plan twice and asserts no new records; that is exactly the property WP-07/WP-11 touched. Add the credential assertion to the same job: after the run, `grep -rl accessToken datasets/` must be empty and the CCI log must contain no `accessToken` value (the wave-1 redaction test proves the unit; this proves the integration).

### 4.6 CI and workflow tests

- **Lint job** gains `actionlint` and `zizmor` on changes under `.github/workflows/**` (both are pinned binaries, no org needed). Baseline any existing `zizmor` findings explicitly.
- **docker-publish** is exercised by a `workflow_dispatch` smoke (`tag: ci-smoke-<date>`, `platforms: linux/amd64`) after any `docker/*` action bump, before the Monday 07:00 UTC schedule.
- **Gate shape** stays as is (path-selected checks behind one always-reported "Mechanical checks", plus `merge_group`), which matches current GitHub guidance to require a stable gate job rather than path-filtered jobs.
- **Environment assertion for F2** (TP-02): after `pip install -r robot/requirements.txt`, run `python -c "import selenium, SeleniumLibrary; assert selenium.__version__.split('.')[0] == '4'"` and `pip check || true` with the known CumulusCI conflict allow-listed, so a future "fix" cannot silently downgrade selenium.

### 4.7 Agent-layer configuration

Already tested: analyzer (14 checks), `sync_claude_rules --check`, `link_skills --check/--fix`, `protect_generated.py` hook (30 checks incl. 3 interpreter layouts), GitNexus guard, skill manifest. Add:
- run the stdlib agent-layer suites on **windows-latest** (TP-05) so junction, hook-launcher and encoding tests execute where they matter;
- a file-shape test that `CLAUDE.md` starts with `@AGENTS.md`, stays ≤ 15 lines, and that `AGENTS.md` ≤ 150 lines / 12,288 bytes (the analyzer already enforces the byte budget; add the import-line check);
- `.gitnexusrc` regression: `npx gitnexus analyze` in a temp clone must leave `git status` clean for `CLAUDE.md`, `AGENTS.md`, `.claude/skills/` (nightly, since it needs the npm package).

### 4.8 The nightly org job (backbone for §4.2, §4.4, §4.5)

Extend `prepare-rlm-org.yml` (already has the protected `devhub` environment and `SFDX_AUTH_URL` via `env:`) with a `schedule: cron: "0 3 * * 1-5"` trigger and a post-build stage:

```text
build:      cci org scratch dev ci-nightly --days 1 → cci flow run prepare_rlm_org
verify:     cci task run run_tests (RunLocalTests, junit+coverage) →
            cci flow run run_qb_idempotency_tests →
            cci task run robot -o suites robot/rlm-base/tests/setup →
            cci task run robot_e2e (+ --rerunfailed once, rebot --merge)
publish:    JUnit XML, coverage JSON, robot output/log/report/screenshots as artifacts;
            $GITHUB_STEP_SUMMARY with pass/fail/flaky counts
cleanup:    if: always() → cci org scratch_delete ci-nightly
```

Budget: 1 nightly scratch org per weekday plus up to 3 label-triggered runs per day. `timeout-minutes: 120`. Concurrency group `prepare-rlm-org-nightly`, no cancel.

## 5. Environments, org matrix, secrets

| Environment | Definition | Used for | Cadence |
|---|---|---|---|
| `dev` scratch | `orgs/dev.json` (Developer edition, features list) | PR-labelled runs, nightly build + Apex + Robot + idempotency | daily |
| `ent` scratch | `orgs/ent.json` | enterprise/billing flag paths (`prepare_billing`, 14 steps) | weekly matrix |
| `tfid-pde` scratch | `orgs/tfid/tfid-pde.json` via `/build-pde` (`pde=true`, `billing_ui=false`) | PDE flag path, `build_pde_dev_r1.sh` | weekly matrix |
| `tfid-qb-tso` | `orgs/tfid/tfid-qb-tso.json` | QuantumBit demo data used by the e2e suites | weekly, with the e2e run |
| `dev-mfg-previous` | `release: previous` (only way to get a prior-release org) | ERD/schema cross-validation, not CI | on demand |
| Sandboxes / TFID clones | customer-like | release-enablement rehearsal, `set_scratch_org_password` **must refuse** here | manual |

The other 12 shapes (`ent-sdb*`, `ent-r1`, `dev-sb0`, …) are instance-specific variants and stay out of the matrix unless a flag they carry is not covered above.

**Secrets and wiring:** the dev hub `SFDX_AUTH_URL` lives in the `devhub` GitHub environment (wave 2, WP-13) and is passed through `env:`; the nightly schedule must be added as an allowed deployment source for that environment. No PATs. Apex and Robot jobs reuse the same environment. Scratch-org credentials never leave the runner; `SF_TEMP_SHOW_SECRETS` stays step-scoped. Artifacts are retained 14 days.

## 6. Gaps and phased roadmap (work packages)

Each package is independently executable; owned paths are disjoint within a phase. Sizes: S ≤ 1 day, M ≤ 3 days, L ≤ 1 week.

| id | Phase | Title | Owner type | Size | Owned files | Acceptance criteria |
|---|---|---|---|---|---|---|
| **TP-01** | 0 | One-off org verification of wave-1 Apex/password/Robot changes | human with dev-hub access | S | none (evidence in a PR comment or `docs/references/`) | The §4.2 command block runs on a `dev` scratch org built from `main`: deploy-validate succeeds with `RLM_AI_UpdateRecordFieldsServiceTest` passing; `set_scratch_org_password` succeeds on scratch and refuses on a non-scratch alias; the 8 setup suites pass headless; the Quinn agent "update record fields" action works as the agent user. Results recorded with org id and run date. |
| **TP-02** | 0 | F2 environment assertion | worker | S | `.github/workflows/prepare-rlm-org.yml` (verify step only), `robot/requirements.txt` (comment), `requirements-dev.txt` (comment), `docs/guides/dev-environment-setup.md` | After the robot install step, a step asserts `selenium` major == 4 and `SeleniumLibrary` ≥ 6.9 and fails otherwise; `pip check` output is captured with the CumulusCI `selenium<4` conflict explicitly allow-listed; the two requirements files state that the robot stack deliberately overrides CCI 4.8.1's pin. |
| **TP-03** | 0 | Contract tests for REST and subprocess wrappers | worker | M | `tests/test_rest_contracts.py` (new), `tests/test_subprocess_contracts.py` (new), `REVIEW.md` (defect-class checklist), `scripts/ai/pr_gate.py` (registration) | Every `_make_request`/`request` wrapper in `tasks/` has a test that patches `requests.request`/`Session.request` and asserts one `timeout` kwarg; every `subprocess.run(["sf"…])` site has an argv test with a `.cmd` shim; tests pass with and without `cumulusci` installed; `REVIEW.md` lists "mocked the unit under test", "sf argv on Windows", "token in log/argv" as named defect classes. |
| **TP-04** | 1 | Nightly org job: build + Apex + idempotency + Robot setup | worker (CI) | L | `.github/workflows/prepare-rlm-org.yml` (schedule + verify/publish/cleanup stages), `cumulusci.yml` (a `ci_nightly_verify` flow wrapping `run_tests`, `run_qb_idempotency_tests`, `robot` setup) | Runs on the `devhub` environment on a weekday cron and on the `ci:prepare-org` label; uploads JUnit, coverage JSON and Robot artifacts; `$GITHUB_STEP_SUMMARY` shows counts; org deleted `if: always()`; `timeout-minutes: 120`; first three nightly runs green or every failure triaged into an issue. |
| **TP-05** | 1 | Windows leg for portable suites | worker (CI) | M | `.github/workflows/pr-checks.yml` (new `gate-windows` job), `scripts/ai/pr_gate.py` (`--tier stdlib` selector) | `windows-latest` runs `python scripts/ai/pr_gate.py --all --tier stdlib` (STDLIB_SUITES + agent-layer + encoding checks) with `PYTHONUTF8` **unset**; passes; job is required alongside "Mechanical checks"; runtime ≤ 10 min. |
| **TP-06** | 1 | Apex test backlog + static Apex analysis | worker (Apex) | L | new `*Test.cls` files listed in §4.2, `RLM_TestDataFactory.cls` (new), `.github/workflows/pr-checks.yml` (code-analyzer step in Lint) | All 16 wave-1 classes have a test class; nightly `run_tests` reports org-wide ≥ 75% and each new test class ≥ 80% on its subject; `sf code-analyzer` runs on changed `*.cls` with a committed baseline and blocks on new Security/ErrorProne findings. |
| **TP-07** | 2 | LWC Jest baseline | worker (JS) | M | `jest.config.js`, `package.json` (scripts; `package-lock.json` committed), `**/lwc/**/__tests__/**` (new), `.github/workflows/pr-checks.yml` (`lwc-tests` job) | `npm test` exits 0 with ≥ 1 test per bundle (51); wire-using bundles cover emit + error; CI job runs on LWC/jest changes and uploads coverage; thresholds set to 50/40/50/50 after the tranche and documented as a ratchet. |
| **TP-08** | 2 | Robot e2e nightly with rerun, artifacts and quarantine | worker (QA) | M | `robot/rlm-base/**`, `tasks/rlm_robot_e2e.py` (`--rerunfailed` + `rebot --merge` support), `.github/workflows/prepare-rlm-org.yml` (e2e stage only) | `quote_to_order`, `setup_quote`, `order_from_quote`, `reset_account` run nightly after setup; exactly one automatic rerun of failed tests; merged report distinguishes pass / pass-after-rerun (flaky) / fail; `flaky` tag + `robot/QUARANTINE.md` entries with owner, issue, expiry; no `Sleep` keyword remains. |
| **TP-09** | 2 | CCI flow matrix across shapes | worker (CI) | M | `.github/workflows/flow-matrix.yml` (new), `cumulusci.yml` (matrix-only flows if needed) | Weekly `matrix: [dev, ent, tfid-pde]` job builds each shape with its flags (`/build-pde` path for `tfid-pde`), runs `validate_setup` and `run_tests`, deletes the org; each leg has its own summary; failures open an issue with the shape name. |
| **TP-10** | 3 | Python coverage ratchet | worker | M | `pyproject.toml` (`[tool.coverage.*]`), `scripts/lint/coverage_ratchet.py` (new), `coverage-floor.json` (new), `.github/workflows/pr-checks.yml` (coverage step) | `coverage run --branch` over T1+T2 suites; `coverage-floor.json` holds per-package floors (`scripts/ai` ≥ 85%, `tasks` ≥ measured baseline); the ratchet script fails a PR that lowers a floor and updates the file when coverage rises; badge/summary in the job. |
| **TP-11** | 3 | Workflow self-tests | worker (CI) | S | `.github/workflows/pr-checks.yml` (Lint: `actionlint`, `zizmor`), `.zizmor.yml` (new baseline), `docs/guides/ci-runbook.md` (new: docker-publish smoke procedure) | `actionlint` and `zizmor --pedantic` run on `.github/workflows/**` changes with pinned binaries; existing findings baselined and listed; the runbook documents the `ci-smoke` dispatch after action bumps. |
| **TP-12** | 3 | Test-health reporting and quarantine automation | worker | M | `scripts/ai/test_health.py` (new), `.github/workflows/test-health.yml` (new), `tests/quarantine/` (new) | Weekly job aggregates JUnit/Robot artifacts into a summary (pass rate, pass-after-rerun rate, quarantine age, MTTR); a check fails when a quarantine entry passes its `expires` date; the report is posted to the job summary and, optionally, an issue. |

**Dependencies:** TP-04 before TP-06's nightly criterion, TP-08 and TP-09 (they extend the same job or reuse its pattern); TP-07 needs `package-lock.json` committed; TP-12 consumes artifacts from TP-04/TP-08. Everything else is independent. Phase 0 can start today with no infrastructure.

## 7. Flaky-test and maintenance policy

1. **Definition.** A test is flaky when it fails and then passes on a rerun of the same commit with no code change.
2. **PR gates never contain known-flaky tests.** A flaky test in `pr_gate.py`, Lint or the Windows leg is fixed or moved to nightly within 2 working days; until then it is skipped with a reason string that names the tracking issue.
3. **No retries on unit tests.** A failing T1/T2 suite is a real failure. Retries exist only for org-backed jobs (Apex, Robot, flow matrix): **one** automatic rerun of the failed subset (`robot --rerunfailed`, `sf apex run test --tests <failed>`), results merged, and pass-after-rerun reported as *flaky*, never as green.
4. **Quarantine is explicit and expiring.** Entry requires owner, issue link, evidence (screenshot/log), date added and `expires` ≤ 14 days. Quarantined tests still run, in a separate non-blocking job. An expired entry fails the health check (TP-12).
5. **Root-cause labels** on every flake: `timing`, `data-dependency`, `environment`, `product-bug`. Environment flakes (Chrome/driver/runner) are fixed at the infrastructure level (pin, Selenium Manager, `--disable-dev-shm-usage`); data flakes by making the suite reset its own state (`reset_account.robot` pattern); timing flakes by replacing sleeps with conditions, never by longer timeouts alone.
6. **Maintenance cadence.** Monthly: re-measure coverage floors, review quarantine, bump `requirements-dev.txt` / `config/tool-versions.env` in one PR each, rerun the F2 resolution check (`uv pip compile`) to see whether CumulusCI has lifted its selenium pin. Quarterly: raise the LWC threshold by 5 points if exceeded, prune tests that no longer map to a flow or task (90 CCI tasks are in no flow; confirm each before deleting anything).
7. **Ownership.** Each layer has a named owner in `CODEOWNERS`-style comments at the top of the relevant workflow job; unowned tests are candidates for deletion after one release cycle.

## 8. Sources

Perplexity citations, as returned (six `perplexity_ask` queries, 2026-09-23; `perplexity_research` repeatedly failed with network errors and was not used):

- **Apex testing and CI:** [sf project deploy validate](https://developer.salesforce.com/docs/platform/salesforce-cli-reference/guide/cli_reference_project_deploy_validate.html) · [sf apex run test](https://developer.salesforce.com/docs/platform/salesforce-cli-reference/guide/cli_reference_apex_run_test.html) · [Deploy validation (Metadata API)](https://developer.salesforce.com/docs/atlas.en-us.daas.meta/daas/forcemigrationtool_deploy_validation.htm) · [Build production release (RunLocalTests → quick deploy)](https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_build_mdapi_production.htm) · [Run specific tests / 75% per class](https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_deploy_run_specific_tests.htm) · [@TestSetup](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_testing_testsetup_using.htm) · [Testing in Salesforce DX](https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_testing.htm) · [project deploy quick](https://developer.salesforce.com/docs/platform/salesforce-cli-reference/guide/cli_reference_project_deploy_quick.html) · [Jenkins CI walkthrough](https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_ci_jenkins_sample_walkthrough.htm)
- **CumulusCI and SFDMU:** [CumulusCI configuration (`run_tests`, `required_org_code_coverage_percent`)](https://cumulusci.readthedocs.io/en/latest/config.html) · [Tasks reference](https://cumulusci.readthedocs.io/en/stable/tasks.html) · [Scratch orgs](https://cumulusci.readthedocs.io/en/latest/scratch-orgs.html) · [History](https://cumulusci.readthedocs.io/en/latest/history.html) · [CLI docs](https://github.com/SFDO-Tooling/CumulusCI/blob/main/docs/cli.md) · [SFDMU export.json JSON schema](https://forcedotcom.github.io/SFDX-Data-Move-Utility/full-documentation/export-json-file-objects-specification/json-schema-for-export-json/) · [SFDMU export.json overview](https://forcedotcom.github.io/SFDX-Data-Move-Utility/full-documentation/export-json-file-objects-specification/export-json-file-overview/) · [SFDMU configuration](https://help.sfdmu.com/configuration)
- **Robot Framework / Salesforce:** [CumulusCI Robot testing](https://cumulusci.readthedocs.io/en/latest/robot.html) · [CumulusCI Robot tutorial](https://cumulusci.readthedocs.io/en/latest/robot-tutorial.html) · [CumulusCI keywords](https://cumulusci.readthedocs.io/en/stable/Keywords.html) · [Robot advanced topics](https://cumulusci.readthedocs.io/en/stable/robot-advanced.html) · [SeleniumLibrary](https://robotframework.org/SeleniumLibrary/) · [LWC shadow DOM](https://developer.salesforce.com/docs/platform/lwc/guide/create-dom.html) · [LWC light DOM](https://developer.salesforce.com/docs/platform/lwc/guide/create-light-dom.html) · [Selenium Manager](https://www.selenium.dev/documentation/selenium_manager/) · [Pabot](https://pabot.readthedocs.io/) · [CumulusCI-CI-Demo](https://github.com/SFDO-Tooling/CumulusCI-CI-Demo)
- **LWC Jest:** [Wire utility testing](https://developer.salesforce.com/docs/platform/lwc/guide/unit-testing-using-wire-utility.html) · [Jest patterns](https://developer.salesforce.com/docs/platform/lwc/guide/unit-testing-using-jest-patterns.html) · [Create tests](https://developer.salesforce.com/docs/platform/lwc/guide/unit-testing-using-jest-create-tests.html) · [Installation](https://developer.salesforce.com/docs/platform/lwc/guide/unit-testing-using-jest-installation.html) · [Run tests](https://developer.salesforce.com/docs/platform/lwc/guide/unit-testing-using-jest-run-tests.html) · [sfdx-lwc-jest README](https://github.com/salesforce/sfdx-lwc-jest/blob/master/README.md) · [Jest coverageThreshold](https://jest-bot.github.io/jest/docs/configuration.html) · [Trailhead: mock other components](https://trailhead.salesforce.com/content/learn/modules/test-lightning-web-components/mock-other-components)
- **Python / pytest / coverage:** [pytest collection](https://docs.pytest.org/en/stable/example/pythoncollection.html) · [pytest docs](https://docs.pytest.org/en/stable/contents.html) · [unittest](https://docs.python.org/3/library/unittest.html) · [coverage.py config](https://coverage.readthedocs.io/en/7.15.4/config.html) · [coverage.py branch coverage](https://coverage.readthedocs.io/en/latest/branch.html) · [coverage.py index](https://coverage.readthedocs.io/en/latest/index.html)
- **GitHub Actions gating:** [Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) · [Troubleshooting required status checks](https://github.com/github/docs/blob/main/content/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks.md) · [Rulesets: available rules](https://docs.github.com/en/enterprise-server@3.18/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) · [Status checks](https://docs.github.com/en/pull-requests/reference/status-checks) · [Concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) · [Re-run workflows and jobs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs) · [nick-fields/retry](https://github.com/nick-fields/retry) · [zizmor](https://docs.zizmor.sh/) · [Copilot GitHub Actions best practices](https://github.com/github/awesome-copilot/blob/main/instructions/github-actions-ci-cd-best-practices.instructions.md)

Repo sources: `scripts/ai/pr_gate.py` (`CHECKS`, `STDLIB_SUITES`, `DEPS`), `cumulusci.yml` (`run_tests`, `robot*`, `run_qb_idempotency_tests`, `orgs:`), `tasks/rlm_robot_e2e.py`, `.github/workflows/prepare-rlm-org.yml`, `pyproject.toml`, `requirements-dev.txt`, `orgs/README.md`, `docs/references/architect-review-2026-09.md` (§6.A I6, F2; §7), GitNexus `context(LoadSFDMUData)` and the tests→tasks import `cypher` query.

## Appendix A: Sequential Thinking chain summary

Driven through the `sequentialthinking` MCP tool (12 thoughts, one revision; each call returned the next `thoughtNumber` and empty `branches`).

1. **Scope.** Seven guarantees ordered by blast radius: org build flows; SFDMU idempotency and credential hygiene; Apex/LWC behaviour (16 unverified classes); Python tasks (A-C1 lesson); meaningful CI gates; agent-layer config on both OSes; no security regressions.
2. **Layers today.** 53 stdlib suites + 2 pytest packages; `pr_gate.py` with 31 checks as the required gate; Apex 73/47 with `run_tests` unused; LWC 51/0; Robot 8+4 never in CI; `prepare-rlm-org` label-only; 18 shapes, 46 flows; data-plan static checks; agent-layer checks.
3. **Gaps.** G1 Apex never executed; G2 Robot never executed, `--dryrun` proves nothing; G3 gate broad but shallow (mocked unit, 45/61 untested modules); G4 zero LWC; G5 F2 masked conflict; G6 Windows checks run on Linux only; G7 workflow YAML unlinted in CI, docker-publish cron-only; G8 no coverage measurement; G9 no flaky policy.
4. **Priorities (first pass).** P0 verify wave-1 Apex/Robot on an org and assert F2; P1 nightly Apex, contract tests, Windows leg; P2 LWC, Robot e2e, flow matrix; P3 coverage, self-tests.
5. **Revision of 4.** Apex needs an org: per-PR scratch orgs are too slow and quota-hungry; choose a nightly org built by the existing `prepare-rlm-org` job plus label-triggered `RunSpecifiedTests` and static PMD on PRs. P1 becomes quota-aware.
6. **Org matrix and secrets.** Minimum matrix `dev`, `ent`, `tfid-pde` (+ `tfid-qb-tso` for e2e data); sandboxes/TFID clones are rehearsal targets, not CI; reuse the `devhub` environment, no PATs; Selenium Manager over webdriver-manager; headless via the task default.
7. **Python strategy.** Three tiers; five rules that would have caught A-C1/A-C2/A-C3/X1; coverage 85% for gate code, 60% for `tasks/` via a ratchet.
8. **Apex and LWC.** Nightly `run_tests`; per-PR label `RunSpecifiedTests`; test-class backlog for the 15 untested wave-1 classes with `System.runAs` for sharing intent; `sf code-analyzer` static check; LWC smoke test per bundle then a 50/40/50/50 threshold ratchet.
9. **Robot, data plans, CI-of-CI, agent layer.** Setup suites nightly as build steps; e2e nightly with one rerun and a quarantine tag; `run_qb_idempotency_tests` nightly plus a credential grep; `actionlint`/`zizmor` in Lint; docker-publish smoke; Windows leg; CLAUDE.md shape test instead of a paid `claude -p` run.
10. **Phasing.** TP-01…TP-12 across Phase 0–3 with disjoint ownership (as in §6).
11. **Flaky policy.** Definition, no flaky tests in PR gates, no unit-test retries, one rerun for org-backed jobs with flaky reporting, expiring quarantine, root-cause labels.
12. **Synthesis / self-check.** The three wave-1 blind spots are each covered (TP-01/TP-04, TP-03, TP-02); PR latency stays in minutes because org work is nightly or label-triggered; the `devhub` environment must allow the schedule trigger; quota budget stated; coverage targets stated per layer. Plan complete.
