import type { CostUsageEvent } from "@/types/cost-management";
import { formatDateTime, formatNumber, formatUsd } from "./cost-management-formatters";

export function UsageLedger({ events }: { events: CostUsageEvent[] }) {
  return (
    <section className="reveal reveal-delay-2 mt-4 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 backdrop-blur-sm">
      <div className="border-b border-border/70 p-5 sm:p-6">
        <h2 className="text-lg font-bold tracking-[-0.025em]">Nhật ký usage gần nhất</h2>
        <p className="mt-1 text-xs text-muted-foreground">25 lần gọi LLM mới nhất trong tháng hiện tại.</p>
      </div>
      <div className="grid gap-3 p-4 sm:hidden">
        {events.map((event) => (
          <article
            key={event.id}
            className="rounded-2xl border border-border/70 bg-secondary/35 p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold">{event.operation}</h3>
                <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(event.occurred_at)}</p>
              </div>
              <span className="text-sm font-bold text-primary">{formatUsd(event.cost_usd)}</span>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {event.model_name} · {formatNumber(event.total_tokens)} token
            </p>
          </article>
        ))}
        {events.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">Chưa có usage nào được ghi nhận.</p>
        )}
      </div>
      <div
        className="hidden max-h-[32rem] overflow-auto sm:block"
        role="region"
        aria-label="Bảng usage LLM gần nhất"
        tabIndex={0}
      >
        <table className="w-full min-w-[52rem] table-fixed caption-bottom text-left text-sm">
          <caption className="sr-only">Bảng usage LLM và chi phí</caption>
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b border-border/60 text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">
              <th className="h-10 w-44 px-6 text-left font-bold">Thời gian</th>
              <th className="h-10 px-2 text-left font-bold">Operation</th>
              <th className="h-10 px-2 text-left font-bold">Model</th>
              <th className="h-10 px-2 text-right font-bold">Token</th>
              <th className="h-10 px-6 text-right font-bold">Chi phí</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr
                key={event.id}
                className="border-b border-border/40 transition-colors last:border-0 hover:bg-secondary/35"
              >
                <td className="px-6 py-4 font-mono text-xs font-bold whitespace-nowrap">
                  {formatDateTime(event.occurred_at)}
                </td>
                <td className="px-2 py-4 font-bold">{event.operation}</td>
                <td className="px-2 py-4 text-xs text-muted-foreground">{event.model_name}</td>
                <td className="px-2 py-4 text-right font-mono text-xs font-bold">{formatNumber(event.total_tokens)}</td>
                <td className="px-6 py-4 text-right font-bold text-primary">{formatUsd(event.cost_usd)}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-10 text-center text-sm text-muted-foreground"
                >
                  Chưa có usage nào được ghi nhận.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
