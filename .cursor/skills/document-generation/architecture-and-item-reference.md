# Architecture, Item Types & DocumentTemplate Reference

Read this for the end-to-end data-flow diagram, the field-level reference
for Extract/Transform ODT item types, and the DocumentTemplate record shape.
For the deep extract-engine internals (formula catalog, filter mechanics,
hierarchy semantics), see [`extract-engine-reference.md`](extract-engine-reference.md).
Parent skill: [SKILL.md](SKILL.md).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DocumentTemplate                          │
│  Name: "RLM_InvoiceTemplate_v2"                             │
│  Type: MicrosoftWord                                        │
│  ExtractOmniDataTransformName: "RLMInvoiceGetDetails"       │
│  MapperOmniDataTransformName: "RLMInvoiceTransformDetails"  │
│  TokenMappingMethodType: "OmniDataTransform"                │
│  UsageType: "Invoice"                                       │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │   Extract ODT       │    │   Transform ODT     │
    │   Type: "Extract"   │    │   Type: "Transform" │
    │   InputType: "JSON" │    │   InputType: "JSON" │
    │   OutputType: "JSON"│    │   OutputType: "JSON" │
    └──────────┬──────────┘    └──────────┬──────────┘
               │                          │
    ┌──────────▼──────────┐    ┌──────────▼──────────┐
    │  OmniDataTransform  │    │  OmniDataTransform  │
    │  Items (2 types):   │    │  Items (3 types):   │
    │  • Object Queries   │    │  • Pass-through     │
    │  • Field Mappings   │    │  • Formula          │
    └─────────────────────┘    │  • Image objects    │
                               └─────────────────────┘
```

**Data flow (live-verified via REST API):**

```
1. TRIGGER: DocumentGenerationProcess record inserted
   Input: {"Id": "<recordId>"}
   (DGP reads DocumentTemplate → resolves Extract + Transform names)

2. EXTRACT: POST /omnistudio/dataraptor/<ExtractName>
   - Receives: {"Id": "<recordId>"}
   - Executes object queries (SOQL) per sequence number
   - Applies filters (FilterValue + FilterOperator + FilterGroup)
   - Maps InputFieldName → OutputFieldName on field mapping items
   - Returns: raw data JSON (nested arrays/objects reflecting hierarchy)

3. TRANSFORM: POST /omnistudio/dataraptor/<TransformName>
   - Receives: Extract output JSON (entire response, as-is)
   - Applies: pass-through renames, formula computations (LIST, IF, CONCAT),
     object builders (IMG_, HYP_), Boolean casts (IF_ conditions)
   - Returns: template-ready JSON (keys = exact token names in .docx)

4. RENDER: Engine merges Transform output with .docx template
   - Scalar tokens: {{TokenName}} → replaced with string value
   - Repeating sections: {{#Array}}...{{/Array}} → one row per array element
   - Conditional sections: {{#IF_x}}...{{/IF_x}} → rendered/hidden by Boolean
   - Dynamic content: IMG_, HYP_, RTB_ → rendered per their contract
   - Output: .docx (intermediate)

5. CONVERT (optional): .docx → .pdf via Microsoft 365 service
   - Only when DGP.Type = "GenerateAndConvert"
   - Output: two ContentVersions (068 IDs) — .docx + .pdf

6. COMPLETE: DGP.Status → "Success", ResponseText = comma-separated 068 IDs
```

**Testable at each stage:**
- Stage 2: `python scripts/docgen/docgen_odt_execute.py RLMQuoteProposalExtract --record-id 0Q0XXXXXXXXXXXXAAA --org dev-scratch`
- Stage 3: `sf api request rest --method POST --body @extract_output.json /services/data/v68.0/omnistudio/dataraptor/RLMQuoteProposalTransform --target-org dev-scratch`
- Full pipeline: `python scripts/docgen/docgen_template_generate.py --record-id 0Q0XXXXXXXXXXXXAAA --template-id 2dtXXXXXXXXXXXXAAA --org dev-scratch`

---

## Extract ODT — Item Types

### Object Query Items

Define which SObjects to query and how to join them:

| Field | Purpose | Example |
|-------|---------|---------|
| `InputObjectName` | SObject to query | `Invoice` |
| `InputFieldName` | Field on this object to match against FilterValue (see below) | `Id`, `InvoiceId` |
| `OutputFieldName` | Internal hierarchy path (join scope) | `Invoice`, `Invoice:Account` |
| `OutputObjectName` | Always `json` | `json` |
| `InputObjectQuerySequence` | Execution order (1, 2, 3...) | `1` |
| `FilterOperator` | Match operator | `=` |
| `FilterValue` | Value or path to match | `Id` (for root), `Invoice:BillingAccountId` (for FK lookup) |
| `FilterGroup` | Required grouping | `0` |

**InputFieldName semantics (critical — generates the WHERE clause):**
```
WHERE <InputFieldName> = <resolved FilterValue>
```

Two join patterns:

| Pattern | InputFieldName | FilterValue | Meaning |
|---------|---------------|-------------|---------|
| **Root** (input param) | `Id` | `Id` | Match input `Id` param → this object's `Id` |
| **FK lookup** (many:1) | `Id` | `Parent:FKField` | Match parent's FK → target's `Id` (1 result per parent) |
| **Child-of** (1:many) | Child's FK field | `Parent:Id` | Match parent's Id → child's FK (0..N per parent) |

**Examples:**
```
Seq 1: Invoice,     InputFieldName="Id",        FilterValue="Id"                        ← root
Seq 4: Account,     InputFieldName="Id",        FilterValue="Invoice:BillingAccountId"  ← FK lookup (safe)
Seq 5: InvoiceLine, InputFieldName="InvoiceId", FilterValue="Invoice:Id"                ← child-of (1:many)
```

**Multi-filter objects** (e.g., InvoiceLine with type filter):
```
Seq 3: InvoiceLine, InputFieldName=InvoiceId, FilterValue="Invoice:Id"
Seq 3: InvoiceLine, InputFieldName=Type,      FilterValue="\"Charge\""
```
Note: literal string filters use embedded quotes: `"\"Charge\""`.

### Field Mapping Items

Extract specific fields from queried objects:

| Field | Purpose | Example |
|-------|---------|---------|
| `InputFieldName` | Source path (colon-separated) | `Invoice:Account:BillingCity` |
| `OutputFieldName` | Key in Extract output | `BillingCity` |
| `OutputObjectName` | Always `json` | `json` |
| `OutputCreationSequence` | Usually `1` | `1` |

---

## Transform ODT — Item Types

### Pass-through Mappings

Simple field rename from Extract output to template token:

| Field | Purpose | Example |
|-------|---------|---------|
| `InputFieldName` | Key from Extract output | `BillingCity` |
| `OutputFieldName` | Template token name | `BillingCity` |
| `OutputObjectName` | Always `json` | `json` |
| `OutputCreationSequence` | `1` for simple mappings | `1` |

### Formula Items (Repeating Sections)

Build arrays for `{{#Section}}` tokens:

| Field | Purpose | Example |
|-------|---------|---------|
| `OutputFieldName` | `Formula` | `Formula` |
| `OutputObjectName` | `Formula` | `Formula` |
| `FormulaExpression` | Function call | `FUNCTION('invoice_docgen.InvoiceDocumentGeneration', 'InvoiceLineCustom', ...)` |
| `FormulaConverted` | RPN form (auto-generated on save — UI and API) | `\| ... FUNCTION` |
| `FormulaResultPath` | Output key name | `InvoiceLines` |
| `FormulaSequence` | Execution order | `1` |
| `OutputCreationSequence` | `0` (runs before mappings) | `0` |

### Object Output Items (Array Pass-through)

After a formula builds an array, map it to the template:

| Field | Purpose | Example |
|-------|---------|---------|
| `InputFieldName` | Formula result key | `InvoiceLines` |
| `OutputFieldName` | Template section name | `InvoiceLines` |
| `OutputObjectName` | `json` | `json` |
| `OutputFieldFormat` | `Object` (for arrays/objects) | `Object` |
| `OutputCreationSequence` | `1` | `1` |

---

## DocumentTemplate Record

| Field | Value | Notes |
|-------|-------|-------|
| `Name` | Template name | No underscores in API Name |
| `Type` | `MicrosoftWord` | For `.docx` templates |
| `TokenMappingType` | `JSON` | Always JSON for ODT approach |
| `TokenMappingMethodType` | `OmniDataTransform` | Links to ODT framework |
| `ExtractOmniDataTransformName` | Extract ODT name | Must match exactly |
| `MapperOmniDataTransformName` | Transform ODT name | Must match exactly |
| `UsageType` | `Invoice`, `Quote`, etc. | Object context |
| `Status` | `Active` / `Draft` | Must be Draft to edit |
| `IsActive` | `true` / `false` | Must be false to edit |
