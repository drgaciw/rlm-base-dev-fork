#!/usr/bin/env python3
"""Count-based baseline for a linter that reports findings this repo cannot fix all at once (TP-11a).

A baseline that lists *locations* (`file:line:col`) goes stale the moment an unrelated PR shifts a
line, and one that ignores a *rule* in a *file* hides the next finding of that rule there. This one
stores how many findings each (rule, file, message) triple is allowed to have and nothing about where:

  * more findings than the baseline allows, or a triple it does not list -> exit 1 (a regression);
  * fewer than allowed -> exit 0 with a warning to shrink the baseline (never a failure, so a PR that
    fixes something is not punished for it);
  * an unreadable input or baseline -> exit 2, a tool error, which is not a verdict.

A finding is `(rule, file, message, where)`:

  rule     the linter's rule id.
  file     repo-relative path with forward slashes.
  message  the finding's text with locations (line/column) and absolute paths stripped by the
           parser, so it is stable when unrelated lines move. May be empty; then only (rule, file)
           is counted. This is part of the key.
  where    display-only (`path:line`), printed under a regression so the new finding can be found.
           Never compared.

A parser is `parser(json_document) -> [(rule, file, message, where)]`, takes only the parsed
document (it reads anything else it needs, such as a run directory to relativize absolute paths,
from the document itself) and is registered in `FORMATS`. Two are built in (`--format`):

  pairs    JSON `[["rule", "path"(, "message"(, "where"))], ...]`.
  zizmor   the output of `zizmor --format json`; findings suppressed by an inline comment are
           skipped, message is zizmor's rule description, where is `path:line`.

Baseline file (`--baseline`), sorted, one entry per triple; `message` is omitted when empty and
`reason` is free text for humans:

  {"description": "...", "entries": [{"rule": "r", "file": "f", "message": "m", "count": 1,
                                       "reason": "..."}]}

Usage:
  zizmor --pedantic --offline --no-exit-codes --format json .github/workflows > findings.json
  python scripts/lint/finding_baseline.py --baseline .github/zizmor-baseline.json \\
      --format zizmor findings.json
  python scripts/lint/finding_baseline.py --baseline ... --format zizmor --write findings.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

Key = tuple  # (rule, file, message)


def normalise_path(path: str) -> str:
    """Repo-relative, forward slashes, so a Windows and a Linux run agree."""
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def pairs_findings(data) -> list[tuple[str, str, str, str]]:
    """`[[rule, file(, message(, where))], ...]` -> [(rule, file, message, where)]."""
    if not isinstance(data, list):
        raise ValueError("pairs input must be a JSON list")
    out = []
    for row in data:
        if not isinstance(row, (list, tuple)) or not 2 <= len(row) <= 4:
            raise ValueError(f"pairs input row is not [rule, file(, message(, where))]: {row!r}")
        rule, file, message, where = (str(x) for x in (*row, "", "")[:4])
        out.append((rule, normalise_path(file), message, where))
    return out


def zizmor_findings(data) -> list[tuple[str, str, str, str]]:
    """`zizmor --format json` -> [(rule, file, message, where)], skipping comment-suppressed ones."""
    if not isinstance(data, list):
        raise ValueError("zizmor JSON output must be a list of findings")
    out = []
    for finding in data:
        if finding.get("ignored"):
            continue
        locations = finding.get("locations") or []
        primary = next((loc for loc in locations
                        if (loc.get("symbolic") or {}).get("kind") == "Primary"), None)
        primary = primary or (locations[0] if locations else None)
        if primary is None:
            raise ValueError(f"zizmor finding has no location: {finding.get('ident')!r}")
        key = (primary.get("symbolic") or {}).get("key") or {}
        path = (key.get("Local") or {}).get("verbatim_path")
        if not path:
            raise ValueError(f"zizmor finding has no local path: {finding.get('ident')!r}")
        path = normalise_path(path)
        row = ((primary.get("concrete") or {}).get("location") or {}).get("start_point", {}).get("row")
        out.append((finding["ident"], path, str(finding.get("desc", "")),
                    f"{path}:{row + 1}" if row is not None else path))
    return out


FORMATS = {"pairs": pairs_findings, "zizmor": zizmor_findings}


def load_baseline(path: Path) -> tuple[Counter, dict]:
    """-> (allowed counts per (rule, file, message), reasons per key)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    allowed: Counter = Counter()
    reasons: dict = {}
    for entry in data.get("entries", []):
        key = (entry["rule"], normalise_path(entry["file"]), entry.get("message", ""))
        if key in allowed:
            raise ValueError(f"baseline lists {key} twice")
        if not isinstance(entry["count"], int) or entry["count"] < 1:
            raise ValueError(f"baseline count for {key} must be an integer >= 1")
        allowed[key] = entry["count"]
        reasons[key] = entry.get("reason", "")
    return allowed, reasons


def compare(found: Counter, allowed: Counter):
    """-> (regressions, improvements), each a sorted list of (key, allowed, found)."""
    regressions, improvements = [], []
    for key in sorted(set(found) | set(allowed)):
        have, may = found.get(key, 0), allowed.get(key, 0)
        if have > may:
            regressions.append((key, may, have))
        elif have < may:
            improvements.append((key, may, have))
    return regressions, improvements


def render_baseline(found: Counter, reasons: dict, description: str) -> str:
    entries = []
    for key, count in sorted(found.items()):
        rule, file, message = key
        entry = {"rule": rule, "file": file}
        if message:
            entry["message"] = message
        entry.update(count=count, reason=reasons.get(key, ""))
        entries.append(entry)
    return json.dumps({"description": description, "entries": entries}, indent=2) + "\n"


def _label(key) -> str:
    rule, file, message = key
    return f"{rule} in {file}" + (f" ({message})" if message else "")


def _summary(lines: list[str]) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target and lines:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="findings file, or - for stdin")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--format", choices=sorted(FORMATS), default="pairs")
    parser.add_argument("--write", action="store_true",
                        help="rewrite the baseline from the findings (keeps existing reasons)")
    parser.add_argument("--name", default="finding", help="what the findings are, for messages")
    args = parser.parse_args(argv)

    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        findings = FORMATS[args.format](json.loads(raw))
        found: Counter = Counter((rule, file, message) for rule, file, message, _ in findings)
        if args.write:
            reasons = load_baseline(args.baseline)[1] if args.baseline.exists() else {}
            args.baseline.write_text(
                render_baseline(found, reasons,
                                f"Allowed {args.name} counts per (rule, file, message)."),
                encoding="utf-8", newline="\n")
            print(f"Wrote {sum(found.values())} {args.name}(s) in {len(found)} entries to {args.baseline}")
            return 0
        allowed, _ = load_baseline(args.baseline)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"finding_baseline: tool error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    regressions, improvements = compare(found, allowed)
    where = defaultdict(list)
    for rule, file, message, at in findings:
        if at:
            where[(rule, file, message)].append(at)

    for key, may, have in regressions:
        print(f"::error::{args.name} regression: {_label(key)}: {have} found, baseline allows {may}")
        for at in where[key]:
            print(f"    {at}")
    for key, may, have in improvements:
        print(f"::warning::{args.name} baseline can shrink: {_label(key)}: {have} found, "
              f"baseline allows {may} - update {args.baseline} (--write)")

    baselined = sum(min(found.get(key, 0), n) for key, n in allowed.items())
    total = sum(found.values())
    print(f"{total} {args.name}(s): {baselined} baselined, {total - baselined} new, "
          f"{len(improvements)} baseline entr{'y' if len(improvements) == 1 else 'ies'} can shrink")
    _summary(
        [f"### {args.name} baseline: {total} found, {baselined} baselined, {total - baselined} new"]
        + [f"- shrink the baseline: {_label(key)} now {have}, allowed {may}"
           for key, may, have in improvements])
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
