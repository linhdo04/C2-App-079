import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Đăng nhập | AeroField",
  description: "Đăng nhập để sử dụng trợ lý AI của AeroField.",
};

export default function RegisterPage() {
  redirect("/login");
}
