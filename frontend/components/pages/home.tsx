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
      {authStatus === "authenticated" ? (
        <>
          <Button asChild>
            <Link href="/dashboard">
              Dashboard
              <ArrowRight />
            </Link>
          </Button>
        </>
      ) : (
        <>
          {/* <Button
            asChild
            variant="ghost"
            className="hidden md:inline-flex"
          >
            <Link href="/login">Đăng nhập</Link>
          </Button> */}
          <Button asChild>
            <Link href="/login">
              Đăng nhập
              <ArrowRight />
            </Link>
          </Button>
        </>
      )}
    </nav>
  );
}

function GuestLoginButton() {
  const authStatus = useAuthStore((state) => state.authStatus);

  return (
    <>
      {authStatus === "authenticated" ? (
        <Button
          asChild
          size="lg"
        >
          <Link href="/dashboard">
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
