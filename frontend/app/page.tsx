"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, isNetworkError } from "@/lib/api";
import type { HistoryPoint, HistoryResponse, RunListItem, SuiteListItem } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDate, fmtScore } from "@/lib/format";
import BackendDown from "@/components/BackendDown";
import ScoreChart, { mergeHistoryRows } from "@/components/ScoreChart";
import StatTile from "@/components/StatTile";

interface RegressionAlert {
  model: string;
  point: HistoryPoint;
  previousMean: number | null;
}

function collectAlerts(history: HistoryResponse): RegressionAlert[] {
  const alerts: RegressionAlert[] = [];
  for (const s of history.series) {
    s.points.forEach((p, i) => {
      if (p.flag === "regression") {
        alerts.push({
          model: s.model,
          point: p,
          previousMean: i > 0 ? s.points[i - 1].mean : null,
        });
      }
    });
  }
  return alerts.sort((a, b) =>
    b.point.created_at.localeCompare(a.point.created_at),
  );
}

export default function DashboardPage() {
  const suites = useApi<SuiteListItem[]>(() => api.listSuites(), []);
  const [suiteId, setSuiteId] = useState<number | null>(null);

  // Default to the first suite once the list arrives.
  useEffect(() => {
    if (suiteId === null && suites.data && suites.data.length > 0) {
      setSuiteId(suites.data[0].id);
    }
  }, [suites.data, suiteId]);

  const history = useApi<HistoryResponse | null>(
    () => (suiteId !== null ? api.getHistory(suiteId) : Promise.resolve(null)),
    [suiteId],
  );
  const runs = useApi<RunListItem[] | null>(
    () => (suiteId !== null ? api.listRuns(suiteId) : Promise.resolve(null)),
    [suiteId],
  );

  const suite = suites.data?.find((s) => s.id === suiteId) ?? null;

  const { latestMean, delta, latestVersion, alerts } = useMemo(() => {
    if (!history.data) {
      return {
        latestMean: null as number | null,
        delta: null as number | null,
        latestVersion: null as string | null,
        alerts: [] as RegressionAlert[],
      };
    }
    const rows = mergeHistoryRows(history.data.series);
    const rowMean = (points: Record<string, HistoryPoint>): number | null => {
      const means = Object.values(points).map((p) => p.mean);
      if (means.length === 0) return null;
      return means.reduce((a, b) => a + b, 0) / means.length;
    };
    const last = rows.length > 0 ? rows[rows.length - 1] : null;
    const prev = rows.length > 1 ? rows[rows.length - 2] : null;
    const lastMean = last ? rowMean(last.points) : null;
    const prevMean = prev ? rowMean(prev.points) : null;
    return {
      latestMean: lastMean,
      delta: lastMean !== null && prevMean !== null ? lastMean - prevMean : null,
      latestVersion: last?.promptVersion ?? null,
      alerts: collectAlerts(history.data),
    };
  }, [history.data]);

  if (isNetworkError(suites.error)) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
        <BackendDown onRetry={suites.reload} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink">Dashboard</h1>
        {suites.data && suites.data.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-ink2">
            Suite
            <select
              value={suiteId ?? ""}
              onChange={(e) => setSuiteId(Number(e.target.value))}
              className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-sm text-ink"
            >
              {suites.data.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {suites.loading && <p className="text-sm text-ink3">Loading suites…</p>}

      {suites.data && suites.data.length === 0 && (
        <div className="rounded-xl border border-hairline bg-surface p-8 text-center">
          <p className="text-sm text-ink2">
            No suites yet. Create one to start evaluating.
          </p>
          <Link
            href="/suites"
            className="mt-3 inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90"
          >
            Create a suite
          </Link>
        </div>
      )}

      {suite && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile
              label="Latest mean score"
              value={latestMean !== null ? fmtScore(latestMean) : "—"}
              delta={delta}
              sub={
                latestVersion
                  ? `run ${latestVersion} · avg across models`
                  : "no completed runs"
              }
            />
            <StatTile
              label="Total runs"
              value={runs.data ? String(runs.data.length) : "—"}
              sub={suite.name}
            />
            <StatTile
              label="Total cases"
              value={String(suite.case_count)}
              sub="in this suite"
            />
            <StatTile
              label="Regression alerts"
              value={String(alerts.length)}
              sub="non-overlapping CI drops"
            />
          </div>

          <section className="rounded-xl border border-hairline bg-surface p-5">
            <h2 className="text-sm font-semibold text-ink">
              Score over time
            </h2>
            <p className="mb-2 text-xs text-ink3">
              Mean judge score per model per run (1–5), with 95% bootstrap CI
              bands.
            </p>
            {history.loading ? (
              <p className="py-12 text-center text-sm text-ink3">
                Loading history…
              </p>
            ) : isNetworkError(history.error) ? (
              <BackendDown onRetry={history.reload} />
            ) : history.data ? (
              <ScoreChart series={history.data.series} />
            ) : null}
          </section>

          <section className="rounded-xl border border-hairline bg-surface p-5">
            <h2 className="text-sm font-semibold text-ink">
              Regression alerts
            </h2>
            {alerts.length === 0 ? (
              <p className="mt-2 flex items-center gap-1.5 text-sm text-ink2">
                <span className="h-1.5 w-1.5 rounded-full bg-good" aria-hidden />
                No regressions detected.
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-hairline">
                {alerts.map((a) => (
                  <li key={`${a.model}-${a.point.run_id}`}>
                    <Link
                      href={`/runs/${a.point.run_id}`}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-2 py-2.5 hover:bg-critical/5"
                    >
                      <span className="font-medium text-critical">
                        ▼ Regression
                      </span>
                      <span className="text-sm text-ink">{a.model}</span>
                      <span className="text-sm text-ink2">
                        dropped to {fmtScore(a.point.mean)}
                        {a.previousMean !== null &&
                          ` (from ${fmtScore(a.previousMean)})`}{" "}
                        in {a.point.prompt_version}
                      </span>
                      <span className="text-xs text-ink3">
                        {formatDate(a.point.created_at)} · run #
                        {a.point.run_id}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
