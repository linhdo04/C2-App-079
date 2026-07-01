import { AlertTriangle, Bot, CircleDollarSign, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { CostSummary } from "@/types/cost-management";
import { formatNumber, formatUsd } from "./cost-management-formatters";

export function CostOverview({ summary }: { summary: CostSummary }) {
  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricCard
        label="Chi phí tháng"
        value={formatUsd(summary.total_cost_usd)}
        detail={`${summary.budget.usage_percent}% ngân sách`}
        icon={CircleDollarSign}
        accent="text-primary"
      />
      <MetricCard
        label="Tổng token"
        value={formatNumber(summary.total_tokens)}
        detail={`${formatNumber(summary.input_tokens)} vào · ${formatNumber(summary.output_tokens)} ra`}
        icon={Bot}
        accent="text-[#59c7f3]"
      />
      <MetricCard
        label="Lượt gọi LLM"
        value={formatNumber(summary.request_count)}
        detail="Tất cả operation của AI Agent"
        icon={Sparkles}
        accent="text-[#ffad89]"
      />
      <MetricCard
        label="Trạng thái ngân sách"
        value={summary.budget.is_alerting ? "Cảnh báo" : "Ổn định"}
        detail={`${formatUsd(summary.budget.spent_usd)} / ${formatUsd(summary.budget.monthly_budget_usd)}`}
        icon={AlertTriangle}
        accent={summary.budget.is_alerting ? "text-destructive-text" : "text-success"}
      />
    </dl>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  accent: string;
}) {
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
