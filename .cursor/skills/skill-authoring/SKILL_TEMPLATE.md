---
name: skill-name
description: >-
  One to three sentences. Describe the capability, then the concrete task
  triggers ("Use when..."). Distinguish this skill from adjacent skills whose
  scope overlaps. Keep it under 1,024 characters and free of release numbers,
  API versions, or object/field counts that will go stale.
---

# Skill Name — Short Purpose

One short paragraph: what this skill is for and who can consume it (this
repo's agents are not Cursor-only — write for any tool that can read files).

## Quick Rules

1. 5-8 numbered rules. State the most important decisions and commands first.
2. Keep each rule to a sentence or two; push detail into the workflow sections
   or a linked sub-file.
3. …

## DO NOT

- **DO NOT** <explicit safety constraint>. <Why, briefly.>
- **DO NOT** <a common mistake this skill exists to prevent>.

## Entry Conditions

| Situation | Use this skill? |
|-----------|-----------------|
| <the common case> | Yes — <what it gives you> |
| <an adjacent case> | No — see `<other-skill>/SKILL.md` |

## <Main workflow section(s)>

The bulk of the skill: the procedure, in imperative wording, with concrete
commands. Prefer tables and short examples over long narrative.

**Budget: this file must stay at or under 500 lines** (checked by
`python scripts/ai/analyze_agent_tooling.py check`). When a workflow section
grows past what fits here — one product domain, one advanced troubleshooting
path, a generated reference — split it into a sub-file under this skill's
directory and link it below rather than letting `SKILL.md` grow past the
budget. See `skill-authoring/SKILL.md` § "Progressive Disclosure" for the
split criteria.

## Sub-Files

Delete this section if the skill has no sub-files yet. When it does, add one
row per sub-file with an actual Markdown link (e.g. `[my-sub-file.md](my-sub-file.md)`)
— this table is the only registry; a sub-file this list omits is effectively
undiscoverable to `analyze_agent_tooling.py check` and to non-Cursor agents.

| File | Contains |
|---|---|
| `<sub-file.md>` | Read this when... |

## Examples

Small, concrete examples that demonstrate routing and expected edits.

## Validation Checks

Commands and review checks to run before commit/PR:

```bash
python scripts/ai/analyze_agent_tooling.py check
```

Also see `doc-consistency/SKILL.md` for the change-surface map, and
`skill-authoring/SKILL.md` § "Registration Checklist" for where a *new*
top-level skill or sub-file must be registered (`.cursor/skills/README.md`,
`AGENTS.md`, native discovery links via `scripts/ai/link_skills.py --fix`,
and `.claude/skill-manifest.yml` if cross-repo/PMOS discoverable).
