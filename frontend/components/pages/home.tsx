"use client";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth-store";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

function Nav() {
  const authStatus = useAuthStore((state) => state.authStatus);

  return (
    <nav
      className="flex items-center gap-2"
      aria-label="Điều hướng chính"
    >
      <Button asChild>
        <Link href={authStatus === "authenticated" ? "/dashboard" : "/login"}>
          {authStatus === "authenticated" ? "Mở bảng điều khiển" : "Đăng nhập"}
          <ArrowRight />
        </Link>
      </Button>
    </nav>
  );
}

function GuestLoginButton() {
  const authStatus = useAuthStore((state) => state.authStatus);

  return (
    <Button
      asChild
      size="lg"
    >
      <Link href={authStatus === "authenticated" ? "/dashboard" : "/login"}>
        {authStatus === "authenticated" ? "Mở trung tâm điều phối" : "Đăng nhập để điều phối"}
        <ArrowRight />
      </Link>
    </Button>
  );
}

export { GuestLoginButton, Nav };
