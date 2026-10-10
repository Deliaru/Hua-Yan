// 与 src/huayan/contracts 中界面用到的模型一致（契约 ③ ⑥ ⑦ ⑫ ⑭）。
export type Role = "customer" | "sales" | "pm" | "rd" | "supervisor";

export interface Actor { id: string; role: Role; name: string }

export interface RunStatus {
  run_id: string;
  replay: boolean;
  system1_impl: string;
  realtime_model: string;
  scheduled_model: string;
  extractor: string;
  gateway_mock: boolean;
  simulated_data: boolean;
  seeds_placeholder: boolean;
}

export interface Meta {
  status: RunStatus;
  actors: Actor[];
  mainline_available: boolean;
  slots: { id: string; label: string }[];
  phenomena: { id: string; label: string }[];
  products: { id: string; name: string }[];
}

export interface Turn { id: string; n: number; speaker: "customer" | "sales"; text: string; ts: string }
export interface SlotFill { slot: string; value: string | null; status: "filled" | "unknown"; confidence: number; quote: string; turn_id: string }
export interface AskHint { slot: string; label: string; ask_text: string; p_need: number; scored_by: string }
export interface AssistantReply { turn_id: string; text: string; ku_ids: string[]; blocked: boolean }
export interface CardSection { title: string; text: string; ku_id: string; level: number }
export interface RecommendationCard { product_id: string | null; version: string; sections: CardSection[]; note: string }

export interface SessionView {
  session_id: string;
  viewer: string;
  viewer_level: number;
  turns: Turn[];
  slots: SlotFill[];
  hints: AskHint[];
  replies: AssistantReply[];
  card: RecommendationCard | null;
  status: string;
  escalation_question_id: string | null;
}

export interface SessionSummary { id: string; customer_id: string; sales_id: string; status: string; phenomenon: string | null }
export interface SessionDetail { view: SessionView; phenomenon: string | null; phenomenon_quote: string; ask_back: Question[]; ask_back_history: Question[] }

export interface Evidence { summary: string; quote: string }
export interface Question {
  id: string;
  family: string;
  title: string;
  object_id: string;
  owner_role: Role;
  owner_id: string | null;
  status: string;
  p_need: number | null;
  urgency: number | null;
  scored_by: string;
  discoverer: string;
  evidence: Evidence[];
  refs: Record<string, string>;
  created_at: string;
}

export interface ReqItem { text: string; slot: string | null; quote_refs: string[]; ku_refs: string[] }
export interface Requirement {
  id: string;
  session_ids: string[];
  phenomenon: string;
  known_slots: Record<string, string>;
  direction: string;
  product_lang: ReqItem[];
  chem_lang: ReqItem[];
  hypotheses: string[];
  status: "draft" | "pm_confirmed" | "rd_confirmed" | "released" | "rejected";
  drafted_by: string;
  chem_drafted_by: string | null;
  pm_confirmed_by: string | null;
  rd_confirmed_by: string | null;
  public_points: string;
  sheet: { sheet: string; usage: string } | null;
  product_id: string | null;
}
export interface RequirementSummary { id: string; status: Requirement["status"]; phenomenon: string }
export interface CitedKnowledge { ku_id: string; owner: string; level: number; title: string; text: string | null; n_cited: number }
export interface RequirementView { requirement: Requirement; quotes: Record<string, string>; cited: CitedKnowledge[] }
export interface ContributionStat { owner: string; ku_id: string; level: number; title: string; n_cited: number; points: number; used_by: string[] }

export interface AgentMessage { role: "principal" | "assistant" | "system"; text: string; at: string; pending_action_ids: string[] }
export interface Conversation { id: string; principal: string; role: Role; session_id: string | null; messages: AgentMessage[] }
export interface AgentStep { step: number; tool: string | null; args: Record<string, unknown>; result_summary: string; blocked: string[] }
export interface PendingAction { id: string; tool: string; args: Record<string, unknown>; summary: string; status: string }
