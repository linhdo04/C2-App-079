import { Users } from "lucide-react";
import type { UserMonthlyCostReport } from "@/types/cost-management";
import { formatDateTime, formatNumber, formatUsd } from "./cost-management-formatters";

export function UserMonthlyReportPanel({ report }: { report: UserMonthlyCostReport }) {
  return (
    <section className="reveal reveal-delay-2 mt-4 overflow-hidden rounded-[1.5rem] border border-border/80 bg-card/80 backdrop-blur-sm">
      <div className="border-b border-border/70 p-5 sm:p-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-primary">
              <Users className="size-5" />
              <h2 className="text-lg font-bold tracking-[-0.025em]">Cost report theo user/tháng</h2>
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Ước tính theo usage hiện tại: tháng hiện tại scale theo số ngày đã qua, custom range chuẩn hóa 30 ngày.
            </p>
          </div>
          <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2 lg:text-right">
            <p>
              Tổng projected:{" "}
              <span className="font-bold text-primary">{formatUsd(report.total_projected_monthly_cost_usd)}</span>
            </p>
            <p>
              TB/user:{" "}
              <span className="font-bold text-primary">
                {formatUsd(report.average_projected_monthly_cost_per_user_usd)}
              </span>
            </p>
          </div>
        </div>
      </div>
      <div className="grid gap-3 p-4 md:hidden">
        {report.users.map((user) => (
          <article
            key={user.user_id ?? "unknown"}
            className="rounded-2xl border border-border/70 bg-secondary/35 p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-bold">{user.user_name}</h3>
                <p className="mt-1 truncate text-xs text-muted-foreground">{user.user_email ?? "Không có email"}</p>
              </div>
              <span className="shrink-0 text-sm font-bold text-primary">
                {formatUsd(user.projected_monthly_cost_usd)}
              </span>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
              <div>
                <dt className="text-muted-foreground">Thực tế</dt>
                <dd className="font-bold">{formatUsd(user.actual_cost_usd)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Agent runs</dt>
                <dd className="font-bold">{formatNumber(user.agent_runs)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Token</dt>
                <dd className="font-bold">{formatNumber(user.total_tokens)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Lần cuối</dt>
                <dd className="font-bold">{formatDateTime(user.last_used_at)}</dd>
              </div>
            </dl>
          </article>
        ))}
        {report.users.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">Chưa có agent run nào trong kỳ này.</p>
        )}
      </div>
      <div
        className="hidden max-h-[34rem] overflow-auto md:block"
        role="region"
        aria-label="Bảng ước tính chi phí AI theo người dùng"
        tabIndex={0}
      >
        <table className="w-full min-w-[64rem] table-fixed caption-bottom text-left text-sm">
          <caption className="sr-only">Bảng cost report theo user/tháng</caption>
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b border-border/60 text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">
              <th className="h-10 w-56 px-6 text-left font-bold">User</th>
              <th className="h-10 px-2 text-right font-bold">Actual cost</th>
              <th className="h-10 px-2 text-right font-bold">Projected/tháng</th>
              <th className="h-10 px-2 text-right font-bold">Token</th>
              <th className="h-10 px-2 text-right font-bold">LLM calls</th>
              <th className="h-10 px-2 text-right font-bold">Agent runs</th>
              <th className="h-10 px-6 text-right font-bold">Last used</th>
            </tr>
          </thead>
          <tbody>
            {report.users.map((user) => (
              <tr
                key={user.user_id ?? "unknown"}
                className="border-b border-border/40 transition-colors last:border-0 hover:bg-secondary/35"
              >
                <td className="px-6 py-4">
                  <p className="truncate font-bold">{user.user_name}</p>
                  <p className="truncate text-xs text-muted-foreground">{user.user_email ?? "Không có email"}</p>
                </td>
                <td className="px-2 py-4 text-right font-mono text-xs font-bold">{formatUsd(user.actual_cost_usd)}</td>
                <td className="px-2 py-4 text-right font-bold text-primary">
                  {formatUsd(user.projected_monthly_cost_usd)}
                </td>
                <td className="px-2 py-4 text-right font-mono text-xs font-bold">{formatNumber(user.total_tokens)}</td>
                <td className="px-2 py-4 text-right font-mono text-xs font-bold">{formatNumber(user.llm_calls)}</td>
                <td className="px-2 py-4 text-right font-mono text-xs font-bold">{formatNumber(user.agent_runs)}</td>
                <td className="px-6 py-4 text-right font-mono text-xs font-bold whitespace-nowrap">
                  {formatDateTime(user.last_used_at)}
                </td>
              </tr>
            ))}
            {report.users.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-6 py-10 text-center text-sm text-muted-foreground"
                >
                  Chưa có agent run nào trong kỳ này.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
