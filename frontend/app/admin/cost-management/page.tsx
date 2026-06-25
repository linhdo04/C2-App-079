import type { Metadata } from "next";
import { CostManagementDashboard } from "@/components/features/admin/cost-management-dashboard";

export const metadata: Metadata = {
  title: "Quản trị chi phí",
  description: "Theo dõi token, chi phí và ngân sách sử dụng trợ lý AI.",
};

export default function CostManagementPage() {
  return <CostManagementDashboard />;
}
