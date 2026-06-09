import type { Metadata } from "next";
import { AuthRoute } from "@/components/features/auth/auth-route";

export const metadata: Metadata = {
  title: "Đăng ký | Autonomous Drones",
  description: "Tạo tài khoản để sử dụng AI Agent của Autonomous Drones.",
};

export default function RegisterPage() {
  return <AuthRoute mode="register" />;
}
