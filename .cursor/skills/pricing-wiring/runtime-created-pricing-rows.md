# Runtime-Created Pricing Rows & Decision-Table Staleness

Read this when a contract-price row written after org build isn't reflected in pricing (silently — no error). Parent skill: [SKILL.md](SKILL.md).

## Runtime-created pricing rows

A decision table goes stale the moment its source object gains or changes a row, and
pricing then silently prices as if that row did not exist — no error, no warning. Most
pricing sources in this repo are loaded once at org build and never touched again, so in
practice the tables stay correct. The ones that bite are the sources normal selling
writes to *after* the build.

`ContractItemPrice` / `ContractItemPriceAdjTier` are the case that bites: selling a contract
with contract prices writes rows that the three `Contract_Pricing_*` tables have not seen.
`RLM_Contract_Activation_Refresh_Pricing_Tables` (record-triggered on `Contract`) refreshes
all three when a contract becomes **Activated**, which covers every path — the UI Activate
button, REST/SOAP, Apex, another flow — because they all end in the same status change.

**Refresh on activation, not on creation.** The two tier tables filter their source on
`ContractItemPriceId.ContractId.StatusCode = 'Activated'` (inspect any table's filter via
`DecisionTableSourceCriteria`). A contract is created **Draft**, so a refresh fired at
creation time excludes that contract's tier rows and *still* stamps `LastSyncDate` — leaving
a table that reads fresh while holding nothing, which is worse than leaving it visibly stale.
`Contract_Pricing_Entries_Decision_Table` has no such filter, so only two of the three tables
show the symptom, which makes it easy to half-test and conclude the wrong thing.

A refresh is still needed by hand after a **bulk data load** of contract prices that does not
end in an activation:

```bash
cci task run refresh_dt_default_pricing
```

(`refresh_dt_*` tasks accept `--org` as of 2026-07-27 — `RefreshDecisionTable` now sets
`salesforce_task = True`. Before that they silently ran against the CCI **default** org.
`manage_expression_sets` and most other custom tasks still reject it; see issue #320.)

**Use `LastSyncDate` to decide whether a refresh happened.** It only advances on a refresh
that actually ran, so the staleness comparison above is the one check that holds for every
failure shape. Do not rely on `DecisionTable.RefreshStatus` / `RefreshFailureReason` as the
detector: they live *on a table record*, so they only tell you anything once a refresh has
been accepted for a table that exists.

Two failure shapes, measured against a live org — the difference matters before you add
error handling to a flow that calls `refreshDecisionTable`:

| Shape | What you get | Where it shows |
|---|---|---|
| Invalid or inactive `DecisionTableApiName` | **A Flow fault** (*"The decision table API Name is invalid…"*), not a `Failed` status | Nowhere on `DecisionTable` — an unresolvable name identifies no table record to stamp. Only the flow's own fault handling sees it. |
| Accepted refresh that then fails | `status = Queued`, async job result | `RefreshStatus` (observed cycling `Initiated` → `Completed`) and `RefreshFailureReason` |

Consequences:

- A flow calling this action needs a `faultConnector`, and in a **record-triggered
  after-save** flow it needs one urgently: an unhandled fault rolls back the triggering DML,
  so a refresh problem would block the very save that should have caused the refresh.
- The documented `status = Failed` output could not be provoked — a valid table returned
  `Queued` on every attempt, including five back-to-back refreshes of the same table.
- Because the fault case leaves no trace on the table, a flow that swallows the fault leaves
  `LastSyncDate` as the *only* evidence. That is by design, but it means the staleness check
  above is the monitoring story, not an afterthought.

To tell whether a table is stale, compare **each** table against **its own** source object's
newest `LastModifiedDate`. Two things make this easy to get wrong:

- The three tables do **not** share one source, so a single source query proves nothing about
  the other two: `Contract_Pricing_Entries_Decision_Table` ← `ContractItemPrice`, while
  `Contract_Pricing_Adjustment_Tiers` and `Contract_Pricing_Volume_Tiers` ←
  `ContractItemPriceAdjTier`.
- Use `LastModifiedDate`, not `CreatedDate`. An **edited** price row invalidates the table
  exactly as a new one does, and `CreatedDate` cannot see it.

The source query must also **reproduce the table's own source criteria**, or it reports rows
the table deliberately excludes. The tier tables only admit rows whose contract is Activated,
so an unfiltered `MAX` over a Draft contract's tiers would report them stale forever:

```bash
sf data query -q "SELECT DeveloperName, LastSyncDate FROM DecisionTable WHERE DeveloperName LIKE 'Contract_Pricing%' ORDER BY DeveloperName" --target-org <sf_alias>

# Entries <- ContractItemPrice, which has NO source criteria: no filter here.
sf data query -q "SELECT MAX(LastModifiedDate) newest FROM ContractItemPrice" --target-org <sf_alias>

# Both tier tables <- ContractItemPriceAdjTier, filtered to activated contracts.
# Note the SOQL relationship names differ from the criteria field path stored in
# DecisionTableSourceCriteria: ContractItemPriceId.ContractId -> ContractItemPrice.Contract
sf data query -q "SELECT MAX(LastModifiedDate) newest FROM ContractItemPriceAdjTier WHERE ContractItemPrice.Contract.StatusCode = 'Activated'" --target-org <sf_alias>
```

A table whose `LastSyncDate` is **earlier** than its own source's `newest` is stale, and the
contract's negotiated price is not being applied. A `null` `newest` means that source has no
qualifying rows, so its tables cannot be stale.

Generalising: read the table's real filter out of the org rather than assuming it has none —

```bash
sf data query -q "SELECT DecisionTable.DeveloperName, SourceFieldName, Operator, Value FROM DecisionTableSourceCriteria WHERE DecisionTable.DeveloperName = '<table>'" --target-org <sf_alias>
```

Never generalise one source's timestamp to a sibling table, and never compare against rows the
table would have excluded anyway.

---
