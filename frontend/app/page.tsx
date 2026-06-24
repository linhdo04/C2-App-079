import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  Bot,
  CloudSun,
  Database,
  Droplets,
  MessageSquareText,
  Radar,
  ShieldCheck,
  Thermometer,
  type LucideIcon,
} from "lucide-react";
import { GuestLoginButton, Nav } from "@/components/pages/home";

export const metadata: Metadata = {
  title: "AeroField",
  description: "Trung tâm điều phối dữ liệu cảm biến và trợ lý AI cho vận hành nông nghiệp chính xác.",
};

const operatorSteps = [
  {
    icon: Thermometer,
    label: "Dữ liệu cảm biến hôm nay",
    title: "Theo dõi nhiệt độ, độ ẩm và trạng thái cảm biến theo thời gian thực.",
  },
  {
    icon: MessageSquareText,
    label: "Hỏi trợ lý AI",
    title: "Đặt câu hỏi bằng tiếng Việt để tìm cực trị, khoảng thời gian hoặc điểm bất thường.",
  },
  {
    icon: Database,
    label: "Bảng điều khiển vận hành",
    title: "Tổng hợp dữ liệu nhiệm vụ thành biểu đồ, bảng đọc và bối cảnh ra quyết định.",
  },
];

const previewSignals = [
  { label: "Nhiệt độ", state: "Cực trị hôm nay", icon: Thermometer },
  { label: "Độ ẩm", state: "Mẫu mới nhất", icon: Droplets },
  { label: "Nhiệm vụ", state: "Theo cảm biến", icon: CloudSun },
];

export default function Home() {
  return (
    <main className="app-shell relative min-h-screen overflow-hidden text-foreground">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute -top-32 right-[-18rem] h-[34rem] w-[34rem] rounded-full bg-primary/10 blur-3xl" />
      <div className="pointer-events-none absolute bottom-10 left-[-16rem] h-[28rem] w-[28rem] rounded-full bg-success/10 blur-3xl" />

      <section className="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 sm:px-6 lg:px-8">
        <header className="flex min-h-20 items-center justify-between gap-3 border-b border-border/60">
          <Link
            href="/"
            className="flex min-w-0 items-center gap-3"
            aria-label="AeroField - Trang chủ"
          >
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Radar className="size-5" />
            </span>
            <span className="truncate text-lg font-bold tracking-[-0.03em]">AeroField</span>
          </Link>
          <Nav />
        </header>

        <div className="grid flex-1 items-center gap-10 py-10 sm:py-14 lg:grid-cols-[1fr_0.9fr] lg:gap-14 lg:py-16">
          <section className="reveal">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-2 text-primary">
              <span className="size-1.5 rounded-full bg-primary shadow-[0_0_12px_var(--primary)]" />
              <span className="eyebrow">Trung tâm điều phối cho người vận hành</span>
            </div>

            <h1 className="text-balance max-w-4xl text-4xl font-bold leading-[1.02] tracking-[-0.05em] sm:text-6xl lg:text-7xl">
              Một nơi để theo dõi dữ liệu cảm biến.
              <span className="block text-primary">Một trợ lý AI để hỏi ngay khi cần.</span>
            </h1>

            <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
              AeroField giúp người vận hành đăng nhập, mở bảng điều khiển và xử lý câu hỏi vận hành từ dữ liệu cảm biến
              trong ngày — không cần tự dò bảng số liệu hay đoán khoảng thời gian.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
              <GuestLoginButton />
              <p className="text-xs leading-5 text-muted-foreground sm:max-w-xs">
                Tài khoản được cấp bởi quản trị viên. Phiên đăng nhập được bảo vệ và refresh tự động.
              </p>
            </div>

            <div
              className="mt-10 grid gap-3 sm:grid-cols-3"
              aria-label="Khả năng chính của AeroField"
            >
              {operatorSteps.map((step) => (
                <CapabilityCard
                  key={step.label}
                  {...step}
                />
              ))}
            </div>
          </section>

          <aside className="reveal reveal-delay-2 relative mx-auto w-full max-w-xl lg:mr-0">
            <div className="absolute -inset-6 rounded-full bg-primary/5 blur-3xl" />
            <div className="relative overflow-hidden rounded-[1.75rem] border border-border bg-card/85 p-3 shadow-[0_30px_100px_rgb(0_0_0/0.35)] backdrop-blur-xl">
              <div className="flex items-center justify-between gap-3 border-b border-border/70 px-3 py-3">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="size-2 shrink-0 rounded-full bg-success shadow-[0_0_14px_rgb(116_217_161/0.75)]" />
                  <span className="eyebrow truncate text-muted-foreground">Luồng vận hành</span>
                </div>
                <span className="rounded-full border border-border/70 px-2 py-1 font-mono text-[0.65rem] text-muted-foreground">
                  MINH HỌA
                </span>
              </div>

              <div className="grid gap-3 p-2 pt-4">
                <article className="rounded-2xl border border-border/70 bg-background/75 p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="eyebrow text-primary">Luồng mẫu</p>
                      <h2 className="mt-2 text-2xl font-bold tracking-[-0.03em]">Từ dữ liệu thô đến câu trả lời</h2>
                    </div>
                    <Bot className="size-7 text-primary" />
                  </div>

                  <div className="mt-6 space-y-3">
                    <PreviewMessage tone="user">Nhiệt độ cao nhất trong 2 giờ vừa rồi là bao nhiêu?</PreviewMessage>
                    <PreviewMessage tone="agent">
                      Trợ lý AI kiểm tra dữ liệu cảm biến theo khoảng thời gian, trả về giá trị, thời điểm và cảm biến
                      liên quan.
                    </PreviewMessage>
                  </div>
                </article>

                <div className="grid gap-3 sm:grid-cols-3">
                  {previewSignals.map((signal) => (
                    <SignalCard
                      key={signal.label}
                      {...signal}
                    />
                  ))}
                </div>

                <article className="grid gap-3 rounded-2xl border border-primary/20 bg-primary p-5 text-primary-foreground sm:grid-cols-[auto_1fr] sm:items-center">
                  <span className="grid size-11 place-items-center rounded-xl bg-primary-foreground/15">
                    <ShieldCheck className="size-5" />
                  </span>
                  <div>
                    <p className="text-sm font-bold">Thiết kế cho user đã có quyền truy cập</p>
                    <p className="mt-1 text-xs leading-5 opacity-75">
                      Trang chủ dẫn thẳng đến đăng nhập hoặc bảng điều khiển, không gây nhiễu bằng luồng đăng ký đang
                      tạm tắt.
                    </p>
                  </div>
                </article>
              </div>
            </div>
          </aside>
        </div>

        <footer className="flex flex-col gap-2 border-t border-border/60 py-5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 Vận hành AeroField</p>
          <p>Dữ liệu cảm biến · Trợ lý AI · Bảng điều khiển nhiệm vụ</p>
        </footer>
      </section>
    </main>
  );
}

function CapabilityCard({ icon: Icon, label, title }: { icon: LucideIcon; label: string; title: string }) {
  return (
    <article className="rounded-2xl border border-border/70 bg-card/55 p-4 backdrop-blur-sm">
      <Icon className="size-5 text-primary" />
      <h2 className="mt-4 text-sm font-bold tracking-[-0.02em]">{label}</h2>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{title}</p>
    </article>
  );
}

function PreviewMessage({ children, tone }: { children: ReactNode; tone: "agent" | "user" }) {
  const isUser = tone === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <p
        className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-border/70 bg-secondary/70 text-secondary-foreground"
        }`}
      >
        {children}
      </p>
    </div>
  );
}

function SignalCard({ icon: Icon, label, state }: { icon: LucideIcon; label: string; state: string }) {
  return (
    <article className="rounded-2xl border border-border/70 bg-secondary/65 p-4">
      <Icon className="size-5 text-primary" />
      <p className="mt-4 text-sm font-bold">{label}</p>
      <p className="mt-1 text-[0.68rem] leading-5 text-muted-foreground">{state}</p>
    </article>
  );
}
