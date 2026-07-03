"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage, isNetworkError } from "@/lib/api";
import type { SuiteListItem } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDate } from "@/lib/format";
import BackendDown from "@/components/BackendDown";

export default function SuitesPage() {
  const suites = useApi<SuiteListItem[]>(() => api.listSuites(), []);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await api.createSuite({
        name: name.trim(),
        description: description.trim(),
      });
      setName("");
      setDescription("");
      suites.reload();
    } catch (err) {
      setCreateError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-ink">Test suites</h1>

      <section className="rounded-xl border border-hairline bg-surface p-5">
        <h2 className="text-sm font-semibold text-ink">Create a suite</h2>
        <form
          onSubmit={onCreate}
          className="mt-3 flex flex-wrap items-end gap-3"
        >
          <label className="flex flex-col gap-1 text-xs font-medium text-ink2">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="e.g. Article Summarization"
              className="w-64 rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink3"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs font-medium text-ink2">
            Description (optional)
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this suite evaluates"
              className="min-w-48 rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink3"
            />
          </label>
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create suite"}
          </button>
        </form>
        {createError && (
          <p className="mt-2 text-sm text-critical">{createError}</p>
        )}
      </section>

      {suites.loading && <p className="text-sm text-ink3">Loading…</p>}
      {isNetworkError(suites.error) && <BackendDown onRetry={suites.reload} />}
      {!suites.loading && !isNetworkError(suites.error) && suites.error != null && (
        <p className="text-sm text-critical">{errorMessage(suites.error)}</p>
      )}

      {suites.data && suites.data.length === 0 && (
        <p className="text-sm text-ink3">
          No suites yet — create your first one above.
        </p>
      )}

      {suites.data && suites.data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-hairline bg-surface">
          <table className="w-full text-left text-sm tabular-nums">
            <thead>
              <tr className="border-b border-hairline text-xs uppercase tracking-wide text-ink3">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Description</th>
                <th className="px-4 py-3 font-medium">Cases</th>
                <th className="px-4 py-3 font-medium">Runs</th>
                <th className="px-4 py-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {suites.data.map((s) => (
                <tr key={s.id} className="hover:bg-page">
                  <td className="px-4 py-3">
                    <Link
                      href={`/suites/${s.id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {s.name}
                    </Link>
                  </td>
                  <td className="max-w-md px-4 py-3 text-ink2">
                    {s.description || <span className="text-ink3">—</span>}
                  </td>
                  <td className="px-4 py-3 text-ink">{s.case_count}</td>
                  <td className="px-4 py-3 text-ink">{s.run_count}</td>
                  <td className="px-4 py-3 text-ink2">
                    {formatDate(s.created_at)}
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
