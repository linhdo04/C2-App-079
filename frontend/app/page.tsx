import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Bot, CloudSun, Radar, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GuestLoginButton, Nav } from "@/components/ui/pages/home";

export const metadata: Metadata = {
  title: "AeroField",
  description: "Trợ lý AI và trung tâm điều phối dữ liệu nông nghiệp chính xác.",
};

export default function Home() {
  return (
    <main className="app-shell relative min-h-screen overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <section className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 sm:px-6 lg:px-8">
        <header className="flex min-h-20 items-center justify-between border-b border-border/60">
          <Link
            href="/"
            className="flex items-center gap-3"
            aria-label="AeroField - Trang chủ"
          >
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Radar className="size-5" />
            </span>
            <span className="text-lg font-bold tracking-[-0.03em]">AeroFieldAeroFieldAeroFieldAeroFieldAeroField</span>
          </Link>
          <Nav />
        </header>

        <div className="grid flex-1 items-center gap-12 py-14 lg:grid-cols-[1.05fr_0.95fr] lg:py-20">
          <div className="reveal">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-2 text-primary">
              <span className="size-1.5 rounded-full bg-primary shadow-[0_0_12px_var(--primary)]" />
              <span className="eyebrow">AI-powered field operations</span>
            </div>
            <h1 className="text-balance max-w-4xl text-5xl font-bold leading-[0.98] tracking-[-0.055em] sm:text-6xl lg:text-7xl">
              Quan sát cánh đồnggggggggg.
              <span className="block text-primary">Ra quyết định nhanh hơn.</span>
            </h1>
            <p className="mt-7 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
              Hợp nhất dữ liệu thời tiết, mùa vụ và thị trường trong một trợ lý vận hành được thiết kế cho nông nghiệp
              chính xác.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Button
                asChild
                size="lg"
              >
                <Link href="/agent">
                  Mở trung tâm điều phối
                  <ArrowRight />
                </Link>
              </Button>
              <GuestLoginButton />
            </div>

            <dl className="mt-12 grid max-w-xl grid-cols-3 gap-4 border-t border-border/60 pt-6">
              <div>
                <dt className="text-2xl font-bold text-foreground">24/7</dt>
                <dd className="mt-1 text-xs leading-5 text-muted-foreground">Sẵn sàng phân tích</dd>
              </div>
              <div>
                <dt className="text-2xl font-bold text-foreground">3 nguồn</dt>
                <dd className="mt-1 text-xs leading-5 text-muted-foreground">Dữ liệu hợp nhất</dd>
              </div>
              <div>
                <dt className="text-2xl font-bold text-foreground">&lt; 1 phút</dt>
                <dd className="mt-1 text-xs leading-5 text-muted-foreground">Để có nhận định</dd>
              </div>
            </dl>
          </div>

          <aside className="reveal reveal-delay-2 relative mx-auto w-full max-w-xl lg:mr-0">
            <div className="absolute -inset-8 rounded-full bg-primary/5 blur-3xl" />
            <div className="relative overflow-hidden rounded-[1.75rem] border border-border bg-card/80 p-3 shadow-[0_30px_100px_rgb(0_0_0/0.35)] backdrop-blur-xl">
              <div className="flex items-center justify-between border-b border-border/70 px-3 py-3">
                <div className="flex items-center gap-2">
                  <span className="size-2 rounded-full bg-success" />
                  <span className="eyebrow text-muted-foreground">Operations online</span>
                </div>
                <span className="font-mono text-[0.65rem] text-muted-foreground">09 JUN 2026</span>
              </div>

              <div className="grid gap-3 p-2 pt-4 sm:grid-cols-2">
                <article className="rounded-2xl border border-border/70 bg-background/70 p-5 sm:col-span-2">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="eyebrow text-primary">Field intelligence</p>
                      <h2 className="mt-2 text-2xl font-bold tracking-[-0.03em]">Điều kiện canh tác ổn định</h2>
                    </div>
                    <CloudSun className="size-7 text-primary" />
                  </div>
                  <div className="mt-8 grid grid-cols-3 gap-3">
                    <Metric
                      label="Nhiệt độ"
                      value="28°C"
                    />
                    <Metric
                      label="Độ ẩm"
                      value="74%"
                    />
                    <Metric
                      label="Gió"
                      value="8 km/h"
                    />
                  </div>
                </article>

                <article className="rounded-2xl border border-border/70 bg-secondary/70 p-5">
                  <Bot className="size-5 text-primary" />
                  <p className="mt-7 text-sm font-bold">AI Agent</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">Sẵn sàng tổng hợp dữ liệu vận hành.</p>
                </article>

                <article className="rounded-2xl border border-primary/20 bg-primary p-5 text-primary-foreground">
                  <ShieldCheck className="size-5" />
                  <p className="mt-7 text-sm font-bold">Phiên bảo mật</p>
                  <p className="mt-1 text-xs leading-5 opacity-70">Token được refresh tự động.</p>
                </article>
              </div>
            </div>
          </aside>
        </div>

        <footer className="flex flex-col gap-2 border-t border-border/60 py-5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 AeroField Operations</p>
          <p>Weather · Crop intelligence · Market signals</p>
        </footer>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-lg font-bold sm:text-xl">{value}</p>
      <p className="mt-1 text-[0.65rem] text-muted-foreground">{label}</p>
    </div>
  );
}
