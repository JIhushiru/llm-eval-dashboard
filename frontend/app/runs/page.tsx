"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, isNetworkError } from "@/lib/api";
import type { Page, RunListItem, SuiteListItem } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/format";
import BackendDown from "@/components/BackendDown";
import StatusBadge from "@/components/StatusBadge";

const PAGE_SIZE = 20;

export default function RunsPage() {
  const router = useRouter();
  const suites = useApi<SuiteListItem[]>(() => api.listSuites(), []);
  const [suiteFilter, setSuiteFilter] = useState<number | "">("");
  const [page, setPage] = useState(0);
  const runs = useApi<Page<RunListItem>>(
    () =>
      api.listRunsPage({
        suiteId: suiteFilter === "" ? undefined : suiteFilter,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    [suiteFilter, page],
  );

  const items = runs.data?.items ?? [];
  const total = runs.data?.total ?? 0;
  const rangeStart = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const rangeEnd = page * PAGE_SIZE + items.length;
  const hasPrev = page > 0;
  const hasNext = (page + 1) * PAGE_SIZE < total;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink">Runs</h1>
        <label className="flex items-center gap-2 text-sm text-ink2">
          Suite
          <select
            value={suiteFilter}
            onChange={(e) => {
              setSuiteFilter(e.target.value === "" ? "" : Number(e.target.value));
              setPage(0);
            }}
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

      {runs.data && total === 0 && (
        <p className="rounded-xl border border-hairline bg-surface p-6 text-center text-sm text-ink3">
          No runs yet — launch one from a{" "}
          <Link href="/suites" className="font-medium text-accent hover:underline">
            suite
          </Link>{" "}
          page.
        </p>
      )}

      {runs.data && total > 0 && (
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
              {items.map((r) => (
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

      {runs.data && total > 0 && (
        <div className="flex items-center justify-between text-sm text-ink2">
          <span>
            {rangeStart}–{rangeEnd} of {total}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={!hasPrev}
              className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={!hasNext}
              className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
