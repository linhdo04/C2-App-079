import type { Metadata } from "next";
import { AuthRoute } from "@/components/features/auth/auth-route";

export const metadata: Metadata = {
  title: "Đăng nhập | Autonomous Drones",
  description: "Đăng nhập để sử dụng AI Agent của Autonomous Drones.",
};

export default function LoginPage() {
  return <AuthRoute mode="login" />;
}
