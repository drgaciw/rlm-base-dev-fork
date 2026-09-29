#!/usr/bin/env python3
"""Test-health reporting and quarantine automation (TP-12).

docs/references/test-plan-2026-09.md section 6 (row TP-12) and section 7 (flaky-test policy).
Stdlib only, so it runs in the portable gate tier and on a bare CI runner. Three subcommands:

  check-quarantine   Parse the two quarantine sources into ONE record type, validate them, print
                     ONE merged table (sorted by expires) and fail when an entry has passed its
                     `expires` date.
                       robot/QUARANTINE.md            TP-08's markdown table, read-only; rows get
                                                      layer `robot`.
                       tests/quarantine/registry.json every other layer (python|apex|lwc|flow).
                     Exit 0 = healthy, 1 = at least one expired entry, 2 = a source cannot be
                     read or breaks a rule (unparseable table, unknown/missing key, non-ISO date,
                     window over 14 days, duplicate id). Exit 2 is never "no entries".
                     stdout is clean markdown for the job summary; `::error::` annotations go
                     to stderr.

  report             Aggregate the JUnit and Robot artifacts of the last N nightly / weekly runs
                     into a markdown summary: pass rate, pass-after-rerun (flaky) rate, MTTR,
                     open failures and the merged quarantine table with ages. Always exits 0 when
                     it could write a report; a missing input is stated in the report, never
                     hidden. The failing check is `check-quarantine`, not this.

  zizmor-audit       Weekly, NON-gating drift audit: compare `zizmor --pedantic --no-config`
                     output with the TP-11 count baseline (.github/zizmor-baseline.json) and list
                     what the baseline (and, for findings it does not list, `.zizmor.yml`) hides.
                     A missing baseline is reported, not an error (exit 0); an unreadable one is.

Artifact layout `report` reads (built by .github/workflows/test-health.yml):

  <artifacts>/<run id>/<artifact name>/**     one directory per downloaded artifact
  <runs.json>                                 [{"id", "created_at", "conclusion", "workflow"}]

Definitions used in the report (kept next to the numbers in its output):

  pass rate            tests that passed on the first attempt / executed (skips excluded).
  pass-after-rerun     tests that failed, then passed on the single rerun (test plan section 7.3)
                       / executed. Flaky is never counted as green.
  MTTR                 mean time from a test's first failing run to the next run in which it
                       passed (clean or after a rerun). Resolution is the run cadence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

REPO_ROOT = Path(__file__).resolve().parents[2]
ROBOT_REGISTER = REPO_ROOT / "robot" / "QUARANTINE.md"
JSON_REGISTRY = REPO_ROOT / "tests" / "quarantine" / "registry.json"
ZIZMOR_BASELINE = REPO_ROOT / ".github" / "zizmor-baseline.json"

MAX_QUARANTINE_DAYS = 14  # test plan section 7.4
ROOT_CAUSES = ("timing", "data-dependency", "environment", "product-bug")
JSON_LAYERS = ("python", "apex", "lwc", "flow")
# Column names of robot/QUARANTINE.md (lower-cased, spaces -> underscores) = the JSON keys.
COLUMNS = ("test", "owner", "issue", "root_cause", "added", "expires", "evidence")
JSON_KEYS = COLUMNS + ("layer",)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISSUE_REF = re.compile(r"^(https://\S+|#\d+)$")


class HealthError(Exception):
    """A source cannot be trusted (parse error or rule break). Carries every problem found."""

    def __init__(self, problems):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("; ".join(self.problems))


# ---- quarantine: one record type, two storage formats ------------------------------------


@dataclass(frozen=True)
class Entry:
    test: str
    layer: str
    owner: str
    issue: str
    root_cause: str
    added: date
    expires: date
    evidence: str
    source: str  # display only: the file the entry came from


def _iso(value, where, field):
    if not isinstance(value, str) or not ISO_DATE.match(value):
        raise ValueError(f"{where}: {field} must be an ISO date YYYY-MM-DD, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{where}: {field} is not a real date: {value!r}") from None


def _split_row(line):
    """Cells of one markdown table row; `\\|` is a literal pipe inside a cell."""
    cells = re.split(r"(?<!\\)\|", line.strip())
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return [c.strip().replace("\\|", "|") for c in cells]


def _column_name(cell):
    return re.sub(r"\s+", "_", cell.strip().lower())


def parse_robot_register(text, source="robot/QUARANTINE.md"):
    """Rows of the Robot register as Entries. Raises HealthError on any table it cannot read.

    The header row must be present and name exactly the seven columns; a register whose table
    was renamed or removed is an error, not an empty register.
    """
    lines = text.splitlines()
    header_at = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and tuple(_column_name(c) for c in _split_row(line)) == COLUMNS:
            header_at = i
            break
    if header_at is None:
        raise HealthError(
            f"{source}: no table with the header columns {' | '.join(COLUMNS)} "
            "(the register format changed; update scripts/ai/test_health.py with it)"
        )
    entries, problems = [], []
    for line in lines[header_at + 1:]:
        if not line.lstrip().startswith("|"):
            break
        cells = _split_row(line)
        if cells and all(set(c) <= {"-", ":", " "} for c in cells):
            continue  # the |---|---| separator
        where = f"{source}: row {cells[0] if cells else line!r}"
        if len(cells) != len(COLUMNS):
            problems.append(f"{where}: {len(cells)} cells, expected {len(COLUMNS)}")
            continue
        empty = [c for c, v in zip(COLUMNS, cells) if not v]
        if empty:
            problems.append(f"{where}: empty cell(s): {', '.join(empty)}")
            continue
        row = dict(zip(COLUMNS, cells))
        try:
            entries.append(Entry(layer="robot", source=source,
                                 added=_iso(row["added"], where, "added"),
                                 expires=_iso(row["expires"], where, "expires"),
                                 **{k: row[k] for k in COLUMNS if k not in ("added", "expires")}))
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise HealthError(problems)
    return entries


def parse_json_registry(text, source="tests/quarantine/registry.json"):
    """Entries of the non-Robot registry. Strict: unknown/missing keys and bad dates are errors."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HealthError(f"{source}: not valid JSON: {exc}") from None
    if not isinstance(data, dict) or set(data) != {"entries"} or not isinstance(data["entries"], list):
        raise HealthError(f'{source}: must be an object with exactly one key, "entries" (a list); '
                          'an empty registry is {"entries": []}')
    entries, problems = [], []
    for n, raw in enumerate(data["entries"], 1):
        where = f"{source}: entry {n}" + (f" ({raw.get('test')})" if isinstance(raw, dict) and raw.get("test") else "")
        if not isinstance(raw, dict):
            problems.append(f"{where}: not an object")
            continue
        unknown, missing = sorted(set(raw) - set(JSON_KEYS)), sorted(set(JSON_KEYS) - set(raw))
        if unknown:
            problems.append(f"{where}: unknown key(s): {', '.join(unknown)}")
        if missing:
            problems.append(f"{where}: missing key(s): {', '.join(missing)}")
        if unknown or missing:
            continue
        bad = [k for k in JSON_KEYS if not isinstance(raw[k], str) or not raw[k].strip()]
        if bad:
            problems.append(f"{where}: must be non-empty string(s): {', '.join(bad)}")
            continue
        if raw["layer"] not in JSON_LAYERS:
            problems.append(f"{where}: layer {raw['layer']!r} not in {list(JSON_LAYERS)} "
                            "(Robot tests belong in robot/QUARANTINE.md)")
            continue
        try:
            entries.append(Entry(source=source, added=_iso(raw["added"], where, "added"),
                                 expires=_iso(raw["expires"], where, "expires"),
                                 **{k: raw[k] for k in JSON_KEYS if k not in ("added", "expires")}))
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        raise HealthError(problems)
    return entries


def rule_problems(entries):
    """Rules that apply to every entry of both sources (test plan section 7.4 and 7.5)."""
    problems, seen = [], {}
    for e in entries:
        where = f"{e.source}: {e.test}"
        if e.test in seen:
            problems.append(f"{where}: duplicate id (also in {seen[e.test]})")
        seen.setdefault(e.test, e.source)
        if e.root_cause not in ROOT_CAUSES:
            problems.append(f"{where}: root cause {e.root_cause!r} not in {list(ROOT_CAUSES)}")
        elif e.root_cause == "product-bug":
            problems.append(f"{where}: a product-bug is filed and kept blocking, not quarantined")
        if not ISSUE_REF.match(e.issue):
            problems.append(f"{where}: issue must be an https URL or #N, got {e.issue!r}")
        window = (e.expires - e.added).days
        if not 0 < window <= MAX_QUARANTINE_DAYS:
            problems.append(f"{where}: expires must be 1..{MAX_QUARANTINE_DAYS} days after added, got {window}")
    return problems


def load_quarantine(robot_path=ROBOT_REGISTER, registry_path=JSON_REGISTRY):
    """Both sources merged and validated. Raises HealthError with every problem, all sources."""
    entries, problems = [], []
    for path, parser, label in ((robot_path, parse_robot_register, "robot/QUARANTINE.md"),
                                (registry_path, parse_json_registry, "tests/quarantine/registry.json")):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{label}: cannot read: {exc}")
            continue
        try:
            entries += parser(text, label)
        except HealthError as exc:
            problems += exc.problems
    if not problems:
        problems = rule_problems(entries)
    if problems:
        raise HealthError(problems)
    return sorted(entries, key=lambda e: (e.expires, e.test))


def expired_entries(entries, today):
    """Entries whose `expires` date is before today (an entry is still valid on its expires date)."""
    return [e for e in entries if today > e.expires]


def md_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def quarantine_table(entries, today):
    """The one merged table, expiry-sorted, with age and days left."""
    if not entries:
        return ["_No quarantined tests._"]
    lines = ["| Test | Layer | Owner | Issue | Root cause | Added | Expires | Age (d) | Days left | Status |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for e in entries:
        left = (e.expires - today).days
        status = "**EXPIRED**" if left < 0 else ("expires today" if left == 0 else "ok")
        lines.append("| " + " | ".join(md_cell(v) for v in (
            e.test, e.layer, e.owner, e.issue, e.root_cause, e.added.isoformat(),
            e.expires.isoformat(), (today - e.added).days, left, status)) + " |")
    return lines


# ---- artifact aggregation ----------------------------------------------------------------

SEVERITY = {"skip": 0, "pass": 1, "flaky": 2, "fail": 3}
STAGES = ("apex", "junit", "robot-setup", "robot-e2e", "robot-e2e-quarantine")


@dataclass
class Run:
    run_id: str
    time: datetime | None = None
    conclusion: str = ""
    workflow: str = ""
    results: list = None  # [(stage, test key, status)]

    def __post_init__(self):
        self.results = self.results or []


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def junit_results(root, stage, artifact):
    """[(stage, key, status)] from a JUnit `testsuite(s)` document."""
    out = []
    for case in root.iter("testcase"):
        name = f"{case.get('classname') or ''}.{case.get('name') or ''}".strip(".")
        if case.find("failure") is not None or case.find("error") is not None:
            status = "fail"
        elif case.find("skipped") is not None:
            status = "skip"
        else:
            status = "pass"
        out.append((stage, f"{artifact}::{name}", status))
    return out


def robot_results(root, artifact):
    """[(stage, key, status)] from a Robot output.xml (the setup suites; e2e uses e2e-summary.json)."""
    out = []

    def walk(suite, prefix):
        path = prefix + [suite.get("name") or ""]
        for child in suite:
            if child.tag == "suite":
                walk(child, path)
            elif child.tag == "test":
                stat = child.find("status")
                raw = (stat.get("status") if stat is not None else "") or ""
                status = {"PASS": "pass", "FAIL": "fail", "SKIP": "skip"}.get(raw.upper(), "fail")
                out.append(("robot-setup", f"{artifact}::{'.'.join(path)}.{child.get('name')}", status))

    for suite in root.findall("suite"):
        walk(suite, [])
    return out


def e2e_summary_results(data, stage, key_prefix):
    """[(stage, key, status)] from tasks/rlm_robot_e2e.py's e2e-summary.json."""
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        raise ValueError("no `tests` list")
    return [(stage, f"{key_prefix}::{t['name']}", t["result"]) for t in data["tests"]]


def collect_run(run_dir, run):
    """Fill `run.results` from every artifact under `run_dir`. Returns (ignored, unreadable) paths."""
    ignored, unreadable = [], []
    summaries = {p.parent for p in run_dir.rglob("e2e-summary.json")}
    for path in sorted(p for p in run_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(run_dir)
        artifact = re.sub(r"-\d+$", "", rel.parts[0])  # drop the run id from the artifact name
        try:
            if path.name == "e2e-summary.json":
                stage = "robot-e2e-quarantine" if "e2e-quarantine" in rel.parts else "robot-e2e"
                key = f"{artifact}/{path.parent.name}"
                data = json.loads(path.read_text(encoding="utf-8"))
                run.results += e2e_summary_results(data, stage, key)
            elif path.suffix.lower() == ".xml":
                if any(parent in summaries for parent in path.parents):
                    continue  # first.xml / rerun.xml / merged output.xml: e2e-summary.json is the truth
                root = ET.parse(path).getroot()
                if root.tag in ("testsuite", "testsuites"):
                    stage = "apex" if "apex" in [p.lower() for p in rel.parts] else "junit"
                    run.results += junit_results(root, stage, artifact)
                elif root.tag == "robot":
                    run.results += robot_results(root, artifact)
                else:
                    ignored.append(str(rel))
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
            unreadable.append(f"{rel}: {type(exc).__name__}: {exc}")
    return ignored, unreadable


def load_runs(artifacts_dir, runs_file):
    """-> (runs ordered oldest first, notes). Run metadata comes from `runs_file` when given."""
    meta = {}
    notes = []
    if runs_file is not None:
        try:
            listing = json.loads(Path(runs_file).read_text(encoding="utf-8"))
            meta = {str(r["id"]): r for r in listing}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            notes.append(f"runs file unreadable ({type(exc).__name__}: {exc}); no run times, so no MTTR")
    runs = {}
    root = Path(artifacts_dir)
    if root.is_dir():
        for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            info = meta.get(run_dir.name, {})
            run = Run(run_dir.name, parse_time(info.get("created_at")), info.get("conclusion") or "",
                      info.get("workflow") or "")
            ignored, unreadable = collect_run(run_dir, run)
            notes += [f"run {run.run_id}: unreadable {u}" for u in unreadable]
            if ignored:
                notes.append(f"run {run.run_id}: {len(ignored)} XML file(s) that are neither JUnit nor Robot ignored")
            runs[run.run_id] = run
    for run_id, info in meta.items():
        if run_id not in runs:
            runs[run_id] = Run(run_id, parse_time(info.get("created_at")), info.get("conclusion") or "",
                               info.get("workflow") or "")
    ordered = sorted(runs.values(), key=lambda r: (r.time or datetime.min.replace(tzinfo=timezone.utc),
                                                   int(r.run_id) if r.run_id.isdigit() else 0))
    return ordered, notes


def rate(part, whole):
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def days(td):
    return f"{td.total_seconds() / 86400:.1f} d"


def stage_counts(runs):
    counts = defaultdict(Counter)
    for run in runs:
        for stage, _, status in run.results:
            counts[stage][status] += 1
    return counts


def outages(runs):
    """Per test key: ([(failed_at, recovered_at)], open_since). Ordered runs, worst status per run."""
    series = defaultdict(list)
    for run in runs:
        worst = {}
        for stage, key, status in run.results:
            k = f"{stage}: {key}"
            if SEVERITY[status] >= SEVERITY.get(worst.get(k, "skip"), 0):
                worst[k] = status
        for k, status in worst.items():
            series[k].append((run, status))
    closed, still_open = defaultdict(list), {}
    for k, points in series.items():
        since = None
        for run, status in points:
            if status == "skip":
                continue
            if status == "fail":
                since = since or run
            elif since is not None:
                closed[k].append((since, run))
                since = None
        if since is not None:
            still_open[k] = since
    return closed, still_open


def render_report(runs, notes, entries, quarantine_error, today):
    lines = ["## Test health", ""]
    with_data = [r for r in runs if r.results]
    if runs:
        times = [r.time for r in runs if r.time]
        span = f", {min(times).date()} to {max(times).date()}" if times else ""
        conclusions = Counter(r.conclusion or "unknown" for r in runs)
        lines.append(f"Runs analysed: **{len(runs)}** ({len(with_data)} with test results{span}; "
                     + ", ".join(f"{n} {c}" for c, n in sorted(conclusions.items())) + ").")
    else:
        lines.append("Runs analysed: **0**.")
    if not with_data:
        lines += ["", "**No test results found.** The nightly job may not have run in the window, or its "
                  "artifacts expired (retention is 14 days). This is a report, not a failure."]
    else:
        counts = stage_counts(runs)
        lines += ["", "| Stage | Executed | Pass | Flaky | Fail | Skip | Pass rate | Pass-after-rerun rate |",
                  "|---|---|---|---|---|---|---|---|"]
        total = Counter()
        for stage in [s for s in STAGES if s in counts] + sorted(set(counts) - set(STAGES)):
            c = counts[stage]
            total.update(c)
            ran = c["pass"] + c["flaky"] + c["fail"]
            lines.append(f"| {stage} | {ran} | {c['pass']} | {c['flaky']} | {c['fail']} | {c['skip']} | "
                         f"{rate(c['pass'], ran)} | {rate(c['flaky'], ran)} |")
        ran = total["pass"] + total["flaky"] + total["fail"]
        lines.append(f"| **all** | {ran} | {total['pass']} | {total['flaky']} | {total['fail']} | "
                     f"{total['skip']} | {rate(total['pass'], ran)} | {rate(total['flaky'], ran)} |")
        lines += ["", "_Pass rate counts first-attempt passes only. Pass-after-rerun (flaky) is a test that "
                  "failed and then passed on the single rerun: reported, never green. Skips are excluded. "
                  "Only Robot e2e reruns; the Apex and setup stages do not retry._"]

        flaky = Counter(f"{stage}: {key}" for run in runs for stage, key, status in run.results
                        if status == "flaky")
        if flaky:
            lines += ["", "### Flaky (pass-after-rerun) tests", "", "| Test | Runs flaky |", "|---|---|"]
            lines += [f"| {md_cell(k)} | {n} |" for k, n in flaky.most_common(20)]

        closed, still_open = outages(runs)
        durations = [b.time - a.time for pairs in closed.values() for a, b in pairs if a.time and b.time]
        lines += ["", "### MTTR", ""]
        if durations:
            lines.append(f"Mean time to recovery: **{days(sum(durations, timedelta()) / len(durations))}** "
                         f"(median {days(median(durations))}) over {len(durations)} recovered failure(s); "
                         "resolution is the run cadence.")
        else:
            lines.append("MTTR: **n/a** (no test went from failing to passing within the window, or the "
                         "runs have no timestamps).")
        if still_open:
            last = max((r.time for r in runs if r.time), default=None)
            lines += ["", "Still failing at the end of the window:", "", "| Test | Failing since | Age |", "|---|---|---|"]
            for k, run in sorted(still_open.items(), key=lambda kv: (kv[1].time is None, kv[1].time)):
                since = run.time.date().isoformat() if run.time else f"run {run.run_id}"
                age = days(last - run.time) if last and run.time else "n/a"
                lines.append(f"| {md_cell(k)} | {since} | {age} |")

    lines += ["", "### Quarantine", ""]
    if quarantine_error is not None:
        lines += ["**Quarantine sources are invalid** (`check-quarantine` fails on this):", ""]
        lines += [f"- {p}" for p in quarantine_error.problems]
    else:
        lines += quarantine_table(entries, today)
        expired = expired_entries(entries, today)
        if expired:
            lines += ["", f"**{len(expired)} expired entr{'y' if len(expired) == 1 else 'ies'}:** fix the test "
                      "and delete the row, or re-triage in the issue and renew both dates."]
    if notes:
        lines += ["", "### Data quality", ""] + [f"- {n}" for n in notes]
    return lines


# ---- zizmor drift audit ------------------------------------------------------------------


def _finding_baseline():
    """scripts/lint/finding_baseline.py (TP-11a), imported by path so the two stay one parser."""
    path = REPO_ROOT / "scripts" / "lint" / "finding_baseline.py"
    spec = importlib.util.spec_from_file_location("finding_baseline", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("finding_baseline", module)
    spec.loader.exec_module(module)
    return module


def render_zizmor_audit(findings, baseline_path, version=""):
    """-> markdown lines. `findings` is `finding_baseline.zizmor_findings(...)` output."""
    fb = _finding_baseline()
    found = Counter((rule, file, message) for rule, file, message, _ in findings)
    where = defaultdict(list)
    for rule, file, message, at in findings:
        where[(rule, file, message)].append(at)
    present = Path(baseline_path).is_file()
    allowed, reasons = fb.load_baseline(Path(baseline_path)) if present else (Counter(), {})

    covered = {k: min(n, allowed.get(k, 0)) for k, n in found.items()}
    uncovered = {k: n - covered[k] for k, n in found.items() if n > covered[k]}
    stale = [(k, allowed[k], found.get(k, 0)) for k in sorted(allowed) if found.get(k, 0) < allowed[k]]
    title = "## zizmor drift audit (`--pedantic --no-config`, offline" + (f", zizmor {version}" if version else "") + ")"
    lines = [title, "", "Non-gating. Shows what the PR check cannot: findings the count baseline "
             "(`.github/zizmor-baseline.json`) accepts, and findings it does not list at all, which the "
             "`.zizmor.yml` policy accepts or which appeared since the baseline was written.", ""]
    if not present:
        lines += [f"**Baseline not found** (`{Path(baseline_path).as_posix()}`; TP-11 may not be merged yet): "
                  "all findings are reported as not baselined.", ""]
    lines += [f"- Findings: **{sum(found.values())}** in {len(found)} (rule, file, message) group(s)",
              f"- Accepted by the baseline: **{sum(covered.values())}**",
              f"- Not in the baseline: **{sum(uncovered.values())}**",
              f"- Baseline entries that can shrink: **{len(stale)}**"]

    by_rule = defaultdict(lambda: [0, 0, 0])
    for (rule, _, _), n in found.items():
        by_rule[rule][0] += n
    for (rule, _, _), n in covered.items():
        by_rule[rule][1] += n
    for (rule, _, _), n in uncovered.items():
        by_rule[rule][2] += n
    lines += ["", "| Rule | Findings | Baselined | Not in baseline |", "|---|---|---|---|"]
    lines += [f"| {r} | {a} | {b} | {c} |" for r, (a, b, c) in sorted(by_rule.items())]

    def label(key):
        rule, file, message = key
        return f"`{rule}` in `{file}`" + (f" ({message})" if message else "")

    if uncovered:
        lines += ["", "### Not in the baseline", "", "| Finding | Count | Locations |", "|---|---|---|"]
        for key in sorted(uncovered):
            spots = ", ".join(f"`{w}`" for w in where[key][:5]) + (" ..." if len(where[key]) > 5 else "")
            lines.append(f"| {md_cell(label(key))} | {uncovered[key]} | {md_cell(spots)} |")
    if covered and any(covered.values()):
        lines += ["", "### Accepted by the baseline", "", "| Finding | Count | Reason |", "|---|---|---|"]
        for key in sorted(k for k, n in covered.items() if n):
            lines.append(f"| {md_cell(label(key))} | {covered[key]} | {md_cell(reasons.get(key, ''))} |")
    if stale:
        lines += ["", "### Baseline can shrink", ""]
        lines += [f"- {label(k)}: baseline allows {may}, found {have}" for k, may, have in stale]
    return lines


# ---- CLI ---------------------------------------------------------------------------------


def _utf8_streams():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _today(value):
    return date.fromisoformat(value) if value else datetime.now(timezone.utc).date()


def _print(lines):
    print("\n".join(lines))


def cmd_check_quarantine(args):
    today = _today(args.today)
    try:
        entries = load_quarantine(args.robot, args.registry)
    except HealthError as exc:
        for problem in exc.problems:
            print(f"::error::quarantine: {problem}", file=sys.stderr)
        _print(["## Quarantine check", "", "**Sources invalid** (exit 2):", ""] + [f"- {p}" for p in exc.problems])
        return 2
    expired = expired_entries(entries, today)
    for e in expired:
        print(f"::error::quarantine entry expired {e.expires} (today {today}): {e.test} [{e.layer}], "
              f"owner {e.owner}, {e.issue}", file=sys.stderr)
    _print(["## Quarantine check", ""] + quarantine_table(entries, today)
           + ["", f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, {len(expired)} expired."])
    return 1 if expired else 0


def cmd_report(args):
    today = _today(args.today)
    runs, notes = load_runs(args.artifacts, args.runs)
    try:
        entries, quarantine_error = load_quarantine(args.robot, args.registry), None
    except HealthError as exc:
        entries, quarantine_error = [], exc
    _print(render_report(runs, notes, entries, quarantine_error, today))
    return 0


def cmd_zizmor_audit(args):
    fb = _finding_baseline()
    try:
        data = json.loads(Path(args.findings).read_text(encoding="utf-8"))
        findings = fb.zizmor_findings(data)
        lines = render_zizmor_audit(findings, args.baseline, args.zizmor_version)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"::error::zizmor-audit: {type(exc).__name__}: {exc}", file=sys.stderr)
        _print(["## zizmor drift audit", "", f"**Tool error:** `{type(exc).__name__}: {exc}`"])
        return 2
    _print(lines)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def sources(p):
        p.add_argument("--robot", type=Path, default=ROBOT_REGISTER, help="Robot register (markdown)")
        p.add_argument("--registry", type=Path, default=JSON_REGISTRY, help="non-Robot registry (JSON)")
        p.add_argument("--today", help="ISO date to evaluate against (default: today, UTC)")

    check = sub.add_parser("check-quarantine", help="merge, validate and expiry-check both registers")
    sources(check)
    check.set_defaults(func=cmd_check_quarantine)

    report = sub.add_parser("report", help="markdown summary of downloaded test artifacts")
    sources(report)
    report.add_argument("--artifacts", type=Path, required=True, help="<dir>/<run id>/<artifact>/**")
    report.add_argument("--runs", type=Path, help="runs.json with id, created_at, conclusion, workflow")
    report.set_defaults(func=cmd_report)

    audit = sub.add_parser("zizmor-audit", help="non-gating zizmor drift audit against the count baseline")
    audit.add_argument("--findings", required=True, type=Path, help="`zizmor --format json` output")
    audit.add_argument("--baseline", type=Path, default=ZIZMOR_BASELINE)
    audit.add_argument("--zizmor-version", default="")
    audit.set_defaults(func=cmd_zizmor_audit)

    args = parser.parse_args(argv)
    _utf8_streams()
    try:
        return args.func(args)
    except ValueError as exc:  # a bad --today
        print(f"test_health: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
