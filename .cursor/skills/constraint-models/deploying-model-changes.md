# Making a Constraint-Model Change Reach an Org

Read this when `import_cml` succeeded but the configurator still runs the old model — the deactivate → import → activate cycle, why `prepare_constraints` orders it the way it does, and the standalone-import cycling recipe. Parent skill: [SKILL.md](SKILL.md).

## Making a change reach an org

**`import_cml` uploads the blob; it does not redeploy the model.** If the target
`ExpressionSetDefinitionVersion` is already `Active`, the new model is stored and the org
keeps running the old one — and the import reports success.

```bash
# manage_expression_sets does NOT accept --org (see Known gaps) -- it uses the DEFAULT org.
# Set the default first so all three steps hit the same org.
cci org default <cci_alias>

# <Version>  = the ApiName from the discovery query, e.g. QuantumBitBundle_V1
# <DataDir>   = the model's directory under datasets/constraints/, from `ls -d`
# <PlanDir>   = the SFDMU plan that loaded the ESC's Product2/PRC rows into the org
#               (it supplies the names that scope import_cml's lookup queries)
cci task run manage_expression_sets -o operation deactivate_versions \
    -o version_full_names "<Version>"

cci task run import_cml --org <cci_alias> \
    -o data_dir <DataDir> \
    -o dataset_dirs "<PlanDir>"

cci task run manage_expression_sets -o operation activate_versions \
    -o version_full_names "<Version>"
```

<details><summary>Filled in for the QuantumBit bundle, as an example</summary>

```bash
cci task run manage_expression_sets -o operation deactivate_versions \
    -o version_full_names "QuantumBitBundle_V1"
cci task run import_cml --org <cci_alias> \
    -o data_dir datasets/constraints/qb/QuantumBitBundle \
    -o dataset_dirs "datasets/sfdmu/qb/en-US/qb-pcm"
cci task run manage_expression_sets -o operation activate_versions \
    -o version_full_names "QuantumBitBundle_V1"
```

</details>

`prepare_constraints` does this for you at steps 11-12; a standalone `import_cml` does
not. See below.

### How the flow handles it, and why step 11 looks redundant

`manage_expression_sets` is the right tool: `_update_version_status` queries
`ExpressionSetVersion` by `ApiName` and PATCHes `IsActive`
(`tasks/rlm_manage_expression_sets.py:527-591`) — the same record and field the Constraint
Builder UI toggles.

`prepare_constraints` orders it like this:

```
 7-10. import_cml  Complete, Server2, PCM, Bundle
11.    deactivate  -> QuantumBitComplete_V1, QuantumBitPCM_V1, QuantumBitBundle_V1, Server2_V1
12.    activate    -> Server2_V1, QuantumBitBundle_V1
```

Those names are the flow's current configuration, not a rule — read them from
`cci flow info prepare_constraints` rather than from here.

**Every version step 12 activates also appears in step 11 — deliberately.**
That is the invariant to preserve: `QuantumBitBundle_V1` and `Server2_V1` are both
activated, so both must be deactivated first. Steps 7–10 upload into a
version that may already be active, which stores the blob without redeploying the runtime
model; step 11 then deactivates Bundle and step 12 reactivates it, giving the
deactivate/reactivate cycle that makes the platform pick the new model up. Removing Bundle
from step 11 would make step 12 a no-op on an already-active version and the flow would
report success while the org kept running the old model. It is a no-op on a fresh build,
where versions are created inactive.

> Verified at step level on a scratch org: Bundle `true` → deactivated → `true`, with
> Complete and PCM left `false`. **Not yet verified end-to-end** — that a full flow run
> against an org with an already-active model carries a change through to the configurator
> still needs a real build, and is tracked separately.

**A standalone `import_cml` gets none of this** — it uploads and stops. That is the normal
way to ship a model change, so cycle the version yourself afterwards:

```bash
cci org default <cci_alias>   # manage_expression_sets does not accept --org, see Known gaps

# <Version> is the ApiName from the discovery query — e.g. QuantumBitBundle_V1,
# Server2_V1, or whatever the org actually reports as active for the model you changed.
cci task run manage_expression_sets -o operation deactivate_versions \
    -o version_full_names "<Version>"
cci task run manage_expression_sets -o operation activate_versions \
    -o version_full_names "<Version>"
```

Cycle **the version you imported into**. If several models are active, cycling an
unrelated one proves nothing and briefly deactivates a model something else may depend on.

or do the same in the UI: the Constraint Model record is the `ExpressionSet` record page
(`/lightning/r/ExpressionSet/<9QL…>/view`), its **Constraint Model Versions** related list
is `ExpressionSetVersion`, and opening a version launches **Constraint Builder**, whose
toolbar carries **Sync**, **Deactivate** and **Save**.

Salesforce documents the requirement:

> "If the table data is deployed when the constraint model is activated, and you add
> records to the table after constraint model activation, to fetch the new table data at
> runtime you must deactivate and reactivate the constraint model."
> — Help, *Import Object Data* (262)

> **Not yet investigated:** the builder's **Sync** button, which is distinct from
> activate/deactivate. Its effect is unknown — do not assume it is a no-op.

---
