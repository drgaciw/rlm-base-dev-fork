"""Offline fixtures for the .cursor/rules -> .claude/rules generator.

Run with Python 3.10+; no org, network, PyYAML, or agent client required:
    python tests/test_sync_claude_rules.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "ai"))
import sync_claude_rules as sync  # noqa: E402


SINGLE_GLOB_RULE = (
    "---\n"
    "description: Example single-glob rule\n"
    "globs: scripts/apex/**/*.apex\n"
    "alwaysApply: false\n"
    "---\n"
    "\n"
    "# Example Rule\n"
    "\n"
    "## DO NOT\n"
    "\n"
    "- Do the thing\n"
)

MULTI_GLOB_RULE = (
    "---\n"
    "description: Example multi-glob rule\n"
    "globs:\n"
    "  - unpackaged/**/*.cls\n"
    "  - force-app/**/*.cls\n"
    "alwaysApply: false\n"
    "---\n"
    "\n"
    "# Multi Rule\n"
)

NO_ALWAYSAPPLY_RULE = (
    "---\n"
    "description: Rule with no alwaysApply key\n"
    "globs:\n"
    "  - robot/**/*.robot\n"
    "---\n"
    "\n"
    "# Robot Rule\n"
)

ALWAYS_APPLY_RULE = (
    "---\n"
    "description: Always-apply rule\n"
    "alwaysApply: true\n"
    "---\n"
    "\n"
    "# Always Rule\n"
)


class SyncClaudeRulesUnit(unittest.TestCase):
    def test_split_frontmatter_roundtrips_body(self):
        fm_lines, body = sync.split_frontmatter(SINGLE_GLOB_RULE)
        self.assertIn("description: Example single-glob rule", fm_lines)
        self.assertTrue(body.startswith("\n# Example Rule"))

    def test_split_frontmatter_requires_delimiters(self):
        with self.assertRaises(sync.FrontmatterError):
            sync.split_frontmatter("no frontmatter here\n")
        with self.assertRaises(sync.FrontmatterError):
            sync.split_frontmatter("---\ndescription: x\n")

    def test_parse_single_glob(self):
        fm_lines, _ = sync.split_frontmatter(SINGLE_GLOB_RULE)
        data = sync.parse_frontmatter(fm_lines)
        self.assertEqual(data["description"], "Example single-glob rule")
        self.assertEqual(data["globs"], ["scripts/apex/**/*.apex"])
        self.assertFalse(data["alwaysApply"])

    def test_parse_multi_glob(self):
        fm_lines, _ = sync.split_frontmatter(MULTI_GLOB_RULE)
        data = sync.parse_frontmatter(fm_lines)
        self.assertEqual(data["globs"], ["unpackaged/**/*.cls", "force-app/**/*.cls"])

    def test_parse_missing_alwaysapply_defaults_false(self):
        fm_lines, _ = sync.split_frontmatter(NO_ALWAYSAPPLY_RULE)
        data = sync.parse_frontmatter(fm_lines)
        self.assertFalse(data["alwaysApply"])
        self.assertEqual(data["globs"], ["robot/**/*.robot"])

    def test_always_apply_true_drops_paths(self):
        generated = sync.generate_claude_rule(ALWAYS_APPLY_RULE)
        self.assertNotIn("paths:", generated)
        self.assertIn("description: Always-apply rule", generated)

    def test_globs_become_paths_yaml_list(self):
        generated = sync.generate_claude_rule(SINGLE_GLOB_RULE)
        self.assertIn("paths:\n  - scripts/apex/**/*.apex\n", generated)
        generated_multi = sync.generate_claude_rule(MULTI_GLOB_RULE)
        self.assertIn(
            "paths:\n  - unpackaged/**/*.cls\n  - force-app/**/*.cls\n",
            generated_multi,
        )

    def test_body_copied_verbatim(self):
        generated = sync.generate_claude_rule(SINGLE_GLOB_RULE)
        self.assertIn("## DO NOT\n\n- Do the thing\n", generated)

    # A-L4 (wave 2): a bare YAML scalar cannot start with "*" (the alias indicator) or
    # contain ": " (the mapping separator) -- both silently produced invalid YAML before.
    def test_glob_starting_with_star_is_quoted(self):
        rule = (
            "---\n"
            "description: Wildcard glob rule\n"
            "globs: *.md\n"
            "alwaysApply: false\n"
            "---\n\n# Rule\n"
        )
        generated = sync.generate_claude_rule(rule)
        self.assertIn('  - "*.md"\n', generated)

    def test_description_with_colon_space_is_quoted(self):
        rule = (
            "---\n"
            "description: Covers: the tricky case\n"
            "alwaysApply: true\n"
            "---\n\n# Rule\n"
        )
        generated = sync.generate_claude_rule(rule)
        self.assertIn('description: "Covers: the tricky case"\n', generated)

    def test_ordinary_description_and_glob_stay_unquoted(self):
        # Byte-stability for every rule this repo actually has today: none of their
        # descriptions or globs hit a quoting case, so the rendered frontmatter must be
        # identical to before this change, not merely equivalent YAML.
        generated = sync.generate_claude_rule(SINGLE_GLOB_RULE)
        self.assertIn("description: Example single-glob rule\n", generated)
        self.assertIn("  - scripts/apex/**/*.apex\n", generated)
        self.assertNotIn('"', generated)

    def test_yaml_scalar_quoting_boundary_cases(self):
        # Directly against the helper, past the two headline cases above: the reserved
        # first-character set, leading/trailing whitespace, an empty string, and a
        # trailing colon (a mapping key with no value) all round-trip through json.dumps
        # rather than emitting an unparsable bare scalar.
        for unsafe in ("*.md", "&anchor", "!tag", "- item", "key: value", "trailing:",
                       "#comment", "", " leading-space", "trailing-space "):
            self.assertTrue(sync._yaml_needs_quoting(unsafe), unsafe)
            self.assertEqual(sync._yaml_scalar(unsafe), json.dumps(unsafe))
        for safe in ("Example rule description", "scripts/apex/**/*.apex", "a-normal-glob"):
            self.assertFalse(sync._yaml_needs_quoting(safe), safe)
            self.assertEqual(sync._yaml_scalar(safe), safe)


class SyncClaudeRulesFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cursor_dir = self.root / ".cursor" / "rules"
        self.cursor_dir.mkdir(parents=True)
        self.claude_dir = self.root / ".claude" / "rules"
        self.write_cursor("apex-scripts.mdc", SINGLE_GLOB_RULE)
        self.write_cursor("apex-classes.mdc", MULTI_GLOB_RULE)
        self.write_cursor("analysis-artifacts.mdc", ALWAYS_APPLY_RULE)

    def write_cursor(self, name, text):
        (self.cursor_dir / name).write_text(text, encoding="utf-8")

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-S", str(REPO / "scripts" / "ai" / "sync_claude_rules.py"),
             "--root", str(self.root), *args],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_write_then_check_are_in_sync(self):
        result = self.cli("--write")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.cli("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_cursor_only_rule_is_not_generated(self):
        self.cli("--write")
        self.assertFalse((self.claude_dir / "analysis-artifacts.md").exists())
        self.assertTrue((self.claude_dir / "apex-scripts.md").exists())
        self.assertTrue((self.claude_dir / "apex-classes.md").exists())

    def test_check_fails_when_generated_file_missing(self):
        self.cli("--write")
        (self.claude_dir / "apex-scripts.md").unlink()
        result = self.cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing", result.stdout)

    def test_check_fails_on_drift(self):
        self.cli("--write")
        target = self.claude_dir / "apex-classes.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nstray edit\n", encoding="utf-8")
        result = self.cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("out of sync", result.stdout)

    def test_check_fails_on_orphaned_generated_file(self):
        self.cli("--write")
        (self.claude_dir / "orphan.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")
        result = self.cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("orphaned", result.stdout)

    def test_check_passes_on_fresh_checkout_with_no_claude_dir(self):
        result = self.cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing", result.stdout)

    def test_invalid_frontmatter_reported_not_raised(self):
        self.write_cursor("broken.mdc", "no frontmatter\n")
        result = self.cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid frontmatter", result.stdout)


class SyncClaudeRulesRepoState(unittest.TestCase):
    """Guards the real repo's .claude/rules/ against drift from .cursor/rules/."""

    def test_repo_rules_are_in_sync(self):
        ok, messages = sync.check(REPO)
        self.assertTrue(ok, "\n".join(messages))


if __name__ == "__main__":
    unittest.main()
