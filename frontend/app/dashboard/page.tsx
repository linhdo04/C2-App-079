import type { Metadata } from "next";
import { Suspense } from "react";
import { AgentChatWidget } from "@/components/features/agent/agent-chat-widget";
import { EnvironmentDashboard } from "@/components/features/dashboard/environment-dashboard";

export const metadata: Metadata = {
  title: "Bảng điều khiển môi trường",
  description: "Theo dõi nhiệt độ và độ ẩm tại cánh đồng theo thời gian thực.",
};

export default function DashboardPage() {
  return (
    <>
      <EnvironmentDashboard />
      <Suspense>
        <AgentChatWidget />
      </Suspense>
    </>
  );
}
