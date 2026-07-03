// Typed client for the EvalForge backend API (SPEC section 9).
// All shapes mirror the backend Pydantic schemas exactly.

export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------- Shared shapes ----------

export type AssertionType =
  | "contains"
  | "not_contains"
  | "regex"
  | "not_regex"
  | "json_valid"
  | "max_length";

export interface Assertion {
  type: AssertionType;
  value?: string;
  case_sensitive?: boolean;
  max_chars?: number;
}

export interface CheckResult {
  type: string;
  passed: boolean;
  detail: string;
}

export interface JudgeScores {
  correctness: number;
  relevance: number;
  instruction_following: number;
}

export interface BackendInfo {
  provider: string;
  available: boolean;
  reason: string;
  models: string[];
}

// ---------- Suites & cases ----------

export interface SuiteListItem {
  id: number;
  name: string;
  description: string;
  created_at: string;
  case_count: number;
  run_count: number;
}

export interface TestCase {
  id: number;
  suite_id: number;
  prompt: string;
  expected_behavior: string;
  reference_answer: string | null;
  tags: string[];
  assertions: Assertion[];
  created_at: string;
}

export interface SuiteDetail {
  id: number;
  name: string;
  description: string;
  created_at: string;
  cases: TestCase[];
}

export interface SuiteCreate {
  name: string;
  description?: string;
}

export interface SuiteUpdate {
  name?: string;
  description?: string;
}

export interface CaseInput {
  prompt: string;
  expected_behavior: string;
  reference_answer?: string | null;
  tags?: string[];
  assertions?: Assertion[];
}

// ---------- Runs ----------

export type RunStatus = "pending" | "running" | "completed" | "failed";

export interface RunProgress {
  total: number;
  done: number;
}

export interface RunListItem {
  id: number;
  suite_id: number;
  suite_name: string;
  prompt_version: string;
  models: string[];
  judge_model: string;
  status: RunStatus;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  progress: RunProgress;
}

export interface RunCreate {
  suite_id: number;
  models: string[];
  prompt_version: string;
  prompt_template?: string;
  judge_model?: string;
}

// POST /api/runs returns the bare run row (status pending).
export interface Run {
  id: number;
  suite_id: number;
  prompt_version: string;
  models: string[];
  judge_model: string;
  status: RunStatus;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface CaseResultOut {
  id: number;
  run_id: number;
  case_id: number;
  model: string;
  response_text: string | null;
  error: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  retries: number;
  checks: CheckResult[];
  checks_passed: boolean | null;
  judge_scores: JudgeScores | null;
  judge_rationale: string | null;
  judge_error: string | null;
  created_at: string;
  // Inlined case fields (SPEC: run detail includes prompt & expected_behavior).
  prompt: string;
  expected_behavior: string;
}

export interface ModelStats {
  model: string;
  n_scored: number;
  mean: number;
  std: number;
  ci_low: number;
  ci_high: number;
  checks_pass_rate: number | null;
  avg_latency_ms: number | null;
  dimensions: JudgeScores;
}

export interface RunDetail {
  id: number;
  suite_id: number;
  prompt_version: string;
  prompt_template: string | null;
  models: string[];
  judge_model: string;
  status: RunStatus;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  results: CaseResultOut[];
  stats: ModelStats[];
}

// ---------- Compare ----------

export interface CompareTest {
  model: string;
  n_a: number;
  n_b: number;
  mean_a: number;
  mean_b: number;
  u_statistic: number;
  p_value: number;
  interpretation: string;
}

export interface CompareCaseSide {
  a: CaseResultOut | null;
  b: CaseResultOut | null;
}

export interface CompareCase {
  case_id: number;
  prompt: string;
  expected_behavior: string;
  results: Record<string, CompareCaseSide>;
}

export interface CompareResponse {
  run_a: RunListItem;
  run_b: RunListItem;
  shared_models: string[];
  tests: CompareTest[];
  cases: CompareCase[];
}

// ---------- History ----------

export type HistoryFlag = "first" | "stable" | "regression" | "improvement";

export interface HistoryPoint {
  run_id: number;
  prompt_version: string;
  created_at: string;
  mean: number;
  ci_low: number;
  ci_high: number;
  n_scored: number;
  flag: HistoryFlag;
}

export interface HistorySeries {
  model: string;
  points: HistoryPoint[];
}

export interface HistoryResponse {
  series: HistorySeries[];
}

// ---------- Errors ----------

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

export class NetworkError extends Error {
  constructor() {
    super(`Backend not reachable at ${API_BASE}`);
    this.name = "NetworkError";
  }
}

export function isNetworkError(e: unknown): e is NetworkError {
  return e instanceof NetworkError;
}

export function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

// ---------- Fetch helper ----------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new NetworkError();
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body: unknown = await res.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // non-JSON error body; keep the status line
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------- API surface ----------

export const api = {
  health: (): Promise<{ status: string }> => request("/api/health"),

  listBackends: (): Promise<BackendInfo[]> => request("/api/backends"),

  listSuites: (): Promise<SuiteListItem[]> => request("/api/suites"),

  createSuite: (body: SuiteCreate): Promise<SuiteListItem> =>
    request("/api/suites", { method: "POST", body: JSON.stringify(body) }),

  getSuite: (id: number): Promise<SuiteDetail> => request(`/api/suites/${id}`),

  updateSuite: (id: number, body: SuiteUpdate): Promise<SuiteListItem> =>
    request(`/api/suites/${id}`, { method: "PUT", body: JSON.stringify(body) }),

  deleteSuite: (id: number): Promise<void> =>
    request(`/api/suites/${id}`, { method: "DELETE" }),

  createCase: (suiteId: number, body: CaseInput): Promise<TestCase> =>
    request(`/api/suites/${suiteId}/cases`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateCase: (caseId: number, body: Partial<CaseInput>): Promise<TestCase> =>
    request(`/api/cases/${caseId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteCase: (caseId: number): Promise<void> =>
    request(`/api/cases/${caseId}`, { method: "DELETE" }),

  createRun: (body: RunCreate): Promise<Run> =>
    request("/api/runs", { method: "POST", body: JSON.stringify(body) }),

  listRuns: (suiteId?: number): Promise<RunListItem[]> =>
    request(
      suiteId !== undefined ? `/api/runs?suite_id=${suiteId}` : "/api/runs",
    ),

  getRun: (id: number): Promise<RunDetail> => request(`/api/runs/${id}`),

  exportUrl: (id: number, format: "csv" | "json"): string =>
    `${API_BASE}/api/runs/${id}/export.${format}`,

  compare: (runA: number, runB: number): Promise<CompareResponse> =>
    request(`/api/compare?run_a=${runA}&run_b=${runB}`),

  getHistory: (suiteId: number, model?: string): Promise<HistoryResponse> =>
    request(
      model
        ? `/api/suites/${suiteId}/history?model=${encodeURIComponent(model)}`
        : `/api/suites/${suiteId}/history`,
    ),
};

// Derived, never stored (SPEC section 3): overall = mean of the three judge dimensions.
export function overallScore(scores: JudgeScores | null): number | null {
  if (!scores) return null;
  return (
    (scores.correctness + scores.relevance + scores.instruction_following) / 3
  );
}
