#!/usr/bin/env python3
"""Contract tests for the REST wrappers in tasks/ (TP-03, test plan 4.1 rule 1).

"Never mock the unit under test." A-C1 shipped a guaranteed
`TypeError: got multiple values for keyword argument 'timeout'` in every context-extension
step because the suite faked `_make_request` itself. These tests call the REAL wrapper and
patch one layer below it - `requests.Session.request`, which every `requests.get/post/
request` call funnels through - with `autospec=True`, so a duplicate or unknown kwarg raises
exactly as it would in production. Each wrapper is asserted on method, URL, headers/body
pass-through and **exactly one** non-null `timeout`.

Also pinned:
* the wrapper registry (a new `_make_request`/`request` def in tasks/ fails the suite until it
  is registered and covered here);
* an AST sweep: every `requests.<verb>(...)` call in tasks/ carries `timeout=`, unless it
  forwards `**kwargs` from a registered wrapper; and no call passes an explicit `timeout=`
  next to a bare `**kwargs` when the enclosing function has no `timeout` parameter (the exact
  A-C1 shape);
* retry semantics of `ExtendStandardContext._make_request` and `rlm_rest_base.request`;
* the tokens never reach a logger.

Runs with and without CumulusCI installed: modules that import it behind a guard are used as
they are; `rlm_sync_pricing_data` imports it unconditionally, so it is loaded against minimal
stand-ins only when the real package is unusable. Offline, no org.

Run: `python tests/test_rest_contracts.py`  (also collectable by pytest).
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "tasks"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# Before anything can import CumulusCI: its plugin discovery can reset `tasks.__path__`
# (A-C3), and rlm_rest_base has no CCI dependency.
from tasks import rlm_rest_base  # noqa: E402

FAKE_TOKEN = "00Dxx0000001gABEAY!AQFAKEACCESSTOKENVALUE1234567890ABCDE"
INSTANCE = "https://fake.my.salesforce.com"
URL = f"{INSTANCE}/services/data/v68.0/connect/context-definitions/1"
HEADERS = {"Authorization": f"Bearer {FAKE_TOKEN}", "Content-Type": "application/json"}
BODY = {"isActive": "true"}
CONTEXT_TIMEOUT = (30, 600)  # _CONNECT_TIMEOUT, _READ_TIMEOUT in the context-definition tasks


# --------------------------------------------------------------------------------------
# Loading task modules with and without CumulusCI
# --------------------------------------------------------------------------------------


def _cumulusci_usable() -> bool:
    try:
        import cumulusci.core.keychain  # noqa: F401
        import cumulusci.tasks.sfdx  # noqa: F401
    except Exception:  # ImportError, or a broken install (pkg_resources missing on 3.12+)
        return False
    return True


def _load(name: str):
    """Load tasks/<name>.py by file path (not `from tasks.x import y`): once CumulusCI is loaded
    the `tasks` namespace package's `__path__` collapses to `[]` and every SECOND `tasks.*`
    import fails (see tests/test_decision_table_tasks.py::load_task_module). Modules that import
    CumulusCI unconditionally get minimal stand-ins for the two names they need, only when the
    real package is unusable. Nothing is registered in sys.modules, so no copy leaks into
    another suite."""
    path = TASKS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_tp03_{name}", path)
    module = importlib.util.module_from_spec(spec)
    if _cumulusci_usable():
        spec.loader.exec_module(module)
        return module
    stubs = {
        "cumulusci": types.ModuleType("cumulusci"),
        "cumulusci.core": types.ModuleType("cumulusci.core"),
        "cumulusci.core.keychain": types.ModuleType("cumulusci.core.keychain"),
        "cumulusci.tasks": types.ModuleType("cumulusci.tasks"),
        "cumulusci.tasks.sfdx": types.ModuleType("cumulusci.tasks.sfdx"),
    }
    stubs["cumulusci.core.keychain"].BaseProjectKeychain = object
    stubs["cumulusci.tasks.sfdx"].SFDXBaseTask = object
    with mock.patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


rlm_context_service = _load("rlm_context_service")
rlm_extend_stdctx = _load("rlm_extend_stdctx")
rlm_modify_context = _load("rlm_modify_context")
rlm_refresh_decision_table = _load("rlm_refresh_decision_table")
rlm_sync_pricing_data = _load("rlm_sync_pricing_data")
rlm_cml = _load("rlm_cml")
rlm_manage_fulfillment_scope_cnfg = _load("rlm_manage_fulfillment_scope_cnfg")
rlm_manage_transaction_processing_types = _load("rlm_manage_transaction_processing_types")


# --------------------------------------------------------------------------------------
# One layer below the wrapper: requests.Session.request
# --------------------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self._json = {} if json_body is None else json_body
        self.text = text if text is not None else ("{}" if json_body is not None else "")

    def json(self):
        return self._json


class Recorder:
    """Replays queued responses (the last one repeats) or raises queued exceptions."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes) or [FakeResponse(200, {})]
        self.calls = []  # (method, url, kwargs)

    def __call__(self, session, method, url, **kwargs):
        self.calls.append((str(method).lower(), url, kwargs))
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@contextlib.contextmanager
def http(*outcomes):
    """autospec=True keeps Session.request's real signature, so a wrapper that passes a
    keyword twice or an unknown one raises TypeError here exactly as it would for real."""
    recorder = Recorder(*outcomes)
    with mock.patch.object(requests.Session, "request", autospec=True, side_effect=recorder):
        yield recorder


class RecordingLogger:
    def __init__(self):
        self.messages = []

    def _log(self, msg, *args, **kwargs):
        self.messages.append(str(msg))

    info = warning = error = debug = _log

    def text(self):
        return "\n".join(self.messages)


def bare(cls, **attrs):
    """A task instance without running CCI's __init__ (no project, keychain or org)."""
    task = cls.__new__(cls)
    task.logger = RecordingLogger()
    for key, value in attrs.items():
        setattr(task, key, value)
    return task


def assert_one_timeout(testcase, call, expected=None, label=""):
    method, url, kwargs = call
    timeout = kwargs.get("timeout")
    testcase.assertIsNotNone(timeout, f"{label}: request went out without a timeout")
    if expected is not None:
        testcase.assertEqual(timeout, expected, label)


# --------------------------------------------------------------------------------------
# rlm_rest_base.request
# --------------------------------------------------------------------------------------


class TestRestBaseRequest(unittest.TestCase):
    def test_default_timeout_method_url_headers_json_and_params_pass_through(self):
        with http() as h:
            rlm_rest_base.request("POST", URL, headers=HEADERS, json=BODY, params={"q": "x"})
        self.assertEqual(len(h.calls), 1)
        method, url, kwargs = h.calls[0]
        self.assertEqual((method, url), ("post", URL))
        self.assertEqual(kwargs["headers"], HEADERS)
        self.assertEqual(kwargs["json"], BODY)
        self.assertEqual(kwargs["params"], {"q": "x"})
        self.assertEqual(kwargs["timeout"], rlm_rest_base.DEFAULT_TIMEOUT)

    def test_explicit_timeout_replaces_the_default_and_is_sent_once(self):
        with http() as h:
            rlm_rest_base.request("get", URL, timeout=7)
        self.assertEqual(h.calls[0][2]["timeout"], 7)

    def test_does_not_retry(self):
        # No retry policy lives here; callers that want one own it (see ExtendStandardContext).
        with http(FakeResponse(503, text="busy")) as h:
            response = rlm_rest_base.request("get", URL)
        self.assertEqual(len(h.calls), 1)
        self.assertEqual(response.status_code, 503)

    def test_transport_errors_propagate_after_a_single_attempt(self):
        with http(requests.exceptions.ConnectionError("boom")) as h:
            with self.assertRaises(requests.exceptions.ConnectionError):
                rlm_rest_base.request("get", URL)
        self.assertEqual(len(h.calls), 1)


# --------------------------------------------------------------------------------------
# Every `_make_request` wrapper
# --------------------------------------------------------------------------------------


def _wrappers():
    """label -> (factory building a bare task, expected default timeout)."""
    return {
        "rlm_context_service.ManageContextDefinition._make_request": (
            lambda: bare(rlm_context_service.ManageContextDefinition),
            CONTEXT_TIMEOUT,
        ),
        "rlm_extend_stdctx.ExtendStandardContext._make_request": (
            lambda: bare(rlm_extend_stdctx.ExtendStandardContext),
            CONTEXT_TIMEOUT,
        ),
        "rlm_modify_context.ModifyContextDefinition._make_request": (
            lambda: bare(rlm_modify_context.ModifyContextDefinition),
            CONTEXT_TIMEOUT,
        ),
        "rlm_refresh_decision_table.RefreshDecisionTable._make_request": (
            lambda: bare(rlm_refresh_decision_table.RefreshDecisionTable),
            rlm_rest_base.DEFAULT_TIMEOUT,
        ),
        "rlm_sync_pricing_data.SyncPricingData._make_request": (
            lambda: bare(rlm_sync_pricing_data.SyncPricingData),
            rlm_rest_base.DEFAULT_TIMEOUT,
        ),
    }


@contextlib.contextmanager
def _real_requests_module_in(module):
    """rlm_refresh_decision_table binds `requests = None` when CumulusCI is not importable (its
    guard sits around `import requests` too). Under CumulusCI the task can run, so pin the real
    module back to test the same code path without it."""
    if getattr(module, "requests", requests) is None:
        with mock.patch.object(module, "requests", requests):
            yield
    else:
        yield


class TestMakeRequestWrappers(unittest.TestCase):
    def _for_each_wrapper(self, body):
        """Run body(label, task, expected_timeout) once per wrapper, each in its own subTest so
        one broken wrapper cannot hide the others."""
        for label, (factory, expected) in _wrappers().items():
            module = globals()[label.split(".")[0]]
            with self.subTest(wrapper=label), _real_requests_module_in(module):
                body(label, factory(), expected)

    def test_success_sends_method_url_headers_body_and_exactly_one_timeout(self):
        def body(label, task, expected):
            with http(FakeResponse(200, {"ok": True})) as h:
                result = task._make_request("post", URL, headers=HEADERS, json=BODY)
            self.assertEqual(result, {"ok": True}, label)
            self.assertEqual(len(h.calls), 1, label)
            method, url, kwargs = h.calls[0]
            self.assertEqual((method, url), ("post", URL), label)
            self.assertEqual(kwargs["headers"], HEADERS, label)
            self.assertEqual(kwargs["json"], BODY, label)
            assert_one_timeout(self, h.calls[0], expected, label)

        self._for_each_wrapper(body)

    def test_caller_supplied_timeout_wins_and_is_still_a_single_kwarg(self):
        def body(label, task, _expected):
            with http(FakeResponse(200, {"ok": True})) as h:
                task._make_request("get", URL, headers=HEADERS, timeout=9)
            self.assertEqual(h.calls[0][2]["timeout"], 9, label)

        self._for_each_wrapper(body)

    def test_error_response_returns_none_and_logs_without_the_token(self):
        def body(label, task, _expected):
            with http(FakeResponse(400, text="INVALID_INPUT: bad request")) as h:
                with mock.patch("time.sleep"):  # ExtendStandardContext sleeps only on 5xx
                    result = task._make_request("post", URL, headers=HEADERS, json=BODY)
            self.assertIsNone(result, label)
            self.assertEqual(len(h.calls), 1, f"{label}: a 4xx must not be retried")
            logged = task.logger.text()
            self.assertIn("INVALID_INPUT", logged, label)
            self.assertNotIn(FAKE_TOKEN, logged, label)

        self._for_each_wrapper(body)

    def test_wrapper_registry_matches_the_defs_in_tasks(self):
        found = set()
        for path in sorted(TASKS_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name in ("_make_request", "request"):
                            found.add(f"{path.stem}.{node.name}.{item.name}")
        registered = set(_wrappers())
        self.assertEqual(
            found,
            registered,
            "a `_make_request`/`request` method was added to (or removed from) tasks/ - register "
            "it in _wrappers() so its timeout/args contract is tested",
        )
        module_level = {
            f"{path.stem}.{node.name}"
            for path in sorted(TASKS_DIR.glob("*.py"))
            for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name in ("_make_request", "request")
        }
        self.assertEqual(module_level, {"rlm_rest_base.request"}, module_level)


class TestExtendStandardContextRetry(unittest.TestCase):
    """`ExtendStandardContext._make_request` is the only wrapper with retry semantics."""

    def _task(self):
        return bare(rlm_extend_stdctx.ExtendStandardContext)

    def test_get_is_retried_on_5xx_and_every_attempt_carries_a_timeout(self):
        task = self._task()
        with http(FakeResponse(503, text="busy"), FakeResponse(200, {"ok": 1})) as h, mock.patch.object(
            rlm_extend_stdctx.time, "sleep"
        ) as sleep:
            result = task._make_request("get", URL, headers=HEADERS)
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(len(h.calls), 2)
        for call in h.calls:
            assert_one_timeout(self, call, CONTEXT_TIMEOUT)
        sleep.assert_called_once_with(rlm_extend_stdctx._RETRY_BACKOFF)

    def test_post_is_not_retried_by_default(self):
        task = self._task()
        with http(FakeResponse(503, text="busy"), FakeResponse(200, {"ok": 1})) as h, mock.patch.object(
            rlm_extend_stdctx.time, "sleep"
        ) as sleep:
            result = task._make_request("post", URL, headers=HEADERS, json=BODY)
        self.assertIsNone(result)
        self.assertEqual(len(h.calls), 1)
        sleep.assert_not_called()
        self.assertEqual(task._last_response_status, 503)

    def test_retryable_true_forces_a_post_retry_and_false_stops_a_get(self):
        with http(FakeResponse(503, text="busy"), FakeResponse(200, {"ok": 1})) as h, mock.patch.object(
            rlm_extend_stdctx.time, "sleep"
        ):
            self.assertEqual(self._task()._make_request("post", URL, retryable=True), {"ok": 1})
        self.assertEqual(len(h.calls), 2)
        with http(FakeResponse(503, text="busy"), FakeResponse(200, {"ok": 1})) as h, mock.patch.object(
            rlm_extend_stdctx.time, "sleep"
        ):
            self.assertIsNone(self._task()._make_request("get", URL, retryable=False))
        self.assertEqual(len(h.calls), 1)

    def test_network_errors_are_retried_up_to_the_cap_then_return_none(self):
        task = self._task()
        error = requests.exceptions.ConnectionError("reset")
        with http(error) as h, mock.patch.object(rlm_extend_stdctx.time, "sleep"):
            result = task._make_request("get", URL)
        self.assertIsNone(result)
        self.assertEqual(len(h.calls), rlm_extend_stdctx._MAX_RETRIES)
        for call in h.calls:
            assert_one_timeout(self, call, CONTEXT_TIMEOUT)

    def test_204_and_non_json_bodies_return_an_empty_dict(self):
        task = self._task()
        with http(FakeResponse(204, text="")):
            self.assertEqual(task._make_request("delete", URL), {})

        class NotJson(FakeResponse):
            def json(self):
                raise ValueError("no json")

        with http(NotJson(200, text="<html>")):
            self.assertEqual(task._make_request("get", URL), {})


class TestContextServiceDryRun(unittest.TestCase):
    def test_dry_run_short_circuits_before_any_request(self):
        task = bare(rlm_context_service.ManageContextDefinition)
        with http() as h:
            self.assertEqual(task._make_request("post", URL, dry_run=True, json=BODY), {})
        self.assertEqual(h.calls, [])


# --------------------------------------------------------------------------------------
# Modules that reach REST through rlm_rest_base.request or requests.<verb> directly
# --------------------------------------------------------------------------------------


class TestCmlBaseTaskRest(unittest.TestCase):
    def _task(self):
        org = types.SimpleNamespace(access_token=FAKE_TOKEN, instance_url=INSTANCE, api_version="68.0")
        return bare(rlm_cml.CMLBaseTask, org_config=org, project_config=None, options={})

    def test_every_rest_helper_sends_bearer_headers_and_the_default_timeout(self):
        task = self._task()
        cases = [
            ("soql_query", lambda: task.soql_query("SELECT Id FROM Product2"), "get", FakeResponse(200, {"records": [], "done": True})),
            ("create_record", lambda: task.create_record("Product2", {"Name": "x"}), "post", FakeResponse(201, {"id": "01t"})),
            ("update_record", lambda: task.update_record("Product2", "01t", {"Name": "y"}), "patch", FakeResponse(204)),
            ("delete_record", lambda: task.delete_record("Product2", "01t"), "delete", FakeResponse(204)),
        ]
        for name, call, verb, response in cases:
            with self.subTest(helper=name), http(response) as h:
                call()
                self.assertEqual(len(h.calls), 1)
                method, url, kwargs = h.calls[0]
                self.assertEqual(method, verb)
                self.assertTrue(url.startswith(f"{INSTANCE}/services/data/v68.0/"), url)
                self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {FAKE_TOKEN}")
                assert_one_timeout(self, h.calls[0], rlm_rest_base.DEFAULT_TIMEOUT, name)

    def test_pagination_follows_next_records_url_with_a_timeout_on_every_page(self):
        task = self._task()
        page1 = FakeResponse(200, {"records": [{"Id": "1"}], "done": False, "nextRecordsUrl": "/services/data/v68.0/query/01g-2000"})
        page2 = FakeResponse(200, {"records": [{"Id": "2"}], "done": True})
        with http(page1, page2) as h:
            records = task.soql_query("SELECT Id FROM Product2")
        self.assertEqual([r["Id"] for r in records], ["1", "2"])
        self.assertEqual(h.calls[1][1], f"{INSTANCE}/services/data/v68.0/query/01g-2000")
        for call in h.calls:
            assert_one_timeout(self, call, rlm_rest_base.DEFAULT_TIMEOUT)


class TestToolingTaskRest(unittest.TestCase):
    def test_fulfillment_scope_reads_and_writes_carry_a_timeout(self):
        task = bare(rlm_manage_fulfillment_scope_cnfg.ManageFulfillmentScopeCnfg)
        args = (FAKE_TOKEN, INSTANCE, "68.0")
        cases = [
            ("_create_record", lambda: task._create_record(*args, {"DeveloperName": "x"}), "post", FakeResponse(201, {"id": "0AB"})),
            ("_data_query", lambda: task._data_query(*args, "SELECT Id FROM ContextTag"), "get", FakeResponse(200, {"records": []})),
            ("_query", lambda: task._query(*args, "SELECT Id FROM CustomFulfillmentScopeCnfg"), "get", FakeResponse(200, {"records": [], "done": True})),
        ]
        for name, call, verb, response in cases:
            with self.subTest(site=name), http(response) as h:
                call()
                self.assertEqual(len(h.calls), 1)
                self.assertEqual(h.calls[0][0], verb)
                self.assertEqual(h.calls[0][2]["headers"]["Authorization"], f"Bearer {FAKE_TOKEN}")
                assert_one_timeout(self, h.calls[0], rlm_rest_base.DEFAULT_TIMEOUT, name)

    def test_transaction_processing_types_reads_and_writes_carry_a_timeout(self):
        task = bare(rlm_manage_transaction_processing_types.ManageTransactionProcessingTypes)
        args = (FAKE_TOKEN, INSTANCE, "68.0")
        cases = [
            ("_describe", lambda: task._describe(*args), "get", FakeResponse(200, {"fields": []})),
            ("_query", lambda: task._query(*args, "SELECT Id FROM TransactionProcessingType"), "get", FakeResponse(200, {"records": []})),
            ("_create_record", lambda: task._create_record(*args, {"DeveloperName": "x"}), "post", FakeResponse(201, {"id": "0AB"})),
            ("_update_record", lambda: task._update_record(*args, "0AB", {"IsActive": True}), "patch", FakeResponse(204)),
        ]
        for name, call, verb, response in cases:
            with self.subTest(site=name), http(response) as h:
                call()
                self.assertEqual(len(h.calls), 1)
                self.assertEqual(h.calls[0][0], verb)
                self.assertIn("/tooling/", h.calls[0][1])
                self.assertEqual(h.calls[0][2]["headers"]["Authorization"], f"Bearer {FAKE_TOKEN}")
                assert_one_timeout(self, h.calls[0], rlm_rest_base.DEFAULT_TIMEOUT, name)


# --------------------------------------------------------------------------------------
# AST sweep: no request leaves tasks/ without a timeout
# --------------------------------------------------------------------------------------

_VERBS = {"get", "post", "patch", "put", "delete", "head", "options", "request"}
_SESSION_NAMES = {"requests", "session", "sess"}


def _http_calls(tree):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _VERBS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in _SESSION_NAMES
        ):
            yield node


def _enclosing_function(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    return None


def timeout_violations(tree, delegating_wrappers=("_make_request", "request")):
    """[(lineno, why)] for requests calls that can leave without exactly one timeout."""
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    problems = []
    for call in _http_calls(tree):
        keywords = {kw.arg for kw in call.keywords}
        forwards_kwargs = None in keywords
        func = _enclosing_function(call, parents)
        params = set()
        if func is not None:
            params = {a.arg for a in func.args.args + func.args.kwonlyargs}
        if "timeout" not in keywords and not forwards_kwargs:
            problems.append((call.lineno, "no timeout="))
        elif "timeout" not in keywords and forwards_kwargs:
            if func is None or func.name not in delegating_wrappers:
                problems.append((call.lineno, "forwards **kwargs but is not a registered wrapper"))
        elif "timeout" in keywords and forwards_kwargs and "timeout" not in params:
            problems.append((call.lineno, "explicit timeout= next to **kwargs (A-C1 shape)"))
    return sorted(problems)


class TestTimeoutSweep(unittest.TestCase):
    def test_every_http_call_in_tasks_carries_a_timeout(self):
        offenders = {}
        for path in sorted(TASKS_DIR.glob("*.py")):
            problems = timeout_violations(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
            if problems:
                offenders[path.name] = problems
        self.assertEqual(offenders, {}, offenders)

    def test_the_sweep_sees_the_calls_it_claims_to_check(self):
        total = sum(
            len(list(_http_calls(ast.parse(p.read_text(encoding="utf-8")))))
            for p in TASKS_DIR.glob("*.py")
        )
        # 60+ direct call sites at the time of writing; a walk that matches nothing is a
        # vacuous pass, so require it to keep seeing a healthy fraction of them.
        self.assertGreater(total, 40)

    def test_controls(self):
        def v(source):
            return timeout_violations(ast.parse(source))

        self.assertEqual(v("def f():\n    requests.get(u)\n"), [(2, "no timeout=")])
        self.assertEqual(v("def f():\n    requests.get(u, timeout=5)\n"), [])
        self.assertEqual(v("def f():\n    session.patch(u, json=b)\n"), [(2, "no timeout=")])
        # the A-C1 shape: setdefault + explicit timeout + **kwargs, no timeout parameter
        self.assertEqual(
            v("def _make_request(self, m, u, **kwargs):\n    return requests.request(m, u, timeout=(1, 2), **kwargs)\n"),
            [(2, "explicit timeout= next to **kwargs (A-C1 shape)")],
        )
        # a keyword-only timeout parameter makes explicit timeout= + **kwargs unambiguous
        self.assertEqual(
            v("def request(m, u, *, timeout=1, **kwargs):\n    return requests.request(m, u, timeout=timeout, **kwargs)\n"),
            [],
        )
        # **kwargs forwarding is only acceptable inside a registered wrapper
        self.assertEqual(v("def _make_request(self, m, u, **kw):\n    return requests.request(m, u, **kw)\n"), [])
        self.assertEqual(
            v("def helper(m, u, **kw):\n    return requests.request(m, u, **kw)\n"),
            [(2, "forwards **kwargs but is not a registered wrapper")],
        )


if __name__ == "__main__":
    unittest.main(verbosity=1)
