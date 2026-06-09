import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Autonomous Drones",
  description: "Trang chủ Autonomous Drones và lối vào AI Agent.",
};

export default function Home() {
  return (
    <main className="min-h-screen overflow-x-hidden bg-[#f7f4ef] text-[#1b1f1d]">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-between gap-10 px-4 py-5 sm:px-6 sm:py-8 lg:px-8">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm font-semibold uppercase tracking-[0.12em] text-[#456b58]">Autonomous Drones</p>
          <nav
            className="flex flex-wrap gap-2"
            aria-label="Điều hướng chính"
          >
            <Link
              className="min-h-11 rounded-xl border border-[#b9afa1] px-4 py-3 text-sm font-semibold text-[#273a31] transition hover:bg-[#f0ebe2]"
              href="/login"
            >
              Đăng nhập
            </Link>
            <Link
              className="min-h-11 rounded-xl bg-[#2f5d48] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#254a39]"
              href="/register"
            >
              Đăng ký
            </Link>
          </nav>
        </header>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-end">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.12em] text-[#456b58]">AI Agent Workspace</p>
            <h1 className="mt-4 max-w-4xl text-4xl font-semibold leading-tight text-[#1d2b24] sm:text-6xl">
              Điều phối dữ liệu nông nghiệp từ một workspace riêng.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-[#526158]">
              Trang chủ chỉ là điểm vào. Đăng nhập để mở workspace AI Agent, hỏi về thời tiết, thị trường và phân tích
              mùa vụ từ backend FastAPI.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                className="min-h-11 rounded-xl bg-[#2f5d48] px-5 py-3 text-center text-sm font-semibold text-white transition hover:bg-[#254a39]"
                href="/agent"
              >
                Mở AI Agent
              </Link>
              <Link
                className="min-h-11 rounded-xl border border-[#b9afa1] px-5 py-3 text-center text-sm font-semibold text-[#273a31] transition hover:bg-[#f0ebe2]"
                href="/login"
              >
                Đăng nhập trước
              </Link>
            </div>
          </div>

          <aside className="rounded-2xl border border-[#d8d2c7] bg-white p-4 shadow-sm sm:p-6">
            <h2 className="text-xl font-semibold text-[#1d2b24]">Routes</h2>
            <dl className="mt-4 grid gap-3 text-sm">
              <div className="rounded-xl bg-[#f7f4ef] p-3">
                <dt className="font-medium text-[#273a31]">/login</dt>
                <dd className="mt-1 text-[#526158]">Trang đăng nhập riêng.</dd>
              </div>
              <div className="rounded-xl bg-[#f7f4ef] p-3">
                <dt className="font-medium text-[#273a31]">/register</dt>
                <dd className="mt-1 text-[#526158]">Trang đăng ký riêng.</dd>
              </div>
              <div className="rounded-xl bg-[#f7f4ef] p-3">
                <dt className="font-medium text-[#273a31]">/agent</dt>
                <dd className="mt-1 text-[#526158]">Workspace hỏi AI Agent.</dd>
              </div>
            </dl>
          </aside>
        </div>

        <p className="text-sm leading-6 text-[#526158]">
          Token vẫn dùng localStorage key hiện tại và được refresh qua API backend khi workspace gọi endpoint protected.
        </p>
      </section>
    </main>
  );
}
