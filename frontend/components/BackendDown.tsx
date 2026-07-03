import { API_BASE } from "@/lib/api";

export default function BackendDown({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-6">
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-warning/20 text-xs font-bold text-serious"
          aria-hidden
        >
          !
        </span>
        <div>
          <h2 className="text-sm font-semibold text-ink">
            Backend not reachable at{" "}
            <code className="rounded bg-page px-1 py-0.5 text-[13px]">
              {API_BASE}
            </code>
          </h2>
          <p className="mt-1 text-sm text-ink2">
            Start the API server (e.g.{" "}
            <code className="rounded bg-page px-1 py-0.5 text-[13px]">
              uvicorn app.main:app --port 8000
            </code>
            ) or set <code>NEXT_PUBLIC_API_URL</code> to where it runs, then
            retry.
          </p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 rounded-md border border-hairline bg-surface px-3 py-1.5 text-sm font-medium text-ink hover:bg-page"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
