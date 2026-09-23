#!/usr/bin/env python3
"""Parity test between the canonical and vendored expression-set schema validators.

``tasks/expression_set_schema.py`` (imported by the CCI task,
``tasks/rlm_expression_set_connect.py``) and
``scripts/expression_sets/_schema.py`` (the standalone toolkit's own copy,
which deliberately does not import the CCI task's module — see that file's
docstring) implement the same validation rules twice. They drifted once
already (the vendored copy validates the overlay ``labels`` block and an
addVariables/addSteps output clash; the canonical copy did not) — see WP-08 in
docs/ARCHITECT_REVIEW.md. This test runs a shared fixture set through both and
asserts they agree, so a future edit to one that is not mirrored in the other
fails CI instead of silently drifting again.

Self-contained — no pytest required (matches this repo's lightweight test
convention). Run from the repo root with base Python:

    python tests/test_expression_set_schema_parity.py

Exits 0 when all checks pass, 1 otherwise.
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from tasks import expression_set_schema as canonical  # noqa: E402
from scripts.expression_sets import _schema as vendored  # noqa: E402

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))


def _issue_set(result):
    """(severity, location, message) tuples, order-independent."""
    return {(i.severity.value, i.location, i.message) for i in result.issues}


def _assert_parity(name, entry_point, payload):
    canonical_result = getattr(canonical, entry_point)(json.loads(json.dumps(payload)))
    vendored_result = getattr(vendored, entry_point)(json.loads(json.dumps(payload)))

    check(f"{name}: passed matches", canonical_result.passed == vendored_result.passed)
    check(f"{name}: issues match", _issue_set(canonical_result) == _issue_set(vendored_result))
    return canonical_result, vendored_result


# ----------------------------------------------------------------------
# Shared fixtures
# ----------------------------------------------------------------------

MINIMAL_PRICING_DEF = {
    "apiName": "ZZ_Test",
    "name": "ZZ Test",
    "usageType": "DefaultPricing",
    "versions": [
        {
            "apiName": "ZZ_Test_V1",
            "versionNumber": 1,
            "rank": 1,
            "steps": [
                {
                    "name": "PricingSetting",
                    "sequenceNumber": 1,
                    "stepType": "BusinessKnowledgeModel",
                    "actionType": "PricingSettings",
                },
                {
                    "name": "SecondStep",
                    "sequenceNumber": 2,
                    "stepType": "ListGroup",
                },
            ],
            "variables": [],
        }
    ],
}

MINIMAL_OVERLAY = {
    "expressionSetApiName": "ZZ_Test",
    "addSteps": [
        {
            "name": "NewStep",
            "stepType": "BusinessKnowledgeModel",
            "placement": {"afterStep": "PricingSetting"},
        }
    ],
}


def _step_with_output(var_name: str) -> dict:
    return {
        "name": "ProducingStep",
        "stepType": "BusinessKnowledgeModel",
        "customElement": {
            "parameters": [
                {"type": "Parameter", "value": var_name, "output": True},
            ]
        },
    }


def test_valid_definition_parity():
    _assert_parity("valid definition", "validate_definition", MINIMAL_PRICING_DEF)


def test_invalid_definition_parity():
    bad = json.loads(json.dumps(MINIMAL_PRICING_DEF))
    bad["versions"][0]["steps"][0]["stepType"] = "NotARealStepType"
    result, _ = _assert_parity("invalid stepType definition", "validate_definition", bad)
    check("invalid stepType definition: actually errors", not result.passed and result.errors)


def test_valid_overlay_parity():
    _assert_parity("valid overlay", "validate_overlay", MINIMAL_OVERLAY)


def test_overlay_valid_labels_parity():
    overlay = {**MINIMAL_OVERLAY, "labels": {"NewStep": "New Step Label"}}
    result, _ = _assert_parity("overlay with valid labels", "validate_overlay", overlay)
    check("overlay with valid labels: passes", result.passed and not result.errors)


def test_overlay_labels_not_object_parity():
    overlay = {**MINIMAL_OVERLAY, "labels": ["not", "a", "dict"]}
    result, _ = _assert_parity("overlay with non-dict labels", "validate_overlay", overlay)
    check(
        "overlay with non-dict labels: errors on 'labels'",
        not result.passed and any(i.location == "labels" for i in result.errors),
    )


def test_overlay_labels_bad_values_parity():
    overlay = {**MINIMAL_OVERLAY, "labels": {"NewStep": 42}}
    result, _ = _assert_parity("overlay with non-string label value", "validate_overlay", overlay)
    check(
        "overlay with non-string label value: errors on 'labels'",
        not result.passed and any(i.location == "labels" for i in result.errors),
    )


def test_overlay_addvariables_step_output_clash_parity():
    overlay = {
        "expressionSetApiName": "ZZ_Test",
        "addSteps": [_step_with_output("MyProducedVar")],
        "addVariables": [
            {"name": "MyProducedVar", "dataType": "String", "purpose": "Constant"}
        ],
    }
    result, _ = _assert_parity(
        "overlay addVariables clashing with step output", "validate_overlay", overlay
    )
    check(
        "overlay addVariables clash: errors",
        not result.passed
        and any("already produced as a step output" in i.message for i in result.errors),
    )


def test_overlay_addvariables_no_clash_parity():
    overlay = {
        "expressionSetApiName": "ZZ_Test",
        "addSteps": [_step_with_output("SomeOtherVar")],
        "addVariables": [
            {"name": "MyOwnConstant", "dataType": "String", "purpose": "Constant"}
        ],
    }
    _assert_parity("overlay addVariables not clashing", "validate_overlay", overlay)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    print(f"Running {len(tests)} parity test groups...\n")
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
