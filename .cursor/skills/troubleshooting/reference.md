# Timeout Reference, Diagnostic Commands & Live-Org Evidence

Read this for the timeout table, the general diagnostic-command cheat sheet,
and how to capture async-failure evidence before a reset destroys it. Parent
skill: [SKILL.md](SKILL.md).

## Timeout Reference

| Operation | Default Timeout |
|-----------|----------------|
| Apex execution (`sf apex run`) | 300s (5 min) |
| UX metadata deploy | 600s (10 min) |
| Stamp commit deploy | 300s (5 min) |
| PSG recalculation (per attempt) | 300s |
| PSG retry delay between attempts | 120s |
| SFDMU record count query | 60s per object |
| Pricing schedule repair | 6 × 10s polls |
| Row-lock retry backoff | 2s, 4s, 6s |
| GitHub Actions workflow | 120 min total |

## Diagnostic Commands

```bash
# Validate local setup
cci task run validate_setup

# Check org build info
sf data query -q "SELECT DeveloperName, RLM_Commit_Hash__c, RLM_Branch__c, \
  RLM_Build_Timestamp__c, RLM_Feature_Flags__c FROM RLM_Build_Info__mdt" --target-org rlm-base__beta

# Validate SFDMU datasets
python scripts/validate_sfdmu_v5_datasets.py

# Check billing structure
cci task run validate_billing_structure --org beta

# Query billing state
cci task run query_billing_state --org beta

# List decision tables with status
cci task run manage_decision_tables -o operation list --org beta

# List expression sets
cci task run manage_expression_sets -o operation list --org beta

# UX dry-run (assemble without deploy)
cci task run assemble_and_deploy_ux -o deploy false

# Clear source tracking corruption
rm -rf .sf/orgs/<org-id>/localSourceTracking

# Validate CML constraint model
cci task run validate_cml -o data_dir datasets/constraints/qb/QuantumBitComplete --org beta
```

## Live-Org Evidence Capture (RLM async / pricing / preprocess failures)

RLM async failures (Place Sales Transaction, preprocess, assetize, rating) leave their
root cause in **records, not stdout** — and that evidence is **destroyed by an account/
data reset**. So when a UI flow fails (e.g. "Preprocessing failed", "prices aren't
updated", an activation/repricing error):

1. **Capture before any reset.** Note the record id from the URL/UI, then query the
   error logs + async trackers + the record's calc state immediately:

```bash
# The actual failure reason (message + code + category)
sf data query --target-org $ORG -q "SELECT Category, ErrorCode, Severity, ErrorMessage, ConfiguratorErrorMessage, PrimaryRecordId, CreatedDate FROM RevenueTransactionErrorLog ORDER BY CreatedDate DESC LIMIT 15"
# Async job outcomes (PSTBaseJob/PSTPrice/PSTPersist/PreprocessOrder/AssetizationAsyncJob/QuoteToOrderJob)
sf data query --target-org $ORG -q "SELECT JobType, Status, ReferenceEntityId, CreatedDate FROM AsyncOperationTracker ORDER BY CreatedDate DESC LIMIT 25"
# The record's pricing/preprocess state (Order example)
sf data query --target-org $ORG -q "SELECT Status, CalculationStatus, ValidationResult, PreprocessingStatus FROM Order WHERE Id='<id>'"
```

2. **Interpret the signals.** `RevenueTransactionErrorLog.ErrorMessage` is usually the
   real reason; `CalculationStatus` is the pricing lifecycle; `ValidationResult != null`
   means "prices not current"; `AsyncOperationTracker.Status=Failure` pinpoints the failed
   async job. Settings/config live in metadata, not SOQL — retrieve them (see below), do
   not expect them in a query.

3. **Settings caution.** `sf project retrieve start -m Settings:RevenueManagement`
   decomposes org settings back into **existing** source paths (it can clobber
   `unpackaged/pre/1_settings/…` and other tracked copies). Retrieve to a throwaway, or
   `git checkout` the clobbered files afterward. Settings deploys **merge** field-by-field.

For the large-deal "Prepare for Activation" (reprice → preprocess → activate) flow
specifically — the `CalculationStatus` enum, the `ValidationResult` gate, async pricing
behavior, the `PreprocessingStatus` decode, and tax-skip — read
[`large-deal-preprocess-reference.md`](large-deal-preprocess-reference.md).

## Async rating/entitlement batch failed — find out why

Batch failures do not surface in the flow result. Query the forensic objects:

```bash
# Per-record failures inside a batch job part. NOTE the field names:
# ErrorDescription (not ErrorMessage) and Record (not RecordId).
sf data query -q "SELECT Id, ErrorDescription, Record, RecordName, Status FROM BatchJobPartFailedRecord ORDER BY CreatedDate DESC LIMIT 20" --target-org <alias>

# Entitlements that never finished processing.
# TransactionUsageEntitlement has NO Status field — EntitlementProcessingStatus
# is the only status, and its values are PENDING / PROCESSED.
sf data query -q "SELECT Id, Name, UsageModelType, EntitlementProcessingStatus FROM TransactionUsageEntitlement WHERE EntitlementProcessingStatus = 'PENDING'" --target-org <alias>
```

⚠ Entitlements for `CommitmentQuantity` / `CommitmentSpend` products are **known to
stay `PENDING`** on live orgs verified against — a platform issue, not a data defect.
Use a `Commit` model type (e.g. `QB-CMT-TKN-FLAT`) instead — it processes correctly.
See [`usage-consumption/SKILL.md`](../usage-consumption/SKILL.md) for the full usage
diagnosis flow.
