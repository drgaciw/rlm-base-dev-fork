---
description: Drive automated PR-review comments to zero unresolved (verify → sweep → reply+👍+resolve)
argument-hint: <pr-number>
allowed-tools: Bash(python scripts/ai/pr_review.py *)
---

Process **every** automated review comment on **PR #$ARGUMENTS** to **zero
unresolved threads**, following the canonical review protocol in
`.cursor/skills/audit-review/SKILL.md` ("The process").
Use the helper `scripts/ai/pr_review.py`.

1. **List open threads:**
   `python scripts/ai/pr_review.py status $ARGUMENTS`

2. **For each open comment** (do NOT trust the bot):
   - **Verify against the code** — open the cited file; classify the finding
     *real*, *partial*, or *false positive*.
   - **Sweep the class** — if real, fix **every** instance of that pattern across
     the change, not just the cited line. Commit the fix; note the SHA.
   - **Resolve it** — for a **valid** finding, reply in-thread with the SHA, 👍,
     and resolve in one call:
     `python scripts/ai/pr_review.py handle $ARGUMENTS --comment <id> --body "<resolution + commit SHA>"`
     For a **false positive**, put an evidence-backed refutation in `--body` and add
     `--no-react` — reply + resolve but **don't** 👍, and don't change correct code.
     (👍 only on valid comments, per `.cursor/skills/audit-review/merge-and-review-procedures.md`.)

2b. **Push once.** After every real finding is fixed and verified locally, push the
    branch a single time (REVIEW.md → *Push discipline*). Post the `handle` replies
    only after that push, so each cited SHA is visible on the PR.

3. **Confirm clean:**
   `python scripts/ai/pr_review.py verify $ARGUMENTS` → must report **0
   unresolved**. If any remain, handle them and re-run.

Never leave a thread open: branches headed for `main` mirror to the internal
Salesforce repo for audit, which re-raises any open thread.
