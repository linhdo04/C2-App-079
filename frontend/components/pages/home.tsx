"use client";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth-store";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

function Nav() {
  const { authStatus, isBooting } = useAuthStore();

  return (
    <nav
      className="flex items-center gap-2"
      aria-label="Điều hướng chính"
    >
      {authStatus === "authenticated" || isBooting ? (
        <>
          <Button
            asChild
            variant="ghost"
            className="hidden sm:inline-flex"
          >
            <Link href="/dashboard">Dashboard</Link>
          </Button>
          <Button asChild>
            <Link href="/agent">
              AI Agent
              <ArrowRight />
            </Link>
          </Button>
        </>
      ) : (
        <>
          <Button
            asChild
            variant="ghost"
            className="hidden md:inline-flex"
          >
            <Link href="/login">Đăng nhập</Link>
          </Button>
          <Button asChild>
            <Link href="/register">
              Bắt đầu
              <ArrowRight />
            </Link>
          </Button>
        </>
      )}
    </nav>
  );
}

function GuestLoginButton() {
  const { authStatus, isBooting } = useAuthStore();

  return (
    <>
      {isBooting || authStatus === "authenticated" ? (
        <Button
          asChild
          size="lg"
        >
          <Link href="/agent">
            Mở trung tâm điều phối
            <ArrowRight />
          </Link>
        </Button>
      ) : (
        <Button
          asChild
          size="lg"
          variant="outline"
        >
          <Link href="/login">Tôi đã có tài khoản</Link>
        </Button>
      )}
    </>
  );
}

export { GuestLoginButton, Nav };
