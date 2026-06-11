import type { Metadata } from "next";
import { EnvironmentDashboard } from "@/components/features/dashboard/environment-dashboard";

export const metadata: Metadata = {
  title: "Dashboard môi trường",
  description: "Theo dõi nhiệt độ và độ ẩm tại cánh đồng theo thời gian thực.",
};

export default function DashboardPage() {
  return <EnvironmentDashboard />;
}
