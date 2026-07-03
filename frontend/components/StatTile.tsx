export default function StatTile({
  label,
  value,
  sub,
  delta,
}: {
  label: string;
  value: string;
  sub?: string;
  delta?: number | null;
}) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-ink3">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        {/* Stat-tile values: semibold, proportional figures (no tabular-nums) */}
        <span className="text-2xl font-semibold text-ink">{value}</span>
        {delta !== undefined && delta !== null && (
          <span
            className={`text-sm font-medium ${
              delta >= 0 ? "text-good" : "text-critical"
            }`}
          >
            {delta >= 0 ? "▲" : "▼"} {delta >= 0 ? "+" : ""}
            {delta.toFixed(2)}
          </span>
        )}
      </div>
      {sub && <div className="mt-0.5 text-xs text-ink3">{sub}</div>}
    </div>
  );
}
