import { Gauge, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CostSummary } from "@/types/cost-management";
import { formatDateTime, formatUsd } from "./cost-management-formatters";

export function AdminHero({
  summary,
  isRefreshing,
  onRefresh,
}: {
  summary: CostSummary;
  isRefreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <section className="reveal py-8 sm:py-10">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-4 flex items-center gap-2 text-primary">
            <span className="size-2 rounded-full bg-primary shadow-[0_0_14px_var(--primary)]" />
            <span className="eyebrow">Admin · Cost Management</span>
          </div>
          <h1 className="max-w-3xl text-4xl font-bold leading-[1.02] tracking-[-0.045em] sm:text-5xl">
            Trạm kiểm soát chi phí trợ lý AI
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
            Theo dõi token, chi phí ước tính và ngân sách tháng cho các lần gọi LLM trong AI Agent.
          </p>
          {summary.pricing_configured && (
            <p className="mt-3 text-xs font-medium text-muted-foreground">
              Đơn giá: {summary.pricing_provider ?? "registry"} · {summary.pricing_model ?? "model hiện tại"}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card/60 px-4 py-3 backdrop-blur-sm">
          <Gauge className="size-6 shrink-0 text-primary" />
          <div className="min-w-0">
            <p className="truncate text-sm font-bold">{formatUsd(summary.total_cost_usd)}</p>
            <p className="text-xs text-muted-foreground">
              {formatDateTime(summary.range.start)} – {formatDateTime(summary.range.end)}
            </p>
          </div>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Làm mới dữ liệu chi phí"
            disabled={isRefreshing}
            onClick={onRefresh}
          >
            <RefreshCw className={isRefreshing ? "animate-spin" : ""} />
          </Button>
        </div>
      </div>
    </section>
  );
}
