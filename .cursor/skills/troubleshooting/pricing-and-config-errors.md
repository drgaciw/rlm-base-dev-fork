# Rating, Expression Set, Constraint & UX Assembly Errors

Read this when rate/rating record deletion is blocked, an expression set
activation is stuck, a constraint import leaves unresolved associations, or
assembled UX content looks wrong. Parent skill: [SKILL.md](SKILL.md).

For **stale decision-table lookups** (pricing right in the data, wrong at
runtime), that diagnosis lives in
[`decision-tables/SKILL.md`](../decision-tables/SKILL.md) — do not duplicate
it here.

## Rating & Rates Errors

### PUR activation fails: "effective period overlaps"

**Cause:** Duplicate Draft PURs exist (from re-running the plan without
deleting first).

**Fix:**
1. Delete rates data first: `cci task run delete_qb_rates_data --org beta`
2. Delete rating data: `cci task run delete_qb_rating_data --org beta`
3. Re-load: `cci task run insert_qb_rating_data --org beta`

**Critical:** Always delete rates before rating (FK constraint).

### PUR deactivation ordering

**Cause:** Platform requires PURs to be deactivated in a specific order —
can't deactivate a PUR when related PURs on the same Product are still Active.

**Fix:** The `deleteQbRatingData.apex` script handles this with iterative
`Database.update(records, false)` (partial success) in a loop until all
are deactivated. If it hangs, check for PURs with unexpected relationships.

### Rate card entry deletion blocked

**Cause:** Can't delete rate adjustment records when related rate card entries
are inactive.

**Fix:** `deleteQbRatesData.apex` deletes in correct dependency order:
RateAdjustmentByTier → RateCardEntry → PriceBookRateCard → RateCard.

## Expression Set Errors

### Row lock during activation/deactivation

**Symptom:** `UNABLE_TO_LOCK_ROW` error.

**Cause:** Concurrent access to expression set version records.

**Fix:** Automatic — the task retries 3 times with linear backoff (2s, 4s,
6s). If it still fails, wait and retry manually.

### Expression set activated without Rank

**Symptom:** Expression set version can't be deactivated or edited.

**Fix:** The `updateExpressionSetVersions.apex` script sets Rank before
activating. If you hit this manually, use Tooling API to update the version's
Rank field first.

For authoring expression sets (steps, variables, overlays), see
[`expression-sets/SKILL.md`](../expression-sets/SKILL.md).

## Constraints / CML Errors

### Unresolved ESC associations

**Cause:** Product catalog (qb-pcm) not loaded before constraint model
import.

**Fix:**
1. Load PCM data: `cci task run insert_quantumbit_pcm_data --org beta`
2. Retry import: `cci task run import_cml -o data_dir <path> --org beta`

For deeper CML authoring/diagnosis, see
[`constraint-models/SKILL.md`](../constraint-models/SKILL.md).

## UX Assembly Errors

### AppSwitcher deploy blocked

**Symptom:** AppSwitcher excluded from deploy; warning logged.

**Cause:** Org's AppMenu contains managed ConnectedApp or Network entries that
the Metadata API can't validate.

**Fix:** This is by design. The `reorder_app_launcher` task (step 2 of
`prepare_ux`) handles App Launcher ordering via Aura XHR. No action needed.

### Assembled UX has wrong content

**Cause:** Editing `unpackaged/post_ux/` directly instead of `templates/`.

**Fix:** Edit the source templates, then re-assemble:
```bash
cci task run assemble_and_deploy_ux -o deploy false
```
Inspect `unpackaged/post_ux/` to verify, then deploy.

## DocGen Errors

### DocumentTemplate binary mismatch

**Symptom:** All DocumentTemplates have the same binary content after deploy.

**Cause:** Salesforce Metadata API bug — all DocumentTemplates deployed in a
single batch receive the same ContentDocument binary (first alphabetically).

**Fix:** The `fix_document_template_binaries` task corrects this by uploading
the correct `.dt` binary for each template. Ensure it runs after
`deploy_post_docgen` + `activate_docgen_templates`.

### EmailTemplatePage deploy fails

**Cause:** `EmailTemplatePage` flexipages cannot be deployed via Metadata API
(permanent platform restriction).

**Fix:** These are in `.forceignore`. The templates are created at runtime by
`create_approval_email_templates` via the REST API. Do NOT add
`EmailTemplatePage` files to `templates/flexipages/`.

For template authoring beyond deploy failures, see
[`document-generation/SKILL.md`](../document-generation/SKILL.md).
