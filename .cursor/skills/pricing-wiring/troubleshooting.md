# Pricing-Wiring Troubleshooting Decision Tree

Read this when a pricing-procedure deploy, lookup, or procedure-plan overlay step is failing. Parent skill: [SKILL.md](SKILL.md).

## Troubleshooting Decision Tree

### `lookup table ... ListPrice ... valid`

Check in order:

1. placeholder resolution applied in deploy transforms
2. decision table exists
3. recipe-to-table mapping row exists for target recipe
4. mapping component type is correct

### Wrong-currency price returned (multicurrency orgs)

A lookup step that does **not** pass `CurrencyIsoCode` matches the first row for the
product regardless of currency — so every currency silently prices at whichever row
the table returns first. The symptom is a *plausible* price, not an error.

**Fix:** add `CurrencyIsoCode` as an input on **every** lookup step that resolves a
currency-denominated value — list price, adjustment schedule, and adjustment tier
lookups alike. Missing it on the tier step alone still yields wrong discounts.

Currency must also *reach* the record for the step to filter on it. Records created
by quick actions and flows default to the **running user's** currency, not the
account's, so wire currency inheritance explicitly. Two before-save flows show the
pattern — note their **placement differs by scope**:

| Flow | Lives in | Why |
|------|----------|-----|
| `RLM_Default_AssetRateCard_Currency` | `force-app/main/default/flows/` | Foundational. An `AssetRateCardEntry` whose currency differs from its Asset is *always* wrong; the platform defaults it to USD and never inherits (262, no config remedy). Every multicurrency build needs this. |
| `RLM_Default_Opportunity_Currency` | `unpackaged/post_quantumbit/flows/` | Feature-specific. It **enforces** account currency, so a deliberately cross-currency Opportunity cannot be created while it is active — acceptable for the QB demo, not something to impose on every build. Gated behind the `quantumbit` flag. |

The distinction generalises: a flow that corrects an always-wrong platform default is
foundational; one that removes a legitimate user choice to suit a demo belongs in
that demo's feature bundle.

Offline guard: `python tests/test_qb_multicurrency_data.py`.
Live guard: `cci task run validate_multicurrency_rates`.

### active version update failures

Confirm deactivate step runs before deploy and targets correct versions.
Note: there are two distinct deactivation gates:

1. **ExpressionSetVersion** — the `deactivate_expression_sets` task handles this
2. **ProcedurePlanDefinitionVersion** — if the expression set is referenced by an
   active plan version, that plan version must also be deactivated before deploy.
   The plan version lock produces a generic "unexpected error" distinct from the
   expression set version lock.

### Connect API mutation errors (`Error processing JSON`, `resourceInitializationType`, version-id)

These are Expression Set CRUD mechanics, not pricing-layering issues — the full
error register (HTML-entity parsing failures, opaque-error bisection, immutable
`resourceInitializationType`, version-id handling, `contextDefinitions[].id`,
admin permission) lives in **`.cursor/skills/expression-sets/SKILL.md`** and its
reference's *Known errors & conditions* table. Come back here for the
pricing-specific deploy error below.

### `ExpressionSetDefinition ... unexpected error occurred`

When the deploy error is generic and points at a single expression set:

1. check whether an active `ProcedurePlanDefinitionVersion` references the
   expression set — an active plan version locks the expression set from
   metadata API updates. Deactivate the plan version first, deploy, then
   reactivate.
2. run a targeted dry-run deploy for that expression set only
3. diff against last known-good version
4. inspect changed steps for duplicate parameter names (especially `LookUpId`)
5. confirm lookup strategy is coherent (`LookUpApiName` baseline, `LookUpId` only when intentional)

### Expression sets fail deploy via raw `sf project deploy`

Expression sets containing `__LOOKUPID_*__` placeholder tokens cannot deploy
via `sf project deploy start` — placeholders are not valid Salesforce record
IDs and the metadata API rejects them. Always use `cci task run
deploy_expression_sets` (or `activate_and_deploy_expression_sets`), which
applies `find_replace` transforms from `cumulusci.yml` to resolve placeholders
to real DecisionTable IDs via SOQL before deploying.

### procedure-plan overlay succeeds only on rerun

Check whether the overlay is still using fixed numeric sequences or separate
manual move steps. Rework it to use `placement.afterSubSectionType` so the task
creates/patches sections first, computes the full target order from the org, and
resequences with a temporary high-sequence pass. A first run that partially moves
sections and only succeeds on rerun usually means sequencing is not owned by the
overlay task.

### feature flow fails before mapping step

Treat as unrelated until proven otherwise (missing metadata/field dependencies can
mask mapping validation).

### `Invalid tag attribute name key`

Usually indicates context definition drift:

1. required context attribute/tag was not applied in target org
2. feature context plan was not wired/run in the flow
3. context plan points to wrong context definition/mapping

---
