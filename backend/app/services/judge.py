"""LLM-as-judge: rubric prompt construction and score parsing."""

import json

from app.schemas import JudgeScores as _JudgeScoresBase
from app.services.checks import strip_code_fences

# Literal JSON braces are doubled so str.format only substitutes the placeholders.
JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator of LLM outputs. Score the RESPONSE against the TASK.

TASK (the prompt given to the model):
<task>
{prompt}
</task>

EXPECTED BEHAVIOR:
<expected>
{expected_behavior}
</expected>
{reference_block}
RESPONSE TO EVALUATE:
<response>
{response}
</response>

Score each dimension as an integer 1-5 (1=very poor, 3=acceptable, 5=excellent):
- correctness: factual/logical accuracy of the response for this task
- relevance: how well the response addresses what was asked, without digressions
- instruction_following: adherence to explicit constraints (format, length, style)

Reply with ONLY a JSON object, no other text:
{{"correctness": <1-5>, "relevance": <1-5>, "instruction_following": <1-5>, "rationale": "<2-3 sentences>"}}"""

REFERENCE_BLOCK_TEMPLATE = (
    "\nREFERENCE ANSWER (gold standard):\n<reference>\n{reference_answer}\n</reference>\n"
)

_REQUIRED_KEYS = ("correctness", "relevance", "instruction_following")


class JudgeParseError(Exception):
    """The judge response could not be parsed into valid scores."""


class JudgeScores(_JudgeScoresBase):
    rationale: str = ""


def build_judge_prompt(
    prompt: str,
    expected_behavior: str,
    response: str,
    reference_answer: str | None = None,
) -> str:
    reference_block = (
        REFERENCE_BLOCK_TEMPLATE.format(reference_answer=reference_answer)
        if reference_answer
        else ""
    )
    return JUDGE_PROMPT_TEMPLATE.format(
        prompt=prompt,
        expected_behavior=expected_behavior,
        response=response,
        reference_block=reference_block,
    )


def parse_judge_response(text: str) -> JudgeScores:
    cleaned = strip_code_fences(text)
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        block = _extract_first_json_object(cleaned)
        if block is None:
            raise JudgeParseError("no JSON object found in judge response") from None
        try:
            obj = json.loads(block)
        except json.JSONDecodeError as err:
            raise JudgeParseError(f"judge JSON does not parse: {err}") from err
    if not isinstance(obj, dict):
        raise JudgeParseError("judge response is not a JSON object")
    scores: dict[str, int] = {}
    for key in _REQUIRED_KEYS:
        if key not in obj:
            raise JudgeParseError(f"judge response is missing key {key!r}")
        scores[key] = _coerce_score(key, obj[key])
    rationale = obj.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = str(rationale)
    return JudgeScores(**scores, rationale=rationale)


def _coerce_score(key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JudgeParseError(f"judge score {key!r} is not a number: {value!r}")
    return max(1, min(5, int(round(float(value)))))


def _extract_first_json_object(text: str) -> str | None:
    """Return the first balanced top-level {...} block, string-literal aware."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            elif ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None
