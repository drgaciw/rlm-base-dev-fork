#!/usr/bin/env python3
"""Unit tests for tasks.rlm_rest_base.

Self-contained — no pytest required (matches this repo's lightweight test
convention). Run from the repo root with base Python:

    python tests/test_rlm_rest_base.py

Covers api_version() resolution order (override > org_config > project_config
> sfdx-project.json > fallback), headers(), base_url() (standard and Tooling),
and request()'s default timeout / override behavior (mocked — no network).
"""
import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from tasks import rlm_rest_base as base  # noqa: E402

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))


class _Obj:
    """Trivial attribute bag standing in for org_config / project_config."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ----------------------------------------------------------------------
# api_version()
# ----------------------------------------------------------------------


def test_api_version_override_wins():
    org = _Obj(api_version="60.0")
    project = _Obj(project__package__api_version="61.0")
    result = base.api_version(org_config=org, project_config=project, override="99.0")
    check("explicit override beats org and project config", result == "99.0")


def test_api_version_org_config_before_project_config():
    org = _Obj(api_version="60.0")
    project = _Obj(project__package__api_version="61.0")
    result = base.api_version(org_config=org, project_config=project)
    check("org_config.api_version beats project_config", result == "60.0")


def test_api_version_falls_back_to_project_config():
    org = _Obj(api_version=None)
    project = _Obj(project__package__api_version="61.0")
    result = base.api_version(org_config=org, project_config=project)
    check("falls back to project_config when org has none", result == "61.0")


def test_api_version_falls_back_to_sfdx_project_json():
    result = base.api_version(start_dir=REPO_ROOT)
    with open(os.path.join(REPO_ROOT, "sfdx-project.json"), encoding="utf-8") as fh:
        expected = json.load(fh)["sourceApiVersion"]
    check(
        "falls back to sfdx-project.json sourceApiVersion when no config given",
        result == expected,
    )


def test_api_version_hard_fallback_when_nothing_resolves():
    with tempfile.TemporaryDirectory() as tmp:
        # An isolated directory tree with no sfdx-project.json anywhere above it
        # (walking up from a fresh temp dir must not accidentally find the
        # repo's own sfdx-project.json).
        nested = os.path.join(tmp, "a", "b", "c")
        os.makedirs(nested, exist_ok=True)
        result = base.api_version(start_dir=nested)
    check("hard-coded fallback used when nothing else resolves", result == "68.0")


def test_api_version_always_returns_a_string():
    org = _Obj(api_version=68.0)  # a float, as some CCI org configs surface it
    result = base.api_version(org_config=org)
    check("numeric api_version is coerced to str", result == "68.0" and isinstance(result, str))


# ----------------------------------------------------------------------
# headers()
# ----------------------------------------------------------------------


def test_headers_default_content_type():
    result = base.headers("tok123")
    check(
        "headers() sets Bearer auth and JSON content-type by default",
        result == {"Authorization": "Bearer tok123", "Content-Type": "application/json"},
    )


def test_headers_no_content_type():
    result = base.headers("tok123", content_type=None)
    check(
        "headers(content_type=None) omits Content-Type (e.g. blob GET)",
        result == {"Authorization": "Bearer tok123"},
    )


# ----------------------------------------------------------------------
# base_url()
# ----------------------------------------------------------------------


def test_base_url_standard():
    result = base.base_url("https://example.my.salesforce.com", "68.0")
    check(
        "base_url() builds the standard services/data URL",
        result == "https://example.my.salesforce.com/services/data/v68.0",
    )


def test_base_url_strips_trailing_slash():
    result = base.base_url("https://example.my.salesforce.com/", "68.0")
    check("base_url() strips a trailing slash on instance_url", "//services" not in result)


def test_base_url_tooling():
    result = base.base_url("https://example.my.salesforce.com", "68.0", tooling=True)
    check(
        "base_url(tooling=True) appends /tooling",
        result == "https://example.my.salesforce.com/services/data/v68.0/tooling",
    )


# ----------------------------------------------------------------------
# request()
# ----------------------------------------------------------------------


def test_request_defaults_timeout():
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs)
        return "fake-response"

    original = base.requests.request
    base.requests.request = fake_request
    try:
        result = base.request("get", "https://example/x", headers={"A": "B"})
    finally:
        base.requests.request = original

    check("request() returns whatever requests.request returns", result == "fake-response")
    check("request() defaults timeout to DEFAULT_TIMEOUT", captured.get("timeout") == base.DEFAULT_TIMEOUT)
    check("request() passes other kwargs through", captured.get("headers") == {"A": "B"})


def test_request_explicit_timeout_overrides_default():
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs)
        return "fake-response"

    original = base.requests.request
    base.requests.request = fake_request
    try:
        base.request("post", "https://example/x", timeout=5)
    finally:
        base.requests.request = original

    check("an explicit timeout= overrides the default", captured.get("timeout") == 5)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    print(f"Running {len(tests)} test groups...\n")
    for t in tests:
        t()
    print()
    for name, ok in RESULTS:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
