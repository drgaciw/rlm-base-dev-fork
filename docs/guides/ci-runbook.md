# CI Runbook

Procedures for keeping the repository's own CI honest: linting the workflows
themselves, proving `docker-publish` still works after an action bump, and
maintaining the baselines and ratchets (sections 3 to 7). Only section 6 involves
a Salesforce org. Background: [test plan §4.6](../references/test-plan-2026-09.md)
(TP-11).

## 1. Workflow lint (`actionlint` + `zizmor`)

Both run as steps of the **Lint (changed files)** job in
`.github/workflows/pr-checks.yml`, on pull requests that change
`.github/workflows/**`, `.zizmor.yml`, `.github/zizmor-baseline.json` or
`scripts/lint/finding_baseline.py`. Any other PR skips them. They are steps of
the existing job, not a new job, so the set of check-run names the workflow
publishes does not change.

| Tool | Pinned as | Verified by |
|---|---|---|
| `actionlint` | release tarball, `ACTIONLINT_VERSION` | `ACTIONLINT_LINUX_AMD64_SHA256` from the release's `checksums.txt` |
| `shellcheck` (used by `actionlint`) | PyPI `shellcheck-py`, `SHELLCHECK_PY_VERSION` | exact version; pinned so findings do not move with the runner image |
| `zizmor` | PyPI wheel, `ZIZMOR_VERSION` | exact version |

### What each one enforces

**actionlint** runs with `SHELLCHECK_OPTS=--severity=warning`. Every workflow
`run:` script is checked, and a shellcheck *warning* or *error* fails the PR.
The `info` and `style` findings are deliberately not reported: the repo has 11
of them (`SC2086` unquoted expansions, some of them intentional, `SC2016` on
literal `$`-text in single quotes, `SC2129` chained `echo >> file`) and hiding them by file or regex would also hide the next real
one. Severity is the one cut that leaves every warning visible.

**zizmor** runs `--pedantic --offline` against `.github/workflows/`, with the
policy in `.zizmor.yml`:

- `actions/*` may be pinned by tag (`ref-pin`); Dependabot bumps them.
- every other action must be pinned to a full commit SHA (`hash-pin`).
- Offline on purpose: the audits that query the GitHub API (known-vulnerable
  actions, impostor commits) depend on live advisory data and the network, so
  they would turn an unrelated PR red for a reason no commit caused. TP-12's
  weekly `zizmor --pedantic --no-config` run is a **non-gating drift audit**: it
  reports what the baseline suppresses and never fails a PR.

### The zizmor baseline

Findings that existed before the check was added are **counted**, not ignored:
`.github/zizmor-baseline.json` holds an allowed count per `(rule, file, message)`
and a one-line `reason`; `message` is zizmor's rule description, with no
location in it. `scripts/lint/finding_baseline.py` (the shared comparator, TP-11a)
compares the live findings with it:

| Situation | Result |
|---|---|
| more findings than allowed, or a `(rule, file, message)` not listed | **fail** (exit 1), the findings are printed with their line |
| fewer findings than allowed | pass, with a warning to shrink the baseline |
| zizmor or the baseline file is unreadable | exit 2, a tool error, not a verdict |

There are no line numbers in the baseline, so a parallel PR that shifts lines
in a workflow cannot make it stale. Because it is a count, a *new* finding of a
rule that is already listed for that file still fails.

Security-class entries (`excessive-permissions`, `adhoc-packages`) are labelled
`SECURITY` in their reason. They are recorded, not endorsed: fixing them belongs
to whoever owns the workflow.

**Fixing a finding.** Fix the workflow, then shrink the baseline:

```bash
pip install "zizmor==<ZIZMOR_VERSION from pr-checks.yml>"
zizmor --pedantic --offline --config .zizmor.yml --no-exit-codes --format json \
  .github/workflows/ > /tmp/zizmor.json
python scripts/lint/finding_baseline.py --name zizmor-finding \
  --baseline .github/zizmor-baseline.json --format zizmor /tmp/zizmor.json
# once it reports "can shrink":
python scripts/lint/finding_baseline.py --name zizmor-finding \
  --baseline .github/zizmor-baseline.json --format zizmor --write /tmp/zizmor.json
```

`--write` keeps the `reason` of every entry that survives. Never use it to
absorb a *new* finding; fix the finding instead. If it truly must be accepted,
add the entry by hand with a reason and say so in the PR description.

**Running actionlint locally** (needs the pinned `shellcheck` on `PATH` to match CI):

```bash
pip install "shellcheck-py==<SHELLCHECK_PY_VERSION>"
SHELLCHECK_OPTS=--severity=warning actionlint
```

### Bumping a pinned tool

One tool per PR. Change the version in the `Install actionlint, shellcheck and
zizmor (pinned)` step; for `actionlint` also replace the sha256 with the one in
that release's `checksums.txt` (`actionlint_<version>_linux_amd64.tar.gz`). A
new `zizmor` release adds audits, so expect the baseline to need an entry or a
fix. Run the commands above before pushing. The monthly maintenance pass in
[test plan §7](../references/test-plan-2026-09.md) covers these pins.

## 2. `docker-publish` smoke after an action bump

`docker-publish.yml` only runs on a tag push, a manual dispatch and the
**Monday 07:00 UTC** cron. A Dependabot bump of a `docker/*` action
(`setup-qemu-action`, `setup-buildx-action`, `login-action`,
`build-push-action`) therefore merges without the workflow having run, and
the first execution is the scheduled one. Prove it earlier:

**When:** after any PR that changes a `docker/*` action pin in
`docker-publish.yml`, before the next Monday 07:00 UTC.

**Dispatch from a throwaway branch, never from the default branch.**
`docker-publish.yml` adds `:latest` to the published tags whenever the run's
ref is the default branch, whatever the `tag` input says:

```yaml
# docker-publish.yml, "Set image coordinates" step
if [ "${EVENT_NAME}" = "schedule" ] || [ "${GITHUB_REF_NAME}" = "${DEFAULT_BRANCH}" ]; then
  tags="$(printf '%s\n%s' "${image}:${tag}" "${image}:latest")"
# ... (else: tags="${image}:${tag}")
```

A smoke dispatched with `--ref main` therefore overwrites the production
`:latest` with the **single-architecture** smoke image and breaks `arm64`
pulls until the next scheduled multi-arch build. The workflow's own guard
(`if [ "${tag}" = "latest" ] && [ "${GITHUB_REF_NAME}" != "${DEFAULT_BRANCH}" ]`)
only refuses `tag=latest` off the default branch; it does not stop `:latest`
being added on it.

```bash
day="$(date -u +%Y%m%d)"
# 1. a short-lived branch from the default branch (it carries the bumped pin)
git fetch <remote> main
git push <remote> "<remote>/main:refs/heads/ci-smoke/${day}"
# 2. dispatch from that branch (Actions -> Publish build-environment image ->
#    Run workflow also works: pick the ci-smoke/<date> branch, not main)
gh workflow run docker-publish.yml --repo <owner>/<repo> --ref "ci-smoke/${day}" \
  -f tag="ci-smoke-${day}" -f platforms=linux/amd64
gh run list --repo <owner>/<repo> --workflow docker-publish.yml --limit 1
gh run watch <run-id> --repo <owner>/<repo>
```

- The `tag` input is required. Use `ci-smoke-YYYYMMDD`, never `latest`.
- `platforms=linux/amd64` keeps the run short. It does **not** exercise the
  `linux/arm64` path or QEMU emulation; a bump of `setup-qemu-action` is only
  fully proved by the scheduled multi-arch run, or by dispatching once from
  the smoke branch with the default `linux/amd64,linux/arm64`.
- The workflow pushes (`push: true`). From the smoke branch it publishes only
  `ghcr.io/<owner>/rlm-base:ci-smoke-YYYYMMDD`. To be sure, note the digest of
  `ghcr.io/<owner>/rlm-base:latest` before dispatching
  (`docker buildx imagetools inspect ghcr.io/<owner>/rlm-base:latest`) and
  confirm it is unchanged afterwards.

**Pass criteria:** the run is green, and the job summary shows
`Published ghcr.io/<owner>/rlm-base:ci-smoke-YYYYMMDD`. Optionally
`docker pull` that tag to confirm the image is there.

**Clean up:** delete both artefacts afterwards.

```bash
git push <remote> --delete "ci-smoke/${day}"
```

and delete the `ci-smoke-*` package version (GitHub -> Packages -> `rlm-base`
-> the version -> *Delete*), so smoke tags do not accumulate. A failed smoke
run means the bump should be reverted or fixed before the cron fires; note the
run URL in the PR that introduced the bump.

This is a manual procedure. Nothing in CI dispatches it, so the run result
above is evidence for a PR only when someone has actually done it.

## 3. Regenerating the Apex Code Analyzer baseline

The **Apex findings vs baseline** step of the Lint job (`pr-checks.yml`) compares
a full Code Analyzer scan (PMD Security + ErrorProne tags) with
`config/code-analyzer-baseline.json`, using the same comparator as zizmor. It runs
when Apex, `code-analyzer.yml`, the baseline, `scripts/lint/finding_baseline.py`
or `pr-checks.yml` changes. Regenerate after a Code Analyzer version bump
(`CODE_ANALYZER_VERSION`, bump it in its own PR) or after fixing findings:

1. Download the `code-analyzer-results` artifact of a green run of that job (its
   paths are Linux paths, which is what CI compares against).
2. Run

   ```bash
   python scripts/lint/finding_baseline.py --format code-analyzer --name "Apex finding"      --baseline config/code-analyzer-baseline.json --write code-analyzer-results.json
   ```

3. `--write` keeps each entry's `reason`; give every new entry one. A renamed or
   moved `.cls` re-surfaces its entries as new findings, so regenerate in the same
   PR.

## 4. Python coverage ratchet: raising a floor

`coverage-floor.json` holds a floor per package; the **Python coverage ratchet**
job fails below a floor and on a PR that lowers one. Being above the floor only
prints a `::notice::` ("coverage floor can be raised"); CI never raises it. To
raise floors after a real improvement:

```bash
python scripts/lint/coverage_ratchet.py measure            # runs the whole gate under coverage
python scripts/lint/coverage_ratchet.py update --report coverage/python-coverage.json
```

`update` sets each floor to the measured value rounded down to one decimal, never
lowers a floor and never touches `target`. Commit the file. Lowering a floor
needs a `coverage-floor-lowered: <reason>` line in the file's top-level `reason`
field, which a reviewer must accept.

## 5. Windows leg: waiving a check

`Mechanical checks (Windows stdlib)` runs `pr_gate.py --all --tier stdlib` on
`windows-latest` with `PYTHONUTF8` unset (never set it: it hides the encoding bugs
the leg exists to find). A check that is flaky or cannot run on Windows is fixed
or moved out of the tier within 2 working days (test plan §7); it is never
retried. The only way out is an entry in `WINDOWS_WAIVERS` in
`scripts/ai/pr_gate.py`, mapping the check name to a written reason;
`tests/test_pr_gate.py` fails an entry that names no real check or has no reason,
and a dependency-free check that is neither in the tier nor waived. The map is
empty today. The leg runs only the dependency-free tier, so the
`requests`-dependent contract suites are not covered on Windows (test plan,
TP-13 row). Making the job a required check is a maintainer settings action.

## 6. Triage of the nightly and the flow matrix

Both need a Dev Hub and are not reproducible offline.

- **Nightly** (`prepare-rlm-org.yml`, weekdays 03:00 UTC): start from the run's job
  summary, then the `verify-<alias>-<run>` and `e2e-<alias>-<run>` artifacts. A
  Robot test that passed only on the single rerun is reported as flaky, not green.
- **Flow matrix** (`flow-matrix.yml`, weekly): a failed leg opens or comments on
  an issue titled `Flow matrix failure: <shape>`; the leg's job summary and
  artifacts hold the detail.
- Neither reruns automatically on the Apex or build stages (test plan §7.3).
  Re-dispatch by hand once the cause is fixed.
- Scratch orgs are created with a 1-day lifetime and deleted at the end of the
  job. A `::warning::` "Could not delete scratch org <alias>" means a possible leak:
  check the Dev Hub.
- A repeat offender goes into `robot/QUARANTINE.md` or
  `tests/quarantine/registry.json` (owner, issue, `expires` within 14 days).

## 7. Staleness policy

The same idea applies everywhere; what differs is whether staleness fails:

| Kind | Examples | An entry that is no longer needed |
|---|---|---|
| Name allowlists | `WINDOWS_WAIVERS`, quarantine registers | **fails** (an entry naming no real check, or past its `expires`, is an error) |
| Count baselines | zizmor, Apex Code Analyzer, robot `Sleep` counts | **warns** that the baseline can shrink; never fails a PR that fixed something |
| Coverage floors | `coverage-floor.json` | **notice** that the floor can be raised |

Shrink or raise them in a normal PR; never widen one to make a check pass without
a `reason` a reviewer accepts.
