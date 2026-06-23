import { Leaf } from "lucide-react";
import type { TelemetryReading } from "@/types/dashboard";
import { formatDateTime, formatMetric } from "./dashboard-utils";

type ReadingsTableProps = {
  readings: TelemetryReading[];
};

export function ReadingsTable({ readings }: ReadingsTableProps) {
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

      <div
        className="max-h-[26rem] overflow-auto overscroll-contain sm:max-h-[32rem]"
        role="region"
        aria-label="Danh sách telemetry trong ngày"
        tabIndex={0}
      >
        <table className="w-full min-w-[30rem] table-fixed caption-bottom text-left text-sm">
          <caption className="sr-only">Bảng nhiệt độ và độ ẩm theo thời gian</caption>
          <thead className="sticky top-0 z-10 bg-card shadow-[0_1px_0_hsl(var(--border))]">
            <tr className="border-b border-border/60 text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">
              <th className="h-10 w-1/3 px-4 text-left align-middle font-bold whitespace-nowrap text-muted-foreground sm:px-6">
                Thời gian
              </th>
              <th className="h-10 w-1/3 px-2 text-left align-middle font-bold whitespace-nowrap text-muted-foreground">
                Nhiệt độ
              </th>
              <th className="h-10 w-1/3 px-2 text-left align-middle font-bold whitespace-nowrap text-muted-foreground">
                Độ ẩm
              </th>
            </tr>
          </thead>
          <tbody>
            {[...readings].reverse().map((reading) => (
              <tr
                key={`${reading.node_name}-${reading.timestamp}`}
                className="border-b border-border/40 text-sm transition-colors last:border-0 hover:bg-secondary/35"
              >
                <td className="px-4 py-4 align-middle font-mono text-xs font-bold whitespace-nowrap sm:px-6">
                  {formatDateTime(reading.timestamp)}
                </td>
                <td className="px-2 py-4 align-middle font-bold whitespace-nowrap text-[#ffad89]">
                  {formatMetric(reading.temperature_celsius, "°C")}
                </td>
                <td className="px-2 py-4 align-middle font-bold whitespace-nowrap text-[#7dd7fa]">
                  {formatMetric(reading.humidity_percent, "%")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
