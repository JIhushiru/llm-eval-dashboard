"""Demo data seeder: ``python -m app.seed [--no-runs] [--force]``.

Creates two demo suites (10 cases each) and, unless ``--no-runs``, four
back-dated synthetic completed runs per suite (prompt versions v1-v4) with a
deliberate v4 regression for one model so the dashboard shows a red alert.
All randomness comes from ``random.Random(42)`` so output is reproducible.
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import CaseResult, Run, Suite, TestCase, utcnow
from app.services.checks import checks_passed, run_checks

_DEMO_MODELS: tuple[str, str] = ("anthropic:claude-opus-4-8", "openai:gpt-4o-mini")
_DEMO_JUDGE: str = "anthropic:claude-opus-4-8"
_REGRESSED_MODEL: str = "openai:gpt-4o-mini"

# (prompt_version, days back-dated from now)
_RUN_SCHEDULE: tuple[tuple[str, int], ...] = (("v1", 7), ("v2", 5), ("v3", 3), ("v4", 1))

# Per-run per-model target mean judge score. The v4 drop for the regressed
# model (~4.3 -> ~3.1) is deliberate: with 10 cases per run the 95% bootstrap
# CIs stop overlapping and history.py flags a regression.
_TARGET_MEANS: dict[str, dict[str, float]] = {
    "anthropic:claude-opus-4-8": {"v1": 4.0, "v2": 4.1, "v3": 4.2, "v4": 4.3},
    "openai:gpt-4o-mini": {"v1": 3.9, "v2": 4.1, "v3": 4.3, "v4": 3.1},
}
_SCORE_SIGMA: float = 0.45
_JUDGE_DIMENSIONS: tuple[str, str, str] = ("correctness", "relevance", "instruction_following")

# Padding used to make degraded summarization responses blow the max_length check.
_VERBOSE_FILLER: str = (
    " It should also be noted, at considerable and frankly unnecessary length, that the"
    " article touches on a number of secondary themes, background details, and contextual"
    " considerations that a concise two-sentence summary would normally omit entirely."
)


@dataclass(frozen=True)
class DemoCase:
    """Seed definition for one test case plus the material for synthetic responses."""

    kind: str  # "summarization" | "extraction"
    prompt: str
    expected_behavior: str
    reference_answer: str | None
    tags: list[str]
    assertions: list[dict[str, Any]]
    demo_answer: str = ""  # good response body (summarization); marker appended later
    payload: dict[str, str | None] | None = None  # gold extraction object (extraction)


# --------------------------------------------------------------------------
# Suite 1: Article Summarization
# --------------------------------------------------------------------------

def _summarization_case(
    *,
    article: str,
    instruction: str,
    expected_behavior: str,
    keyword: str,
    max_chars: int,
    topic_tag: str,
    demo_answer: str,
    reference_answer: str | None = None,
    extra_assertions: Sequence[dict[str, Any]] = (),
) -> DemoCase:
    assertions: list[dict[str, Any]] = [
        {"type": "max_length", "max_chars": max_chars},
        {"type": "contains", "value": keyword},
        *extra_assertions,
    ]
    return DemoCase(
        kind="summarization",
        prompt=f"{article}\n\n{instruction}",
        expected_behavior=expected_behavior,
        reference_answer=reference_answer,
        tags=["summarization", "news", topic_tag],
        assertions=assertions,
        demo_answer=demo_answer,
    )


SUMMARIZATION_CASES: list[DemoCase] = [
    _summarization_case(
        article=(
            "Aurora Fabrication, a five-year-old semiconductor startup based in Eindhoven, "
            "said on Tuesday it has begun pilot production of its low-power AI accelerator "
            "chip, the AF-200, at a converted research fab it acquired last year. The company "
            "claims the chip delivers inference performance comparable to mainstream "
            "data-center GPUs while drawing roughly a third of the power, a figure it "
            "attributes to an unusual asynchronous circuit design that eliminates the global "
            "clock signal. Analysts caution that pilot production is a long way from "
            "commercial volume, and that the company must still prove its yields at scale. "
            "Aurora has raised 340 million euros to date and employs about 280 people. Chief "
            "executive Mireille Dekker said the first evaluation boards will ship to twelve "
            "early-access customers in the autumn, with volume production targeted for late "
            "next year if yield targets are met."
        ),
        instruction="Summarize the article above in at most 2 sentences.",
        expected_behavior=(
            "A faithful summary of no more than two sentences that mentions Aurora "
            "Fabrication's pilot production of the AF-200 chip and its claimed power "
            "efficiency, without inventing figures or exceeding the length limit."
        ),
        keyword="chip",
        max_chars=500,
        topic_tag="tech",
        demo_answer=(
            "Semiconductor startup Aurora Fabrication has begun pilot production of its "
            "AF-200 AI accelerator chip, which it claims matches mainstream GPU inference "
            "performance at roughly a third of the power. Evaluation boards ship to twelve "
            "early-access customers this autumn, with volume production targeted for late "
            "next year."
        ),
        reference_answer=(
            "Aurora Fabrication started pilot production of the AF-200, a low-power AI "
            "accelerator it says rivals data-center GPUs at about one third of the power "
            "draw. Twelve early-access customers receive evaluation boards in the autumn, "
            "with volume production planned for late next year if yields hold."
        ),
        extra_assertions=[{"type": "not_contains", "value": "as an AI"}],
    ),
    _summarization_case(
        article=(
            "Marine biologists working off the coast of northern Sulawesi have documented an "
            "unexpected recovery in a coral reef system that was severely bleached during the "
            "2023 heat wave. In a study published this week, the team reports that "
            "fast-growing Acropora colonies have regained nearly 60 percent of their "
            "pre-bleaching cover in under three years, aided by unusually stable water "
            "temperatures and a ban on anchor mooring introduced by local authorities. The "
            "researchers stress that the recovery is fragile: a single severe warming event "
            "could undo the gains, and slower-growing massive corals have shown little "
            "improvement. Still, the findings suggest that well-enforced local protections "
            "can meaningfully improve a reef's odds of bouncing back, a conclusion with "
            "implications for marine park management across the region."
        ),
        instruction="In at most two sentences, summarize the key findings of the article above.",
        expected_behavior=(
            "No more than two sentences covering the roughly 60 percent coral recovery and "
            "the researchers' caveat that the gains are fragile; no invented statistics."
        ),
        keyword="coral",
        max_chars=480,
        topic_tag="science",
        demo_answer=(
            "A reef system off northern Sulawesi has regained nearly 60 percent of its "
            "pre-bleaching coral cover in under three years, helped by stable temperatures "
            "and a local anchoring ban. Researchers warn the recovery remains fragile and "
            "could be undone by a single severe warming event."
        ),
        reference_answer=(
            "Fast-growing corals off northern Sulawesi have recovered almost 60 percent of "
            "their pre-bleaching cover within three years, aided by stable temperatures and "
            "a local anchoring ban. The gains are fragile and could be reversed by one "
            "severe warming event."
        ),
    ),
    _summarization_case(
        article=(
            "Kenyan runner Amos Kiprotich shattered the course record at the Valencia "
            "Marathon on Sunday, crossing the line in 2:02:41, some 38 seconds inside the "
            "previous best set in 2022. The 26-year-old, contesting only his third marathon, "
            "surged clear of the lead pack at the 32-kilometre mark and ran the closing "
            "stretch alone into a light headwind. Organizers credited cooler-than-usual "
            "conditions and a revised pacing plan that kept the leaders on record schedule "
            "through halfway. In the women's race, Ethiopia's Tigist Bekele defended her "
            "title in 2:17:55 after a sprint finish decided by three seconds. Kiprotich's "
            "manager confirmed the runner will now target the world record at a spring "
            "marathon, with Berlin and London both under consideration. Sunday's field "
            "included forty-one runners who finished inside two hours and ten minutes, the "
            "deepest elite field in the race's history."
        ),
        instruction="Summarize this article in no more than 2 sentences.",
        expected_behavior=(
            "At most two sentences, mentioning Kiprotich's course record of 2:02:41 at the "
            "Valencia Marathon; secondary details optional but nothing fabricated."
        ),
        keyword="marathon",
        max_chars=450,
        topic_tag="sports",
        demo_answer=(
            "Amos Kiprotich broke the Valencia Marathon course record in 2:02:41, pulling "
            "away at the 32-kilometre mark in only his third marathon. He will target the "
            "world record at a spring marathon next year."
        ),
    ),
    _summarization_case(
        article=(
            "Norway's central bank held its policy rate at 4.25 percent on Thursday but "
            "surprised markets by signalling that the first cut could come as early as "
            "March, months ahead of what most economists had pencilled in. Governor Ida "
            "Braathen told reporters that underlying inflation had cooled faster than the "
            "bank's December projections, easing to 3.1 percent in the latest reading, while "
            "a stronger krone had reduced imported price pressure. Bond yields fell sharply "
            "on the announcement and the krone weakened against the euro. Analysts at two "
            "Nordic banks moved their rate-cut forecasts forward within hours of the press "
            "conference, though several cautioned that persistent wage growth, running near "
            "5 percent, could yet delay the timetable. The bank's updated projections imply "
            "three quarter-point cuts before the end of the year, which would leave the "
            "policy rate at 3.5 percent going into the following spring."
        ),
        instruction="Provide a summary of the article above in at most two sentences.",
        expected_behavior=(
            "Two sentences at most: rate held at 4.25 percent with an earlier-than-expected "
            "cut signalled; may note the market reaction or wage-growth caveat. No "
            "editorializing or investment advice."
        ),
        keyword="rate",
        max_chars=480,
        topic_tag="finance",
        demo_answer=(
            "Norway's central bank kept its policy rate at 4.25 percent but signalled a "
            "first cut could come as early as March, citing faster-than-expected cooling in "
            "underlying inflation. Markets reacted with falling bond yields and a weaker "
            "krone, though strong wage growth could still delay the timetable."
        ),
        extra_assertions=[{"type": "not_contains", "value": "financial advice"}],
    ),
    _summarization_case(
        article=(
            "A longitudinal study tracking more than 12,000 adults across eight years has "
            "found that irregular sleep timing may matter as much for cardiovascular health "
            "as how long people sleep. Participants whose bedtimes varied by more than 90 "
            "minutes from night to night had a 26 percent higher incidence of major cardiac "
            "events than those with consistent schedules, even when both groups averaged "
            "seven hours of sleep. The association held after adjusting for age, smoking, "
            "body-mass index and shift work. The researchers propose that erratic schedules "
            "disrupt circadian regulation of blood pressure and glucose metabolism. They "
            "caution that the study is observational and cannot prove causation, but note "
            "the effect size rivals that of several established risk factors. Sleep "
            "specialists not involved in the work said the findings support treating a "
            "regular bedtime as a legitimate public-health target rather than a lifestyle "
            "nicety."
        ),
        instruction="Summarize the article above in at most 2 sentences, preserving the key caveat.",
        expected_behavior=(
            "At most two sentences: irregular bedtimes linked to 26 percent more cardiac "
            "events independent of sleep duration, and the observational/no-causation "
            "caveat must be preserved."
        ),
        keyword="sleep",
        max_chars=500,
        topic_tag="health",
        demo_answer=(
            "An eight-year study of over 12,000 adults found that bedtimes varying by more "
            "than 90 minutes were linked to a 26 percent higher rate of major cardiac "
            "events, independent of sleep duration. The authors caution the study is "
            "observational and cannot prove causation."
        ),
        reference_answer=(
            "Adults whose bedtimes varied by more than 90 minutes had 26 percent more major "
            "cardiac events over eight years than consistent sleepers, regardless of sleep "
            "duration. As an observational study, it cannot establish causation."
        ),
        extra_assertions=[{"type": "not_contains", "value": "as an AI"}],
    ),
    _summarization_case(
        article=(
            "The city of Rotterdam has completed the conversion of a 14-hectare disused rail "
            "yard into a freshwater wetland, the largest urban rewilding project in the "
            "Netherlands to date. Over three years, engineers broke up the concrete apron, "
            "re-contoured the ground to hold rainwater, and planted more than 60,000 native "
            "reeds, willows and marsh marigolds. Early monitoring has recorded 87 bird "
            "species on the site, including bitterns and bearded reedlings absent from the "
            "city for decades, along with a resident population of grass snakes. The wetland "
            "also serves a practical purpose: it can store roughly 30 million litres of "
            "stormwater, easing pressure on the surrounding district's drainage during "
            "cloudbursts. City officials say maintenance costs are about a fifth of those "
            "for a conventional park, and two further conversions of industrial land are "
            "now in planning."
        ),
        instruction="Summarize the article above in at most two sentences.",
        expected_behavior=(
            "No more than two sentences naming Rotterdam and the rail-yard-to-wetland "
            "conversion; ecological or stormwater details welcome but accurate."
        ),
        keyword="Rotterdam",
        max_chars=480,
        topic_tag="environment",
        demo_answer=(
            "Rotterdam has turned a 14-hectare disused rail yard into the Netherlands' "
            "largest urban wetland, now home to 87 recorded bird species. The site can also "
            "store about 30 million litres of stormwater and costs far less to maintain "
            "than a conventional park."
        ),
    ),
    _summarization_case(
        article=(
            "Finland's education ministry has announced a nationwide revision of the "
            "upper-secondary curriculum that will make a course in applied artificial "
            "intelligence compulsory from autumn 2027. The course, developed with three "
            "Finnish universities, focuses less on programming than on critical use: "
            "students will learn how machine-learning systems are trained, where their "
            "outputs fail, and how to evaluate AI-generated text and images encountered in "
            "daily life. Teachers will receive 40 hours of paid training, and the ministry "
            "has budgeted 28 million euros for materials and instructor support over four "
            "years. The plan drew broad support in parliament, though the teachers' union "
            "warned that the training allocation is too small for schools in remote "
            "municipalities. Ministry officials pointed to a pilot programme in 60 schools "
            "where, they said, students' ability to identify fabricated content improved "
            "markedly within a single term."
        ),
        instruction="In two sentences or fewer, summarize the article above.",
        expected_behavior=(
            "At most two sentences: compulsory applied-AI course in Finland's "
            "upper-secondary curriculum from autumn 2027, oriented to critical use; may "
            "note teacher training or the union's objection."
        ),
        keyword="curriculum",
        max_chars=520,
        topic_tag="education",
        demo_answer=(
            "Finland will make an applied artificial intelligence course compulsory in "
            "upper-secondary schools from autumn 2027, focusing on critical use rather than "
            "programming. The revised curriculum includes paid teacher training, though the "
            "union says the allocation is too small for remote schools."
        ),
    ),
    _summarization_case(
        article=(
            "The privately built lunar lander Selene-2 touched down in the Mare Nubium "
            "region early on Friday, making its operator, the Kyoto-based firm Tsukiyomi "
            "Aerospace, the second private company to achieve a fully soft landing on the "
            "Moon. Telemetry confirmed the craft settled within 40 metres of its target "
            "point, a precision the company attributes to a new terrain-relative navigation "
            "camera. Selene-2 carries four payloads, including a drill designed to extract a "
            "30-centimetre regolith core and a French-built radiation dosimeter intended to "
            "gather data for future crewed missions. The lander is expected to operate for "
            "one lunar day, roughly fourteen Earth days, before the freezing lunar night "
            "ends the mission. A first attempt by the same company two years ago ended in a "
            "crash caused by a software fault in the altitude estimator, a failure engineers "
            "say directly shaped the redesigned descent system."
        ),
        instruction="Summarize the article above in at most 2 sentences.",
        expected_behavior=(
            "Two sentences at most: Selene-2's soft lunar landing (second private company) "
            "and something of its payload or mission duration; no invented specifics."
        ),
        keyword="lunar",
        max_chars=480,
        topic_tag="space",
        demo_answer=(
            "Tsukiyomi Aerospace's Selene-2 lander touched down softly in the Mare Nubium, "
            "landing within 40 metres of its target and making the firm the second private "
            "company to soft-land on the Moon. It will run four payloads, including a "
            "regolith drill, for about one lunar day."
        ),
        reference_answer=(
            "Selene-2 soft-landed within 40 metres of its Mare Nubium target, making "
            "Tsukiyomi Aerospace the second private firm to land on the Moon. Its four "
            "payloads will operate for about one lunar day."
        ),
    ),
    _summarization_case(
        article=(
            "Vertical-farming company Skyfield Greens has begun supplying supermarket "
            "chains in the north of England with strawberries grown entirely indoors, a "
            "first for the UK at commercial scale. The company's converted warehouse "
            "outside Leeds stacks growing trays twelve layers high under tuned LED "
            "lighting, and the firm says the facility produces fruit year-round using 90 "
            "percent less water than field cultivation and no pesticides. The strawberries "
            "reach shelves within 24 hours of picking, against a typical three to five days "
            "for imported fruit in winter. Critics of vertical farming point to its "
            "electricity consumption, which Skyfield acknowledges is the operation's "
            "largest cost, though it has signed a power-purchase agreement tied to two "
            "Yorkshire wind farms. The company plans a second site near Glasgow and says "
            "winter retail prices should match those of imported Spanish fruit within two "
            "seasons if energy costs stay stable."
        ),
        instruction="Summarize this article in at most two sentences.",
        expected_behavior=(
            "At most two sentences: indoor-grown strawberries reaching UK supermarkets at "
            "commercial scale; should reflect at least one trade-off (energy cost) or "
            "benefit (water/pesticides) accurately."
        ),
        keyword="strawberr",
        max_chars=550,
        topic_tag="agriculture",
        demo_answer=(
            "Skyfield Greens is now supplying UK supermarkets with strawberries grown "
            "year-round in a twelve-layer vertical farm near Leeds, using 90 percent less "
            "water and no pesticides. Electricity remains its biggest cost, mitigated by a "
            "wind-power purchase agreement, and a second site is planned near Glasgow."
        ),
        extra_assertions=[{"type": "not_contains", "value": "as an AI"}],
    ),
    _summarization_case(
        article=(
            "Istanbul's ferry operator has taken delivery of the first three vessels in a "
            "planned fleet of fifteen fully electric passenger ferries, marking the largest "
            "single order of battery-powered ferries in the Mediterranean region. Each "
            "42-metre vessel carries up to 450 passengers across the Bosphorus and "
            "recharges in under ten minutes at automated shore stations installed at four "
            "terminals. The operator estimates the electric fleet will cut its diesel "
            "consumption by 11,000 tonnes a year once all fifteen vessels enter service by "
            "2028. Trial crossings this spring recorded noise levels inside the cabin at "
            "roughly half those of the diesel boats they replace, a change crews say "
            "passengers noticed immediately. The project is financed jointly by the "
            "municipality and a European development bank, with the loan terms tied to "
            "verified emissions reductions. Two additional shore stations are planned on "
            "the Asian side next year."
        ),
        instruction="Summarize the article above in no more than two sentences.",
        expected_behavior=(
            "No more than two sentences: Istanbul's first electric ferries delivered out of "
            "a fleet of fifteen, with an accurate supporting detail such as the diesel "
            "savings or charging time."
        ),
        keyword="ferr",
        max_chars=460,
        topic_tag="transport",
        demo_answer=(
            "Istanbul has received the first three of fifteen planned fully electric "
            "passenger ferries, each carrying up to 450 passengers and recharging in under "
            "ten minutes. The full fleet is expected to cut diesel use by 11,000 tonnes a "
            "year by 2028."
        ),
    ),
]


# --------------------------------------------------------------------------
# Suite 2: Contact JSON Extraction
# --------------------------------------------------------------------------

def _extraction_case(
    *, blurb: str, payload: dict[str, str | None], topic_tag: str
) -> DemoCase:
    keys = ", ".join(payload)
    prompt = (
        f"{blurb}\n\nExtract the contact details from the text above and reply with ONLY "
        f"a JSON object with exactly these keys: {keys}. Use null for any value not "
        "present in the text."
    )
    expected = (
        f"A valid JSON object with exactly the keys {keys}; values copied verbatim from "
        "the text, null where a value is missing, and no prose or code fences around the "
        "JSON."
    )
    assertions: list[dict[str, Any]] = [
        {"type": "json_valid"},
        {"type": "contains", "value": '"name"'},
        {"type": "contains", "value": '"email"'},
    ]
    return DemoCase(
        kind="extraction",
        prompt=prompt,
        expected_behavior=expected,
        reference_answer=json.dumps(payload, indent=2, ensure_ascii=False),
        tags=["extraction", "json", topic_tag],
        assertions=assertions,
        payload=payload,
    )


EXTRACTION_CASES: list[DemoCase] = [
    _extraction_case(
        blurb=(
            "Thanks again for the quick turnaround on the audit. Let's reconnect after the "
            "board meeting next month. -- Priya Raghavan, Chief Financial Officer, Meridian "
            "Textiles Ltd. | priya.raghavan@meridiantextiles.com | +44 20 7946 0301"
        ),
        payload={
            "name": "Priya Raghavan",
            "email": "priya.raghavan@meridiantextiles.com",
            "company": "Meridian Textiles Ltd.",
            "role": "Chief Financial Officer",
            "phone": "+44 20 7946 0301",
        },
        topic_tag="email-signature",
    ),
    _extraction_case(
        blurb=(
            "Voicemail transcript, 09:42: Hi, this is Marcus Webb calling from Northgate "
            "Logistics about the warehouse lease renewal. Best way to reach me is "
            "marcus.webb@northgatelog.com, or my cell, 555-0177. Talk soon."
        ),
        payload={
            "name": "Marcus Webb",
            "email": "marcus.webb@northgatelog.com",
            "company": "Northgate Logistics",
            "phone": "555-0177",
        },
        topic_tag="voicemail",
    ),
    _extraction_case(
        blurb=(
            "Our next speaker flew in from Nairobi this morning: please welcome Dr. Wanjiru "
            "Maathai, head of research at the Savannah Data Collective. She answers email "
            "at w.maathai@savannahdata.org and is happy to take questions after the talk."
        ),
        payload={
            "name": "Wanjiru Maathai",
            "email": "w.maathai@savannahdata.org",
            "company": "Savannah Data Collective",
            "role": "head of research",
            "location": "Nairobi",
        },
        topic_tag="event",
    ),
    _extraction_case(
        blurb=(
            "Ticket #8841: customer reports sync failures on the mobile app after the last "
            "release. Reported by Tomas Lindgren (tomas.lindgren@fjordbank.no) of the "
            "platform team at Fjordbank, severity 2. Callback number +47 921 44 318."
        ),
        payload={
            "name": "Tomas Lindgren",
            "email": "tomas.lindgren@fjordbank.no",
            "company": "Fjordbank",
            "phone": "+47 921 44 318",
        },
        topic_tag="support",
    ),
    _extraction_case(
        blurb=(
            "Met Elena Petrova at the Lisbon fintech meetup last night. She runs developer "
            "relations at PayLoom and mentioned they are hiring. Her card lists "
            "elena@payloom.io and the site payloom.io."
        ),
        payload={
            "name": "Elena Petrova",
            "email": "elena@payloom.io",
            "company": "PayLoom",
            "role": "developer relations",
            "website": "payloom.io",
        },
        topic_tag="networking",
    ),
    _extraction_case(
        blurb=(
            "New inquiry via the website contact form: Jordan Ellis is asking about the "
            "two-bedroom listing on Maple Court and whether pets are allowed. No company "
            "given. Reply-to address is jellis1987@gmail.com; the phone field was left "
            "blank."
        ),
        payload={
            "name": "Jordan Ellis",
            "email": "jellis1987@gmail.com",
            "company": None,
            "phone": None,
        },
        topic_tag="web-form",
    ),
    _extraction_case(
        blurb=(
            "This week's guest needs no introduction: Sam Okafor, founder and CEO of the "
            "climate-analytics startup TerraSignal, joining us from Lagos. You can reach "
            "Sam at sam@terrasignal.co with questions about the episode."
        ),
        payload={
            "name": "Sam Okafor",
            "email": "sam@terrasignal.co",
            "company": "TerraSignal",
            "role": "founder and CEO",
            "location": "Lagos",
        },
        topic_tag="podcast",
    ),
    _extraction_case(
        blurb=(
            "INVOICE #2024-118. Billed to: Hana Yoshida, procurement lead, Kite & Anchor "
            "Brewing Co., hana.yoshida@kiteanchor.jp. Payment due within 30 days of the "
            "invoice date. Purchase order reference KA-7719."
        ),
        payload={
            "name": "Hana Yoshida",
            "email": "hana.yoshida@kiteanchor.jp",
            "company": "Kite & Anchor Brewing Co.",
            "role": "procurement lead",
        },
        topic_tag="invoice",
    ),
    _extraction_case(
        blurb=(
            "Application received for the senior data engineer role. Applicant: Gabriel "
            "Fonseca, currently at Riverbed Analytics in Sao Paulo; contact "
            "gfonseca@riverbedanalytics.com or via the referral portal. Screening call to "
            "be scheduled this week."
        ),
        payload={
            "name": "Gabriel Fonseca",
            "email": "gfonseca@riverbedanalytics.com",
            "company": "Riverbed Analytics",
            "location": "Sao Paulo",
        },
        topic_tag="recruiting",
    ),
    _extraction_case(
        blurb=(
            "Per our call, the counterparty's point of contact for the licensing agreement "
            "is Ingrid Sorensen, general counsel at Polaris Media Group "
            "(i.sorensen@polarismedia.dk, office +45 33 12 88 00). She expects the redlined "
            "draft by Friday."
        ),
        payload={
            "name": "Ingrid Sorensen",
            "email": "i.sorensen@polarismedia.dk",
            "company": "Polaris Media Group",
            "role": "general counsel",
            "phone": "+45 33 12 88 00",
        },
        topic_tag="legal",
    ),
]


# --------------------------------------------------------------------------
# Synthetic run generation
# --------------------------------------------------------------------------

def _find_max_chars(assertions: Sequence[dict[str, Any]]) -> int | None:
    for assertion in assertions:
        if assertion.get("type") == "max_length" and assertion.get("max_chars") is not None:
            return int(assertion["max_chars"])
    return None


def _demo_response(case: DemoCase, model: str, version: str, degrade: bool) -> str:
    marker = f"[synthetic demo response - {model}, {version}]"
    if case.kind == "extraction":
        payload = case.payload if case.payload is not None else {}
        # The extra "_note" key keeps json_valid/contains checks passing while
        # still clearly marking the response as synthetic.
        body = json.dumps({**payload, "_note": marker}, indent=2, ensure_ascii=False)
        if degrade:
            # Prose before the JSON makes json_valid fail (regression realism).
            return f"Sure! Here is the extracted contact information:\n\n{body}"
        return body
    if degrade:
        # Pad past the max_length budget so the check fails.
        limit = _find_max_chars(case.assertions) or 600
        padded = case.demo_answer
        while len(padded) <= limit + 80:
            padded += _VERBOSE_FILLER
        return f"{padded}\n\n{marker}"
    return f"{case.demo_answer}\n\n{marker}"


def _draw_judge_scores(rng: random.Random, target: float) -> dict[str, int]:
    return {
        dimension: max(1, min(5, round(rng.gauss(target, _SCORE_SIGMA))))
        for dimension in _JUDGE_DIMENSIONS
    }


def _rationale(overall: float, degraded: bool) -> str:
    if degraded:
        return (
            "[demo data] The response ignores the format or length constraint and drifts "
            "from the requested output, dragging down instruction following and "
            "correctness. Synthetic rationale generated for dashboard demonstration."
        )
    if overall >= 4.5:
        return (
            "[demo data] Accurate, tightly scoped, and fully compliant with the stated "
            "constraints. Synthetic rationale generated for dashboard demonstration."
        )
    if overall >= 3.5:
        return (
            "[demo data] Largely faithful to the source with only minor omissions, and it "
            "respects the format constraints. Synthetic rationale generated for dashboard "
            "demonstration."
        )
    if overall >= 2.5:
        return (
            "[demo data] Captures part of the task but misses key details or bends a "
            "constraint. Synthetic rationale generated for dashboard demonstration."
        )
    return (
        "[demo data] Substantially incomplete or off-target for the task as specified. "
        "Synthetic rationale generated for dashboard demonstration."
    )


def _seed_runs(
    session: Session,
    suite: Suite,
    demo_cases: Sequence[DemoCase],
    orm_cases: Sequence[TestCase],
    rng: random.Random,
    now: datetime,
) -> tuple[int, int]:
    """Create the four back-dated synthetic completed runs for one suite."""
    runs_created = 0
    results_created = 0
    for version, days_ago in _RUN_SCHEDULE:
        created_at = now - timedelta(days=days_ago)
        run = Run(
            suite_id=suite.id,
            prompt_version=version,
            prompt_template=None,
            models=list(_DEMO_MODELS),
            judge_model=_DEMO_JUDGE,
            status="completed",
            created_at=created_at,
            completed_at=created_at + timedelta(seconds=rng.uniform(90.0, 300.0)),
        )
        session.add(run)
        session.flush()
        for demo_case, orm_case in zip(demo_cases, orm_cases, strict=True):
            for model in _DEMO_MODELS:
                target = _TARGET_MEANS[model][version]
                degrade = (
                    model == _REGRESSED_MODEL and version == "v4" and rng.random() < 0.4
                )
                response = _demo_response(demo_case, model, version, degrade)
                check_results = run_checks(response, demo_case.assertions)
                # Degraded cases score a bit lower, but the shift is kept small so
                # the realized v4 mean stays near the spec's ~3.1 target.
                scores = _draw_judge_scores(rng, target - 0.2 if degrade else target)
                overall = sum(scores.values()) / len(scores)
                session.add(
                    CaseResult(
                        run_id=run.id,
                        case_id=orm_case.id,
                        model=model,
                        response_text=response,
                        error=None,
                        latency_ms=round(rng.uniform(400.0, 2500.0), 1),
                        input_tokens=max(1, len(demo_case.prompt) // 4 + rng.randint(-12, 12)),
                        output_tokens=max(1, len(response) // 4 + rng.randint(-6, 6)),
                        retries=1 if rng.random() < 0.06 else 0,
                        checks=[check.model_dump() for check in check_results],
                        checks_passed=checks_passed(check_results),
                        judge_scores=scores,
                        judge_rationale=_rationale(overall, degrade),
                        judge_error=None,
                        created_at=created_at + timedelta(seconds=rng.uniform(5.0, 90.0)),
                    )
                )
                results_created += 1
        runs_created += 1
    return runs_created, results_created


# --------------------------------------------------------------------------
# Seeding entry point
# --------------------------------------------------------------------------

_SUITE_DEFINITIONS: tuple[tuple[str, str, list[DemoCase]], ...] = (
    (
        "Article Summarization",
        "Ten short news-style articles, each to be summarized in at most two sentences. "
        "Exercises faithfulness, brevity, and instruction following.",
        SUMMARIZATION_CASES,
    ),
    (
        "Contact JSON Extraction",
        "Ten free-text blurbs from which contact details must be extracted as strict "
        "JSON. Exercises structured output and schema adherence.",
        EXTRACTION_CASES,
    ),
)


def _seed_suite(
    session: Session,
    name: str,
    description: str,
    demo_cases: Sequence[DemoCase],
    force: bool,
) -> tuple[Suite, list[TestCase]] | None:
    """Create the suite and its cases; returns None when skipped (already exists)."""
    existing = session.scalar(select(Suite).where(Suite.name == name))
    if existing is not None:
        if not force:
            print(f"Suite '{name}' already exists - skipping (use --force to recreate).")
            return None
        session.delete(existing)  # ORM cascade removes cases, runs, and results
        session.flush()
        print(f"Suite '{name}' already existed - deleted for --force recreate.")
    suite = Suite(name=name, description=description)
    session.add(suite)
    session.flush()
    orm_cases = [
        TestCase(
            suite_id=suite.id,
            prompt=case.prompt,
            expected_behavior=case.expected_behavior,
            reference_answer=case.reference_answer,
            tags=list(case.tags),
            assertions=[dict(assertion) for assertion in case.assertions],
        )
        for case in demo_cases
    ]
    session.add_all(orm_cases)
    session.flush()
    return suite, orm_cases


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed",
        description="Seed EvalForge with demo suites, cases, and synthetic runs.",
    )
    parser.add_argument(
        "--no-runs", action="store_true", help="seed suites and cases only (no demo runs)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="delete and recreate the demo suites if they already exist",
    )
    args = parser.parse_args(argv)

    init_db()
    rng = random.Random(42)
    now = utcnow()
    totals = {"suites": 0, "cases": 0, "runs": 0, "results": 0}

    with SessionLocal() as session:
        for name, description, demo_cases in _SUITE_DEFINITIONS:
            seeded = _seed_suite(session, name, description, demo_cases, args.force)
            if seeded is None:
                continue
            suite, orm_cases = seeded
            runs_created = 0
            results_created = 0
            if not args.no_runs:
                runs_created, results_created = _seed_runs(
                    session, suite, demo_cases, orm_cases, rng, now
                )
            session.commit()
            totals["suites"] += 1
            totals["cases"] += len(orm_cases)
            totals["runs"] += runs_created
            totals["results"] += results_created
            print(
                f"Suite '{name}': created with {len(orm_cases)} cases, "
                f"{runs_created} runs, {results_created} case results."
            )

    print("-" * 64)
    print(
        f"Seed complete: {totals['suites']} suites, {totals['cases']} cases, "
        f"{totals['runs']} runs, {totals['results']} case results created."
    )
    if totals["runs"] > 0:
        print(
            f"Demo regression: '{_REGRESSED_MODEL}' deliberately drops from a mean of "
            "~4.3 (v3) to ~3.1 (v4) so the dashboard shows a regression alert."
        )
    print(f"Database: {get_settings().evalforge_db_path}")


if __name__ == "__main__":
    main()
