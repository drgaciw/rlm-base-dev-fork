---
name: document-generation
description: >-
  Create, modify, and troubleshoot Salesforce OmniStudio .docx templates and
  DocumentTemplate lifecycle operations. Use for token mapping, template activation,
  document generation, or output verification; use odt-authoring for deep
  OmniDataTransform mapper work.
---

# OmniStudio Document Generation

Use this skill when creating, modifying, or troubleshooting Salesforce OmniStudio
document templates (`.docx`) and DocumentTemplate lifecycle operations.
For ODT mapper architecture and deep ODT troubleshooting, use
`../odt-authoring/SKILL.md`.

## Quick Rules

1. **Template needs two ODT names** — DocumentTemplate must reference one Extract
   and one Transform ODT by name.
2. **Token syntax** — use `{{FieldName}}` for scalars, `{{#Section}}...{{/Section}}`
   for repeating rows, and `{{IMG_name}}` for images.
3. **Use canonical template scripts** — `docgen_template_*` is the only public
   command surface for template build, token extraction, lifecycle, and generation.
4. **Deactivate before mutable edits** — set template to Draft before binary or
   metadata updates; reactivate only after changes are complete.
5. **Generate to verify behavior** — use `docgen_template_generate.py` for
   end-to-end smoke tests after template or mapper updates.
6. **Keep Context Service input separate from runtime Context API input.** For a
   Context Service DocumentGenerationProcess, set `DocGenAdditionalInputType`
   to `ContextService` and pass the root entity ID as the plain
   `DocGenAdditionalInput` value. The runtime `{"inputData": ...}` shape does
   not belong in that DGP field.
7. **Keep template and mapper changes in sync** — if token structure changes,
   confirm Extract/Transform output alignment before reactivation.
8. **Route ODT deep work to ODT skill** — hierarchy design, mapper structure,
   filter semantics, and array-depth debugging live in `../odt-authoring/SKILL.md`.
9. **Dynamic image contract is strict** — `IMG_*:src` must resolve to
   ContentDocument (`069`) plus width/height; see `dynamic-images.md`.


## DO NOT

- **DO NOT** use dot notation in Extract `InputFieldName` — use colons
  (`Invoice:PaymentTerm:Name`, not `Invoice.PaymentTerm.Name`).
- **DO NOT** leave `OutputObjectName` null on any OmniDataTransformItem — this
  causes a runtime NPE that silently produces empty output.
- **DO NOT** create duplicate object query items — duplicates can cause the entire
  Extract to fail silently, producing no data.
- **DO NOT** pass a ContentVersion Id (`068`) or file Title to `IMG_token:src` —
  only ContentDocument Id (`069`) works; others crash the engine.
- **DO NOT** omit `width` or `height` from `IMG_` token objects — the image
  silently fails to render if either dimension is missing.
- **DO NOT** edit `TargetOutputFileName` or `MapperOmniDataTransformName` while the
  DocumentTemplate or ODT is Active — deactivate first.
- **DO NOT** use the SObject REST API to create/edit/delete ODTs in shared,
  production, or customer orgs — the official docs say these records are "for
  internal use only." Use Metadata API XML instead.

---

## Entry Conditions

| Task | Use this skill? |
|------|-----------------|
| Create a new `.docx` invoice/quote/contract template | Yes |
| Wire up Extract + Transform ODTs for a template | Use `../odt-authoring/SKILL.md` |
| Add fields/tokens to an existing template | Yes |
| Troubleshoot blank output or generation errors | Yes |
| Add dynamic images to a template | Yes — see `dynamic-images.md` |
| Create ODT items programmatically via API | Use `../odt-authoring/SKILL.md` |

---

## ODT Context for Template Authors

| Path | Use When | Supportability |
|------|----------|----------------|
| **Metadata API** (`.rpt-meta.xml`) | Committed assets, CI/CD, `prepare_docgen` | Fully supported — official metadata type since API v54.0 |
| **OmniStudio Designer UI** | Prototyping, visual editing | Fully supported |
| **SObject REST API** (`docgen_odt_*`) | Scratch-org repair, rapid iteration, debugging | **Internal use only** — not supported for production |

### Metadata API (Primary)

ODTs are source-controlled as XML in `unpackaged/post_docgen/omniDataTransforms/`:
```
unpackaged/post_docgen/omniDataTransforms/
  RLMQuoteExtractBasic_1.rpt-meta.xml
  RLMQuoteTransformBasic_1.rpt-meta.xml
  BillingDocumentGenerationGetInvoiceDetails_1.rpt-meta.xml
  ...
```

Deploy via `cci flow run prepare_docgen --org dev-scratch`. See
`docs/guides/docgen-setup.md` for the full 10-step deployment sequence
(formula field pre-deploy, ODT seed workaround, binary fix).

### SObject REST API (ODT Experimentation Only)

> **Salesforce official warning** (from [SObject API reference](https://developer.salesforce.com/docs/atlas.en-us.industries_reference.meta/industries_reference/sforce_api_objects_omnidatatransform.htm)):
> *"This object and associated records are only for internal use. Don't perform
> any create, edit, or delete operations on this object. Modifying or deleting
> this object's records may result in errors with your implementation."*

The ODT helper scripts (`docgen_odt_*`) use this API for rapid scratch-org
iteration. They are appropriate for:
- Debugging blank output (inspecting/fixing items quickly)
- Cloning an ODT to experiment with variations
- Validating item structure before committing as Metadata API XML
- **Executing Extracts/Transforms** for automated testing (`docgen_odt_execute.py`)
- **Full document generation** end-to-end (`docgen_template_generate.py`)

They are **NOT** appropriate for production deployment.

### Template Lifecycle Management

The `docgen_template_manage.py` script manages the full DocumentTemplate
lifecycle: list, inspect, activate/deactivate, upload/replace binary,
create new templates, and download source or generated files.

```bash
# List all templates in an org
python scripts/docgen/docgen_template_manage.py list --org dev-scratch

# Show detail for a specific template
python scripts/docgen/docgen_template_manage.py status RLM_QuoteProposal --org dev-scratch

# Full replace lifecycle (deactivate → upload → reactivate)
python scripts/docgen/docgen_template_manage.py replace RLM_QuoteProposal template.docx --org dev-scratch

# Download template source .docx
python scripts/docgen/docgen_template_manage.py download --template RLM_QuoteProposal --org dev-scratch -o out.docx

# Download generated output by ContentVersion ID (from DGP ResponseText)
python scripts/docgen/docgen_template_manage.py download --version-id 068XXXXXXXXXXXXAAA --org dev-scratch -o out.pdf

# Create new template with ODT wiring
python scripts/docgen/docgen_template_manage.py create RLM_NewProposal template.docx --org dev-scratch \
  --extract-odt RLMQuoteProposalExtract --transform-odt RLMQuoteProposalTransform \
  --usage-type Revenue_Lifecycle_Management --activate
```

Use `--template-id <2dt...>` or `--content-doc-id <069...>` on mutating
commands when disambiguation is needed.

**Key behaviors:**
- DGP `ResponseText` returns 15-char ContentVersion IDs (e.g., `068xxxxxxxxxxxx`);
  the download command accepts both 15- and 18-char IDs.
- Generated `.docx` output is inspectable with `python-docx` (tables, paragraphs,
  token fill values). PDF output is compressed and requires `poppler` for text
  extraction — prefer downloading the `.docx` intermediate for verification.
- To get both `.docx` and `.pdf` from a single DGP run, set
  `"keepIntermediate": true` in `RequestText`.
- `RequestText` must include `templateContentVersionId` (the 068 ID of the
  template binary). Without it, DGP returns `INVALID_INPUT`.

### Context Service DGP Contract

When `DocumentTemplate.TokenMappingMethodType` is `ContextService`, the
Document Generation engine resolves the definition and mapping from the template.
Set the DGP fields as follows:

| Field | Required value |
|-------|----------------|
| `ReferenceObject` | Root source-record ID |
| `DocGenAdditionalInputType` | `ContextService` |
| `DocGenAdditionalInput` | The same root source-record ID as a plain string |

Do not put the Context Service runtime API's `{"inputData": ...}` request body in
`DocGenAdditionalInput`. For a hierarchical context, map each auto-created child
`ParentReference` to the child SObject's lookup to its parent (for example,
`QuoteLineItem.QuoteId`) so repeating template sections hydrate correctly.

### OmniStudio REST API (Execution & Testing)

The OmniStudio REST endpoint executes ODTs with standard OAuth (no
Lightning session needed). Works for both Extracts and Transforms:

```bash
# Execute an Extract against a record
python scripts/docgen/docgen_odt_execute.py RLMQuoteProposalExtract --record-id 0Q0XXXXXXXXXXXXAAA --org dev-scratch

# Execute a Transform (pass Extract output as input)
python scripts/docgen/docgen_odt_execute.py RLMQuoteProposalTransform --input extract_output.json --org dev-scratch

# Pipeline: Extract → Transform (--json pipes output)
python scripts/docgen/docgen_odt_execute.py RLMQuoteProposalExtract --record-id 0Q0XXXXXXXXXXXXAAA --org dev-scratch --json > /tmp/e.json
python scripts/docgen/docgen_odt_execute.py RLMQuoteProposalTransform --input /tmp/e.json --org dev-scratch

# Full end-to-end document generation (DGP: Extract → Transform → .docx → PDF)
python scripts/docgen/docgen_template_generate.py \
  --record-id 0Q0XXXXXXXXXXXXAAA --template-id 2dtXXXXXXXXXXXXAAA --org dev-scratch
```

Use this for:
- Automated validation of Extract output (entry counts, field presence)
- Phantom-entry detection (compare expected vs actual entry count)
- Transform output verification before wiring to a template
- End-to-end template smoke tests (DGP script triggers generation + polls)

### Static inspection — validate and diff without executing

Two helpers read an ODT's items straight from the org, so they work before you
have a record to execute against:

```bash
# Lint one ODT's items: null fields, duplicate keys, malformed dot notation
python scripts/docgen/docgen_odt_validate.py RLMQuoteProposalExtract --org dev-scratch

# Diff two ODTs item-by-item — the fastest way to find what a clone lost
python scripts/docgen/docgen_odt_compare.py RLMQuoteProposalExtract RLMInvoiceExtract --org dev-scratch

# Create an ODT from a JSON spec (--example extract|transform emits a starter spec)
python scripts/docgen/docgen_odt_create.py spec.json --org dev-scratch
```

`docgen_odt_create.py`'s spec format, cloning patterns, and shell-escaping
pitfalls are in `data-mapper-authoring.md`; `odt-authoring/SKILL.md` covers
authoring the mapper itself.

Reach for `docgen_odt_validate.py` when an Extract returns empty or partial
output and you want to rule out the mapper before blaming the data, and for
`docgen_odt_compare.py` when a cloned ODT misbehaves — cloning is the pattern
this skill recommends (see `data-mapper-authoring.md`), and a silent item drop
during a clone is its characteristic failure.

---

## Architecture Overview

Full data-flow diagram (DocumentTemplate → Extract → Transform → Render → Convert) and stage-by-stage test commands:
[`architecture-and-item-reference.md`](architecture-and-item-reference.md#architecture-overview).

---

## Token Reference

| Token Type | Syntax | Example | Transform Output |
|-----------|--------|---------|-----------------|
| Scalar | `{{Name}}` | `{{InvoiceNumber}}` | `"InvoiceNumber": "INV-001"` |
| Repeating section | `{{#List}}...{{/List}}` | `{{#InvoiceLines}}{{ProductName}}{{/InvoiceLines}}` | `"InvoiceLines": [{...}, ...]` |
| Truthy gate | `{{#Field}}...{{/Field}}` | `{{#GrantType}}row content{{/GrantType}}` | Renders when field is non-empty string/object; skips when absent/null/empty |
| Condition (boolean) | `{{#IF_x}}...{{/IF_x}}` | `{{#IF_has_discount}}...{{/IF_has_discount}}` | `"IF_has_discount": true` (Boolean only) |
| Inverse condition | `{{^IF_x}}...{{/IF_x}}` | `{{^IF_no_discount}}...{{/IF_no_discount}}` | Shows when value is `false`; hidden when `true` |
| Image | `{{IMG_name}}` | `{{IMG_CompanyLogo}}` | `{"src": "069...", "width": "200", "height": "80"}` (see `dynamic-images.md`) |
| Hyperlink | `{{HYP_name}}` | `{{HYP_PaymentLink}}` | `{"url": "https://...", "text": "label"}` |
| Rich text | `{{RTB_name}}` | `{{RTB_TermsContent}}` | HTML string: `"<b>Bold</b> <a href='...'>link</a>"` |

### Dynamic Content Token Notes

**RTB_ (Rich Text)** — **Confirmed working.** Pass an HTML string directly.
Supports `<b>`, `<i>`, `<ul>/<li>`, `<a href>` (renders clickable links),
and inline images. Best option for hyperlinks (renders with formatting).
- **Limitation:** RTB tokens must NOT be placed within a paragraph (causes
  generation failure). Place them as standalone blocks.
- **Limitation:** Bullets in template surrounding RTB tokens are not supported.

**IMG_ (Dynamic Images)** — **Confirmed working** with specific requirements:
- `src`: ContentDocument ID (`069` prefix) — **required**
- `width`: pixel string — **required**
- `height`: pixel string — **required**
- Image must be in a Content Library accessible to the Integration User
- See `dynamic-images.md` for full verified contract

**HYP_ (Hyperlinks)** — **Confirmed working.** Requires:
- Field name must be `"url"` (NOT `"src"`) — using `src` causes the "URL is invalid" error
- Template token must be **plain text** — do NOT format as a Word hyperlink (Cmd+K / Ctrl+K)
- `"text"` is optional — if omitted, the URL itself is displayed as the link text
- Alternative: RTB_ with `<a>` tags also works and offers richer formatting control

**IF_ (Conditions)** — Must receive **Boolean values only** (`true`/`false`).
Strings and numbers always evaluate as `true`, causing unexpected rendering.
Use `IF(expression, true, false)` formula in the Transform.

### Page Break and Token Spacing Guidelines

- **DO NOT** place page breaks directly before `{{#IF_` or `{{#Section}}` start
  tokens — creates blank pages when condition is false or section is empty.
- **DO NOT** place page breaks directly after `{{/IF_` or `{{/Section}}` end
  tokens — same blank page issue.
- **DO** place page breaks **between** sections, not adjacent to token markers.
- **Remove empty lines between adjacent conditional tokens** — the engine
  interprets whitespace between tokens as content, creating blank pages.

### Repeating Sections in Tables

Place `{{#SectionName}}` in the first cell of the data row and
`{{/SectionName}}` in the last cell. The engine duplicates the entire row for
each array element:

```
| Product                         | Qty          | Amount                        |
| {{#InvoiceLines}}{{ProductName}}| {{Quantity}} | {{Subtotal}}{{/InvoiceLines}} |
```

---

## Item Type & DocumentTemplate Reference

Field-level reference for Extract ODT item types (object queries, field mappings), Transform ODT item types (pass-through, formula, object output), and the DocumentTemplate record shape:
[`architecture-and-item-reference.md`](architecture-and-item-reference.md).

---

## Validation Checks

### Before generation

1. Both ODTs are Active (`IsActive: true`)
2. DocumentTemplate references correct ODT names (exact match, case-sensitive)
3. No items with null `OutputObjectName`:
   ```sql
   SELECT Id, OutputFieldName FROM OmniDataTransformItem
   WHERE OmniDataTransformationId = '<id>' AND OutputObjectName = null
   ```
4. No duplicate object query items (same Seq + OutputFieldName + FilterValue)
5. All object queries have `InputFieldName` and `FilterGroup` set
6. Field mapping paths use colons, not dots

### Common Extract Architecture Pitfalls & Troubleshooting

Full pitfall table (cartesian products, mixed-depth leakage, grantless parents, ...) and symptom-to-fix troubleshooting table:
[`extract-engine-reference.md`](extract-engine-reference.md#extract-architecture-pitfalls--general-troubleshooting).

---

## Platform Behavior Reference

> Full detail: **[`extract-engine-reference.md`](extract-engine-reference.md)**
> (formula catalog, filter mechanics, hierarchy semantics, array patterns, Preview API)

Verified on Release 262, API v67.0. Key concepts summarized below;
read the sub-file when designing or debugging complex Extracts.

### Critical Rules (quick reference)

| Rule | Detail |
|------|--------|
| **Internal ≠ Output paths** | Object query `OutputFieldName` (join scope) is decoupled from field mapping `OutputFieldName` (JSON shape). They share colon syntax but are independent namespaces. |
| **Depth uniformity** | ALL field mappings for the same output array must read from the same internal hierarchy depth. Mixed depths → parent entries leak into child array. |
| **Redundant join for parent fields** | To get a parent's field at child level without leaking grantless parents, re-join the parent object at the child level (Seq N filtering by child FK). |
| **Section-as-conditional** | `{{#FieldName}}...{{/FieldName}}` acts as truthy/falsy gate — renders when non-empty string/array/object; skips when absent, null, false, or empty. |
| **FilterGroup = OR** | Multiple FilterGroups are UNION ALL — on nested sequences this causes N×M×G cartesian explosion. Use only on root queries. |
| **Literals must be quoted** | `FilterValue: "'Active'"` not `FilterValue: "Active"`. Unquoted literals generate no WHERE clause. |
| **No subqueries** | Cannot filter "only parents with children." Use child-first hierarchy + redundant join pattern. |
| **Transform formulas are scalar** | `FormulaResultPath` cannot target per-array-element paths. Use section-as-conditional instead. |

### Formula Quick Reference

Supported: `IF`, `ISBLANK`, `CONCAT`, `SUBSTRING`, `LIST`, `FUNCTION`,
arithmetic, comparisons, `AND`/`OR`/`NOT`, `ABS`/`ROUND`/`FLOOR`/`CEILING`/`MAX`/`MIN`.

**Not supported** (saves silently, produces no output): `CASE`, `LEN`,
`UPPER`/`LOWER`, `TEXT`, `FORMAT`, `VALUE`, `MOD`, `POWER`.

### ODT Naming

Alphanumeric only (no underscores/spaces). Use camelCase: `RLMQuoteExtractBasic`.

---

## Examples

### Creating a complete template pipeline

See `data-mapper-authoring.md` for the programmatic API approach to creating
Extract + Transform ODTs with all items.

### Adding a new field to an existing template

1. **Template**: Add `{{NewField}}` token in the `.docx`
2. **Extract**: Add field mapping item — `InputFieldName: "Object:FieldApiName"`,
   `OutputFieldName: "NewField"`, `OutputObjectName: "json"`
3. **Transform**: Add pass-through — `InputFieldName: "NewField"`,
   `OutputFieldName: "NewField"`, `OutputObjectName: "json"`
4. **If field is on a new object**: Add object query item first (with proper
   Seq, InputFieldName, FilterValue, FilterGroup)
5. **Re-toggle** both ODTs (`IsActive` false → true)
6. **Upload** new `.docx` (deactivate template → replace file → reactivate)

---

## Helper Scripts

Scripts in `scripts/docgen/` support document generation workflows.
Install deps first: `pip install -r scripts/docgen/requirements.txt`

```bash
# ODT workflows are covered by ../odt-authoring/SKILL.md (docgen_odt_* commands).

# Extract all mustache tokens from a .docx template
python scripts/docgen/docgen_template_extract_tokens.py template.docx
python scripts/docgen/docgen_template_extract_tokens.py template.docx --validate-transform RLMQuoteProposalTransform --org dev-scratch

# Build/modify .docx templates programmatically (requires python-docx)
# NOTE: replace/audit operate on body + tables only — headers/footers NOT searched.
# Use docgen_template_extract_tokens.py for full-template token inventory (includes headers/footers).
python scripts/docgen/docgen_template_build.py create layout.json --output template.docx
python scripts/docgen/docgen_template_build.py replace template.docx --tokens '{"Old": "New"}'
python scripts/docgen/docgen_template_build.py audit template.docx
python scripts/docgen/docgen_template_build.py --example > layout.json   # generate layout spec

# Full document generation (DGP): Extract → Transform → .docx → PDF
python scripts/docgen/docgen_template_generate.py --record-id 0Q0XXXXXXXXXXXXAAA --template-id 2dtXXXXXXXXXXXXAAA --org dev-scratch
python scripts/docgen/docgen_template_generate.py --record-id 0Q0XXXXXXXXXXXXAAA --template-id 2dtXXXXXXXXXXXXAAA --org dev-scratch --no-convert  # .docx only
python scripts/docgen/docgen_template_generate.py --record-id 0Q0XXXXXXXXXXXXAAA --template-id 2dtXXXXXXXXXXXXAAA --org dev-scratch --title "Custom Name"
python scripts/docgen/docgen_template_generate.py --record-id 0Q0XXXXXXXXXXXXAAA --template-id 2dtXXXXXXXXXXXXAAA --org dev-scratch --dry-run
```

---

## Deployment & Repo Integration

For the full deployment guide, see **`docs/guides/docgen-setup.md`**.

### Key points:

- **Metadata path**: `unpackaged/post_docgen/omniDataTransforms/*.rpt-meta.xml`
- **Deploy flow**: `cci flow run prepare_docgen --org dev-scratch` (10 steps)
- **Fresh-org bug**: ODT INSERT fails when formula fields referenced in
  `inputFieldName` don't exist yet. Steps 3–5 of `prepare_docgen` pre-deploy
  formula fields and seed stub ODT records as a workaround.
- **Binary fix**: `fix_document_template_binaries` uploads correct `.docx` binary
  after metadata deploy (Metadata API drops binary content on deploy).
- **Feature gate**: All steps gated by `project_config.project__custom__docgen`.
- **Context Service alternative**: `RLM_QuoteProposal_CS` uses Context Service
  instead of ODTs — see the setup guide for that path.

### Retrieve an ODT from a scratch org:

```bash
sf project retrieve start --metadata OmniDataTransform:RLMInvoiceGetDetails --target-org dev-scratch
```

Then move the retrieved `.rpt-meta.xml` to `unpackaged/post_docgen/omniDataTransforms/`.

---

## Related Skills

- `../odt-authoring/SKILL.md` — ODT architecture, mapper design, and execution patterns
- `expression-sets/SKILL.md` — Expression Set authoring (pricing procedures use
  similar Connect/Metadata API patterns)
- `repo-integration/SKILL.md` — Where to place template metadata in the repo
- `sfdmu-data-plans/SKILL.md` — Loading template/ODT records via data plans
- `docs/guides/docgen-setup.md` — Full deployment sequence, bug workarounds, Context Service
