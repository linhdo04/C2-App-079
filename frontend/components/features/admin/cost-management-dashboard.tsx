"use client";

import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CircleDollarSign,
  Gauge,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import type { FormEvent, ReactNode } from "react";
import { useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useCostSummaryQuery, useCostUsageQuery, useUpdateCostBudgetMutation } from "@/lib/api-hooks";
import { ADMIN_ENTRY_PATH } from "@/lib/auth-constants";
import type { CostSummary, CostUsageEvent } from "@/types/cost-management";

const USD_FORMATTER = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 4,
});

const NUMBER_FORMATTER = new Intl.NumberFormat("vi-VN");

function formatUsd(value: number) {
  return USD_FORMATTER.format(value);
}

function formatNumber(value: number) {
  return NUMBER_FORMATTER.format(value);
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(value));
}

export function CostManagementDashboard() {
  const summaryQuery = useCostSummaryQuery();
  const usageQuery = useCostUsageQuery();

  const isLoading = summaryQuery.isPending || usageQuery.isPending;
  const isRefreshing = summaryQuery.isFetching || usageQuery.isFetching;

  if (isLoading) {
    return <AdminLoading />;
  }

  if (summaryQuery.isError || usageQuery.isError) {
    const error = summaryQuery.error ?? usageQuery.error;
    return (
      <AdminShell>
        <section className="grid min-h-[60vh] place-items-center py-10">
          <div className="w-full max-w-lg rounded-[1.5rem] border border-border bg-card/90 p-6 text-center shadow-[0_28px_90px_rgb(0_0_0/0.32)] backdrop-blur-sm">
            <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-destructive-muted text-destructive-text">
              <AlertTriangle className="size-5" />
            </span>
            <h1 className="mt-4 text-2xl font-bold tracking-[-0.035em]">Không thể tải dữ liệu chi phí</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              {error instanceof Error ? error.message : "Vui lòng thử lại sau."}
            </p>
            <Button
              className="mt-6"
              onClick={() => {
                void summaryQuery.refetch();
                void usageQuery.refetch();
              }}
            >
              <RefreshCw />
              Thử lại
            </Button>
          </div>
        </section>
      </AdminShell>
    );
  }

  return (
    <AdminShell>
      <AdminHero
        summary={summaryQuery.data}
        isRefreshing={isRefreshing}
        onRefresh={() => {
          void summaryQuery.refetch();
          void usageQuery.refetch();
        }}
      />
      <CostOverview summary={summaryQuery.data} />
      {!summaryQuery.data.pricing_configured && (
        <Alert className="mt-4 border-primary/35 bg-primary/10 text-foreground">
          <Sparkles className="absolute left-4 top-4 size-4 text-primary" />
          <div className="pl-7">
            <AlertTitle>Chưa xác định được đơn giá token</AlertTitle>
            <AlertDescription className="text-muted-foreground">
              Hệ thống đã ghi nhận token, nhưng chi phí USD sẽ bằng 0 cho đến khi model hiện tại có bảng giá tự động
              trong pricing registry.
            </AlertDescription>
          </div>
        </Alert>
      )}
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <CostTrend summary={summaryQuery.data} />
        <BudgetPanel summary={summaryQuery.data} />
      </div>
      <UsageLedger events={usageQuery.data.data} />
    </AdminShell>
  );
}

function AdminShell({ children }: { children: ReactNode }) {
  return (
    <main className="app-shell relative min-h-screen overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute right-[-6rem] top-[-6rem] h-80 w-80 rounded-full bg-primary/10 blur-3xl" />
      <section className="relative mx-auto w-full max-w-[1440px] px-4 pb-10 sm:px-6 lg:px-8">
        <header className="flex min-h-20 items-center justify-between gap-3 border-b border-border/60">
          <Link
            href={ADMIN_ENTRY_PATH}
            className="flex min-w-0 items-center gap-3"
            aria-label="Trang quản trị chi phí"
          >
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
              <ShieldCheck className="size-5" />
            </span>
            <div className="min-w-0">
              <span className="block text-base font-bold tracking-[-0.03em]">Quản trị AeroField</span>
              <span className="hidden text-[0.62rem] font-bold uppercase tracking-[0.16em] text-muted-foreground sm:block">
                Kiểm soát chi phí AI
              </span>
            </div>
          </Link>
          <Button
            asChild
            variant="outline"
            size="sm"
          >
            <Link href={ADMIN_ENTRY_PATH}>
              <ArrowLeft />
              Quản trị chi phí
            </Link>
          </Button>
        </header>
        {children}
      </section>
    </main>
  );
}

function AdminHero({
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

function CostOverview({ summary }: { summary: CostSummary }) {
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

function CostTrend({ summary }: { summary: CostSummary }) {
  const points = useMemo(
    () =>
      summary.daily.map((item) => ({
        ...item,
        label: formatDate(item.date),
      })),
    [summary.daily],
  );

  return (
    <section className="reveal reveal-delay-1 min-w-0 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 shadow-[0_24px_80px_rgb(0_0_0/0.2)] backdrop-blur-sm">
      <div className="p-5 pb-2 sm:p-6 sm:pb-2">
        <h2 className="text-lg font-bold tracking-[-0.025em]">Xu hướng chi phí theo ngày</h2>
        <p className="mt-1 text-xs text-muted-foreground">Tính theo usage metadata đã ghi nhận từ các lần gọi LLM.</p>
      </div>
      <div
        className="h-72 w-full px-2 pb-4 pt-3 sm:px-4 sm:pb-5"
        role="img"
        aria-label="Biểu đồ chi phí AI theo ngày"
      >
        {points.length === 0 ? (
          <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
            Chưa có dữ liệu chi phí trong khoảng thời gian này.
          </div>
        ) : (
          <ResponsiveContainer
            width="100%"
            height="100%"
            minWidth={0}
            initialDimension={{ width: 640, height: 260 }}
          >
            <AreaChart
              data={points}
              margin={{ top: 8, right: 8, left: -18, bottom: 0 }}
              accessibilityLayer
            >
              <defs>
                <linearGradient
                  id="cost-gradient"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor="#b9f34a"
                    stopOpacity={0.28}
                  />
                  <stop
                    offset="100%"
                    stopColor="#b9f34a"
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                vertical={false}
                stroke="var(--border)"
                strokeDasharray="5 7"
              />
              <XAxis
                dataKey="label"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                width={56}
                tick={{ fill: "var(--muted-foreground)", fontSize: 10 }}
                tickFormatter={(tick: number) => `$${tick.toFixed(2)}`}
              />
              <Tooltip
                cursor={{ stroke: "#b9f34a", strokeOpacity: 0.35 }}
                formatter={(tooltipValue) => [formatUsd(Number(tooltipValue)), "Chi phí"]}
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: "0.75rem",
                  color: "var(--card-foreground)",
                  fontSize: "0.75rem",
                }}
                labelStyle={{ color: "var(--muted-foreground)" }}
              />
              <Area
                type="monotone"
                dataKey="cost_usd"
                name="Chi phí"
                stroke="#b9f34a"
                strokeWidth={3}
                fill="url(#cost-gradient)"
                dot={{ r: 3, fill: "#b9f34a", strokeWidth: 0 }}
                activeDot={{
                  r: 6,
                  fill: "var(--card)",
                  stroke: "#b9f34a",
                  strokeWidth: 3,
                }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

function BudgetPanel({ summary }: { summary: CostSummary }) {
  const [monthlyBudget, setMonthlyBudget] = useState(String(summary.budget.monthly_budget_usd));
  const [threshold, setThreshold] = useState(String(summary.budget.alert_threshold_percent));
  const updateBudget = useUpdateCostBudgetMutation();
  const queryClient = useQueryClient();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const monthly_budget_usd = Number(monthlyBudget);
    const alert_threshold_percent = Number(threshold);
    if (Number.isNaN(monthly_budget_usd) || Number.isNaN(alert_threshold_percent)) {
      toast.error("Vui lòng nhập ngân sách và ngưỡng cảnh báo hợp lệ.");
      return;
    }
    try {
      await updateBudget.mutateAsync({
        monthly_budget_usd,
        alert_threshold_percent,
      });
      void queryClient.invalidateQueries({
        queryKey: ["admin", "cost-management"],
      });
      toast.success("Đã cập nhật ngân sách chi phí AI.");
    } catch {
      toast.error("Không thể cập nhật ngân sách. Vui lòng thử lại.");
    }
  }

  return (
    <aside className="reveal reveal-delay-1 rounded-[1.5rem] border border-border/80 bg-card/80 p-5 shadow-[0_24px_80px_rgb(0_0_0/0.18)] backdrop-blur-sm sm:p-6">
      <h2 className="text-lg font-bold tracking-[-0.025em]">Ngân sách tháng</h2>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        V1 chỉ cảnh báo theo ngưỡng, chưa tự động chặn người dùng gọi trợ lý AI.
      </p>
      <div className="mt-5 overflow-hidden rounded-2xl border border-border/70 bg-secondary/45">
        <div
          className="h-3 bg-primary"
          style={{ width: `${Math.min(summary.budget.usage_percent, 100)}%` }}
          aria-hidden="true"
        />
        <div className="p-4">
          <p className="text-2xl font-bold tracking-[-0.04em]">{summary.budget.usage_percent}%</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Đã dùng {formatUsd(summary.budget.spent_usd)} trên {formatUsd(summary.budget.monthly_budget_usd)}
          </p>
        </div>
      </div>
      <form
        className="mt-5 grid gap-4"
        onSubmit={handleSubmit}
      >
        <label className="grid gap-2 text-sm font-bold">
          Ngân sách tháng (USD)
          <Input
            type="number"
            min="0"
            step="0.01"
            value={monthlyBudget}
            onChange={(event) => setMonthlyBudget(event.target.value)}
          />
        </label>
        <label className="grid gap-2 text-sm font-bold">
          Ngưỡng cảnh báo (%)
          <Input
            type="number"
            min="1"
            max="100"
            step="1"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
        </label>
        <Button
          type="submit"
          disabled={updateBudget.isPending}
        >
          {updateBudget.isPending ? <Spinner /> : <Save />}
          Lưu ngân sách
        </Button>
      </form>
    </aside>
  );
}

function UsageLedger({ events }: { events: CostUsageEvent[] }) {
  return (
    <section className="reveal reveal-delay-2 mt-4 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 backdrop-blur-sm">
      <div className="border-b border-border/70 p-5 sm:p-6">
        <h2 className="text-lg font-bold tracking-[-0.025em]">Nhật ký usage gần nhất</h2>
        <p className="mt-1 text-xs text-muted-foreground">25 lần gọi LLM mới nhất trong tháng hiện tại.</p>
      </div>
      <div className="grid gap-3 p-4 sm:hidden">
        {events.map((event) => (
          <article
            key={event.id}
            className="rounded-2xl border border-border/70 bg-secondary/35 p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold">{event.operation}</h3>
                <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(event.occurred_at)}</p>
              </div>
              <span className="text-sm font-bold text-primary">{formatUsd(event.cost_usd)}</span>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {event.model_name} · {formatNumber(event.total_tokens)} token
            </p>
          </article>
        ))}
        {events.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">Chưa có usage nào được ghi nhận.</p>
        )}
      </div>
      <div
        className="hidden max-h-[32rem] overflow-auto sm:block"
        role="region"
        aria-label="Bảng usage LLM gần nhất"
        tabIndex={0}
      >
        <table className="w-full min-w-[52rem] table-fixed caption-bottom text-left text-sm">
          <caption className="sr-only">Bảng usage LLM và chi phí</caption>
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b border-border/60 text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">
              <th className="h-10 w-44 px-6 text-left font-bold">Thời gian</th>
              <th className="h-10 px-2 text-left font-bold">Operation</th>
              <th className="h-10 px-2 text-left font-bold">Model</th>
              <th className="h-10 px-2 text-right font-bold">Token</th>
              <th className="h-10 px-6 text-right font-bold">Chi phí</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr
                key={event.id}
                className="border-b border-border/40 transition-colors last:border-0 hover:bg-secondary/35"
              >
                <td className="px-6 py-4 font-mono text-xs font-bold whitespace-nowrap">
                  {formatDateTime(event.occurred_at)}
                </td>
                <td className="px-2 py-4 font-bold">{event.operation}</td>
                <td className="px-2 py-4 text-xs text-muted-foreground">{event.model_name}</td>
                <td className="px-2 py-4 text-right font-mono text-xs font-bold">{formatNumber(event.total_tokens)}</td>
                <td className="px-6 py-4 text-right font-bold text-primary">{formatUsd(event.cost_usd)}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-10 text-center text-sm text-muted-foreground"
                >
                  Chưa có usage nào được ghi nhận.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AdminLoading() {
  return (
    <AdminShell>
      <div className="py-8 sm:py-10">
        <div className="h-12 max-w-2xl animate-pulse rounded-xl bg-secondary" />
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-32 animate-pulse rounded-2xl border border-border bg-card/70"
            />
          ))}
        </div>
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <div className="h-80 animate-pulse rounded-[1.5rem] border border-border bg-card/70" />
          <div className="h-80 animate-pulse rounded-[1.5rem] border border-border bg-card/70" />
        </div>
      </div>
    </AdminShell>
  );
}
