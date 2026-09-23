# Architect Review — rlm-base-dev (Revenue Cloud Base Foundations)

| | |
|---|---|
| Reviewer | ARCHITECT (Claude Code, Opus 5.5) |
| Date | 2026-09-22 |
| Commit reviewed | `832a411b` on `main`. The working tree also held uncommitted GitNexus edits to `AGENTS.md` and `CLAUDE.md`, plus an untracked `.claude/skills/gitnexus/`. |
| Scope | Repo structure; build and deploy tooling; tests; CI; security; Claude Code / agent configuration; skills, commands, templates and docs |
| Mode | Read-only. This file is the only change. |

## Assumptions

1. **PR base branch is `main`.** `README.md` and `AGENTS.md` describe `main` as the Release 264 line and say it is in sync with `264`. `CONTRIBUTING.md:169` was just retargeted to `main` by commit `5b7ab3fa`. The `origin/264` references in `AGENTS.md:183,235` are therefore stale.
2. **Windows contributors are in scope.** This clone is Windows 11 with `core.symlinks=false`, and the implementation workers will run on it.
3. **The GitHub repository is public.** `pr-checks.yml:28-30` says so, which means Actions logs are public.
4. **GitNexus is a per-developer tool, not a project requirement.** The blocks it wrote into `AGENTS.md` and `CLAUDE.md` came from a local `gitnexus analyze` run and were never reviewed as project policy.
5. **Claude Code features were checked against current docs** (code.claude.com, retrieved 2026-09-22). They are not from memory. See [Sources](#sources).

---

## 1. Executive summary

The repository is mature and heavily automated:
- a 5,231-line `cumulusci.yml` with 286 tasks and 46 flows;
- about 85k lines of Python across `tasks/` and `scripts/`;
- a well-designed path-selected PR gate, `scripts/ai/pr_gate.py`;
- 32 curated agent skills, plus a self-auditing tooling analyzer.

The engineering discipline is strong. The main problems are **delivery of the agent layer** and **a few security and CI leaks**, not code quality.

**The single most important finding:** on any Windows checkout (or archive download), **Claude Code receives almost none of the project's instructions.**
- `CLAUDE.md` and all 64 skill-discovery entries (`.claude/skills/*`, `.agents/skills/*`) are git **symlinks**.
- With `core.symlinks=false` they check out as 30–45-byte text stubs. `CLAUDE.md` literally contains the text `AGENTS.md`.
- The result: no DO-NOT rules, no SFDMU rules, no push discipline, and zero of the 32 skills in Claude Code or Codex.
- A local `gitnexus analyze` then appended about 3 KB of generic "MUST run impact analysis before editing any symbol" rules into both files. Committing that would push `AGENTS.md` over the repo's own 25 KB budget. It would also re-point the `CLAUDE.md` **symlink** at a 46-line string, breaking it on macOS and Linux too.
- The current Claude Code docs explicitly recommend a real `CLAUDE.md` containing `@AGENTS.md` instead of a symlink on Windows ([memory docs](https://code.claude.com/docs/en/memory)).

Other high-priority items:
- **Live org access tokens are written to logs.** `tasks/rlm_sfdmu.py:262` logs the full `export.json` including `accessToken`; lines 416 and 1391 log a command line that can contain the token. The command also runs with `shell=True`. This executes in 25 build-flow steps, including the public CI `prepare-rlm-org` workflow.
- **There is no shared Claude Code configuration.** The repo has no `.claude/settings.json` (permissions or secret-read denies), no hooks, no `.claude/rules/`, no subagents and no `.mcp.json`. `.gitignore:118` (`.claude/*`) would silently drop them if anyone added them.
- **`AGENTS.md` (443 lines, 24.6 KB) is more than 2× the recommended size** for an always-loaded memory file. The docs recommend under 200 lines. Guidance is duplicated in up to 7 places: the review protocol ×7, the SFDMU rules ×5, the skill index ×3+.
- **Release identity (260/262/264, v67/v68) is hand-written in about 8 places** and has already drifted: the manifest, `model-routing.md`, `CONTRIBUTING.md` and `AGENTS.md` disagree.
- **CI gaps:**
  - no Dependabot, although a workflow comment claims it exists;
  - Actions pinned only by tag;
  - no ESLint, Prettier, Jest or Python lint in CI;
  - Apex tests never run automatically;
  - the Dev Hub secret is interpolated inline in shell with no protected environment;
  - the Claude review workflow re-runs, and is billed, on every push and every label event.

**Ten work packages** (§5) address all of this. Seven have no dependencies, two have a merge-order dependency only, and one is a final integration pass. File ownership is disjoint.

---

## 2. Findings

Severity: **C** = critical, **H** = high, **M** = medium, **L** = low.

### 2.1 Agent instruction layer (CLAUDE.md, AGENTS.md, skills discovery)

| # | Sev | Finding | Evidence |
|---|---|---|---|
| A1 | **C** | **`CLAUDE.md` is a symlink.** On Windows or archive checkouts it becomes a text stub reading `AGENTS.md`, so Claude Code loads none of the `AGENTS.md` rules. The instructions injected into this session contained only the stub plus the GitNexus block. Current docs: on Windows, "use the `@AGENTS.md` import instead… Git checks a committed symlink out as a plain text file unless `core.symlinks` is enabled." | `git ls-files -s CLAUDE.md` → mode `120000`; `git config core.symlinks` → `false` |
| A2 | **C** | **The uncommitted GitNexus append must not be committed.** Git still records `CLAUDE.md` as mode 120000, so committing would turn the symlink target into a 46-line string and break it on every OS. The append also takes `AGENTS.md` from 24,642 to 27,570 bytes, which fails the repo's own budget gate. `python scripts/ai/analyze_agent_tooling.py check` → FAIL 2/13. | `git diff CLAUDE.md AGENTS.md`; budget check at `scripts/ai/analyze_agent_tooling.py:825` |
| A3 | **H** | **All 32 repo skills are invisible to Claude Code and Codex on Windows.** The 64 discovery entries are symlink stubs. Nothing warns at runtime. The limitation is documented, but only a manual catalog fallback is offered. | `.claude/skills/*`, `.agents/skills/*` (33–44-byte files); `docs/guides/agent-skill-discovery.md:60-90` |
| A4 | **H** | **The GitNexus block doesn't fit this repo.** It says "MUST run impact before editing any symbol" and "NEVER commit without detect_changes()", but most edits here are YAML, CSV, XML and Markdown. It hard-codes `base_ref: "main"` against the gate's `origin/264`, embeds symbol counts that go stale, and points at an untracked, doubly nested `.claude/skills/gitnexus/*`. That path is re-included by `.gitignore:121` (`!.claude/skills/`), so `git add .` would publish it. The GitNexus index is also degraded: FTS indexes are missing and there is no PDG/taint layer. | `AGENTS.md:400-443` (working tree); `.gitignore:118-121`; GitNexus `query` warning "FTS indexes missing"; `explain` → "no taint layer" |
| A5 | **H** | **`AGENTS.md` is 443 lines / 24.6 KB and always loaded.** Docs recommend under 200 lines per memory file and moving topic rules to path-scoped `.claude/rules/`. It carries the full SFDMU rules (`:112-157`), the Context Service rules (`:370-376`), a skill index table (`:294-331`), a script reference and documentation conventions (`:381-396`). All of these load on every turn. | `AGENTS.md`; [memory docs](https://code.claude.com/docs/en/memory), [best practices](https://code.claude.com/docs/en/best-practices) |
| A6 | **M** | **Content is duplicated across many files, and the copies drift.** Review protocol: 7 copies. SFDMU rules: 5. Skill index: 3+. The "rated zero" usage diagnosis: 3. | Review protocol: `AGENTS.md:260-283`, `REVIEW.md:104-150`, `audit-review/SKILL.md`, `merge-and-review-procedures.md`, `.claude/commands/pr-review.md`, `CONTRIBUTING.md` §9, `.agents/adapters/claude-code.md:20-23`. SFDMU: `AGENTS.md:112-157`, `.cursor/rules/sfdmu-*.mdc`, `sfdmu-data-plans/SKILL.md`, `CONTRIBUTING.md:74` |
| A7 | **M** | **Release and branch identity is hand-written in about 8 places and has drifted.** `CONTRIBUTING.md:169` says target `main`, while `AGENTS.md:183,235` say gate against `origin/264`. `.agents/model-routing.md:13` still says "Release 262". `AGENTS.md:33` says 264 has "no release notes", yet `docs/salesforce/264/help/` exists and is dated 2026-09-07. | `AGENTS.md:27-37`, `README.md:14,137-146`, `docs/index.md:101-105`, `.agents/context/project-map.md:7-12`, `.agents/context/project-memory.json`, `.claude/skill-manifest.yml` header |
| A8 | **M** | **`.claude/skill-manifest.yml` is stale.** Its `--check` only tests that paths resolve, so these pass:<br>• `erd_data` says 262 / v67.0 / 4,190 fields; `docs/erds/erd-data.json` says 264 / v68.0 / 4,252.<br>• `help_corpus_active` says "264 Help has not published".<br>• The `rlm-business-apis` caveat says v67.0.<br>• The header references the unfinished "Phase 6.3" and gitignored `.agents/artifacts/`. | `.claude/skill-manifest.yml:114,438-474,7-31` |
| A9 | **M** | **`skill_manifest.py --check` fails in any clone whose directory isn't named `rlm-base-dev`.** It never falls back to the repo that contains the manifest. Its em-dashes also print as `�` on the Windows console. | `scripts/ai/skill_manifest.py` (run from `rlm-base-dev-fork`) |
| A10 | **M** | **`.gitignore:118` ignores `.claude/*`** and re-includes only `skill-manifest.yml`, `commands/` and `skills/`. A shared `settings.json`, `rules/`, `agents/` or `hooks/` would be silently dropped. | `.gitignore:114-121` |
| A11 | **L** | **The agent adapters and README assert that `CLAUDE.md` is a symlink** and never mention the Windows failure mode. | `.agents/adapters/claude-code.md:12,27`, `.agents/README.md:27-28`, `AGENTS.md:15` |

### 2.2 Skills, commands, rules and templates

All 32 skills have valid frontmatter. Each `name` matches its directory and fits the spec, and each `description` is ≤1024 characters and includes a "Use when…" trigger. The analyzer's metadata and navigation-link checks pass.

| # | Sev | Finding | Evidence |
|---|---|---|---|
| S1 | **M** | **6 SKILL.md bodies exceed the 500-line guidance**, and 3 of them have no sub-files. The limit comes from the [Claude Code skills docs](https://code.claude.com/docs/en/skills) and the [Agent Skills spec](https://agentskills.io/specification). | troubleshooting 670, document-generation 646, pricing-wiring 566, expression-sets 558, constraint-models 521, ramped-quotes 512 |
| S2 | **M** | **Public skills link into gitignored `.agents/artifacts/`**, so those links are dead for every other clone. | `pmos-integration/SKILL.md:125-143` (10 links); schema-validation, qb-demo-script, revenue-cloud-data-model, inapp-framework, revenue-cloud-docs (1–4 each) |
| S3 | **M** | **`troubleshooting` repeats every domain skill's error catalog** instead of routing to it. The usage "rated zero" diagnosis exists 3×. | `troubleshooting/SKILL.md:362-458`, `usage-consumption/verification.md`, `docs/guides/usage-consumption-runbook.md:304-312` |
| S4 | **L** | **Some descriptions spend always-loaded tokens on volatile detail.** Descriptions share a budget of about 1% of context. Examples: `revenue-cloud-docs` is 819 characters; version pins and counts appear in `rlm-business-apis` and `revenue-cloud-data-model`; `release-enablement` has a stale "(260, 262…)". | `.cursor/skills/*/SKILL.md` frontmatter |
| S5 | **L** | **Change logs and dated history sit in skill bodies.** | `revenue-cloud-docs/SKILL.md:345`, `release-enablement/SKILL.md:214,255` |
| S6 | **L** | **`cci-orchestration/tasks-reference.md` is 3,788 lines with no TOC.** | `.cursor/skills/cci-orchestration/tasks-reference.md` |
| S7 | **L** | **15 of 32 skills lack the house sections** (Entry Conditions, Examples, Validation Checks). 3 of them also lack DO NOT. | `AGENTS.md:333-336` acknowledges this |
| S8 | **L** | **audit-review Quick Rule 5 says "never stage `cumulusci.yml`".** That contradicts `AGENTS.md:214-215`, which requires committing `cumulusci.yml` edits. | `audit-review/SKILL.md` |
| S9 | **L** | **Commands lack `allowed-tools`.** `/pr-review` could pre-approve `python scripts/ai/pr_review.py`. `build-pde-dev-r1` exists only as a Cursor command. | `.claude/commands/pr-review.md`, `.cursor/commands/build-pde-dev-r1.md` |
| S10 | **L** | **No SKILL.md template exists, and `skill-authoring` gives no hard line budget.** It also requires symlinks without offering a Windows-safe path. `templates/` holds UX metadata, not authoring templates. | `.cursor/skills/skill-authoring/SKILL.md` |
| S11 | **L** | **The 12 `.cursor/rules/*.mdc` files have no Claude Code equivalent.** Claude Code supports `.claude/rules/*.md` with `paths:` globs, and `.agents/context/rule-skill-coverage.md` already lists missing high-risk rules (post_ux, profiles, objects, `rlm.network-meta.xml`). | `.cursor/rules/`, `.agents/context/rule-skill-coverage.md` |

### 2.3 Claude Code project configuration (missing pieces)

| # | Sev | Finding | Evidence / recommendation basis |
|---|---|---|---|
| K1 | **H** | **There is no `.claude/settings.json`.** Without it there are no shared permission rules. In particular there are no denies on reading `.env`, `*.key` or org auth files, and no pre-approvals for the read-only gates (`pr_gate.py`, `analyze_agent_tooling.py check`). Deny and ask rules apply even before workspace trust. | [settings](https://code.claude.com/docs/en/settings), [permissions](https://code.claude.com/docs/en/permissions) |
| K2 | **M** | **There are no hooks.** The DO-NOT rules are only advisory. The docs frame CLAUDE.md as advisory and hooks as deterministic. Candidates:<br>• block Edit/Write to generated output (`unpackaged/post_ux/**`, `datasets/bre/**`, `datasets/dx/**`);<br>• a SessionStart warning when skill links are stubs (A3). | [hooks guide](https://code.claude.com/docs/en/hooks-guide) |
| K3 | **M** | **There are no `.claude/agents/`.** Natural candidates are a REVIEW.md-driven read-only reviewer and an SFDMU plan auditor. | [sub-agents](https://code.claude.com/docs/en/sub-agents) |
| K4 | **L** | **There is no `.mcp.json`.** GitNexus and Salesforce DX MCP are configured per user only. Opt-in project servers are a reasonable later addition. | [mcp](https://code.claude.com/docs/en/mcp) |
| K5 | **L** | **The docs corpus drowns search.** `docs/salesforce/` holds 6,015 help-corpus files (43 MB of `docs/` across 262 and 264). They dominate Grep and GitNexus results and inflate the index (8,292 files indexed). No rule tells agents to scope searches to `docs/salesforce/264/`. | `git ls-files docs/salesforce \| wc -l` |

### 2.4 Security

| # | Sev | Finding | Evidence |
|---|---|---|---|
| X1 | **H** | **Org access tokens are logged.**<br>• `accessToken` is injected into `export.json`, then the whole file is logged at INFO.<br>• For non-scratch orgs, `targetusername` falls back to `org_config.access_token`, so the token also appears in the logged, `shell=True` command line and in the process list.<br>• This runs in 25 flow steps, including public CI `prepare-rlm-org` runs.<br>• The class's own comment at `:777` warns against exactly this. | `tasks/rlm_sfdmu.py:252-262, 394-417, 1377-1393` |
| X2 | **M** | **The token is written into a tracked file.** It goes into `export.json` under `datasets/…`, and only a `finally` block removes it, so a killed process leaves the token in a file that can be committed. | `tasks/rlm_sfdmu.py:252-260, 825-827` |
| X3 | **M** | **The Dev Hub `SFDX_AUTH_URL` is interpolated inline in shell** (`echo "${{ secrets… }}"`) in a job that runs PR code when a label is applied. There is no protected `environment:`, and checkout keeps its credentials. The label trigger limits this to same-repo branches. | `.github/workflows/prepare-rlm-org.yml:19-20,124-135` |
| X4 | **M** | **`SF_TEMP_SHOW_SECRETS=true` is set shell-wide and image-wide.** CI already scopes it per step. | `.envrc:48`, `docker/Dockerfile:41` vs `prepare-rlm-org.yml:239-261` |
| X5 | **M** | **A hard-coded admin password `Cumulus1234!` is set by a task with no scratch-org guard.** The flow guards the call, but `cci task run set_scratch_org_password --org <sandbox>` does not. | `scripts/apex/setScratchOrgPassword.apex:13`, `robot/rlm-base/resources/SetupToggles.robot:18`, `cumulusci.yml:2234` |
| X6 | **M** | **An agent action can update any sObject in `SYSTEM_MODE`.** It is labelled demo code, but the result is that prompt injection can edit any object. | `unpackaged/post_agents/classes/RLM_AI_UpdateRecordFieldsService.cls:155-165,239` |
| X7 | **M** | **Apex classes without explicit sharing.** 13 non-test classes declare no sharing mode. `RLM_AssetInfoUtility` is `without sharing` and exposes an `@InvocableMethod`. | `force-app/main/default/classes/RLM_PlaceQuoteModel.cls`, `unpackaged/pre/4_tax/*.cls`, `RLM_AssetInfoUtility.cls:1` |
| X8 | **M** | **67 of 101 `requests.*` calls have no timeout.** | `scripts/cml/import_cml.py` (14), `tasks/rlm_cml.py` (7), `tasks/rlm_manage_fulfillment_scope_cnfg.py` (6), `scripts/docgen/docgen_template_manage.py` (6) |
| X9 | **L** | **Ignore-file gaps.**<br>• `.gitignore` lacks `.env.*`, `*.key`, `*.pem`.<br>• `.dockerignore` lacks `.agents/artifacts/` (marked "MUST NOT ship"), `extracted/`, `datasets/sfdmu/extractions/`, `.gitnexus/` and `.claude/settings.local.json`, and the Dockerfile does `COPY .`. | `.gitignore`, `.dockerignore`, `docker/Dockerfile:106` |
| X10 | **L** | **One org's My Domain and Org ID are embedded in an OmniScript image URL.** This leaks that org, and the image breaks everywhere else. | `unpackaged/post_guidedselling/omniScripts/QuantumBit_GuidedSelling_English_1.os-meta.xml:202,367` |
| X11 | **L** | **`SECURITY.md` is generic**, with no supported-versions or scope section. | `SECURITY.md` |

No hard-coded real secrets were found (AWS/GitHub/Anthropic key patterns, private keys, `force://` URLs). There is no unsafe `yaml.load` and no `eval` outside tests.

### 2.5 CI and supply chain

| # | Sev | Finding | Evidence |
|---|---|---|---|
| C1 | **M** | **The `claude-code-review.yml` trigger re-runs a paid review too often.** It fires on `[labeled, synchronize]` and only checks that the `claude-review` label is present, so adding *any* label or pushing any commit re-runs it. There is no concurrency group or timeout, and the plugin marketplace is taken unpinned from HEAD. | `.github/workflows/claude-code-review.yml:3-11` |
| C2 | **M** | **`claude.yml` is correctly limited to OWNER/MEMBER/COLLABORATOR, but its runs are unbounded.** It grants `contents: write` on every run, with no `timeout-minutes`, no concurrency and no `--max-turns` / `--allowedTools` in `claude_args`. `issues: edited` re-fires on every edit. The action's security guide also warns about hidden-markdown prompt injection. | `.github/workflows/claude.yml:15-43`; [action security](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md) |
| C3 | **M** | **Actions are pinned by tag, and there is no Dependabot.** Only `peter-evans/create-pull-request` is SHA-pinned, and its comment says "Bump via Dependabot", but there is no `.github/dependabot.yml`. | `agent-tooling-optimization.yml:110`; `ls .github/dependabot.yml` → missing |
| C4 | **M** | **`docker-publish.yml` has two problems.**<br>• It always pushes `:latest`, even when dispatched from any branch.<br>• It interpolates `github.event.inputs.*` directly into shell, and uses `checkout@v4` while other workflows use v6. | `.github/workflows/docker-publish.yml:59-60,94` |
| C5 | **M** | **Tool versions drift.**<br>• CumulusCI minimum is 4.0.0; CI and the gate pin 4.8.1.<br>• The Dockerfile installs latest CumulusCI, `sf` and `sfdmu` unpinned, via `curl \| bash`.<br>• Comments mention 4.10.x.<br>• CI pins Node 24.16.0 because 24.17 broke `sf org login`, so the image can ship the known-bad combination. | `cumulusci.yml:2`, `scripts/ai/pr_gate.py:82`, `prepare-rlm-org.yml:216`, `docker/Dockerfile:82` |
| C6 | **M** | **No JS or Python lint, and no Jest, in CI.** ESLint and Prettier are configured but not enforced, and already fail on main (`CONTRIBUTING.md:135-139`). There is no ruff or flake8 config, even though `# noqa` is used throughout. There is no pre-commit config and no `.editorconfig`. | `eslint.config.mjs`, `.prettierrc`, `pyproject.toml`, `.github/workflows/pr-checks.yml` |
| C7 | **L** | **No pip cache in CI.** pr-checks tests only Python 3.13, although the floor is 3.11. `package-lock.json` is gitignored (`.gitignore:62`), so npm installs are not reproducible. | `pr-checks.yml`, `.gitignore:56,62` |

### 2.6 Build and deploy tooling, code quality, tests

| # | Sev | Finding | Evidence |
|---|---|---|---|
| B1 | **M** | **`cumulusci.yml` is 5,231 lines / 247 KB.** It has 286 tasks, 46 flows and 166 flags. 164 tasks share one group and 26 have none. It contains near-clones: 24 `SnapshotSalesforceHelp` tasks, 22 Extract, 21 Idempotency and 29 SFDMU loads. CumulusCI has no include mechanism, so the lever is to parameterize the clones. | `cumulusci.yml` |
| B2 | **M** | **45 of 61 `tasks/*.py` modules have no test,** including the most-called ones: `rlm_context_service` (1,659 lines; `_make_request` has 22 callers per GitNexus), `rlm_ux_assembly` (1,522) and `rlm_writeback_ux` (1,458). | `tasks/`, `tests/` |
| B3 | **M** | **The two expression-set schema validators have drifted.** The vendored copy differs by 61 lines, and only the copy validates `labels`. No parity test exists. | `scripts/expression_sets/_schema.py` vs `tasks/expression_set_schema.py` |
| B4 | **M** | **REST boilerplate is duplicated.** 27 task files build their own Bearer headers. `_api_version` is defined 12×, `_headers` 11× and `_make_request` 5×, and `"68.0"` is hard-coded about 15×. | `tasks/*.py` |
| B5 | **M** | **No LWC Jest tests.** There are 51 LWCs and 0 Jest tests. There are about 47 Apex test classes, but none run in CI. | `force-app/**/lwc`, `CONTRIBUTING.md:108` |
| B6 | **L** | **Error handling hides failures.** There are 8 `except Exception: pass` blocks. `rlm_sfdmu.py:23-35` turns an ImportError into a later NameError. `rlm_configure_search_index.py:393-666` holds about 270 lines of `__main__` self-tests that never run. | `tasks/` |
| B7 | **L** | **Probably-dead code:** `tasks/rlm_modify_context.py` (legacy, not wired) and 3 unreferenced `scripts/compare_*` / `reconcile_*` scripts. 90 tasks are in no flow; they are run from the CLI, so check before removing. | `tasks/`, `scripts/` |
| B8 | **L** | **Two ways to run tests.** pytest `testpaths` covers only the harness directories; top-level suites run as `python tests/x.py`. `pr_gate.py --all` is the one documented entry point and papers over this. | `pyproject.toml`, `scripts/ai/pr_gate.py:384-455` |
| B9 | **L** | **Local setup doesn't work on Windows.** `.envrc` needs `brew`, and `tui-cci` assumes a `bin/python` venv. | `.envrc`, `tui-cci` |
| B10 | **L** | **The generated `docs/analysis/tooling-optimization-report.md` breaks the repo's own rule** against generated analysis in `docs/analysis/`. `docs/index.md` doesn't link the ERD or API docs. | `.cursor/rules/analysis-artifacts.mdc:17-18`, `docs/index.md` |

### 2.7 Strengths worth preserving

- **`pr_gate.py`** selects suites by path, fails rather than skipping when dependencies are missing, and CI runs it with least privilege, concurrency and `persist-credentials: false`.
- **`analyze_agent_tooling.py`** self-audits the agent layer. It caught A2 and A3 immediately.
- **Skill metadata quality is high.** The disambiguation between pricing-wiring, expression-sets and decision-tables, and between odt-authoring and document-generation, is exemplary.
- **`claude.yml` restricts triggers by `author_association`**, and `claude-code-review.yml` guards against forks.

---

## 3. Recommendations (prioritized)

**P0: immediately, before any other agent-layer change is committed**
1. **Do not commit the GitNexus edits** to `AGENTS.md` / `CLAUDE.md` or `.claude/skills/gitnexus/`. Revert them with `git checkout -- AGENTS.md CLAUDE.md`. Keep GitNexus guidance at user scope (`~/.claude/CLAUDE.md` or user skills), where it already lives as a hook. (A2, A4)
2. **Stop leaking tokens.** Redact `orgs[].accessToken` before logging, drop the access-token-as-username fallback in favour of `_get_org_for_cli`, switch to list-args `subprocess.run`, and write `export.json` to a temp copy. (X1, X2) → WP-07

**P1: agent-layer correctness on every OS**

3. **Replace the `CLAUDE.md` symlink with a regular tracked file:** `@AGENTS.md` plus at most about 15 Claude-specific lines. This follows the [official Windows guidance](https://code.claude.com/docs/en/memory). Update the analyzer check and the adapters to match. (A1, A11) → WP-01
4. **Make skills work on Windows without Developer Mode.**
   - Add `scripts/ai/link_skills.py`. It replaces stub files with directory **junctions**, which need no admin rights, and marks them `skip-worktree` so git stays clean.
   - Add a SessionStart hook that detects stubs and tells the user to run it.
   - Longer term, consider an ADR on making `.claude/skills/` the canonical real directory.

   (A3) → WP-03, with the analyzer message in WP-01
5. **Slim `AGENTS.md` to 150 lines or fewer (12 KB or less).** Keep:
   - the overview;
   - the DO-NOT list, one line each with a link, because it is universal across tools;
   - org and alias identity;
   - the pre-PR command;
   - a one-sentence review rule;
   - a pointer to the skill catalog.

   Move SFDMU, Context Service and doc conventions into path-scoped rules generated from `.cursor/rules/*.mdc`, so there is one source and both tools get them. (A5, A6, S11) → WP-01 + WP-02
6. **Add the shared Claude Code config.**
   - Change `.gitignore` negations so the files are tracked.
   - Add `.claude/settings.json`: `$schema`; deny reading secrets; allow the read-only gates; ask for `cci flow run`, `sf project deploy` and `git push`; deny force-push.
   - Add a PreToolUse hook that blocks edits to generated directories.

   (K1, K2, A10) → WP-03

**P2: consistency and CI hardening**

7. **Single source for release and branch identity** (proposed: `.agents/context/project-memory.json`). `skill_manifest.py --check` should fail on drift and compare release and counts against `erd-data.json` and the Help `manifest.json`. Refresh the stale manifest entries and fix the PR-base contradiction (target `main`). (A7, A8, A9) → WP-06
8. **CI hardening.**
   - Protected environment plus `env:` for `SFDX_AUTH_URL`.
   - Fix the claude-code-review trigger, and add concurrency, timeouts and `claude_args` limits to both Claude workflows.
   - Add Dependabot and SHA-pin write-scoped actions.
   - Pin tool versions in one file consumed by the Dockerfile and workflows.
   - Stop pushing `:latest` on dispatch.
   - Add a diff-only lint job (ESLint, Prettier, ruff).

   (X3, X4, C1–C7) → WP-09
9. **Skill hygiene.**
   - Split the six >500-line skills; make troubleshooting a router.
   - Trim volatile descriptions.
   - Annotate or remove private links.
   - Add a TOC to `tasks-reference.md`.
   - Add a SKILL.md template and a 500-line budget.
   - Add `allowed-tools` to `/pr-review`.

   (S1–S10) → WP-04
10. **Python task quality.**
    - Add a shared REST helper with a default timeout (X8, B4).
    - Add an expression-set schema parity test or merge the two copies (B3).
    - Add tests for `rlm_context_service` request handling (B2).

    → WP-08

**P3: follow-ups, no WP yet**
- Parameterize the cloned CCI tasks (B1). This is large and needs its own design, so it should get an ADR first.
- LWC Jest baseline and a scheduled Apex test flow (B5).
- Re-index GitNexus with `--force --pdg`, excluding `docs/salesforce/**` (A4, K5).

---

## 4. Contracts shared between work packages

These names are fixed now, so packages can proceed in parallel and link to each other before they merge.

| Contract | Owner | Consumers |
|---|---|---|
| **Rule files** in `.claude/rules/`: `sfdmu-export-json.md`, `sfdmu-csv-data.md`, `cci-task-definitions.md`, `cci-python-tasks.md`, `apex-scripts.md`, `apex-classes.md`, `lwc-components.md`, `ux-templates.md`, `robot-tests.md`, `context-plans.md`, `doc-review.md`, `protected-metadata.md` (new: profiles, `*.object-meta.xml`, `rlm.network-meta.xml`, `templates/flexipages/**`), `docs-conventions.md` (new). Each is generated from a same-named `.cursor/rules/*.mdc`. | WP-02 | WP-01 links to them from `AGENTS.md` |
| **Skill-link repair script** at `scripts/ai/link_skills.py` (`--check` exits 1 if any stub is present; `--fix` creates junctions or symlinks). | WP-03 | The WP-01 analyzer message, the WP-03 SessionStart hook, and the WP-01 edit to `docs/guides/agent-skill-discovery.md` |
| **Rules sync script** at `scripts/ai/sync_claude_rules.py` (`--check` / `--write`). | WP-02 | WP-10 registers it in `pr_gate.py` |
| **Tool versions file** at `config/tool-versions.env` (`CUMULUSCI_VERSION`, `SF_CLI_VERSION`, `SFDMU_VERSION`, `NODE_VERSION`, `PYTHON_VERSION`). | WP-09 | WP-10 points `pr_gate.py:82` at it |
| **Release identity source** at `.agents/context/project-memory.json` (keys `release_active`, `release_prior_ga`, `api_version_active`, `pr_base_branch`). | WP-06 | WP-01 refers to it in prose |
| **New test files are not registered in `pr_gate.py` by their authors.** Each author lists them in the PR description, and WP-10 registers them all. | all | WP-10 |

---

## 5. Work Packages

Rules for workers:
- Edit **only** the files you own.
- Read anything you like.
- Do not commit on `main`. Branch `wp-XX-<slug>` and open the PR against `main`.
- Run `python scripts/ai/pr_gate.py --base origin/main` before the PR.
- On this Windows clone, create **regular files, not symlinks**.

| id | title | owned files/dirs (exclusive) | dependencies | acceptance criteria | size |
|---|---|---|---|---|---|
| **WP-01** | Windows-safe instruction layer; slim AGENTS.md | `CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `.agents/README.md`, `.agents/adapters/**`, `.agents/model-routing.md`, `scripts/ai/analyze_agent_tooling.py`, `tests/test_agent_launch_checks.py`, `docs/guides/agent-skill-discovery.md` | none | 1. GitNexus blocks removed from `AGENTS.md` and `CLAUDE.md`.<br>2. `CLAUDE.md` is a **regular file** (`git ls-files -s CLAUDE.md` shows mode `100644`) whose first line is `@AGENTS.md`, followed by ≤15 Claude-specific lines: skill-stub note, `docs/salesforce/264/` search scope, "generated analysis goes to `.agents/artifacts/`".<br>3. `AGENTS.md` ≤150 lines and ≤12,288 bytes. Keeps a one-line DO-NOT list. SFDMU, Context Service and doc-conventions detail is replaced by links to the §4 rule files. Skill index and script reference are replaced by a link to `.cursor/skills/README.md` and `scripts/ai/README.md`. Gate base is `origin/main`.<br>4. The analyzer accepts a regular `CLAUDE.md` containing `@AGENTS.md`. Its budget constant is lowered to 12,288. Its skill-link check names `scripts/ai/link_skills.py --fix` in the failure message.<br>5. Adapters and the discovery guide describe the import, not a symlink, and give the Windows fix.<br>6. `python scripts/ai/analyze_agent_tooling.py check` passes on Linux CI. | M |
| **WP-02** | Path-scoped rules for Claude Code, generated from Cursor rules | `.claude/rules/**` (new), `.cursor/rules/**`, `scripts/ai/sync_claude_rules.py` (new), `tests/test_sync_claude_rules.py` (new) | WP-03 (merge order only: `.gitignore` negation for `.claude/rules/`) | 1. Every §4 rule exists as `.cursor/rules/<n>.mdc` (source) and `.claude/rules/<n>.md` (generated). `globs` becomes `paths:` YAML list; always-apply becomes no `paths`.<br>2. New `protected-metadata` and `docs-conventions` rules carry the moved `AGENTS.md` content verbatim (DO NOT #2, #3, #6, #7 detail; `AGENTS.md:381-396`).<br>3. `analysis-artifacts` stays Cursor-only; WP-01 covers it in `CLAUDE.md`.<br>4. `sync_claude_rules.py --check` exits 0 when in sync and 1 on drift. The test covers both and runs standalone with `python tests/test_sync_claude_rules.py` using stdlib only.<br>5. Narrow globs, e.g. `datasets/sfdmu/**/export.json`. | M |
| **WP-03** | Shared Claude Code settings, hooks and Windows skill-link repair | `.gitignore`, `.claude/settings.json` (new), `.claude/hooks/**` (new), `scripts/ai/link_skills.py` (new), `tests/test_link_skills.py` (new) | none | 1. `.gitignore` re-includes `.claude/settings.json`, `.claude/rules/`, `.claude/agents/` and `.claude/hooks/`. It ignores `.claude/skills/gitnexus/`, `.env.*`, `*.key`, `*.pem` and `.gitnexus/`. `.claude/settings.local.json` stays ignored.<br>2. `settings.json` carries `"$schema": "https://json.schemastore.org/claude-code-settings.json"`.<br>3. `permissions.deny`: `Read(./.env)`, `Read(./.env.*)`, `Read(//**/*.key)`, `Bash(git push --force *)`, `Bash(git push * main)`.<br>4. `permissions.ask`: `Bash(cci flow run *)`, `Bash(sf project deploy *)`, `Bash(git push *)`.<br>5. `permissions.allow`: `Bash(python scripts/ai/pr_gate.py *)`, `Bash(python scripts/ai/analyze_agent_tooling.py check*)`, `Bash(cci task info *)`, `Bash(cci flow info *)`. No `defaultMode`.<br>6. PreToolUse hook (`Edit\|Write`) is a Python script invoked as `python "$CLAUDE_PROJECT_DIR/.claude/hooks/protect_generated.py"`. It exits 2 for `unpackaged/post_ux/**`, `datasets/bre/**` and `datasets/dx/**`, with a reason naming the generator. It must be self-contained, because claude-code-action restores `.claude/` from base.<br>7. A SessionStart hook runs `link_skills.py --check` and prints a one-line fix hint. It never blocks.<br>8. `link_skills.py --fix` creates directory junctions on Windows (`mklink /J`, no admin rights) and symlinks elsewhere, then runs `git update-index --skip-worktree` on the paths. `--check` is idempotent.<br>9. The test covers stub detection and `--check` exit codes on a temp dir.<br>10. Verified manually: after `--fix`, a new Claude Code session on this clone lists the 32 repo skills. | M |
| **WP-04** | Skill and command hygiene | `.cursor/skills/**` (includes `README.md`), `.claude/commands/**`, `.cursor/commands/**` | none | 1. No SKILL.md over 500 lines. troubleshooting, document-generation, pricing-wiring, expression-sets, constraint-models and ramped-quotes are split into one-level-deep sub-files. troubleshooting becomes a router to domain skills.<br>2. Descriptions: `revenue-cloud-docs` ≤400 characters; `pmos-integration` and `release-enablement` trimmed; no release numbers, API versions or object and field counts in any `description`.<br>3. Change logs and dated history removed from bodies.<br>4. Every link into `.agents/artifacts/` is removed or marked "(private tracker; may be absent)".<br>5. TOC added to `cci-orchestration/tasks-reference.md`.<br>6. `skill-authoring` states a hard 500-line budget and a Windows-safe link step (`link_skills.py`), and ships `skill-authoring/SKILL_TEMPLATE.md`.<br>7. The review protocol lives canonically in `audit-review`; `/pr-review` points to it.<br>8. audit-review Quick Rule 5 is reworded to "local-only flag flips".<br>9. `/pr-review` gains `allowed-tools: Bash(python scripts/ai/pr_review.py *)`. New `.claude/commands/build-pde.md` mirrors the Cursor command.<br>10. The analyzer checks "skill discovery metadata" and "skill navigation links" still pass. | L |
| **WP-05** | Project subagents | `.claude/agents/**` (new) | WP-03 (merge order only: `.gitignore` negation) | 1. `rlm-reviewer.md` has `tools: Read, Grep, Glob, Bash`, applies `REVIEW.md` to the current diff, and outputs findings by severity, read-only.<br>2. `sfdmu-plan-auditor.md` validates `datasets/sfdmu/**` plans against the `sfdmu-data-plans` skill (preloaded via `skills:`) and runs `scripts/validate_sfdmu_v5_datasets.py`.<br>3. Both have precise `description` triggers and `model` unset (inherit).<br>4. Frontmatter uses only documented fields ([sub-agents](https://code.claude.com/docs/en/sub-agents)). | S |
| **WP-06** | Release identity single source; docs and manifest refresh | `.agents/context/**`, `.claude/skill-manifest.yml`, `scripts/ai/skill_manifest.py`, `tests/test_skill_manifest_audit.py`, `README.md`, `CONTRIBUTING.md`, `REVIEW.md`, `SECURITY.md`, `docs/index.md`, `docs/references/**`, `docs/analysis/**` | none | 1. `project-memory.json` holds `release_active` (264), `release_prior_ga` (262), `api_version_active` (v68.0) and `pr_base_branch` (main).<br>2. `skill_manifest.py --check` fails when the manifest, README, CONTRIBUTING or `docs/index.md` disagree with it. It also compares `erd_data` and `help_corpus_active` against `docs/erds/erd-data.json` and `docs/salesforce/264/help/manifest.json`.<br>3. `--check` falls back to the manifest's own repo root when sibling paths are absent, so it passes in `rlm-base-dev-fork`. Output is ASCII-safe on a Windows console.<br>4. Stale manifest entries are refreshed; "Phase 6.3" and "Sandy will mirror" are removed.<br>5. `docs/analysis/tooling-optimization-report.md` is moved out, or its generator note is updated.<br>6. `docs/index.md` links ERD and API docs.<br>7. `SECURITY.md` gains scope and supported branches.<br>8. The test covers the drift failure. | M |
| **WP-07** | Security fixes: token handling, password, Apex | `tasks/rlm_sfdmu.py`, `tests/test_rlm_sfdmu_redaction.py` (new), `scripts/apex/setScratchOrgPassword.apex`, `robot/rlm-base/resources/SetupToggles.robot`, `unpackaged/post_guidedselling/omniScripts/QuantumBit_GuidedSelling_English_1.os-meta.xml`, all `*.cls` under `force-app/**` and `unpackaged/**` | none | 1. No log line emits `accessToken` or any token-shaped value. The test feeds a fake token and asserts it is absent from captured logs and from the command string.<br>2. The access-token-as-username fallback is removed.<br>3. `subprocess.run` uses list args, never `shell=True`.<br>4. `export.json` with credentials is written only to a temp directory, never under `datasets/`.<br>5. The password Apex aborts unless `[SELECT IsSandbox, TrialExpirationDate FROM Organization]` indicates a scratch org. The password comes from an option or env var with a random default. The Robot resource reads it from a variable.<br>6. `RLM_AI_UpdateRecordFieldsService` gets an object allowlist (Quote, QuoteLineItem, Opportunity) and uses `USER_MODE`.<br>7. Each of the 13 classes gets an explicit sharing declaration (`with sharing` or `inherited sharing`); `RLM_AssetInfoUtility` is justified or changed.<br>8. The hard-coded org URL in the OmniScript is replaced with a relative or static-resource reference.<br>9. Existing `tests/test_sfdmu_*` still pass. Apex changes are validated with `sf project deploy validate` or a scratch-org run noted in the PR; if no org is available, say so explicitly. | M |
| **WP-08** | Python task quality: REST helper, timeouts, schema parity | `tasks/**` except `tasks/rlm_sfdmu.py`, `scripts/cml/**`, `scripts/docgen/**`, `scripts/expression_sets/**`, `tests/test_rlm_rest_base.py` (new), `tests/test_expression_set_schema_parity.py` (new), `tests/test_rlm_context_service.py` (new) | none | 1. New `tasks/rlm_rest_base.py` provides `api_version()`, `headers()`, `base_url()` and `request()` with default `timeout=(10, 120)`, and reads the API version from `sfdx-project.json` instead of a hard-coded `"68.0"`.<br>2. `grep -rnE "requests\.(get\|post\|put\|patch\|delete\|request)\(" tasks scripts/cml scripts/docgen` shows a timeout on every call.<br>3. At least `rlm_context_service`, `rlm_cml` and `rlm_manage_fulfillment_scope_cnfg` use the helper.<br>4. The parity test asserts the vendored and canonical schema validators agree on a shared fixture set, including `labels`. Fix the canonical copy to validate `labels`.<br>5. `rlm_context_service` `_make_request` / `_fetch_context_definition` are unit-tested with mocked `requests`.<br>6. `except Exception: pass` is replaced with logged warnings. The ImportError in `rlm_sfdmu` is out of scope (WP-07).<br>7. All existing suites touched by `pr_gate.py --all` pass. | L |
| **WP-09** | CI, supply chain, container and lint tooling | `.github/workflows/**`, `.github/dependabot.yml` (new), `docker/**`, `.dockerignore`, `.devcontainer/**`, `.envrc`, `config/tool-versions.env` (new), `pyproject.toml`, `package.json`, `eslint.config.mjs`, `.prettierrc`, `.prettierignore`, `.pre-commit-config.yaml` (new), `.editorconfig` (new) | none | 1. `prepare-rlm-org.yml`: job uses `environment: devhub` (document that required reviewers must be set in repo settings); secret passed via `env:`, never `${{ }}` in `run:`; checkout `persist-credentials: false`.<br>2. `claude-code-review.yml` runs when `github.event.action == 'labeled' && github.event.label.name == 'claude-review'` or on `synchronize` with the label present. Concurrency cancels in progress; `timeout-minutes` is set; the marketplace ref is pinned.<br>3. `claude.yml`: `timeout-minutes`, concurrency per issue/PR, `claude_args` with `--max-turns`; `issues: edited` dropped.<br>4. `dependabot.yml` covers github-actions, pip and npm, weekly. Write-scoped third-party actions are SHA-pinned.<br>5. `docker-publish.yml`: inputs go through `env:`; `:latest` only from `main`; `checkout@v6`.<br>6. Dockerfile pins CumulusCI, `sf`, `sfdmu` and Node from `config/tool-versions.env`; `SF_TEMP_SHOW_SECRETS` is removed from the image ENV and `.envrc` (scope via wrapper); `.dockerignore` adds `.agents/artifacts/`, `extracted/`, `datasets/sfdmu/extractions/`, `.gitnexus/`, `.claude/settings.local.json`.<br>7. `pyproject.toml` adds `[tool.ruff]` with a baseline that passes on main (per-file ignores OK).<br>8. New `lint` job runs ruff, ESLint and `prettier --check` on **changed files only**.<br>9. pip cache is enabled.<br>10. `package-lock.json` stays out of scope; note it for a follow-up.<br>11. All workflows pass `actionlint`. | L |
| **WP-10** | Integration pass: gate wiring and final verification | `scripts/ai/pr_gate.py`, `tests/test_pr_gate.py` | WP-01, WP-02, WP-03, WP-06, WP-07, WP-08, WP-09 | 1. Registers every new test file from the other WPs (listed in their PR descriptions) and `sync_claude_rules.py --check` as gate suites with correct `triggers`.<br>2. The CumulusCI pin at `pr_gate.py:82` reads `config/tool-versions.env`.<br>3. `tests/test_pr_gate.py` updated.<br>4. On a fresh clone of merged `main`, all of these pass: `python scripts/ai/pr_gate.py --all`, `python scripts/ai/analyze_agent_tooling.py check`, `python scripts/ai/skill_manifest.py --check`.<br>5. Run on this Windows clone after `link_skills.py --fix`: a new Claude Code session loads `AGENTS.md` via `@AGENTS.md` and lists 32 repo skills.<br>6. Re-index GitNexus with `--force --pdg` (local, not committed). | S |

**Parallelism**
- **Seven packages start immediately with no dependencies:** WP-01, 03, 04, 06, 07, 08, 09.
- **WP-02 and WP-05 can also be developed immediately.** They only need to merge after WP-03, whose `.gitignore` negation stops their files being ignored. Until then, workers may stage their files with `git add -f`.
- **WP-10 is the only sequential package.**
- **Ownership check:** every path appears in exactly one package. `.gitignore` belongs to WP-03 and `.dockerignore` to WP-09. `tasks/rlm_sfdmu.py` belongs to WP-07; the rest of `tasks/` belongs to WP-08. `.agents/context/**` belongs to WP-06; the rest of `.agents/` (excluding `artifacts/`) belongs to WP-01. `pr_gate.py` belongs to WP-10.

**Suggested merge order:** WP-03 → WP-07 (security) → WP-01 + WP-02 → WP-04, WP-05, WP-06, WP-08, WP-09 in any order → WP-10.

---

## Sources

Claude Code, Agent Skills and MCP documentation (retrieved 2026-09-22 via WebFetch and the Context7 MCP):
- https://code.claude.com/docs/en/memory: CLAUDE.md size (under 200 lines), `@AGENTS.md` import, Windows symlink guidance, `.claude/rules/` with `paths:`, AGENTS.md native-read semantics
- https://code.claude.com/docs/en/skills: skill frontmatter, 500-line guidance, description budget, symlinked skill dirs, commands merged into skills
- https://code.claude.com/docs/en/settings
- https://code.claude.com/docs/en/settings-reference
- https://code.claude.com/docs/en/permissions: rule syntax, deny→ask→allow evaluation, path anchors on Windows
- https://code.claude.com/docs/en/sandboxing: not supported on native Windows
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/hooks-guide: exit-code-2 blocking, `$CLAUDE_PROJECT_DIR`, hooks are deterministic while CLAUDE.md is advisory
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/mcp
- https://code.claude.com/docs/en/mcp-quickstart
- https://code.claude.com/docs/en/plugins
- https://code.claude.com/docs/en/discover-plugins
- https://code.claude.com/docs/en/github-actions
- https://github.com/anthropics/claude-code-action/blob/main/docs/security.md
- https://code.claude.com/docs/en/best-practices (redirect target of https://www.anthropic.com/engineering/claude-code-best-practices)
- https://code.claude.com/docs/en/output-styles
- https://code.claude.com/docs/en/statusline
- https://agentskills.io/specification: `name` ≤64 characters, `description` ≤1024, SKILL.md under about 5k tokens, references one level deep
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://json.schemastore.org/claude-code-settings.json (schema URL cited by the settings docs)

Repo-internal references are cited inline as `path:line`.

Research could not verify some points:
- perplexity.ai was not consulted.
- The exact `marketplace.json` schema and any Windows `cmd /c` wrapper requirement for stdio MCP servers were not confirmed, so no package depends on them.
- WP-03's junction approach must be verified empirically; that is acceptance criterion 10.

---

## 6. Wave 2 (post-implementation review and research)

| | |
|---|---|
| Date | 2026-09-22 |
| Input | Wave 1 working tree (WP-01…WP-10). The changes are uncommitted: 97 modified files plus 35 untracked. Only `CLAUDE.md` is staged, where the 120000→100644 type change is correct. |
| Method | Three parallel read-only reviews: agent layer, code/CI/security, and research. Every finding marked Critical or High was re-verified by ARCHITECT. |
| Environment limits | This machine has no `sf`, no pytest and no textual installed. CumulusCI 4.8.1 was tested in a scratch venv. **Perplexity is not available here**, so the research used Context7 and official docs and repositories only. |

One side effect occurred during review: running `pr_gate.py --all` rewrote `.cursor/skills/cci-orchestration/{tasks,flows}-reference.md` and `feature-flags.md` with CRLF line endings only. ARCHITECT restored them with `git checkout --`; the content diff was empty.

### 6.A Review findings

**Acceptance summary.** Most wave-1 criteria are MET. These are not:
- WP-04 AC5: there is no TOC, because the file is generated (see A-M5).
- WP-07 AC5, AC8 and AC9: partial or unverified (A-C4, A-C5, and the §6.A org-validation block).
- WP-08 AC2: two SFDMU `requests` calls still have no timeout.
- WP-08 AC7: two new tests fail when CumulusCI is installed.
- WP-09 AC2: the marketplace is still unpinned (R3).
- WP-09 AC5: `:latest` can still be pushed from a branch.
- WP-09 AC6: the container and direnv lose `SF_TEMP_SHOW_SECRETS`.
- WP-10 AC4: `pr_gate --all` is not green.

Local results:
- `analyze_agent_tooling.py check`: 13/13.
- `skill_manifest.py --check`, `sync_claude_rules.py --check` and `link_skills.py --check`: all OK. The last reports 64/64 junctions.
- `pr_gate.py --all` crashes on the cp1252 console. With `PYTHONUTF8=1` it runs 29 checks and exits 1:
  - 8 FAIL: `erd_doc_counts`, `pr_gate_suite`, `cci_reference_drift`, `plan_readme_parsing`, `sfdmu_csv_expectation`, `repo_paths_shared`, `branch_scope`, `stdlib_offline_suites`.
  - 5 MISSING-DEP.

#### Code, security and CI (WP-07/08/09 follow-ups)

| # | Sev | Finding | Evidence | Fix owner |
|---|---|---|---|---|
| A-C1 | **Critical** | **`ExtendStandardContext._make_request` raises `TypeError: got multiple values for keyword argument 'timeout'` on every call.** Every context-extension flow step would fail, and the intentional 600 s read timeout would also have been overridden. The test mocks `_make_request`, so nothing caught it. | `tasks/rlm_extend_stdctx.py:520,527` (verified) | WP-12 |
| A-C2 | High | **SFDMU list-argv breaks on native Windows.** `subprocess.run(["sf", …])` raises FileNotFoundError because `sf` is `sf.cmd`. The main load and extract path used `shell=True` before, so this is a new regression. `:445` also passes `"config set"` as a single argv element (pre-existing). | `tasks/rlm_sfdmu.py:383,445,870,951,1277` (verified) | WP-11 |
| A-C3 | High | **New tests fail whenever CumulusCI is importable, which includes the CI gate.**<br>• `test_rlm_context_service`: the CCI import sets `tasks.__path__ = []` before `from tasks import rlm_rest_base`.<br>• `test_rlm_sfdmu_redaction`: assigns to the read-only `ScratchOrgConfig.username`. | `tasks/rlm_context_service.py:13,22`; `tests/test_rlm_sfdmu_redaction.py:101` | WP-12 / WP-11 |
| A-C4 | High | **Password injection is dead code.** CumulusCI 4.8.1 `AnonymousApexTask` substitutes only `%%%PARAM_1%%%` and `%%%PARAM_2%%%` (`-o param1`/`param2`); there is no `apex_options` (verified: `cumulusci.yml:2234` is unchanged). The random fallback misses the default password policy about 11% of the time (P(no digit) = 0.114). The exception is then swallowed, and the must-reset flag stays set. | `scripts/apex/setScratchOrgPassword.apex:19-25` | WP-11 |
| A-C5 | High | **The OmniScript image is now broken in every org.** The new URL `/servlet/servlet.ImageServer?id=015Wt00000456AXIAY` references a Document that the repo does not ship. | `unpackaged/post_guidedselling/omniScripts/QuantumBit_GuidedSelling_English_1.os-meta.xml:202,367` | WP-11 |
| A-C6 | High | **USER_MODE DML may break the Quinn agent demo.** The post_agents permission sets grant 0 object and 0 field permissions. The allowlist check is also now case-sensitive (`quote` is rejected). The read at :558 is still system mode. This needs a live-org check. | `unpackaged/post_agents/classes/RLM_AI_UpdateRecordFieldsService.cls:36-39,173,251,558` | WP-11 |
| A-C7 | Medium | **The `RLM_AssetInfoUtility` justification comment is inaccurate.** It claims the class is invoked only from a flow, but no metadata references it, and a partner permission set grants access to the invocable, which is exposed via REST. | `force-app/main/default/classes/RLM_AssetInfoUtility.cls` | WP-11 |
| A-C8 | Medium | **Two `requests` calls in `rlm_sfdmu.py` still have no timeout.** | `tasks/rlm_sfdmu.py:724,754` | WP-11 |
| A-C9 | Medium | **The idempotency test cannot fail.** It still passes with temp staging disabled, because `finally` resets `orgs` either way. | `tests/test_rlm_sfdmu_redaction.py` | WP-11 |
| A-C10 | Medium | **The 120 s read timeout is too short for Context Definition POSTs.** The repo's own notes say they take 5–10 minutes. The literal `(10, 120)` is also copy-pasted into 14 files instead of using `rlm_rest_base.DEFAULT_TIMEOUT`. | `tasks/rlm_modify_context.py:155` | WP-12 |
| A-C11 | Medium | **Pre-existing bug surfaced by ruff:** flow activation raises NameError on the undefined `definition_id`. `rlm_writeback_ux.py:67` has a similar F821. | `tasks/rlm_manage_flows.py:266,269,296,299` | WP-12 |
| A-C12 | Medium | **`SF_TEMP_SHOW_SECRETS` scoping broke two environments.**<br>• **Container:** `docker/rlm-cli` and `entrypoint.sh` never set it, so `cci` in the image loses the token.<br>• **direnv:** the `.envrc` `export -f cci` wrapper is not propagated, because direnv exports variables only. | `docker/*`, `.envrc:57-61` | WP-13 |
| A-C13 | Medium | **Claude workflow concurrency is set at workflow level.**<br>• In `claude-code-review.yml`, an unrelated label event cancels an in-progress review.<br>• In `claude.yml`, a later ordinary comment replaces a queued `@claude` run. | `.github/workflows/claude-code-review.yml`, `claude.yml` | WP-13 |
| A-C14 | Medium | **Two `docker-publish.yml` problems.**<br>• The dispatch input `tag` defaults to `latest`, so a branch dispatch can still publish `:latest`.<br>• The Summary step interpolates `${{ steps.meta.outputs.tag }}` into `run:`. | `.github/workflows/docker-publish.yml:22,131,135` | WP-13 |
| A-C15 | Medium | **Lint job problems.**<br>• `xargs` splits file names that contain spaces; tracked examples exist under `postman/` and `templates/profiles/`.<br>• `prettier --check` on whole legacy `.cls` files will fail any PR that touches them. | `.github/workflows/pr-checks.yml` lint job | WP-13 |
| A-C16 | Low | **Other CI and build nits.**<br>• The Dockerfile uses ARG defaults instead of reading `config/tool-versions.env`, so local builds can drift.<br>• There is no pip cache in `prepare-rlm-org`.<br>• pre-commit whitespace and EOF fixers run over `datasets/**` CSVs and can mutate data.<br>• The `# v3` pin comments are imprecise.<br>• The stale ruff `F821` ignore for `rlm_sfdmu.py`.<br>• `_sync_objectset_source_to_source` runs before temp staging, so it still rewrites tracked CSVs.<br>• SFDMU `logs/` are lost when the temp dir is cleaned up. | various | WP-13 / WP-14 / WP-11 |

#### Agent layer (WP-01…06, WP-10 follow-ups)

| # | Sev | Finding | Evidence | Fix owner |
|---|---|---|---|---|
| A-H1 | High | **The `erd_doc_counts` gate regressed.** WP-04 removed "covering 263 objects" from the revenue-cloud-data-model description. The test requires the phrase (`:624`) and pins `EXPECTED_CHECKS = 102`; it now runs 100. `pr_gate_suite` fails as a result. | `tests/test_erd_doc_counts.py:133,624` | WP-15 |
| A-H2 | High | **After `link_skills.py --fix`, 168 files inside the junctions show as untracked** under `git status -uall`. `skip-worktree` covers only the 64 link entries, so `git add -A` could stage duplicate skill copies. The guide's claim that "checkout stays clean" is false. | verified: `git status -uall` shows 168 `??` under `.claude/skills/` and `.agents/skills/` | WP-15 (script), WP-16 (guide) |
| A-M1 | Medium | **Stale `origin/264` remains after WP-01 moved the base to `origin/main`.** | `.cursor/skills/audit-review/merge-and-review-procedures.md:12,91`, `audit-review/SKILL.md:191`, `doc-consistency/SKILL.md:197`, `renewal-asset-creation/SKILL.md:209`, `scripts/ai/README.md:208,289,292`, `scripts/ai/pr_gate.py:45,925`, `scripts/ai/check_branch_scope.py:108` (`DEFAULT_BASE`) | WP-15 (scripts/ai), WP-16 (skills) |
| A-M2 | Medium | **The DO-NOT list was renumbered and references now dangle.** Old #9 is now #7, and old #8 is now #6. | `.cursor/rules/cci-python-tasks.mdc:20`, `robot-tests.mdc:21` (and the generated `.claude/rules` copies), `inapp-framework/SKILL.md:40,139`, `.claude/commands/build-pde.md:106`, `.cursor/commands/build-pde-dev-r1.md:106`, `release-enablement/resume-enablement-work.md:91` | WP-16 |
| A-M3 | Medium | **Docs still describe removed AGENTS.md content or call CLAUDE.md a symlink.** | `doc-consistency/SKILL.md:31,186`, `skill-authoring/SKILL.md:57`, `REVIEW.md:15,58,65`, `docs/guides/prepare-rlm-org-build-guide.md:244`, `.claude/commands/pr-review.md:25`, `docs/guides/agent-skill-discovery.md:62-64` (never mentions `@AGENTS.md`, WP-01 AC5) | WP-16 |
| A-M4 | Medium | **The `protect_generated.py` hook fails open.** It relativizes only when the payload `cwd` is a case-exact prefix. Absolute paths without `cwd`, a subdirectory `cwd`, `c:` vs `C:`, and MSYS `/c/...` paths all exit 0. Its reason text quotes a removed AGENTS.md sentence. It has no test. | `.claude/hooks/protect_generated.py:14,43,63-68` | WP-15 |
| A-M5 | Medium | **The TOC for `tasks-reference.md` is missing.** The file is generated, so the TOC must come from the generator. | `scripts/ai/generate_cci_reference.py` | WP-15 |
| A-M6 | Medium | **Hook commands use `python "$CLAUDE_PROJECT_DIR/…"` in shell form.** Current docs: when Git Bash is missing, hooks fall back to PowerShell, and a bare `$CLAUDE_PROJECT_DIR` becomes `$null` there. Also, `python` does not exist on stock macOS or Linux, where only `python3` does. | `.claude/settings.json` hooks; [hooks](https://code.claude.com/docs/en/hooks) | WP-15 |
| A-M7 | Medium | **Deny rules cover only the Bash tool.** On Windows the PowerShell tool is the primary shell, so the `Bash(git push --force *)` denies need `PowerShell(...)` mirrors. `-f` is not denied either; it falls through to `ask`. | `.claude/settings.json` | WP-15 |
| A-L1 | Low | **The ramped-quotes split left broken anchors:** `#discovering-ids`, `#compound-uplift`, `#read-back--the-ramp-schedule` and `#status`. The analyzer does not check fragments. | `.cursor/skills/ramped-quotes/build-sequence.md:6,66,130,153`, `SKILL.md:61` | WP-16 |
| A-L2 | Low | **Generators write CRLF on Windows** because `write_text()` has no `newline="\n"`. This is the actual cause of I3: the CCI references are **not** stale. ARCHITECT regenerated all three in memory, and each is identical to HEAD; `cci_reference_drift` fails on Windows only. Committed blobs normalize to LF via `.gitattributes`. | `scripts/ai/sync_claude_rules.py:167`, `generate_cci_reference.py:394`, the analyzer report writer | WP-15 |
| A-L3 | Low | **Unicode and gate-selection issues.**<br>• `pr_gate.py` crashes printing failure detail on cp1252 (`:1049`).<br>• `generate_cci_reference.py --dry-run` crashes on `→` (verified).<br>• A CONTRIBUTING.md change does not select `skill_manifest`. | `scripts/ai/pr_gate.py:147,1049` | WP-15 |
| A-L4 | Low | **Three tooling gaps.**<br>• `sync_claude_rules.py` emits unquoted YAML: a glob starting with `*` or a `: ` in a description produces invalid YAML.<br>• The analyzer's `_is_link_like` misfires when the repo path contains a symlink.<br>• `rule-skill-coverage.md` is not regenerated and still cites old DO-NOT numbers. | `sync_claude_rules.py:94-101`, `analyze_agent_tooling.py:854`, `.agents/context/rule-skill-coverage.md` | WP-15 |
| A-L5 | Low | **Windows-only test failures, all pre-existing.**<br>• `test_agent_launch_checks`: 29/29 fail with WinError 1314 on `symlink_to`.<br>• `test_fix_scratch_identity`: 0o666 modes.<br>• `repo_paths_shared`: path case.<br>• `sfdmu_csv_expectation`: 216/217, `--fix-all` byte-identity.<br>• `test_decision_table_tasks`: `read_text()` cp1252.<br>• `plan_readme_parsing`: 1/96.<br>• `branch_scope`: `gh` has no host. | tests/… | WP-14 / WP-15 |
| A-L6 | Low | **This report is untracked, and its uppercase filename breaks the new kebab-case docs rule.** The analyzer's report generator cites B10 from it. Recommendation: the orchestrator renames it to `docs/references/architect-review-2026-09.md` when committing wave 2, and WP-15 points the analyzer note at that path. | `docs/ARCHITECT_REVIEW.md`, `analyze_agent_tooling.py:1432` | WP-15 + orchestrator |

**On I4** (`scripts/ai/README.md` was edited by WP-10 outside its ownership): **acceptable.** It is self-documentation of the gate's check count and belongs with `pr_gate.py`. From wave 2 on, `scripts/ai/README.md` is owned by WP-15. Its "29 checks in about 17 seconds" figure should be re-measured; `branch_scope` alone took 24 s on this machine.

**On I5** (MISSING-DEP for the docgen, harness and billing_portal suites): this is not a code bug. A `requirements-dev.txt` plus a short Windows developer-setup guide is warranted, and is scoped into WP-14.

**On I6:** the WP-07 Apex, Robot and anonymous-Apex changes **remain unverified against an org.** Of the 16 changed Apex classes, only `RLM_AI_UpdateRecordFieldsService` has a test class. After WP-11 lands, the user should run the following against a scratch org built from this branch with `cci flow run prepare_rlm_org --org <alias>`:

```bash
# 1. Compile + run the only covering test (validate = no persistent deploy)
sf project deploy validate --target-org <alias> \
  --source-dir force-app/main/default/classes \
  --source-dir unpackaged/pre/4_tax \
  --source-dir unpackaged/post_agents/classes \
  --source-dir unpackaged/post_approvals/classes \
  --source-dir unpackaged/post_docgen/classes \
  --source-dir unpackaged/post_guidedselling/omniScripts \
  --test-level RunSpecifiedTests --tests RLM_AI_UpdateRecordFieldsServiceTest --wait 30
# 2. Password task: must succeed on scratch and refuse on a sandbox/prod alias
cci task run set_scratch_org_password --org <alias>
# 3. Quinn agent demo: as the agent user, run the "update record fields" action on a Quote (USER_MODE/FLS check)
# 4. Robot setup suite that imports resources/SetupToggles.robot (password variable path)
```

Before relying on step 1, run `sf project deploy validate --help`. The `RunSpecifiedTests` requirement differs between org types.

### 6.B Research results

**R1. Plugin packaging: not recommended for this repo.**
- **Current schema:**
  - `plugin.json` requires only `name`. Components go in `skills/`, `commands/`, `agents/`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json` and `output-styles/`.
  - `marketplace.json` requires `name`, `owner.name` and `plugins[]`, each plugin with `name` and `source`.
  - Plugin `source` can be `./relative` or `github`/`url`/`git-subdir` with `ref`/`sha`, or `npm`, `archive` or `command`.
  - Marketplace sources accept `ref`, but **not** `sha`.
  - Distribution is `extraKnownMarketplaces` plus `enabledPlugins`, after workspace trust. Since v2.1.195, external plugins still need a per-user `claude plugin install`.
  - Validate with `claude plugin validate . --strict`.
- **Why not for this repo:**
  - Plugins **cannot ship `.claude/rules`**, and a plugin's CLAUDE.md is not loaded.
  - Plugins are copied to `~/.claude/plugins/cache`, and Windows symlink stubs would be copied as stubs.
  - The skills depend on repo-relative `scripts/` and `datasets/`.
  - Namespacing would rename `/pr-review` to `/<plugin>:pr-review`.
  - Project-scope `.claude/` already does the job.
- **Revisit** only if a portable subset is needed in PMOS. Migration steps:
  1. An in-repo `plugins/<name>/` containing only path-independent skills.
  2. A root `.claude-plugin/marketplace.json` with `"source":"./plugins/<name>"`.
  3. A CI `claude plugin validate . --strict` step.
  4. Consumers use `extraKnownMarketplaces` with a `ref` tag plus `claude plugin install`.
  5. Never enable the plugin in this repo, which would load skills twice.
- Sources: [plugins-reference](https://code.claude.com/docs/en/plugins-reference), [plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [discover-plugins](https://code.claude.com/docs/en/discover-plugins).

**R2. Windows stdio MCP and the Salesforce DX MCP server.**
- **No `cmd /c` wrapper is needed on current Claude Code.** The MCP docs have no Windows wrapper note, and CHANGELOG 2.1.119 removed the "false-positive 'Windows requires cmd /c wrapper' MCP config warning". This is not verified empirically here. If bare `npx` fails, the `cmd /c` form belongs in **local scope only**, because it breaks macOS and Linux.
- **`@salesforce/mcp`** is at 0.30.15 (2026-07-09), so still 0.x.
  - Each tool is marked GA or NON-GA, and only GA tools load without `--allow-non-ga-tools`.
  - `--orgs` is required: `DEFAULT_TARGET_ORG`, `DEFAULT_TARGET_DEV_HUB`, `ALLOW_ALL_ORGS` or an alias. It reuses `sf` CLI auth.
  - Mutating tools include `deploy_metadata`, `assign_permission_set`, the devops tools, `retrieve_metadata` (overwrites local files), and the NON-GA `create_scratch_org`/`delete_org`.
- **Recommendation: do not commit a root `.mcp.json`.** `claude -p`, the SDK and claude-code-action load project servers **without prompting**, so CI would spawn it. Document it as opt-in instead, with local scope or `settings.local.json`:
  ```json
  { "mcpServers": { "salesforce": { "command": "npx",
    "args": ["-y","@salesforce/mcp@0.30.15","--orgs","DEFAULT_TARGET_ORG",
             "--toolsets","data","--tools","run_apex_test,list_all_orgs","--no-telemetry"] } } }
  ```
  Also add backstop denies to `.claude/settings.json`: `mcp__salesforce__deploy_metadata`, `mcp__salesforce__assign_permission_set`, `mcp__salesforce__delete_org`. Prefer explicit aliases over `DEFAULT_TARGET_ORG` whenever a production org could be the default.
- Sources: [mcp](https://code.claude.com/docs/en/mcp), [CHANGELOG](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md), [salesforcecli/mcp](https://github.com/salesforcecli/mcp), [npm registry](https://registry.npmjs.org/@salesforce/mcp).
- Unverified: the developer.salesforce.com MCP guide returned 403, so GA status of the server as a whole is not confirmed.

**R3. claude-code-action marketplace pinning gap: confirmed.**
- **The gap:**
  - `action.yml` (v1.0.231, matching the repo's SHA pin) has only `plugins` and `plugin_marketplaces`, with no ref or sha input.
  - `base-action/src/install-plugins.ts` validates `^https://….git$`, so a `.git#ref` suffix is **rejected**.
  - Upstream fix is pending: issue #1229 and PR #1497.
  - Local paths are accepted.
- **Best mitigation: vendor by checkout at a SHA.** Pin the checkout to a full SHA, then point the action at the local path:
  ```yaml
  - uses: actions/checkout@<sha>
    with: { repository: anthropics/claude-code, ref: <40-char-sha>, path: .ci/claude-code, persist-credentials: false }
  # then: plugin_marketplaces: './.ci/claude-code'   plugins: 'code-review@claude-code-plugins'
  ```
  The equivalent alternative is `claude_args: --plugin-dir ./.ci/claude-code/plugins/code-review`.
- The plugin entry uses `"source":"./plugins/code-review"`, so pinning the checkout pins the plugin.
- Bump the SHA deliberately. Revisit when #1497 lands, although that gives ref pinning only, not sha.
- Sources: [action.yml](https://github.com/anthropics/claude-code-action/blob/main/action.yml), [install-plugins.ts](https://github.com/anthropics/claude-code-action/blob/main/base-action/src/install-plugins.ts), [#1229](https://github.com/anthropics/claude-code-action/issues/1229), [#1497](https://github.com/anthropics/claude-code-action/pull/1497), [marketplace.json](https://github.com/anthropics/claude-code/blob/main/.claude-plugin/marketplace.json).

**R4. Contradictions between the wave-1 config and the current docs** (Claude Code 2.1.280, docs fetched 2026-09-22):
- **Hooks:** the shell-form `$CLAUDE_PROJECT_DIR` fails under the PowerShell fallback (A-M6). Use exec form (`"command"` plus `"args"` with `${CLAUDE_PROJECT_DIR}`) and resolve `python` vs `python3`.
- **Permissions:** rules are per tool, so mirror the destructive denies for `PowerShell(...)` (A-M7). The rest of the syntax is valid: `Read(//**/*.key)` is the documented all-drives form, and deny→ask→allow ordering holds.
- **Rules:** a `paths:` YAML list with brace globs is valid. `paths` is the only frontmatter field read, and the `description:` field is silently ignored, which is harmless.
- **Subagents and commands:** all fields used are documented (`tools`, `skills`, `description`, `argument-hint`, `allowed-tools`). `.claude/commands/` is the legacy form but still supported. Commands' `allowed-tools` applies even in untrusted folders and `-p` runs, which is acceptable for the read-only `pr_review.py status`.
- **CLAUDE.md:** `@AGENTS.md` is correct. Native AGENTS.md reading (v2.1.277+) is disabled whenever a CLAUDE.md exists, so the import is required.
- Sources: [hooks](https://code.claude.com/docs/en/hooks), [permissions](https://code.claude.com/docs/en/permissions), [memory](https://code.claude.com/docs/en/memory), [sub-agents](https://code.claude.com/docs/en/sub-agents), [skills](https://code.claude.com/docs/en/skills), [settings-reference](https://code.claude.com/docs/en/settings-reference).

**I1. GitNexus re-injecting into CLAUDE.md and AGENTS.md: a supported opt-out exists.**
- `gitnexus` 1.6.9 is installed; 1.6.12 is the latest on npm. ARCHITECT verified the following against `gitnexus analyze --help` and `dist/cli/analyze-config.js`:
  - CLI flags: `--skip-agents-md`, `--skip-skills`, `--index-only`, `--no-stats`.
  - A **repo-root `.gitnexusrc`** (JSON) is read on every `analyze`, with keys `skipAgentsMd` (aliases `skipContextFiles`/`skipAiContext`), `skipSkills`, `indexOnly`, `noStats`, `pdg` and others. It **fails closed on unknown keys**.
  - No environment variable disables injection.
- **Durable mitigation (WP-15):**
  1. Commit `.gitnexusrc` = `{"analyze":{"skipAgentsMd":true,"skipSkills":true}}`.
  2. Add an analyzer check that fails when `gitnexus:start` appears in `CLAUDE.md` or `AGENTS.md`, or when anything under `.claude/skills/gitnexus/` is tracked.
  3. Keep the `.gitignore` backstop.
- Sources: [GitNexus README](https://github.com/abhigyanpatwari/GitNexus/blob/main/gitnexus/README.md), [npm registry](https://registry.npmjs.org/gitnexus).

**I2. Encoding.**
- An AST scan found **338** text-mode I/O calls that rely on the locale encoding: `tasks` 65, `scripts` 104, `tests` 158, `robot` 1, `datasets` 2, `postman` 8.
  - These are `open()` without `encoding=`, `read_text`/`write_text` without it, and `subprocess` with `text=True` and no `encoding=`.
- **Ruff's `PLW1514` (unspecified-encoding) covers the file-I/O part**: 136 hits in `tasks`, `scripts` and `tests`.
  - It is a preview rule, so enable it with `preview = true` plus `explicit-preview-rules = true`, so that only the explicitly selected preview rules turn on.
  - The existing changed-files lint job then enforces it on every package's touched files.
  - A small AST checker covers the `subprocess text=True` part, which ruff does not.

### 6.C Wave 2 Work Packages

Rules are the same as §5: branch `wp-XX-<slug>`, gate with `python scripts/ai/pr_gate.py --base origin/main`, create regular files only, and add **no new symlinks**.

**New contracts:**
- The encoding checker lives at `scripts/lint/check_text_encoding.py` (WP-14) and uses exit code 1 on findings.
- Ruff `PLW1514` is enabled via `pyproject.toml` (WP-14).
- Each package must make **its own touched Python files** pass both checks, so no package waits on another.
- The repo-wide zero count is a wave-2 exit criterion that the orchestrator verifies after all merges.

| id | title | owned files/dirs (exclusive) | dependencies | acceptance criteria | size |
|---|---|---|---|---|---|
| **WP-11** | SFDMU, Apex and password follow-ups (WP-07 regressions) | `tasks/rlm_sfdmu.py`, `tests/test_rlm_sfdmu_redaction.py`, `tests/test_sfdmu_export.py`, `scripts/apex/**`, `cumulusci.yml`, `force-app/**`, `unpackaged/**`, `robot/**/*.robot`, `robot/**/*.resource` | none | 1. Every `sf` argv resolves via `shutil.which("sf") or "sf"`. `:445` is split into `["sf","config","set",…]`. A test simulates a `.cmd` shim on Windows or monkeypatches `which` (A-C2).<br>2. `requests` calls at `:724` and `:754` get `rlm_rest_base.DEFAULT_TIMEOUT` (A-C8).<br>3. The redaction test uses `config={"username":…}` or a spec'd mock and passes **with CumulusCI 4.8.1 installed** (A-C3).<br>4. The idempotency test asserts the tracked `export.json` has no `accessToken` **from inside** the `subprocess.run` side effect (A-C9).<br>5. `_sync_objectset_source_to_source` runs after staging. The temp dir's `logs/` path is logged, or its contents are copied back on failure (A-C16).<br>6. The password is injected via `%%%PARAM_1%%%` and `cumulusci.yml` `set_scratch_org_password` passes `param1`. The value is escaped for an Apex string literal. The random fallback guarantees at least 1 upper, 1 lower, 1 digit and 1 special (A-C4).<br>7. The OmniScript image ships as a static resource referenced by `/resource/<name>`, or the image element is removed (A-C5).<br>8. `ALLOWED_OBJECT_TYPES` is compared case-insensitively. The `:558` read uses `WITH USER_MODE`. The post_agents permission sets gain the minimum object and field grants on Quote, QuoteLineItem and Opportunity that the demo needs, **or** the PR states the exact live-org result (A-C6).<br>9. The `RLM_AssetInfoUtility` comment reflects actual callers and states a decision (A-C7).<br>10. Owned `.py` files pass `ruff --preview --select PLW1514` and the encoding checker.<br>11. The PR description includes the §6.A I6 command block and marks it **"org validation pending: user to run"**. | M |
| **WP-12** | REST and task fixes (WP-08 regressions) | `tasks/**` except `tasks/rlm_sfdmu.py`, `tests/test_rlm_context_service.py`, `tests/test_extend_stdctx.py`, `tests/test_rlm_rest_base.py`, `tests/test_expression_set_schema_parity.py` | none | 1. `rlm_extend_stdctx.py:527` becomes `requests.request(method, url, **kwargs)`. A new test calls the **real** `_make_request` with `requests.request` patched, and asserts a single `timeout` equal to `(_CONNECT_TIMEOUT, _READ_TIMEOUT)` (A-C1).<br>2. `from tasks import rlm_rest_base` moves above the CCI import in `rlm_context_service.py` (and in any other module with the same shape). `test_rlm_context_service` passes with CumulusCI 4.8.1 installed (A-C3).<br>3. Context-definition POSTs use a read timeout of 600 s or more (A-C10).<br>4. All `(10, 120)` literals are replaced by `rlm_rest_base.DEFAULT_TIMEOUT`, or a named per-module constant with a comment.<br>5. The `definition_id` NameError in `rlm_manage_flows.py` and the F821 in `rlm_writeback_ux.py:67` are fixed (A-C11).<br>6. The bare `except: pass` at `rlm_manage_expression_sets.py:142,313` logs at debug level.<br>7. `ruff check tasks` shows no F821. Owned files pass PLW1514 and the encoding checker.<br>8. The wave-1 suites for `tasks/` (extend_stdctx, fulfillment_scope, expression_set_schema, cml, context_*) pass with and without CumulusCI installed. | M |
| **WP-13** | CI, container and direnv fixes (WP-09 regressions, R3) | `.github/workflows/**`, `.github/dependabot.yml`, `docker/**`, `.dockerignore`, `.devcontainer/**`, `.envrc`, `config/tool-versions.env`, `.pre-commit-config.yaml`, `.editorconfig` | none | 1. `claude-code-review.yml` and `claude.yml` use **job-level** concurrency, keyed so unrelated labels or comments neither cancel nor replace a pending review or `@claude` run (A-C13).<br>2. `claude-code-review.yml` vendors the plugin marketplace via `actions/checkout` of `anthropics/claude-code` at a 40-char SHA (itself SHA-pinned) into `.ci/claude-code`, and uses `plugin_marketplaces: './.ci/claude-code'`. The existing comment is updated to cite action PR #1497 (R3).<br>3. `docker-publish.yml`: the `tag` input has no `latest` default; a job step fails when tag == `latest` and the ref is not the default branch; the Summary step reads outputs via `env:` (A-C14).<br>4. Lint job uses `xargs -d '\n'` or `-0`, and Prettier is limited to changed **non-Apex** files, or runs with a documented Apex exclusion (A-C15).<br>5. The container sets `SF_TEMP_SHOW_SECRETS=true` only for `cci` (a `/usr/local/bin/cci` shim or `rlm-cli`), and `cci org import` works in the image. `.envrc` either exports the variable with a warning comment or documents a manual prefix; no `export -f` (A-C12).<br>6. The Dockerfile reads versions from `config/tool-versions.env`, or a CI step fails if the ARG defaults differ from it.<br>7. pip cache is added to `prepare-rlm-org.yml`.<br>8. pre-commit whitespace and EOF hooks exclude `^datasets/`.<br>9. `.editorconfig` has no CRLF sections that contradict `.gitattributes`.<br>10. Pin comments name the exact version.<br>11. `actionlint` reports 0 findings. `shellcheck` is run on workflow `run:` blocks if available, and the PR says whether it was. | M |
| **WP-14** | Encoding and Windows portability, dev dependencies (I2, I5) | `scripts/**` except `scripts/ai/**` and `scripts/apex/**`; `scripts/lint/check_text_encoding.py` (new); `tests/**` except files owned by WP-11, WP-12 and WP-15; `robot/**/*.py`; `postman/**`; `datasets/**/*.py`; `pyproject.toml`; `requirements-dev.txt` (new); `docs/guides/windows-dev-setup.md` (new) | none | 1. `pyproject.toml` enables `PLW1514` (`[tool.ruff.lint] preview = true`, `explicit-preview-rules = true`, `extend-select = ["PLW1514"]`) and removes the stale `rlm_sfdmu.py` F821 ignore.<br>2. `scripts/lint/check_text_encoding.py` (AST-based, with `-v` for per-line output) flags text-mode `open`/`Path.open`/`io.open`, `read_text`/`write_text` and `subprocess` `text=True` or `universal_newlines=True` without `encoding=`. It has a unit test under `tests/`.<br>3. `ruff check --preview --select PLW1514` and the checker both exit 0 over **WP-14-owned paths**. Fixes use `encoding="utf-8"`, or `encoding="locale"` with a comment where the locale is intended.<br>4. These Windows failures are fixed test-side or in owned scripts, and each passes on Windows and Linux: `test_agent_launch_checks` (skip the symlink cases with a reason when `os.symlink` lacks privilege, or use junctions), `test_fix_scratch_identity` (file modes), `repo_paths_shared` (path case), `sfdmu_csv_expectation` (`--fix-all` byte-identity / newline), `test_decision_table_tasks` (encoding) (A-L5).<br>5. `requirements-dev.txt` pins `cumulusci`, `setuptools<70`, `pytest`, `textual`, `ruff` and PyYAML to the CI versions in `config/tool-versions.env` (read-only reference).<br>6. `windows-dev-setup.md` covers Developer Mode or `link_skills.py --fix`, `PYTHONUTF8=1`, `py -3.11 -m venv`, installing `requirements-dev.txt`, and running `pr_gate.py --all` with the expected MISSING-DEP list at 0 (I5). | L |
| **WP-15** | Claude config, `scripts/ai` tooling and the GitNexus guard (I1, I3, I4) | `.claude/settings.json`, `.claude/hooks/**`, `.gitnexusrc` (new), `.gitignore`, `scripts/ai/**` (includes `README.md`), `.agents/context/**`, `docs/analysis/**`, `.cursor/skills/cci-orchestration/{tasks,flows}-reference.md`, `.cursor/skills/cci-orchestration/feature-flags.md`, `tests/test_pr_gate.py`, `tests/test_erd_doc_counts.py`, `tests/test_link_skills.py`, `tests/test_sync_claude_rules.py`, `tests/test_skill_manifest_audit.py`, `tests/test_generate_cci_reference.py`, `tests/test_branch_scope.py`, `tests/test_check_plan_readme_consistency.py`, `tests/test_protect_generated_hook.py` (new), `tests/test_gitnexus_guard.py` (new) | none | 1. **I1 (MUST):** `.gitnexusrc` = `{"analyze":{"skipAgentsMd":true,"skipSkills":true}}`. The analyzer gets a check "no GitNexus injection" that fails on `gitnexus:start` in `CLAUDE.md` or `AGENTS.md`, or on any tracked `.claude/skills/gitnexus/**`, with a remediation message. The test covers both. **Verified by running `npx gitnexus analyze` once locally and confirming that `git diff CLAUDE.md AGENTS.md` is empty.**<br>2. **A-H1:** the `erd_doc_counts` prose pattern follows the WP-04 description change: the pattern is retired, `EXPECTED_CHECKS` is updated, and the test comment explains why. `pr_gate_suite` passes.<br>3. **A-H2:** `link_skills.py --fix` appends `/.claude/skills/*/**` and `/.agents/skills/*/**` to `.git/info/exclude`, idempotently. `--check` warns if they are missing. After `--fix`, `git status --short -uall` shows 0 entries under those paths (tested).<br>4. **A-M4:** `protect_generated.py` matches on normalized path segments (`(^\|/)unpackaged/post_ux/` etc., case-insensitive on Windows, MSYS `/c/` handled) and derives the root from `CLAUDE_PROJECT_DIR`. Its reason text is current. A new test covers relative, absolute, subdirectory `cwd`, `c:`/`C:` and MSYS paths. Registered in `pr_gate.py`.<br>5. **A-M6:** both hooks use exec form (`"command"` + `"args"` with `${CLAUDE_PROJECT_DIR}`). The PR documents how `python` vs `python3` is resolved, with manual runs on Windows Git Bash and one of macOS or Linux. The SessionStart hook never blocks.<br>6. **A-M7 and R2:** `settings.json` gains `PowerShell(...)` mirrors of every Bash deny and ask rule, plus `Bash(git push -f *)`, plus denies for `mcp__salesforce__deploy_metadata`, `mcp__salesforce__assign_permission_set` and `mcp__salesforce__delete_org`. **No `.mcp.json` is committed.**<br>7. **A-L2 / I3:** every generator in `scripts/ai` writes with `newline="\n"`. `cci_reference_drift` passes on Windows. The three reference files are regenerated, and `tasks-reference.md` gains a generator-emitted TOC (A-M5).<br>8. **A-L3:** `pr_gate.py` and `generate_cci_reference.py --dry-run` never crash on cp1252 (use `sys.stdout.reconfigure(errors="replace")` or ASCII output). A CONTRIBUTING.md change selects `skill_manifest`.<br>9. **A-M1:** `origin/264` is replaced by `origin/main` in `scripts/ai/**`, including `check_branch_scope.DEFAULT_BASE` (with a test).<br>10. **A-L4:** `sync_claude_rules.py` quotes YAML scalars only when needed, keeping output byte-stable for current rules; `_is_link_like` is fixed; `rule-skill-coverage.md` is regenerated.<br>11. `scripts/ai/README.md` documents `link_skills.py`, `sync_claude_rules.py` and the re-measured check count and time (I4).<br>12. The analyzer B10 note points to `docs/references/architect-review-2026-09.md` (A-L6).<br>13. `plan_readme_parsing` and `branch_scope` pass on Windows. `branch_scope` skips its `gh`-dependent cases with a reason when `gh` has no host.<br>14. Owned `.py` files pass PLW1514 and the encoding checker.<br>15. `sync_claude_rules.py --check` passes against whatever `.claude/rules` holds. | L |
| **WP-16** | Docs, skills and rules consistency after the AGENTS.md slim-down | `AGENTS.md`, `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, `REVIEW.md`, `SECURITY.md`, `.github/copilot-instructions.md`, `.agents/**` except `.agents/context/**`, `.cursor/rules/**`, `.claude/rules/**`, `.cursor/skills/**` except the three cci-orchestration generated references, `.claude/commands/**`, `.cursor/commands/**`, `.claude/agents/**`, `docs/**` except `docs/analysis/**`, `docs/ARCHITECT_REVIEW.md` and `docs/guides/windows-dev-setup.md` | none | 1. **A-M2:** every DO-NOT cross-reference matches the current AGENTS.md numbering. Prefer a stable anchor/slug over numbers; if slugs are added, AGENTS.md defines them. `grep -rnE "DO NOT #[0-9]\|AGENTS.md rule [0-9]"` returns only valid references.<br>2. **A-M3:** no document calls CLAUDE.md a symlink. `agent-skill-discovery.md` describes the `@AGENTS.md` import and the `.git/info/exclude` step (contract with WP-15). REVIEW.md and `pr-review.md` link to the actual homes of the protocol, SFDMU rules and doc-consistency rules (`.claude/rules/*`, `.cursor/rules/*`, the audit-review skill).<br>3. **A-M1:** no `origin/264` remains in owned files unless it is historical and marked as such.<br>4. **A-L1:** all ramped-quotes anchors resolve. A one-off local script is fine; paste its output in the PR.<br>5. `.claude/rules/**` is regenerated with `python scripts/ai/sync_claude_rules.py --write` after the `.mdc` edits, and `--check` passes.<br>6. A new "Optional: Salesforce DX MCP (opt-in)" section in `docs/guides/agent-skill-discovery.md` (or a new `docs/guides/claude-code-setup.md`) gives the R2 snippet, local-scope instructions, the Windows `cmd /c` fallback note, and the warning about unattended loading in CI (R2).<br>7. A short note under "Claude Code specifics" in `CLAUDE.md`, or the setup guide, records that GitNexus must not inject context and that `.gitnexusrc` enforces it. **`CLAUDE.md` stays ≤15 lines.**<br>8. `analyze_agent_tooling.py check` passes 13/13 or more, AGENTS.md stays ≤150 lines and ≤12,288 bytes, and `skill_manifest.py --check` passes. | M |

**Independence and merge order**
- **All six packages have no dependencies** and can run fully in parallel.
- **Ownership is disjoint:**
  - `tasks/rlm_sfdmu.py` belongs to WP-11; the rest of `tasks/` belongs to WP-12.
  - `scripts/ai/**` belongs to WP-15, `scripts/apex/**` to WP-11, and the rest of `scripts/` to WP-14.
  - Test files are assigned by name. Every unnamed test belongs to WP-14.
  - The three generated cci-orchestration references belong to WP-15; the rest of `.cursor/skills/` belongs to WP-16.
  - `.agents/context/**` belongs to WP-15; the rest of `.agents/` belongs to WP-16.
  - `pyproject.toml` belongs to WP-14.
- **Suggested merge order:** WP-12 (critical A-C1) → WP-11 → WP-15 → WP-14 → WP-13 → WP-16. Order matters only for rebase convenience.

**Wave 2 exit criteria** (orchestrator, after all merges, on this Windows clone **and** in Linux CI):
1. `python scripts/ai/pr_gate.py --all` reports 0 FAIL. MISSING-DEP is acceptable only on machines without `requirements-dev.txt` installed.
2. `ruff check --preview --select PLW1514 tasks scripts tests` and `python scripts/lint/check_text_encoding.py tasks scripts tests robot` both exit 0.
3. `npx gitnexus analyze` leaves `git status` unchanged for `CLAUDE.md`, `AGENTS.md` and `.claude/skills/`.
4. A fresh Claude Code session lists the 32 repo skills. `git status -uall` is clean under the skill junctions.
5. The user has run the §6.A I6 org-validation block against a scratch org, and the result is recorded in the PR. **Until then, the WP-07/WP-11 Apex and Robot changes are UNVERIFIED.**

---

## 7. Wave 3: Perplexity verification (2026-09-23)

| | |
|---|---|
| Scope | Re-check the wave 1 and wave 2 recommendations against current information, with Perplexity as the main source. This is research only. |
| Tooling | The Perplexity tools were not in ARCHITECT's own MCP list, because `MCP_DOCKER` failed to connect at session start. Queries went through the orchestrator's gateway helper (`pplx.py`, `docker mcp gateway run --profile=research_`).<br>• Seven queries ran: three `perplexity_research`, four `perplexity_ask`.<br>• Parallel calls hit **HTTP 429** rate limits and one hung; the helper also crashed on non-cp1252 output. Once rerun one at a time with `PYTHONIOENCODING=utf-8`, all seven returned answers. |
| Method | Where Perplexity disagreed with the implementation or with the wave-2 research, ARCHITECT checked the **primary source** directly (`curl` of code.claude.com `.md` pages, the claude-code CHANGELOG, the salesforcecli/mcp README, and `npm view`) before recording a verdict. |

**Headline result: 0 confirmed contradictions of the implementation.** Perplexity contradicted it three times, and each time the primary source showed Perplexity's answer to be stale or invented:
- `@salesforce/mcp` version;
- the Windows `cmd /c` wrapper;
- the hook event names.

Two findings **add** something worth acting on:
1. **Windows `python3` in exec-form hooks** is a real portability gap (WP-17).
2. **Concrete model aliases** could be added to `model-routing.md`. This is optional (WP-18).

### 7.A Findings

| # | Item | What Perplexity found | Verdict | Primary-source check | Follow-up |
|---|---|---|---|---|---|
| 1a | `CLAUDE.md` = `@AGENTS.md` import vs symlink (Windows) | The import is the documented, recommended cross-platform pattern, and symlinks are not a documented pattern. AGENTS.md is read natively only when no project CLAUDE.md, `.claude/CLAUDE.md` or CLAUDE.local.md exists (added in v2.1.277). When AGENTS.md is read natively it does not appear in `/memory` or `/context`. It also reported a `/config` "Project instructions" setting that can load both files. | **CONFIRMS** (WP-01), and **ADDS** the `/config` option | Matches code.claude.com/docs/en/memory as fetched in wave 1 and wave 2. Wave 2 found that the both-files mode is only available at user or managed scope. | None. `/config` is a per-user choice and does not replace the committed import. |
| 1b | `.claude/rules` `paths:` frontmatter | The key is exactly `paths:`, globs are matched against paths, brace expansion is supported within a documented limit, and rules load lazily. | **CONFIRMS** (WP-02) | Matches wave-2 R4. The limit is 1,000 patterns. | None |
| 1c | Permission rule syntax incl. `PowerShell(...)` | `PowerShell` is a **separate tool** with its own rule namespace, and `Bash(...)` rules do **not** apply to it. The two share wildcard syntax, and `:*` is equivalent to a trailing ` *`. Precedence is deny → ask → allow. PowerShell rules **canonicalize aliases**, so `PowerShell(Remove-Item *)` also matches `rm`, `del`, etc. | **CONFIRMS** (WP-15 PowerShell mirrors), and **ADDS** alias canonicalization | Consistent with code.claude.com/docs/en/permissions. `.claude/settings.json` now mirrors every Bash deny and ask rule. | Optional: mirror the four **allow** rules for PowerShell too, to cut prompts on Windows. Non-safety; can be folded into WP-17. |
| 1d | Hook exec form and event names | **Exec form is correct:** with `args` present, `command` is spawned directly with no shell, and `${CLAUDE_PROJECT_DIR}` belongs in `args`. **On Windows, exec form requires `command` to resolve to a real `.exe`.** Perplexity also **invented** event names: `Start`, `PreMessage`, `PostMessage`, `ToolError`. | Exec form **CONFIRMS** (WP-15). The Windows `.exe` requirement **ADDS** a risk. The event names are a **Perplexity error**. | `curl code.claude.com/docs/en/hooks.md`:<br>• `:470-475` says "On Windows, exec form requires `command` to resolve to a real executable such as a `.exe`".<br>• The real events include `PreToolUse`, `PostToolUse`, `PostToolBatch`, `UserPromptSubmit`, `SessionStart` and `Stop`, with no `Start`, `PreMessage` or `ToolError`.<br>The repo's `SessionStart` and `PreToolUse` are valid. | **WP-17.** `command: "python3"` works on this machine only because the Microsoft Store Python ships a `python3.exe` alias (`where python3` → `WindowsApps\python3.exe`). python.org Windows installers ship `python.exe` and `py.exe`, not `python3.exe`. On those machines both hooks fail to spawn, which is a **non-blocking** error, so the generated-files protection is **silently lost**. |
| 1e | Subagent frontmatter fields | Only `name` and `description` are required. Documented optional fields include `tools`, `disallowedTools`, `model` (or `inherit`), `permissionMode`, `maxTurns`, `skills`, `memory`, `background`, `effort`, `isolation`, `initialPrompt` and `omitClaudeMd`. Field names are camelCase, and **unknown fields are silently ignored**. | **CONFIRMS** (WP-05) | `.claude/agents/rlm-reviewer.md` uses only `name`, `description` and `tools`, and `sfdmu-plan-auditor.md` adds `skills`, so both are valid. | None. Because unknown fields are ignored silently, a typo would go unnoticed. Consider an analyzer frontmatter allowlist check later (low). |
| 1f | Skills: 500-line guidance, description limit, commands | The agentskills.io spec says to keep the SKILL.md body **under 500 lines** or about 5k tokens, with progressive disclosure. `description` must be 1–1024 characters and say what the skill does and when to use it. `.claude/commands` shares the skills configuration model. | **CONFIRMS** (WP-04) | Matches wave 1 and wave 2 sources. The largest SKILL.md is now 497 lines. | None |
| 2a | claude-code-action `plugin_marketplaces` pinning | There is no documented `.git#ref` or SHA pinning in v1. Issue #1229 is open and PR #1497 is not in the v1 docs. The recommended workaround is to check out the marketplace at a SHA and pass the local path. | **CONFIRMS** (WP-13) | `claude-code-review.yml:56-68` checks out `anthropics/claude-code` at `56f36532…` into `.ci/claude-code` and uses `plugin_marketplaces: './.ci/claude-code'`. | None. Revisit when #1497 merges. |
| 2b | Job-level concurrency, `timeout-minutes`, `--max-turns` | Use **job-level** `timeout-minutes` (the action's old `timeout_minutes` input is deprecated), `claude_args: --max-turns N` (replaces `max_turns`), and **job-level** concurrency keyed per PR or issue. The upstream example uses `--max-turns 10` and `cancel-in-progress: true`. | **CONFIRMS** (WP-13) | `claude.yml:29-39,64` has timeout 30, job-level group, `cancel-in-progress: false` and `--max-turns 30`. `claude-code-review.yml:22-32` has timeout 20, job-level group and `cancel-in-progress: true`. | None. `cancel-in-progress: false` for `@claude` is a deliberate choice (wave 2, A-C13): a newer comment must not kill an in-flight answer. `--max-turns 30` is within guidance. |
| 3a | `@salesforce/mcp` version and flags | It reported **0.19.1** as the latest. It said `--orgs` takes aliases or usernames only, gave only a generic toolset list, and **did not mention `DEFAULT_TARGET_ORG`**. | **Perplexity error**, stale | `npm view @salesforce/mcp`: `latest` = **0.30.15**, modified 2026-07-09. The salesforcecli/mcp README's own examples use `"--orgs","DEFAULT_TARGET_ORG","--toolsets","orgs,metadata,data,users"`. The wave-2 R2 snippet (pinned `@0.30.15`, `DEFAULT_TARGET_ORG`, `--toolsets data`) stands. | None |
| 3b | Least privilege for Salesforce MCP | Treat `deploy_metadata`, `assign_permission_set` and `delete_org` as write or destructive and keep them unavailable. Use a dedicated integration user, pin the version (not `@latest`), and separate read-only from deployment configurations. **Hiding tools does not replace Salesforce-side least-privilege permissions.** | **CONFIRMS**, and **ADDS** the integration-user and Salesforce-side permissions advice | `.claude/settings.json` denies `mcp__salesforce__deploy_metadata`, `assign_permission_set` and `delete_org`. | Fold into the WP-16 opt-in MCP doc section as two lines: dedicated integration user; the deny list is a backstop, not a boundary. That section was written in wave 2, so this goes in WP-18. |
| 3c | Windows stdio MCP `cmd /c` | It claimed the docs **still require** a `cmd /c` wrapper for `npx` on native Windows. | **Perplexity error** | `curl code.claude.com/docs/en/mcp.md` (117 KB) has **no** `cmd /c` text; the only Windows mention is the WSL note at `:1093`. The claude-code `CHANGELOG.md:4043` says "Windows: removed false-positive 'Windows requires cmd /c wrapper' MCP config warning". | None. Keep the wave-2 guidance: bare `npx`, with `cmd /c` only as a local-scope fallback. Perplexity's citations were to translated or mirror pages (`anthropic.mintlify.app/ja/...`, third-party guides), which is the probable source of the stale claim. |
| 4 | GitNexus `.gitnexusrc` | It confirmed the repo-root `.gitnexusrc` JSON keys `analyze.skipAgentsMd`, `analyze.skipSkills` and `analyze.indexOnly`, the flags `--skip-agents-md`, `--skip-skills` and `--index-only`, and the aliases `skipContextFiles`/`skipAiContext`. It says the latest is RC `1.6.13-rc.28` (2026-09-22). | **CONFIRMS** (WP-15 I1) | Verified in wave 2 against local `gitnexus analyze --help` and `dist/cli/analyze-config.js` (1.6.9). `npm view gitnexus version` shows **1.6.12** stable. The config **fails closed on unknown keys**, so the committed keys must stay in the supported set. | None. When upgrading to 1.6.13 or later, re-run `npx gitnexus analyze` and confirm `git diff CLAUDE.md AGENTS.md` stays empty (wave-2 exit criterion 3). |
| 5 | Model selection vs `.agents/model-routing.md` | The lineup is **Fable 5.1** (`claude-fable-5-1`, hardest long-horizon reasoning), **Opus 5.5** (`claude-opus-5-5`, demanding agentic coding), **Sonnet 5** (`claude-sonnet-5`, default balance) and **Haiku 4.5** (`claude-haiku-4-5-20251001`, fast and cheap). All support 1M context. Suggested subagent allocation: exploration on Haiku, escalating to Sonnet; planning, implementation and review on Sonnet, escalating to Opus for high-risk work; Fable used sparingly. Effort should track task difficulty. Subagent model resolution order is invocation → subagent `model` → `CLAUDE_CODE_SUBAGENT_MODEL` → main model. | **CONFIRMS** the existing tiered approach, and **ADDS** concrete aliases | The model IDs match this session's environment model list exactly. Prices ($10/$50, $4/$20, $2/$10, $1/$5 per MTok) are **as reported by Perplexity and not independently verified**. `model-routing.md` is deliberately vendor-neutral ("efficient model / frontier / most capable available"), which is correct for a multi-tool repo. | **WP-18 (optional):** add a short "Claude Code mapping" table beside, not replacing, the neutral tiers: efficient → `haiku`, reasoning → `sonnet`, frontier → `opus`, most capable → `opus` or `fable`, each with an effort hint. Keep both project subagents without `model` (inherit): their review scope includes security and SFDMU-destructive checks, which `model-routing.md` routes to "most capable". |

### 7.B Wave 3 Work Packages

There are no confirmed contradictions, so both packages are small hardening follow-ups taken from the **ADDS** findings. The ownership sets are disjoint, and neither package depends on the other.

| id | title | owned files/dirs (exclusive) | dependencies | acceptance criteria | size |
|---|---|---|---|---|---|
| **WP-17** | Portable hook interpreter on Windows (finding 1d) | `.claude/settings.json`, `.claude/hooks/**`, `tests/test_protect_generated_hook.py`, `docs/guides/windows-dev-setup.md` | none | 1. Both project hooks run successfully on:<br>&nbsp;&nbsp;(a) macOS or Linux with only `python3` on PATH;<br>&nbsp;&nbsp;(b) Windows with Microsoft Store Python (`python3.exe` alias);<br>&nbsp;&nbsp;(c) Windows with a python.org install (`python.exe` and `py.exe`, **no** `python3.exe`).<br>The mechanism is the worker's choice, but it must respect the docs' rule that on Windows exec form needs a real `.exe` (hooks.md `:475`). Options include shell form with `"shell": "bash"` and a quoted `"${CLAUDE_PROJECT_DIR}"` plus a `python3`/`python` fallback, or a documented per-user `settings.local.json` override. The PR records a manual run for each of the three cases, or explains why a case can't be tested here.<br>2. If no interpreter can be found, the failure is **visible**, not a silent spawn error. For example, the SessionStart check prints a one-line warning that the protect hook is inactive.<br>3. The protect-hook test still passes. `windows-dev-setup.md` states the interpreter requirement.<br>4. Optional: add `PowerShell(...)` mirrors of the four `allow` rules (finding 1c). | S |
| **WP-18** | Model-routing aliases and MCP least-privilege notes (findings 3b, 5) | `.agents/model-routing.md`, `docs/guides/agent-skill-discovery.md` (or `docs/guides/claude-code-setup.md` if WP-16 created it) | none | 1. `model-routing.md` gains a ≤10-line "Claude Code mapping" table from the vendor-neutral tiers to `haiku`, `sonnet`, `opus` and `fable`, with an effort hint. The neutral tiers stay authoritative. It says project subagents intentionally inherit the main model, and points to `CLAUDE_CODE_SUBAGENT_MODEL` for per-user overrides. It contains no prices, because they are unverified and volatile.<br>2. The opt-in Salesforce DX MCP section adds two lines: use a dedicated least-privilege integration user; the `mcp__salesforce__*` denies are a backstop, not the security boundary.<br>3. `analyze_agent_tooling.py check` and `skill_manifest.py --check` still pass. | S |

### 7.C Sources

**Perplexity citations** (as returned):
- **Q1a, memory and rules:**
  - https://code.claude.com/docs/en/memory
  - https://code.claude.com/docs/en/claude-directory
  - https://code.claude.com/docs/en/large-codebases
  - https://code.claude.com/docs/en/how-claude-code-works
  - https://code.claude.com/docs/en/glossary
  - https://github.com/anthropics/claude-code/issues/31005
  - https://www.infoworld.com/article/4224410/claude-code-now-also-accepts-instructions-in-openais-agents-md-format.html
  - https://www.mindstudio.ai/blog/claude-code-mods-agents-md
  - https://ccaf-exam.guide/fr/docs/07-claude-md-and-rules/
  - https://dev.to/thlandgraf/how-i-use-clauderules-to-give-claude-code-domain-knowledge-about-my-projects-file-structure-47l9
  - Localized memory pages: `/de`, `/fr`, `/ko`, `/id`, `/es`, `/ja`, `/it`
- **Q1b, permissions and hooks:**
  - https://code.claude.com/docs/en/settings-reference
  - https://code.claude.com/docs/en/permissions
  - https://code.claude.com/docs/en/hooks
  - https://code.claude.com/docs/en/skills
  - Localized permissions pages: `/fr`, `/pt`, `/zh-TW`, `/ko`
  - Localized hooks pages: `/de`, `/ru`, `/zh-CN`, `/zh-TW`
  - https://docs.claude.com/de/docs/claude-code/hooks
  - https://docs.claude.com/it/docs/claude-code/hooks
  - https://docs.arantic.com/claude-code/permissions
  - https://claudefa.st/blog/guide/development/permission-management
  - https://github.com/disler/claude-code-hooks-mastery
- **Q1c, subagents and skills:**
  - https://code.claude.com/docs/en/sub-agents
  - Localized sub-agents pages: `/fr`, `/ru`, `/zh-CN`, `/es`, `/ja`, `/ko`, `/zh-TW`
  - https://code.claude.com/docs/en/skills
  - https://code.claude.com/docs/en/agent-sdk/skills
  - https://code.claude.com/docs/en/plugins-reference
  - https://agentskills.io/specification
  - https://agentskills.io/skill.md
  - https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
  - https://atlan.com/know/ai-agent/ai-agent-skills/what-are-agent-skills/
  - https://www.useparagon.com/blog/what-are-agent-skills
- **Q2, claude-code-action:**
  - https://github.com/anthropics/claude-code-action/blob/main/docs/usage.md
  - https://github.com/anthropics/claude-code-action/blob/main/docs/migration-guide.md
  - https://github.com/anthropics/claude-code-action/blob/main/docs/configuration.md
  - https://github.com/anthropics/claude-code-action/blob/main/docs/security.md
  - https://github.com/anthropics/claude-code-action/blob/main/examples/claude.yml
  - https://github.com/anthropics/claude-code-action/pull/761
  - https://github.com/anthropics/claude-code-action/issues/1266
  - https://github.com/anthropics/claude-code-action/releases
- **Q3, Salesforce MCP and Windows:**
  - https://github.com/salesforcecli/mcp
  - https://www.npmjs.com/package/@salesforce/mcp
  - https://code.claude.com/docs/en/mcp
  - https://code.claude.com/docs/en/mcp-quickstart
  - https://code.claude.com/docs/en/agent-sdk/mcp
  - https://anthropic.mintlify.app/ja/docs/claude-code/mcp
  - https://raw.githubusercontent.com/Cranot/claude-code-guide/main/README.md
  - https://github.com/luongnv89/claude-howto/blob/main/05-mcp/README.md
- **Q4, GitNexus:**
  - https://github.com/abhigyanpatwari/GitNexus
  - https://github.com/abhigyanpatwari/GitNexus/blob/main/README.md
  - https://github.com/abhigyanpatwari/GitNexus/issues/243
  - https://github.com/abhigyanpatwari/GitNexus/releases
  - https://github.com/abhigyanpatwari/GitNexus/blob/main/RUNBOOK.md
- **Q5, models:**
  - https://docs.anthropic.com/en/docs/about-claude/models/overview
  - https://docs.anthropic.com/en/docs/about-claude/pricing
  - https://www.anthropic.com/claude-opus-5-5
  - https://www.anthropic.com/news/claude-sonnet-5
  - https://docs.anthropic.com/en/release-notes/api
  - https://code.claude.com/docs/en/subagents
  - https://code.claude.com/docs/en/workflows

**Primary sources ARCHITECT fetched to settle the contradictions:**
- https://code.claude.com/docs/en/mcp.md (no `cmd /c` note)
- https://code.claude.com/docs/en/hooks.md (exec form; the Windows `.exe` requirement at `:475`; event names)
- https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md (`:4043`, the `cmd /c` warning removed)
- https://raw.githubusercontent.com/salesforcecli/mcp/main/README.md (`DEFAULT_TARGET_ORG` examples)
- `npm view @salesforce/mcp` (0.30.15)
- `npm view gitnexus` (1.6.12)

**Reliability note.** In this pass Perplexity was right on documented behaviour, but it was wrong on three fast-moving facts: a package version, the removal of a warning, and hook event names. Where it cited localized or mirror pages, it tended to lag the English docs. Treat Perplexity as a **lead generator**, and settle version- and changelog-sensitive claims against the primary source.
