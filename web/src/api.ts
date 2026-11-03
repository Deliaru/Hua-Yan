// 前端唯一的数据入口：src/huayan/ui/server.py 的 JSON 接口，每个接口对应一个门面方法（WP-C 第 5 项）。
// 身份由界面选择后作为 viewer / by 传入，裁剪与可签条件都在门面里；门面拒绝时原样显示它返回的 error。
import type {
  Capability, Claim, Conversation, ContributionStat, MemoryEntry, JueTimeline, LeakHit, Meta, PendingAction, Question, ReqItem, RequirementSummary,
  RequirementView, RunMode, SessionSummary, SessionView, SheetDraft, NextAction, Activity, AgentRun, SourcePreparation, SourcePreparationStatus, AuthorizedSourceReply,
  Route, CaseStory, OldFlow, TimeBar, PlayState, Readiness, SessionReadiness, Workload, DemoRoute, StoryState, LedgerItem, MonthDay, MonthProgress, FrozenActor, SourceTrialRecord, SourceImage, CeoData, PlaySettle, GrantScope, SourceSearch, SourceImageAnswer, AgentStep, PlanDraft, ClientMessage,
  LiveCase, JueRadar, DecisionCatalog, BusItem, QuestionLife,
} from "./types";

// 会话隔离：每个浏览器一个会话号，后端为它单独维护一套演示进度（多人同时试用互不干扰）；存 localStorage，刷新不丢进度
const SESSION = localStorage.getItem("huayan-session") ?? crypto.randomUUID();
localStorage.setItem("huayan-session", SESSION);

// 正在进行的写操作数：过程面板据此轮询处理过程（切换运行方式有自己的提示，不计入）
let inflight = 0;
const listeners = new Set<() => void>();
export const writes = {
  count: () => inflight,
  subscribe: (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; },
};
const track = (d: number) => { inflight += d; listeners.forEach((fn) => fn()); };

// 相对路径：页面可部署在子路径下（如 /huayan-demo/）
async function call<T>(path: string, body?: object): Promise<T> {
  const tracked = !!body && path !== "mode";
  if (tracked) track(1);
  try {
    return await request<T>(path, body);
  } finally {
    if (tracked) track(-1);
  }
}

async function request<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`api/${path}`, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Huayan-Session": SESSION },
    body: JSON.stringify(body),
  } : { headers: { "X-Huayan-Session": SESSION } }).catch(() => { throw new Error("连不上化言服务，请确认后端已启动"); });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error ?? `接口返回 ${r.status}`);
  // 草稿会用于编辑和签字，保留原文，确保界面与台词录制提交同一份内容。
  return data;
}

const q = (params: Record<string, string | null | undefined>) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v != null) as [string, string][]).toString();

// ── 接口 ────────────────────────────────────────────────
export const api = {
  meta: () => call<Meta>("meta"),
  reset: () => call<{ run_id: string }>("reset", {}),
  trialRole: (actor: string | null) => call<{ actor: string | null }>("trial/role", { actor }),
  // 切换本会话的运行方式（回放 / 自带密钥）；密钥只发给本服务，服务端只存在内存里
  setMode: (body: Record<string, string | boolean>) => call<RunMode>("mode", body),
  // 处理过程：不排会话锁，处理中也能读
  progress: (viewer: string) => call<Activity | null>(`progress?${q({ viewer })}`),
  agentFailures: (viewer: string) => call<Record<string, { at: string; error: string }>>(`agents/failures?${q({ viewer })}`),
  agentRetry: (question_id: string, by: string) => call<{ question_id: string }>("agents/retry", { question_id, by }),
  // V11.5 游戏模式：关卡进度与控制
  playState: () => call<PlayState>("play/state"),
  playSettle: () => request<PlaySettle>("play/settle"),                                          // V11.9 这一局的结算
  playControl: (p: { paused?: boolean; speed?: number }) => call<PlayState>("play/control", p),
  playRestart: (p: { real?: boolean; roadshow?: boolean } = {}) => call<PlayState>("play/restart", p),
  trialStamp: () => call<{ events: number; failures: number; sessions: number }>("trial/stamp"),
  agentProcess: (conversation_id: string, viewer: string) => call<Record<string, AgentRun>>(`agents/process?${q({ conversation_id, viewer })}`),

  // 读
  sessions: () => call<SessionSummary[]>("sessions"),
  session: (id: string, viewer: string) => call<SessionView | { view: SessionView }>(`session?${q({ id, viewer })}`).then((d) => ("view" in d ? d.view : d)),
  questions: (viewer: string) => call<Question[]>(`questions?${q({ viewer })}`),
  requirements: (viewer: string) => call<RequirementSummary[]>(`requirements?${q({ viewer })}`),
  frozen: (actor: string) => call<{ frozen: boolean }>(`frozen?${q({ actor })}`),
  frozenActors: (viewer: string) => call<FrozenActor[]>(`frozen_actors?${q({ viewer })}`),
  requirement: (id: string, viewer: string) => call<RequirementView>(`requirement?${q({ id, viewer })}`),
  sourcePreparation: (req_id: string, viewer: string) => call<SourcePreparation | null>(`source-preparation?${q({ req_id, viewer })}`),
  sourcePreparationStatus: (req_id: string, viewer: string) => call<SourcePreparationStatus | null>(`source-preparation/status?${q({ req_id, viewer })}`),
  sourceTrial: (doc_id: string, viewer: string) => call<SourceTrialRecord>(`sources/trial?${q({ doc_id, viewer })}`),
  sourceImage: (doc_id: string, page: number, viewer: string, span?: string) =>
    call<SourceImage>(`sources/image?${q({ doc_id, page: String(page), viewer, span })}`),
  sourceSearch: (query: string, viewer: string, req_id?: string) => call<SourceSearch>(`sources/search?${q({ query, viewer, req_id })}`),
  plan: (req_id: string, viewer: string) => call<PlanDraft | null>(`plan?${q({ req_id, viewer })}`),
  adoptPlan: (req_id: string, by: string) => call<PlanDraft>("plan/adopt", { req_id, by }),
  sourceAskImage: (doc_id: string, page: number, question: string, by: string) =>
    call<SourceImageAnswer>("sources/ask-image", { doc_id, page, question, by }),
  agentTrace: (conversation_id: string, viewer: string) => call<AgentStep[]>(`agents/trace?${q({ conversation_id, viewer })}`),
  authorizedSourceReplies: (session_id: string, viewer: string) => call<AuthorizedSourceReply[]>(`source-preparation/replies?${q({ session_id, viewer })}`),
  leak: (id: string, viewer: string) => call<LeakHit[]>(`leak?${q({ id, viewer })}`),
  timeline: (target: string, viewer: string) => call<JueTimeline>(`timeline?${q({ target_id: target, viewer })}`),
  ledger: () => call<Record<string, number>>("ledger"),
  contributions: (viewer: string) => call<ContributionStat[]>(`contributions?${q({ viewer })}`),
  report: <T,>(name: "distortion" | "distortion_300" | "jue_k" | "week" | "v6_routes") => call<T>(`report?${q({ name })}`),
  // 单卡对照按查看者裁剪（WP-E2）：L1 只拿到三组统计，L2/L3 有单卡明细
  // v8 Q9.5：模拟业务月（不属于浏览器会话；时间线只给主管）
  monthRuns: () => request<MonthProgress[]>("month/runs"),
  monthTimeline: (run: string, day: string, viewer: string) => request<MonthDay>(`month/timeline?${q({ run, day, viewer })}`),
  singleCard: <T,>(viewer: string) => call<T>(`report?${q({ name: "single_card", viewer })}`),

  // 业务员工作面
  startSession: (customer_id: string, sales_id?: string) => call<{ id: string }>("sessions", { customer_id, sales_id }),
  addTurn: (session_id: string, speaker: "customer" | "sales", text: string) => call("turn", { session_id, speaker, text }),
  recommend: (session_id: string) => call("recommend", { session_id }),
  escalateNote: (session_id: string, text: string, by: string) => call("escalate-note", { session_id, text, by }),
  escalate: (session_id: string, by: string) => call("escalate", { session_id, by }),
  requestDecrypt: (session_id: string, by: string) => call("decrypt/request", { session_id, by }),
  marketEval: (req_id: string, result: "pass" | "fail", note: string, by: string, missing_slots: string[] = []) =>
    call("market-eval", { req_id, result, note, by, missing_slots }),
  rework: (req_id: string, by: string) => call("rework", { req_id, by }),
  returnForConditions: (req_id: string, slots: string[], by: string) => call("return_for_conditions", { req_id, slots, by }),
  askBeforeAccept: (req_id: string, slots: string[], by: string) => call("ask_before_accept", { req_id, slots, by }),
  narrowCapability: (cap_id: string, conditions: Record<string, string[]>, by: string) => call("qi/narrow", { cap_id, conditions, by }),

  // 契的签字入口
  capabilities: (viewer: string) => call<Capability[]>(`capabilities?${q({ viewer })}`),
  claims: (req_id: string | null, viewer: string) => call<Claim[]>(`claims?${q({ req_id, viewer })}`),
  reviewClaims: (ku_ids: string[], by: string) => call<{
    claims: Claim[]; reviewed_evidence: Record<string, string[]>;
    fragments: Record<string, { doc_id: string; span: string; text: string; fingerprint: string }[]>;
    pending_evidence: Record<string, { capability_id: string; contributor: string }>;
  }>("qi/review", { ku_ids, by }),
  confirmClaims: (req_id: string | null, ku_ids: string[], by: string, reviewed_evidence?: Record<string, string[]>) =>
    call("qi/confirm", { req_id, ku_ids, by, reviewed_evidence }),
  reviseClaim: (ku_id: string, text: string, by: string) => call<Claim>("qi/revise", { ku_id, text, by }),
  grantCapability: (question_id: string, by: string, note = "", scope?: GrantScope) =>
    call("qi/grant", scope ? { question_id, by, note, scope } : { question_id, by, note }),
  revokeCapability: (cap_id: string, by: string) => call("qi/revoke", { cap_id, by }),
  requestShare: (ku_id: string, by: string) => call("qi/request-share", { ku_id, by }),
  withdrawClaim: (ku_id: string, by: string) => call("qi/withdraw", { ku_id, by }),

  // 研发工作面
  reuseNote: (req_id: string, text: string, by: string) => call("reuse-note", { req_id, text, by }),
  adoptReuse: (req_id: string, by: string) => call("reuse/adopt", { req_id, by }),
  declineReuse: (req_id: string, reason: string, by: string) => call("reuse/decline", { req_id, reason, by }),
  merge: (question_id: string, by: string, note = "") => call("merge", { question_id, by, note }),
  accept: (req_id: string, by: string) => call("accept", { req_id, by }),
  returnReq: (req_id: string, reason: string, by: string) => call("return", { req_id, reason, by }),
  editItem: (req_id: string, index: number, item: ReqItem, by: string) => call("req-item", { req_id, index, item, by }),
  confirm: (req_id: string, by: string) => call("confirm", { req_id, by }),
  contribute: (req_id: string, item_index: number, scene_phrase: string, chem_term: string, by: string) =>
    call("contribute", { req_id, item_index, scene_phrase, chem_term, by }),
  points: (req_id: string, text: string, sealed: string[], by: string) => call("points", { req_id, text, sealed, by }),
  sheet: (req_id: string, sheet: SheetDraft, by: string) => call("sheet", { req_id, sheet, by }),
  release: (req_id: string, by: string, name = "", category = "") => call("release", { req_id, by, name, category }),
  decideDecrypt: (question_id: string, approve: boolean, text: string, by: string) =>
    call("decrypt/decide", { question_id, approve, text, by }),
  trial: (req_id: string, result: "pass" | "fail", by: string, cause = "none", missing_slots: string[] = []) =>
    call("trial", { req_id, result, by, cause, missing_slots }),
  resolve: (question_id: string, action: "dismiss" | "update_sheet" | "freeze_access" | "take_over" | "sign", by: string, note = "", reviewed_evidence?: Record<string, string[]>) =>
    call("resolve", { question_id, action, by, note, reviewed_evidence }),
  unfreeze: (actor_id: string, by: string) => call("unfreeze", { actor_id, by }),

  // v6：路由、开工条件、岗位工作、产品经理协作、研发不立项
  route: (id: string, viewer: string) => call<Route>(`route?${q({ id, viewer })}`),
  caseStory: (id: string, viewer: string) => call<CaseStory>(`case-story?${q({ id, viewer })}`),   // V11.1 前情
  sheetRevision: (question_id: string, viewer: string) => call<{ text: string; by?: string; at?: string }>(`sheet-revision?${q({ question_id, viewer })}`),   // V12.7
  clientMessages: (viewer: string) => call<ClientMessage[]>(`client/messages?${q({ viewer })}`),   // V12.6 Client-View 主动消息
  oldFlow: (id: string, viewer: string) => call<OldFlow>(`old-flow?${q({ id, viewer })}`),         // V11.2 旧流程推算
  timeBar: (viewer: string) => call<TimeBar>(`time-bar?${q({ viewer })}`),                         // V11.4 我的时间构成
  live: (viewer: string) => call<{ cases: LiveCase[] }>(`live?${q({ viewer })}`),                     // V12.8 组织运行实况
  jueRadar: (viewer: string) => call<JueRadar>(`jue/radar?${q({ viewer })}`),                          // V12.8 觉雷达
  catalog: (viewer: string) => call<DecisionCatalog>(`jue/catalog?${q({ viewer })}`),                  // V12.8 决策目录墙
  bus: (viewer: string) => call<BusItem[]>(`bus?${q({ viewer })}`),                                    // V12.8 问题总线
  busLife: (question_id: string, viewer: string) => call<QuestionLife>(`bus/life?${q({ question_id, viewer })}`),
  ceo: (viewer: string) => call<CeoData>(`ceo?${q({ viewer })}`),                                     // V11.8 CEO 面（这一局）
  monthCeo: (run: string, viewer: string) => request<CeoData>(`month/ceo?${q({ run, viewer })}`),     // V11.8 CEO 面（模拟业务月）
  readiness: (id: string, viewer: string) => call<Readiness>(`readiness?${q({ id, viewer })}`),
  sessionReadiness: (id: string, viewer: string) => call<SessionReadiness>(`session-readiness?${q({ id, viewer })}`),
  workload: (viewer: string) => call<Workload>(`workload?${q({ viewer })}`),
  decline: (req_id: string, reason: string, by: string, product_id: string | null, limits = "",
            claim_ids: string[] = [], reviewed_evidence?: Record<string, string[]>) =>
    call("decline", { req_id, reason, by, product_id, limits, claim_ids, reviewed_evidence }),
  // V9.5：与本单相符、带研发限制原文的适用
  matchedLimits: (id: string, viewer: string) =>
    call<{ product_id: string; capability_id: string; granted_by: string; conditions: Record<string, string[]>; limits: string }[]>(
      `matched_limits?${q({ id, viewer })}`),
  extendScope: (question_id: string, note: string, by: string) => call("scope/extend", { question_id, note, by }),
  contributeL2: (req_id: string, item_index: number, scene_phrase: string, product_term: string, by: string) =>
    call("contribute_l2", { req_id, item_index, scene_phrase, product_term, by }),
  prepared: (question_id: string, by: string) => call("prepared", { question_id, by }),
  demoRoutes: () => call<DemoRoute[]>("demo/routes"),
  openRoute: (route: string, customer?: string) => call<{ session_id: string; customer_id: string }>("demo/open", { route, customer }),
  routeNext: (session: string) => call<{ text: string | null }>(`demo/route-next?${q({ session })}`),
  // V6-5.5 演示讲解：服务端按 demo/story.yaml 真的执行每一步；begin 只执行开场，其余由看的人在工作面上点，next 收尾（或替看的人做完）
  story: () => call<StoryState>("demo/story"),
  storyBegin: () => call<StoryState>("demo/story/begin", {}),
  storyNext: () => call<StoryState>("demo/story/next", {}),
  storyGoto: (index: number) => call<StoryState>("demo/story/goto", { index }),
  demoLedger: () => call<LedgerItem[]>("demo/ledger"),

  // Agent 协作（契约 ⑭）
  // v8：thread = 工作面打开的对象；按对象分段时取这一段对话
  conversation: (actor: string, session_id: string | null, thread: string | null = null) =>
    call<Conversation | null>(`agents/conversation?${q({ actor, session_id, thread })}`),
  memory: (actor: string) => call<MemoryEntry[]>(`agents/memory?${q({ actor })}`),
  forget: (id: string, by: string) => call<null>("agents/forget", { id, by }),
  chat: (actor: string, text: string, session_id: string | null, focus: string | null) =>
    call<Conversation>("agents/chat", { actor, text, session_id, focus }),
  pending: (actor: string) => call<PendingAction[]>(`agents/pending?${q({ actor })}`),
  approve: (action_id: string, by: string) => call<PendingAction>("agents/approve", { action_id, by }),
  reject: (action_id: string, by: string) => call<PendingAction>("agents/reject", { action_id, by }),

  // 演示（WP-I2）：「下一句」只填进「客户说」输入框，由人发出；检查点只在服务以演示配置启动时可用
  nextLine: (session: string) => call<{ text: string | null }>(`demo/next?${q({ session })}`),
  // 回放部署：台词里下一步人要做的事；现场模式返回 null
  nextAction: () => call<NextAction | null>("demo/next-action"),
  checkpoints: () => call<string[]>("demo/checkpoints"),
  loadCheckpoint: (name: string) => call("demo/load", { name }),
};
