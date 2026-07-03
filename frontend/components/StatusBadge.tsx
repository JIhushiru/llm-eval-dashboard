import type { RunStatus } from "@/lib/api";

// Status badges are icon/dot + label — never color alone (SPEC visual system).
const STYLES: Record<
  RunStatus,
  { dot: string; text: string; bg: string; label: string }
> = {
  pending: {
    dot: "bg-ink3",
    text: "text-ink2",
    bg: "bg-page",
    label: "Pending",
  },
  running: {
    dot: "bg-accent animate-pulse",
    text: "text-accent",
    bg: "bg-accent/10",
    label: "Running",
  },
  completed: {
    dot: "bg-good",
    text: "text-good",
    bg: "bg-good/10",
    label: "Completed",
  },
  failed: {
    dot: "bg-critical",
    text: "text-critical",
    bg: "bg-critical/10",
    label: "Failed",
  },
};

export default function StatusBadge({ status }: { status: RunStatus }) {
  const s = STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${s.bg} ${s.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden />
      {s.label}
    </span>
  );
}
