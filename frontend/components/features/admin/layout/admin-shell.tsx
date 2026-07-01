"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Menu, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { PublicRouter } from "@/enums/public-routers";
import { useLogoutMutation } from "@/lib/api-hooks";
import { ADMIN_ENTRY_PATH } from "@/lib/auth-constants";
import { useAuthStore } from "@/lib/auth-store";
import { AdminSidebar } from "./admin-sidebar";

export function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const logoutMutation = useLogoutMutation();
  const [isLogoutConfirmOpen, setIsLogoutConfirmOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  async function handleLogout() {
    try {
      await logoutMutation.mutateAsync();
      queryClient.removeQueries({ queryKey: ["auth"] });
      clearAuth();
      router.replace(PublicRouter.Home);
      setIsLogoutConfirmOpen(false);
      toast.success("Bạn đã đăng xuất thành công.");
    } catch {
      toast.error("Có lỗi xảy ra, vui lòng thử lại sau.");
    }
  }

  return (
    <main className="app-shell relative min-h-screen overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute right-[-6rem] top-[-6rem] h-80 w-80 rounded-full bg-primary/10 blur-3xl" />
      <section className="relative mx-auto w-full max-w-[1440px] px-4 pb-10 sm:px-6 lg:px-8">
        <header className="flex min-h-20 items-center justify-between gap-2 border-b border-border/60">
          <div className="flex min-w-0 items-center gap-1 sm:gap-3">
            <Button
              size="icon"
              variant="ghost"
              className="lg:hidden"
              aria-label="Mở menu quản trị"
              aria-expanded={isSidebarOpen}
              onClick={() => setIsSidebarOpen(true)}
            >
              <Menu />
            </Button>
            <Link
              href={ADMIN_ENTRY_PATH}
              className="flex min-w-0 items-center gap-2 sm:gap-3"
              aria-label="Trang quản trị chi phí"
            >
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
                <ShieldCheck className="size-5" />
              </span>
              <div className="min-w-0">
                <span className="block text-base font-bold tracking-[-0.03em]">Quản trị AeroField</span>
                <span className="hidden text-[0.62rem] font-bold uppercase tracking-[0.16em] text-muted-foreground sm:block">
                  Kiểm soát chi phí AI
                </span>
              </div>
            </Link>
          </div>
          <Button
            variant="outline"
            size="sm"
            aria-haspopup="dialog"
            aria-expanded={isLogoutConfirmOpen}
            disabled={logoutMutation.isPending}
            onClick={() => setIsLogoutConfirmOpen(true)}
          >
            {logoutMutation.isPending ? <Spinner /> : <LogOut />}
            <span className="hidden sm:inline">{logoutMutation.isPending ? "Đang đăng xuất" : "Đăng xuất"}</span>
          </Button>
        </header>
        <div className="flex min-w-0">
          <AdminSidebar
            isOpen={isSidebarOpen}
            onClose={() => setIsSidebarOpen(false)}
          />
          <div className="min-w-0 flex-1 lg:pl-6">{children}</div>
        </div>
      </section>
      {isLogoutConfirmOpen && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 px-4 backdrop-blur-sm"
          role="presentation"
        >
          <button
            className="absolute inset-0"
            type="button"
            aria-label="Huỷ đăng xuất"
            disabled={logoutMutation.isPending}
            onClick={() => setIsLogoutConfirmOpen(false)}
          />
          <section
            className="relative w-full max-w-sm rounded-[1.5rem] border border-border bg-card/95 p-5 text-foreground shadow-[0_30px_100px_rgb(0_0_0/0.45)] backdrop-blur-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-logout-confirm-title"
            aria-describedby="admin-logout-confirm-description"
          >
            <span className="grid size-12 place-items-center rounded-2xl bg-destructive-muted text-destructive-text">
              <LogOut className="size-5" />
            </span>
            <h2
              id="admin-logout-confirm-title"
              className="mt-4 text-xl font-bold tracking-[-0.03em]"
            >
              Xác nhận đăng xuất
            </h2>
            <p
              id="admin-logout-confirm-description"
              className="mt-2 text-sm leading-6 text-muted-foreground"
            >
              Bạn có chắc muốn kết thúc phiên quản trị hiện tại và quay về trang chủ không?
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <Button
                type="button"
                variant="outline"
                disabled={logoutMutation.isPending}
                onClick={() => setIsLogoutConfirmOpen(false)}
              >
                Huỷ
              </Button>
              <Button
                type="button"
                variant="destructive"
                disabled={logoutMutation.isPending}
                onClick={handleLogout}
              >
                {logoutMutation.isPending ? (
                  <>
                    <Spinner />
                    Đang đăng xuất
                  </>
                ) : (
                  <>
                    <LogOut />
                    Đăng xuất
                  </>
                )}
              </Button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
