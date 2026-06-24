"use client";

import { AlertCircle, Database, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDashboardTelemetryQuery } from "@/lib/api-hooks";
import { DashboardContent } from "./dashboard-content";
import { DashboardLoading, DashboardMessage } from "./dashboard-states";

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
        title="Chưa có dữ liệu cảm biến"
        description="Hãy kết nối cảm biến với nhiệm vụ hoặc chạy dữ liệu demo để bắt đầu theo dõi."
      />
    );
  }

  return (
    <DashboardContent
      readings={telemetryQuery.data.data}
      isRefreshing={telemetryQuery.isFetching}
      onRefresh={() => telemetryQuery.refetch()}
    />
  );
}
