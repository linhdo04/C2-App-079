"use client";

import { CircleDollarSign, Plane, Users, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ADMIN_ENTRY_PATH } from "@/lib/auth-constants";

type AdminNavigationItem = {
  label: string;
  description: string;
  icon: LucideIcon;
  href?: string;
};

const ADMIN_NAVIGATION: AdminNavigationItem[] = [
  {
    label: "Chi phí AI",
    description: "Ngân sách và usage",
    icon: CircleDollarSign,
    href: ADMIN_ENTRY_PATH,
  },
  {
    label: "Người dùng",
    description: "Tài khoản và phân quyền",
    icon: Users,
  },
  {
    label: "Drone",
    description: "Thiết bị và trạng thái",
    icon: Plane,
  },
];

export function AdminSidebar({ isOpen = false, onClose }: { isOpen?: boolean; onClose?: () => void }) {
  const pathname = usePathname();

  return (
    <>
      <aside className="hidden w-64 shrink-0 border-r border-border/60 pr-4 pt-6 lg:block">
        <SidebarContent pathname={pathname} />
      </aside>
      {isOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            aria-label="Đóng menu quản trị"
            onClick={onClose}
          />
          <aside
            className="relative h-full w-[min(18rem,calc(100vw-2rem))] overflow-y-auto border-r border-border bg-card p-4 text-card-foreground shadow-2xl"
            aria-label="Điều hướng quản trị"
          >
            <div className="mb-5 flex min-h-11 items-center justify-between gap-3 border-b border-border/60 pb-4">
              <p className="text-sm font-bold">Menu quản trị</p>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Đóng menu quản trị"
                onClick={onClose}
              >
                <X />
              </Button>
            </div>
            <SidebarContent
              pathname={pathname}
              onNavigate={onClose}
            />
          </aside>
        </div>
      )}
    </>
  );
}

function SidebarContent({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav aria-label="Điều hướng quản trị">
      <p className="px-3 text-[0.65rem] font-bold uppercase tracking-[0.16em] text-muted-foreground">
        Quản lý hệ thống
      </p>
      <ul className="mt-3 grid gap-1.5">
        {ADMIN_NAVIGATION.map((item) => {
          const Icon = item.icon;
          const isActive = item.href !== undefined && pathname.startsWith(item.href);

          return (
            <li key={item.label}>
              {item.href ? (
                <Link
                  href={item.href}
                  className={`flex min-h-14 items-center gap-3 rounded-xl border px-3 py-2 transition-colors ${
                    isActive
                      ? "border-primary/30 bg-primary/12 text-foreground"
                      : "border-transparent text-muted-foreground hover:border-border hover:bg-secondary/55 hover:text-foreground"
                  }`}
                  aria-current={isActive ? "page" : undefined}
                  onClick={onNavigate}
                >
                  <span
                    className={`grid size-9 shrink-0 place-items-center rounded-lg ${isActive ? "bg-primary text-primary-foreground" : "bg-secondary"}`}
                  >
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-bold">{item.label}</span>
                    <span className="block truncate text-[0.68rem] text-muted-foreground">{item.description}</span>
                  </span>
                </Link>
              ) : (
                <div
                  className="flex min-h-14 items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-muted-foreground/70"
                  aria-disabled="true"
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-secondary/60">
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-bold">{item.label}</span>
                    <span className="block truncate text-[0.68rem]">{item.description}</span>
                  </span>
                  <span className="rounded-full border border-border px-2 py-1 text-[0.58rem] font-bold uppercase tracking-wide">
                    Sắp có
                  </span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
