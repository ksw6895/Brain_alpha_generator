"use client";

import {
  LineChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";

import type { BacktestPoint } from "@/lib/brain-types";

interface BacktestChartProps {
  points: BacktestPoint[];
  latestSharpe: number | null;
}

export function BacktestChart({ points, latestSharpe }: BacktestChartProps) {
  return (
    <section className="panel p-4">
      <header className="panel-head">
        <span>Simulator Pulse</span>
        <span className="panel-meta">
          sharpe {Number.isFinite(latestSharpe) ? latestSharpe?.toFixed(2) : "N/A"}
        </span>
      </header>
      <div className="mt-3 h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points}>
            <CartesianGrid stroke="rgba(101, 115, 159, 0.2)" strokeDasharray="3 3" />
            <XAxis
              dataKey="step"
              tick={{ fill: "#9ea9d7", fontSize: 10 }}
              stroke="rgba(122, 138, 184, 0.45)"
            />
            <YAxis
              tick={{ fill: "#9ea9d7", fontSize: 10 }}
              stroke="rgba(122, 138, 184, 0.45)"
            />
            <Tooltip
              contentStyle={{
                background: "rgba(10, 13, 27, 0.95)",
                border: "1px solid rgba(120, 143, 207, 0.45)",
                borderRadius: 12,
                color: "#d4ddff",
              }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="#62ffe7"
              strokeWidth={2.3}
              dot={false}
              activeDot={{
                r: 4,
                stroke: "#e8fffa",
                strokeWidth: 1,
                fill: "#62ffe7",
              }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

