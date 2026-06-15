import type { TelemetryReading } from "@/types/dashboard";

export type ChartPoint = {
  timestamp: string;
  value: number;
};

type MetricKey = "temperature_celsius" | "humidity_percent";

export function metricPoints(readings: TelemetryReading[], key: MetricKey): ChartPoint[] {
  return readings.flatMap((reading) => {
    const value = reading[key];
    return value === null ? [] : [{ timestamp: reading.timestamp, value }];
  });
}

export function formatMetric(value: number | null | undefined, unit: string, precision = 1): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(precision)}${unit}`;
}

export function averageDetail(points: ChartPoint[], label: string, unit: string, precision = 1): string {
  if (points.length === 0) {
    return "Chưa có dữ liệu";
  }

  const average = points.reduce((total, point) => total + point.value, 0) / points.length;
  return `${label} ${average.toFixed(precision)}${unit}`;
}

export function metricChange(points: ChartPoint[], unit: string, precision = 1): string {
  if (points.length < 2) {
    return "Chưa đủ dữ liệu so sánh";
  }

  const change = points.at(-1)!.value - points[0].value;
  const sign = change > 0 ? "+" : "";
  return `${sign}${change.toFixed(precision)}${unit} trong kỳ`;
}

export function formatTime(timestamp: string): string {
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

export function formatDateTime(timestamp: string): string {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}
