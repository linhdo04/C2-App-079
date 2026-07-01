import type { ReactNode } from "react";
import { AdminShell } from "@/components/features/admin/layout/admin-shell";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
