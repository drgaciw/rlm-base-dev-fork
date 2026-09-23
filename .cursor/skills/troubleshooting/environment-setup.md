# Environment & Setup Errors

Read this when local toolchain setup, org auth, or the initial
`validate_setup` gate is failing. Parent skill: [SKILL.md](SKILL.md).

## `cci task run validate_setup` fails

Run this first — it checks everything:

| Check | Fix |
|-------|-----|
| Python < 3.10 | Install Python 3.12 or 3.13 via `pyenv` (3.10 is the repo floor; 3.12/3.13 are recommended for CumulusCI) |
| CumulusCI not found | `pipx install cumulusci --python "$(pyenv prefix)/bin/python3"` |
| SF CLI < v2 | `npm install -g @salesforce/cli` (NOT `brew install sf`) |
| SFDMU plugin missing/outdated | Auto-fixed by default (`auto_fix=true`). Manual: `sf plugins install sfdmu` |
| Node.js not found | `nvm install --lts && nvm alias default lts/*` |
| Robot Framework deps missing | Auto-fixed by default. Manual: `pipx inject cumulusci --force -r robot/requirements.txt` |
| Chrome/ChromeDriver missing | Install Chrome; `pip install webdriver-manager` |
| urllib3 < 2.6.3 (CVE) | `pipx inject cumulusci urllib3>=2.6.3` |

## `sf` or `node` not found in IDE / CI

**Cause:** `~/.zshenv` is missing nvm/pyenv init blocks. Non-interactive
shells (IDE terminals, CI runners) don't source `~/.zshrc`.

**Fix:** Add both nvm and pyenv init to `~/.zshenv` AND `~/.zshrc`.

## "Org not found" or "auth failed" errors

CCI and `sf` CLI maintain **separate org registries** with different aliases.

| Tool | Alias Format | Example |
|------|-------------|---------|
| `cci` (`--org`) | Short alias | `beta` |
| `sf` (`--target-org`) | Project-prefixed | `rlm-base__beta` |
| Either | Username (always works) | `test-abc123@example.com` |

**Common mistakes:**
- Using CCI alias `beta` with `sf` CLI → **fails** (use `rlm-base__beta`)
- Using SF CLI alias `rlm-base__beta` with `cci` → **fails** (use `beta`)
- Using `org_config.access_token` as `--target-org` → **fails** + leaks secret

**In Python tasks:** Always use `self.org_config.username` for `sf` CLI
calls. Use `self.org_config.access_token` + `.instance_url` only for
direct REST API calls via `requests`.

```bash
# Find the right identifier
cci org list              # shows CCI aliases
sf org list               # shows sf aliases (rlm-base__* prefix)
cci org info beta         # shows username, instance URL
```

## `INVALID_AUTH_HEADER` / "Expired session" on a healthy scratch org

**Symptom:** every `cci` command that touches an org fails with
`INVALID_AUTH_HEADER` (or "Expired session"), even on a brand-new org — but
`sf data query --target-org USERNAME` reaches the same org fine.

**Cause:** CumulusCI 4.10 parses `sf org display` for the access token, and
sf CLI >= 2.13.0 now **redacts** it. CCI sends a bogus header.

**Fix:** set `SF_TEMP_SHOW_SECRETS=true`. The repo's tracked `.envrc` already exports
it, so **direnv users are covered automatically** inside the repo; otherwise prefix a
command for a one-off, or for a durable / Dock-launched-IDE setup use `~/.zshenv` + a
LaunchAgent. **Do not** delete or recreate the org — and never `cci org remove` a
scratch org (it deletes it).
Full guide, including the durable setup, the security tradeoff, and **how to
check for / remove the workaround once an official fix ships**:
[cci-sf-cli-token-workaround.md](../../../docs/guides/cci-sf-cli-token-workaround.md).

## `NonScratchOrgError` ("This command works with only scratch orgs")

**Symptom:** a scratch-only SF CLI command — most often `sf org create user`
(the `create_personas_sales_rep_user` task in `prepare_personas`), but also
`sf org generate password` — fails with `NonScratchOrgError` against an org you
created as a scratch org. Common on **Enterprise-Edition / "ent"** shapes
(e.g. `orgs/internal/ent-r1.json`).

**Cause:** an SF CLI bug — EE scratch orgs created via the DevHub API get
`"isScratch": false` written to the local auth file
(`~/.sfdx/<username>.json`) even though they are real scratch orgs (valid
`devHubUsername`, listed under `scratchOrgs` in `sf org list`). The CLI then
refuses scratch-only commands. CCI's own `org_config.scratch` is unaffected, so
**`prepare_rlm_org` self-heals** — `prepare_core` step 1 runs
`fix_scratch_org_identity` before any scratch-only CLI command.

**Fix (standalone, when running CLI commands outside the flow):**

```bash
cci org default ent-r1                      # this CCI build uses the default org (no --org)
cci task run fix_scratch_org_identity        # sets isScratch=true (when false or missing) if devHubUsername is present
```

The task is idempotent (no-op when already correct) and only sets
`isScratch=true` (when it is false or missing) when the auth file has a
`devHubUsername` (so it never mis-tags a real non-scratch org).
