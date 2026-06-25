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
