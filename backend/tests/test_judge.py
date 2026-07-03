"""Unit tests for services/judge.py (SPEC section 5)."""

from __future__ import annotations

import pytest

from app.services.judge import (
    JudgeParseError,
    build_judge_prompt,
    parse_judge_response,
)

# ------------------------------------------------------------- prompt builder


def test_prompt_without_reference() -> None:
    prompt = build_judge_prompt(
        prompt="Add 2+2", expected_behavior="Says 4", response="The answer is 4."
    )
    assert prompt.startswith("You are an expert evaluator of LLM outputs.")
    assert "<task>\nAdd 2+2\n</task>" in prompt
    assert "<expected>\nSays 4\n</expected>" in prompt
    assert "<response>\nThe answer is 4.\n</response>" in prompt
    assert "REFERENCE ANSWER" not in prompt
    assert (
        '{"correctness": <1-5>, "relevance": <1-5>, "instruction_following": <1-5>, '
        '"rationale": "<2-3 sentences>"}'
    ) in prompt


def test_prompt_with_reference_block() -> None:
    prompt = build_judge_prompt(
        prompt="Capital of France?",
        expected_behavior="Names Paris",
        response="Paris",
        reference_answer="Paris",
    )
    assert (
        "\nREFERENCE ANSWER (gold standard):\n<reference>\nParis\n</reference>\n" in prompt
    )
    # reference block sits between the expected and response sections
    assert prompt.index("</expected>") < prompt.index("REFERENCE ANSWER") < prompt.index(
        "<response>"
    )


def test_prompt_empty_reference_treated_as_absent() -> None:
    prompt = build_judge_prompt("p", "e", "r", reference_answer="")
    assert "REFERENCE ANSWER" not in prompt


# -------------------------------------------------------------------- parsing


def test_parse_bare_json() -> None:
    scores = parse_judge_response(
        '{"correctness": 4, "relevance": 5, "instruction_following": 3, "rationale": "solid"}'
    )
    assert (scores.correctness, scores.relevance, scores.instruction_following) == (4, 5, 3)
    assert scores.rationale == "solid"


def test_parse_fenced_json() -> None:
    scores = parse_judge_response(
        '```json\n{"correctness": 2, "relevance": 2, "instruction_following": 2, '
        '"rationale": "meh"}\n```'
    )
    assert (scores.correctness, scores.relevance, scores.instruction_following) == (2, 2, 2)


def test_parse_json_surrounded_by_prose() -> None:
    text = (
        "Sure! Here is my evaluation:\n"
        '{"correctness": 3, "relevance": 4, "instruction_following": 5, "rationale": "ok"}\n'
        "Hope that helps."
    )
    scores = parse_judge_response(text)
    assert (scores.correctness, scores.relevance, scores.instruction_following) == (3, 4, 5)


def test_parse_clamps_out_of_range_scores() -> None:
    scores = parse_judge_response(
        '{"correctness": 9, "relevance": 0, "instruction_following": -3, "rationale": "x"}'
    )
    assert scores.correctness == 5
    assert scores.relevance == 1
    assert scores.instruction_following == 1


def test_parse_coerces_floats_to_int() -> None:
    scores = parse_judge_response(
        '{"correctness": 4.0, "relevance": 2.0, "instruction_following": 5.7, "rationale": "x"}'
    )
    assert scores.correctness == 4
    assert scores.relevance == 2
    assert scores.instruction_following == 5  # clamped after coercion


def test_parse_missing_key_raises() -> None:
    with pytest.raises(JudgeParseError):
        parse_judge_response('{"correctness": 4, "relevance": 5, "rationale": "no third key"}')


def test_parse_non_json_raises() -> None:
    with pytest.raises(JudgeParseError):
        parse_judge_response("I would rate this response quite highly overall.")


def test_parse_non_object_json_raises() -> None:
    with pytest.raises(JudgeParseError):
        parse_judge_response("[4, 5, 3]")


def test_parse_non_numeric_score_raises() -> None:
    with pytest.raises(JudgeParseError):
        parse_judge_response(
            '{"correctness": "four", "relevance": 5, "instruction_following": 3}'
        )


def test_parse_rationale_defaults_to_empty_string() -> None:
    scores = parse_judge_response(
        '{"correctness": 4, "relevance": 4, "instruction_following": 4}'
    )
    assert scores.rationale == ""
