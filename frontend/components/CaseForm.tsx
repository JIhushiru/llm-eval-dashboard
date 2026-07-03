"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import type { Assertion, AssertionType, CaseInput, TestCase } from "@/lib/api";

const ASSERTION_TYPES: { value: AssertionType; label: string }[] = [
  { value: "contains", label: "contains" },
  { value: "not_contains", label: "not contains" },
  { value: "regex", label: "regex" },
  { value: "not_regex", label: "not regex" },
  { value: "json_valid", label: "JSON valid" },
  { value: "max_length", label: "max length" },
];

// Editable row state; normalized into a clean Assertion on submit.
interface AssertionDraft {
  type: AssertionType;
  value: string;
  case_sensitive: boolean;
  max_chars: string;
}

function toDraft(a: Assertion): AssertionDraft {
  return {
    type: a.type,
    value: a.value ?? "",
    case_sensitive: a.case_sensitive ?? false,
    max_chars: a.max_chars !== undefined ? String(a.max_chars) : "500",
  };
}

function toAssertion(d: AssertionDraft): Assertion {
  switch (d.type) {
    case "contains":
    case "not_contains":
      return { type: d.type, value: d.value, case_sensitive: d.case_sensitive };
    case "regex":
    case "not_regex":
      return { type: d.type, value: d.value };
    case "json_valid":
      return { type: d.type };
    case "max_length":
      return { type: d.type, max_chars: Number(d.max_chars) || 0 };
  }
}

const inputCls =
  "rounded-md border border-hairline bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink3";
const labelCls = "flex flex-col gap-1 text-xs font-medium text-ink2";

export default function CaseForm({
  initial,
  saving,
  error,
  onSave,
  onCancel,
}: {
  initial: TestCase | null;
  saving: boolean;
  error: string | null;
  onSave: (input: CaseInput) => void;
  onCancel: () => void;
}) {
  const [prompt, setPrompt] = useState(initial?.prompt ?? "");
  const [expected, setExpected] = useState(initial?.expected_behavior ?? "");
  const [reference, setReference] = useState(initial?.reference_answer ?? "");
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const [assertions, setAssertions] = useState<AssertionDraft[]>(
    (initial?.assertions ?? []).map(toDraft),
  );

  const updateAssertion = (i: number, patch: Partial<AssertionDraft>) => {
    setAssertions((prev) =>
      prev.map((a, j) => (j === i ? { ...a, ...patch } : a)),
    );
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSave({
      prompt,
      expected_behavior: expected,
      reference_answer: reference.trim() === "" ? null : reference,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0),
      assertions: assertions.map(toAssertion),
    });
  };

  return (
    <form
      onSubmit={submit}
      className="space-y-4 rounded-xl border border-hairline bg-surface p-5"
    >
      <h3 className="text-sm font-semibold text-ink">
        {initial ? `Edit case #${initial.id}` : "Add a test case"}
      </h3>

      <label className={labelCls}>
        Prompt
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          required
          rows={4}
          placeholder="The prompt sent to the model"
          className={inputCls}
        />
      </label>

      <label className={labelCls}>
        Expected behavior
        <textarea
          value={expected}
          onChange={(e) => setExpected(e.target.value)}
          required
          rows={2}
          placeholder="What a good response looks like (used by the judge)"
          className={inputCls}
        />
      </label>

      <label className={labelCls}>
        Reference answer (optional gold standard)
        <textarea
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          rows={2}
          className={inputCls}
        />
      </label>

      <label className={labelCls}>
        Tags (comma-separated)
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="summarization, news"
          className={inputCls}
        />
      </label>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-ink2">
            Assertions (deterministic checks)
          </span>
          <button
            type="button"
            onClick={() =>
              setAssertions((prev) => [
                ...prev,
                { type: "contains", value: "", case_sensitive: false, max_chars: "500" },
              ])
            }
            className="rounded-md border border-hairline px-2.5 py-1 text-xs font-medium text-ink hover:bg-page"
          >
            + Add assertion
          </button>
        </div>
        {assertions.length === 0 && (
          <p className="text-xs text-ink3">
            No assertions — checks column will show “—” for this case.
          </p>
        )}
        <div className="space-y-2">
          {assertions.map((a, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center gap-2 rounded-md border border-hairline bg-page p-2"
            >
              <select
                value={a.type}
                onChange={(e) =>
                  updateAssertion(i, { type: e.target.value as AssertionType })
                }
                className="rounded-md border border-hairline bg-surface px-2 py-1.5 text-sm text-ink"
              >
                {ASSERTION_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>

              {(a.type === "contains" ||
                a.type === "not_contains" ||
                a.type === "regex" ||
                a.type === "not_regex") && (
                <input
                  value={a.value}
                  onChange={(e) => updateAssertion(i, { value: e.target.value })}
                  required
                  placeholder={
                    a.type === "regex" || a.type === "not_regex"
                      ? "pattern (re.search, MULTILINE)"
                      : "needle substring"
                  }
                  className={`${inputCls} flex-1 py-1.5`}
                />
              )}

              {(a.type === "contains" || a.type === "not_contains") && (
                <label className="flex items-center gap-1.5 text-xs text-ink2">
                  <input
                    type="checkbox"
                    checked={a.case_sensitive}
                    onChange={(e) =>
                      updateAssertion(i, { case_sensitive: e.target.checked })
                    }
                  />
                  case sensitive
                </label>
              )}

              {a.type === "max_length" && (
                <label className="flex items-center gap-1.5 text-xs text-ink2">
                  max chars
                  <input
                    type="number"
                    min={1}
                    value={a.max_chars}
                    onChange={(e) =>
                      updateAssertion(i, { max_chars: e.target.value })
                    }
                    required
                    className={`${inputCls} w-24 py-1.5`}
                  />
                </label>
              )}

              {a.type === "json_valid" && (
                <span className="text-xs text-ink3">
                  response must parse as JSON (code fences stripped)
                </span>
              )}

              <button
                type="button"
                onClick={() =>
                  setAssertions((prev) => prev.filter((_, j) => j !== i))
                }
                aria-label="Remove assertion"
                className="ml-auto rounded-md px-2 py-1 text-xs text-ink3 hover:bg-surface hover:text-critical"
              >
                ✕ Remove
              </button>
            </div>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-critical">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
        >
          {saving ? "Saving…" : initial ? "Save case" : "Add case"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-hairline px-4 py-2 text-sm font-medium text-ink hover:bg-page"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
