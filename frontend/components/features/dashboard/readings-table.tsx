import { Leaf } from "lucide-react";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
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

      <Table className="table-fixed text-left">
        <TableCaption className="sr-only">Bảng nhiệt độ và độ ẩm theo thời gian</TableCaption>
        <TableHeader>
          <TableRow className="border-border/60 text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground hover:bg-transparent">
            <TableHead className="w-1/3 px-4 font-bold text-muted-foreground sm:px-6">Thời gian</TableHead>
            <TableHead className="w-1/3 px-2 font-bold text-muted-foreground">Nhiệt độ</TableHead>
            <TableHead className="w-1/3 px-2 font-bold text-muted-foreground">Độ ẩm</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...readings].reverse().map((reading) => (
            <TableRow
              key={`${reading.node_name}-${reading.timestamp}`}
              className="border-border/40 text-sm hover:bg-secondary/35"
            >
              <TableCell className="px-4 py-4 font-mono text-xs font-bold sm:px-6">
                {formatDateTime(reading.timestamp)}
              </TableCell>
              <TableCell className="px-2 py-4 font-bold text-[#ffad89]">
                {formatMetric(reading.temperature_celsius, "°C")}
              </TableCell>
              <TableCell className="px-2 py-4 font-bold text-[#7dd7fa]">
                {formatMetric(reading.humidity_percent, "%", 0)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}
