"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Home, LogOut, Radar } from "lucide-react";
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

  async function handleLogout() {
    try {
      await logoutMutation.mutateAsync();
      queryClient.removeQueries({ queryKey: ["auth"] });
      clearAuth();
      router.replace(PublicRouter.Home);
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
            Field operations
          </span>
        </div>
      </Link>

      <nav
        className="flex min-w-0 items-center gap-1 sm:gap-2"
        aria-label="Điều hướng dashboard"
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
            aria-label={logoutMutation.isPending ? "Đang đăng xuất" : "Đăng xuất"}
            disabled={logoutMutation.isPending}
            onClick={handleLogout}
          >
            {logoutMutation.isPending ? <Spinner /> : <LogOut />}
          </Button>
        </div>
      </nav>
    </header>
  );
}
