"use client";

import Link from "next/link";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  api,
  errorMessage,
  isNetworkError,
  overallScore,
  ApiError,
} from "@/lib/api";
import type { CaseResultOut, RunDetail, SuiteDetail } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import {
  fmtLatency,
  fmtPct,
  fmtScore,
  formatDateTime,
  truncate,
} from "@/lib/format";
import BackendDown from "@/components/BackendDown";
import StatusBadge from "@/components/StatusBadge";

interface CaseGroup {
  caseId: number;
  prompt: string;
  expectedBehavior: string;
  rows: CaseResultOut[];
}

function ChecksCell({ result }: { result: CaseResultOut }) {
  if (result.checks_passed === null) {
    return <span className="text-ink3">—</span>;
  }
  const passed = result.checks.filter((c) => c.passed).length;
  return result.checks_passed ? (
    <span className="font-medium text-good">
      ✓ {passed}/{result.checks.length}
    </span>
  ) : (
    <span className="font-medium text-critical">
      ✗ {passed}/{result.checks.length}
    </span>
  );
}

function ResultDetail({ result }: { result: CaseResultOut }) {
  return (
    <div className="space-y-3 bg-page px-4 py-4">
      {result.error && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-critical">
            Generation error
          </h4>
          <p className="mt-1 whitespace-pre-wrap text-sm text-critical">
            {result.error}
          </p>
        </div>
      )}

      {result.response_text !== null && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink3">
            Response
          </h4>
          <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-hairline bg-surface p-3 font-sans text-sm text-ink">
            {result.response_text}
          </pre>
        </div>
      )}

      {result.checks.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink3">
            Checks
          </h4>
          <ul className="mt-1 space-y-1">
            {result.checks.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                {c.passed ? (
                  <span className="font-medium text-good">✓</span>
                ) : (
                  <span className="font-medium text-critical">✗</span>
                )}
                <span className="text-ink2">
                  <span className="font-medium text-ink">{c.type}</span> —{" "}
                  {c.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.judge_scores && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink3">
            Judge scores
          </h4>
          <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink2">
            <span>
              correctness{" "}
              <span className="font-medium text-ink">
                {result.judge_scores.correctness}
              </span>
            </span>
            <span>
              relevance{" "}
              <span className="font-medium text-ink">
                {result.judge_scores.relevance}
              </span>
            </span>
            <span>
              instruction following{" "}
              <span className="font-medium text-ink">
                {result.judge_scores.instruction_following}
              </span>
            </span>
            <span>
              overall{" "}
              <span className="font-medium text-ink">
                {fmtScore(overallScore(result.judge_scores) ?? 0)}
              </span>
            </span>
          </div>
          {result.judge_rationale && (
            <p className="mt-1.5 whitespace-pre-wrap text-sm italic text-ink2">
              {result.judge_rationale}
            </p>
          )}
        </div>
      )}

      {result.judge_error && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-serious">
            Judge error
          </h4>
          <p className="mt-1 whitespace-pre-wrap text-sm text-serious">
            {result.judge_error}
          </p>
        </div>
      )}
    </div>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = Number(params.id);

  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [reloadTick, setReloadTick] = useState(0);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  // Load, then poll every 2s while the run is pending/running (SPEC 10).
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      try {
        const r = await api.getRun(runId);
        if (cancelled) return;
        setRun(r);
        setError(null);
        setLoading(false);
        if (r.status === "pending" || r.status === "running") {
          timer = setTimeout(load, 2000);
        }
      } catch (e) {
        if (cancelled) return;
        setError(e);
        setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId, reloadTick]);

  const suite = useApi<SuiteDetail | null>(
    () => (run ? api.getSuite(run.suite_id) : Promise.resolve(null)),
    [run?.suite_id],
  );

  const groups = useMemo<CaseGroup[]>(() => {
    if (!run) return [];
    const byCase = new Map<number, CaseGroup>();
    for (const r of run.results) {
      let g = byCase.get(r.case_id);
      if (!g) {
        g = {
          caseId: r.case_id,
          prompt: r.prompt,
          expectedBehavior: r.expected_behavior,
          rows: [],
        };
        byCase.set(r.case_id, g);
      }
      g.rows.push(r);
    }
    for (const g of byCase.values()) {
      g.rows.sort((a, b) => a.model.localeCompare(b.model));
    }
    return [...byCase.values()].sort((a, b) => a.caseId - b.caseId);
  }, [run]);

  const toggleExpanded = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (loading) return <p className="text-sm text-ink3">Loading run…</p>;
  if (isNetworkError(error)) {
    return <BackendDown onRetry={() => setReloadTick((t) => t + 1)} />;
  }
  if (error instanceof ApiError && error.status === 404) {
    return <p className="text-sm text-critical">Run not found.</p>;
  }
  if (error != null) {
    return <p className="text-sm text-critical">{errorMessage(error)}</p>;
  }
  if (!run) return null;

  const live = run.status === "pending" || run.status === "running";
  const total = suite.data ? suite.data.cases.length * run.models.length : null;
  const done = run.results.length;

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl font-semibold text-ink">Run #{run.id}</h1>
            <StatusBadge status={run.status} />
          </div>
          <div className="flex gap-2">
            <a
              href={api.exportUrl(run.id, "csv")}
              className="rounded-md border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-page"
            >
              Export CSV
            </a>
            <a
              href={api.exportUrl(run.id, "json")}
              className="rounded-md border border-hairline px-3 py-1.5 text-sm font-medium text-ink hover:bg-page"
            >
              Export JSON
            </a>
          </div>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink3">
              Suite
            </dt>
            <dd className="mt-0.5">
              {suite.data ? (
                <Link
                  href={`/suites/${run.suite_id}`}
                  className="font-medium text-accent hover:underline"
                >
                  {suite.data.name}
                </Link>
              ) : (
                <span className="text-ink2">#{run.suite_id}</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink3">
              Prompt version
            </dt>
            <dd className="mt-0.5 text-ink">{run.prompt_version}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink3">
              Judge
            </dt>
            <dd className="mt-0.5 text-ink">{run.judge_model}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-ink3">
              Created
            </dt>
            <dd className="mt-0.5 text-ink2">
              {formatDateTime(run.created_at)}
              {run.completed_at &&
                ` → ${formatDateTime(run.completed_at)}`}
            </dd>
          </div>
        </dl>

        {run.prompt_template && (
          <p className="mt-3 text-xs text-ink3">
            Template:{" "}
            <code className="rounded bg-page px-1 py-0.5">
              {truncate(run.prompt_template, 160)}
            </code>
          </p>
        )}

        {live && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs text-ink2">
              <span>
                {done}
                {total !== null && `/${total}`} results
              </span>
              <span className="text-ink3">refreshing every 2s</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-page">
              <div
                className="h-full rounded-full bg-accent transition-all duration-500"
                style={{
                  width:
                    total !== null && total > 0
                      ? `${Math.min(100, (done / total) * 100)}%`
                      : "10%",
                }}
              />
            </div>
          </div>
        )}

        {run.error && (
          <p className="mt-3 rounded-md bg-critical/5 px-3 py-2 text-sm text-critical">
            {run.error}
          </p>
        )}
      </section>

      {run.stats.length > 0 && (
        <section className="grid gap-4 md:grid-cols-2">
          {run.stats.map((s) => (
            <div
              key={s.model}
              className="rounded-xl border border-hairline bg-surface p-4"
            >
              <h3 className="text-sm font-semibold text-ink">{s.model}</h3>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-semibold text-ink">
                  {fmtScore(s.mean)}
                </span>
                <span className="text-sm text-ink3">
                  95% CI {fmtScore(s.ci_low)}–{fmtScore(s.ci_high)} · n=
                  {s.n_scored}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <div>
                  <div className="text-xs text-ink3">correctness</div>
                  <div className="font-medium text-ink">
                    {fmtScore(s.dimensions.correctness)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-ink3">relevance</div>
                  <div className="font-medium text-ink">
                    {fmtScore(s.dimensions.relevance)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-ink3">instr. following</div>
                  <div className="font-medium text-ink">
                    {fmtScore(s.dimensions.instruction_following)}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-hairline pt-2 text-sm text-ink2">
                <span>
                  checks{" "}
                  <span className="font-medium text-ink">
                    {s.checks_pass_rate !== null
                      ? fmtPct(s.checks_pass_rate)
                      : "—"}
                  </span>
                </span>
                <span>
                  avg latency{" "}
                  <span className="font-medium text-ink">
                    {s.avg_latency_ms !== null
                      ? fmtLatency(s.avg_latency_ms)
                      : "—"}
                  </span>
                </span>
                <span>
                  std{" "}
                  <span className="font-medium text-ink">
                    {fmtScore(s.std)}
                  </span>
                </span>
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-ink">
          Results by case ({groups.length})
        </h2>
        {groups.length === 0 && (
          <p className="rounded-xl border border-hairline bg-surface p-6 text-center text-sm text-ink3">
            {live ? "Waiting for the first results…" : "No results recorded."}
          </p>
        )}
        {groups.map((g) => (
          <div
            key={g.caseId}
            className="overflow-hidden rounded-xl border border-hairline bg-surface"
          >
            <div className="border-b border-hairline px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-ink3">
                Case #{g.caseId}
              </div>
              <p className="mt-1 text-sm text-ink">{truncate(g.prompt, 240)}</p>
              <p className="mt-1 text-xs text-ink2">
                <span className="font-medium">Expected:</span>{" "}
                {truncate(g.expectedBehavior, 200)}
              </p>
            </div>
            <table className="w-full text-left text-sm tabular-nums">
              <thead>
                <tr className="border-b border-hairline text-xs uppercase tracking-wide text-ink3">
                  <th className="px-4 py-2 font-medium">Model</th>
                  <th className="px-4 py-2 font-medium">Overall</th>
                  <th className="px-4 py-2 font-medium">Checks</th>
                  <th className="px-4 py-2 font-medium">Latency</th>
                  <th className="px-4 py-2 font-medium">Tokens in/out</th>
                  <th className="px-4 py-2 font-medium">Retries</th>
                  <th className="px-4 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {g.rows.map((r) => {
                  const overall = overallScore(r.judge_scores);
                  const open = expanded.has(r.id);
                  return (
                    <Fragment key={r.id}>
                      <tr
                        onClick={() => toggleExpanded(r.id)}
                        className="cursor-pointer hover:bg-page"
                      >
                        <td className="px-4 py-2.5 text-ink">
                          {r.model}
                          {r.error && (
                            <span className="ml-2 text-xs font-medium text-critical">
                              ✗ error
                            </span>
                          )}
                          {!r.error && r.judge_error && (
                            <span className="ml-2 text-xs font-medium text-serious">
                              ! judge error
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          {overall !== null ? (
                            <span className="font-medium text-ink">
                              {fmtScore(overall)}
                            </span>
                          ) : (
                            <span className="text-ink3">—</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <ChecksCell result={r} />
                        </td>
                        <td className="px-4 py-2.5 text-ink2">
                          {r.latency_ms !== null ? fmtLatency(r.latency_ms) : "—"}
                        </td>
                        <td className="px-4 py-2.5 text-ink2">
                          {r.input_tokens ?? "—"}/{r.output_tokens ?? "—"}
                        </td>
                        <td className="px-4 py-2.5 text-ink2">{r.retries}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-accent">
                          {open ? "▴ collapse" : "▾ expand"}
                        </td>
                      </tr>
                      {open && (
                        <tr>
                          <td colSpan={7} className="p-0">
                            <ResultDetail result={r} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </section>
    </div>
  );
}
