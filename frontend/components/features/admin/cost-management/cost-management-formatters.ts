import type { EvaluationMetric } from "@/types/cost-management";

const USD_FORMATTER = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 4,
});

const NUMBER_FORMATTER = new Intl.NumberFormat("vi-VN");

export function formatUsd(value: number) {
  return USD_FORMATTER.format(value);
}

export function formatNumber(value: number) {
  return NUMBER_FORMATTER.format(value);
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(value));
}

export function formatMetricValue(metric: EvaluationMetric, value: number | null) {
  if (value === null) return "Chưa có dữ liệu";
  if (metric.unit === "ms") return `${formatNumber(Math.round(value))} ms`;
  if (metric.unit === "percent") return `${value.toFixed(2)}%`;
  if (metric.unit === "usd" || metric.unit === "usd_per_user_month") return formatUsd(value);
  return formatNumber(value);
}

export function getDeltaTone(metric: EvaluationMetric) {
  if (metric.delta_value === null || metric.delta_value === 0) return "text-muted-foreground";
  const improved = metric.direction === "lower_better" ? metric.delta_value < 0 : metric.delta_value > 0;
  return improved ? "text-success" : "text-destructive-text";
}
