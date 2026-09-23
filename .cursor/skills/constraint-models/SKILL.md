---
name: constraint-models
description: >-
  Author, deploy, and diagnose Revenue Cloud Constraint Modeling Language (CML) bundle
  rules. Use when editing constraint .ffxblob artifacts, wiring bundle members,
  importing models, or investigating why configurator behavior did not change after
  deployment.
---

# Constraint Models (CML)

Working with Revenue Cloud Constraint Modeling Language models — the rules that decide
what a configurator will let a user select inside a bundle.

Covers the file layout, the four records a bundle member needs, how a change reaches an
org, and why a change can appear to deploy and still not take effect.

**Related:** `datasets/constraints/README.md` (the `export_cml` / `import_cml` /
`validate_cml` utility reference) · `.cursor/skills/expression-sets/SKILL.md` (Expression
Sets generally — constraint models are Expression Sets with `UsageType=Constraint`).

---

## Quick Rules

1. **The `.ffxblob` is plain text and it IS the artifact.** `import_cml` uploads it
   verbatim. Edit the blob.
2. **`scripts/cml/*.cml` is reference only.** Editing it changes nothing in any org. Where
   a model ships one, keep it byte-identical to the blob (`cp` from the blob) — not every
   model does.
3. **Importing into an ACTIVE version does not redeploy the model.** The version must be
   cycled — deactivate then reactivate — after the upload. `prepare_constraints` does this
   for the models it names. **A standalone `import_cml` does not**, so cycle it yourself.
   See [Making a change reach an org](#making-a-change-reach-an-org).
4. **Only the configurator proves deployment.** Reading `ConstraintModel` back proves the
   blob was *stored* — it is the same field `import_cml` writes. It cannot tell you the
   runtime rebuilt.
5. **A bundle member needs FOUR records, not one.** PRC row, `type` + `relation` in the
   model, an ESC `Type` association, and an ESC `Port` association.
6. **`Sequence` is part of the PRC composite key.** A Port association whose sequence
   disagrees with the PRC row **in the target org** fails to resolve — the SFDMU plan
   matters only because it is what loads that row. `import_cml` warns per row and raises —
   but **it half-applies first**: rows that did resolve are already created and the old
   ESC rows are not deleted. The blob is not uploaded, and a clean rerun clears the mix,
   so fix the cause and run it again.
7. **Exactly one model per family may be active** — for QuantumBit that means
   `QuantumBitBundle` *or* `Complete` *or* `PCM`, currently Bundle. Unrelated models
   (`Server2`, and the mfg models when they land) are active alongside it, so **discover
   what is active before deactivating anything** rather than reading a name out of a
   document. See [Discovering what you are working with](#discovering-what-you-are-working-with).

---

## DO NOT

- **DO NOT** edit `scripts/cml/*.cml` and expect an org to change. It is documentation.
- **DO NOT** treat `.ffxblob` as binary. It is ASCII CML source (`file` reports it as
  "c program text").
- **DO NOT** report a model change as verified because `import_cml` succeeded, **or**
  because `ConstraintModel` reads back with your change in it. `import_cml` writes that
  exact field, so reading it back only proves the upload was stored. Deployment is proved
  by selecting the product in the configurator.
- **DO NOT** add a **bundle member** without both its ESC `Type` **and** `Port`
  associations. A product with a PRC row but no `Type` association appears in the bundle
  and then fails Product Validation — the failure looks like a product problem, not a
  model problem. (`Port` is per bundle **relation**, not per type — a cart-level or
  virtual-quote type has no port. See below.)
- **DO NOT** invent a `Sequence` for a new PRC row. Copy the one the SFDMU plan already
  uses for that product — and if the Port still fails to resolve, check the **org**, which
  is what `import_cml` matches against.
- **DO NOT** activate a second QuantumBit model without deactivating the current one.
  `manage_expression_sets` toggles only the versions you name; it does not auto-deactivate
  others.

---

## Entry Conditions

Use this skill when you are:

- adding or removing a product from a configurable bundle's constraint model;
- editing CML types, relations, attributes or rules;
- debugging "product fails Product Validation when selected" in the configurator;
- debugging a model change that deployed but did not take effect;
- adding a whole new constraint model (see `datasets/constraints/README.md` →
  *Adding New Models*).

---

## <a name="discovering-what-you-are-working-with"></a>Discovering what you are working with

**Do not hardcode a model name from this or any other document.** The set of constraint
models differs per org and per feature flag, and grows as verticals are added. Three
sources, in the order you should consult them:

**1. What the org actually has** — authoritative for anything you are about to change:

```bash
# every constraint model and its active state
sf data query --target-org <sf_alias_or_username> -q "
  SELECT ExpressionSet.ApiName, ApiName, VersionNumber, IsActive
  FROM ExpressionSetVersion
  WHERE ExpressionSet.UsageType = 'Constraint'
  ORDER BY ExpressionSet.ApiName"
```

`ExpressionSet.UsageType = 'Constraint'` is the discriminator — that, not the name, is what
makes something a constraint model.

> **Two registries, two placeholders.** CCI and the `sf` CLI keep *separate* alias lists —
> a CCI alias `beta` is `rlm-base__beta` to `sf`. Recipes below use `<cci_alias>` with
> `cci … --org` and `<sf_alias_or_username>` with `sf … --target-org`; they are not
> interchangeable. See `AGENTS.md` → *Org Identity: CCI vs SF CLI*.

**2. What the repo ships** — authoritative for a fresh build, and the inventory a build
will import:

```bash
ls -d datasets/constraints/*/*/          # one directory per model, grouped by vertical
find datasets/constraints -name '*.ffxblob'
```

The **blob** set is the real inventory. A model can ship a blob with no matching
`scripts/cml/<Model>.cml` reference copy.

**3. What the flow imports and activates** — authoritative for what a build will end up
with, and the list to edit when adding a model:

```bash
cci flow info prepare_constraints    # import_cml steps, then the deactivate/activate lists
```

Adding a model means adding it to the data dir, the import steps, **and** the
activate/deactivate lists — see `datasets/constraints/README.md` → *Adding New Models*.

---

## The file layout

```
datasets/constraints/<vertical>/<Model>/     # e.g. qb/QuantumBitBundle, mfg/fuelCell
├── ExpressionSet.csv                        # the Expression Set (UsageType=Constraint)
├── ExpressionSetConstraintObj.csv           # ESC: Type + Port associations  <- the wiring
├── ExpressionSetDefinitionContextDefinition.csv
├── ExpressionSetDefinitionVersion.csv
├── Product2.csv                             # legacy Id -> Name map for remapping
├── ProductClassification.csv
├── ProductRelatedComponent.csv              # legacy Id -> composite key map
└── blobs/
    └── ESDV_<Model>_V1.ffxblob              # THE MODEL. Plain text CML.

scripts/cml/<Model>.cml                      # reference copy, byte-identical to the blob
                                             # (optional — QuantumBitPCM ships without one)
```

Ids in these CSVs are from the **authoring** org and are placeholders. `import_cml` remaps
them: `Product2` by **Name**, `ProductRelatedComponent` by **composite key**. So the
placeholder Id only has to be internally consistent, and mnemonic ones are conventional
(`01tWt000009CMTE` → Each, `...CMTF` → Flat, `...CMTB` → Bounded).

⚠️ `QuantumBitPCM` has a blob and **no** reference `.cml`, so the blob set — not the
`.cml` set — is the authoritative inventory of shipped models.

### What this repo ships today

Concrete instances, correct as of Release 262 — **verify with the queries above rather
than trusting this table**, which is a snapshot and will age:

| Model | Data dir | Reference `.cml` | Activated by `prepare_constraints`? |
|---|---|---|---|
| `QuantumBitBundle` | `datasets/constraints/qb/QuantumBitBundle` | yes | **yes** — the active QB model |
| `QuantumBitComplete` | `datasets/constraints/qb/QuantumBitComplete` | yes | no — imported inactive, kept for A/B |
| `QuantumBitPCM` | `datasets/constraints/qb/QuantumBitPCM` | **no** | no — imported inactive, kept for A/B |
| `Server2` | `datasets/constraints/qb/Server2` | yes | **yes** — a separate model, not part of the QuantumBit family |

Two models are active at once, and that is correct: **`Server2` is not a QuantumBit
model.** The one-active-model rule is scoped to a family — exactly one of
`QuantumBitBundle` / `QuantumBitComplete` / `QuantumBitPCM` may be active — and says
nothing about unrelated models alongside it. Read "active" per family, not per org, before
deactivating anything.

(`Server2` lives under `datasets/constraints/qb/` for historical reasons; the directory it
sits in does not make it a QuantumBit model.)

Manufacturing adds `datasets/constraints/mfg/…` when that series lands, which is exactly
why the discovery queries matter more than this table.

---

## The four records a bundle member needs

Adding a product to a configurable bundle is not one change — missing any of the four records fails differently, and only the first is obvious. Full table, the Ports-per-relation rule, and the `Sequence`/composite-key resolution mechanics (including the two failure modes and how a clean rerun recovers):
[`bundle-member-records.md`](bundle-member-records.md).

## Making a change reach an org

**`import_cml` uploads the blob; it does not redeploy the model.** If the target version is already `Active`, the import reports success while the org keeps running the old model — it must be deactivated then reactivated. The manual cycling recipe, why `prepare_constraints` orders its deactivate/activate steps the way it does, and the UI equivalent:
[`deploying-model-changes.md`](deploying-model-changes.md).

## Examples

### Add a product to a configurable bundle

Worked example — adding `QB-CMT-TKN-BND` to `QB-COMPLETE` in the `QuantumBitBundle` and
`QuantumBitComplete` models. Substitute your own model and product; the shape is the same
for any vertical.

```bash
# 1. Confirm the PRC row exists and note its Sequence (here: 25)
grep QB-CMT-TKN-BND datasets/sfdmu/qb/en-US/qb-pcm/ProductRelatedComponent.csv

# 2. Edit the BLOB (not the .cml): add a relation and a type next to the siblings
#      relation quantumbitdatabasetokencommitbounded : QuantumBitDatabaseTokenCommitBounded;
#      type     QuantumBitDatabaseTokenCommitBounded : LineItem;

# 3. Re-sync the reference copy
cp datasets/constraints/qb/QuantumBitBundle/blobs/ESDV_QuantumBitBundle_V1.ffxblob \
   scripts/cml/QuantumBitBundle.cml

# 4. Add Product2 + both ESC rows (Type and Port), reusing Sequence 25 on the PRC row
# 5. Dry run, then deactivate -> import -> activate (above)
```

### Read the deployed model back out of an org

```bash
URL=$(sf data query --use-tooling-api --target-org <sf_alias_or_username> \
  -q "SELECT ConstraintModel FROM ExpressionSetDefinitionVersion WHERE DeveloperName='QuantumBitBundle_V1'" \
  --json | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['records'][0]['ConstraintModel'])")
INST=$(sf org display --target-org <sf_alias_or_username> --json | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['instanceUrl'])")
TOK=$(sf org display --target-org <sf_alias_or_username> --json | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['accessToken'])")
curl -s -H "Authorization: Bearer $TOK" "$INST$URL" | grep "TokenCommitBounded"
```

---

## Validation Checks

Before calling a constraint-model change done:

1. `cci task run validate_cml -o cml_dir scripts/cml -o data_dir <dir>` → **0 errors**
   (warnings are noisy and largely pre-existing; the error count is the signal).
2. Blob and reference `.cml` byte-identical — **only for a model that ships one**
   (`QuantumBitPCM` does not): `diff -q <blob> scripts/cml/<Model>.cml`. A model with no
   reference copy skips this check; the blob is the artifact, so its absence is not a
   failure.
3. Dry-run import resolves your new rows to **real org Ids**, and you queried those Ids
   back to confirm they are the records you meant — not just that something resolved.
4. Deactivate → import → activate actually run, in that order.
5. `ConstraintModel` reads back with your change in it (recipe above). Note what this
   does **not** prove: `import_cml` writes that same field, so it confirms the upload was
   stored and nothing more. It cannot distinguish "stored" from "deployed".
6. Diff the **expected** set against the org rather than listing what is there — and
   **scope the query to the model you changed**. Models deliberately share most tags
   (Bundle is a graft of Complete plus PCM), so an unscoped query lets a tag missing from
   one model be masked by another model's row:
   ```bash
   sf data query --target-org <sf_alias_or_username> -q "
     SELECT ConstraintModelTag, ConstraintModelTagType
     FROM ExpressionSetConstraintObj
     WHERE ExpressionSet.ApiName = '<Model>'"
   ```
   then assert every product you expect has **both** a `Type` and a `Port` row.
7. **Exercise the configuration rules.** This is what proves the runtime model was
   rebuilt — nothing above distinguishes a deployed model from a stored one. It does
   **not** require the UI: activation only flips `IsActive`, and the model is compiled
   when config rules run, so POSTing the Product Configurator `configure` action with
   `executeConfigurationRules: true` against a quote line that uses the model exercises
   the same path headlessly. A valid model returns `success: true`,
   `solverStatus: "success"`, `errors: []`; an invalid one returns `Model '…' is invalid`.
   Full recipe: `datasets/constraints/README.md` → *Validating the combined model
   (headless)*.

---

## Known gaps

- **`manage_expression_sets` rejects `--org`** and runs against the default org. One
  instance of a repo-wide problem (102 of 193 custom tasks). `import_cml`, `export_cml`
  and `validate_cml`'s siblings do accept it.
- **`validate_cml`'s warning stream is not clean enough to gate on** — it emitted ~1,779
  warnings against the QuantumBit models at the time of writing, nearly all pre-existing
  "missing type association for leaf type". Treat the **error** count as the signal and
  check the warning count against a known-good baseline for the models you are touching.
- **A standalone `import_cml` never cycles the version.** `prepare_constraints` covers
  this at steps 11-12, but shipping a model change usually means running `import_cml` on
  its own — where the upload lands and nothing redeploys. There is no single task that
  does import-and-cycle.
- **No *passive* signal distinguishes "stored" from "deployed".** `ConstraintModel` is the
  upload field, so no query tells you the runtime rebuilt — you have to make the engine
  run. The configurator `configure` POST does that headlessly (see Validation check 7), so
  this is a gap in observability, not in automation: there is no status field to watch,
  but there is no need for a browser either.
- **`import_cml` still half-applies on failure** — but it no longer hides it.
  `create_record()` runs inline per row, so a failure leaves the rows that already resolved
  in place while the delete-old-rows step is skipped — "a mix of old and new constraints",
  in the task's own words. Both failure modes now raise (outside `dry_run`), and neither
  uploads the blob, so a partial ESC set can no longer ship under a model that references
  rows which never landed.
  A **clean** rerun clears the mix (the snapshot is retaken each run, so the delete on a
  clean pass removes the partial rows too); a rerun that fails again layers another partial
  generation. What remains unfixed is the half-apply itself: the writes are not staged, so a
  failure still leaves the org changed. Staging them (collect payloads, insert at the end,
  or roll back what was created) is the real fix. See
  [`bundle-member-records.md`](bundle-member-records.md) → *Sequence is part of
  the composite key* for the full table.
- **The builder's `Sync` button is uninvestigated.**
