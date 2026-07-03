"""Deterministic assertion checks against a model response."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.schemas import Assertion, CheckResult

_FENCE_RE = re.compile(r"^```[\w-]*\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def strip_code_fences(text: str) -> str:
    """Remove one surrounding markdown code fence (```json ... ``` or ``` ... ```)."""
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def run_checks(
    response_text: str, assertions: Sequence[Assertion | Mapping[str, Any]]
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for raw in assertions:
        assertion = raw if isinstance(raw, Assertion) else Assertion.model_validate(raw)
        results.append(_run_one(response_text, assertion))
    return results


def checks_passed(results: Sequence[CheckResult]) -> bool | None:
    """All checks passed; None when there are no assertions."""
    if not results:
        return None
    return all(result.passed for result in results)


def _run_one(response_text: str, assertion: Assertion) -> CheckResult:
    if assertion.type in ("contains", "not_contains"):
        return _check_contains(response_text, assertion)
    if assertion.type in ("regex", "not_regex"):
        return _check_regex(response_text, assertion)
    if assertion.type == "json_valid":
        return _check_json_valid(response_text)
    return _check_max_length(response_text, assertion)


def _check_contains(response_text: str, assertion: Assertion) -> CheckResult:
    needle = assertion.value or ""
    if assertion.case_sensitive:
        found = needle in response_text
    else:
        found = needle.lower() in response_text.lower()
    passed = found if assertion.type == "contains" else not found
    sensitivity = "case-sensitive" if assertion.case_sensitive else "case-insensitive"
    detail = (
        f"{assertion.type}: {needle!r} {'found' if found else 'not found'} "
        f"in response ({sensitivity})"
    )
    return CheckResult(type=assertion.type, passed=passed, detail=detail)


def _check_regex(response_text: str, assertion: Assertion) -> CheckResult:
    pattern = assertion.value or ""
    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error as err:
        return CheckResult(type=assertion.type, passed=False, detail=f"invalid regex: {err}")
    found = compiled.search(response_text) is not None
    passed = found if assertion.type == "regex" else not found
    detail = f"{assertion.type}: pattern {pattern!r} {'matched' if found else 'did not match'}"
    return CheckResult(type=assertion.type, passed=passed, detail=detail)


def _check_json_valid(response_text: str) -> CheckResult:
    candidate = strip_code_fences(response_text)
    try:
        json.loads(candidate)
    except json.JSONDecodeError as err:
        return CheckResult(type="json_valid", passed=False, detail=f"invalid JSON: {err}")
    return CheckResult(type="json_valid", passed=True, detail="response parses as JSON")


def _check_max_length(response_text: str, assertion: Assertion) -> CheckResult:
    if assertion.max_chars is None:
        return CheckResult(
            type="max_length", passed=False, detail="max_length assertion is missing max_chars"
        )
    length = len(response_text)
    passed = length <= assertion.max_chars
    comparison = "within" if passed else "exceeds"
    detail = f"length {length} {comparison} max of {assertion.max_chars} characters"
    return CheckResult(type="max_length", passed=passed, detail=detail)
