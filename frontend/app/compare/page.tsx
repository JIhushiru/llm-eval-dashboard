"use client";

import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, isNetworkError, overallScore } from "@/lib/api";
import type {
  CaseResultOut,
  CompareResponse,
  RunListItem,
} from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtP, fmtScore, formatDate, truncate } from "@/lib/format";
import BackendDown from "@/components/BackendDown";

function runLabel(r: RunListItem): string {
  return `#${r.id} · ${r.suite_name} · ${r.prompt_version} · ${formatDate(
    r.created_at,
  )}`;
}

function SideResult({
  label,
  version,
  result,
}: {
  label: "A" | "B";
  version: string;
  result: CaseResultOut | null;
}) {
  return (
    <div className="min-w-0 flex-1 rounded-lg border border-hairline bg-page p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink3">
        {label} · {version}
      </div>
      {result === null ? (
        <p className="mt-2 text-sm text-ink3">No result for this model.</p>
      ) : (
        <div className="mt-2 space-y-2">
          {result.error ? (
            <p className="whitespace-pre-wrap text-sm text-critical">
              Error: {result.error}
            </p>
          ) : (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-hairline bg-surface p-2.5 font-sans text-sm text-ink">
              {result.response_text ?? ""}
            </pre>
          )}

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink2">
            {result.judge_scores ? (
              <>
                <span>
                  overall{" "}
                  <span className="font-medium text-ink">
                    {fmtScore(overallScore(result.judge_scores) ?? 0)}
                  </span>
                </span>
                <span>
                  C {result.judge_scores.correctness} · R{" "}
                  {result.judge_scores.relevance} · IF{" "}
                  {result.judge_scores.instruction_following}
                </span>
              </>
            ) : (
              <span className="text-ink3">not scored</span>
            )}
            {result.checks_passed !== null &&
              (result.checks_passed ? (
                <span className="font-medium text-good">
                  ✓ {result.checks.filter((c) => c.passed).length}/
                  {result.checks.length} checks
                </span>
              ) : (
                <span className="font-medium text-critical">
                  ✗ {result.checks.filter((c) => c.passed).length}/
                  {result.checks.length} checks
                </span>
              ))}
          </div>

          {result.judge_rationale && (
            <p className="text-xs italic text-ink2">
              {result.judge_rationale}
            </p>
          )}
          {result.judge_error && (
            <p className="text-xs text-serious">
              Judge error: {result.judge_error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ComparePage() {
  const runs = useApi<RunListItem[]>(() => api.listRuns(), []);
  const [aId, setAId] = useState<number | "">("");
  const [bId, setBId] = useState<number | "">("");
  const [model, setModel] = useState<string>("");

  const completed = useMemo(
    () => (runs.data ?? []).filter((r) => r.status === "completed"),
    [runs.data],
  );
  const runA = completed.find((r) => r.id === aId) ?? null;
  // B is limited to completed runs of the same suite once A is chosen (SPEC 10).
  const bOptions = runA
    ? completed.filter((r) => r.suite_id === runA.suite_id && r.id !== runA.id)
    : [];

  useEffect(() => {
    if (bId !== "" && !bOptions.some((r) => r.id === bId)) setBId("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aId]);

  const cmp = useApi<CompareResponse | null>(
    () =>
      aId !== "" && bId !== ""
        ? api.compare(aId, bId)
        : Promise.resolve(null),
    [aId, bId],
  );

  // Default the diff model picker to the first shared model.
  useEffect(() => {
    if (cmp.data && cmp.data.shared_models.length > 0) {
      if (!cmp.data.shared_models.includes(model)) {
        setModel(cmp.data.shared_models[0]);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmp.data]);

  const selectCls =
    "w-full rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink";

  // const capture so narrowing survives into render callbacks
  const data = cmp.data;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-ink">Compare runs</h1>

      {isNetworkError(runs.error) && <BackendDown onRetry={runs.reload} />}
      {runs.loading && <p className="text-sm text-ink3">Loading runs…</p>}

      {runs.data && (
        <section className="rounded-xl border border-hairline bg-surface p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs font-medium text-ink2">
              Run A
              <select
                value={aId}
                onChange={(e) =>
                  setAId(e.target.value === "" ? "" : Number(e.target.value))
                }
                className={selectCls}
              >
                <option value="">Select a completed run…</option>
                {completed.map((r) => (
                  <option key={r.id} value={r.id}>
                    {runLabel(r)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-ink2">
              Run B (same suite)
              <select
                value={bId}
                onChange={(e) =>
                  setBId(e.target.value === "" ? "" : Number(e.target.value))
                }
                disabled={runA === null}
                className={`${selectCls} disabled:opacity-50`}
              >
                <option value="">
                  {runA === null
                    ? "Choose run A first…"
                    : bOptions.length === 0
                      ? "No other completed runs in this suite"
                      : "Select a completed run…"}
                </option>
                {bOptions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {runLabel(r)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {completed.length === 0 && !runs.loading && (
            <p className="mt-3 text-sm text-ink3">
              Comparison needs at least two completed runs of the same suite.
            </p>
          )}
        </section>
      )}

      {cmp.loading && aId !== "" && bId !== "" && (
        <p className="text-sm text-ink3">Comparing…</p>
      )}
      {!cmp.loading && cmp.error != null && !isNetworkError(cmp.error) && (
        <p className="text-sm text-critical">{errorMessage(cmp.error)}</p>
      )}
      {isNetworkError(cmp.error) && <BackendDown onRetry={cmp.reload} />}

      {data !== null && (
        <>
          <section className="rounded-xl border border-hairline bg-surface p-5">
            <h2 className="text-sm font-semibold text-ink">
              Mann-Whitney U (per-case overall scores)
            </h2>
            <p className="mt-0.5 text-xs text-ink3">
              A = {data.run_a.prompt_version} · B ={" "}
              {data.run_b.prompt_version}
            </p>
            {data.tests.length === 0 ? (
              <p className="mt-3 text-sm text-ink3">
                No shared model has scored results on both sides.
              </p>
            ) : (
              <div className="mt-3 space-y-3">
                {data.tests.map((t) => {
                  const diff = t.mean_b - t.mean_a;
                  return (
                    <div
                      key={t.model}
                      className="rounded-lg border border-hairline p-3"
                    >
                      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                        <span className="text-sm font-semibold text-ink">
                          {t.model}
                        </span>
                        <span className="text-sm text-ink2 tabular-nums">
                          mean A{" "}
                          <span className="font-medium text-ink">
                            {fmtScore(t.mean_a)}
                          </span>{" "}
                          (n={t.n_a}) → mean B{" "}
                          <span className="font-medium text-ink">
                            {fmtScore(t.mean_b)}
                          </span>{" "}
                          (n={t.n_b})
                        </span>
                        <span
                          className={`text-sm font-medium ${
                            diff >= 0 ? "text-good" : "text-critical"
                          }`}
                        >
                          {diff >= 0 ? "▲ +" : "▼ "}
                          {diff.toFixed(2)}
                        </span>
                        <span className="text-sm text-ink2 tabular-nums">
                          U = {t.u_statistic.toFixed(1)} · p = {fmtP(t.p_value)}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm text-ink2">
                        {t.interpretation}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-ink">
                Per-case diff ({data.cases.length} cases)
              </h2>
              <label className="flex items-center gap-2 text-sm text-ink2">
                Model
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-sm text-ink"
                >
                  {data.shared_models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {data.shared_models.length === 0 ? (
              <p className="rounded-xl border border-hairline bg-surface p-6 text-center text-sm text-ink3">
                The two runs share no models.
              </p>
            ) : (
              data.cases.map((c) => {
                const side = c.results[model] ?? { a: null, b: null };
                return (
                  <div
                    key={c.case_id}
                    className="rounded-xl border border-hairline bg-surface p-4"
                  >
                    <div className="text-xs font-medium uppercase tracking-wide text-ink3">
                      Case #{c.case_id}
                    </div>
                    <p className="mt-1 text-sm text-ink">
                      {truncate(c.prompt, 240)}
                    </p>
                    <p className="mt-1 text-xs text-ink2">
                      <span className="font-medium">Expected:</span>{" "}
                      {truncate(c.expected_behavior, 200)}
                    </p>
                    <div className="mt-3 flex flex-col gap-3 md:flex-row">
                      <SideResult
                        label="A"
                        version={data.run_a.prompt_version}
                        result={side.a}
                      />
                      <SideResult
                        label="B"
                        version={data.run_b.prompt_version}
                        result={side.b}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </section>
        </>
      )}
    </div>
  );
}
