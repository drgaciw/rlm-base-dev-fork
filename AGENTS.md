# AI Agent Instructions — Revenue Cloud Base Foundations

> Canonical instructions for **any** AI coding agent working with this
> repository (Cursor, Claude Code, GitHub Copilot, Codex, Windsurf,
> Aider, or any future tool). Safety-critical rules that apply to every
> task. Detailed guidance lives in skill and topic-rule files, not here.

## Agent Entry Points

1. Read this file for universal rules; use [.cursor/skills/README.md](.cursor/skills/README.md)
   to select task guidance. Read a skill before using its tools.
2. `CLAUDE.md` imports this file (`@AGENTS.md`); edit `AGENTS.md` only for the
   shared contract. `.github/copilot-instructions.md` is a separate pointer.
3. [`REVIEW.md`](REVIEW.md) governs how reviews are conducted; this file governs
   required behavior. Keep them aligned; do not duplicate detail between them.
4. [`CONTRIBUTING.md`](CONTRIBUTING.md) covers contribution conventions.
   Governance companions: `LICENSE.txt` (Apache-2.0), `CODE_OF_CONDUCT.md`, `SECURITY.md`.
5. [`.agents/README.md`](.agents/README.md) describes routing, model guidance
   and project context. [Discovery setup and fallback](docs/guides/agent-skill-discovery.md).

## Project Overview

**Revenue Cloud Base Foundations** automates creation and configuration of
Salesforce environments for Revenue Lifecycle Management (RLM). `main` is the
active release line and the pull-request base branch; it is pre-GA, so **a
live org on the active release is ground truth, not documentation**. Release
identity (active release, API version, PR base branch) is tracked in
[`.agents/context/project-memory.json`](.agents/context/project-memory.json) —
treat it as the single source, not the numbers in this paragraph.

Key technology stack:
- **CumulusCI (CCI)** — orchestration engine for tasks and flows
- **SFDMU v5** — data import/export (`sf sfdmu run`), **v5.6.4+ required**
- **Salesforce DX / `sf` CLI** — metadata deployment and org management
- **Python** — custom CCI task classes in `tasks/`
- **Apex** — post-load activation scripts in `scripts/apex/`

See the [repository map](docs/references/repository-layout.md) for full layout
detail (`cumulusci.yml`, `tasks/`, `force-app/`, `unpackaged/`, `templates/`,
`datasets/`, `scripts/`, `tests/`, `robot/rlm-base/`).

## DO NOT — Safety Guards

1. **DO NOT** edit `unpackaged/post_ux/` — edit `templates/` instead. (`.claude/rules/ux-templates.md`)
2. **DO NOT** add profile `layoutAssignment`/`applicationVisibilities`, object `actionOverrides`, or `EmailTemplatePage` flexipages to `force-app/`/`templates/flexipages/` — see the rule for placement. (`.claude/rules/protected-metadata.md`)
3. **DO NOT** change SFDMU `operation: Upsert` to `Insert` + `deleteOldData: true` without explicit user approval. (`.claude/rules/sfdmu-export-json.md`)
4. **DO NOT** pass `access_token` to `sf` CLI commands — use `org_config.username` as `--target-org`. (`.claude/rules/cci-python-tasks.md`)
5. **DO NOT** commit real emails in `rlm.network-meta.xml` — use the placeholder. (`.claude/rules/protected-metadata.md`)
6. **DO NOT** commit or push directly to `main` or the active release branch (incl. `release/*`) — always use a feature branch and PR, including for docs and agent-instruction files. Never force-push without explicit user approval.
7. **DO NOT** present a behavioral Robot Framework change as verified on `robot --dryrun` alone — it never runs a browser. Behavioral changes need a live scratch-org run before merge. (`.claude/rules/robot-tests.md`)

## Org Identity: CCI vs SF CLI

CCI and `sf` CLI use **different alias registries** — never mix them:

| Context | Flag | Example |
|---------|------|---------|
| CCI task/flow | `--org <cci_alias>` | `cci task run insert_quantumbit_pricing_data --org beta` |
| SF CLI command | `--target-org <sf_alias_or_username>` | `sf data query -q "..." --target-org <sf_alias_or_username>` |

CCI alias `beta` maps to SF CLI alias `rlm-base__beta`. In Python tasks, use
`self.org_config.username` for CLI calls and `.access_token`/`.instance_url`
for REST API only.

## Common Workflows

```bash
cci task run insert_quantumbit_pricing_data --org beta
cci flow run prepare_rlm_org --org beta
cci task run assemble_and_deploy_ux -o deploy false   # dry-run: local assembly only
cci task run validate_setup                            # no org needed
python scripts/validate_sfdmu_v5_datasets.py
python scripts/ai/generate_cci_reference.py            # after cumulusci.yml edits
```

## Topic Rules

Detailed, path-scoped guidance for Claude Code (`.claude/rules/*.md`) is
generated from Cursor's source rules (`.cursor/rules/*.mdc`): SFDMU export/CSV
(`sfdmu-export-json.md`, `sfdmu-csv-data.md`), CCI (`cci-task-definitions.md`,
`cci-python-tasks.md`), Apex (`apex-scripts.md`, `apex-classes.md`), LWC
(`lwc-components.md`), UX templates (`ux-templates.md`), Robot tests
(`robot-tests.md`), Context Service plans (`context-plans.md`), doc review
(`doc-review.md`), protected metadata (`protected-metadata.md`), and
documentation conventions (`docs-conventions.md`). Read the one matching the
file you are editing before you edit it.

## Pre-merge checklist

Before opening or updating a PR, run `python scripts/ai/pr_gate.py --base origin/main`.
Every selected check gates; missing dependencies fail rather than skip;
inspect every result, including skips. `Mechanical checks` (GitHub Actions) is
a required check on `main` and the active release branch — do not path-filter,
rename, or shadow it. Full procedure, including SFDMU/CCI/doc-consistency
detail: [merge-and-review-procedures.md](.cursor/skills/audit-review/merge-and-review-procedures.md).

## PR Review Focus Areas

SFDMU v5 compliance, idempotency, Apex bulk safety, `cumulusci.yml` task
accuracy, CSV `$$` header/externalId alignment, UX templates vs generated
output, force-app profile safety, PRM Network placeholder emails, and
edition-flag (`pde`/`trial`) `when:` guards.

## Responding to Automated PR Reviews

Read [`REVIEW.md`](REVIEW.md) for standards. Handle every comment to
completion and finish every round with **zero unresolved threads**, verified
across all pages. Use `python scripts/ai/pr_review.py` (`status`/`handle`/`verify`)
or the `/pr-review <pr>` command; full procedure at
[merge-and-review-procedures.md](.cursor/skills/audit-review/merge-and-review-procedures.md#responding-to-automated-pr-reviews).

## Skill Catalog

Task-specific guidance lives in `.cursor/skills/` (plain Markdown, readable by
any agent). Start at [`.cursor/skills/README.md`](.cursor/skills/README.md)
for the full index, the Cursor-rule-to-skill mapping, and the skill-authoring
guide. Helper scripts are documented by the skill that owns them; the general
reference is [`scripts/ai/README.md`](scripts/ai/README.md).
