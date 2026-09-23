@AGENTS.md

## Claude Code specifics

- If skills under `.claude/skills/` or `.agents/skills/` look like tiny stub files instead of directories, this checkout lost symlinks (common on Windows): run `python scripts/ai/link_skills.py --fix` (no admin rights needed), then start a new session.
- Scope file searches under `docs/salesforce/` to `docs/salesforce/264/` — older release snapshots live alongside it and are not the active line.
- Generated analysis (reports, scorecards, coverage matrices) belongs under `.agents/artifacts/`, not `docs/analysis/`.
