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
  go: (page: string, focus?: string | null, who?: string) => void;   // v6：跳到某个角色子工作面（可指定那个人）并打开同一对象
  focus: string | null;             // 跳转时带来的对象 id，子工作面据此选中
  side: HTMLElement | null;         // 侧栏下半部分：各页面把自己的 source list 放进来
  startDemo: () => void;            // V6-5.5：进入演示讲解（左侧换成讲解栏）
  openMode: () => void;             // 打开「运行方式」（接入自己的模型）
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
  qi_grant: "授予能力", qi_review: "依据复核", trial_rework: "退回重新转译", trial_risk: "试样风险", stale_capability: "判断过时",
  ask_slot: "追问", escalate_need: "推荐还是升级", reuse_product: "现成产品审定", opportunity: "机会汇聚",
  accept_requirement: "接单", ask_back: "回问", distortion: "转译失真", confirm_translation: "确认化学要点",
  contribution: "沉淀", market_eval: "客户评价", seal_points: "封存 / 放出", seal_leak: "说明书泄密",
  release: "发布审定", knowledge_conflict: "知识冲突", leak_risk: "泄露风险", mechanism_followup: "追问产品内部", decrypt_request: "解密申请",
  route_rd: "直达研发", handoff_sales: "交业务员", scope_update: "扩展适用范围", contribution_pm: "沉淀产品需求",
};
// 准备中的问题只显示主人在做什么
export const PREPARING: Record<string, string> = {
  qi_grant: "正在整理授予依据", qi_review: "正在整理变化的依据",
  reuse_product: "正在查现成产品", opportunity: "正在读各单原话、判断是不是同一件事",
  accept_requirement: "正在起草产品需求（L2）", confirm_translation: "正在起草化学语言（L3）",
  contribution: "正在提炼可沉淀的知识", seal_points: "正在起草封存 / 放出两栏", release: "正在包装说明书",
  seal_leak: "正在改写说明书", escalate_need: "正在起草升级说明", decrypt_request: "正在准备解密说明",
  scope_update: "正在整理研发的判断与客户原话", contribution_pm: "正在提炼可沉淀的产品需求",
};
export const REQ_STATUS: Record<string, string> = {
  draft: "产品经理 Agent 起草中", reused: "已复用现成产品", merged: "已并入另一张单", rd_accepted: "研发已接单",
  rd_confirmed: "研发已确认化学要点", released: "已发布", rejected: "研发不立项",
};
export const SESSION_STATUS: Record<string, string> = { open: "进行中", recommended: "已推荐", escalated: "已转研发", closed: "已记录，暂无方案" };
export const ACTION: Record<string, string> = {
  sign: "已签字", accept: "已接单", return: "已退回", answered: "已回答", update_sheet: "已更新适用表",
  freeze_access: "已冻结上层知识检索", take_over: "已接手", approve_decrypt: "已批准解密", reject_decrypt: "已拒绝解密", dismiss: "现在不需要",
  auto: "觉 · 自动执行",
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
  const actors: Record<string, string> = { jue: "觉", "jue:auto": "觉", system: "系统",
    ...Object.fromEntries(meta.actors.map((a) => [a.id, a.name.replace("（模拟）", "")])) };
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
      .replace("转译可以确认了吗", "化学要点（L3）可以确认了吗")   // 模板标题进 Agent 提示词（改了会让录制缓存失效），只在显示处改说法
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
