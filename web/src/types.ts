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
  slots: { id: string; label: string; values: string[] }[];
  phenomena: { id: string; label: string }[];
  products: { id: string; name: string }[];
  trial?: { actor: string | null };
  play?: boolean;                    // V11.5 游戏模式（--play）
  jue?: { realtime: string; scheduled: string; cells: string[] };   // V9.6：实际加载的觉模型与学习格   // V9.1 试用实例：本浏览器选定的身份（服务端记住，读写都以它为主体）
}

// ③ 会话
export interface Turn { id: string; n: number; speaker: "customer" | "sales" | "assistant"; text: string; ts: string }
export interface SlotFill { slot: string; value: string | null; status: "filled" | "unknown"; confidence: number; quote: string; turn_id: string }
export interface TemperatureFill { celsius: [number, number] | null; status: "filled" | "unknown"; quote: string; turn_id: string }
export interface SourcePreparation {
  req_id: string; evidence: string[]; claim_ids: string[]; pending: string;
  known_slots: Record<string, string>; temperatures: Record<string, TemperatureFill | null>;
  by: string; at: string;
  compilation?: { ir_id: string; at: string; report: { admitted: { ku_id: string }[]; unaligned: string[]; dropped: string[] } };
}
export interface SourcePreparationStatus {
  claims: { id: string; status: "candidate" | "active" | "withdrawn"; confirmed_by: string | null }[];
  capabilities: Pick<Capability, "id" | "form" | "audience" | "status" | "granted_by" | "approved_by">[];
}
export interface AuthorizedSourceReply { ref: string; text: string; audience: number }

// 读取侧试样记录的显示字段，与正式业务Trial分开。
export interface SourceCitation { fragment: string; span: string; pages: number[]; quote: string; cell: [number, number] | null }
export interface SourceImage {
  doc_id: string; span: string | null; page: number; bbox: [number, number, number, number] | null;
  kind: "page" | "region"; level: number; source: "public" | "internal" | "external";
  width: number; height: number; fingerprint: string; image_url: string;
}
export interface SourceTrialText { text: string; evidence: SourceCitation[] }
export interface SourceReading {
  span: string; cell: [number, number] | null; object: string; group: "A" | "B" | null;
  stage: string | null; value: string; unit: string; conditions: string[]; quote: string; status: "native" | "needs_reading";
}
export interface SourceTrialRecord {
  source_id: string; level: number; source: "public" | "internal" | "external"; status: "draft"; extracted_by: "rule";
  metadata: SourceTrialText[]; purpose: SourceTrialText[]; common_conditions: SourceTrialText[];
  groups: {
    group: "A" | "B";
    formula: { name: string; value: string; unit: string | null; basis: string | null; evidence: SourceCitation[] }[];
    formula_notes: SourceTrialText[]; curve_labels: SourceReading[]; curve_evidence: SourceCitation[]; operations: SourceTrialText[];
  }[];
  time: { a: SourceReading | null; b: SourceReading | null; reported_saving: SourceReading | null;
    calculated_saving: string | null; formula: string | null; unit: string; basis: string; evidence: SourceCitation[] };
  quality: SourceTrialText[]; cost: SourceTrialText[]; follow_up: SourceTrialText[]; reported_results: SourceTrialText[];
  pending: string[]; review_notes: SourceTrialText[];
}
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
  temperature: TemperatureFill | null;
  hints: AskHint[];
  replies: AssistantReply[];
  card: RecommendationCard | null;
  status: string;
  escalation_question_id: string | null;
  requirement: Requirement | null;
  reply_draft: string;
  escalate_note: string;
  reuse: ReuseView | null;
  asks: { question_id: string; slot: string; label: string; ask_text: string }[];
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
// V11.1 一件事的前情（门面 case_story）：每行的主体与角色；waiting 是这件事上还开着的决策
export type StorySubject = "human" | "agent" | "jue" | "jev" | "qi" | "system";
export interface StoryLine { ts: string; kind: string; subject: StorySubject; role: Role | null; who: string; text: string }
export interface StoryWaiting { question_id: string; family: string; decision: string; owner_id: string | null; signer_id: string | null; prepared: boolean }
export interface CaseStory { session_id: string; requirement_id: string | null; story: StoryLine[]; waiting: StoryWaiting[] }
// V11.2 / V11.4 旧流程推算（eval/old_flow.py）：now_times 是这次实际还发生的次数（交叉工位按前情数，本职工位照常保留）
export interface OldFlowStation { station: string; role: "sales" | "pm" | "rd"; times: number; minutes: number; now_times?: number; now_minutes?: number }
export interface OldFlow {
  path: string; cases: number; source: string; assumed: string[]; params_source: string;
  old: { stations: OldFlowStation[]; roles: string[]; handoffs: number; lost: string[] | null; backs: number; reworks: number;
         by_role_minutes: Record<string, number>; work_hours: number; wait_hours: number };
  now: { roles: string[]; human_steps: number };
}
// V11.4 个人时间构成：现状比例（假设）按这批事的交叉工位缩短
export interface TimeSegment {
  whose: string; before: number; after: number; worse: boolean; old_minutes: number; saved_minutes: number;
  steps: { station: string; times: number; now_times: number; minutes_each: number }[];
}
export interface TimeBar { role: string; cases: number; own_before: number; own_after: number; segments: TimeSegment[]; source: string; split_source: string }
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
    conditions?: Record<string, string[]>; required?: boolean; prior?: Record<string, number>;
    temperature_c?: [number, number]; limits?: string };
  based_on: string[]; granted_by: string; approved_by: string | null;
  status: "proposed" | "active" | "suspended" | "revoked"; at: string;
}
export interface Claim {
  id: string; title: string; text: string; evidence: string[]; status: string; owner: string;
}

// v8 Q9.5：模拟业务月。运行进度来自 runs/<运行>/progress.json；时间线是门面 timeline(day, by)，只给主管。
export interface MonthProgress {
  run_id?: string; group: "jue" | "sm"; day: number; days: number; at: string; tick: number; ticks: number;
  elapsed_s: number; eta_s: number; calls: number; failed: number; inflight_peak: number;
  input_tokens: number; output_tokens: number; open_questions: number; requirements: Record<string, number>;
  rejected: number; jue: string; updated: string;
}
export interface MonthItem {
  id: string; lane: string; at: string; kind: string; actor: string; family: string | null;
  session_id: string | null; text: string;
}
export interface MonthSession {
  id: string; customer: string; sales: string | null; status: string; phenomenon: string | null; start: string; end: string;
  turns: { at: string; speaker: string; text: string }[];
}
export interface MonthDay {
  day: string; days: string[]; lanes: { id: string; label: string }[]; items: MonthItem[]; sessions: MonthSession[];
  board: { requirements: Record<string, string[]>; capabilities: Record<string, number>; jue: { model: string; version: string | null } };
  kpi: Record<string, number>; summary: string; highlights: MonthItem[];
  cases: MonthCase[]; discoveries: MonthStep[]; qi: MonthQi;
}
// 案件故事里的一步：一句话（turn）、觉的一个问题（decision：提出 → 准备 → 签字）、或一件事实（推荐、建单、试样…）
export interface MonthStep {
  at: string; kind: string; text?: string; speaker?: string; by?: string; tone?: "ok" | "fail"; owner?: string | null;
  family?: string; label?: string; discovery?: boolean; scored_by?: string; p?: number | null; object?: string;
  prepared_at?: string | null; signer?: string | null; status?: string; done_at?: string; action?: string; note?: string;
  ask?: string; case?: string | null; title?: string;
}
export interface MonthCase {
  id: string; key: string; customer: string; customer_name: string; sales: string | null; phenomenon: string;
  opening: string; started_at: string; requirements: string[]; story: MonthStep[];
  outcome: { state: "done" | "open" | "fail"; text: string; since?: string };
}
export interface MonthQi {
  used_by_owner: Record<string, number>; used_total: number; denied: number; outbound: number; leaked: number;
  grants: { at: string; kind: string; by: string; capability: string | null; form: string | null; audience: number | null; uses_since: number }[];
  points: Record<string, number>;
}

// v8 Q9.8：主管工作台的已冻结名单
export interface FrozenActor {
  actor_id: string; name: string; frozen_at: string; frozen_by: string;
  evidence: string[]; n_denied: number; customers: string[];
}

// V11.10 授予适用能力的范围：默认是试过的条件，研发授予时可以放宽（条件取值、温度、限制原文）
export interface GrantScope { conditions: Record<string, string[]>; temperature_c: [number, number] | null; limits: string }
// V11.5 游戏模式：导演的进度（sim/director.py 的 view）
export interface PlayLevel { id: number; title: string; brief: string; to: string; decide: string; mechanism: string; point: string; ready: boolean }
export interface PlayState {
  levels: PlayLevel[]; level: number; round: number; speed: number;
  real: boolean; real_ready: boolean;   // 这一局第 4、5、6、9 关用真实报告；服务配了真实报告版（play_real_report）才能换
  paused: boolean; passed: boolean; done: number[];
  cases: string[]; acted: { ts: string; actor: string; path: string }[]; error: string | null; now: string;
  lines: { customer: string; session_id: string; text: string }[];   // 客户由人扮时，接下来可以说的台词
  notes: { who: string; text: string }[];   // 有人在玩的岗位要用到的外部世界信息（试样结果）
}
// V11.8 CEO 面：化言线逐件路径（门面 pipeline）+ 同一件事的旧流程推算（given 按参数文件、safe 按最保守参数）
export interface CeoStation { station: string; enter: string; leave: string; by: string[]; loop: boolean }
export interface CeoEstimate extends OldFlow { first_reply_hours: number }
export interface CeoCase {
  session_id: string; stations: CeoStation[]; arrived: string; answered: string | null; used: string[];
  path: string; quote: string; reused: boolean; given: CeoEstimate; safe: CeoEstimate;
}
// 参数文件 config/old_flow.default.yaml 的全部字段（规模、单价是数，另有工位分钟数、时间构成与仍用假设值的参数名）
export type CeoParams = { minutes: Record<string, number>; time_split: Record<string, Record<string, number>>; assumed: string[]; [k: string]: any };
export interface CeoData {
  cases: CeoCase[]; caps: { id: string; product: string; phenomenon: string; granted_by: string; new: boolean }[];   // granted_by 是签字人姓名
  params: Record<"given" | "safe", CeoParams>; names: Record<string, string>; bars: Record<"given" | "safe", Record<"sales" | "pm" | "rd", TimeBar>>;
}
// V11.9 游戏结算：九关各送来的事（会话号）与这一局的账本（各件只给路径与推算，不给原话与经手人）
export interface PlaySettle {
  params: CeoData["params"]; bars: CeoData["bars"];
  cases: (Pick<CeoCase, "session_id" | "path" | "reused" | "arrived" | "answered" | "given" | "safe"> & { rerouted: boolean })[];
  levels: { id: number; title: string; point: string; passed: boolean; cases: string[] }[];
}
