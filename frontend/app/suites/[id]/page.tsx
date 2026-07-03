"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, errorMessage, isNetworkError, ApiError } from "@/lib/api";
import type { CaseInput, SuiteDetail, TestCase } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { truncate } from "@/lib/format";
import BackendDown from "@/components/BackendDown";
import CaseForm from "@/components/CaseForm";
import RunLauncher from "@/components/RunLauncher";

export default function SuiteDetailPage() {
  const params = useParams<{ id: string }>();
  const suiteId = Number(params.id);
  const router = useRouter();

  const suite = useApi<SuiteDetail>(() => api.getSuite(suiteId), [suiteId]);

  // Name/description editor
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [savingMeta, setSavingMeta] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);
  useEffect(() => {
    if (suite.data) {
      setName(suite.data.name);
      setDescription(suite.data.description);
    }
  }, [suite.data]);

  // Case form state: null = closed, "new" = create, TestCase = edit
  const [caseFormTarget, setCaseFormTarget] = useState<TestCase | "new" | null>(
    null,
  );
  const [savingCase, setSavingCase] = useState(false);
  const [caseError, setCaseError] = useState<string | null>(null);

  const saveMeta = async (e: FormEvent) => {
    e.preventDefault();
    setSavingMeta(true);
    setMetaError(null);
    try {
      await api.updateSuite(suiteId, {
        name: name.trim(),
        description: description.trim(),
      });
      suite.reload();
    } catch (err) {
      setMetaError(errorMessage(err));
    } finally {
      setSavingMeta(false);
    }
  };

  const saveCase = async (input: CaseInput) => {
    setSavingCase(true);
    setCaseError(null);
    try {
      if (caseFormTarget === "new") {
        await api.createCase(suiteId, input);
      } else if (caseFormTarget) {
        await api.updateCase(caseFormTarget.id, input);
      }
      setCaseFormTarget(null);
      suite.reload();
    } catch (err) {
      setCaseError(errorMessage(err));
    } finally {
      setSavingCase(false);
    }
  };

  const deleteCase = async (c: TestCase) => {
    if (!window.confirm(`Delete case #${c.id}? This cannot be undone.`)) return;
    try {
      await api.deleteCase(c.id);
      suite.reload();
    } catch (err) {
      window.alert(errorMessage(err));
    }
  };

  const deleteSuite = async () => {
    if (
      !window.confirm(
        "Delete this suite (and all its cases and runs)? This cannot be undone.",
      )
    )
      return;
    try {
      await api.deleteSuite(suiteId);
      router.push("/suites");
    } catch (err) {
      window.alert(errorMessage(err));
    }
  };

  if (suite.loading) {
    return <p className="text-sm text-ink3">Loading suite…</p>;
  }
  if (isNetworkError(suite.error)) {
    return <BackendDown onRetry={suite.reload} />;
  }
  if (suite.error instanceof ApiError && suite.error.status === 404) {
    return <p className="text-sm text-critical">Suite not found.</p>;
  }
  if (suite.error != null) {
    return <p className="text-sm text-critical">{errorMessage(suite.error)}</p>;
  }
  if (!suite.data) return null;

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-xl font-semibold text-ink">{suite.data.name}</h1>
          <button
            onClick={deleteSuite}
            className="rounded-md border border-hairline px-3 py-1.5 text-xs font-medium text-critical hover:bg-critical/5"
          >
            Delete suite
          </button>
        </div>
        <form onSubmit={saveMeta} className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-ink2">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-64 rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs font-medium text-ink2">
            Description
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="min-w-48 rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink"
            />
          </label>
          <button
            type="submit"
            disabled={savingMeta}
            className="rounded-md border border-hairline px-4 py-2 text-sm font-medium text-ink hover:bg-page disabled:opacity-50"
          >
            {savingMeta ? "Saving…" : "Save"}
          </button>
        </form>
        {metaError && <p className="mt-2 text-sm text-critical">{metaError}</p>}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">
            Cases ({suite.data.cases.length})
          </h2>
          {caseFormTarget === null && (
            <button
              onClick={() => {
                setCaseError(null);
                setCaseFormTarget("new");
              }}
              className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90"
            >
              + Add case
            </button>
          )}
        </div>

        {caseFormTarget !== null && (
          <CaseForm
            key={caseFormTarget === "new" ? "new" : caseFormTarget.id}
            initial={caseFormTarget === "new" ? null : caseFormTarget}
            saving={savingCase}
            error={caseError}
            onSave={saveCase}
            onCancel={() => setCaseFormTarget(null)}
          />
        )}

        {suite.data.cases.length === 0 ? (
          <p className="rounded-xl border border-hairline bg-surface p-6 text-center text-sm text-ink3">
            No cases yet — add one to make this suite runnable.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-hairline bg-surface">
            <table className="w-full text-left text-sm tabular-nums">
              <thead>
                <tr className="border-b border-hairline text-xs uppercase tracking-wide text-ink3">
                  <th className="px-4 py-3 font-medium">#</th>
                  <th className="px-4 py-3 font-medium">Prompt</th>
                  <th className="px-4 py-3 font-medium">Tags</th>
                  <th className="px-4 py-3 font-medium">Assertions</th>
                  <th className="px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {suite.data.cases.map((c) => (
                  <tr key={c.id} className="align-top hover:bg-page">
                    <td className="px-4 py-3 text-ink3">{c.id}</td>
                    <td className="max-w-lg px-4 py-3 text-ink2">
                      {truncate(c.prompt, 120)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {c.tags.length === 0 ? (
                          <span className="text-ink3">—</span>
                        ) : (
                          c.tags.map((t) => (
                            <span
                              key={t}
                              className="rounded-full bg-page px-2 py-0.5 text-xs text-ink2"
                            >
                              {t}
                            </span>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-ink">
                      {c.assertions.length}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <button
                        onClick={() => {
                          setCaseError(null);
                          setCaseFormTarget(c);
                        }}
                        className="rounded-md px-2 py-1 text-xs font-medium text-accent hover:bg-accent/10"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => deleteCase(c)}
                        className="ml-1 rounded-md px-2 py-1 text-xs font-medium text-critical hover:bg-critical/5"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <RunLauncher suiteId={suiteId} />
    </div>
  );
}
