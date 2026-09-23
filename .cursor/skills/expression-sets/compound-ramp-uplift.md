# Compound Ramp Uplift

Read this when checking whether compound ramp uplift is enabled/configured, diagnosing why a ramp priced as standard instead of compound, or building a compound-capable ramp quote. Parent skill: [SKILL.md](SKILL.md) — linked from its Entry Conditions table.


Compound ramp uplift (each ramp segment's price uplifts on the *prior segment's*
factor, not the list price) is a **group-ramp + pricing-procedure** capability.
The procedure element is this skill's turf; the rest is Revenue Settings + a
**group** ramp deal. It is **not** a line field you set — `RampUpliftType` is
read-only on `QuoteLineItem`/`OrderItem` (Place API, Apex, and Tooling all reject
a write) and lives on the `QuoteLineGroup`, cascading to its ramped lines.

**Five prerequisites** (Salesforce Help: *"Compound Uplift in Ramp Deals"*,
*"Create Ramp Deals with Standard or Compound Price Uplifts"*):

1. **Revenue Settings → Advanced Detail Line Pricing = ON** — this repo now defaults it
   **ON** (`unpackaged/pre/1_settings/RevenueManagement.settings-meta.xml`,
   `enableAdvancedDetailLinePricing=true`), so compound is available (it is hidden from the
   Ramp Uplift Type picklist only when ADLP is off). The 264 Help's hand-authoring path
   (*Compound Uplift for Ramp Deals* → *Use Advanced Transaction Detail Line Pricing to Map
   Custom Fields*) — clone the template, add a map line item mapping
   `ItemApplUnitPriceUpliftPct__std` → `itemDetailApplUnitPriceUpliftPct__std`, sync the
   context — is **not required in this repo**: the tracked `RLM_DefaultPricingProcedure`
   already ships the ramp-path compound `PriceRevision` (prerequisite 4), and the bound
   ramp attributes plus the `itemDetailApplUnitPriceUpliftPct__std` target are
   **standard/inherited** from base `SalesTransactionContext`, so no clone, no map line,
   and no context sync are needed (verified on a fresh 264 build). Off ⇒ standard
   (list-based) uplift only; turning it off *after* compound quotes/orders/assets exist
   corrupts pricing, amendments, renewals.
2. **Ramp Deals for *Groups*** (a group ramp), **not** the line-level ramp path.
   A single-line `createRampDeal` yields ungrouped segments
   (`QuoteLineGroupId=null`) — no group to hold the uplift mode, so it can never
   compound.
3. **`RampUpliftType='Compound'` on the ramp group** — with *Multiple Ramp Schedules
   Per Transaction* on (the repo default), set it on the **top-level `RampScheduleGroup`**;
   with it off, on the single ramp segment group. On individual segment groups and
   lines the type is **read-only**. It cascades to every ramped line in the schedule.
4. **A fully-configured ramp `PriceRevision` element** — `IsCompoundUpliftEnabled=true`
   (UI *"Enable Compound Uplift"*) is *necessary but not sufficient*. Per the 264 Help
   (*Use the Price Revision Element in a Pricing Procedure*), the checkbox appears
   **only after a lookup table is selected**, and exposes bindings that must all be set:

   | Binding | Rule (blank / wrong ⇒) |
   |---|---|
   | **Ramp Identifier** | Groups a ramp's segments so they compound independently; lines with no Ramp Identifier price independently |
   | **Base Price Multiplier** | Blank ⇒ 1 for a new sale; for amend/renew, the ramp's compounded multiplier from the prior transaction |
   | **Uplift Method** | **Blank ⇒ silently *standard* (no compounding)** — this is the quiet failure mode |
   | **Effective From** / **Effective To** | Segment date range; **every segment needs a *unique* Effective From** — a missing or duplicated one **fails pricing for the entire ramp group**, not just that segment |

   Note: changing/removing the lookup table auto-clears `IsCompoundUpliftEnabled`. The 264
   Help says compound "requires a newly-created procedure" — that is a **UI-authoring**
   limitation (the builder won't let you enable compound uplift on an existing procedure);
   deploying the full expression-set metadata bypasses it. The tracked
   `RLM_DefaultPricingProcedure` in this repo **now ships two** `PriceRevision` BKMs — the
   long-standing **non-ramp** step, **and** the **ramp-path** compound step (migrated from
   the old `FormulaBasedPricing` `Uplift` BKM by metadata deploy). Compound ramp uplift
   therefore works on the tracked default out of the box; no clone is needed:

   | BKM step (parent filter) | Kind in tracked default | Drives |
   |---|---|---|
   | `AdjustNetUnitPriceandSubtotalbyusingpricerevision` under *Apply price revision for lines with subscription and without derived pricing* | `PriceRevision` (present) | non-ramp price revision |
   | `Uplift` under *Apply uplifts to ramped subscriptions items during amendment* (filter requires `IsLineGroupRamped__std=true` AND `ItemRampIdentifier IS NOT NULL`) | `PriceRevision` with `IsCompoundUpliftEnabled=true` (migrated from `FormulaBasedPricing`) | **compound** ramp uplift when `RampUpliftType=Compound`; flat when `Standard` |

5. **`UnitPriceUplift` (per-year %) set per segment** (writeable). First segment
   is the baseline (applied uplift = its own line uplift, usually 0); a 0% segment
   is a *carryover* (prior cumulative multiplier preserved, not reset).

Compounding math (in **percent units**, matching `UnitPriceUplift` /
`ApplUnitPriceUpliftPct`):
`applied%(n) = [(1 + applied%(n-1)/100) × (1 + unitUplift%(n)/100) − 1] × 100`, and
`NetUnitPrice(n) = base × (1 + applied%(n)/100)`. The `× 100` converts the
compounded multiplier back to a percentage — uplifts 5% then 3% give `applied% =
8.15` (not `0.0815`), i.e. `NetUnitPrice = base × 1.0815`.

**Unsupported for compound** (264 Help, *Considerations for Ramp Deals*): a SKU
using **CPI renewal uplift**, **usage-based pricing**, or **derived pricing** can't
compound. Compound also **resets on renewal** (new term's Year 1 is the new
baseline); pre-Winter '27 records use standard uplift.

### Inspect / research (read-only)

```bash
# 0. Discover the org's ACTIVE pricing procedure first — RLM_DefaultPricingProcedure
#    is the template default, but an org may run a different one. Never assume the name.
#    --versions is REQUIRED to mark the active version ([ACTIVE]); without it the tool
#    prints set names only (list_expression_sets.py) and can't tell active from draft.
python scripts/expression_sets/list_expression_sets.py --target-org <sf_alias> \
    --type PricingProcedure --versions
# Is compound enabled, and what feeds the rate? Inspect the SELECTED procedure for a
# ramp-path PriceRevision BKM (the ramp branch is "Applyupliftstoramped…") and read
# IsCompoundUpliftEnabled + its Rate input. NOTE the tracked RLM_DefaultPricingProcedure
# NOW ships one there (IsCompoundUpliftEnabled=true), so compound works out of the box; an
# ABSENT ramp-path PriceRevision is the signal that compound uplift is not configured on
# that procedure (e.g. a custom procedure that predates the migration). Use the
# DeveloperName discovered above.
python scripts/expression_sets/describe_expression_set.py --target-org <sf_alias> \
    --developer-name <PRICING_PROCEDURE> --params

# Do live compound ramps exist? (any Compound row = yes)
sf data query --target-org <sf_alias> -q \
  "SELECT RampUpliftType, COUNT(Id) FROM QuoteLineGroup GROUP BY RampUpliftType"

# Segment breakdown for one quote (verify the compounding numerically):
sf data query --target-org <sf_alias> -q "SELECT SegmentName, IsPrimarySegment, \
  StartDate, EndDate, UnitPrice, NetUnitPrice, UnitPriceUplift, \
  ApplUnitPriceUpliftPct, RampUpliftType FROM QuoteLineItem \
  WHERE QuoteId='<id>' AND RampUpliftType='Compound' ORDER BY StartDate NULLS FIRST"
```

Diff the ramp path org-vs-org with `diff_expression_set.py` (compare
`IsCompoundUpliftEnabled` and the `Rate`/`Subtotal` bindings on the ramp
`PriceRevision`). Building the compound-capable ramp quote end-to-end (a **group**
ramp via `placeSalesTransaction` create → `groupRampAction: EditGroup` → clone, then
per-segment `UnitPriceUplift` + `RampUpliftType='Compound'` on the group) is a
transaction-building task, outside this skill — see
`.cursor/skills/ramped-quotes/SKILL.md`. (Do **not** use the line-level
`createRampDeal` or the legacy `/commerce/…/ramp-deals` API — neither produces the
group that holds the compound uplift mode.) Ground behavior in the tracked 264 Help
snapshots: `docs/salesforce/264/help/articles/ind.qocal_ramp_deal_compound_uplift.htm.md`,
`ind.qocal_ramp_deal_compound_uplift_sales_reps.htm.md`, and
`ind.pricing_use_the_price_revision_element_in_a_pricing_procedure.htm.md`.

---
