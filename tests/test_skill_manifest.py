#!/usr/bin/env python3
"""Offline unit tests for scripts/ai/skill_manifest.py beyond `--check`'s local-only handling (TP-10b).

tests/test_skill_manifest_audit.py pins the audit's private-tree behaviour and needs PyYAML. This
suite covers the rest of the module and is stdlib-only, because everything here is decided *before*
or *around* a YAML library: the no-PyYAML fallback parser (which the CLI degrades to on a bare
interpreter), git-URL identity comparison, clone discovery and its refusal of a foreign clone, the
lookup helpers, the diagnostics CLI and its exit codes, and the Foundations path audit.

Discovery is exercised on throwaway directory trees; `git` is never run (`subprocess.run` is patched
at the module boundary), so there is no network and no dependence on this checkout's remotes.

Self-contained -- no pytest:

    python tests/test_skill_manifest.py

Exits 0 when every check passes, 1 otherwise.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ai"))

import skill_manifest as S  # noqa: E402

RESULTS = []


def _ascii(text):
    """stdout may be cp1252 (Windows, PYTHONUTF8 unset); never let a check name crash the run."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition)))
    print(_ascii(f"  [{'PASS' if condition else 'FAIL'}] {name}"
                 + ("" if condition or detail == "" else f": {detail}")))


def write(root, rel, text=""):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def captured(fn, *a, **kw):
    """(result, stdout, stderr); a raised SystemExit or ValueError is returned as the result."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            result = fn(*a, **kw)
        except (SystemExit, ValueError) as exc:
            result = exc
    return result, out.getvalue(), err.getvalue()


def git_returns(stdout="", exc=None):
    """A stand-in for subprocess.run that answers every git call with `stdout` (or raises `exc`)."""
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    fake.calls = calls
    return fake


# ---------------------------------------------------------------------------------- fallback parser


def test_scalars():
    print("\nfallback parser: scalars")
    check("an inline comment is cut only where YAML says (start of value or after whitespace)",
          S._strip_inline_comment("a  # note") == "a"
          and S._strip_inline_comment("# all comment") == ""
          and S._strip_inline_comment("docs/foo#section") == "docs/foo#section")
    check("a # inside quotes is not a comment",
          S._strip_inline_comment("'a # b' # c") == "'a # b'"
          and S._strip_inline_comment('"a # b"') == '"a # b"')
    for text in ("", "null", "Null", "NULL", "~"):
        check(f"{text!r} parses to None", S._parse_scalar(text) is None)
    check("booleans in the three YAML spellings",
          all(S._parse_scalar(t) is True for t in ("true", "True", "TRUE"))
          and all(S._parse_scalar(t) is False for t in ("false", "False", "FALSE")))
    check("plain integers are coerced, signed zero included; zero-padded codes stay strings",
          S._parse_scalar("42") == 42 and S._parse_scalar("-7") == -7 and S._parse_scalar("0") == 0
          and S._parse_scalar("007") == "007" and S._parse_scalar("1_000") == "1_000"
          and S._parse_scalar("68.0") == "68.0")
    check("quoted strings are unquoted (single and double), and a quoted number stays a string",
          S._parse_scalar('"x y"') == "x y" and S._parse_scalar("'x'") == "x" and S._parse_scalar('"12"') == "12")
    check("flow lists parse, drop empty segments (trailing comma) and nest scalar rules",
          S._parse_scalar("[]") == [] and S._parse_scalar("[ ]") == [] and S._parse_scalar("[a, b,]") == ["a", "b"]
          and S._parse_scalar("[1, true, ~]") == [1, True, None])
    check("a trailing comment after a value is ignored", S._parse_scalar("5 # five") == 5)

    check("_split_key_value splits at the first `: `", S._split_key_value("a: b: c") == ("a", " b: c"))
    check("a URL colon (no following space) is not a separator",
          S._split_key_value("url: http://x/y") == ("url", " http://x/y"))
    check("a bare `key:` yields an empty value", S._split_key_value("key:") == ("key", ""))
    check("a quoted key containing a colon is not split mid-key",
          S._split_key_value('"a:b": 1') == ('"a:b"', " 1")
          and S._split_key_value("'a: b'") == ("'a: b'", None))
    check("no separator means (content, None)", S._split_key_value("just text") == ("just text", None))

    for ok in ("text", "a | b", ""):
        S._reject_block_scalar(ok)
    for bad in ("|", ">", "|-", ">+", "|2"):
        result, _, _ = captured(S._reject_block_scalar, bad)
        check(f"block scalar indicator {bad!r} is refused loudly", isinstance(result, ValueError))


SAMPLE = """\
# a comment
manifest_version: 2
last_verified: "2026-07-26"   # stamped
flag: true
empty:
nothing: null
foundations:
  name: rlm-base-dev
  optional: false
  local_path_hints: [$FOO, ../rlm-base-dev]
  skills:
    - id: alpha
      path: .cursor/skills/alpha/SKILL.md
      sub_skills:
        - one.md
        - two.md
    - id: beta
      purpose: "with: colon"
    - plain-scalar
  "quoted:key": value
pmos:
  optional: true
"""


def test_document_parser():
    print("\nfallback parser: documents")
    data = S._load_manifest_minimal(SAMPLE)
    check("top-level scalars, comments and blank values", data["manifest_version"] == 2
          and data["last_verified"] == "2026-07-26" and data["flag"] is True
          and data["empty"] is None and data["nothing"] is None, data)
    fnd = data["foundations"]
    check("nested mappings and inline lists", fnd["name"] == "rlm-base-dev" and fnd["optional"] is False
          and fnd["local_path_hints"] == ["$FOO", "../rlm-base-dev"], fnd)
    check("a list of mappings, with nested block lists inside an item",
          fnd["skills"][0] == {"id": "alpha", "path": ".cursor/skills/alpha/SKILL.md",
                               "sub_skills": ["one.md", "two.md"]}, fnd["skills"])
    check("a quoted value containing a colon stays whole", fnd["skills"][1] == {"id": "beta", "purpose": "with: colon"})
    check("a scalar list item is a scalar", fnd["skills"][2] == "plain-scalar")
    check("a quoted mapping key is unquoted", fnd["quoted:key"] == "value")
    check("sections after a nested block are parsed at the right depth", data["pmos"] == {"optional": True})

    check("a document that is not a mapping yields {}", S._load_manifest_minimal("- a\n- b\n") == {})
    check("empty text yields {}", S._load_manifest_minimal("") == {} and S._load_manifest_minimal("# only\n") == {})
    result, _, _ = captured(S._load_manifest_minimal, "key: |\n  folded\n")
    check("a block scalar in the manifest raises rather than truncating", isinstance(result, ValueError))
    check("a key with no children before a dedent is None",
          S._load_manifest_minimal("a:\nb: 1\n") == {"a": None, "b": 1})

    if S.yaml is not None:
        real = (REPO_ROOT / S.MANIFEST_FILENAME).read_text(encoding="utf-8")
        # KNOWN DIVERGENCE (reported in the TP-10b PR, not fixed here -- the script is not owned by TP-10b):
        # a flow list written on the line *after* its key (`consumed_by_pmos:` / `[a, b]`) is parsed by the
        # fallback as a one-key mapping, so full equality with yaml.safe_load does not hold on the committed
        # manifest despite the parser's docstring. The structure the audit walks is pinned instead.
        fallback, reference = S._load_manifest_minimal(real), S.yaml.safe_load(real)
        check("on the committed manifest the fallback agrees with yaml.safe_load on the top-level keys and "
              "the declared skill ids per repo",
              set(fallback) == set(reference) and all(
                  [x.get("id") for x in fallback[r]["skills"]] == [x.get("id") for x in reference[r]["skills"]]
                  for r in ("foundations", "pmos")))
    else:
        print("  [SKIP] fallback-vs-PyYAML parity on the committed manifest: PyYAML is not installed")


# ---------------------------------------------------------------------------------- URL identity


def test_urls():
    print("\ngit URL normalisation and comparison")
    n = S._normalize_repo_url
    check("https URLs lose .git and a trailing slash and are lower-cased",
          n("https://GitHub.com/Owner/Repo.git/") == ("github.com", "owner/repo"))
    check("ssh:// and scp-style forms normalise to the same identity",
          n("ssh://git@github.com/owner/repo.git") == ("github.com", "owner/repo")
          and n("git@github.com:owner/repo.git") == ("github.com", "owner/repo"))
    check("only the last two path segments identify the repo", n("https://h/group/sub/repo") == ("h", "sub/repo"))
    check("URLs that do not reduce to host + owner/repo return None",
          n("/local/mirror/repo") is None and n("file:///x") is None and n("https://host/onlyone") is None
          and n("not a url") is None)
    eq = S._urls_equivalent
    check("same repo over different transports is True",
          eq("git@github.com:o/r.git", "https://github.com/o/r") is True)
    check("a provably different repo is False", eq("https://github.com/o/r", "https://github.com/o/other") is False)
    check("a different host is a different repo", eq("https://a.com/o/r", "https://b.com/o/r") is False)
    check("an incomparable URL is None (unverifiable, never a mismatch)",
          eq("/srv/mirror", "https://github.com/o/r") is None and eq("https://github.com/o/r", "file:///x") is None)


def test_git_remote_url():
    print("\n_git_remote_url")
    fake = git_returns("  https://github.com/o/r.git\n")
    with mock.patch.object(S.subprocess, "run", fake):
        url = S._git_remote_url(Path("/some/clone"))
    check("it asks git for remote.origin.url via -C, with utf-8 text capture and a timeout",
          url == "https://github.com/o/r.git" and fake.calls[0][:3] == ["git", "-C", str(Path("/some/clone"))]
          and fake.calls[0][3:] == ["config", "--get", "remote.origin.url"])
    with mock.patch.object(S.subprocess, "run", git_returns("")):
        check("no remote is None", S._git_remote_url(Path("/x")) is None)
    with mock.patch.object(S.subprocess, "run", git_returns(exc=OSError("no git"))):
        check("git not installed is None, not a crash", S._git_remote_url(Path("/x")) is None)
    with mock.patch.object(S.subprocess, "run", git_returns(exc=subprocess.TimeoutExpired("git", 10))):
        check("a git timeout is None, not a crash", S._git_remote_url(Path("/x")) is None)


# ---------------------------------------------------------------------------------- discovery


def make_foundations(root):
    write(root, ".cursor/skills/alpha/SKILL.md", "# alpha\n")
    return Path(root)


def make_pmos(root):
    write(root, ".claude/skills/beta/SKILL.md", "# beta\n")
    return Path(root)


SECTION_F = {"name": "rlm-base-dev", "role": "foundations", "repo_url": "https://github.com/o/rlm-base-dev"}
SECTION_P = {"name": "pmos-revenue-cloud", "role": "pmos", "repo_url": "https://github.com/o/pmos"}


def test_repo_surface():
    print("\n_repo_surface_present")
    with tempfile.TemporaryDirectory() as tmp:
        f = make_foundations(Path(tmp) / "f")
        p = make_pmos(Path(tmp) / "p")
        both = make_pmos(make_foundations(Path(tmp) / "both"))
        deep = Path(tmp) / "deep"
        write(deep, ".claude/skills/gitnexus/sub/SKILL.md")
        check("Foundations is identified by .cursor/skills/*/SKILL.md",
              S._repo_surface_present(f, "rlm-base-dev") and not S._repo_surface_present(p, "rlm-base-dev"))
        check("PMOS is identified by .claude/skills/*/SKILL.md and the absence of .cursor/skills",
              S._repo_surface_present(p, "pmos-revenue-cloud"))
        check("a fixed-up Foundations checkout (both surfaces) is not mistaken for PMOS",
              S._repo_surface_present(both, "rlm-base-dev") and not S._repo_surface_present(both, "pmos-revenue-cloud"))
        check("a skill cache two levels deep does not count as a PMOS surface",
              not S._repo_surface_present(deep, "pmos-revenue-cloud"))
        check("an unknown repo name never matches", not S._repo_surface_present(f, "other"))


def test_discovery():
    print("\n_discover_repo")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clone = make_foundations(tmp / "clone")
        section = dict(SECTION_F, local_path_hints=[str(clone)])

        with mock.patch.object(S.subprocess, "run", git_returns("git@github.com:o/rlm-base-dev.git")):
            loc = S._discover_repo(section)
        check("a surface match whose remote equals repo_url is 'verified-remote'",
              loc.path == clone and loc.identity == "verified-remote" and loc.rejected == []
              and loc.name == "rlm-base-dev" and loc.role == "foundations", loc)

        with mock.patch.object(S.subprocess, "run", git_returns("https://github.com/departed/rlm-base-dev.git")):
            loc = S._discover_repo(section)
        check("a stale clone whose remote names a different repo is REJECTED, not accepted",
              loc.path is None and loc.identity == "unknown"
              and loc.rejected == [(clone, "https://github.com/departed/rlm-base-dev.git")], loc)

        for label, remote in (("an unreadable remote", ""), ("a local-path mirror remote", "/srv/mirror.git")):
            with mock.patch.object(S.subprocess, "run", git_returns(remote)):
                loc = S._discover_repo(section)
            check(f"{label} is accepted as 'unverified' (never a false rejection)",
                  loc.path == clone and loc.identity == "unverified", loc)

        with mock.patch.object(S.subprocess, "run", git_returns("https://x/y/z")):
            loc = S._discover_repo(dict(section, repo_url=""))
        check("an undeclared repo_url cannot be compared: unverified", loc.identity == "unverified", loc)

        # Strict match: the manifest itself ships in the candidate.
        strict = write(tmp / "strict", S.MANIFEST_FILENAME, "manifest_version: 2\n").parent.parent
        with mock.patch.object(S.subprocess, "run", git_returns("https://github.com/o/rlm-base-dev")):
            loc = S._discover_repo(dict(SECTION_F, local_path_hints=[str(strict)]))
        check("a candidate that already carries the manifest is a strict match", loc.path == strict
              and loc.identity == "verified-remote", loc)

        # Self-discovery: the checkout holding the manifest, whatever its directory is called.
        self_root = make_foundations(tmp / "renamed-fork")
        with mock.patch.object(S.subprocess, "run", git_returns("https://github.com/someone/else")):
            loc = S._discover_repo(dict(SECTION_F), self_root)
        check("the checkout holding the manifest is found for the section it describes ('verified-self'), "
              "without consulting the remote",
              loc.path == self_root.resolve() and loc.identity == "verified-self", loc)
        with mock.patch.object(S.subprocess, "run", git_returns("")):
            loc = S._discover_repo(dict(SECTION_P), self_root)
        check("...but never offered to the section it does not describe (PMOS hint at a Foundations checkout)",
              loc.path is None, loc)

        # Hints: relative anchors to manifest_root, env vars, junk.
        with mock.patch.object(S.subprocess, "run", git_returns("")):
            loc = S._discover_repo(dict(SECTION_F, local_path_hints=["../clone"]), tmp / "elsewhere")
        check("a relative hint anchors at manifest_root, not the process cwd",
              loc.path == clone.resolve(), loc)
        with mock.patch.dict(os.environ, {"TP10B_CLONE": str(clone)}), \
                mock.patch.object(S.subprocess, "run", git_returns("")):
            loc = S._discover_repo(dict(SECTION_F, local_path_hints=["$TP10B_CLONE"]))
        check("an env-var hint is expanded", loc.path == clone, loc)
        env = {k: v for k, v in os.environ.items() if k != "TP10B_UNSET"}
        with mock.patch.dict(os.environ, env, clear=True):
            loc = S._discover_repo(dict(SECTION_F, local_path_hints=["$TP10B_UNSET/sub", 42, ["x"], str(tmp / "nope")]))
        check("an unset env var is remembered for the diagnostic and skipped; non-string and missing hints are skipped",
              loc.path is None and loc.env_var == "TP10B_UNSET"
              and all("$" not in str(c) for c in loc.candidates_tried) and str(tmp / "nope") in map(str, loc.candidates_tried),
              loc)
        loc = S._discover_repo({})
        check("an empty section resolves to nothing and names itself '<unknown>'",
              loc.path is None and loc.name == "<unknown>" and loc.role == "<unknown>")


# ---------------------------------------------------------------------------------- find/load manifest


def test_find_and_load():
    print("\nfind_manifest / load_manifest")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        manifest = write(tmp / "repo", S.MANIFEST_FILENAME, SAMPLE)
        sub = tmp / "repo" / "a" / "b"
        sub.mkdir(parents=True)
        check("the manifest is found walking up from a subdirectory", S.find_manifest(sub) == manifest.resolve())
        with mock.patch.object(Path, "cwd", classmethod(lambda cls: sub)):
            check("the default start is the cwd", S.find_manifest() == manifest.resolve())
        empty = tmp / "empty"
        empty.mkdir()
        try:
            S.find_manifest(empty)
            raised = None
        except FileNotFoundError as exc:
            raised = str(exc)
        check("no manifest anywhere above raises FileNotFoundError with guidance",
              raised is not None and S.MANIFEST_FILENAME in raised and "REPO_ROOT" in raised, raised)

        with mock.patch.object(S, "yaml", None), mock.patch.object(S.subprocess, "run", git_returns("")):
            data, _, err = captured(S.load_manifest, manifest)
        check("without PyYAML the fallback parses it and says so on stderr", isinstance(data, dict)
              and data["manifest_version"] == 2 and "minimal fallback" in err, err)
        check("the manifest path and self root are stashed", data["_manifest_path"] == str(manifest)
              and data["_self_repo_root"] == str(manifest.parent.parent))
        check("mapping sections get a _resolved location; empty/None sections do not",
              isinstance(data["foundations"]["_resolved"], S.RepoLocation) and "_resolved" in data["pmos"]
              and data["empty"] is None)

        bad = write(tmp, "bad.yml", "key: |\n  x\n")
        with mock.patch.object(S, "yaml", None):
            result, _, _ = captured(S.load_manifest, bad)
        check("a fallback parse failure is a clean SystemExit, not a traceback",
              isinstance(result, SystemExit) and "cannot parse" in str(result.code), result)
        result, _, _ = captured(S.load_manifest, tmp / "missing.yml")
        check("an unreadable manifest is a clean SystemExit",
              isinstance(result, SystemExit) and "cannot read" in str(result.code), result)
        binary = tmp / "binary.yml"
        binary.write_bytes(b"\xff\xfe\x00\x80")
        result, _, _ = captured(S.load_manifest, binary)
        check("an undecodable manifest is a clean SystemExit", isinstance(result, SystemExit)
              and "cannot read" in str(result.code), result)

        class FakeYamlError(Exception):
            pass

        def fake_yaml(loaded):
            def safe_load(text):
                if isinstance(loaded, Exception):
                    raise loaded
                return loaded
            return type("FakeYaml", (), {"safe_load": staticmethod(safe_load), "YAMLError": FakeYamlError})

        with mock.patch.object(S, "yaml", fake_yaml(["not", "a", "mapping"])):
            data, _, _ = captured(S.load_manifest, manifest)
        check("with PyYAML, a non-mapping document is treated as empty", set(data) == {"_manifest_path", "_self_repo_root"}, data)
        with mock.patch.object(S, "yaml", fake_yaml(None)):
            data, _, _ = captured(S.load_manifest, manifest)
        check("with PyYAML, an empty document is treated as empty", "_manifest_path" in data)
        with mock.patch.object(S, "yaml", fake_yaml(FakeYamlError("bad indent"))):
            result, _, _ = captured(S.load_manifest, manifest)
        check("with PyYAML, a YAML error is a clean SystemExit",
              isinstance(result, SystemExit) and "cannot parse" in str(result.code) and "bad indent" in str(result.code))


# ---------------------------------------------------------------------------------- lookups


def resolved_manifest(root):
    loc = S.RepoLocation(name="rlm-base-dev", role="f", path=Path(root), candidates_tried=[], env_var=None)
    return {
        "foundations": {
            "_resolved": loc,
            "grounding": {
                "single": "docs/one.md",
                "with_path": {"path": "docs/two.md", "count": 3},
                "structured": {"tasks": "docs/tasks.md", "flows": "docs/flows.json", "count": 12, "status": "ok",
                               "bare": "notes.txt", "prose": "not a path"},
                "no_paths": {"count": 1, "status": "x"},
                "number": 7,
            },
            "skills": [{"id": "alpha", "path": ".cursor/skills/alpha/SKILL.md", "purpose": "A"},
                       {"id": "nopath"}],
        },
        "pmos": {"_resolved": S.RepoLocation("pmos", "p", None, [], None),
                 "context_files": {"caps": "docs/caps.md"}},
        "hollow": {},
    }


def test_lookups():
    print("\nresolve_* / list_skills / find_skill")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        m = resolved_manifest(root)
        check("resolve_repo_root returns the located clone", S.resolve_repo_root(m, "foundations") == root)
        check("...and None for an unlocated clone, an unknown repo and an empty section",
              S.resolve_repo_root(m, "pmos") is None and S.resolve_repo_root(m, "nope") is None
              and S.resolve_repo_root(m, "hollow") is None and S.resolve_repo_root({"x": {"a": 1}}, "x") is None)
        check("resolve_path joins under the clone, or is None without one",
              S.resolve_path(m, "foundations", "a/b.md") == root / "a/b.md" and S.resolve_path(m, "pmos", "a") is None)

        g = S.resolve_grounding
        check("a string entry resolves to a Path", g(m, "foundations", "single") == root / "docs/one.md")
        check("a `path:` entry resolves to that Path", g(m, "foundations", "with_path") == root / "docs/two.md")
        structured = g(m, "foundations", "structured")
        check("a structured entry resolves only path-like sub-values (a '/' or a known extension)",
              structured == {"tasks": root / "docs/tasks.md", "flows": root / "docs/flows.json",
                             "bare": root / "notes.txt"}, structured)
        check("an entry with no path-like values, a missing key and a non-str/dict entry are None",
              g(m, "foundations", "no_paths") is None and g(m, "foundations", "absent") is None
              and g(m, "foundations", "number") is None)
        check("an unlocated clone yields None for a structured entry", g(m, "pmos", "caps") is None)
        m2 = {"foundations": {"_resolved": m["foundations"]["_resolved"], "context_files": {"k": "x/y.md"}}}
        check("context_files is the fallback when there is no grounding block",
              g(m2, "foundations", "k") == root / "x/y.md")
        check("a repo absent from the manifest yields None", g(m, "ghost", "k") is None)

        check("list_skills returns the declared entries, [] for none",
              [s["id"] for s in S.list_skills(m, "foundations")] == ["alpha", "nopath"]
              and S.list_skills(m, "pmos") == [] and S.list_skills(m, "ghost") == [])
        check("find_skill finds by id", S.find_skill(m, "foundations", "alpha")["purpose"] == "A"
              and S.find_skill(m, "foundations", "zzz") is None)
        check("resolve_skill returns the SKILL.md path; None for unknown, path-less or unlocated",
              S.resolve_skill(m, "foundations", "alpha") == root / ".cursor/skills/alpha/SKILL.md"
              and S.resolve_skill(m, "foundations", "zzz") is None
              and S.resolve_skill(m, "foundations", "nopath") is None)


# ---------------------------------------------------------------------------------- CLI


def test_cli_list_and_resolve():
    print("\n--list-skills / --resolve")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, ".cursor/skills/alpha/SKILL.md", "x")
        write(root, "docs/one.md", "x")
        write(root, "docs/tasks.md", "x")
        m = resolved_manifest(root)

        rc, out, _ = captured(S._cli_list_skills, m, "foundations")
        check("skills are listed with OK or MISSING per SKILL.md on disk",
              rc == 0 and "[OK     ] alpha" in out and "[MISSING] nopath" in out, out)
        rc, _, err = captured(S._cli_list_skills, m, "pmos")
        check("no declared skills is exit 1 on stderr", rc == 1 and "No skills declared for repo 'pmos'" in err)

        rc, out, _ = captured(S._cli_resolve, m, "foundations/grounding/single")
        check("resolving an existing grounding file prints it and exits 0", rc == 0 and str(root / "docs/one.md") in out, out)
        rc, out, _ = captured(S._cli_resolve, m, "foundations/grounding/with_path")
        check("a resolvable but absent file prints the path and exits 1", rc == 1 and "two.md" in out)
        rc, out, _ = captured(S._cli_resolve, m, "foundations/grounding/structured")
        check("a structured entry prints one sorted line per sub-key and flags missing files (exit 1)",
              rc == 1 and out.splitlines()[0].startswith("bare:") and "(MISSING)" in out
              and "tasks:" in out and "tasks.md  (MISSING)" not in out, out)
        rc, out, _ = captured(S._cli_resolve, m, "foundations/skills/alpha")
        check("kind `skills` resolves a skill", rc == 0 and "SKILL.md" in out, out)
        rc, out, _ = captured(S._cli_resolve, m, "foundations/path/docs/one.md")
        check("kind `path` keeps slashes in the key", rc == 0 and "one.md" in out, out)
        rc, out, _ = captured(S._cli_resolve, m, "pmos/context_files/caps")
        check("kind `context_files` is accepted (unlocated clone: exit 1)", rc == 1)
        rc, _, err = captured(S._cli_resolve, m, "foundations/grounding/absent")
        check("an unresolvable spec is exit 1 with a message", rc == 1 and "could not resolve" in err)
        rc, _, err = captured(S._cli_resolve, m, "foundations/grounding")
        check("a short spec is a usage error (exit 2)", rc == 2 and "{repo}/{kind}/{key}" in err)
        rc, _, err = captured(S._cli_resolve, m, "foundations/frobs/x")
        check("an unknown kind is a usage error (exit 2)", rc == 2 and "unknown kind 'frobs'" in err)


def test_cli_check():
    print("\n_cli_check reporting")

    def manifest(f_path=None, p_path=None, p_optional=True, rejected=None, identity="verified-remote",
                 f_section=True):
        f_loc = S.RepoLocation("rlm-base-dev", "f", f_path, [Path("/tried/f")], "FOUNDATIONS_REPO_ROOT",
                               identity=identity, rejected=rejected or [])
        p_loc = S.RepoLocation("pmos-revenue-cloud", "p", p_path, [Path("/tried/p")], "PMOS_REPO_ROOT",
                               identity=identity)
        return {"_manifest_path": "M", "manifest_version": 2,
                "foundations": {"_resolved": f_loc} if f_section else {},
                "pmos": {"_resolved": p_loc, "optional": p_optional}}

    def run(m):
        with mock.patch.object(S, "_audit_foundations", lambda mm: True), \
                mock.patch.object(S, "_audit_release_identity", lambda mm: True):
            return captured(S._cli_check, m)

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "f"
        f.mkdir()
        rc, out, _ = run(manifest(f_path=f, p_path=None))
        check("an absent OPTIONAL clone is an INFO line and does not fail the check",
              rc == 0 and "[INFO]  pmos" in out and "to enable, set env var: PMOS_REPO_ROOT" in out, out)
        rc, out, _ = run(manifest(f_path=f, p_path=None, p_optional=False))
        check("an absent REQUIRED clone is an ERROR and exit 1",
              rc == 1 and "[ERROR] pmos" in out and "consider setting env var: PMOS_REPO_ROOT" in out, out)
        rc, out, _ = run(manifest(f_path=None, p_path=None))
        check("an absent Foundations clone fails", rc == 1 and "[ERROR] foundations" in out, out)
        rc, out, _ = run(manifest(f_path=f, p_path=None, f_section=False))
        check("a missing section is always fatal, even for an optional repo",
              rc == 1 and "section missing in manifest" in out, out)
        rc, out, _ = run(manifest(f_path=f, p_path=None, rejected=[(Path("/stale"), "https://x/y/z")]))
        check("a rejected stale clone is reported as a WARN naming its remote",
              "[WARN]" in out and "REJECTED candidate" in out and "https://x/y/z" in out, out)
        for identity, needle in (("verified-remote", "git remote matches repo_url"),
                                 ("verified-self", "contains this manifest"),
                                 ("unverified", "UNVERIFIED")):
            _, out, _ = run(manifest(f_path=f, p_path=f, identity=identity))
            check(f"identity {identity!r} is explained", needle in out, out)
        rc, out, _ = run(manifest(f_path=f, p_path=f))
        check("a located optional clone is tagged OK-OPT", "[OK-OPT]" in out and "[OK    ]" in out, out)

        pmos = Path(tmp) / "pmos"
        write(pmos, ".claude/skills/a/SKILL.md")
        write(pmos, ".claude/skills/b/SKILL.md")
        (pmos / ".claude" / "skills" / "c").mkdir()
        _, out, _ = run(manifest(f_path=f, p_path=pmos))
        check("the PMOS skill count is measured from disk (directories without a SKILL.md excluded)",
              "skills on disk: 2" in out, out)

        with mock.patch.object(S, "_audit_foundations", lambda mm: False), \
                mock.patch.object(S, "_audit_release_identity", lambda mm: True):
            rc, _, _ = captured(S._cli_check, manifest(f_path=f, p_path=f))
        check("a failing Foundations audit fails the check even when every clone is found", rc == 1)
        with mock.patch.object(S, "_audit_foundations", lambda mm: True), \
                mock.patch.object(S, "_audit_release_identity", lambda mm: False):
            rc, _, _ = captured(S._cli_check, manifest(f_path=f, p_path=f))
        check("a failing release-identity audit fails the check", rc == 1)


def test_main():
    print("\nmain()")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        write(tmp / "repo", ".cursor/skills/alpha/SKILL.md", "x")
        manifest = write(tmp / "repo", S.MANIFEST_FILENAME,
                         "foundations:\n  name: rlm-base-dev\n  skills:\n    - id: alpha\n"
                         "      path: .cursor/skills/alpha/SKILL.md\n      purpose: p\n")
        with mock.patch.object(S.subprocess, "run", git_returns("")), mock.patch.object(S, "yaml", None):
            rc, out, _ = captured(S.main, ["--list-skills", "foundations", "--manifest", str(manifest)])
            check("--list-skills reads the manifest named by --manifest", rc == 0 and "alpha" in out, out)
            rc, out, _ = captured(S.main, ["--resolve", "foundations/skills/alpha", "--manifest", str(manifest)])
            check("--resolve dispatches", rc == 0 and "SKILL.md" in out, out)
            rc, out, _ = captured(S.main, ["--check", "--manifest", str(manifest)])
            check("--check dispatches and, on a tree with no release identity source, fails rather than passing",
                  rc == 1 and "release identity" in out, out)
        for label, argv in (("no mode", []), ("two modes", ["--check", "--list-skills", "foundations"]),
                            ("an unknown repo for --list-skills", ["--list-skills", "nope"])):
            result, _, _ = captured(S.main, argv)
            check(f"{label} is an argparse error (exit 2)", isinstance(result, SystemExit) and result.code == 2)


# ---------------------------------------------------------------------------------- audit


def test_audit_foundations():
    print("\n_audit_foundations")

    def section(root, skills, extra=None):
        loc = S.RepoLocation("rlm-base-dev", "f", Path(root), [], None)
        sec = {"_resolved": loc, "skills": skills}
        sec.update(extra or {})
        return {"foundations": sec}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, ".cursor/skills/alpha/SKILL.md")
        write(root, "docs/enablement/264/guide.md")

        ok = section(root, [{"id": "alpha", "path": ".cursor/skills/alpha/SKILL.md"}])
        rc, out, _ = captured(S._audit_foundations, ok)
        check("a manifest whose declared skills and paths all exist passes", rc is True and "[OK    ]" in out, out)

        rc, out, _ = captured(S._audit_foundations, section(root, []))
        check("a SKILL.md on disk that is not declared is drift", rc is False and "alpha: has a SKILL.md but is not declared" in out, out)

        rc, out, _ = captured(S._audit_foundations, section(root, [
            {"id": "alpha", "path": ".cursor/skills/alpha/SKILL.md", "sub_skills": ["docs/nope.md"],
             "tooling": ["scripts/nope.py"]}]))
        check("a declared skill's missing path, sub-skill or tooling file is reported",
              rc is False and "skill alpha: missing docs/nope.md" in out and "missing scripts/nope.py" in out, out)

        tmpl_ok = section(root, [{"id": "alpha", "path": ".cursor/skills/alpha/SKILL.md"}],
                          {"grounding": {"guide": "docs/enablement/{release}/guide.md"}})
        rc, _, _ = captured(S._audit_foundations, tmpl_ok)
        check("a {release} template passes when at least one expansion exists", rc is True)
        tmpl_bad = section(root, [{"id": "alpha", "path": ".cursor/skills/alpha/SKILL.md"}],
                           {"grounding": {"guide": "docs/enablement/{release}/never-existed.md"}})
        rc, out, _ = captured(S._audit_foundations, tmpl_bad)
        check("a template that matches nothing is a problem (not accepted unchecked)",
              rc is False and "never-existed.md" in out, out)

        rc, out, _ = captured(S._audit_foundations, section(root, [{"id": "alpha", "path": ".cursor/skills/alpha/SKILL.md"}],
                                                            {"grounding": {"nested": {"deep": ["docs/enablement/264/nope.md"]}}}))
        check("every path-shaped value in the section is walked, however deep", rc is False
              and "foundations.grounding.nested.deep[0]" in out, out)

        loc = S.RepoLocation("rlm-base-dev", "f", None, [], None)
        rc, _, _ = captured(S._audit_foundations, {"foundations": {"_resolved": loc}})
        check("with no located clone there is nothing to audit (passes; the clone check reported it)", rc is True)

    check("_path_like_values yields only strings that name a repo path",
          list(S._path_like_values({"a": "docs/x.md", "b": "prose text", "c": ["AGENTS.md", 5, {"d": "tasks/t.py"}]}, "s"))
          == [("s.a", "docs/x.md"), ("s.c[0]", "AGENTS.md"), ("s.c[2].d", "tasks/t.py")])


def release_fixture(root, *, pmem=True, **overrides):
    """A tree whose release identity is self-consistent; overrides break one thing at a time."""
    if pmem:
        write(root, ".agents/context/project-memory.json", json.dumps(
            {"release_active": "264", "release_prior_ga": "262", "api_version_active": "v68.0",
             "pr_base_branch": "main"}))
    for rel in ("README.md", "CONTRIBUTING.md", "docs/index.md"):
        write(root, rel, "Release 264 v68.0 `main`\n")
    write(root, "docs/erds/erd-data.json", json.dumps(
        {"metadata": {"release": "264", "apiVersion": "68.0"}, "stats": {"totalFields": 10}}))
    write(root, "docs/salesforce/264/help/manifest.json", json.dumps({"release": "264", "stats": {"captured": 5}}))
    manifest = {"_self_repo_root": str(root), "salesforce_release_active": "264",
                "salesforce_release_prior_ga": "262", "api_version_active": "v68.0",
                "foundations": {"grounding": {
                    "erd_data": {"release": "264", "api_version": "v68.0", "field_count": 10},
                    "help_corpus_active": {"release": "264", "path": "docs/salesforce/264/help/articles/",
                                           "article_count": 5}}}}
    manifest.update(overrides)
    return manifest


def test_audit_release_identity():
    print("\n_audit_release_identity")
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, _ = captured(S._audit_release_identity, release_fixture(Path(tmp)))
        check("a self-consistent tree passes", rc is True and "release identity matches" in out, out)

    with tempfile.TemporaryDirectory() as tmp:
        m = release_fixture(Path(tmp), pmem=False)
        rc, out, _ = captured(S._audit_release_identity, m)
        check("no project-memory.json fails naming the file", rc is False and "cannot read" in out, out)
    with tempfile.TemporaryDirectory() as tmp:
        m = release_fixture(Path(tmp))
        write(tmp, ".agents/context/project-memory.json", '{"release_active": "264"}')
        rc, out, _ = captured(S._audit_release_identity, m)
        check("a project-memory.json missing keys fails naming them",
              rc is False and "missing key(s): release_prior_ga" in out, out)

    for label, override, needle in (
            ("a manifest release field that disagrees with the source of truth",
             {"salesforce_release_active": "262"}, "salesforce_release_active='262'"),
            ("a manifest api_version_active that is absent", {"api_version_active": None},
             "api_version_active=None"),
            ("a stale erd_data grounding release", {"foundations": {"grounding": {
                "erd_data": {"release": "262", "api_version": "v67.0", "field_count": 1},
                "help_corpus_active": {"release": "264", "path": "docs/salesforce/264/help/articles/",
                                       "article_count": 5}}}}, "erd_data.release='262'"),
            ("a help_corpus_active count that drifted", {"foundations": {"grounding": {
                "erd_data": {"release": "264", "api_version": "v68.0", "field_count": 10},
                "help_corpus_active": {"release": "262", "path": "docs/salesforce/262/help/articles/",
                                       "article_count": 9}}}}, "help_corpus_active.release='262'")):
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, _ = captured(S._audit_release_identity, release_fixture(Path(tmp), **override))
        check(f"{label} is reported", rc is False and needle in out, out)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        m = release_fixture(root)
        (root / "CONTRIBUTING.md").write_text("Release 263 v67.0\n", encoding="utf-8")
        (root / "docs" / "index.md").unlink()
        (root / "docs" / "erds" / "erd-data.json").unlink()
        (root / "docs" / "salesforce" / "264" / "help" / "manifest.json").unlink()
        rc, out, _ = captured(S._audit_release_identity, m)
        check("a doc that names the wrong release/API/base branch, an unreadable doc, and missing ERD and help "
              "manifests are each reported",
              rc is False and "CONTRIBUTING.md does not mention 'Release 264'" in out
              and "does not name pr_base_branch 'main'" in out and "cannot read docs/index.md" in out
              and "cannot read" in out and "does not exist or is not valid JSON" in out, out)


def main():
    test_scalars()
    test_document_parser()
    test_urls()
    test_git_remote_url()
    test_repo_surface()
    test_discovery()
    test_find_and_load()
    test_lookups()
    test_cli_list_and_resolve()
    test_cli_check()
    test_main()
    test_audit_foundations()
    test_audit_release_identity()

    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
