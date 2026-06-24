"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Home, LogOut, Radar, ShieldCheck } from "lucide-react";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { PublicRouter } from "@/enums/public-routers";
import { useLogoutMutation } from "@/lib/api-hooks";
import { useAuthStore } from "@/lib/auth-store";

export function DashboardHeader() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const user = useAuthStore((state) => state.user);
  const logoutMutation = useLogoutMutation();
  const [isLogoutConfirmOpen, setIsLogoutConfirmOpen] = useState(false);

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
    <header className="flex min-h-20 items-center justify-between gap-2 border-b border-border/60">
      <Link
        href="/"
        className="flex min-w-0 items-center gap-2 sm:gap-3"
        aria-label="AeroField - Trang chủ"
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
          <Radar className="size-5" />
        </span>
        <div className="min-w-0">
          <span className="block text-base font-bold tracking-[-0.03em]">AeroField</span>
          <span className="hidden text-[0.62rem] font-bold uppercase tracking-[0.16em] text-muted-foreground sm:block">
            Vận hành cánh đồng
          </span>
        </div>
      </Link>

      <nav
        className="flex min-w-0 items-center gap-1 sm:gap-2"
        aria-label="Điều hướng bảng điều khiển"
      >
        <Button
          asChild
          variant="ghost"
          size="icon"
        >
          <Link
            href="/"
            aria-label="Trang chủ"
          >
            <Home />
          </Link>
        </Button>
        {user?.role === "admin" && (
          <Button
            asChild
            variant="ghost"
            size="icon"
          >
            <Link
              href="/admin/cost-management"
              aria-label="Quản trị chi phí"
            >
              <ShieldCheck />
            </Link>
          </Button>
        )}
        <div className="flex min-w-0 items-center gap-2 rounded-xl border border-border/70 bg-card/65 p-1 pl-2">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-secondary text-xs font-bold text-primary">
            {user?.name.trim().charAt(0).toUpperCase() ?? "?"}
          </span>
          <div className="hidden min-w-0 sm:block">
            <p className="max-w-32 truncate text-xs font-bold">{user?.name ?? "Tài khoản"}</p>
            <p className="max-w-32 truncate text-[10px] text-muted-foreground">{user?.email}</p>
          </div>
          <Button
            size="icon"
            variant="ghost"
            aria-label={logoutMutation.isPending ? "Đang đăng xuất" : "Mở xác nhận đăng xuất"}
            aria-haspopup="dialog"
            aria-expanded={isLogoutConfirmOpen}
            disabled={logoutMutation.isPending}
            onClick={() => setIsLogoutConfirmOpen(true)}
          >
            {logoutMutation.isPending ? <Spinner /> : <LogOut />}
          </Button>
        </div>
      </nav>

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
            aria-labelledby="logout-confirm-title"
            aria-describedby="logout-confirm-description"
          >
            <span className="grid size-12 place-items-center rounded-2xl bg-destructive-muted text-destructive-text">
              <LogOut className="size-5" />
            </span>
            <h2
              id="logout-confirm-title"
              className="mt-4 text-xl font-bold tracking-[-0.03em]"
            >
              Xác nhận đăng xuất
            </h2>
            <p
              id="logout-confirm-description"
              className="mt-2 text-sm leading-6 text-muted-foreground"
            >
              Bạn có chắc muốn kết thúc phiên làm việc hiện tại và quay về trang chủ không?
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
    </header>
  );
}
