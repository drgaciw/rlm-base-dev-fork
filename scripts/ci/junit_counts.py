#!/usr/bin/env python3
"""Count JUnit XML results for CI job summaries (TP-15). Stdlib only.

One implementation for what `prepare-rlm-org.yml` and `flow-matrix.yml` each carried inline.
A missing or empty report is reported as such and never as 0 tests, and malformed XML is an
error, so a broken report cannot read as a green run.

    python scripts/ci/junit_counts.py 'test-results/apex/*.xml'

Prints `tests=N failed=N skipped=N reruns=N files=N`. Exit 0 when at least one report holds at
least one testcase, 1 when no report matches or every matching report is empty, 2 when a
report is not well-formed XML.
"""
import glob
import sys
import xml.etree.ElementTree as ET
from typing import NamedTuple

EXIT_OK, EXIT_NO_RESULTS, EXIT_MALFORMED = 0, 1, 2


class MalformedReport(Exception):
    """A report matched the pattern but is not parseable JUnit XML."""

    def __init__(self, path, reason):
        super().__init__(f"{path}: {reason}")
        self.path = path


class Counts(NamedTuple):
    total: int = 0
    failed: int = 0
    skipped: int = 0
    reruns: int = 0

    def __add__(self, other):
        return Counts(*(a + b for a, b in zip(self, other)))


def junit_counts(path):
    """Counts for one report. A testcase with a failure or error child counts as failed, else
    with a skipped child as skipped. `reruns` counts rerun records (pytest-rerunfailures'
    rerunFailure/rerunError, surefire's rerunFailure/flakyFailure) and is informational: a case
    that failed, was rerun and passed is neither failed nor skipped."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise MalformedReport(path, str(exc)) from exc
    total = failed = skipped = reruns = 0
    for case in root.iter("testcase"):
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failed += 1
        elif case.find("skipped") is not None:
            skipped += 1
        reruns += sum(len(case.findall(tag)) for tag in ("rerunFailure", "rerunError", "flakyFailure", "flakyError"))
    return Counts(total, failed, skipped, reruns)


def aggregate(pattern):
    """(Counts, files matched) over every report matching the glob (recursive)."""
    files = sorted(glob.glob(pattern, recursive=True))
    counts = Counts()
    for f in files:
        counts += junit_counts(f)
    return counts, files


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[0] + "\nusage: junit_counts.py <glob>", file=sys.stderr)
        return EXIT_MALFORMED
    try:
        counts, files = aggregate(argv[0])
    except MalformedReport as exc:
        print(f"::error::malformed JUnit report {exc}", file=sys.stderr)
        return EXIT_MALFORMED
    if not files:
        print(f"::error::no JUnit report matched {argv[0]}", file=sys.stderr)
        print("tests=0 files=0 (no report)")
        return EXIT_NO_RESULTS
    print(f"tests={counts.total} failed={counts.failed} skipped={counts.skipped} "
          f"reruns={counts.reruns} files={len(files)}")
    if counts.total == 0:
        print(f"::error::JUnit report(s) matching {argv[0]} contain no testcases", file=sys.stderr)
        return EXIT_NO_RESULTS
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
