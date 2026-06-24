"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartPoint } from "./dashboard-utils";
import { formatDateTime, formatTime } from "./dashboard-utils";

type EnvironmentChartProps = {
  title: string;
  subtitle: string;
  value: string;
  change: string;
  points: ChartPoint[];
  color: string;
  gradientId: string;
  unit: string;
  precision?: number;
};

export function EnvironmentChart({
  title,
  subtitle,
  value,
  change,
  points,
  color,
  gradientId,
  unit,
  precision = 1,
}: EnvironmentChartProps) {
  return (
    <article className="reveal reveal-delay-1 min-w-0 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 shadow-[0_24px_80px_rgb(0_0_0/0.2)] backdrop-blur-sm">
      <div className="flex items-start justify-between gap-4 p-5 pb-2 sm:p-6 sm:pb-2">
        <div>
          <h2 className="text-lg font-bold tracking-[-0.025em]">{title}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold tracking-[-0.04em]">{value}</p>
          <p
            className="mt-1 text-xs font-bold"
            style={{ color }}
          >
            {change}
          </p>
        </div>
      </div>

      {points.length === 0 ? (
        <div className="grid h-64 place-items-center px-5 pb-5 text-center text-sm text-muted-foreground">
          Chưa có dữ liệu {title.toLowerCase()} để hiển thị.
        </div>
      ) : (
        <div
          className="h-64 w-full px-2 pb-4 pt-3 sm:px-4 sm:pb-5"
          role="img"
          aria-label={`Biểu đồ ${title.toLowerCase()} từ dữ liệu cảm biến`}
        >
          <ResponsiveContainer
            width="100%"
            height="100%"
            minWidth={0}
            initialDimension={{ width: 640, height: 224 }}
          >
            <AreaChart
              data={points}
              margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
              accessibilityLayer
            >
              <defs>
                <linearGradient
                  id={gradientId}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor={color}
                    stopOpacity={0.25}
                  />
                  <stop
                    offset="100%"
                    stopColor={color}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                vertical={false}
                stroke="var(--border)"
                strokeDasharray="5 7"
              />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatTime}
                axisLine={false}
                tickLine={false}
                minTickGap={36}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                width={48}
                domain={["auto", "auto"]}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                tickFormatter={(tick: number) => tick.toFixed(precision)}
              />
              <Tooltip
                cursor={{ stroke: color, strokeOpacity: 0.35 }}
                labelFormatter={(label) => formatDateTime(String(label))}
                formatter={(tooltipValue) => [`${Number(tooltipValue).toFixed(precision)}${unit}`, title]}
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: "0.75rem",
                  color: "var(--card-foreground)",
                  fontSize: "0.75rem",
                }}
                labelStyle={{ color: "var(--muted-foreground)" }}
              />
              <Area
                type="monotone"
                dataKey="value"
                name={title}
                stroke={color}
                strokeWidth={3}
                fill={`url(#${gradientId})`}
                dot={{ r: 3, fill: color, strokeWidth: 0 }}
                activeDot={{
                  r: 6,
                  fill: "var(--card)",
                  stroke: color,
                  strokeWidth: 3,
                }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </article>
  );
}
