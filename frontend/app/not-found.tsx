import { ArrowRight, Home, MapPinOff, Radar } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="app-shell relative grid min-h-screen overflow-hidden px-4 py-8 text-foreground sm:px-6">
      <div className="grid-surface pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute left-[-7rem] top-[-8rem] size-80 rounded-full bg-primary/10 blur-3xl" />
      <div className="pointer-events-none absolute bottom-[-8rem] right-[-6rem] size-80 rounded-full bg-[#59c7f3]/10 blur-3xl" />

      <section className="relative mx-auto grid w-full max-w-5xl place-items-center py-10">
        <div className="w-full max-w-2xl rounded-[2rem] border border-border/80 bg-card/80 p-5 text-center shadow-[0_32px_120px_rgb(0_0_0/0.35)] backdrop-blur-xl sm:p-10">
          <Link
            href="/"
            className="mx-auto inline-flex min-h-11 items-center gap-3 rounded-xl px-2"
            aria-label="AeroField - Trang chủ"
          >
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Radar className="size-5" />
            </span>
            <span className="text-left">
              <span className="block text-base font-bold tracking-[-0.03em]">AeroField</span>
              <span className="block text-[0.62rem] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                Vận hành cánh đồng
              </span>
            </span>
          </Link>

          <div className="mx-auto mt-10 grid size-16 place-items-center rounded-2xl border border-primary/30 bg-primary/10 text-primary sm:size-20">
            <MapPinOff className="size-7 sm:size-9" />
          </div>
          <p className="mt-6 text-sm font-bold uppercase tracking-[0.24em] text-primary">Lỗi 404</p>
          <h1 className="mt-3 text-3xl font-bold tracking-[-0.045em] sm:text-5xl">Không tìm thấy khu vực này</h1>
          <p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-muted-foreground sm:text-base">
            Đường dẫn có thể không tồn tại, đã được di chuyển hoặc tính năng này vẫn chưa được triển khai.
          </p>

          <div className="mt-8 grid gap-3 sm:flex sm:justify-center">
            <Button
              asChild
              size="lg"
            >
              <Link href="/">
                <Home />
                Về trang chủ
              </Link>
            </Button>
            <Button
              asChild
              size="lg"
              variant="outline"
            >
              <Link href="/admin">
                Trang quản trị
                <ArrowRight />
              </Link>
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}
