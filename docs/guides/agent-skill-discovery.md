# Use the skills in your coding agent

Clone the **full repository**, preserve symbolic links, and open the repository
root in your agent. Skills use the scripts, data, documentation, and safety
rules shipped alongside them; copying an individual skill folder is not a
standalone installation.

## Shared content and discovery paths

| Path | Role |
|------|------|
| `.cursor/skills/<name>/` | Canonical skill content; edit here |
| `.agents/skills/<name>` | Relative directory link to the canonical skill for Codex and compatible clients |
| `.claude/skills/<name>` | Relative directory link to the same skill for Claude Code and compatible clients |

Each link targets `../../.cursor/skills/<name>`, so the entry point and its
supporting files stay together. There is one content copy. Read
[`AGENTS.md`](../../AGENTS.md) for repository-wide rules before using a skill.
The cross-repository manifest in `.claude/skill-manifest.yml` is separate from
these native discovery paths.

## Try discovery

Start a new session after cloning or updating the repository. Use the client's
skill picker to find `odt-authoring`, then try this read-only prompt:

```text
Use the odt-authoring skill to explain whether ODT field paths use dots or
colons, and which skill handles .docx templates. Do not change files or an org.
```

In Codex CLI, select the skill with `$odt-authoring` or `/skills`. In Claude
Code, invoke `/odt-authoring`. A successful answer identifies colon-separated
ODT paths and routes template work to `document-generation`.

### Verification coverage

The following checks were run on macOS for this adapter change:

| Client | Result |
|--------|--------|
| Codex CLI `0.154.0-alpha.6.2` | Native inventory found all 32 repository skills once each; explicit `$odt-authoring` invocation passed |
| Claude Code `2.1.69` | Native inventory found all 32 repository skills once each; explicit `/odt-authoring` invocation passed |
| Cursor Agent CLI `2026.05.01-eea359f` | Invocation could not run without authentication; discovery and duplicate handling remain unverified |
| GitHub Copilot | No local client test; native discovery and duplicate handling remain unverified |

These results cover discovery and one read-only invocation, not every workflow
or client version. Keep the catalog fallback below available.

Official references describe the respective discovery locations:
[Codex](https://learn.chatgpt.com/docs/build-skills),
[Claude Code](https://code.claude.com/docs/en/skills),
[Cursor](https://cursor.com/docs/skills), and
[Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills).
Some clients scan several compatible roots. If a client shows duplicate names,
they may point to the same canonical content; use the catalog path to select
the intended skill. Avoid installing another personal copy of this library
unless you deliberately want it available across repositories.

## Windows, downloads, and missing skills

Git must check out the skill adapters (`.agents/skills/<name>`,
`.claude/skills/<name>`) as symbolic links. Many Windows environments and
archive extraction tools instead produce small text files containing the
link target. Those files do not provide native discovery. Windows symlink
checkout requires OS support/permission as well as Git's `core.symlinks`
setting; changing the setting alone does not repair an existing checkout.
(`CLAUDE.md` itself is a regular tracked file that imports `AGENTS.md` via
`@AGENTS.md` — see the [official Windows guidance](https://code.claude.com/docs/en/memory)
— so it needs no symlink repair.)

**Fix it in place — no admin rights or Developer Mode required:**

```sh
python scripts/ai/link_skills.py --fix
```

This replaces the stub files under `.agents/skills/` and `.claude/skills/`
with directory junctions on Windows (or symlinks elsewhere) and marks the
64 link entries themselves `skip-worktree`, so plain `git status` stays
clean. `skip-worktree` does **not** cover the files a junction resolves
into: `git status -uall` (and therefore `git add -A`) shows those as
untracked, so stage skill changes by editing under `.cursor/skills/`
directly rather than through a `.claude/skills/`/`.agents/skills/` path, and
avoid `git add -A`/`git add .` from the repository root after running
`--fix`. Restart the agent session afterward. Run
`python scripts/ai/link_skills.py --check` any time to detect stubs without
changing anything; a project `SessionStart` hook runs this automatically and
prints a one-line hint when it finds one.

If you would rather avoid per-checkout repair, use a fresh clone in a
symlink-capable environment (such as WSL), or use the catalog fallback below.

From the repository root, verify the shape of one link:

```sh
ls -ld .agents/skills/odt-authoring .claude/skills/odt-authoring
```

Both should be directory links (or, after `link_skills.py --fix` on Windows,
junctions) to `../../.cursor/skills/odt-authoring`, and `SKILL.md` should be
readable through either path. If the client still omits the skill, restart
its session and check its project-skill settings. In Claude Code, excluding
`project` from `--setting-sources` also excludes these project skills in the
tested version.

### Catalog fallback — works without native discovery

Give any agent with repository-file access this prompt:

```text
Read AGENTS.md and .cursor/skills/README.md. Select and read the relevant
.cursor/skills/<name>/SKILL.md and its linked references before answering
my task. Follow the repository's validation and approval requirements.
```

The [skill catalog](../../.cursor/skills/README.md) and canonical files remain
usable when links are unavailable. Private maintainer artifacts are not
required to browse the public skills; workflows such as the private todo
tracker have their own access requirements.

## Optional: Salesforce DX MCP (opt-in)

The [`@salesforce/mcp`](https://github.com/salesforcecli/mcp) server exposes
Salesforce DX tooling (deploy, query, org/test/devops operations) as MCP
tools. This repository does **not** commit a root `.mcp.json` for it: `claude
-p`, the Agent SDK and `claude-code-action` all load project-scoped MCP
servers **without prompting**, so a committed server would spawn in CI on
every run. Add it yourself, locally, in **local scope** (`.claude/settings.local.json`,
which is git-ignored) or with `claude mcp add --scope local`:

```json
{ "mcpServers": { "salesforce": { "command": "npx",
  "args": ["-y", "@salesforce/mcp@0.30.15", "--orgs", "DEFAULT_TARGET_ORG",
           "--toolsets", "data", "--tools", "run_apex_test,list_all_orgs",
           "--no-telemetry"] } } }
```

Prefer an explicit org alias over `DEFAULT_TARGET_ORG` whenever a production
org could be the default — the server reuses `sf` CLI auth, and several of
its tools (`deploy_metadata`, `assign_permission_set`, `retrieve_metadata`,
the devops and NON-GA scratch-org tools) mutate an org or overwrite local
files. The project `.claude/settings.json` already denies
`mcp__salesforce__deploy_metadata`, `mcp__salesforce__assign_permission_set`
and `mcp__salesforce__delete_org`. Add denies in your own settings for any
other mutating tool you enable.

Those denies are a **backstop, not the security boundary**. Hiding a tool
limits what the agent can ask for. It does not limit what the authenticated
Salesforce user is allowed to do. Authorize the server's org as a
**dedicated, least-privilege integration user**, not a personal admin login.
Grant that user only the permissions the enabled toolsets need, and avoid
Modify All Data, Author Apex and Modify Metadata unless a workflow truly
requires them.

If a bare `npx` invocation fails to launch under a stdio client on Windows,
wrap it — `"command": "cmd", "args": ["/c", "npx", "-y", "@salesforce/mcp@0.30.15", …]`
— but keep that wrapped form in **local scope only**: it breaks the same
config on macOS and Linux, so it must never land in a project-scoped or
committed file. Because unattended runs (CI, `-p`, `claude-code-action`) load
project-scoped servers silently, never promote this server out of local
scope, and never add a root `.mcp.json` for it.
