# EvalForge — Technical Specification

This document is the **binding contract** for all components. Implement exactly these
shapes. If something is ambiguous, choose the simplest interpretation consistent with
this spec and note the decision in code comments only where a constraint isn't obvious.

## 1. Overview

EvalForge is an LLM evaluation platform:
- Define **test suites** of prompts (with expected behavior, optional reference answer, tags).
- Execute **runs** of a suite against one or more LLM backends with a prompt-template version label.
- Score outputs three ways: **deterministic checks**, **LLM-as-judge** (1–5 on three dimensions
  with rationale), and **statistics** (mean, std, 95% bootstrap CI; Mann-Whitney U between runs).
- Track **regressions** over time per suite per model (non-overlapping CIs → alert).
- **Diff** two runs side-by-side per case. **Export** runs as CSV/JSON.

Layout:

```
backend/            FastAPI app (Python 3.11+ compatible; local dev uses 3.12)
  requirements.txt
  .env.example
  app/
    __init__.py
    config.py         pydantic-settings Settings (env: ANTHROPIC_API_KEY, OPENAI_API_KEY,
                      OLLAMA_BASE_URL default http://localhost:11434,
                      EVALFORGE_DB_PATH default ./evalforge.db,
                      DEFAULT_JUDGE_MODEL default "anthropic:claude-opus-4-8",
                      GENERATION_MAX_TOKENS default 1024, JUDGE_MAX_TOKENS default 1024,
                      EVALFORGE_API_TOKEN default None (auth gate; §14),
                      EVALFORGE_RATE_LIMIT_PER_MINUTE default 120 (§14),
                      EVALFORGE_USE_MIGRATIONS default False (§13))
    database.py       SQLAlchemy engine/session factory; startup runs Alembic
                      migrations when EVALFORGE_USE_MIGRATIONS else create_all
    security.py       shared-token auth dependency (§14)
    ratelimit.py      in-memory per-client rate-limit ASGI middleware (§14)
    migrations/       Alembic env + versioned revisions (§13)
    models.py         ORM models (SQLAlchemy 2.0 Mapped[] style)
    schemas.py        Pydantic v2 models for ALL API request/response bodies
    main.py           FastAPI app, CORS (allow http://localhost:3000), routers, startup
    adapters/
      __init__.py     registry: get_adapter(provider), list_backends()
      base.py         LLMAdapter ABC + GenerationResult + AdapterError
      anthropic_adapter.py
      openai_adapter.py
      ollama_adapter.py
    services/
      checks.py       deterministic assertions
      judge.py        LLM-as-judge
      stats.py        bootstrap CI, Mann-Whitney U, interpretation (numpy only)
      runner.py       async run executor (semaphore 5, retries w/ exp backoff)
      history.py      score-over-time series + regression flags
      export.py       CSV/JSON export builders
    routers/
      suites.py  cases.py  runs.py  compare.py  backends.py
    seed.py           demo data seeder (python -m app.seed)
  tests/              pytest suite
frontend/             Next.js 14 App Router + TypeScript + Tailwind + Recharts
docker-compose.yml
backend/Dockerfile  frontend/Dockerfile
README.md
```

Ports: backend **8000**, frontend **3000**. Frontend reads `NEXT_PUBLIC_API_URL`
(default `http://localhost:8000`). Never hardcode another host.

## 2. Model ID format

`"provider:model"` — provider ∈ `anthropic | openai | ollama`.
Examples: `anthropic:claude-opus-4-8`, `openai:gpt-4o-mini`, `ollama:llama3.1`.
Split on the FIRST colon only. Unknown provider → 400 on run creation.

## 3. Database schema (SQLite, SQLAlchemy 2.0)

**suites**: `id int PK`, `name str unique not null`, `description text default ""`,
`created_at datetime UTC default now`.

**test_cases**: `id PK`, `suite_id FK(suites.id, ondelete=CASCADE)`, `prompt text not null`,
`expected_behavior text not null`, `reference_answer text nullable`,
`tags JSON list[str] default []`, `assertions JSON list[Assertion] default []`,
`created_at`.

**runs**: `id PK`, `suite_id FK(suites.id, CASCADE)`, `prompt_version str not null`,
`prompt_template text nullable` (if set, must contain literal `{prompt}`; validated at creation),
`models JSON list[str] not null`, `judge_model str not null`,
`status str ∈ pending|running|completed|failed`, `error text nullable`,
`created_at`, `completed_at datetime nullable`.

**case_results**: `id PK`, `run_id FK(runs.id, CASCADE)`, `case_id FK(test_cases.id, CASCADE)`,
`model str`, `response_text text nullable`, `error text nullable`,
`latency_ms float nullable`, `input_tokens int nullable`, `output_tokens int nullable`,
`retries int default 0`,
`checks JSON list[CheckResult] default []`, `checks_passed bool nullable`
(null when case has no assertions or generation failed),
`judge_scores JSON nullable` = `{"correctness": int, "relevance": int, "instruction_following": int}`,
`judge_rationale text nullable`, `judge_error text nullable`, `created_at`.

Derived (never stored): **overall score** per case_result = mean of the three judge
dimensions (float). A case_result is "scored" iff `judge_scores` is non-null.

## 4. Assertions (deterministic checks) — `services/checks.py`

Assertion (JSON object on a test case):
```json
{"type": "contains" | "not_contains" | "regex" | "not_regex" | "json_valid" | "max_length",
 "value": "string (needle or pattern; omitted for json_valid)",
 "case_sensitive": false,          // contains/not_contains only, default false
 "max_chars": 500}                 // max_length only
```

`run_checks(response_text: str, assertions: list[Assertion]) -> list[CheckResult]`
where CheckResult = `{"type": ..., "passed": bool, "detail": "human-readable"}`.

Semantics:
- `contains` / `not_contains`: substring test; case-insensitive unless `case_sensitive`.
- `regex` / `not_regex`: `re.search` with `re.MULTILINE`. An **invalid pattern** yields
  `passed=False` with detail "invalid regex: <err>" (never raises).
- `json_valid`: strip surrounding markdown code fences (```json ... ``` or ``` ... ```)
  and whitespace, then `json.loads` must succeed.
- `max_length`: `len(response_text) <= max_chars` (characters).

`checks_passed` = all(passed) — or `None` if the assertions list is empty.

## 5. LLM-as-judge — `services/judge.py`

Judge model is configurable per run (`judge_model`, default from settings). The judge
is called through the same adapter layer with the same retry policy.

Rubric prompt (exact template; fill placeholders):

```
You are an expert evaluator of LLM outputs. Score the RESPONSE against the TASK.

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
{"correctness": <1-5>, "relevance": <1-5>, "instruction_following": <1-5>, "rationale": "<2-3 sentences>"}
```

`reference_block` = `"\nREFERENCE ANSWER (gold standard):\n<reference>\n{reference_answer}\n</reference>\n"`
when a reference answer exists, else `""`.

Parsing (`parse_judge_response(text) -> JudgeScores`):
1. Strip markdown code fences.
2. Try `json.loads` on the whole string; if that fails, extract the first balanced
   `{...}` block and parse that.
3. Require all three integer keys; coerce floats to int; **clamp to [1, 5]**.
   `rationale` optional (default "").
4. Any failure → raise `JudgeParseError`; runner stores `judge_error` and leaves scores null.

## 6. Statistics — `services/stats.py` (numpy only, no scipy)

All functions fully type-hinted, pure, unit-testable.

- `mean_std(scores: Sequence[float]) -> tuple[float, float]` — std is sample std
  (ddof=1) for n>1, else 0.0.
- `bootstrap_ci(scores, n_resamples=1000, confidence=0.95, seed=None) -> tuple[float, float]`
  — percentile method: resample with replacement (same n), take means, return
  (2.5th, 97.5th) percentiles. `np.random.default_rng(seed)`. Empty input →
  `ValueError`; single value → `(v, v)`.
- `mann_whitney_u(a, b) -> MannWhitneyResult(u_statistic: float, p_value: float)` —
  two-sided, **normal approximation with tie correction and continuity correction**:
  average ranks over the pooled sample (numpy argsort-based), U = R1 − n1(n1+1)/2,
  report `u_statistic = min(U, n1*n2 − U)`; σ² = (n1·n2/12)·((N+1) − Σ(t³−t)/(N(N−1)));
  if σ == 0 (all values identical) → p = 1.0; z = (U − n1·n2/2 ± 0.5)/σ (continuity
  correction toward the mean); p = 2·(1 − Φ(|z|)) via `math.erfc`, clipped to [0, 1].
  Empty input → `ValueError`. Document that this is the large-sample approximation.
- `interpret_p_value(p) -> str` plain-English:
  - p < 0.001 → "Highly significant difference (p < 0.001): it is very unlikely these two runs perform the same."
  - p < 0.01  → "Significant difference (p = {p:.3f}): strong evidence the runs perform differently."
  - p < 0.05  → "Statistically significant difference (p = {p:.3f}): evidence the runs perform differently at the 95% confidence level."
  - p < 0.1   → "Weak evidence of a difference (p = {p:.3f}): not significant at the 95% level; more data may clarify."
  - else      → "No statistically significant difference (p = {p:.3f}): the observed gap is consistent with chance."
- `ci_overlap(a: tuple[float,float], b: tuple[float,float]) -> bool`.

**Regression rule** (`services/history.py`): for completed runs of the same
(suite, model) ordered by `created_at`, each point gets a flag vs the previous point:
`"first"` (no predecessor), `"regression"` (CIs do NOT overlap and mean decreased),
`"improvement"` (CIs do NOT overlap and mean increased), else `"stable"`.
A run+model needs ≥ 2 scored results to produce a point. Use `seed=42` for the
bootstrap in API responses so numbers are stable across refreshes.

## 7. Adapters — `app/adapters/`

```python
class GenerationResult(BaseModel):
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None

class AdapterError(Exception): ...   # retryable failure

class LLMAdapter(ABC):
    provider: str
    def is_configured(self) -> tuple[bool, str]: ...   # (available, reason)
    async def generate(self, model: str, prompt: str, max_tokens: int) -> GenerationResult: ...
    async def list_models(self) -> list[str]: ...      # suggested models for the UI
```

- **anthropic**: `anthropic.AsyncAnthropic`. Configured iff `ANTHROPIC_API_KEY` set.
  `client.messages.create(model=..., max_tokens=..., messages=[{"role":"user","content":prompt}])`.
  Do NOT pass `temperature` (rejected on current models). Text = concatenation of
  blocks with `block.type == "text"`. Tokens from `response.usage.input_tokens/output_tokens`.
  Suggested models: `["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]`.
- **openai**: `openai.AsyncOpenAI`. Configured iff `OPENAI_API_KEY` set.
  `client.chat.completions.create(model=..., messages=[...])` (no token-cap param, for
  broad model compatibility). Tokens from `usage.prompt_tokens/completion_tokens`.
  Suggested: `["gpt-4o", "gpt-4o-mini"]`.
- **ollama**: raw `httpx.AsyncClient`. Configured = always "maybe"; availability probe is
  `GET {OLLAMA_BASE_URL}/api/tags` with a 2s timeout — reachable → available, listing the
  locally installed model names as suggestions; unreachable → unavailable with reason.
  Generate: `POST /api/generate` `{"model": m, "prompt": p, "stream": false}` (120s timeout);
  text = `json["response"]`, tokens = `prompt_eval_count`/`eval_count` when present.
- Wrap provider SDK/network errors in `AdapterError` so the runner's retry sees one type.
- `list_backends()` (used by `GET /api/backends`) returns, per provider:
  `{"provider", "available": bool, "reason": str, "models": list[str]}`. For anthropic/openai,
  `available` is key presence (no network call); for ollama it's the reachability probe.

## 8. Runner — `services/runner.py`

`async def execute_run(run_id: int) -> None`, launched via FastAPI `BackgroundTasks`.

- Set status `running`. Build (case × model) task list. `asyncio.Semaphore(5)` limits
  concurrent tasks (a task = one generation + its checks + its judge call).
- Prompt = `run.prompt_template.replace("{prompt}", case.prompt)` if template else `case.prompt`.
- **Retries**: `async def with_retries(coro_factory, attempts=3, base_delay=1.0)` —
  exponential backoff `base_delay * 2**i` plus `random.uniform(0, 0.5)` jitter, retrying
  on `AdapterError`. Count stored in `case_results.retries` (0 = first try succeeded).
- Latency = wall time of the successful generate call only, ms.
- After generation: run checks; then judge via `judge_model` (same retry policy).
  Judge failure (after retries or parse error) → store `judge_error`, keep the result.
  Generation failure after retries → store `error`, skip checks/judge.
- Persist each case_result as it completes (its own session usage is fine; SQLite is local).
- Finish: status `completed` + `completed_at` (even if some cases errored).
  Unexpected top-level exception → status `failed` + `error`.
- Run creation validates: suite exists and has ≥1 case; every model string parses and its
  provider is available; judge model's provider is available. Else 400 with clear message.

## 9. API (all JSON under `/api`; Pydantic schemas for every body)

- `GET  /api/health` → `{"status": "ok"}`
- `GET  /api/backends` → `[{provider, available, reason, models}]`
- `GET  /api/suites` → `[{id, name, description, created_at, case_count, run_count}]`
  (optional `?limit=&offset=` pagination; `X-Total-Count` header carries the
  unpaginated total. No params → full list, as before.)
- `POST /api/suites` `{name, description?}` → suite (409 on duplicate name)
- `GET  /api/suites/{id}` → suite + `cases: [...]`
- `PUT  /api/suites/{id}` `{name?, description?}` → suite
- `DELETE /api/suites/{id}` → 204
- `POST /api/suites/{id}/cases` `{prompt, expected_behavior, reference_answer?, tags?, assertions?}` → case
- `PUT  /api/cases/{case_id}` (same fields, all optional) → case
- `DELETE /api/cases/{case_id}` → 204
- `POST /api/runs` `{suite_id, models: [str] (min 1), prompt_version: str, prompt_template?: str, judge_model?: str}`
  → run (status `pending`), background execution kicked off
- `GET  /api/runs?suite_id=` → newest-first `[{id, suite_id, suite_name, prompt_version, models,
  judge_model, status, error, created_at, completed_at, progress: {total, done}}]`
  (`total` = cases×models; `done` = case_results written).
  Optional `?limit=&offset=` pagination; `X-Total-Count` header carries the
  unpaginated total (respecting the `suite_id` filter). No params → full list.
- `GET  /api/runs/{id}` → run detail: run fields + `results: [CaseResultOut]` (includes case
  prompt & expected_behavior inline) + `stats: [ModelStats]` where ModelStats =
  `{model, n_scored, mean, std, ci_low, ci_high, checks_pass_rate (0-1 or null),
    avg_latency_ms, dimensions: {correctness, relevance, instruction_following}}`
  (stats entry only when n_scored ≥ 1; CI = (mean, mean) when n_scored == 1... follow
  stats.py single-value rule; bootstrap seed=42)
- `GET  /api/runs/{id}/export.json` → attachment; full run + per-case results + stats
- `GET  /api/runs/{id}/export.csv` → attachment; one row per case_result, columns:
  `run_id, prompt_version, case_id, model, prompt, expected_behavior, response_text,
  latency_ms, input_tokens, output_tokens, retries, checks_passed, correctness, relevance,
  instruction_following, overall, judge_rationale, error` (stdlib `csv`, UTF-8)
- `GET  /api/compare?run_a=&run_b=` → both runs must be completed & same suite (else 400):
  ```
  {run_a: RunListItem, run_b: RunListItem,
   shared_models: [str],
   tests: [{model, n_a, n_b, mean_a, mean_b, u_statistic, p_value, interpretation}],
   cases: [{case_id, prompt, expected_behavior,
            results: {model: {a: CaseResultOut|null, b: CaseResultOut|null}}}]}
  ```
  `tests` uses per-case overall scores per shared model; entry only when both sides have ≥1 score.
- `GET  /api/suites/{id}/history?model=` → `{series: [{model, points: [{run_id, prompt_version,
  created_at, mean, ci_low, ci_high, n_scored, flag: first|stable|regression|improvement}]}]}`
  (all models present in the suite's completed runs unless `model` filter given)

Errors: FastAPI `HTTPException` with `detail` string; 404 for missing entities.

## 10. Frontend (Next.js 14 App Router, TypeScript strict, Tailwind, Recharts)

`lib/api.ts`: typed fetch client + TS interfaces mirroring every schema above.
`API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"`.
All data-fetching pages are client components (`"use client"`) — this dashboard is
interactive; keep it simple (no server actions). Poll run detail every 2s while
status ∈ pending|running.

Pages:
- `/` **Dashboard**: suite selector (default first suite) → stat tiles row
  (latest mean score w/ delta vs previous run, total runs, total cases, # regression
  alerts) + **score-over-time chart** (see chart spec) + regression alerts list
  (red entries linking to the offending run).
- `/suites` list + create form. `/suites/[id]` detail: edit name/description, cases
  table (prompt preview, tags, #assertions, edit/delete), add/edit case form with an
  assertions builder (type select + value/max_chars/case_sensitive inputs) and a
  comma-separated tags input, and a **Run launcher** panel: backend/model checkboxes
  built from `GET /api/backends` (unavailable providers rendered disabled with the
  reason), free-text prompt_version (required), optional prompt_template textarea
  (hint: must contain `{prompt}`), judge model select, Launch → POST /api/runs →
  navigate to `/runs/{id}`.
- `/runs` table (suite filter): status badge, models, version, progress, created; row → detail.
- `/runs/[id]` detail: header (suite, version, judge, status w/ live progress bar while
  running), per-model stats cards (mean ± CI, dimension means, checks pass rate, avg
  latency), export CSV/JSON buttons (plain `<a href>` to the API), results table grouped
  by case with one row per model — expandable to show full response, check results
  (pass/fail with detail), judge scores and rationale, error/judge_error if any.
- `/compare` two run selects (filtered to completed runs of the same suite once A chosen)
  → per-model Mann-Whitney panel (mean A vs mean B, U, p, plain-English interpretation)
  + per-case side-by-side diff with a model picker: prompt/expected once, then response A
  vs response B, judge scores + rationales, checks summary for each side.

### Chart spec (score-over-time, Recharts)

- One series per model; **fixed categorical palette in slot order (never cycled,
  color follows the model, not its rank)**:
  `#2a78d6, #1baf7a, #eda100, #008300, #4a3aa7, #e34948, #e87ba4, #eb6834`.
- Mean line 2px round; CI band = Recharts `Area` with `dataKey` returning
  `[ci_low, ci_high]`, filled with the series hue at ~10% opacity, no stroke.
- Regression points: red dot `#d03b3b` (r≈6, 2px white ring) via custom dot renderer;
  improvements `#0ca30c`; normal points series-colored r=4 with 2px surface ring.
- X = run (created_at order, tick label = prompt_version), Y domain [1, 5] fixed.
- Single y-axis only. Legend when ≥ 2 series (none for one). Tooltip on hover:
  version, date, per-series mean [ci_low–ci_high], flag. Gridlines: 1px solid
  `#e1e0d9`, recessive; axis line `#c3c2b7`; tick text `#898781` 12px.
- Text never wears the series color; labels/values use ink tokens.

### Visual system (light mode)

Page plane `#f9f9f7`; cards/chart surface `#fcfcfb` with hairline border
`rgba(11,11,11,0.10)`, radius 8–12px; primary ink `#0b0b0b`, secondary `#52514e`,
muted `#898781`. Status colors (badges/alerts only, never as series colors):
good `#0ca30c`, warning `#fab219`, serious `#ec835a`, critical `#d03b3b`.
Status badges = icon/dot + label (never color alone). Font: system-ui sans stack;
stat-tile values semibold, proportional figures; `tabular-nums` only inside tables.
Keep chrome quiet — the data is the only loud thing. Accent for interactive elements:
slot-1 blue `#2a78d6`.

## 11. Seed script — `app/seed.py` (`python -m app.seed [--no-runs] [--force]`)

- Suite **"Article Summarization"** (10 cases): each prompt embeds a short (~120–200 word)
  original article snippet with an instruction like "Summarize in at most 2 sentences.";
  expected_behavior describes faithfulness/length; assertions typically
  `max_length` (e.g. 400–600 chars) and a `contains`/`not_contains`; tags like
  `["summarization", "news"]`. Vary topics (tech, science, sports, finance, health…).
- Suite **"Contact JSON Extraction"** (10 cases): prompt gives a free-text blurb and asks
  for JSON with specific keys (name/email/company/…); expected_behavior lists required
  keys; assertions `json_valid` + `contains` for key names; tags `["extraction", "json"]`.
- Unless `--no-runs`: create **4 synthetic completed runs per suite** (prompt_versions
  v1–v4, created_at back-dated 7/5/3/1 days, models
  `["anthropic:claude-opus-4-8", "openai:gpt-4o-mini"]`, judge `anthropic:claude-opus-4-8`).
  Responses are placeholder text clearly marked `"[synthetic demo response]"`; judge
  scores drawn from `random.Random(42)` around per-run per-model target means, with a
  deliberate **regression in v4 for one model** (drop from ≈4.3 to ≈3.1) so the dashboard
  shows a red alert; plausible latency (400–2500ms) and token counts; rationale text
  labels itself as demo data.
- Idempotent: if a suite name already exists, skip it (print notice) unless `--force`
  (which deletes and recreates the demo suites only). Print a summary at the end.

## 12. Tests — `backend/tests/` (pytest, pytest-asyncio)

No network. LLM calls always mocked/faked. `conftest.py` provides a fresh temp-file
SQLite DB per test (env override + dependency override) and a FastAPI `TestClient`.

- `test_stats.py`: bootstrap — determinism with seed; band contains sample mean for
  symmetric data; width shrinks as n grows (200 vs 20 samples, same distribution);
  single value → (v, v); empty raises. Mann-Whitney — disjoint samples
  a=[1..5], b=[6..10] → U=0 and p<0.05; identical distributions → p≈1 (>0.9);
  symmetry U_a(min-side) invariance when swapping a/b; ties handled (mixed-tie case
  runs and yields 0≤p≤1); all-identical values → p=1.0; against a scipy-precomputed
  reference: a=[12,15,14,10,18], b=[22,25,19,24,28] → p within ±0.02 of 0.0122
  (scipy two-sided ties-corrected value ~0.01193... assert 0.005<p<0.03 to be robust).
  interpret_p_value thresholds; ci_overlap true/false cases.
- `test_checks.py`: every assertion type passes & fails; case sensitivity; invalid regex
  → passed=False; json_valid with fenced/bare/invalid JSON; max_length boundary;
  empty assertions → checks_passed None semantics (via runner or checks helper).
- `test_judge.py`: builds rubric prompt including/excluding reference; parses bare JSON,
  fenced JSON, JSON surrounded by prose; clamps out-of-range scores; float coercion;
  missing key / non-JSON → JudgeParseError.
- `test_runner.py` (asyncio): fake adapter with an internal gauge asserting max
  concurrency ≤ 5 across 20 tasks; flaky adapter failing twice then succeeding →
  retries==2 and success (patch `asyncio.sleep` to no-op); permanent failure → result
  row with error, run still completes; judge parse failure → judge_error set.
- `test_api.py`: suite/case CRUD flows; duplicate suite name → 409; run creation with
  unavailable provider → 400; full happy path with a monkeypatched fake adapter →
  poll run → completed, stats present; export.csv/json content sanity; compare endpoint
  (two synthetic runs) returns tests + interpretation; history endpoint flags a
  constructed regression.

Target: the scoring logic (stats/checks/judge) is the priority per the product brief.

## 13. Docker & migrations

- `backend/Dockerfile`: `python:3.11-slim`, install requirements, copy app +
  `alembic.ini` + `migrations/`, `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `frontend/Dockerfile`: `node:20-alpine`, `npm ci`, `npm run build`, `npm start`
  (port 3000). Accept `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_API_TOKEN` build args.
- `docker-compose.yml` (root): service `backend` (8000:8000, `env_file: backend/.env`
  optional via `${...:-}` or documented, volume `evalforge-data:/data` with
  `EVALFORGE_DB_PATH=/data/evalforge.db`, `EVALFORGE_USE_MIGRATIONS=true`), service
  `frontend` (3000:3000, `depends_on: backend`). One command: `docker-compose up --build`.

**Migrations (Alembic).** Schema is versioned under `backend/migrations/`. Zero-config
local dev/tests use `create_all` (idempotent). Managed deployments set
`EVALFORGE_USE_MIGRATIONS=true` so startup runs `alembic upgrade head` instead.
An existing create_all DB adopts migrations with a one-time `alembic stamp head`;
thereafter evolve schema via `alembic revision --autogenerate -m "…"` + `upgrade head`.
The initial revision `0001_initial` mirrors §3. `render_as_batch` is on for SQLite ALTERs.

## 14. Quality bar

- Python: type hints everywhere; Pydantic v2 for every API schema; SQLAlchemy 2.0
  `Mapped[]`/`mapped_column` style; no bare `except:`; module docstrings brief.
- TypeScript: `strict: true`; shared types in `lib/api.ts`; no `any` unless unavoidable.
- **Auth (opt-in shared-token gate).** Default is open (local tool). When
  `EVALFORGE_API_TOKEN` is set, every `/api` request except `GET /api/health`
  must present it as `Authorization: Bearer <token>` (or, for the plain-anchor
  export links, `?token=<token>`); otherwise 401. Constant-time compare. This
  is a coarse shared secret, not per-user auth.
- **Rate limiting.** `EVALFORGE_RATE_LIMIT_PER_MINUTE` (default 120, 0 disables)
  caps requests per client (bearer token if present, else IP) over a 60s
  sliding window; over the cap → 429 with `Retry-After`. `/api/health` is
  exempt. In-memory, per-process (single-instance tool; use Redis to scale out).
- CORS open to localhost:3000 (and it decorates 429/401 responses so the
  browser can read them).
- README (root): what it is, mermaid architecture diagram, quickstart (local dev +
  docker), screenshots placeholders, .env setup, seed instructions, and a
  **"Design decisions"** section explaining: why bootstrap percentile CIs (1000
  resamples) for 1–5 ordinal judge scores; why Mann-Whitney U (nonparametric, ordinal
  data, no normality assumption) over a t-test; the normal approximation + tie
  correction; the regression-alert rule (non-overlapping 95% CIs + direction) and its
  conservativeness; judge-model bias caveats; deterministic checks as a cheap first
  gate; concurrency/retry choices.
