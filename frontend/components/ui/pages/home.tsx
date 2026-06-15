"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { hasAuthSession } from "@/lib/auth-client";
import { useAuthStore } from "@/lib/auth-store";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

function useHomeAuth() {
  const { authStatus, isBooting, setAuthenticated, setBooting } = useAuthStore();

  useEffect(() => {
    setAuthenticated(hasAuthSession());
    setBooting(false);
  }, [setAuthenticated, setBooting]);

  return {
    isAuthenticated: authStatus === "authenticated",
    isBooting,
  };
}

function Nav() {
  const { isAuthenticated, isBooting } = useHomeAuth();

  if (isBooting) {
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
        <Link href="/dashboard">Dashboard</Link>
      </Button>
      {isAuthenticated ? (
        <Button asChild>
          <Link href="/agent">
            AI Agent
            <ArrowRight />
          </Link>
        </Button>
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
