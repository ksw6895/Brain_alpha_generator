export type RuntimeState = "idle" | "thinking" | "simulating" | "error";

export interface BrainEvent {
  event_type?: string;
  run_id?: string;
  idea_id?: string;
  stage?: string;
  message?: string;
  severity?: "info" | "warn" | "error" | string;
  created_at?: string;
  payload?: Record<string, unknown>;
}

export interface ControlActionSpec {
  action: string;
  description: string;
  template: Record<string, unknown>;
}

export interface ControlActionsResponse {
  actions: ControlActionSpec[];
}

export interface ControlJob {
  job_id: string;
  action: string;
  params: Record<string, unknown>;
  status: "queued" | "running" | "completed" | "failed" | string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  run_id?: string;
  idea_id?: string;
  return_code?: number | null;
  result?: Record<string, unknown> | null;
  command?: string[] | null;
  stdout_tail?: string;
  stderr_tail?: string;
}

export interface ReactorGauges {
  pressure?: number;
  prompt_tokens?: number;
  prompt_limit?: number;
  completion_tokens?: number;
  completion_limit?: number;
}

export interface ReactorFlags {
  reactor_state?: string;
  protection_mode?: boolean;
}

export interface ReactorPayload {
  run_id?: string;
  as_of?: string;
  gauges?: ReactorGauges;
  flags?: ReactorFlags;
}

export interface BacktestPoint {
  step: number;
  score: number;
  sharpe: number;
}

