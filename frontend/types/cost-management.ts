export type CostBudget = {
  monthly_budget_usd: number;
  alert_threshold_percent: number;
  spent_usd: number;
  usage_percent: number;
  is_alerting: boolean;
};

export type DailyCost = {
  date: string;
  cost_usd: number;
  total_tokens: number;
  request_count: number;
};

export type CostSummary = {
  range: {
    start: string;
    end: string;
  };
  total_cost_usd: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  request_count: number;
  budget: CostBudget;
  pricing_configured: boolean;
  pricing_provider: string | null;
  pricing_model: string | null;
  pricing_source: string | null;
  daily: DailyCost[];
};

export type EvaluationMetric = {
  key: string;
  label: string;
  unit: "ms" | "percent" | "usd" | "usd_per_user_month" | string;
  direction: "lower_better" | "higher_better" | string;
  current_value: number | null;
  baseline_value: number | null;
  delta_value: number | null;
  delta_percent: number | null;
  sample_count: number;
};

export type EvaluationMetricsResponse = {
  range: {
    start: string;
    end: string;
  };
  baseline_range: {
    start: string;
    end: string;
  };
  metrics: EvaluationMetric[];
};

export type UserMonthlyCostReportItem = {
  user_id: number | null;
  user_name: string;
  user_email: string | null;
  actual_cost_usd: number;
  projected_monthly_cost_usd: number;
  total_tokens: number;
  llm_calls: number;
  agent_runs: number;
  avg_cost_per_run_usd: number | null;
  last_used_at: string;
};

export type UserMonthlyCostReport = {
  range: {
    start: string;
    end: string;
  };
  projection_basis: string;
  projection_multiplier: number;
  total_projected_monthly_cost_usd: number;
  average_projected_monthly_cost_per_user_usd: number;
  users: UserMonthlyCostReportItem[];
};

export type CostUsageEvent = {
  id: number;
  occurred_at: string;
  user_id: number | null;
  chat_session_id: number | null;
  run_id: string | null;
  operation: string;
  model_name: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
};

export type CostUsageResponse = {
  data: CostUsageEvent[];
  meta: {
    count: number;
    limit: number;
    offset: number;
  };
};

export type CostBudgetUpdateRequest = {
  monthly_budget_usd: number;
  alert_threshold_percent: number;
};
