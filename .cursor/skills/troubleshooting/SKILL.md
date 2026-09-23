---
name: troubleshooting
description: >-
  Diagnose Revenue Cloud Foundations build, metadata deployment, data load, and local
  toolchain failures. Use when a CCI flow step fails, SFDMU loads misbehave, permissions
  or activation block deployment, or usage and rating results are unexpected.
---

# Troubleshooting & Common Errors

Use this skill when diagnosing failures in the rlm-base-dev build pipeline,
data loading, metadata deployment, or local environment setup. This is a
**router**: each category below is a short pointer to where the actual
error catalog lives — a sub-file here, or a domain skill when one already
owns that ground. Don't duplicate a domain skill's catalog back into this
file; add to the owning file instead.

## Quick Rules

1. Run `cci task run validate_setup` first — it checks everything. See
   [environment-setup.md](environment-setup.md).
2. CCI alias `beta` ≠ SF CLI alias `rlm-base__beta`. Never mix them.
3. SFDMU load fails → check stdout for specific object error. See
   [data-loading.md](data-loading.md).
4. Duplicates on re-run → missing `$$` composite key column in CSV.
5. Rating errors → always delete rates before rating (FK constraint). See
   [pricing-and-config-errors.md](pricing-and-config-errors.md).
6. Deploy fails → check for missing fields or wrong deploy order. See
   [deploy-and-permissions.md](deploy-and-permissions.md).
7. Source tracking corrupt → `rm -rf .sf/orgs/<org-id>/localSourceTracking`
8. Active billing records → can NEVER be deleted (platform constraint).
9. Rated usage reads **zero** with no error → an ordering problem, not a data
   problem. Route to [`usage-consumption/SKILL.md`](../usage-consumption/SKILL.md)
   — do not re-diagnose it here.
10. Pricing looks wrong but the data looks right → check decision-table
    freshness first: [`decision-tables/SKILL.md`](../decision-tables/SKILL.md).

## Quick Diagnosis: Which Step Failed?

The `prepare_rlm_org` flow runs 34 steps. Identify the failing step from
CCI output, then jump to the relevant section below.

| Step Range | Category | Where |
|-----------|----------|-------|
| 1 (prepare_core) | PSLs, PSGs, context defs, deploy_pre | [deploy-and-permissions.md](deploy-and-permissions.md) |
| 2–3 | Decision tables, expression sets | [`decision-tables/SKILL.md`](../decision-tables/SKILL.md), [pricing-and-config-errors.md](pricing-and-config-errors.md) |
| 5 (deploy_full) | Metadata deploy (force-app) | [deploy-and-permissions.md](deploy-and-permissions.md) |
| 9–11 | Product/pricing data load | [data-loading.md](data-loading.md) |
| 12 (prepare_docgen) | DocGen | [pricing-and-config-errors.md](pricing-and-config-errors.md) |
| 13 (prepare_dro) | DRO data load | [data-loading.md](data-loading.md) |
| 14–15 | Tax/billing data + activation | [data-loading.md](data-loading.md) |
| 18 (prepare_rating) | Rating/rates data + activation | [pricing-and-config-errors.md](pricing-and-config-errors.md) |
| *(post-build, runtime)* | Recording/rating usage, commitments, drawdown | [`usage-consumption/SKILL.md`](../usage-consumption/SKILL.md) |
| 22 (prepare_prm) | PRM community + data | [deploy-and-permissions.md](deploy-and-permissions.md) |
| 24 (prepare_constraints) | Constraints + CML import | [pricing-and-config-errors.md](pricing-and-config-errors.md) |
| 29 (prepare_ux) | UX assembly + deploy | [pricing-and-config-errors.md](pricing-and-config-errors.md) |
| 30 | Decision table refresh | [`decision-tables/SKILL.md`](../decision-tables/SKILL.md) |

## Sub-Files

| File | Contains |
|---|---|
| [`environment-setup.md`](environment-setup.md) | `validate_setup` failures, `sf`/`node` not found in IDE/CI, CCI-vs-sf org alias confusion, `INVALID_AUTH_HEADER`, `NonScratchOrgError`. |
| [`data-loading.md`](data-loading.md) | SFDMU load failures, idempotency re-run duplication, dynamic `AssignedTo` lookups, Billing & Tax errors, DRO `ExecuteOnRuleId`. |
| [`deploy-and-permissions.md`](deploy-and-permissions.md) | Metadata deploy component errors, deploy timeouts, source tracking corruption, PSG recalculation, context-definition apply errors, PRM/Community network deploy. |
| [`pricing-and-config-errors.md`](pricing-and-config-errors.md) | Rating/rates deletion ordering, expression-set row locks and Rank, unresolved CML/ESC associations, UX assembly, DocGen template errors. |
| [`reference.md`](reference.md) | Timeout reference table, general diagnostic-command cheat sheet, live-org async-failure evidence capture before a reset. |
| [`large-deal-preprocess-reference.md`](large-deal-preprocess-reference.md) | The large-deal "Prepare for Activation" (reprice → preprocess → activate) flow: `CalculationStatus`, `ValidationResult`, async pricing, `PreprocessingStatus`, tax-skip. |

## Where else to look

These categories are owned entirely by a domain skill — go there directly
rather than routing through this file:

| Symptom | Skill |
|---|---|
| Pricing right in data, wrong at runtime (stale decision table) | [`decision-tables/SKILL.md`](../decision-tables/SKILL.md) |
| Rated usage/consumption is zero, journals stuck `Pending`, commitment vs. anchor confusion | [`usage-consumption/SKILL.md`](../usage-consumption/SKILL.md) |
| Expression set authoring (steps, variables, overlays, activation lifecycle beyond a row-lock retry) | [`expression-sets/SKILL.md`](../expression-sets/SKILL.md) |
| Context definition/mapping authoring beyond a failed apply | [`context-service/SKILL.md`](../context-service/SKILL.md) |
| CML bundle authoring beyond an unresolved ESC association | [`constraint-models/SKILL.md`](../constraint-models/SKILL.md) |
| Document template authoring beyond a deploy failure | [`document-generation/SKILL.md`](../document-generation/SKILL.md) |
| SFDMU plan authoring (externalId, operations, dependencies) | [`sfdmu-data-plans/SKILL.md`](../sfdmu-data-plans/SKILL.md) |

## Validation Checks

- `cci task run validate_setup` passes before debugging anything else.
- `python scripts/validate_sfdmu_v5_datasets.py` reports 0 Critical/0 High
  after any data-load fix.
- A new failure class you diagnose here that recurs belongs in the owning
  sub-file or domain skill, not as a one-off note in this router.
