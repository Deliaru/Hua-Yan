import { createContext, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { Meta, Question, Role } from "./types";

export interface Ctx {
  meta: Meta;
  me: string;                       // 当前身份（演示无登录，工具栏切换）
  role: Role;
  agentOnline: boolean;             // Agent 是否运行（gateway_mock 为 false）
  version: number;                  // 每次写操作后 +1，各处据此重新读取
  refresh: () => void;
  fail: (e: unknown) => void;
  switchTo: (actor: string) => void;  // 演示导览一键切换到该做下一步的人
  side: HTMLElement | null;         // 侧栏下半部分：各页面把自己的 source list 放进来
}

export const AppCtx = createContext<Ctx>(null!);
export const useApp = () => useContext(AppCtx);

// 页面把自己的侧栏内容（客户会话、收件箱、需求单）放进外壳侧栏
export function Side({ children }: { children: React.ReactNode }) {
  const { side } = useApp();
  return side ? createPortal(children, side) : null;
}

// ── 显示用标签：界面上不出现内部 id 与枚举 ─────────────────
export const FAMILY: Record<string, string> = {
  ask_slot: "追问", escalate_need: "推荐还是升级", reuse_product: "现成产品审定", opportunity: "机会汇聚",
  accept_requirement: "接单", ask_back: "回问", distortion: "转译失真", confirm_translation: "确认转译",
  contribution: "沉淀", market_eval: "客户评价", seal_points: "封存 / 放出", seal_leak: "说明书泄密",
  release: "发布审定", knowledge_conflict: "知识冲突", leak_risk: "拼凑风险", decrypt_request: "解密申请",
};
// 准备中的问题只显示主人在做什么
export const PREPARING: Record<string, string> = {
  reuse_product: "正在查现成产品", opportunity: "正在读各单原话、判断是不是同一件事",
  accept_requirement: "正在起草产品需求（L2）", confirm_translation: "正在起草化学语言（L3）",
  contribution: "正在提炼可沉淀的知识", seal_points: "正在起草封存 / 放出两栏", release: "正在包装说明书",
  seal_leak: "正在改写说明书", escalate_need: "正在起草升级说明", decrypt_request: "正在准备解密说明",
};
export const REQ_STATUS: Record<string, string> = {
  draft: "产品经理 Agent 起草中", reused: "已复用现成产品", merged: "已并入另一张单", rd_accepted: "研发已接单",
  rd_confirmed: "研发已确认转译", released: "已发布", rejected: "已失效",
};
export const SESSION_STATUS: Record<string, string> = { open: "进行中", recommended: "已推荐", escalated: "已转产品经理 Agent" };
export const ACTION: Record<string, string> = {
  sign: "已签字", accept: "已接单", return: "已退回", answered: "已回答", update_sheet: "已更新适用表",
  freeze_access: "已冻结权限", approve_decrypt: "已批准解密", reject_decrypt: "已拒绝解密", dismiss: "现在不需要",
};
const SCORER: Record<string, string> = {
  rule: "规则", onejev: "OneJev", jue_k: "Jue-K", mock: "桩", llm_fallback: "大模型降级", human: "人工",
};
const VERSION: Record<string, string> = {
  product: "产品版", product_usage: "产品与用法", full_mechanism: "含机理（已解密）", internal: "内部版",
};
const LEAK_SOURCE: Record<string, string> = { sealed: "命中封存项", l3_term: "含研发术语", hypothesis: "命中研发假设" };

export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const isModel = (scoredBy: string) => scoredBy === "jue_k" || scoredBy === "onejev";
export const hhmm = (iso: string) => iso.slice(11, 16);

export function useLabels() {
  const { meta } = useApp();
  const actors = Object.fromEntries(meta.actors.map((a) => [a.id, a.name.replace("（模拟）", "")]));
  const slot = (id: string) => meta.slots.find((s) => s.id === id)?.label ?? id;
  const phen = (id: string | null | undefined) => meta.phenomena.find((p) => p.id === id)?.label ?? "未识别现象";
  const name = (id: string | null | undefined) => (id ? actors[id] ?? "（未知身份）" : "—");
  return {
    name,
    slot,
    phen,
    family: (f: string) => FAMILY[f] ?? f,
    product: (id: string | null) => meta.products.find((p) => p.id === id)?.name.replace("（模拟）", "") ?? id ?? "—",
    scorer: (s: string) => SCORER[s] ?? s,
    version: (v: string) => VERSION[v] ?? v,
    leak: (s: string) => LEAK_SOURCE[s] ?? s,
    // 模板标题、证据里的对象 id 换成人话（铁律：界面不暴露内部 id）
    scrub: (text: string) => text
      .replace(/(需求单\s*)?(?:requirement:)?req:[\w-]+/g, "需求单")
      .replace(/\s*(?:ku:)?(?:case|tr|translation):[\w:-]+/g, "")
      .replace(/slot:(?:sess:)?[\w-]+\/(\w+)/g, (_, s) => slot(s))
      .replace(/(?:session:)?sess:[\w-]+/g, "会话")
      .replace(/theme:(\w+)/g, (_, p) => phen(p))
      .replace(/[（(](?:actor:)?(?:sales|rd|pm|supervisor|customer):\w+[）)]/g, "")
      .replace(/(?:actor:)?((?:sales|rd|pm|supervisor|customer):[\w]+)/g, (_, a) => name(a))
      .replace(/(\w+): /, (m, s) => (meta.slots.some((x) => x.id === s) ? `${slot(s)} ` : m)),
  };
}

// 觉打分的显示：规则打分的推进决策显示「到点」，不冒充概率（REPLAN 3.2）
export function scoreText(q: Pick<Question, "p_need" | "scored_by">) {
  if (!isModel(q.scored_by) || q.p_need == null) return "到点";
  return pct(q.p_need);
}

// 读取接口；version 变化（任何写操作之后）重新读取。
export function useData<T>(load: () => Promise<T>, deps: unknown[]): T | null {
  const { version, fail } = useApp();
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    load().then((d) => alive && setData(d), (e) => alive && fail(e));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, ...deps]);
  return data;
}
