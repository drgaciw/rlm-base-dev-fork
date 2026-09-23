#!/usr/bin/env python
"""Offline checks for the local-only path handling in `skill_manifest.py --check`.

The audit's claim is that every path-shaped value in the Foundations section resolves in
the working tree. `.agents/artifacts/` breaks that claim by design: it is a separate
PRIVATE repo, gitignored by the main one, and the analysis-artifacts rule requires
generated working documents to live there — so tracked files legitimately cite paths
inside it. The audit demanded those paths resolve, which made `--check` fail on every
fresh clone and in CI while passing on the one workstation holding the clone. Found by
review on PR #383, when the gate proposed to make `skill_manifest.py --check` gating.

The fix must hold two properties at once, and only the pair is correct:

  1. Absent private tree  -> the reference is REPORTED as unaudited, and the run passes.
     A silent skip would be the unfalsifiable check this module's own docstrings warn
     about; a failure would break CI for a path CI cannot have.
  2. Present private tree -> the reference is audited normally, so a typo still fails.
     Downgrading it everywhere would have traded a false failure for a blind spot.

Run: python tests/test_skill_manifest_audit.py   (needs PyYAML; no org, no network)
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "scripts", "ai"))

import skill_manifest  # noqa: E402

PASSED = 0
FAILED = []


def check(label, condition, detail=""):
    global PASSED
    if condition:
        PASSED += 1
        print(f"  [PASS] {label}")
    else:
        FAILED.append(label)
        print(f"  [FAIL] {label}" + (f"\n         {detail}" if detail else ""))


class _Resolved:
    """Stands in for RepoLocation: the audit reads only `.path`."""

    def __init__(self, path):
        self.path = path


def audit(root, cited, *, create_private):
    """Run the audit over a throwaway tree citing one local-only path."""
    tracked = Path(root, "docs", "real.md")
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("tracked\n", encoding="utf-8")
    if create_private:
        target = Path(root, cited)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("private\n", encoding="utf-8")
    section = {
        "_resolved": _Resolved(root),
        # A real path alongside the local-only one, so a pass cannot come from an
        # empty walk.
        "grounding": {"tracked": "docs/real.md", "private": cited},
        "skills": [],
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = skill_manifest._audit_foundations({"foundations": section})
    return ok, buf.getvalue()


CITED = ".agents/artifacts/integration-staging/pmos-integration.md"

print(__doc__.splitlines()[0])
print("=" * 100)

with TemporaryDirectory() as root:
    ok, out = audit(root, CITED, create_private=False)
    check("an absent private tree does not fail the audit", ok is True, out)
    check("the unaudited reference is named, not swallowed", CITED in out, out)
    check("the reason is given as absence, not drift",
          "not audited" in out and "absent" in out, out)
    check("the summary stops claiming that ALL paths resolve",
          "all auditable paths resolve" in out, out)
    check("a real path in the same walk is still resolved", "[OK" in out, out)

with TemporaryDirectory() as root:
    ok, out = audit(root, CITED, create_private=True)
    check("a present private tree is audited, and a correct path passes", ok is True, out)
    check("nothing is reported as unaudited when the tree is there",
          "not audited" not in out, out)
    check("the summary reverts to the unqualified claim",
          "all paths resolve" in out and "auditable" not in out, out)

with TemporaryDirectory() as root:
    # The discriminating case: the tree exists but the cited file inside it does not.
    Path(root, ".agents", "artifacts").mkdir(parents=True)
    ok, out = audit(root, CITED, create_private=False)
    check("a typo inside a PRESENT private tree still fails", ok is False, out)
    check("the failure names the missing path", CITED in out, out)
    check("it is reported as a problem, not as unaudited",
          "[ERROR]" in out and "not audited" not in out, out)

with TemporaryDirectory() as root:
    # A path merely *resembling* the private prefix must not inherit the exemption.
    lookalike = ".agents/artifacts-notes/decoy.md"
    Path(root, ".agents", "artifacts").mkdir(parents=True)
    ok, out = audit(root, lookalike, create_private=False)
    check("a sibling directory with a similar name is not exempt", ok is False, out)

check("the exempt prefix is anchored with a separator",
      skill_manifest.LOCAL_ONLY_PREFIXES == (".agents/artifacts/",),
      skill_manifest.LOCAL_ONLY_PREFIXES)


# ─── _audit_release_identity: release-identity drift detection ─────────────
#
# `.agents/context/project-memory.json` is the single source of truth for
# release identity (release_active, release_prior_ga, api_version_active,
# pr_base_branch). Finding A7/A8 (docs/ARCHITECT_REVIEW.md) was that this
# identity had already drifted in ~8 hand-written places, including this
# manifest's own erd_data/help_corpus_active grounding pointing at a stale
# capture after a fresher one existed on disk. These checks build a minimal,
# internally-consistent fixture tree and then perturb one fact at a time to
# confirm each kind of drift is actually caught, not just resolvable.

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _release_fixture(root: str, **overrides):
    """Build a self-consistent release-identity fixture tree and manifest dict.

    `overrides` replaces top-level keys of the returned manifest dict (e.g.
    `salesforce_release_active="262"`) so a caller can introduce exactly one
    drift without hand-rebuilding the whole fixture.
    """
    root_path = Path(root)
    _write(root_path / ".agents" / "context" / "project-memory.json", json.dumps({
        "release_active": "264",
        "release_prior_ga": "262",
        "api_version_active": "v68.0",
        "pr_base_branch": "main",
    }))
    _write(root_path / "README.md", "This branch: Release 264 (Winter '27), API v68.0.\n")
    _write(root_path / "CONTRIBUTING.md", "Target base branch `main` (Release 264, API v68.0).\n")
    _write(root_path / "docs" / "index.md", "main is the Release 264 (API v68.0) line.\n")
    _write(root_path / "docs" / "erds" / "erd-data.json", json.dumps({
        "metadata": {"release": "264", "apiVersion": "68.0"},
        "stats": {"totalFields": 4252},
    }))
    _write(root_path / "docs" / "salesforce" / "264" / "help" / "manifest.json", json.dumps({
        "release": "264",
        "stats": {"captured": 1131},
    }))
    manifest = {
        "_self_repo_root": str(root_path),
        "salesforce_release_active": "264",
        "salesforce_release_prior_ga": "262",
        "api_version_active": "v68.0",
        "foundations": {
            "grounding": {
                "erd_data": {"release": "264", "api_version": "v68.0", "field_count": 4252},
                "help_corpus_active": {
                    "release": "264",
                    "path": "docs/salesforce/264/help/articles/",
                    "article_count": 1131,
                },
            }
        },
    }
    manifest.update(overrides)
    return manifest


with TemporaryDirectory() as root:
    manifest = _release_fixture(root)
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = skill_manifest._audit_release_identity(manifest)
    out = buf.getvalue()
    check("a self-consistent fixture passes", ok is True, out)
    check("a passing run reports OK, not ERROR", "[ERROR]" not in out, out)

with TemporaryDirectory() as root:
    # Manifest top-level disagrees with project-memory.json (the A7 shape:
    # CONTRIBUTING said `main` while AGENTS.md gated against `origin/264`).
    manifest = _release_fixture(root, salesforce_release_active="262")
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = skill_manifest._audit_release_identity(manifest)
    out = buf.getvalue()
    check("manifest top-level drift from project-memory.json fails", ok is False, out)
    check("the failure names salesforce_release_active", "salesforce_release_active" in out, out)

with TemporaryDirectory() as root:
    # README stops mentioning the active release (drift in a prose doc).
    manifest = _release_fixture(root)
    _write(Path(root) / "README.md", "This branch: Release 262 (Summer '26), API v67.0.\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = skill_manifest._audit_release_identity(manifest)
    out = buf.getvalue()
    check("a stale README fails the audit", ok is False, out)
    check("the failure names README.md", "README.md" in out, out)

with TemporaryDirectory() as root:
    # erd_data grounding is stale relative to the actual erd-data.json on disk
    # (the exact A8 shape: manifest says 4,190 fields, the file says 4,252).
    manifest = _release_fixture(root)
    manifest["foundations"]["grounding"]["erd_data"]["field_count"] = 4190
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = skill_manifest._audit_release_identity(manifest)
    out = buf.getvalue()
    check("stale erd_data.field_count fails the audit", ok is False, out)
    check("the failure names erd-data.json", "erd-data.json" in out, out)

with TemporaryDirectory() as root:
    # help_corpus_active still points at the prior-GA release even though the
    # active release's corpus is captured on disk (the exact A8 shape).
    manifest = _release_fixture(root)
    manifest["foundations"]["grounding"]["help_corpus_active"] = {
        "release": "262",
        "path": "docs/salesforce/262/help/articles/",
        "article_count": 935,
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = skill_manifest._audit_release_identity(manifest)
    out = buf.getvalue()
    check("stale help_corpus_active fails the audit", ok is False, out)
    check("the failure names the active release", "264" in out, out)

with TemporaryDirectory() as root:
    # project-memory.json itself is absent -- the SSOT is missing, not just
    # disagreeing, and that must fail loudly rather than default to "OK".
    manifest = _release_fixture(root)
    (Path(root) / ".agents" / "context" / "project-memory.json").unlink()
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = skill_manifest._audit_release_identity(manifest)
    out = buf.getvalue()
    check("a missing project-memory.json fails the audit", ok is False, out)
    check("the failure names project-memory.json", "project-memory.json" in out, out)

print("\n" + "=" * 100)
if FAILED:
    print(f"{len(FAILED)} FAILED: {', '.join(FAILED)}")
    sys.exit(1)
EXPECTED = 13 + 2 + 2 + 2 + 2 + 2 + 2
if PASSED != EXPECTED:
    print(f"{PASSED} checks passed but {EXPECTED} were expected — update EXPECTED "
          "deliberately when adding or removing a check")
    sys.exit(1)
print(f"{PASSED}/{EXPECTED} checks passed")
