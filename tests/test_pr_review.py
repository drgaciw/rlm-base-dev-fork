#!/usr/bin/env python3
"""Unit tests for scripts/ai/pr_review.py (TP-10b).

`pr_review.py` is the mechanical half of the automated-PR-review protocol in AGENTS.md: `status`
lists review threads, `handle` replies + reacts + resolves one, `verify` confirms zero unresolved.
It shells out to the authenticated `gh` CLI, so these tests mock at the subprocess contract level:
`subprocess.run` is replaced by a fake `gh` that records every argv and answers from a scripted
router. Nothing reaches the network, `gh` need not be installed, and every assertion is about the
argv the script *sends* (the contract with `gh`) or the exit code / output it produces from the
replies it *receives*.

Self-contained -- no pytest -- matching the repo's lightweight test convention:

    python tests/test_pr_review.py

Exits 0 when every check passes, 1 otherwise.
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai"))

import pr_review as P  # noqa: E402

RESULTS = []


def _ascii(text):
    """stdout may be cp1252 (Windows, PYTHONUTF8 unset); never let a check name crash the run."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(_ascii(f"  [{'PASS' if condition else 'FAIL'}] {name}"
                 + ("" if condition or detail == "" else f": {detail}")))


# --------------------------------------------------------------------------- fake gh


class FakeGh:
    """A scripted stand-in for `subprocess.run(["gh", ...])`.

    `router(args, input_text)` returns `(returncode, stdout, stderr)` for one call. Every call is
    recorded in `calls` as the argv after `gh`, with its keyword arguments in `kwargs`.
    """

    def __init__(self, router):
        self.router = router
        self.calls = []
        self.kwargs = []

    def __call__(self, cmd, **kwargs):
        if cmd[0] != "gh":
            raise AssertionError(f"pr_review must only shell out to gh, got {cmd[0]!r}")
        args = list(cmd[1:])
        self.calls.append(args)
        self.kwargs.append(kwargs)
        code, stdout, stderr = self.router(args, kwargs.get("input"))
        return subprocess.CompletedProcess(cmd, code, stdout, stderr)

    def matching(self, *needles):
        """Calls whose argv contains every needle as a substring of some argument."""
        return [c for c in self.calls if all(any(n in a for a in c) for n in needles)]


def gh_patch(fake):
    return mock.patch.object(P.subprocess, "run", fake)


def thread(tid, resolved, dbid, author="reviewer", path="a.py", line=3, body="fix it",
           original_line=None):
    comment = {"databaseId": dbid, "author": {"login": author} if author else None,
               "path": path, "line": line, "originalLine": original_line, "body": body}
    return {"id": tid, "isResolved": resolved, "isOutdated": False,
            "comments": {"nodes": [comment]}}


def page(nodes, has_next=False, cursor=None):
    return json.dumps({"data": {"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor}, "nodes": nodes}}}}})


def is_mutation(args):
    return any(a.startswith("query=mutation") for a in args)


def run_captured(fn, *a, **kw):
    """(result, stdout, stderr) of fn(*a, **kw); a SystemExit is returned as the result."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = fn(*a, **kw)
        except SystemExit as exc:
            result = exc
    return result, out.getvalue(), err.getvalue()


def exit_code(result):
    return result.code if isinstance(result, SystemExit) else result


def exit_message(result):
    return str(result.code) if isinstance(result, SystemExit) else None


# --------------------------------------------------------------------------- _run / _json


def test_run_and_json():
    print("\n_run / _json: the gh subprocess contract")
    fake = FakeGh(lambda a, i: (0, '{"x": 1}\n', ""))
    with gh_patch(fake):
        res = P._run(["repo", "view"], input_text="stdin-body")
        data = P._json(["api", "x"])
    check("argv is ['gh', *args] with utf-8 text capture (Windows-safe, no shell)",
          fake.calls[0] == ["repo", "view"]
          and fake.kwargs[0].get("capture_output") is True
          and fake.kwargs[0].get("text") is True
          and fake.kwargs[0].get("encoding") == "utf-8"
          and not fake.kwargs[0].get("shell"))
    check("input_text is forwarded on stdin", fake.kwargs[0].get("input") == "stdin-body")
    check("_run returns the CompletedProcess", res.stdout == '{"x": 1}\n')
    check("_json parses stdout", data == {"x": 1})

    with gh_patch(FakeGh(lambda a, i: (0, "  \n", ""))):
        check("_json of empty stdout is None", P._json(["api", "x"]) is None)

    boom = FakeGh(lambda a, i: (4, "partial-out", "boom-err"))
    with gh_patch(boom):
        result, _, err = run_captured(P._run, ["api", "graphql", "-f", "q=1"])
    check("a failing gh call raises SystemExit naming the command and exit code",
          "`gh api graphql -f q=1` failed (exit 4)" in (exit_message(result) or ""),
          exit_message(result))
    check("the failing call's stdout and stderr are echoed to stderr for diagnosis",
          "partial-out" in err and "boom-err" in err, err)

    with gh_patch(boom):
        res = P._run(["api", "x"], check=False)
    check("check=False hands a failure back instead of raising", res.returncode == 4)


# --------------------------------------------------------------------------- resolve_repo


def test_resolve_repo():
    print("\nresolve_repo")
    fake = FakeGh(lambda a, i: (0, "octo/cat\n", ""))
    with gh_patch(fake):
        check("an explicit owner/name is returned as given and gh is not called",
              P.resolve_repo("octo/dog") == "octo/dog" and fake.calls == [])
        check("no --repo asks gh for the current checkout's nameWithOwner",
              P.resolve_repo(None) == "octo/cat"
              and fake.calls == [["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]])
    for bad in ("nodash", "a/b/c", "/name", "owner/"):
        result, _, _ = run_captured(P.resolve_repo, bad)
        check(f"--repo {bad!r} is rejected as not owner/name",
              "owner/name format" in (exit_message(result) or ""))
    with gh_patch(FakeGh(lambda a, i: (0, "\n", ""))):
        result, _, _ = run_captured(P.resolve_repo, None)
    check("gh returning nothing asks for an explicit --repo",
          "pass --repo owner/name" in (exit_message(result) or ""))


# --------------------------------------------------------------------------- fetch_threads


def test_fetch_threads():
    print("\nfetch_threads: paginated GraphQL read")
    nodes1 = [thread("T1", False, 11)]
    nodes2 = [thread("T2", True, 22)]

    def router(args, _input):
        has_cursor = "cursor=CUR1" in args
        return (0, page(nodes2) if has_cursor else page(nodes1, True, "CUR1"), "")

    fake = FakeGh(router)
    with gh_patch(fake):
        got = P.fetch_threads("octo/cat", 212)
    check("every page is followed and the nodes concatenated in order",
          [t["id"] for t in got] == ["T1", "T2"] and len(fake.calls) == 2)
    first, second = fake.calls
    check("the query is sent as -f query=..., owner/name as -f, and pr as a typed -F int",
          first[:2] == ["api", "graphql"]
          and any(a.startswith("query=") and "reviewThreads" in a for a in first)
          and "owner=octo" in first and "name=cat" in first and "pr=212" in first
          and first[first.index("pr=212") - 1] == "-F")
    check("the first request carries no cursor; the second carries the endCursor",
          not any(a.startswith("cursor=") for a in first) and "cursor=CUR1" in second)

    def abort_message(stdout, stderr="", code=0):
        with gh_patch(FakeGh(lambda a, i: (code, stdout, stderr))):
            result, _, _ = run_captured(P.fetch_threads, "octo/cat", 7)
        return exit_message(result)

    msg = abort_message(json.dumps({"errors": [{"message": "bad token"}, {"message": "rate"}]}))
    check("a GraphQL errors block aborts with every message joined",
          "GraphQL error for PR #7 in octo/cat: bad token; rate" in (msg or ""), msg)
    msg = abort_message(json.dumps({"errors": [{"type": "X"}]}))
    check("an error entry without a message is still reported", "type" in (msg or ""), msg)
    msg = abort_message("<html>502</html>", stderr="gateway")
    check("non-JSON output is treated as unreadable and surfaces stderr",
          "Could not read PR #7 in octo/cat: gateway" in (msg or ""), msg)
    msg = abort_message("", stderr="", code=1)
    check("empty output with no stderr reports 'unknown error'", "unknown error" in (msg or ""), msg)
    msg = abort_message(json.dumps({"data": {"repository": {"pullRequest": None}}}))
    check("a missing PR with no errors block is an unreadable-PR abort, not a KeyError",
          "Could not read PR #7" in (msg or ""), msg)
    msg = abort_message(json.dumps({"data": None}))
    check("a null data block is handled the same way", "Could not read PR" in (msg or ""), msg)


# --------------------------------------------------------------------------- status


def test_status():
    print("\ncmd_status")
    threads = [thread("T1", False, 101, author="greptile", path="x/y.py", line=9, body="nit  here"),
               thread("T2", True, 102, author="human", path="z.py", line=None, original_line=44,
                      body="old")]
    fake = FakeGh(lambda a, i: (0, page(threads), ""))
    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_status, "octo/cat", 5, False)
    check("default lists only unresolved threads and returns 0",
          rc == 0 and "PR #5 (octo/cat): 2 thread(s), 1 unresolved" in out
          and "[OPEN] greptile" in out and "RESOLVED" not in out, out)
    check("a location is path:line and the id is shown", "x/y.py:9" in out and "comment id 101" in out, out)
    check("body whitespace is collapsed", "nit here" in out and "nit  here" not in out, out)
    check("an open thread prints a copy-pasteable handle command with the comment id",
          "python scripts/ai/pr_review.py handle 5 --comment 101" in out, out)
    check("without --repo the suggestion carries no --repo flag", "--repo" not in out, out)

    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_status, "octo/cat", 5, True, "octo/cat")
    check("--all also lists resolved threads, with the originalLine fallback for the location",
          rc == 0 and "[RESOLVED] human" in out and "z.py:44" in out, out)
    check("an explicit --repo is threaded through into the handle suggestion, before the subcommand",
          "pr_review.py --repo octo/cat handle 5 --comment 101" in out, out)
    check("resolved threads get no handle suggestion", out.count("→ resolve") == 1, out)

    long_body = "w " * 200
    with gh_patch(FakeGh(lambda a, i: (0, page([thread("T", False, 1, body=long_body)]), ""))):
        _, out, _ = run_captured(P.cmd_status, "octo/cat", 5, False)
    snippet = [ln for ln in out.splitlines() if ln.startswith("  w")]
    check("a long body is cut to 160 chars plus an ellipsis",
          len(snippet) == 1 and snippet[0].endswith("…") and len(snippet[0].strip()) == 161, out)

    empty = FakeGh(lambda a, i: (0, page([]), ""))
    with gh_patch(empty):
        rc, out, _ = run_captured(P.cmd_status, "octo/cat", 5, False)
        rc_all, out_all, _ = run_captured(P.cmd_status, "octo/cat", 5, True)
    check("no threads at all reads 'nothing to handle'", rc == 0 and "nothing to handle" in out, out)
    check("no threads with --all reads '(no threads)'", rc_all == 0 and "(no threads)" in out_all, out_all)

    weird = {"id": "TW", "isResolved": False, "isOutdated": False, "comments": {"nodes": []}}
    with gh_patch(FakeGh(lambda a, i: (0, page([weird]), ""))):
        rc, out, _ = run_captured(P.cmd_status, "octo/cat", 5, False)
    check("a thread with no comments does not crash: placeholders for author and location",
          rc == 0 and "? — ?:?" in out, out)
    anon = thread("TA", False, 9, author=None)
    with gh_patch(FakeGh(lambda a, i: (0, page([anon]), ""))):
        rc, out, _ = run_captured(P.cmd_status, "octo/cat", 5, False)
    check("a deleted-user (null) author renders as '?'", rc == 0 and "[OPEN] ? —" in out, out)


# --------------------------------------------------------------------------- verify


def test_verify():
    print("\ncmd_verify")
    clean = FakeGh(lambda a, i: (0, page([thread("T", True, 1)]), ""))
    with gh_patch(clean):
        rc, out, _ = run_captured(P.cmd_verify, "octo/cat", 8)
    check("all resolved -> exit 0 and the success line", rc == 0 and "0 unresolved" in out, out)

    dirty = FakeGh(lambda a, i: (0, page([thread("T1", True, 1),
                                          thread("T2", False, 2, author="bot", path="q.py", line=7)]), ""))
    with gh_patch(dirty):
        rc, out, _ = run_captured(P.cmd_verify, "octo/cat", 8)
    check("an unresolved thread -> exit 1 and it is named with location and comment id",
          rc == 1 and "OPEN: bot — q.py:7 (comment id 2)" in out and "NOT clean" in out, out)

    def two_pages(args, _input):
        if "cursor=C" in args:
            return (0, page([thread("T2", False, 2)]), "")
        return (0, page([thread("T1", True, 1)], True, "C"), "")

    with gh_patch(FakeGh(two_pages)):
        rc, _, _ = run_captured(P.cmd_verify, "octo/cat", 8)
    check("verify reads every page: an unresolved thread on page 2 still fails", rc == 1)


# --------------------------------------------------------------------------- handle


def handle_router(threads, reaction_rc=0, resolve_ok=True, reply_rc=0):
    def router(args, _input):
        joined = " ".join(args)
        if "replies" in joined:
            return (reply_rc, "{}", "reply-err" if reply_rc else "")
        if "reactions" in joined:
            return (reaction_rc, "{}", "no-scope" if reaction_rc else "")
        if is_mutation(args):
            return (0, json.dumps({"data": {"resolveReviewThread": {"thread": {
                "isResolved": resolve_ok}}}}), "")
        return (0, page(threads), "")
    return router


def test_handle():
    print("\ncmd_handle: reply + reaction + resolve")
    threads = [thread("THREAD-A", False, 3369933169), thread("THREAD-B", False, 5)]
    fake = FakeGh(handle_router(threads))
    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_handle, "octo/cat", 212, "3369933169", "Fixed in abc1234", True)
    check("happy path returns 0 and reports each step", rc == 0 and "replied in-thread" in out
          and "reaction added" in out and "thread resolved" in out, out)
    reply = fake.matching("replies")
    check("the reply is a POST to /pulls/{pr}/comments/{id}/replies with the body as -f body=",
          len(reply) == 1
          and reply[0][:3] == ["api", "--method", "POST"]
          and "repos/octo/cat/pulls/212/comments/3369933169/replies" in reply[0]
          and "body=Fixed in abc1234" in reply[0], reply)
    react = fake.matching("reactions")
    check("the reaction is a +1 POST to the comment with the GA Accept header",
          len(react) == 1
          and "repos/octo/cat/pulls/comments/3369933169/reactions" in react[0]
          and "content=+1" in react[0]
          and "Accept: application/vnd.github+json" in react[0], react)
    mutation = [c for c in fake.calls if is_mutation(c)]
    check("the mutation resolves the thread whose FIRST comment is the cited id (string id coerced)",
          len(mutation) == 1 and "tid=THREAD-A" in mutation[0]
          and "THREAD-B" not in " ".join(mutation[0]), mutation)
    kinds = ["reply" if "replies" in " ".join(c) else "react" if "reactions" in " ".join(c)
             else "resolve" if is_mutation(c) else "lookup" for c in fake.calls]
    check("order is reply, reaction, thread lookup, resolve -- resolve is last",
          kinds == ["reply", "react", "lookup", "resolve"], kinds)

    fake = FakeGh(handle_router(threads))
    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_handle, "octo/cat", 212, 3369933169, "refuted", False)
    check("--no-react (react=False) skips the reaction call entirely",
          rc == 0 and fake.matching("reactions") == [] and "reaction" not in out, out)

    fake = FakeGh(handle_router(threads, reaction_rc=1))
    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_handle, "octo/cat", 212, 3369933169, "ok", True)
    check("a failed reaction warns but STILL resolves the thread (never the half-finished state)",
          rc == 0 and "reaction failed (continuing to resolve): no-scope" in out
          and "thread resolved" in out and len([c for c in fake.calls if is_mutation(c)]) == 1, out)

    fake = FakeGh(handle_router(threads))
    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_handle, "octo/cat", 212, 999, "ok", True)
    check("a comment id that heads no thread (a reply id / wrong PR) returns 1 and resolves nothing",
          rc == 1 and "no thread found whose first comment is 999" in out
          and not [c for c in fake.calls if is_mutation(c)], out)

    fake = FakeGh(handle_router([thread("THREAD-A", True, 3369933169)]))
    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_handle, "octo/cat", 212, 3369933169, "ok", True)
    check("an already-resolved thread is a success and is not resolved again",
          rc == 0 and "already resolved" in out and not [c for c in fake.calls if is_mutation(c)], out)

    fake = FakeGh(handle_router(threads, resolve_ok=False))
    with gh_patch(fake):
        rc, out, _ = run_captured(P.cmd_handle, "octo/cat", 212, 3369933169, "ok", True)
    check("the API answering isResolved=false is reported and returns 1",
          rc == 1 and "isResolved=false" in out, out)

    fake = FakeGh(handle_router(threads, reply_rc=1))
    with gh_patch(fake):
        result, _, err = run_captured(P.cmd_handle, "octo/cat", 212, 3369933169, "ok", True)
    check("a failed reply aborts before any reaction or resolve",
          isinstance(result, SystemExit) and fake.matching("reactions") == []
          and not [c for c in fake.calls if is_mutation(c)] and "reply-err" in err)


# --------------------------------------------------------------------------- main


def run_main(argv, router=None, stdin=None):
    router = router or (lambda a, i: (0, page([]), ""))
    fake = FakeGh(router)
    with contextlib.ExitStack() as stack:
        stack.enter_context(gh_patch(fake))
        stack.enter_context(mock.patch.object(sys, "argv", ["pr_review.py", *argv]))
        if stdin is not None:
            stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(stdin)))
        result, out, err = run_captured(P.main)
    return result, out, err, fake


def test_main():
    print("\nmain(): argument wiring and exit codes")
    result, out, _, fake = run_main(["--repo", "octo/cat", "status", "3"])
    check("status exits 0 through sys.exit", exit_code(result) == 0 and "PR #3 (octo/cat)" in out, out)

    result, _, _, _ = run_main(["--repo", "octo/cat", "verify", "3"],
                               lambda a, i: (0, page([thread("T", False, 1)]), ""))
    check("verify exits 1 when a thread is open", exit_code(result) == 1)

    result, out, _, fake = run_main(["status", "3", "--all"], lambda a, i: (
        (0, "octo/cat\n", "") if a[0] == "repo" else (0, page([]), "")))
    check("no --repo resolves the repo from gh, then runs the subcommand",
          exit_code(result) == 0 and fake.calls[0][0] == "repo" and "(octo/cat)" in out, out)

    ok_router = handle_router([thread("TT", False, 77)])
    result, _, _, fake = run_main(["--repo", "octo/cat", "handle", "4", "--comment", "77",
                                   "--body", "done in deadbee"], ok_router)
    check("handle --body replies, reacts and resolves (exit 0)",
          exit_code(result) == 0 and "body=done in deadbee" in fake.matching("replies")[0])

    result, _, _, fake = run_main(["--repo", "octo/cat", "handle", "4", "--comment", "77",
                                   "--body", "no", "--no-react"], ok_router)
    check("--no-react reaches cmd_handle", exit_code(result) == 0 and fake.matching("reactions") == [])

    with tempfile.TemporaryDirectory() as tmp:
        body_file = Path(tmp) / "reply.md"
        body_file.write_text("from file — ✅\n", encoding="utf-8", newline="\n")
        result, _, _, fake = run_main(["--repo", "octo/cat", "handle", "4", "--comment", "77",
                                       "--body-file", str(body_file)], ok_router)
    check("--body-file is read as UTF-8 (non-ASCII survives)",
          exit_code(result) == 0 and "body=from file — ✅\n" in fake.matching("replies")[0])

    result, _, _, fake = run_main(["--repo", "octo/cat", "handle", "4", "--comment", "77",
                                   "--body-file", "-"], ok_router, stdin="from stdin")
    check("--body-file - reads the reply from stdin",
          exit_code(result) == 0 and "body=from stdin" in fake.matching("replies")[0])

    for label, extra in (("no body", []), ("a blank body", ["--body", "   "])):
        result, _, _, fake = run_main(["--repo", "octo/cat", "handle", "4", "--comment", "77", *extra],
                                      ok_router)
        check(f"handle with {label} is refused before calling gh",
              "handle requires --body or --body-file" in (exit_message(result) or "")
              and fake.calls == [])

    for label, argv in (("no subcommand", []), ("handle without --comment", ["handle", "4", "--body", "x"]),
                        ("a non-integer PR", ["status", "abc"])):
        result, _, err, _ = run_main(["--repo", "octo/cat", *argv])
        check(f"{label} is an argparse usage error (exit 2)", exit_code(result) == 2, err)

    result, _, _, _ = run_main(["--repo", "bogus", "status", "1"])
    check("a malformed --repo is rejected before any gh call",
          "owner/name format" in (exit_message(result) or ""))


def main():
    test_run_and_json()
    test_resolve_repo()
    test_fetch_threads()
    test_status()
    test_verify()
    test_handle()
    test_main()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
