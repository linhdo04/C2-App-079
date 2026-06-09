"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { readSession } from "@/lib/auth-client";
import { useAuthStore } from "@/lib/auth-store";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

function useHomeAuth() {
  const { isBooting, session, setBooting, setSession } = useAuthStore();

  useEffect(() => {
    setSession(readSession());
    setBooting(false);
  }, [setBooting, setSession]);

  return {
    isAuthenticated: session !== null,
    isBooting,
  };
}

function Nav() {
  const { isAuthenticated, isBooting } = useHomeAuth();

  if (isBooting || isAuthenticated) {
    return null;
  }

  return (
    <nav
      className="flex items-center gap-2"
      aria-label="Điều hướng chính"
    >
      <Button
        asChild
        variant="ghost"
        className="hidden sm:inline-flex"
      >
        <Link href="/login">Đăng nhập</Link>
      </Button>
      <Button asChild>
        <Link href="/register">
          Bắt đầu
          <ArrowRight />
        </Link>
      </Button>
    </nav>
  );
}

function GuestLoginButton() {
  const { isAuthenticated, isBooting } = useHomeAuth();

  if (isBooting || isAuthenticated) {
    return null;
  }

  return (
    <Button
      asChild
      size="lg"
      variant="outline"
    >
      <Link href="/login">Tôi đã có tài khoản</Link>
    </Button>
  );
}

export { GuestLoginButton, Nav };
