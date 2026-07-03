"use client";

import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, isNetworkError } from "@/lib/api";
import type { BackendInfo } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function RunLauncher({ suiteId }: { suiteId: number }) {
  const router = useRouter();
  const backends = useApi<BackendInfo[]>(() => api.listBackends(), []);

  const [selected, setSelected] = useState<string[]>([]);
  const [promptVersion, setPromptVersion] = useState("");
  const [promptTemplate, setPromptTemplate] = useState("");
  const [judgeModel, setJudgeModel] = useState("");
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const judgeOptions = useMemo(() => {
    if (!backends.data) return [];
    return backends.data
      .filter((b) => b.available)
      .flatMap((b) => b.models.map((m) => `${b.provider}:${m}`));
  }, [backends.data]);

  const toggle = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const launch = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (selected.length === 0) {
      setError("Select at least one model.");
      return;
    }
    if (!promptVersion.trim()) {
      setError("Prompt version is required.");
      return;
    }
    const template = promptTemplate.trim();
    if (template !== "" && !template.includes("{prompt}")) {
      setError("Prompt template must contain the literal {prompt} placeholder.");
      return;
    }
    setLaunching(true);
    try {
      const run = await api.createRun({
        suite_id: suiteId,
        models: selected,
        prompt_version: promptVersion.trim(),
        ...(template !== "" ? { prompt_template: template } : {}),
        ...(judgeModel !== "" ? { judge_model: judgeModel } : {}),
      });
      router.push(`/runs/${run.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setLaunching(false);
    }
  };

  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <h2 className="text-sm font-semibold text-ink">Launch a run</h2>

      {backends.loading && (
        <p className="mt-2 text-sm text-ink3">Loading backends…</p>
      )}
      {isNetworkError(backends.error) && (
        <p className="mt-2 text-sm text-ink2">
          Backends unavailable — backend not reachable.{" "}
          <button
            onClick={backends.reload}
            className="font-medium text-accent hover:underline"
          >
            Retry
          </button>
        </p>
      )}

      {backends.data && (
        <form onSubmit={launch} className="mt-3 space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            {backends.data.map((b) => (
              <fieldset
                key={b.provider}
                disabled={!b.available}
                className={`rounded-lg border border-hairline p-3 ${
                  b.available ? "" : "opacity-60"
                }`}
              >
                <legend className="flex items-center gap-1.5 px-1 text-xs font-semibold text-ink">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      b.available ? "bg-good" : "bg-ink3"
                    }`}
                    aria-hidden
                  />
                  {b.provider}
                  <span className="font-normal text-ink3">
                    {b.available ? "available" : "unavailable"}
                  </span>
                </legend>
                {!b.available && (
                  <p className="mb-1 text-xs text-ink3">{b.reason}</p>
                )}
                {b.models.length === 0 && b.available && (
                  <p className="text-xs text-ink3">no models listed</p>
                )}
                <div className="space-y-1">
                  {b.models.map((m) => {
                    const id = `${b.provider}:${m}`;
                    return (
                      <label
                        key={id}
                        className="flex items-center gap-2 text-sm text-ink"
                      >
                        <input
                          type="checkbox"
                          checked={selected.includes(id)}
                          onChange={() => toggle(id)}
                          disabled={!b.available}
                        />
                        {m}
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            ))}
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-ink2">
              Prompt version (required)
              <input
                value={promptVersion}
                onChange={(e) => setPromptVersion(e.target.value)}
                required
                placeholder="e.g. v5"
                className="w-40 rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink3"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-ink2">
              Judge model
              <select
                value={judgeModel}
                onChange={(e) => setJudgeModel(e.target.value)}
                className="rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink"
              >
                <option value="">(backend default)</option>
                {judgeOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="flex flex-col gap-1 text-xs font-medium text-ink2">
            Prompt template (optional — must contain{" "}
            <code className="text-[11px]">{"{prompt}"}</code>, replaced with each
            case&apos;s prompt)
            <textarea
              value={promptTemplate}
              onChange={(e) => setPromptTemplate(e.target.value)}
              rows={3}
              placeholder={"You are a helpful assistant.\n\n{prompt}"}
              className="rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink3"
            />
          </label>

          {error && <p className="text-sm text-critical">{error}</p>}

          <button
            type="submit"
            disabled={launching}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
          >
            {launching ? "Launching…" : "Launch run"}
          </button>
        </form>
      )}
    </section>
  );
}
