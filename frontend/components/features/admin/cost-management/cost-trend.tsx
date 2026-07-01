"use client";

import { useMemo } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CostSummary } from "@/types/cost-management";
import { formatDate, formatUsd } from "./cost-management-formatters";

export function CostTrend({ summary }: { summary: CostSummary }) {
  const points = useMemo(
    () => summary.daily.map((item) => ({ ...item, label: formatDate(item.date) })),
    [summary.daily],
  );

  return (
    <section className="reveal reveal-delay-1 min-w-0 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 shadow-[0_24px_80px_rgb(0_0_0/0.2)] backdrop-blur-sm">
      <div className="p-5 pb-2 sm:p-6 sm:pb-2">
        <h2 className="text-lg font-bold tracking-[-0.025em]">Xu hướng chi phí theo ngày</h2>
        <p className="mt-1 text-xs text-muted-foreground">Tính theo usage metadata đã ghi nhận từ các lần gọi LLM.</p>
      </div>
      <div
        className="h-72 w-full px-2 pb-4 pt-3 sm:px-4 sm:pb-5"
        role="img"
        aria-label="Biểu đồ chi phí AI theo ngày"
      >
        {points.length === 0 ? (
          <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
            Chưa có dữ liệu chi phí trong khoảng thời gian này.
          </div>
        ) : (
          <ResponsiveContainer
            width="100%"
            height="100%"
            minWidth={0}
            initialDimension={{ width: 640, height: 260 }}
          >
            <AreaChart
              data={points}
              margin={{ top: 8, right: 8, left: -18, bottom: 0 }}
              accessibilityLayer
            >
              <defs>
                <linearGradient
                  id="cost-gradient"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor="#b9f34a"
                    stopOpacity={0.28}
                  />
                  <stop
                    offset="100%"
                    stopColor="#b9f34a"
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
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                width={56}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                tickFormatter={(tick: number) => `$${tick.toFixed(2)}`}
              />
              <Tooltip
                cursor={{ stroke: "#b9f34a", strokeOpacity: 0.35 }}
                formatter={(value) => [formatUsd(Number(value)), "Chi phí"]}
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
                dataKey="cost_usd"
                name="Chi phí"
                stroke="#b9f34a"
                strokeWidth={3}
                fill="url(#cost-gradient)"
                dot={{ r: 3, fill: "#b9f34a", strokeWidth: 0 }}
                activeDot={{ r: 6, fill: "var(--card)", stroke: "#b9f34a", strokeWidth: 3 }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
