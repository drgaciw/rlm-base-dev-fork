#!/usr/bin/env python3
"""Sync .claude/rules/*.md from .cursor/rules/*.mdc (the source of truth).

Cursor's `globs:` / `alwaysApply:` frontmatter becomes Claude Code's
`paths:` frontmatter (a YAML list); a rule with `alwaysApply: true` gets no
`paths:` key at all, so it applies unconditionally. The rule body is copied
verbatim -- only the frontmatter shape changes.

`analysis-artifacts.mdc` stays Cursor-only (see CURSOR_ONLY below) and is
never generated into `.claude/rules/`.

Usage:
    python scripts/ai/sync_claude_rules.py --check   # exit 1 on drift
    python scripts/ai/sync_claude_rules.py --write   # regenerate in place

Stdlib only -- no PyYAML, no network, no org required.
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CURSOR_RULES_DIRNAME = ".cursor/rules"
CLAUDE_RULES_DIRNAME = ".claude/rules"

# Rules that intentionally have no Claude Code equivalent.
CURSOR_ONLY = {"analysis-artifacts"}


class FrontmatterError(ValueError):
    pass


def split_frontmatter(text):
    """Split a rule file into (frontmatter_lines, body).

    frontmatter_lines excludes the delimiting '---' lines. body is
    everything after the closing '---' line, including its leading
    newline, so `header + body` reconstructs the file layout.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("missing opening '---'")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_lines = lines[1:i]
            body = "\n".join(lines[i + 1:])
            if text.endswith("\n"):
                body += "\n"
            return fm_lines, body
    raise FrontmatterError("missing closing '---'")


def parse_frontmatter(fm_lines):
    """Parse the small frontmatter subset used by .cursor/rules/*.mdc:
    `description: <text>`, `globs: <text>` (single glob) or a `globs:`
    block followed by `  - item` lines (multiple globs), and
    `alwaysApply: true|false` (defaults to false when absent).
    """
    data = {"description": "", "globs": [], "alwaysApply": False}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip():
            i += 1
            continue
        if ":" not in line:
            raise FrontmatterError(f"unrecognized frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "description":
            data["description"] = value
            i += 1
        elif key == "globs":
            if value:
                data["globs"] = [value]
                i += 1
            else:
                items = []
                i += 1
                while i < len(fm_lines) and fm_lines[i].lstrip().startswith("- "):
                    items.append(fm_lines[i].lstrip()[2:].strip())
                    i += 1
                data["globs"] = items
        elif key == "alwaysApply":
            data["alwaysApply"] = value.lower() == "true"
            i += 1
        else:
            raise FrontmatterError(f"unknown frontmatter key: {key!r}")
    return data


def _yaml_needs_quoting(s):
    """True if `s` cannot stand as a bare YAML scalar.

    A-L4 (wave 2): a glob starting with `*` (the YAML alias indicator) or a
    description containing `: ` (the mapping key/value separator) produced
    invalid YAML when emitted unquoted. Conservative on purpose: this only
    quotes shapes that are actually ambiguous or reserved in YAML's plain
    scalar grammar, so every existing rule's frontmatter -- none of which
    hits these cases -- renders byte-identically to before.
    """
    if s == "":
        return True
    if s[0] in "!&*-?|>%@`\"'#[]{},":
        return True
    if s[0] in " \t" or s[-1] in " \t":
        return True
    if ": " in s or s.endswith(":"):
        return True
    if " #" in s or s.startswith("#"):
        return True
    return False


def _yaml_scalar(s):
    """`s` rendered as a valid YAML scalar -- quoted only when it must be.

    Double-quoted YAML scalars follow the same escaping rules as JSON
    strings for every character this repo's rule text actually uses
    (backslash, double quote, control characters), so `json.dumps` is a
    correct, stdlib-only YAML double-quoted-scalar encoder here without
    reimplementing YAML's escaping grammar.
    """
    return json.dumps(s) if _yaml_needs_quoting(s) else s


def render_claude_frontmatter(data):
    lines = ["---", f"description: {_yaml_scalar(data['description'])}"]
    if not data["alwaysApply"]:
        lines.append("paths:")
        for glob in data["globs"]:
            lines.append(f"  - {_yaml_scalar(glob)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def generate_claude_rule(cursor_text):
    """Return the generated .claude/rules/<name>.md content for a given
    .cursor/rules/<name>.mdc source's text."""
    fm_lines, body = split_frontmatter(cursor_text)
    data = parse_frontmatter(fm_lines)
    header = render_claude_frontmatter(data)
    if body.startswith("\n") or not body:
        return header + body
    return header + "\n" + body


def discover_cursor_rules(cursor_dir):
    if not cursor_dir.is_dir():
        return []
    return sorted(p for p in cursor_dir.glob("*.mdc") if p.stem not in CURSOR_ONLY)


def iter_rule_pairs(root):
    cursor_dir = root / CURSOR_RULES_DIRNAME
    claude_dir = root / CLAUDE_RULES_DIRNAME
    for cursor_path in discover_cursor_rules(cursor_dir):
        yield cursor_path, claude_dir / f"{cursor_path.stem}.md"


def check(root):
    """Return (ok, messages) -- ok is False if any generated file is
    missing, stale, or orphaned (no matching .cursor/rules source)."""
    ok = True
    messages = []
    expected_names = set()
    for cursor_path, claude_path in iter_rule_pairs(root):
        expected_names.add(claude_path.name)
        try:
            expected = generate_claude_rule(cursor_path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            ok = False
            messages.append(f"invalid frontmatter: {cursor_path}: {exc}")
            continue
        if not claude_path.exists():
            ok = False
            messages.append(f"missing: {claude_path}")
            continue
        actual = claude_path.read_text(encoding="utf-8")
        if actual != expected:
            ok = False
            messages.append(f"out of sync: {claude_path}")
    claude_dir = root / CLAUDE_RULES_DIRNAME
    if claude_dir.is_dir():
        for extra in sorted(claude_dir.glob("*.md")):
            if extra.name not in expected_names:
                ok = False
                messages.append(f"orphaned (no .cursor/rules source): {extra}")
    return ok, messages


def write(root):
    """Regenerate every .claude/rules/*.md from its .cursor/rules source.
    Returns the list of paths written."""
    claude_dir = root / CLAUDE_RULES_DIRNAME
    claude_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for cursor_path, claude_path in iter_rule_pairs(root):
        content = generate_claude_rule(cursor_path.read_text(encoding="utf-8"))
        # newline="\n": otherwise write_text() translates "\n" to os.linesep on
        # Windows, producing CRLF that diffs against the LF-normalized committed
        # blob even when the content is identical (A-L2).
        claude_path.write_text(content, encoding="utf-8", newline="\n")
        written.append(claude_path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify .claude/rules/ matches .cursor/rules/; exit 1 on drift")
    mode.add_argument("--write", action="store_true", help="regenerate .claude/rules/ from .cursor/rules/")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository root (default: this repo)")
    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.write:
        for path in write(root):
            print(f"wrote {path.relative_to(root)}")
        return 0

    ok, messages = check(root)
    for message in messages:
        print(message)
    if ok:
        print("OK: .claude/rules/ is in sync with .cursor/rules/")
        return 0
    print("FAIL: .claude/rules/ is out of sync with .cursor/rules/ -- run with --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
