#!/usr/bin/env python3
"""Unit tests for tasks.rlm_context_service's REST plumbing.

Self-contained — no pytest required (matches this repo's lightweight test
convention). Run from the repo root with base Python:

    python tests/test_rlm_context_service.py

Covers ``ManageContextDefinition._make_request`` (dry-run short-circuit,
success/empty-body/error handling, delegation to ``tasks.rlm_rest_base``) and
``_fetch_context_definition`` (dict pass-through, single-item list unwrap,
multi-item list warning, falsy response) with ``requests`` mocked out via a
monkeypatch of ``rlm_rest_base.request`` — no network or org access.
"""
import logging
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from tasks import rlm_context_service as rcs  # noqa: E402
from tasks import rlm_rest_base  # noqa: E402

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json_body = json_body
        # A response with a JSON body always has non-empty text in practice;
        # let the caller override explicitly for the "empty body" case.
        self.text = text if text else ("{}" if json_body is not None else "")

    def json(self):
        return self._json_body


class _FakeContextTask(rcs.ManageContextDefinition):
    """Bare instance bypassing the CCI task __init__ (no project/org context).

    Matches the pattern used by tests/test_expression_set_schema.py's
    _CascadeTask / _OverlayApplier for pure-logic unit testing.
    """

    def __init__(self):
        self.logger = logging.getLogger("test_context_service_task")
        self.logger.addHandler(logging.NullHandler())
        self.options = {}
        self.access_token = "fake-token"
        self.instance_url = "https://example.my.salesforce.com"
        self.api_version = "68.0"


class _RequestRecorder:
    """Stand-in for rlm_rest_base.request: records calls, returns a queued response."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def _patched_request(response):
    """Context-manager-less monkeypatch helper: swap rlm_rest_base.request,
    return the recorder, and give the caller a restore function."""
    recorder = _RequestRecorder(response)
    original = rlm_rest_base.request
    rlm_rest_base.request = recorder

    def restore():
        rlm_rest_base.request = original

    return recorder, restore


# ----------------------------------------------------------------------
# _make_request
# ----------------------------------------------------------------------


def test_make_request_dry_run_short_circuits():
    task = _FakeContextTask()
    recorder, restore = _patched_request(_FakeResponse(status_code=200, json_body={}))
    try:
        result = task._make_request("post", "https://example/x", dry_run=True, json={"a": 1})
    finally:
        restore()
    check("dry-run returns {} without an HTTP call", result == {} and recorder.calls == [])


def test_make_request_success_returns_parsed_json():
    task = _FakeContextTask()
    body = {"contextDefinitionId": "0ct000000000001"}
    recorder, restore = _patched_request(_FakeResponse(status_code=200, json_body=body))
    try:
        result = task._make_request("get", "https://example/context-definitions/1")
    finally:
        restore()
    check("success returns the parsed JSON body", result == body)
    check(
        "success delegates through rlm_rest_base.request (not requests directly)",
        len(recorder.calls) == 1 and recorder.calls[0][0] == "get",
    )


def test_make_request_success_empty_body_returns_empty_dict():
    task = _FakeContextTask()
    recorder, restore = _patched_request(_FakeResponse(status_code=204, text=""))
    try:
        result = task._make_request("delete", "https://example/context-nodes/1")
    finally:
        restore()
    check("204/empty-body success returns {}", result == {})


def test_make_request_error_logs_and_returns_none():
    task = _FakeContextTask()
    recorder, restore = _patched_request(
        _FakeResponse(status_code=400, text="INVALID_INPUT: bad request")
    )
    try:
        result = task._make_request("post", "https://example/context-nodes")
    finally:
        restore()
    check("error response returns None", result is None)


def test_make_request_passes_kwargs_through_to_helper():
    task = _FakeContextTask()
    recorder, restore = _patched_request(_FakeResponse(status_code=200, json_body={}))
    try:
        task._make_request(
            "patch",
            "https://example/context-mappings/1",
            headers={"Authorization": "Bearer fake-token"},
            json={"isActive": "true"},
        )
    finally:
        restore()
    method, url, kwargs = recorder.calls[0]
    check(
        "headers/json kwargs reach rlm_rest_base.request untouched",
        kwargs.get("headers", {}).get("Authorization") == "Bearer fake-token"
        and kwargs.get("json") == {"isActive": "true"},
    )


# ----------------------------------------------------------------------
# _fetch_context_definition
# ----------------------------------------------------------------------


def _with_fetch_response(task, body):
    """Monkeypatch task._make_request to return `body`, restoring afterward."""
    original = task._make_request
    task._make_request = lambda *a, **k: body
    return original


def test_fetch_context_definition_dict_pass_through():
    task = _FakeContextTask()
    detail = {"contextDefinitionVersionList": [{"contextNodes": []}]}
    original = _with_fetch_response(task, detail)
    try:
        result = task._fetch_context_definition("0ct000000000001")
    finally:
        task._make_request = original
    check("dict response is returned as-is", result == detail)


def test_fetch_context_definition_unwraps_single_item_list():
    task = _FakeContextTask()
    detail = {"contextDefinitionVersionList": []}
    original = _with_fetch_response(task, [detail])
    try:
        result = task._fetch_context_definition("0ct000000000001")
    finally:
        task._make_request = original
    check("single-item list response is unwrapped", result == detail)


def test_fetch_context_definition_warns_on_multi_item_list():
    task = _FakeContextTask()
    original = _with_fetch_response(task, [{"a": 1}, {"b": 2}])
    try:
        result = task._fetch_context_definition("0ct000000000001")
    finally:
        task._make_request = original
    check("multi-item list response falls back to {}", result == {})


def test_fetch_context_definition_falsy_response_returns_empty_dict():
    task = _FakeContextTask()
    original = _with_fetch_response(task, None)
    try:
        result = task._fetch_context_definition("0ct000000000001")
    finally:
        task._make_request = original
    check("None response (error) returns {}", result == {})


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
