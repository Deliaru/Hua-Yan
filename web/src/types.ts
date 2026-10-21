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
export interface RunMode { kind: "replay" | "byok" | "local"; llm_model: string | null; jev_model: string | null; jev_fallback: boolean; probe?: Probe[] }
// 接入体检：对话、JSON 输出、工具调用三项，不支持的项影响哪一环
export interface Probe { item: string; ok: boolean; affects: string; detail: string }

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
export interface Turn { id: string; n: number; speaker: "customer" | "sales" | "assistant"; text: string; ts: string }
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

export interface SessionSummary { id: string; customer_id: string; sales_id: string | null; status: string; phenomenon: string | null; origin: "sales" | "customer" }

// v6 需求轨迹（门面 route_of）：四格状态 human 人真实处理过 / auto 由 Agent 或觉代办 / pending 已到、待处理 / none 未经过
export type RouteState = "human" | "auto" | "pending" | "none";
export interface RouteBasis { question_id: string; family: string; title: string; p_need: number | null; scored_by: string;
  status: string; action: string | null; by: string | null; note: string }
export interface Route {
  session_id: string; requirement_id: string | null; origin: "sales" | "customer"; path: string;
  roles: Record<"customer" | "sales" | "pm" | "rd", { state: RouteState; by: string[] }>;
  basis: RouteBasis[]; quote: string; n_human_steps: number; why: RouteWhy | null;
}
// 为什么直达研发：升级时查过的现有产品、按客户条件被排除的原因、Jev 判「都不合适」的概率
export interface RouteWhy {
  by: string; phenomenon: string; p_none: number; scored_by: string;
  candidates: { product_id: string; p: number }[];
  excluded: { product_id: string; mismatch: { slot: string; value: string; allowed: string[] }[] }[];
}
// v6.1 开工条件（E1 会话视角 / E2 需求单视角）
export interface Condition { slot: string; label: string; value: string | null; quote: string; in_opening: boolean; asked_by_jue: boolean }
export interface SessionReadiness { session_id: string; phenomenon: string | null; items: Condition[]; n_required: number; n_known: number; n_in_opening: number; n_asked_by_jue: number }
export interface Readiness {
  requirement_id: string; items: Condition[]; n_required: number; n_known: number; n_in_opening: number; n_asked_by_jue: number;
  n_open_ask_back: number; n_open_distortion: number; n_items_with_quote: number; n_items: number; ready: boolean;
}
// v6.1 E6：被拿掉的无效工作 / 保留的专业判断（事件日志计数）
export interface Workload { removed: { label: string; n: number; note: string }[]; kept: { label: string; n: number }[] }
export interface DemoRoute { id: string; title: string; customer: string; lines: string[]; hint: string }
// V6-5.5 演示讲解：讲解五段 happened / before / freed / money（$）/ fame（★），没有的不写
export interface StoryStep {
  chapter: string; title: string; do?: object[]; view: { page: string };
  happened: string; before?: string; freed?: string; money?: string; fame?: string;
  look?: { role: string; text: string };         // 讲完后引导点需求轨迹上的哪个角色格
}
// 这一步还没做的人工动作：谁来做、点哪个按钮、「演示自动填入」填什么、在哪个工作面（前提没出现时为空）
export interface StoryGuide { target: string; who: string | null; arg: string | null; view: { page: string; focus: string | null; who: string | null } | null }
export interface StoryState {
  chapters: { id: string; title: string; needs?: string[] }[]; steps: StoryStep[];
  done: number;                                  // 已执行到第几步（0 = 还没开始）
  view: { page: string; focus: string | null; who: string | null } | null;
  // 上一步：耗时、大模型调用次数与 token（回放时是录制下来的输出）、真实运行和剧本不同之处
  last: { seconds: number; calls: number; tokens: number; diverged: string | null } | null;
  begun: boolean;                                // 下一步已开始，等看的人在工作面上操作
  guide: StoryGuide | null;                      // begun 时还没做的第一个人工动作；做完为空，由讲解栏收尾
}
export interface LedgerItem { label: string; value: number; base?: number; note: string }

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
export interface MemoryEntry { id: string; principal: string; kind: "habit" | "fact" | "lesson"; text: string; why: string; refs: string[]; at: string }
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

// v7 契：研发自己授予的能力和本单待确认的结论。
export interface Capability {
  id: string; form: string; audience: number | string;
  payload: { product_id?: string; phenomenon?: string; slot?: string; text?: string; ku_id?: string;
    conditions?: Record<string, string[]>; required?: boolean; prior?: Record<string, number> };
  based_on: string[]; granted_by: string; approved_by: string | null;
  status: "proposed" | "active" | "suspended" | "revoked"; at: string;
}
export interface Claim {
  id: string; title: string; text: string; evidence: string[]; status: string;
}
