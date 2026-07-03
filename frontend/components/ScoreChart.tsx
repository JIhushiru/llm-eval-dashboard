"use client";

import type { ReactElement } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HistoryPoint, HistorySeries } from "@/lib/api";
import { formatDate, fmtScore } from "@/lib/format";

// Fixed categorical palette in slot order — never cycled; the color follows
// the model, not its rank (SPEC chart spec).
export const SERIES_PALETTE = [
  "#2a78d6",
  "#1baf7a",
  "#eda100",
  "#008300",
  "#4a3aa7",
  "#e34948",
  "#e87ba4",
  "#eb6834",
] as const;

const REGRESSION_RED = "#d03b3b";
const IMPROVEMENT_GREEN = "#0ca30c";
const SURFACE = "#fcfcfb";
const GRID = "#e1e0d9";
const AXIS_LINE = "#c3c2b7";
const TICK_INK = "#898781";

export interface ChartRow {
  runId: number;
  promptVersion: string;
  createdAt: string;
  points: Record<string, HistoryPoint>;
}

// Merge per-model series into one row per run, in created_at order.
export function mergeHistoryRows(series: HistorySeries[]): ChartRow[] {
  const byRun = new Map<number, ChartRow>();
  for (const s of series) {
    for (const p of s.points) {
      let row = byRun.get(p.run_id);
      if (!row) {
        row = {
          runId: p.run_id,
          promptVersion: p.prompt_version,
          createdAt: p.created_at,
          points: {},
        };
        byRun.set(p.run_id, row);
      }
      row.points[s.model] = p;
    }
  }
  return [...byRun.values()].sort(
    (a, b) => a.createdAt.localeCompare(b.createdAt) || a.runId - b.runId,
  );
}

// Stable slot assignment: slot follows the model's position in the full
// series list, so filtering never repaints survivors.
export function paletteColorMap(models: string[]): Record<string, string> {
  const map: Record<string, string> = {};
  models.forEach((m, i) => {
    map[m] = SERIES_PALETTE[i % SERIES_PALETTE.length];
  });
  return map;
}

interface DotRenderProps {
  cx?: number;
  cy?: number;
  payload?: ChartRow;
  index?: number;
}

function makeDot(
  model: string,
  color: string,
): (props: DotRenderProps) => ReactElement {
  const DotShape = (props: DotRenderProps): ReactElement => {
    const { cx, cy, payload, index } = props;
    const point = payload?.points[model];
    if (cx === undefined || cy === undefined || !point) {
      return <g key={`dot-${model}-${index ?? "x"}`} />;
    }
    const key = `dot-${model}-${point.run_id}`;
    if (point.flag === "regression") {
      return (
        <circle
          key={key}
          cx={cx}
          cy={cy}
          r={6}
          fill={REGRESSION_RED}
          stroke="#ffffff"
          strokeWidth={2}
        />
      );
    }
    if (point.flag === "improvement") {
      return (
        <circle
          key={key}
          cx={cx}
          cy={cy}
          r={6}
          fill={IMPROVEMENT_GREEN}
          stroke="#ffffff"
          strokeWidth={2}
        />
      );
    }
    return (
      <circle
        key={key}
        cx={cx}
        cy={cy}
        r={4}
        fill={color}
        stroke={SURFACE}
        strokeWidth={2}
      />
    );
  };
  return DotShape;
}

const FLAG_CLASS: Record<string, string> = {
  regression: "text-critical font-medium",
  improvement: "text-good font-medium",
  first: "text-ink3",
  stable: "text-ink3",
};

interface TooltipPayloadEntry {
  payload?: ChartRow;
}

function ChartTooltip({
  active,
  payload,
  models,
  colors,
}: {
  active?: boolean;
  payload?: ReadonlyArray<TooltipPayloadEntry>;
  models: string[];
  colors: Record<string, string>;
}): ReactElement | null {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  return (
    <div className="rounded-lg border border-hairline bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="font-semibold text-ink">{row.promptVersion}</div>
      <div className="text-ink3">{formatDate(row.createdAt)}</div>
      <div className="mt-1.5 space-y-1">
        {models
          .filter((m) => row.points[m])
          .map((m) => {
            const p = row.points[m];
            return (
              <div key={m} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ background: colors[m] }}
                  aria-hidden
                />
                <span className="text-ink2">{m}</span>
                <span className="font-medium text-ink">
                  {fmtScore(p.mean)}
                </span>
                <span className="text-ink3">
                  [{fmtScore(p.ci_low)}–{fmtScore(p.ci_high)}]
                </span>
                {p.flag !== "stable" && (
                  <span className={FLAG_CLASS[p.flag] ?? "text-ink3"}>
                    {p.flag}
                  </span>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}

export default function ScoreChart({ series }: { series: HistorySeries[] }) {
  // Slots are never cycled: beyond 8 series the extras are omitted and noted.
  const shown = series.slice(0, SERIES_PALETTE.length);
  const omitted = series.length - shown.length;
  const models = shown.map((s) => s.model);
  const colors = paletteColorMap(series.map((s) => s.model));
  const rows = mergeHistoryRows(shown);

  if (rows.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-ink3">
        No history yet — complete a run with at least 2 scored results per
        model to see the score-over-time chart.
      </p>
    );
  }

  return (
    <div>
      <div className="h-80 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={rows}
            margin={{ top: 10, right: 16, bottom: 4, left: 0 }}
          >
            <CartesianGrid stroke={GRID} strokeWidth={1} vertical={false} />
            <XAxis
              dataKey="promptVersion"
              tick={{ fill: TICK_INK, fontSize: 12 }}
              tickLine={{ stroke: AXIS_LINE }}
              axisLine={{ stroke: AXIS_LINE }}
              padding={{ left: 16, right: 16 }}
            />
            <YAxis
              domain={[1, 5]}
              ticks={[1, 2, 3, 4, 5]}
              tick={{ fill: TICK_INK, fontSize: 12 }}
              tickLine={{ stroke: AXIS_LINE }}
              axisLine={{ stroke: AXIS_LINE }}
              width={32}
            />
            <Tooltip
              cursor={{ stroke: AXIS_LINE, strokeDasharray: "3 3" }}
              content={({ active, payload }) => (
                <ChartTooltip
                  active={active}
                  payload={payload as ReadonlyArray<TooltipPayloadEntry>}
                  models={models}
                  colors={colors}
                />
              )}
            />
            {models.map((model) => (
              <Area
                key={`band-${model}`}
                type="monotone"
                dataKey={(row: ChartRow) => {
                  const p = row.points[model];
                  return p ? [p.ci_low, p.ci_high] : null;
                }}
                stroke="none"
                fill={colors[model]}
                fillOpacity={0.1}
                connectNulls
                isAnimationActive={false}
                activeDot={false}
                tooltipType="none"
              />
            ))}
            {models.map((model) => (
              <Line
                key={`mean-${model}`}
                type="monotone"
                dataKey={(row: ChartRow) => row.points[model]?.mean ?? null}
                stroke={colors[model]}
                strokeWidth={2}
                strokeLinecap="round"
                connectNulls
                isAnimationActive={false}
                dot={makeDot(model, colors[model])}
                activeDot={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {models.length >= 2 && (
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 px-2">
          {models.map((m) => (
            <span key={m} className="flex items-center gap-1.5 text-xs text-ink2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: colors[m] }}
                aria-hidden
              />
              {m}
            </span>
          ))}
          {omitted > 0 && (
            <span className="text-xs text-ink3">
              +{omitted} more not shown (8-slot palette limit)
            </span>
          )}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 px-2 text-xs text-ink3">
        <span className="flex items-center gap-1.5">
          <span
            className="h-3 w-3 rounded-full border-2 border-white"
            style={{ background: REGRESSION_RED }}
            aria-hidden
          />
          regression
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="h-3 w-3 rounded-full border-2 border-white"
            style={{ background: IMPROVEMENT_GREEN }}
            aria-hidden
          />
          improvement
        </span>
        <span>shaded band = 95% bootstrap CI</span>
      </div>
    </div>
  );
}
