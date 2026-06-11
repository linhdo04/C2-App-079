"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Bot,
  CloudSun,
  Database,
  Droplets,
  Leaf,
  Radar,
  RadioTower,
  RefreshCw,
  Thermometer,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDashboardTelemetryQuery } from "@/lib/api-hooks";
import type { TelemetryReading } from "@/types/dashboard";

type ChartPoint = {
  timestamp: string;
  value: number;
};

export function EnvironmentDashboard() {
  const telemetryQuery = useDashboardTelemetryQuery();

  if (telemetryQuery.isPending) {
    return <DashboardLoading />;
  }

  if (telemetryQuery.isError) {
    return (
      <DashboardMessage
        icon={AlertCircle}
        title="Không thể tải dữ liệu môi trường"
        description={
          telemetryQuery.error instanceof Error
            ? telemetryQuery.error.message
            : "Máy chủ chưa phản hồi. Vui lòng thử lại."
        }
        action={
          <Button onClick={() => telemetryQuery.refetch()}>
            <RefreshCw />
            Thử lại
          </Button>
        }
      />
    );
  }

  if (telemetryQuery.data.data.length === 0) {
    return (
      <DashboardMessage
        icon={Database}
        title="Chưa có dữ liệu telemetry"
        description="Hãy kết nối cảm biến với mission hoặc chạy dữ liệu demo để bắt đầu theo dõi."
      />
    );
  }

  return (
    <DashboardContent
      readings={telemetryQuery.data.data}
      sampleLimit={telemetryQuery.data.meta.limit}
      isRefreshing={telemetryQuery.isFetching}
      onRefresh={() => telemetryQuery.refetch()}
    />
  );
}

type DashboardContentProps = {
  readings: TelemetryReading[];
  sampleLimit: number;
  isRefreshing: boolean;
  onRefresh: () => void;
};

function DashboardContent({ readings, sampleLimit, isRefreshing, onRefresh }: DashboardContentProps) {
  const latest = readings.at(-1)!;
  const temperatures = metricPoints(readings, "temperature_celsius");
  const humidities = metricPoints(readings, "humidity_percent");
  const latestTemperature = temperatures.at(-1)?.value;
  const latestHumidity = humidities.at(-1)?.value;
  const stationCount = new Set(readings.map((reading) => reading.node_name)).size;

  return (
    <main className="app-shell relative min-h-screen overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute right-0 top-0 h-80 w-80 rounded-full bg-primary/5 blur-3xl" />

      <section className="relative mx-auto w-full max-w-[1440px] px-4 pb-10 sm:px-6 lg:px-8">
        <DashboardHeader />

        <div className="reveal py-8 sm:py-10">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="mb-4 flex items-center gap-2 text-primary">
                <span className="size-2 rounded-full bg-primary shadow-[0_0_14px_var(--primary)]" />
                <span className="eyebrow">{latest.node_name} · telemetry trực tuyến</span>
              </div>
              <h1 className="max-w-3xl text-4xl font-bold leading-[1.02] tracking-[-0.045em] sm:text-5xl">
                Vi khí hậu cánh đồng
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
                Dữ liệu nhiệt độ và độ ẩm thực tế từ các cảm biến thuộc mission của bạn.
              </p>
            </div>

            <div className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card/60 px-4 py-3 backdrop-blur-sm">
              <CloudSun className="size-6 text-primary" />
              <div className="min-w-0">
                <p className="truncate text-sm font-bold">{latest.mission_name}</p>
                <p className="text-xs text-muted-foreground">Cập nhật {formatDateTime(latest.timestamp)}</p>
              </div>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Làm mới dữ liệu"
                disabled={isRefreshing}
                onClick={onRefresh}
              >
                <RefreshCw className={isRefreshing ? "animate-spin" : ""} />
              </Button>
            </div>
          </div>

          <dl className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MetricCard
              icon={Thermometer}
              label="Nhiệt độ hiện tại"
              value={formatMetric(latestTemperature, "°C")}
              detail={averageDetail(temperatures, "Trung bình", "°C")}
              accent="text-[#ff9364]"
            />
            <MetricCard
              icon={Droplets}
              label="Độ ẩm hiện tại"
              value={formatMetric(latestHumidity, "%", 0)}
              detail={averageDetail(humidities, "Trung bình", "%", 0)}
              accent="text-[#59c7f3]"
            />
            <MetricCard
              icon={Database}
              label="Số mẫu hiển thị"
              value={String(readings.length)}
              detail={`Tối đa ${sampleLimit} mẫu gần nhất`}
              accent="text-primary"
            />
            <MetricCard
              icon={RadioTower}
              label="Cảm biến"
              value={String(stationCount)}
              detail="Thuộc mission của bạn"
              accent="text-success"
            />
          </dl>
        </div>

        <section
          className="grid gap-4 lg:grid-cols-2"
          aria-label="Biểu đồ môi trường"
        >
          <EnvironmentChart
            title="Nhiệt độ"
            subtitle="Các mẫu telemetry gần nhất"
            value={formatMetric(latestTemperature, "°C")}
            change={metricChange(temperatures, "°C")}
            points={temperatures}
            color="#ff9364"
            gradientId="temperature-gradient"
          />
          <EnvironmentChart
            title="Độ ẩm"
            subtitle="Các mẫu telemetry gần nhất"
            value={formatMetric(latestHumidity, "%", 0)}
            change={metricChange(humidities, "%", 0)}
            points={humidities}
            color="#59c7f3"
            gradientId="humidity-gradient"
          />
        </section>

        <ReadingsTable readings={readings} />
      </section>
    </main>
  );
}

function DashboardHeader() {
  return (
    <header className="flex min-h-20 items-center justify-between border-b border-border/60">
      <Link
        href="/"
        className="flex items-center gap-3"
        aria-label="AeroField - Trang chủ"
      >
        <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
          <Radar className="size-5" />
        </span>
        <div>
          <span className="block text-base font-bold tracking-[-0.03em]">AeroField</span>
          <span className="hidden text-[0.62rem] font-bold uppercase tracking-[0.16em] text-muted-foreground sm:block">
            Field operations
          </span>
        </div>
      </Link>

      <nav
        className="flex items-center gap-2"
        aria-label="Điều hướng dashboard"
      >
        <Button
          asChild
          variant="ghost"
          className="hidden sm:inline-flex"
        >
          <Link href="/agent">
            <Bot />
            AI Agent
          </Link>
        </Button>
        <Button
          asChild
          variant="outline"
        >
          <Link href="/">
            Trang chủ
            <ArrowUpRight />
          </Link>
        </Button>
      </nav>
    </header>
  );
}

type MetricCardProps = {
  icon: typeof Thermometer;
  label: string;
  value: string;
  detail: string;
  accent: string;
};

function MetricCard({ icon: Icon, label, value, detail, accent }: MetricCardProps) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card/65 p-4 backdrop-blur-sm sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <dt className="text-xs font-bold text-muted-foreground">{label}</dt>
        <Icon className={`size-5 ${accent}`} />
      </div>
      <dd className="mt-4 text-2xl font-bold tracking-[-0.04em] sm:text-3xl">{value}</dd>
      <p className="mt-2 text-[0.68rem] text-muted-foreground">{detail}</p>
    </div>
  );
}

type EnvironmentChartProps = {
  title: string;
  subtitle: string;
  value: string;
  change: string;
  points: ChartPoint[];
  color: string;
  gradientId: string;
};

function EnvironmentChart({ title, subtitle, value, change, points, color, gradientId }: EnvironmentChartProps) {
  const width = 640;
  const height = 240;
  const paddingX = 20;
  const paddingY = 28;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const xDivisor = Math.max(points.length - 1, 1);
  const coordinates = points.map((point, index) => ({
    x: paddingX + (index / xDivisor) * (width - paddingX * 2),
    y: height - paddingY - ((point.value - min) / range) * (height - paddingY * 2),
  }));
  const linePath = coordinates.map(({ x, y }, index) => `${index === 0 ? "M" : "L"} ${x} ${y}`).join(" ");
  const lastCoordinate = coordinates.at(-1)!;
  const areaPath = `${linePath} L ${lastCoordinate.x} ${height - paddingY} L ${coordinates[0].x} ${
    height - paddingY
  } Z`;
  const labels = chartLabels(points);

  return (
    <article className="reveal reveal-delay-1 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 shadow-[0_24px_80px_rgb(0_0_0/0.2)] backdrop-blur-sm">
      <div className="flex items-start justify-between gap-4 p-5 pb-2 sm:p-6 sm:pb-2">
        <div>
          <p className="text-lg font-bold tracking-[-0.025em]">{title}</p>
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

      <div className="relative px-3 pb-4 sm:px-5 sm:pb-5">
        <div className="pointer-events-none absolute inset-x-5 top-5 flex h-[calc(100%-3.5rem)] flex-col justify-between text-[0.62rem] text-muted-foreground">
          <span>{max.toFixed(1)}</span>
          <span>{min.toFixed(1)}</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="relative block h-auto w-full overflow-visible"
          role="img"
          aria-label={`Biểu đồ ${title.toLowerCase()} từ dữ liệu telemetry`}
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
                stopOpacity="0.25"
              />
              <stop
                offset="100%"
                stopColor={color}
                stopOpacity="0"
              />
            </linearGradient>
          </defs>
          {[36, 96, 156, 216].map((y) => (
            <line
              key={y}
              x1="20"
              x2="620"
              y1={y}
              y2={y}
              stroke="var(--border)"
              strokeWidth="1"
              strokeDasharray="5 7"
            />
          ))}
          <path
            d={areaPath}
            fill={`url(#${gradientId})`}
          />
          <path
            d={linePath}
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {coordinates.map(({ x, y }, index) => (
            <circle
              key={`${x}-${y}`}
              cx={x}
              cy={y}
              r={index === coordinates.length - 1 ? 6 : 3}
              fill={index === coordinates.length - 1 ? "var(--card)" : color}
              stroke={color}
              strokeWidth={index === coordinates.length - 1 ? 4 : 0}
            />
          ))}
        </svg>
        <div
          className="grid px-1 text-center font-mono text-[0.6rem] text-muted-foreground"
          style={{ gridTemplateColumns: `repeat(${labels.length}, minmax(0, 1fr))` }}
        >
          {labels.map((label) => (
            <span key={`${label.timestamp}-${label.value}`}>{formatTime(label.timestamp)}</span>
          ))}
        </div>
      </div>
    </article>
  );
}

function ReadingsTable({ readings }: { readings: TelemetryReading[] }) {
  return (
    <section className="reveal reveal-delay-2 mt-4 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-4 border-b border-border/70 p-5 sm:p-6">
        <div>
          <div className="flex items-center gap-2">
            <Leaf className="size-4 text-primary" />
            <h2 className="text-lg font-bold tracking-[-0.025em]">Dữ liệu gần nhất</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Nhiệt độ và độ ẩm được trả về từ API telemetry</p>
        </div>
        <span className="hidden rounded-full border border-success/20 bg-success-muted px-3 py-1.5 text-[0.65rem] font-bold text-success-foreground sm:inline-flex">
          {readings.length} mẫu
        </span>
      </div>

      <table className="w-full table-fixed text-left">
        <caption className="sr-only">Bảng nhiệt độ và độ ẩm theo thời gian</caption>
        <thead>
          <tr className="border-b border-border/60 text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">
            <th
              scope="col"
              className="w-1/3 px-4 py-3 font-bold sm:px-6"
            >
              Thời gian
            </th>
            <th
              scope="col"
              className="w-1/3 px-2 py-3 font-bold"
            >
              Nhiệt độ
            </th>
            <th
              scope="col"
              className="w-1/3 px-2 py-3 font-bold"
            >
              Độ ẩm
            </th>
            <th
              scope="col"
              className="hidden px-6 py-3 text-right font-bold md:table-cell"
            >
              Cảm biến
            </th>
          </tr>
        </thead>
        <tbody>
          {[...readings].reverse().map((reading) => (
            <tr
              key={`${reading.node_name}-${reading.timestamp}`}
              className="border-b border-border/40 text-sm last:border-0 hover:bg-secondary/35"
            >
              <th
                scope="row"
                className="px-4 py-4 font-mono text-xs font-bold sm:px-6"
              >
                {formatDateTime(reading.timestamp)}
              </th>
              <td className="px-2 py-4 font-bold text-[#ffad89]">{formatMetric(reading.temperature_celsius, "°C")}</td>
              <td className="px-2 py-4 font-bold text-[#7dd7fa]">{formatMetric(reading.humidity_percent, "%", 0)}</td>
              <td className="hidden truncate px-6 py-4 text-right text-xs text-muted-foreground md:table-cell">
                {reading.node_name}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

type DashboardMessageProps = {
  icon: typeof AlertCircle;
  title: string;
  description: string;
  action?: ReactNode;
};

function DashboardMessage({ icon: Icon, title, description, action }: DashboardMessageProps) {
  return (
    <main className="app-shell relative grid min-h-screen place-items-center overflow-hidden px-4 text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <section className="relative w-full max-w-lg rounded-[1.5rem] border border-border bg-card/85 p-6 text-center shadow-[0_24px_80px_rgb(0_0_0/0.25)] backdrop-blur-sm sm:p-8">
        <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-secondary text-primary">
          <Icon className="size-6" />
        </span>
        <h1 className="mt-5 text-2xl font-bold tracking-[-0.03em]">{title}</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{description}</p>
        <div className="mt-6 flex justify-center gap-3">
          {action}
          <Button
            asChild
            variant="outline"
          >
            <Link href="/">Trang chủ</Link>
          </Button>
        </div>
      </section>
    </main>
  );
}

function DashboardLoading() {
  return (
    <main
      className="app-shell min-h-screen px-4 py-8 text-foreground sm:px-6 lg:px-8"
      aria-busy="true"
      aria-label="Đang tải dashboard"
    >
      <div className="mx-auto max-w-[1440px]">
        <div className="h-12 w-48 animate-pulse rounded-xl bg-secondary" />
        <div className="mt-16 h-12 max-w-xl animate-pulse rounded-xl bg-secondary" />
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-32 animate-pulse rounded-2xl border border-border bg-card/70"
            />
          ))}
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {[0, 1].map((item) => (
            <div
              key={item}
              className="h-80 animate-pulse rounded-[1.5rem] border border-border bg-card/70"
            />
          ))}
        </div>
      </div>
    </main>
  );
}

function metricPoints(readings: TelemetryReading[], key: "temperature_celsius" | "humidity_percent"): ChartPoint[] {
  return readings.flatMap((reading) => {
    const value = reading[key];
    return value === null ? [] : [{ timestamp: reading.timestamp, value }];
  });
}

function formatMetric(value: number | null | undefined, unit: string, precision = 1): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(precision)}${unit}`;
}

function averageDetail(points: ChartPoint[], label: string, unit: string, precision = 1): string {
  if (points.length === 0) {
    return "Chưa có dữ liệu";
  }
  const average = points.reduce((total, point) => total + point.value, 0) / points.length;
  return `${label} ${average.toFixed(precision)}${unit}`;
}

function metricChange(points: ChartPoint[], unit: string, precision = 1): string {
  if (points.length < 2) {
    return "Chưa đủ dữ liệu so sánh";
  }
  const change = points.at(-1)!.value - points[0].value;
  const sign = change > 0 ? "+" : "";
  return `${sign}${change.toFixed(precision)}${unit} trong kỳ`;
}

function chartLabels(points: ChartPoint[]): ChartPoint[] {
  if (points.length <= 6) {
    return points;
  }
  return Array.from({ length: 6 }, (_, index) => points[Math.round((index / 5) * (points.length - 1))]);
}

function formatTime(timestamp: string): string {
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}

function formatDateTime(timestamp: string): string {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp));
}
