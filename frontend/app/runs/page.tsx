"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, isNetworkError } from "@/lib/api";
import type { RunListItem, SuiteListItem } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/format";
import BackendDown from "@/components/BackendDown";
import StatusBadge from "@/components/StatusBadge";

export default function RunsPage() {
  const router = useRouter();
  const suites = useApi<SuiteListItem[]>(() => api.listSuites(), []);
  const [suiteFilter, setSuiteFilter] = useState<number | "">("");
  const runs = useApi<RunListItem[]>(
    () => api.listRuns(suiteFilter === "" ? undefined : suiteFilter),
    [suiteFilter],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink">Runs</h1>
        <label className="flex items-center gap-2 text-sm text-ink2">
          Suite
          <select
            value={suiteFilter}
            onChange={(e) =>
              setSuiteFilter(e.target.value === "" ? "" : Number(e.target.value))
            }
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-sm text-ink"
          >
            <option value="">All suites</option>
            {(suites.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {runs.loading && <p className="text-sm text-ink3">Loading runs…</p>}
      {isNetworkError(runs.error) && <BackendDown onRetry={runs.reload} />}
      {!runs.loading && !isNetworkError(runs.error) && runs.error != null && (
        <p className="text-sm text-critical">{errorMessage(runs.error)}</p>
      )}

      {runs.data && runs.data.length === 0 && (
        <p className="rounded-xl border border-hairline bg-surface p-6 text-center text-sm text-ink3">
          No runs yet — launch one from a{" "}
          <Link href="/suites" className="font-medium text-accent hover:underline">
            suite
          </Link>{" "}
          page.
        </p>
      )}

      {runs.data && runs.data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-hairline bg-surface">
          <table className="w-full text-left text-sm tabular-nums">
            <thead>
              <tr className="border-b border-hairline text-xs uppercase tracking-wide text-ink3">
                <th className="px-4 py-3 font-medium">Run</th>
                <th className="px-4 py-3 font-medium">Suite</th>
                <th className="px-4 py-3 font-medium">Version</th>
                <th className="px-4 py-3 font-medium">Models</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Progress</th>
                <th className="px-4 py-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {runs.data.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => router.push(`/runs/${r.id}`)}
                  className="cursor-pointer hover:bg-page"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/runs/${r.id}`}
                      className="font-medium text-accent hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      #{r.id}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-ink">{r.suite_name}</td>
                  <td className="px-4 py-3 text-ink">{r.prompt_version}</td>
                  <td className="max-w-xs px-4 py-3 text-ink2">
                    {r.models.join(", ")}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-3 text-ink2">
                    {r.progress.done}/{r.progress.total}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink2">
                    {formatDateTime(r.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
