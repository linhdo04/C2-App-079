import { TrendingUp } from "lucide-react";
import type { EvaluationMetricsResponse } from "@/types/cost-management";
import { formatDateTime, formatMetricValue, formatNumber, getDeltaTone } from "./cost-management-formatters";

export function EvaluationMetricsPanel({ evaluation }: { evaluation: EvaluationMetricsResponse }) {
  return (
    <section className="reveal reveal-delay-2 mt-4 rounded-[1.5rem] border border-border/80 bg-card/80 p-5 backdrop-blur-sm sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-primary">
            <TrendingUp className="size-5" />
            <h2 className="text-lg font-bold tracking-[-0.025em]">Evaluation Metrics</h2>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            So sánh kỳ hiện tại với baseline là kỳ liền trước cùng độ dài.
          </p>
        </div>
        <p className="rounded-full border border-border/70 px-3 py-1 text-[0.68rem] font-bold text-muted-foreground">
          Baseline: {formatDateTime(evaluation.baseline_range.start)} – {formatDateTime(evaluation.baseline_range.end)}
        </p>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {evaluation.metrics.map((metric) => (
          <article
            key={metric.key}
            className="rounded-2xl border border-border/70 bg-secondary/30 p-4"
          >
            <h3 className="text-xs font-bold text-muted-foreground">{metric.label}</h3>
            <p className="mt-3 text-2xl font-bold tracking-[-0.04em]">
              {formatMetricValue(metric, metric.current_value)}
            </p>
            <div className="mt-3 space-y-1 text-xs">
              <p className="text-muted-foreground">
                Baseline:{" "}
                <span className="font-bold text-foreground">
                  {metric.baseline_value === null
                    ? "Chưa có baseline"
                    : formatMetricValue(metric, metric.baseline_value)}
                </span>
              </p>
              <p className={getDeltaTone(metric)}>
                {metric.delta_value === null
                  ? "Chưa đủ dữ liệu so sánh"
                  : `${metric.delta_value > 0 ? "+" : ""}${formatMetricValue(metric, metric.delta_value)}${metric.delta_percent === null ? "" : ` · ${metric.delta_percent > 0 ? "+" : ""}${metric.delta_percent}%`}`}
              </p>
              <p className="text-muted-foreground">{formatNumber(metric.sample_count)} agent run</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
