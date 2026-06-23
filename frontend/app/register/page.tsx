import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Đăng nhập | AeroField",
  description: "Đăng nhập để sử dụng AI Agent của AeroField.",
};

export default function RegisterPage() {
  redirect("/login");
}
