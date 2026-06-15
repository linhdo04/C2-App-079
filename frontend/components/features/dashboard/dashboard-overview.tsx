import { CloudSun, Database, Droplets, RadioTower, RefreshCw, Thermometer, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TelemetryReading } from "@/types/dashboard";
import type { ChartPoint } from "./dashboard-utils";
import { averageDetail, formatDateTime, formatMetric } from "./dashboard-utils";

type DashboardOverviewProps = {
  readings: TelemetryReading[];
  sampleLimit: number;
  latest: TelemetryReading;
  temperatures: ChartPoint[];
  humidities: ChartPoint[];
  isRefreshing: boolean;
  onRefresh: () => void;
};

export function DashboardOverview({
  readings,
  sampleLimit,
  latest,
  temperatures,
  humidities,
  isRefreshing,
  onRefresh,
}: DashboardOverviewProps) {
  const latestTemperature = temperatures.at(-1)?.value;
  const latestHumidity = humidities.at(-1)?.value;
  const stationCount = new Set(readings.map((reading) => reading.node_name)).size;

  return (
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
          <CloudSun className="size-6 shrink-0 text-primary" />
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
  );
}

type MetricCardProps = {
  icon: LucideIcon;
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
