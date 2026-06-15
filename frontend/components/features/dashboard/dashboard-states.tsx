import Link from "next/link";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

type DashboardMessageProps = {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
};

export function DashboardMessage({ icon: Icon, title, description, action }: DashboardMessageProps) {
  return (
    <main className="app-shell relative grid min-h-screen place-items-center overflow-hidden px-4 text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <section className="relative w-full max-w-lg rounded-[1.5rem] border border-border bg-card/85 p-6 text-center shadow-[0_24px_80px_rgb(0_0_0/0.25)] backdrop-blur-sm sm:p-8">
        <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-secondary text-primary">
          <Icon className="size-6" />
        </span>
        <h1 className="mt-5 text-2xl font-bold tracking-[-0.03em]">{title}</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{description}</p>
        <div className="mt-6 flex justify-center gap-3">
          {action}
          <Button
            asChild
            variant="outline"
          >
            <Link href="/">Trang chủ</Link>
          </Button>
        </div>
      </section>
    </main>
  );
}

export function DashboardLoading() {
  return (
    <main
      className="app-shell min-h-screen px-4 py-8 text-foreground sm:px-6 lg:px-8"
      aria-busy="true"
      aria-label="Đang tải dashboard"
    >
      <div className="mx-auto max-w-[1440px]">
        <div className="h-12 w-48 animate-pulse rounded-xl bg-secondary" />
        <div className="mt-16 h-12 max-w-xl animate-pulse rounded-xl bg-secondary" />
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-32 animate-pulse rounded-2xl border border-border bg-card/70"
            />
          ))}
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {[0, 1].map((item) => (
            <div
              key={item}
              className="h-80 animate-pulse rounded-[1.5rem] border border-border bg-card/70"
            />
          ))}
        </div>
      </div>
    </main>
  );
}
