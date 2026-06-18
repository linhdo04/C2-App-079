import type { Metadata } from "next";
import { AuthRoute } from "@/components/features/auth/auth-route";

export const metadata: Metadata = {
  title: "Đăng ký | AeroField",
  description: "Tạo tài khoản để sử dụng AI Agent của AeroField.",
};

export default function RegisterPage() {
  return <AuthRoute mode="register" />;
}
