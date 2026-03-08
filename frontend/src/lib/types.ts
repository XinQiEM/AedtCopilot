// ─── Chat ────────────────────────────────────────────────────────────────────

export type Role = "user" | "assistant" | "system";

export interface HistoryItem {
  role: Role;
  content: string;
}

/** Inline tool-call record attached to an assistant message. */
export interface ToolCall {
  tool: string;
  params: Record<string, unknown>;
  /** Populated when tool_result arrives. */
  ok?: boolean;
  message?: string;
}

/** A single renderable message in the chat panel. */
export interface ChatMessage {
  id: string;
  role: Role;
  /** Accumulated text content (built up token-by-token for assistant messages). */
  content: string;
  /** Intent label returned by the orchestrator (e.g. "geometry"). */
  intent?: string;
  /** RAG context snippet titles (for display badge). */
  ragHint?: string;
  /** Whether this message is still streaming. */
  streaming?: boolean;
  /** Timestamp (ms since epoch). */
  ts: number;
  /** Ordered list of tool invocations that occurred during this response. */
  toolCalls?: ToolCall[];
}

// ─── WebSocket events from backend ───────────────────────────────────────────

export type SimpleStreamEvent = {
  type: "intent" | "rag" | "token" | "done" | "error";
  content: string;
};

export type ToolCallStreamEvent = {
  type: "tool_call";
  tool: string;
  params: Record<string, unknown>;
};

export type ToolResultStreamEvent = {
  type: "tool_result";
  ok: boolean;
  message: string;
};

export type ChartStreamEvent = {
  type: "chart";
  chart_type: "s_params" | "far_field";
  plotly_json: SParamData | FarFieldData;
};

export type SimStatusStreamEvent = {
  type: "sim_status";
  pass: number;
  delta_s: number;
  max_passes: number;
  converged: boolean;
};

export type StreamEvent =
  | SimpleStreamEvent
  | ToolCallStreamEvent
  | ToolResultStreamEvent
  | ChartStreamEvent
  | SimStatusStreamEvent;

// ─── HFSS / backend health ────────────────────────────────────────────────────

export interface HealthStatus {
  hfss_connected: boolean;
  version?: string;
  llm_provider: string;
  llm_model: string;
  rag_ready: boolean;
  rag_chunks: number;
}

// ─── LLM config ──────────────────────────────────────────────────────────────

export interface LLMConfig {
  provider: "openai" | "azure_openai" | "anthropic" | "openai_compatible";
  api_key: string;
  model: string;
  base_url?: string | null;
  azure_endpoint?: string | null;
  azure_deployment?: string | null;
  azure_api_version?: string;
  temperature?: number;
  max_tokens?: number;
}

// ─── Chart / results ─────────────────────────────────────────────────────────

export interface SParamData {
  freq_ghz: number[];
  traces: Record<string, number[]>;
}

export interface FarFieldData {
  theta_deg: number[];
  gain_dbi: number[];
  phi_deg?: number;
}

export interface SimStatusData {
  pass: number;
  delta_s: number;
  max_passes: number;
  converged: boolean;
}
