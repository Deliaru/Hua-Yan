// 前端唯一的数据入口：src/huayan/ui/server.py 的 JSON 接口，每个接口对应一个门面方法。
// 身份由界面选择后作为 viewer / actor 传入，裁剪在门面里完成。
import type {
  AgentStep, Conversation, ContributionStat, Meta, PendingAction, Question, RequirementSummary, RequirementView,
  SessionDetail, SessionSummary,
} from "./types";

async function call<T>(path: string, body?: object): Promise<T> {
  const r = await fetch(`/api/${path}`, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error ?? `接口返回 ${r.status}`);
  return data;
}

const q = (params: Record<string, string | null | undefined>) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v != null) as [string, string][]).toString();

export const api = {
  meta: () => call<Meta>("meta"),
  reset: () => call<{ run_id: string }>("reset", {}),
  offlineMainline: () => call("offline-mainline", {}),
  sessions: () => call<SessionSummary[]>("sessions"),
  session: (id: string, viewer: string) => call<SessionDetail>(`session?${q({ id, viewer })}`),
  startSession: (customer_id: string, sales_id: string) => call<{ id: string }>("sessions", { customer_id, sales_id }),
  addTurn: (session_id: string, speaker: "customer" | "sales", text: string) => call("turn", { session_id, speaker, text }),
  questions: (role: string, viewer: string) => call<Question[]>(`questions?${q({ role, viewer })}`),
  requirements: (viewer: string) => call<RequirementSummary[]>(`requirements?${q({ viewer })}`),
  requirement: (id: string, viewer: string) => call<RequirementView>(`requirement?${q({ id, viewer })}`),
  ledger: () => call<Record<string, number>>("ledger"),
  contributions: (viewer: string) => call<ContributionStat[]>(`contributions?${q({ viewer })}`),
  // 角色助手（契约 ⑭）：只在助手运行（gateway_mock: false）时调用
  conversation: (actor: string, session_id: string | null) =>
    call<Conversation | null>(`agents/conversation?${q({ actor, session_id })}`),
  trace: (conversation_id: string) => call<AgentStep[]>(`agents/trace?${q({ conversation_id })}`),
  pending: (actor: string) => call<PendingAction[]>(`agents/pending?${q({ actor })}`),
  chat: (actor: string, text: string, session_id: string | null) => call<Conversation>("agents/chat", { actor, text, session_id }),
  approve: (action_id: string, by: string) => call<PendingAction>("agents/approve", { action_id, by }),
  reject: (action_id: string, by: string) => call<PendingAction>("agents/reject", { action_id, by }),
};
