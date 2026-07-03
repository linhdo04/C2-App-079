"use client";

import { AlertTriangle, RefreshCw, Sparkles } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  useCostSummaryQuery,
  useCostUsageQuery,
  useEvaluationMetricsQuery,
  useUserMonthlyCostReportQuery,
} from "@/lib/api-hooks";
import { AdminHero } from "./admin-hero";
import { AdminLoading } from "./admin-loading";
import { BudgetPanel } from "./budget-panel";
import { CostOverview } from "./cost-overview";
import { CostTrend } from "./cost-trend";
import { EvaluationMetricsPanel } from "./evaluation-metrics-panel";
import { UsageLedger } from "./usage-ledger";
import { UserMonthlyReportPanel } from "./user-monthly-report-panel";

export function CostManagementDashboard() {
  const summaryQuery = useCostSummaryQuery();
  const usageQuery = useCostUsageQuery();
  const evaluationQuery = useEvaluationMetricsQuery();
  const userReportQuery = useUserMonthlyCostReportQuery();

  const isLoading =
    summaryQuery.isPending || usageQuery.isPending || evaluationQuery.isPending || userReportQuery.isPending;
  const isRefreshing =
    summaryQuery.isFetching || usageQuery.isFetching || evaluationQuery.isFetching || userReportQuery.isFetching;

  function refreshDashboard() {
    void summaryQuery.refetch();
    void usageQuery.refetch();
    void evaluationQuery.refetch();
    void userReportQuery.refetch();
  }

  if (isLoading) {
    return <AdminLoading />;
  }

  if (summaryQuery.isError || usageQuery.isError || evaluationQuery.isError || userReportQuery.isError) {
    const error = summaryQuery.error ?? usageQuery.error ?? evaluationQuery.error ?? userReportQuery.error;
    return (
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
            onClick={refreshDashboard}
          >
            <RefreshCw />
            Thử lại
          </Button>
        </div>
      </section>
    );
  }

  return (
    <>
      <AdminHero
        summary={summaryQuery.data}
        isRefreshing={isRefreshing}
        onRefresh={refreshDashboard}
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
      <EvaluationMetricsPanel evaluation={evaluationQuery.data} />
      <UserMonthlyReportPanel report={userReportQuery.data} />
      <UsageLedger events={usageQuery.data.data} />
    </>
  );
}
