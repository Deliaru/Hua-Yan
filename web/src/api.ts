// 前端唯一的数据入口：src/huayan/ui/server.py 的 JSON 接口，每个接口对应一个门面方法（WP-C 第 5 项）。
// 身份由界面选择后作为 viewer / by 传入，裁剪与可签条件都在门面里；门面拒绝时原样显示它返回的 error。
//
// 样例模式（地址带 ?fixture）：WP-U2 接真实接口前，工作面与觉视图的读操作取 web/src/fixtures/ 的接口样例，
// 写操作一律拒绝（不写门面替身）。身份、槽位名等仍取 /api/meta。接真实接口后删掉 FIXTURE 分支。
import type {
  Conversation, ContributionStat, JueTimeline, LeakHit, Meta, PendingAction, Question, ReqItem, RequirementSummary,
  RequirementView, SessionSummary, SessionView, SheetDraft,
} from "./types";

export const FIXTURE = new URLSearchParams(location.search).has("fixture");

// 种子与样例文本逐句带「（模拟）」前缀；全局已常驻「模拟数据」标识（铁律 7），显示时去掉逐句前缀。
const clean = <T,>(x: T): T => (typeof x === "string" ? x.replace(/（模拟[^）]{0,6}）/g, "")
  : Array.isArray(x) ? x.map(clean) : x && typeof x === "object"
    ? Object.fromEntries(Object.entries(x).map(([k, v]) => [k, clean(v)])) : x) as T;

async function call<T>(path: string, body?: object): Promise<T> {
  if (FIXTURE && body && path !== "reset") throw new Error("样例模式：接真实接口后可用");
  const r = await fetch(`/api/${path}`, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined).catch(() => { throw new Error("连不上化言服务，请确认后端已启动"); });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error ?? `接口返回 ${r.status}`);
  return clean(data);
}

const q = (params: Record<string, string | null | undefined>) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v != null) as [string, string][]).toString();

// ── 样例 ────────────────────────────────────────────────
interface SalesScene { label: string; session: SessionView; questions: Question[] }
interface RdScene { label: string; requirement: RequirementView; questions: Question[]; leak: LeakHit[] }
export const scene = { sales: "asking", rd: "reuse_pending" };
const salesFx = () => import("./fixtures/sales_workbench.json").then((m) => clean(m.default.scenarios) as unknown as Record<string, SalesScene>);
const rdFx = () => import("./fixtures/rd_workbench.json").then((m) => clean(m.default.scenarios) as unknown as Record<string, RdScene>);
export const fixtureScenes = async () => ({
  sales: Object.entries(await salesFx()).map(([k, v]) => [k, v.label] as const),
  rd: Object.entries(await rdFx()).map(([k, v]) => [k, v.label] as const),
});
const fx = {
  sessions: async (): Promise<SessionSummary[]> => {
    const s = (await salesFx())[scene.sales].session;
    return [{ id: s.session_id, customer_id: "", sales_id: s.viewer, status: s.status, phenomenon: null }];
  },
  session: async () => (await salesFx())[scene.sales].session,
  questions: async (viewer: string) => viewer.startsWith("rd:") ? (await rdFx())[scene.rd].questions
    : viewer.startsWith("sales:") ? (await salesFx())[scene.sales].questions : [],
  requirements: async (): Promise<RequirementSummary[]> => {
    const r = (await rdFx())[scene.rd].requirement.requirement;
    return [{ id: r.id, status: r.status, phenomenon: r.phenomenon }];
  },
  requirement: async () => (await rdFx())[scene.rd].requirement,
  leak: async () => (await rdFx())[scene.rd].leak,
  timeline: () => import("./fixtures/jue_timeline.json").then((m) => clean(m.default) as unknown as JueTimeline),
};

// ── 接口 ────────────────────────────────────────────────
export const api = {
  meta: () => call<Meta>("meta"),
  reset: () => call<{ run_id: string }>("reset", {}),

  // 读
  sessions: () => FIXTURE ? fx.sessions() : call<SessionSummary[]>("sessions"),
  session: (id: string, viewer: string) => FIXTURE ? fx.session()
    : call<SessionView | { view: SessionView }>(`session?${q({ id, viewer })}`).then((d) => ("view" in d ? d.view : d)),
  questions: (viewer: string) => FIXTURE ? fx.questions(viewer) : call<Question[]>(`questions?${q({ viewer })}`),
  requirements: (viewer: string) => FIXTURE ? fx.requirements() : call<RequirementSummary[]>(`requirements?${q({ viewer })}`),
  requirement: (id: string, viewer: string) => FIXTURE ? fx.requirement() : call<RequirementView>(`requirement?${q({ id, viewer })}`),
  leak: (id: string, viewer: string) => FIXTURE ? fx.leak() : call<LeakHit[]>(`leak?${q({ id, viewer })}`),
  timeline: (target: string, viewer: string) => FIXTURE ? fx.timeline() : call<JueTimeline>(`timeline?${q({ target_id: target, viewer })}`),
  ledger: () => call<Record<string, number>>("ledger"),
  contributions: (viewer: string) => call<ContributionStat[]>(`contributions?${q({ viewer })}`),
  report: <T,>(name: "distortion" | "jue_k" | "week") => call<T>(`report?${q({ name })}`),

  // 业务员工作面
  startSession: (customer_id: string, sales_id: string) => call<{ id: string }>("sessions", { customer_id, sales_id }),
  addTurn: (session_id: string, speaker: "customer" | "sales", text: string) => call("turn", { session_id, speaker, text }),
  recommend: (session_id: string) => call("recommend", { session_id }),
  escalateNote: (session_id: string, text: string, by: string) => call("escalate-note", { session_id, text, by }),
  escalate: (session_id: string, by: string) => call("escalate", { session_id, by }),
  requestDecrypt: (session_id: string, by: string) => call("decrypt/request", { session_id, by }),
  marketEval: (req_id: string, result: "pass" | "fail", note: string, by: string) => call("market-eval", { req_id, result, note, by }),

  // 研发工作面
  reuseNote: (req_id: string, text: string, by: string) => call("reuse-note", { req_id, text, by }),
  adoptReuse: (req_id: string, by: string) => call("reuse/adopt", { req_id, by }),
  declineReuse: (req_id: string, reason: string, by: string) => call("reuse/decline", { req_id, reason, by }),
  merge: (question_id: string, by: string) => call("merge", { question_id, by }),
  accept: (req_id: string, by: string) => call("accept", { req_id, by }),
  returnReq: (req_id: string, reason: string, by: string) => call("return", { req_id, reason, by }),
  editItem: (req_id: string, index: number, item: ReqItem, by: string) => call("req-item", { req_id, index, item, by }),
  confirm: (req_id: string, by: string) => call("confirm", { req_id, by }),
  contribute: (req_id: string, item_index: number, scene_phrase: string, chem_term: string, by: string) =>
    call("contribute", { req_id, item_index, scene_phrase, chem_term, by }),
  points: (req_id: string, text: string, sealed: string[], by: string) => call("points", { req_id, text, sealed, by }),
  sheet: (req_id: string, sheet: SheetDraft, by: string) => call("sheet", { req_id, sheet, by }),
  release: (req_id: string, by: string) => call("release", { req_id, by }),
  decideDecrypt: (question_id: string, approve: boolean, text: string, by: string) =>
    call("decrypt/decide", { question_id, approve, text, by }),
  trial: (req_id: string, result: "pass" | "fail", by: string) => call("trial", { req_id, result, by }),
  resolve: (question_id: string, action: "dismiss" | "update_sheet" | "freeze_access", by: string, note = "") =>
    call("resolve", { question_id, action, by, note }),

  // Agent 协作（契约 ⑭）
  conversation: (actor: string, session_id: string | null) => FIXTURE ? Promise.resolve(null)
    : call<Conversation | null>(`agents/conversation?${q({ actor, session_id })}`),
  chat: (actor: string, text: string, session_id: string | null, focus: string | null) =>
    call<Conversation>("agents/chat", { actor, text, session_id, focus }),
  pending: (actor: string) => FIXTURE ? Promise.resolve([]) : call<PendingAction[]>(`agents/pending?${q({ actor })}`),
  approve: (action_id: string, by: string) => call<PendingAction>("agents/approve", { action_id, by }),
  reject: (action_id: string, by: string) => call<PendingAction>("agents/reject", { action_id, by }),

  // 演示（WP-I2）：「下一句」只填进「客户说」输入框，由人发出；检查点只在服务以演示配置启动时可用
  nextLine: (session: string) => call<{ text: string | null }>(`demo/next?${q({ session })}`),
  checkpoints: () => call<string[]>("demo/checkpoints"),
  loadCheckpoint: (name: string) => call("demo/load", { name }),
};
