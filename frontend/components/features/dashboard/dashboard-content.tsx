import type { TelemetryReading } from "@/types/dashboard";
import { DashboardHeader } from "./dashboard-header";
import { DashboardOverview } from "./dashboard-overview";
import { EnvironmentChart } from "./environment-chart";
import { ReadingsTable } from "./readings-table";
import { formatMetric, metricChange, metricPoints } from "./dashboard-utils";

type DashboardContentProps = {
  readings: TelemetryReading[];
  isRefreshing: boolean;
  onRefresh: () => void;
};

export function DashboardContent({ readings, isRefreshing, onRefresh }: DashboardContentProps) {
  const latest = readings.at(-1)!;
  const temperatures = metricPoints(readings, "temperature_celsius");
  const humidities = metricPoints(readings, "humidity_percent");
  const latestTemperature = temperatures.at(-1)?.value;
  const latestHumidity = humidities.at(-1)?.value;

  return (
    <main className="app-shell relative min-h-screen overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute right-0 top-0 h-80 w-80 rounded-full bg-primary/5 blur-3xl" />

      <section className="relative mx-auto w-full max-w-[1440px] px-4 pb-10 sm:px-6 lg:px-8">
        <DashboardHeader />
        <DashboardOverview
          readings={readings}
          latest={latest}
          temperatures={temperatures}
          humidities={humidities}
          isRefreshing={isRefreshing}
          onRefresh={onRefresh}
        />

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
            unit="°C"
          />
          <EnvironmentChart
            title="Độ ẩm"
            subtitle="Các mẫu telemetry gần nhất"
            value={formatMetric(latestHumidity, "%", 0)}
            change={metricChange(humidities, "%", 0)}
            points={humidities}
            color="#59c7f3"
            gradientId="humidity-gradient"
            unit="%"
            precision={0}
          />
        </section>

        <ReadingsTable readings={readings} />
      </section>
    </main>
  );
}
