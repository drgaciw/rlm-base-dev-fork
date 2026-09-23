# The Proven Group-Ramp Build Sequence

Read this when building a multi-year group ramp end to end: the four Connect calls (create → EditGroup → clone × N-1 → compound-uplift PATCH) and the `CalculationStatus` polling contract between them. Parent skill: [SKILL.md](SKILL.md).


`<PLACEHOLDER>` values are ids you resolve first (see [Discovering ids](SKILL.md#discovering-ids)).
Windows are contiguous per-period spans. For **`SegmentType=Yearly`** each segment
must be **exactly 365 days** (`ind.qocal_ramp_deal_for_groups_create.htm.md`:
"exactly 365 days for all segments, fixed") — so use `StartDate` + 364 days, **not**
calendar-year spans: a leap year (e.g. 2028 = 366 days) violates the Yearly rule.
For variable or true calendar-year durations use **`SegmentType=Custom`** instead.
(The `2026`/`2027` examples below happen to be 365-day years; a 3-year ramp reaching
2028 would need the 365-day form or `Custom`.)

**Multi-schedule mode (repo default).** With `enableGroupRampMultiSchedulePref=true`
(this repo's setting), `EditGroup` produces the **two-level** structure — a top-level
`Type='RampScheduleGroup'` group with the period segments nested under it — and
`RampUpliftType` is set on that **parent** (Quick Rule 5). After each mutating call,
read the groups back (`SELECT Id, Type, ParentQuoteLineGroupId, IsRamped FROM
QuoteLineGroup WHERE QuoteId='<QUOTE_ID>'`) to get the parent-schedule and
last-segment ids rather than assuming them.

### 1. `placeSalesTransaction` (create) — Quote + group + lines

`POST /connect/rev/sales-transaction/actions/place`. Fields are **siblings of
`attributes`**, not nested under a `fields` key; `@{refX.id}` wires children to
parents created in the same call.

```json
{
  "pricingPref": "System",
  "configurationPref": { "configurationMethod": "Skip" },
  "graph": { "graphId": "rampCreate", "records": [
    { "referenceId": "refQuote", "record": {
        "attributes": { "type": "Quote", "method": "POST" },
        "Name": "<deal name>", "QuoteAccountId": "<ACCOUNT_ID>",
        "CurrencyIsoCode": "<ACCOUNT_CURRENCY>",
        "Status": "Draft", "Pricebook2Id": "<PRICEBOOK_ID>" } },
    { "referenceId": "refGroup", "record": {
        "attributes": { "type": "QuoteLineGroup", "method": "POST" },
        "Name": "Year 1", "QuoteId": "@{refQuote.id}" } },
    { "referenceId": "refLine0", "record": {
        "attributes": { "type": "QuoteLineItem", "method": "POST" },
        "QuoteId": "@{refQuote.id}", "QuoteLineGroupId": "@{refGroup.id}",
        "Product2Id": "<PRODUCT2_ID>", "PricebookEntryId": "<PBE_ID>",
        "Quantity": 1, "SubscriptionTerm": 12,
        "StartDate": "2026-01-01", "EndDate": "2026-12-31",
        "PeriodBoundary": "AlignToCalendar", "BillingFrequency": "Monthly",
        "BillingTreatmentId": "<TREATMENT_ID>" } }
  ] }
}
```

Add one `refLineN` per product. A ramp line needs **both** `Product2Id` and
`PricebookEntryId` (PBE alone fails). For **group** ramps the product needs **no
per-product ramp flag** — all subscription (term-defined) products that meet the
requirements are eligible by default (264 Help, *Ramp Deals for Groups Transition*);
`Product2.CanRamp` gates the *line*-ramp path, not this one. Set
`CurrencyIsoCode` on the Quote to the **account currency** — this repo enables
multicurrency (`config/project-scratch-def.json`), so omitting it lets the quote take
the running user's currency and mismatch the PBE/billing-treatment currency (the
proven builder sets it, `scripts/build_quote_to_asset.py`).
`BillingTreatmentId` is **required** for a term-defined line with a `BillingFrequency`:
the Place call fails with no treatment ("Add a Billing Treatment…") *and* if the
referenced treatment has `CanChangeBillingFrequency=false` ("Update the Billing
Treatment…"). Resolve one for the account currency (see [Discovering ids](SKILL.md#discovering-ids));
this mirrors `scripts/build_quote_to_asset.py`.

> **Check the response body after every Place call — a returned Quote id is not
> success.** `place` reports per-record graph failures in an **`errorResponse`** array
> while still returning **HTTP 200** *and* still creating the parent `Quote` (a naive
> "did I get a quote id?" check then proceeds on a quote with no/partial lines, and
> polling it can look settled). Before polling, fail on a top-level `errorCode`, and on
> a dict response fail if `errorResponse` is non-empty **or** `isSuccess === false`.
> This applies to the create call here and the `EditGroup` call in step 2; the proven
> builder does exactly this (`scripts/build_quote_to_asset.py`). (The `clone` call in
> step 3 has its own contract — `success:false` + populated `errors[]` — covered there.)

### 2. `placeSalesTransaction` (EditGroup) — mark period 1 ramped

Same endpoint, with **`groupRampAction: "EditGroup"`**. This flips the group and
stamps `RampIdentifier` on its lines. In multi-schedule mode (repo default) the
platform also creates the top-level `RampScheduleGroup` here and nests this segment
under it — read the groups back afterward to capture the parent-schedule id (needed
for `RampUpliftType` in step 4) and the segment id.

```json
{
  "groupRampAction": "EditGroup",
  "pricingPref": "System",
  "graph": { "graphId": "rampEdit", "records": [
    { "referenceId": "q", "record": {
        "attributes": { "type": "Quote", "method": "PATCH", "id": "<QUOTE_ID>" } } },
    { "referenceId": "g", "record": {
        "attributes": { "type": "QuoteLineGroup", "method": "PATCH", "id": "<GROUP_ID>" },
        "StartDate": "2026-01-01", "EndDate": "2026-12-31",
        "SortOrder": 1, "IsRamped": true, "SegmentType": "Yearly" } }
  ] }
}
```

### 3. `cloneSalesTransaction` — add each subsequent period

`POST /connect/rev/sales-transaction/actions/clone`, once per additional period,
each cloning the most recent ramped group:

```json
{ "salesTransactionId": "<QUOTE_ID>",
  "recordIds": [ "<LAST_RAMPED_GROUP_ID>" ],
  "options": { "lineScope": "AllLines" } }
```

The v68 clone response is `{ requestId, salesTransactionId, success, errors }`
(`docs/salesforce/264/dev-guide/articles/connect_responses_clone_sales_transaction_output.htm.md`)
— there is **no** `trackerId`. `success:false` with a populated `errors[]` is a
synchronous failure — stop. On `success:true` the save runs **async**: `requestId`
identifies that process, and the observable gate is `Quote.CalculationStatus` —
poll it to a settled state ([Status](#status)) before the next call. Do **not**
read or clone the next group until it settles; then read back the new group's id
for the next clone.

### 4. `placeSalesTransaction` (PATCH) — apply compound uplift, then reprice

Cloning copies the prior segment as-is; it does **not** set the uplift. To produce a
compound ramp you must, after the segments exist, PATCH `RampUpliftType='Compound'`
onto the **top-level `RampScheduleGroup`** (multi-schedule; the single segment group
when the setting is off) and the per-segment **`UnitPriceUplift`** onto each segment's
line, in one Place graph, then reprice and poll. This step is what actually yields the
compound result — the three calls above alone do not. It also needs the fully-configured
`PriceRevision` engine ([Compound uplift](SKILL.md#compound-uplift)).

```json
{
  "pricingPref": "Force",
  "graph": { "graphId": "rampCompound", "records": [
    { "referenceId": "q", "record": {
        "attributes": { "type": "Quote", "method": "PATCH", "id": "<QUOTE_ID>" } } },
    { "referenceId": "sg", "record": {
        "attributes": { "type": "QuoteLineGroup", "method": "PATCH", "id": "<RAMP_SCHEDULE_GROUP_ID>" },
        "RampUpliftType": "Compound" } },
    { "referenceId": "l1", "record": {
        "attributes": { "type": "QuoteLineItem", "method": "PATCH", "id": "<SEGMENT_2_LINE_ID>" },
        "UnitPriceUplift": 5 } },
    { "referenceId": "l2", "record": {
        "attributes": { "type": "QuoteLineItem", "method": "PATCH", "id": "<SEGMENT_3_LINE_ID>" },
        "UnitPriceUplift": 3 } }
  ] }
}
```

Segment 1 is the baseline (leave `UnitPriceUplift` 0). `pricingPref: "Force"`
re-runs pricing so the engine applies the compound uplift. Poll `CalculationStatus`
to a settled state, then read back ([Read-back](SKILL.md#read-back--the-ramp-schedule)) and
verify the compounding numerically.

> **Apex-invocable variant.** Some connectors expose clone as a CLASSIC Apex
> invocable whose args are wrapped in an `inputs` array. `lineScope` lives inside the
> Apex-defined **`options`** input (with optional `recordTypeId`), not at the top level
> (`actions_obj_deep_clone_sales_transaction.htm.md`):
> `{ "inputs": [ { "salesTransactionId": "...", "recordIds": ["..."], "options": { "lineScope": "AllLines" } } ] }`.
> Same semantics; use whichever the transport exposes.

### <a name="status"></a>Poll `CalculationStatus` between calls

`Quote.CalculationStatus` is read-only and moves through tax/price/save states.
Match against the **live v68 enum** (from `scripts/erd/schema_diff/264-schema.json`),
not a suffix wildcard — several in-flight values are `QueuedFor…`-**prefixed** (they
do not *end* in `Queued`) and `TaxCalculationInProcess` is not `…InProgress`:

- **Settled — success:** `CompletedWithTax` (the org returns this where the describe
  lists `TaxCalculationSuccess` — treat both as success); `CompletedWithoutPricing`
  (settled, but pricing was **skipped** — not a priced result, so do not report
  prices from it).
- **`CompletedWithPricing` — settled *only when tax is skipped*.** It means pricing
  is complete and **tax is now calculating** (order/quote field reference). The
  examples here omit `taxPref`, and `taxPref` defaults to **running** tax
  (`connect_requests_place_sales_transaction_input.htm.md`), so in this flow
  `CompletedWithPricing` is **still in-flight** — wait for `CompletedWithTax`. It is
  terminal only if you passed `taxPref: "Skip"` (then no `CompletedWithTax` follows).
- **Settled — failure (terminal):** any `…Failed` — `TaxCalculationFailed`,
  `PriceCalculationFailed`, `SaveFailedOrIncomplete`, `ConfigurationFailed`,
  `ReconciliationFailed`, `GroupRampConfigurationFailed`, `PstBaseStepFailed`,
  `ARCStepFailed`, `QuoteRequestFailed`, `CloneFailed`.
- **In-flight (keep polling):** `NotStarted`, `TaxCalculationWaiting`,
  `TaxCalculationInProcess`, `PriceCalculationQueued`, `PriceCalculationInProgress`,
  `Saving`, `ConfigurationInProgress`, `ReconciliationInProgress`,
  `ContextHydrationInProgress`, `ARCInProgress`, `CloneInProgress`, and every
  `QueuedFor…` value (`QueuedForConfiguration`, `QueuedForPricing`,
  `QueuedForPricingAndSaving`, `QueuedForSaving`, `QueuedForARC`, `QueuedForClone`).

**A value in none of these = stop and look**, not "keep polling" or "assume done".
