# Metadata Deploy, Permission & Context Errors

Read this when a deploy step, a Permission Set Group, or a context-definition
plan apply is failing. Parent skill: [SKILL.md](SKILL.md).

## Metadata Deploy Errors

### Deploy fails with component errors

Check the deploy result for specific component names. Common causes:

| Component Type | Likely Cause | Fix |
|---------------|-------------|-----|
| FlexiPage | References object/field not yet deployed | Ensure the referenced metadata is in `force-app/` or deployed in an earlier step |
| Layout | References field that doesn't exist | Add the field to the pre-deploy bundle |
| Profile | Contains `layoutAssignment` in `force-app/` | **Never** add layout assignments to `force-app/` profiles — use `templates/profiles/` |
| ExpressionSet | `__ATTRIBUTEPasID__` not replaced | XPath transform query failed — check `PriceAdjustmentSchedule` records exist |

### Deploy timeout (600s for UX, 300s for stamp)

**Cause:** Slow org response or large deploy payload.

**Fix:** Retry. If persistent, check org health and reduce deploy size by
using `metadata_type` or `metadata_name` options on `assemble_and_deploy_ux`.

### Source tracking corruption

**Symptom:** Deploy succeeds but `sf project deploy` complains about
conflicts on subsequent runs.

**Fix:**
```bash
rm -rf .sf/orgs/<org-id>/localSourceTracking
```

## Permission & PSG Errors

### Permission Set Group stuck in "Outdated"

**Cause:** PSG needs recalculation after PSL changes or deploy.

**Fix:** The `recalculate_permission_set_groups` task handles this
automatically — it touches the PSG Description field to trigger recalc,
then polls. If it times out:
1. Check PSG status in Setup → Permission Set Groups
2. Manually trigger recalculation
3. Increase `timeout_seconds` option (default 300s)

### PSG recalculation fails with "Failed" status

**Cause:** Conflicting permissions in the PSG's member permission sets.

**Fix:** Check Setup → Permission Set Groups → the failing PSG for conflict
details. Remove conflicting permission set members.

## Context Definition Errors

### `INSUFFICIENT_ACCESS` on context plan apply

**Cause:** Connect API PATCH rejects relationship-traversal hydration rules.

**Fix:** This is handled automatically by the task — it falls back to
direct SObject REST API calls for `ContextAttributeMapping` and
`ContextAttrHydrationDetail` records. If it still fails, verify the running
user has the correct PSLs assigned.

### Context definition not found

**Cause:** `developer_name` doesn't match any existing context definition.

**Fix:** Context definitions are extended at runtime by `extend_context_*`
tasks in `prepare_core` (step 1). Ensure `prepare_core` ran successfully
before the failing step.

For context definition/mapping authoring beyond these two failure modes, see
[`context-service/SKILL.md`](../context-service/SKILL.md).

## PRM & Community Errors

### Network deploy fails (emailSenderAddress)

**Cause:** The committed `rlm.network-meta.xml` uses a placeholder email.
The `patch_network_email_for_deploy` task replaces it with the org's actual
email before deploy.

**Fix:** If the patch task fails, the Network's email is immutable after
creation. Verify the Network exists with:
```bash
sf data query -q "SELECT Id, Name, UrlPathPrefix FROM Network" --target-org rlm-base__beta
```

### Placeholder email committed to repo

**Cause:** `revert_network_email_after_deploy` didn't run after deploy.

**Fix:** Run it manually:
```bash
cci task run revert_network_email_after_deploy
```
Or reset the file: `git checkout -- unpackaged/post_prm/force-app/main/default/networks/rlm.network-meta.xml`
