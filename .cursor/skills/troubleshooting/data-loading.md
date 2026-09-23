# SFDMU Data Loading Errors

Read this when a data-plan load fails or an idempotency re-run duplicates
records. For plan authoring itself, see
[`sfdmu-data-plans/SKILL.md`](../sfdmu-data-plans/SKILL.md). Parent skill:
[SKILL.md](SKILL.md).

## Load fails with non-zero exit code

Check the SFDMU stdout for the specific object and error. Common causes:

| Symptom | Cause | Fix |
|---------|-------|-----|
| `has no mandatory external Id field definition` | All-multi-hop externalId (v5 Bug 1) | **Fixed at the 5.6.4+ floor** — should not occur; if it does, verify the plugin is ≥5.6.4 (`validate_setup`) |
| Invalid SOQL generated | 2-hop traversal column in Upsert (v5 Bug 2) | **Fixed in 5.6.3** — should not occur on the 5.6.4+ floor; verify the plugin version |
| Duplicates on every run | Relationship-traversal externalId in Upsert (v5 Bug 3) | **Fixed in 5.6.4** — Upsert matches on the floor; verify the plugin version. (Do NOT switch to `Insert`+`deleteOldData` citing this bug.) |
| `REQUIRED_FIELD_MISSING` | Parent records not loaded yet | Check plan dependency order (PCM before pricing/billing) |
| `DUPLICATE_VALUE` | Composite key mismatch | Verify `$$` column in CSV matches `externalId` fields |

## Idempotency test fails (record count increased)

**Cause:** Missing or mismatched `$$` composite key column in the CSV. The
second load inserts instead of matching.

**Fix:** Verify that `$$` column header in CSV matches the `externalId`
fields exactly (e.g., `externalId: "Field1;Field2"` → CSV header
`$$Field1$Field2`). Run `python scripts/validate_sfdmu_v5_datasets.py` to
check all plans.

## Dynamic `AssignedTo` user lookup fails

**Cause:** `dynamic_assigned_to_user: true` queries the org for a user, but
the org auth is token-only (no username).

**Fix:** Use `cci org connect` instead of JWT-only auth, or set the username
in the org config.

## Billing & Tax Errors

### Active billing records can't be deleted

**Cause:** Platform constraint — Active `BillingTreatment` and
`BillingTreatmentItem` records can never be deleted.

**Fix:** `deleteDraftBillingRecords.apex` only deletes Draft records. Active
billing records must be deactivated before deletion (if the platform allows),
or the org must be recreated.

### BillingTreatment missing BillingPolicyId

**Cause:** Data load ordering issue — BillingTreatment loaded before its
parent BillingPolicy.

**Fix:** Validate structure first:
```bash
cci task run validate_billing_structure --org beta
```
Then reload: delete billing data and re-run `insert_billing_data`.

## DRO Errors

### ProductFulfillmentDecompRule missing ExecuteOnRuleId

**Cause:** Salesforce 260 platform bug — `ExecuteOnRuleId` not created on
INSERT.

**Fix:** The `update_product_fulfillment_decomp_rules` task re-saves the
records to trigger ruleset generation. If it still fails, manually re-save
in Setup.
