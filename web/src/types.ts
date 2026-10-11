// 与 src/huayan/contracts 中界面用到的模型一致（契约 ③ ⑥ ⑦ ⑫ ⑭，v5.3）。
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

// 本会话的运行方式（服务端会话层给出，不含密钥）：replay 录制回放；byok 试用者自带模型；local 本地部署按配置运行
export interface RunMode { kind: "replay" | "byok" | "local"; llm_model: string | null; jev_model: string | null; jev_fallback: boolean }

// 处理过程（服务端会话层，墙钟）：一次写操作里觉、模型、Jev、各角色 Agent 依次做了什么；别人的 Agent 不含工具名
export interface ProgressEvent {
  kind: "jue" | "llm_start" | "llm" | "s1_start" | "s1" | "dispatch" | "agent_start" | "step" | "agent_end";
  t: number;                        // 距本次处理开始的秒数
  caller?: string; model?: string; cached?: boolean; ok?: boolean; latency_ms?: number;   // 模型与 Jev；回放时 latency 为录制时耗时
  n?: number; mode?: string;        // 觉：本次判断的决策点数
  actor?: string; family?: string; conversation_id?: string; index?: number;            // Agent
  step?: number; tool?: string | null; blocked?: boolean; pending?: boolean;
}
export interface Activity { path: string; running: boolean; elapsed_ms: number; error: string | null; events: ProgressEvent[] }
export interface AgentRun { events: ProgressEvent[]; ms: number }

export interface Meta {
  status: RunStatus;
  mode: RunMode;
  actors: Actor[];
  slots: { id: string; label: string }[];
  phenomena: { id: string; label: string }[];
  products: { id: string; name: string }[];
}

// ③ 会话
export interface Turn { id: string; n: number; speaker: "customer" | "sales"; text: string; ts: string }
export interface SlotFill { slot: string; value: string | null; status: "filled" | "unknown"; confidence: number; quote: string; turn_id: string }
export interface AskHint { slot: string; label: string; ask_text: string; p_need: number; scored_by: string }
export interface AssistantReply { turn_id: string; text: string; ku_ids: string[]; blocked: boolean }
export interface CardSection { title: string; text: string; ku_id: string; level: number }
export interface RecommendationCard { product_id: string | null; version: string; sections: CardSection[]; note: string }

export interface ReuseView {
  requirement_id: string;
  product_id: string | null;
  product_name: string;
  usage: string;
  customer_note: string;
  basis: string[];
  status: "pending" | "adopted" | "declined" | "none";
}

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
  requirement: Requirement | null;
  reply_draft: string;
  escalate_note: string;
  reuse: ReuseView | null;
}

export interface SessionSummary { id: string; customer_id: string; sales_id: string; status: string; phenomenon: string | null }

// ⑥ 问题总线
export interface Evidence { summary: string; event_ids: string[]; quote: string }
export interface Resolution { action: string; by: string; note: string }
export interface Question {
  id: string;
  family: string;
  title: string;
  object_id: string;
  owner_role: Role;
  owner_id: string | null;
  signer_role: Role | null;
  signer_id: string | null;
  prepared_at: string | null;
  template_id: string | null;
  status: "open" | "resolved" | "dismissed";
  p_need: number | null;
  urgency: number | null;
  scored_by: string;
  discoverer: string;
  evidence: Evidence[];
  refs: Record<string, string>;
  bounty_points: number;
  created_at: string;
  resolved_at: string | null;
  resolution: Resolution | null;
}

// ⑦ 需求单
export interface ReqItem { text: string; slot: string | null; quote_refs: string[]; ku_refs: string[]; edited_by: string | null }
export interface ReuseProposal { product_id: string | null; ku_refs: string[]; customer_note: string; note: string; declined_reason: string }
export interface LeakHit { index: number; source: "sealed" | "l3_term" | "hypothesis" }
export interface PointsDraft { public: string; sealed: string[]; self_check: LeakHit[] }
export interface ContributionDraft { item_index: number; scene_phrase: string; chem_term: string; note: string }
export interface SheetDraft { sheet: string; usage: string }

export type ReqStatus = "draft" | "reused" | "merged" | "rd_accepted" | "rd_confirmed" | "released" | "rejected";
export interface Requirement {
  id: string;
  question_id: string;
  session_ids: string[];
  phenomenon: string;
  known_slots: Record<string, string>;
  assigned_rd: string;
  escalate_note: string;
  reuse: ReuseProposal | null;
  merged_into: string | null;
  merge_from: string[];
  merge_note: string;
  direction: string;
  product_lang: ReqItem[];
  chem_lang: ReqItem[];
  hypotheses: string[];
  status: ReqStatus;
  drafted_by: string;
  chem_drafted_by: string | null;
  rd_accepted_by: string | null;
  rd_confirmed_by: string | null;
  return_notes: string[];
  contribution_drafts: ContributionDraft[];
  points_draft: PointsDraft | null;
  public_points: string;
  sealed: string[];
  sheet: SheetDraft | null;
  product_id: string | null;
  created_at: string;
}
export interface RequirementSummary { id: string; status: ReqStatus; phenomenon: string; customer_ids: string[] }
export interface CitedKnowledge { ku_id: string; owner: string; level: number; title: string; text: string | null; n_cited: number }
export interface RequirementView { viewer: string; viewer_level: number; requirement: Requirement; quotes: Record<string, string>; cited: CitedKnowledge[] }
export interface ContributionStat { owner: string; ku_id: string; level: number; title: string; n_cited: number; points: number; used_by: string[] }

// ⑫ 觉视图
export interface TimelinePoint { at: string; family: string; object_id: string; p_need: number | null; threshold: number; scored_by: string; raised: boolean }
export interface TimelineNode {
  question_id: string;
  family: string;
  owner_id: string | null;
  signer_id: string | null;
  created_at: string;
  prepared_at: string | null;
  resolved_at: string | null;
  action: string | null;
  by: string | null;
}
export interface JueTimeline {
  target_id: string;
  viewer: string;
  points: TimelinePoint[];
  nodes: TimelineNode[];
  n_judgments: number;
  n_llm_calls: number;
  n_questions: number;
  n_signatures: number;
}

// ⑭ Agent
export interface AgentMessage { role: "principal" | "assistant" | "system"; text: string; at: string; pending_action_ids: string[]; target: string | null }
export interface Conversation { id: string; principal: string; role: Role; session_id: string | null; messages: AgentMessage[] }
export interface PendingAction { id: string; principal: string; tool: string; summary: string; status: string }

// 回放部署的台词（demo/mainline.yaml 的一个动作，原样转发）：{ start | customer | send | chat | sign | edit | trial: {...} }
export type ScriptAction = Record<string, Record<string, any>>;
export interface NextAction {
  index: number;
  total: number;
  sessions: Record<string, { session: string; customer: string; sales: string }>;
  action: ScriptAction | null;
  chapter: string | null;       // 这个动作所在的台词段标题，如「4 接单与 L3：……」
}
