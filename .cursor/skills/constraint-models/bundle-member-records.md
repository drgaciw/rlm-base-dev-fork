# The Four Records a Bundle Member Needs

Read this when a product appears in a bundle then fails Product Validation, a Port association won't resolve, or `import_cml` raises mid-run. Parent skill: [SKILL.md](SKILL.md).

## The four records a bundle member needs

Adding a product to a configurable bundle is not one change. Missing any of these fails
differently, and only the first is obvious:

| # | Record | Where | Symptom if missing |
|---|--------|-------|--------------------|
| 1 | `ProductRelatedComponent` | `datasets/sfdmu/qb/en-US/qb-pcm/ProductRelatedComponent.csv` | Product never appears in the bundle |
| 2 | `type` + `relation` | the `.ffxblob` | Model has no concept of the product |
| 3 | ESC association, `ConstraintModelTagType = Type` | `ExpressionSetConstraintObj.csv` | **Product appears, then fails Product Validation** |
| 4 | ESC association, `ConstraintModelTagType = Port` | `ExpressionSetConstraintObj.csv` | Relation is not bound to the bundle component |

**#3 is the one that bites.** With #1 present and #3 missing, the configurator offers the
product because the bundle says it is a component, then rejects it because the model has
no type for it. Nothing points at the constraint model.

`Type` associations reference a **Product2** (`01t` prefix); `Port` associations reference
a **ProductRelatedComponent** (`0dS` prefix).

### Ports are per bundle relation, not per type

Only types reachable as **bundle members** get a `Port`. The counts make the rule visible —
Port count tracks `relation` count, not `type` count:

| Model | Type | Port | `relation`s in the CML |
|---|---:|---:|---:|
| `QuantumBitComplete` | 29 | 28 | 28 |
| `Server2` | 41 | 40 | 40 |
| `QuantumBitBundle` | 33 | 28 | 29 |
| `QuantumBitPCM` | 12 | **0** | — |

`QuantumBitPCM` is the case that disproves any "every type needs a Port" rule: it is a
virtual-quote model whose types are cart line items, not bundle components, so it has
**zero** Ports and is correct that way.

Bundle's 29 relations against 28 Ports is the same distinction in miniature — the odd one
is `lineitems` on the `@(virtual = "true") Quote` container, a cart-level relation rather
than a bundle component, so it has no Port either.

**So the four-record rule above applies to bundle members.** For a cart-level or
virtual-quote type, records 1 and 4 (the PRC row and the `Port` association) do not
apply.

### Sequence is part of the composite key

`import_cml` resolves a Port association's PRC in two hops, and neither one reads the
SFDMU plan's PRC rows:

1. **Legacy Id → composite key**, built from the **constraint dir's own**
   `ProductRelatedComponent.csv` (`tasks/rlm_cml.py:842-854`), as
   `ParentProduct.Name | ChildProduct.Name | ChildProductClassification.Name |
   ProductRelationshipType.Name | Sequence`.
2. **Composite key → real Id**, matched against `ProductRelatedComponent` records
   **queried from the target org** (`tasks/rlm_cml.py:868-892`).

`dataset_dirs` contributes only candidate *names* — products, classifications and PRC
parents — and those merely scope the org lookups, here as
`WHERE ParentProduct.Name IN (…) OR Name IN (…)`. It never supplies a composite key.

**So the sequence in the constraint dir has to match the PRC row the org actually holds.**
The plan matters because it is what loads that row — which is why copying the sequence
from the plan is the right authoring move. But when a Port fails to resolve, **query the
org**; do not diff the two CSVs. An org whose plan was never loaded, or was loaded from a
different revision, disagrees with the plan on disk.

It fails loudly rather than silently — `ImportCML` logs `Could not resolve
ReferenceObjectId` per row and accumulates `unresolved_tags` — but **it does not fail
atomically**, and the distinction matters when you are recovering.

`create_record()` is called inline for every row as the loop walks the ESC list, so by the
time a failure is diagnosed the rows that *did* resolve are already in the org. Step 6
(delete the old ESC records) is skipped on a failed import, so the previous generation of
rows is still there too. The task says so itself: *"Import had errors -- skipping deletion
of old ESC records. Target org may contain a mix of old and new constraints."*

**Two failure modes. Both now fail loudly** — they did not always:

| Failure | Raises? | Org left holding |
|---|---|---|
| A reference will not resolve (bad `Sequence`, missing product) | **yes** (not in `dry_run`) | every pre-existing ESC row, plus whatever was created before the failure; blob **not** uploaded |
| `create_record()` fails but every reference resolved | **yes** (not in `dry_run`) | same |

Usually that means a *mix* of old and new — but not always: if every create failed there
are no new rows, and on a model with no prior rows there is no old generation to mix with.
Query the ESC set rather than assuming.

Both converge on `describe_esc_import_failure()` in `tasks/rlm_cml.py`, and steps 6-7 run
through `_finalize_esc_import()`. The raise happens *after* the "skipping deletion of old
ESC records" warning and *before* the blob upload, so the model is never uploaded over a
partial ESC set. **A `dry_run` logs the same diagnosis at error level and does not raise** —
it wrote nothing, so nothing is left behind.

> ⚠️ **Before this fix, the second mode exited 0.** `unresolved_tags` was empty so the raise
> never fired: the blob uploaded, `Import complete` logged, and the task returned success
> over a partial set. `prepare_constraints` runs `import_cml`, so a build could go green
> carrying a partial constraint model. If you are reading logs from an older build, an
> `Import complete` there does **not** mean every ESC row landed.

**A clean rerun cleans up after either failure.** The existing-ESC snapshot is taken fresh
at the top of every run (`WHERE ExpressionSetId = …`, unfiltered otherwise), so it captures
the old generation *and* the partial rows left by the failed run; a pass that resolves and
creates everything then deletes the whole snapshot. Fix the cause and rerun — you do not
have to clear the mix by hand.

What does not self-correct is a rerun that *also* fails: the delete is skipped again and
another partial generation layers on. So if the import errored, rerun until one pass is
clean.

A dry run surfaces the resolution warnings without touching the org, which is why it is
worth reading rather than just checking its exit code.

---
