import Link from "next/link";
import { ArrowUpRight, Bot, Radar } from "lucide-react";
import { Button } from "@/components/ui/button";

export function DashboardHeader() {
  return (
    <header className="flex min-h-20 items-center justify-between border-b border-border/60">
      <Link
        href="/"
        className="flex items-center gap-3"
        aria-label="AeroField - Trang chủ"
      >
        <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
          <Radar className="size-5" />
        </span>
        <div>
          <span className="block text-base font-bold tracking-[-0.03em]">AeroField</span>
          <span className="hidden text-[0.62rem] font-bold uppercase tracking-[0.16em] text-muted-foreground sm:block">
            Field operations
          </span>
        </div>
      </Link>

      <nav
        className="flex items-center gap-2"
        aria-label="Điều hướng dashboard"
      >
        <Button
          asChild
          variant="ghost"
          className="hidden sm:inline-flex"
        >
          <Link href="/agent">
            <Bot />
            AI Agent
          </Link>
        </Button>
        <Button
          asChild
          variant="outline"
        >
          <Link href="/">
            Trang chủ
            <ArrowUpRight />
          </Link>
        </Button>
      </nav>
    </header>
  );
}
