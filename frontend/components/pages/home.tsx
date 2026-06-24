"use client";

import { Button } from "@/components/ui/button";
import { ADMIN_ENTRY_PATH, OPERATOR_ENTRY_PATH } from "@/lib/auth-constants";
import { useAuthStore } from "@/lib/auth-store";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

function Nav() {
  const authStatus = useAuthStore((state) => state.authStatus);
  const user = useAuthStore((state) => state.user);
  const entryPath = user?.role === "admin" ? ADMIN_ENTRY_PATH : OPERATOR_ENTRY_PATH;

  return (
    <nav
      className="flex items-center gap-2"
      aria-label="Điều hướng chính"
    >
      <Button asChild>
        <Link href={authStatus === "authenticated" ? entryPath : "/login"}>
          {authStatus === "authenticated" && user?.role === "admin"
            ? "Mở trang quản trị"
            : authStatus === "authenticated"
              ? "Mở bảng điều khiển"
              : "Đăng nhập"}
          <ArrowRight />
        </Link>
      </Button>
    </nav>
  );
}

function GuestLoginButton() {
  const authStatus = useAuthStore((state) => state.authStatus);
  const user = useAuthStore((state) => state.user);
  const entryPath = user?.role === "admin" ? ADMIN_ENTRY_PATH : OPERATOR_ENTRY_PATH;

  return (
    <Button
      asChild
      size="lg"
    >
      <Link href={authStatus === "authenticated" ? entryPath : "/login"}>
        {authStatus === "authenticated" && user?.role === "admin"
          ? "Mở trung tâm quản trị"
          : authStatus === "authenticated"
            ? "Mở trung tâm điều phối"
            : "Đăng nhập để điều phối"}
        <ArrowRight />
      </Link>
    </Button>
  );
}

export { GuestLoginButton, Nav };
