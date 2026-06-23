import type { Metadata } from "next";
import { AuthRoute } from "@/components/features/auth/auth-route";

export const metadata: Metadata = {
  title: "Đăng nhập | AeroField",
  description: "Đăng nhập để sử dụng AI Agent của AeroField.",
};

export default function LoginPage() {
  return <AuthRoute />;
}
