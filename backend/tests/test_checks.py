"""Unit tests for services/checks.py (SPEC section 4)."""

from __future__ import annotations

from app.schemas import Assertion, CheckResult
from app.services.checks import checks_passed, run_checks


def one(response: str, **assertion_fields: object) -> CheckResult:
    return run_checks(response, [Assertion.model_validate(assertion_fields)])[0]


# ------------------------------------------------------------------ contains


def test_contains_pass_and_fail() -> None:
    assert one("Hello World", type="contains", value="World").passed is True
    assert one("Hello World", type="contains", value="xyz").passed is False


def test_contains_is_case_insensitive_by_default() -> None:
    assert one("Hello World", type="contains", value="world").passed is True


def test_contains_case_sensitive() -> None:
    assert one("Hello World", type="contains", value="world", case_sensitive=True).passed is False
    assert one("Hello World", type="contains", value="World", case_sensitive=True).passed is True


def test_not_contains_pass_and_fail() -> None:
    assert one("Hello World", type="not_contains", value="xyz").passed is True
    assert one("Hello World", type="not_contains", value="world").passed is False  # ci default
    assert (
        one("Hello World", type="not_contains", value="world", case_sensitive=True).passed
        is True
    )


# --------------------------------------------------------------------- regex


def test_regex_pass_and_fail() -> None:
    assert one("order #12345 confirmed", type="regex", value=r"#\d+").passed is True
    assert one("no digits here", type="regex", value=r"#\d+").passed is False


def test_regex_uses_multiline_flag() -> None:
    assert one("total:\n42\ndone", type="regex", value=r"^\d+$").passed is True


def test_not_regex_pass_and_fail() -> None:
    assert one("clean text", type="not_regex", value=r"\d{3}").passed is True
    assert one("code 123", type="not_regex", value=r"\d{3}").passed is False


def test_invalid_regex_fails_without_raising() -> None:
    result = one("anything", type="regex", value="([")
    assert result.passed is False
    assert result.detail.startswith("invalid regex:")
    result = one("anything", type="not_regex", value="([")
    assert result.passed is False
    assert result.detail.startswith("invalid regex:")


# ---------------------------------------------------------------- json_valid


def test_json_valid_bare_json() -> None:
    assert one('{"a": 1, "b": [2, 3]}', type="json_valid").passed is True
    assert one("[1, 2, 3]", type="json_valid").passed is True


def test_json_valid_strips_code_fences() -> None:
    assert one('```json\n{"a": 1}\n```', type="json_valid").passed is True
    assert one('```\n{"a": 1}\n```', type="json_valid").passed is True
    assert one('  \n```json\n{"a": 1}\n```\n  ', type="json_valid").passed is True


def test_json_invalid_fails() -> None:
    assert one("not json at all", type="json_valid").passed is False
    assert one('```json\n{"a": }\n```', type="json_valid").passed is False


# ---------------------------------------------------------------- max_length


def test_max_length_boundary() -> None:
    text = "x" * 10
    assert one(text, type="max_length", max_chars=10).passed is True  # len == max passes
    assert one(text, type="max_length", max_chars=9).passed is False


def test_max_length_without_max_chars_fails() -> None:
    # SPEC is silent on a missing max_chars; the implementation fails the check.
    assert one("hi", type="max_length").passed is False


# --------------------------------------------------------------- aggregation


def test_checks_passed_semantics() -> None:
    assert checks_passed([]) is None  # no assertions -> null, not true
    all_pass = run_checks(
        "Hello 42", [Assertion(type="contains", value="42"), Assertion(type="max_length", max_chars=100)]
    )
    assert checks_passed(all_pass) is True
    one_fail = run_checks(
        "Hello 42", [Assertion(type="contains", value="42"), Assertion(type="contains", value="nope")]
    )
    assert checks_passed(one_fail) is False


def test_run_checks_accepts_raw_dicts_as_stored_in_db() -> None:
    results = run_checks(
        "Hello World",
        [{"type": "contains", "value": "world"}, {"type": "max_length", "max_chars": 5}],
    )
    assert [r.passed for r in results] == [True, False]


def test_every_check_result_has_human_readable_detail() -> None:
    results = run_checks(
        '{"k": 1}',
        [
            {"type": "contains", "value": "k"},
            {"type": "not_contains", "value": "z"},
            {"type": "regex", "value": r"\d"},
            {"type": "not_regex", "value": r"[A-Z]"},
            {"type": "json_valid"},
            {"type": "max_length", "max_chars": 100},
        ],
    )
    assert len(results) == 6
    assert all(r.passed for r in results)
    assert all(isinstance(r.detail, str) and r.detail for r in results)
