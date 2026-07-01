"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useUpdateCostBudgetMutation } from "@/lib/api-hooks";
import type { CostSummary } from "@/types/cost-management";
import { formatUsd } from "./cost-management-formatters";

export function BudgetPanel({ summary }: { summary: CostSummary }) {
  const [monthlyBudget, setMonthlyBudget] = useState(String(summary.budget.monthly_budget_usd));
  const [threshold, setThreshold] = useState(String(summary.budget.alert_threshold_percent));
  const updateBudget = useUpdateCostBudgetMutation();
  const queryClient = useQueryClient();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const monthly_budget_usd = Number(monthlyBudget);
    const alert_threshold_percent = Number(threshold);
    if (Number.isNaN(monthly_budget_usd) || Number.isNaN(alert_threshold_percent)) {
      toast.error("Vui lòng nhập ngân sách và ngưỡng cảnh báo hợp lệ.");
      return;
    }
    try {
      await updateBudget.mutateAsync({ monthly_budget_usd, alert_threshold_percent });
      void queryClient.invalidateQueries({ queryKey: ["admin", "cost-management"] });
      toast.success("Đã cập nhật ngân sách chi phí AI.");
    } catch {
      toast.error("Không thể cập nhật ngân sách. Vui lòng thử lại.");
    }
  }

  return (
    <aside className="reveal reveal-delay-1 rounded-[1.5rem] border border-border/80 bg-card/80 p-5 shadow-[0_24px_80px_rgb(0_0_0/0.18)] backdrop-blur-sm sm:p-6">
      <h2 className="text-lg font-bold tracking-[-0.025em]">Ngân sách tháng</h2>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        V1 chỉ cảnh báo theo ngưỡng, chưa tự động chặn người dùng gọi trợ lý AI.
      </p>
      <div className="mt-5 overflow-hidden rounded-2xl border border-border/70 bg-secondary/45">
        <div
          className="h-3 bg-primary"
          style={{ width: `${Math.min(summary.budget.usage_percent, 100)}%` }}
          aria-hidden="true"
        />
        <div className="p-4">
          <p className="text-2xl font-bold tracking-[-0.04em]">{summary.budget.usage_percent}%</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Đã dùng {formatUsd(summary.budget.spent_usd)} trên {formatUsd(summary.budget.monthly_budget_usd)}
          </p>
        </div>
      </div>
      <form
        className="mt-5 grid gap-4"
        onSubmit={handleSubmit}
      >
        <label className="grid gap-2 text-sm font-bold">
          Ngân sách tháng (USD)
          <Input
            type="number"
            min="0"
            step="0.01"
            value={monthlyBudget}
            onChange={(event) => setMonthlyBudget(event.target.value)}
          />
        </label>
        <label className="grid gap-2 text-sm font-bold">
          Ngưỡng cảnh báo (%)
          <Input
            type="number"
            min="1"
            max="100"
            step="1"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
        </label>
        <Button
          type="submit"
          disabled={updateBudget.isPending}
        >
          {updateBudget.isPending ? <Spinner /> : <Save />}Lưu ngân sách
        </Button>
      </form>
    </aside>
  );
}
