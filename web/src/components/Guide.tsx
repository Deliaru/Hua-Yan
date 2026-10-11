// 演示导览：工具栏正中的一枚胶囊，状态一变就自动展开；按系统当前状态说明主线走到哪一步、现在轮到谁、该在哪里做什么。
// 导览同时指出下一步要按的按钮（target）：轮到当前身份时，工作面上那个按钮呼吸高亮；不是当前身份时高亮「切换」。
// 只用于给评委看懂流程：步骤由会话、需求单状态与问题总线上的开放问题推断，可签条件仍由门面判断。
// 导览是旁白视角，不随当前身份：以研发（L3）权限读取全局状态，浮层底部向评委写明；实际业务中当前身份看不到这些。
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { NextAction, Question, RequirementView, SessionSummary, SessionView } from "../types";
import { STEPS } from "../pages/Overview";
import { ChevronDown } from "./Icons";

const SHORT = ["客户描述", "追问补全", "推荐或升级", "查现成产品", "转产品需求", "研发接单", "化学转译", "试样与沉淀", "说明书", "发布回流"];

// 每类决策落在主线哪一步、签字人在工作面上做什么
const DO: Record<string, [number, string]> = {
  ask_slot: [1, "觉判断还缺关键信息：点「发给客户」上方的追问提词（或「帮我回一句」），再点「发出」；然后用「演示自动填入」录入客户的回答"],
  escalate_need: [2, "现有产品都不合适，业务员的 Agent 已起草升级说明；看一遍，在签字区签字转产品经理 Agent"],
  reuse_product: [3, "产品经理 Agent 在历史案例里找到可复用的产品；研发审定是否直接用，用则不必立项"],
  opportunity: [4, "几位客户说的可能是同一件事；研发判断是否合并成一张单"],
  accept_requirement: [5, "产品经理 Agent 已把客户场景转成产品需求（L2）；研发看懂后接单（= 立项），看不懂就退回"],
  ask_back: [6, "研发要的信息客户没说过；切到业务员，在该客户的会话里把 Agent 起草的回问发出，再录入客户的回答，答复会自动回填需求单"],
  distortion: [6, "觉发现转译和客户原话对不上；研发核对后处理"],
  confirm_translation: [6, "研发的 Agent 已把需求写成化学要点（L3），每条标明依据了谁的知识；研发逐条看、可修改，然后确认"],
  contribution: [7, "研发改过的转译可以沉淀为自己的知识，以后被引用就给他记分；研发签字"],
  market_eval: [7, "试样通过后业务员把样品给客户，带回客户评价"],
  seal_points: [7, "研发决定哪些是窗户纸要封存、哪些作为对外要点放出"],
  seal_leak: [8, "觉发现说明书碰到了封存内容；研发的 Agent 改写，研发签字"],
  release: [9, "说明书只用产品需求和对外要点写成；研发审定发布，新品回到 L1 知识库"],
  decrypt_request: [7, "客户要看机理，业务员申请解密；由研发本人审批"],
  knowledge_conflict: [6, "试样结果和产品适用表对不上；研发判断是否更新适用表"],
  leak_risk: [8, "觉发现有人反复检索同一产品的机理和配方，可能在拼凑保密知识；主管判断是否冻结其高层级检索权限"],
};

// 导览指向的按钮：sign:<family> 签字区的主按钮；reply 追问提词与「发出」；send「发出」；send-rec 填进发给客户；
// customer「演示自动填入」与「录入」；new-session 新建客户会话；trial 试样通过；回放部署另有 chat / edit / reuse-note。
// arg 是台词要填的内容（客户 id、对 Agent 说的话、要补的文字），由对应输入处的「演示自动填入」使用。只在轮到当前身份时高亮。
// customer：这一步发生在哪位客户的会话里（回放部署按台词给出），业务员工作面据此选中、高亮那段会话。
type Target = { who: string | null; target: string | null; arg: string | null; customer: string | null };
let current: Target = { who: null, target: null, arg: null, customer: null };
const subs = new Set<() => void>();
function publish(t: Target) {
  if (t.who === current.who && t.target === current.target && t.arg === current.arg && t.customer === current.customer) return;
  current = t;
  subs.forEach((f) => f());
}
export function useGuide(): Target {
  return useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f); }; }, () => current);
}
export function useGlow(target: string): boolean {
  const { me } = useApp();
  const g = useGuide();
  return g.who === me && g.target === target;
}
// 轮到当前身份做 target 时，台词要填的内容
export function useGuideArg(target: string): string | null {
  const g = useGuide();
  return useGlow(target) ? g.arg : null;
}

type Plan = { step: number; who: string | null; todo: string; raised: string | null; target: string | null; arg?: string | null; customer?: string | null };

// 台词里签字动作 → 决策 family（与 scripts/demo_mainline.py 的 FAMILIES 一致）
const SIGN_FAMILY: Record<string, string> = {
  escalate: "escalate_need", "reuse/adopt": "reuse_product", merge: "opportunity", accept: "accept_requirement",
  confirm: "confirm_translation", contribute: "contribution", "market-eval": "market_eval", points: "seal_points", release: "release",
};

export function Guide() {
  const { meta, me, version, switchTo } = useApp();
  const L = useLabels();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => ref.current?.contains(e.target as Node) || setOpen(false);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const humans = meta.actors.filter((a) => a.role === "sales" || a.role === "rd" || a.role === "supervisor");
  const sales = humans.find((a) => a.role === "sales")!.id;
  const rd = humans.find((a) => a.role === "rd")!.id;
  const state = useData(async () => {
    const [sessions, reqs, qs] = await Promise.all([
      api.sessions(), api.requirements(rd), Promise.all(humans.map((a) => api.questions(a.id))),
    ]);
    const open = new Map<string, Question>();
    qs.flat().filter((q) => q.status === "open").forEach((q) => open.set(q.id, q));
    const last = reqs[reqs.length - 1];
    const view = last ? await api.requirement(last.id, rd) : null;
    const s = sessions[sessions.length - 1];
    const session = s ? await api.session(s.id, s.sales_id) : null;
    const script = meta.status.replay ? await api.nextAction() : null;
    return { sessions, reqs, view, session, script, open: [...open.values()].sort((a, b) => a.created_at.localeCompare(b.created_at)) };
  }, [me, version]);
  const customers = meta.actors.filter((a) => a.role === "customer").map((a) => a.id);
  // 回放部署按台词引导（偏离台词会缓存未命中）；现场按系统状态推断
  const plan = state && (state.script ? fromScript(state.script, state.view?.requirement.assigned_rd ?? rd, L)
    : derive(state, sales, rd, customers, L));
  const key = plan ? `${plan.step}|${plan.who}|${plan.target}|${plan.raised}` : "";
  useEffect(() => { if (key) setOpen(true); }, [key]);   // 走到新的一步自动展开
  useEffect(() => publish({ who: plan?.who ?? null, target: plan?.target ?? null, arg: plan?.arg ?? null, customer: plan?.customer ?? null }),
            [plan?.who, plan?.target, plan?.arg, plan?.customer]);
  useEffect(() => () => publish({ who: null, target: null, arg: null, customer: null }), []);
  if (!plan) return null;
  const { step, who, todo, raised } = plan;
  const mine = who === me;
  const whoText = who ? (mine ? "轮到你" : `轮到 ${L.name(who)}`) : step === 9 ? "已完成" : "Agent 准备中";

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(!open)} title="演示导览：以研发（L3）权限读取全局状态，只为介绍流程"
              className={`flex h-7 items-center gap-2 rounded-full pl-1 pr-2.5 text-[12px] transition-colors ${open ? "bg-fill" : "glow bg-white hover:bg-fill"}`}>
        <span className="num flex h-5 items-center rounded-full bg-attn px-1.5 text-[11px] font-semibold text-white">{step + 1}/{SHORT.length}</span>
        <span className="text-ink-2">演示导览</span>
        <span className="font-semibold">{SHORT[step]}</span>
        <span className="text-ink-3">·</span>
        <span className={mine ? "text-attn-ink" : "text-ink-2"}>{whoText}</span>
        <span className="text-ink-3"><ChevronDown /></span>
      </button>
      {open && (
        <div className="popover anim-fade left-1/2 top-full mt-2 w-[400px] -translate-x-1/2 !p-0">
          <div className="px-4 pb-2 pt-3">
            <p className="eyebrow">演示导览</p>
            <p className={`mt-1 text-[13px] ${raised ? "font-semibold text-attn-ink" : "text-ink-2"}`}>
              {raised ?? "觉此刻没有提出决策；下一步由人操作"}</p>
          </div>
          <p className="px-4 pb-1 text-[11px] text-ink-3">典型路径（参考）· 实际走哪一步由觉提出</p>
          <ol className="px-2 pb-2">
            {SHORT.map((name, i) => i === step ? (
              <li key={name} className="my-1 rounded-[10px] bg-white px-3 py-2.5 shadow-[0_0_0_.5px_rgba(0,0,0,.08),0_1px_3px_rgba(0,0,0,.06)]">
                <p className="flex items-center gap-2 text-[13px] font-semibold">
                  <Dot i={i} step={step} />{name}<span className="ml-auto font-normal text-ink-2">{whoText}</span>
                </p>
                <p className="mt-1.5 pl-7 text-[13px] leading-[20px]">{todo}</p>
                <p className="mt-1 pl-7 text-[12px] leading-[18px] text-ink-2">{STEPS[i].how}</p>
                {who && !mine && (
                  <div className="mt-2 pl-7">
                    <button className="btn btn-primary glow" onClick={() => { switchTo(who!); setOpen(false); }}>切换到 {L.name(who)}</button>
                  </div>
                )}
              </li>
            ) : (
              <li key={name} className={`flex items-center gap-2 px-3 py-[3px] text-[12.5px] ${i < step ? "text-ink-2" : "text-ink-3"}`}>
                <Dot i={i} step={step} />{name}
              </li>
            ))}
          </ol>
          <p className="border-t border-sep px-4 py-2 text-[11px] leading-4 text-ink-3">
            导览以研发（L3）权限读取全局状态，只为介绍流程；实际业务中，当前身份看不到自己权限以外的内容。完整流程图见「架构总览」。</p>
        </div>
      )}
    </div>
  );
}

type GuideState = {
  sessions: SessionSummary[]; view: RequirementView | null; session: SessionView | null; script: NextAction | null; open: Question[];
};

// 台词段（demo/mainline.yaml 的 steps 编号）落在导览十步里的哪一步
const CHAPTER_STEP: Record<string, number> = { 1: 1, 2: 2, 3: 4, 4: 6, 5: 6, 6: 7, 7: 9, 支线: 3 };

// 回放部署：下一步就是台词里的下一个动作；要填的文字给出原文并由「演示自动填入」填好，保证与录制一致
function fromScript(n: NextAction, trialBy: string, L: ReturnType<typeof useLabels>): Plan {
  const part = n.chapter?.split("：")[0].replace(/（[^）]*）/, "") ?? "";
  const no = `台词 ${Math.min(n.index + 1, n.total)}/${n.total}${part ? ` · ${part.replace(/^(\d+)\s*/, "第 $1 段 ")}` : ""}`;
  if (!n.action) return { step: 9, who: null, target: null, raised: null,
    todo: "录制好的演示主线与支线已全部走完。可以点右上角「载入检查点」回到某一步，或「重置进度」从头再来" };
  const [kind, b] = Object.entries(n.action)[0];
  const salesOf = (alias: string) => n.sessions[alias].sales;
  const plan = scriptPlan(kind, b, no, salesOf, trialBy, L);
  const alias = b.session ?? b.args?.session;
  // 客户、发出、对 Agent 说话不对应决策：主线进度按台词段定（如回问的「发出」在第 4 段，属于化学转译）
  const step = kind === "sign" || kind === "edit" || kind === "trial" ? plan.step : CHAPTER_STEP[part.match(/^\d+/)?.[0] ?? "支线"] ?? plan.step;
  return { ...plan, step, customer: alias ? n.sessions[alias].customer : null };
}

function scriptPlan(kind: string, b: Record<string, any>, no: string, salesOf: (alias: string) => string, trialBy: string,
                    L: ReturnType<typeof useLabels>): Plan {
  switch (kind) {
    case "start":
      return { step: 0, who: b.sales, target: "new-session", arg: b.customer, raised: no,
        todo: `点左侧「客户会话」右边的 ＋，选「${L.name(b.customer)}」，开始一段新的客户会话` };
    case "customer":
      return { step: 1, who: salesOf(b.session), target: "customer", raised: no,
        todo: `演示者扮客户：点沟通记录底部的「演示自动填入」，再点「录入」。客户说：「${b.text}」` };
    case "send":
      return { step: 1, who: salesOf(b.session), target: "send", raised: no,
        todo: "业务员的 Agent 已把要回的话填进底部「发给客户」；看一遍，点「发出」" };
    case "chat":
      return { step: 1, who: b.actor, target: "chat", arg: b.text, raised: no,
        todo: `人说意图、Agent 起草：在右下「与 Agent 协作」点「演示自动填入」再发送，对 Agent 说：「${b.text}」` };
    case "sign": {
      const family = SIGN_FAMILY[b.action];
      return { step: DO[family][0], who: b.actor, target: `sign:${family}`, arg: b.args.note ?? null, todo: `${where(b.actor, family, L)}${DO[family][1]}`,
        raised: `${no} · 觉提出「${L.family(family)}」，已准备好，等 ${L.name(b.actor)} 签字` };
    }
    case "edit":
      return b.path === "req-item"
        ? { step: 6, who: b.actor, target: "edit", arg: JSON.stringify(b.args), raised: no,
            todo: `研发亲自改一条：在「化学要点 · L3」里找到含「${b.args.contains}」的那条，点「演示自动填入」（会在末尾补上「${b.args.append}」），再点「保存」` }
        : { step: 3, who: b.actor, target: "reuse-note", arg: JSON.stringify(b.args.replace), raised: no,
            todo: `研发改给客户的说明：点「演示自动填入」把「${b.args.replace[0]}」改成「${b.args.replace[1]}」，点「保存修改」` };
    default:   // trial
      return { step: 7, who: trialBy, target: "trial", raised: no,
        todo: "研发去实验室做试样。演示里用需求单上的「试样通过」按钮代替实验室系统回传结果" };
  }
}

// 现在该做的事与要按的按钮，全部由会话、需求单状态与问题总线推断
function derive(state: GuideState, sales: string, rd: string, customers: string[], L: ReturnType<typeof useLabels>): Plan {
  // 演示台词按客户准备：建议选还没开过会话的第一位客户
  const nextCustomer = L.name(customers.find((c) => !state.sessions.some((s) => s.customer_id === c)));
  // 最新会话已有推荐、业务员还没回过客户：下一步是把推荐填进「发给客户」再发出
  const lastTurn = state.session?.turns[state.session.turns.length - 1];
  const recUnsent = state.session?.status === "recommended" && lastTurn?.speaker === "customer";
  const salesOf = state.sessions[state.sessions.length - 1]?.sales_id ?? sales;
  // 现在该做的事：先看已准备好、等人签字的决策；再看主人还在准备的；都没有就按会话与需求单状态推断
  const ready = state.open.find((q) => q.prepared_at != null && DO[q.family]);
  const preparing = state.open.find((q) => q.prepared_at == null && DO[q.family]);
  const req = state.view?.requirement;
  const owner = req?.assigned_rd ?? rd;
  // raised：觉此刻提出的决策（来自问题总线）；没有时给出不经过觉的操作提示（录入客户的话、试样）
  let step: number, who: string | null, todo: string, raised: string | null = null, target: string | null = null;
  if (ready) {
    [step, todo] = DO[ready.family];
    who = ready.signer_id ?? ready.owner_id;
    todo = `${where(who!, ready.family, L)}${todo}`;
    raised = `觉提出「${L.family(ready.family)}」· 已准备好，等 ${L.name(who!)} 签字`;
    target = `sign:${ready.family}`;
  } else if (preparing && preparing.signer_role == null && preparing.owner_id) {
    // 提示类决策（回问）不进待签：主人的 Agent 把话术填进「发给客户」后，就轮到主人本人向客户发出
    [step, todo] = DO[preparing.family];
    who = preparing.owner_id;
    raised = `觉提出「${L.family(preparing.family)}」· 等 ${L.name(who)} 向客户发出`;
    target = "reply";
  } else if (preparing) {
    step = DO[preparing.family][0];
    who = null;
    todo = DO[preparing.family][1];
    raised = `觉提出「${L.family(preparing.family)}」· ${preparing.owner_id ? L.name(preparing.owner_id) + " 的 Agent" : "产品经理 Agent"}正在准备`;
  } else if (req?.status === "released") {
    const last = state.sessions[state.sessions.length - 1];
    const fresh = last && !req.session_ids.includes(last.id) ? last : null;
    if (fresh && recUnsent) {
      [step, who, target] = [9, salesOf, "send-rec"];
      todo = `${L.name(fresh.customer_id)} 说了同样的现象，L1 直接推荐了研发刚发布的新品、不再升级。点右侧推荐卡的「填进发给客户」，再点「发出」`;
    } else if (fresh?.status === "recommended") {
      // 新客户已在 L1 拿到推荐：主线闭环，不再指向任何按钮
      [step, who, target] = [9, null, null];
      todo = `主线完成：${L.name(fresh.customer_id)} 说了同样的现象，L1 直接推荐了研发刚发布的新品，不再升级。右侧推荐卡里的产品说明就是研发审定发布的那份说明书`;
    } else {
      [step, who, target] = [9, sales, fresh ? "customer" : "new-session"];
      todo = fresh ? "让新客户说出同样的现象（「演示自动填入」或直接输入），这次在 L1 直接命中新品，不再升级"
        : `研发已发布新品。点左侧「客户会话」右边的 ＋，选「${nextCustomer}」，让新客户说同样的现象，这次在 L1 直接命中新品`;
    }
  } else if (req?.status === "rd_confirmed") {
    [step, who, todo, target] = [7, owner, "研发去实验室做试样。演示里用需求单上的「试样通过」按钮代替实验室系统回传结果", "trial"];
  } else if (req?.status === "draft") {
    [step, who, todo] = [4, null, "产品经理 Agent 正在把客户场景转成产品需求（L2）"];
  } else if (recUnsent) {
    [step, who, todo, target] = [2, salesOf, "现有产品能解决，L1 已给出推荐。点右侧推荐卡的「填进发给客户」，再点「发出」", "send-rec"];
  } else if (state.sessions.length) {
    [step, who, todo, target] = [1, sales, "点沟通记录底部的「演示自动填入」，再点「录入」，替客户说下一句；觉在旁边判断是否要追问、推荐还是升级", "customer"];
  } else {
    [step, who, todo, target] = [0, sales, `点左侧「客户会话」右边的 ＋，选「${nextCustomer}」开始。客户只会描述现象，比如「染完布面深一块浅一块」`, "new-session"];
  }
  return { step, who, todo, raised, target };
}

// 去哪里签：研发、主管在左侧收件箱「待签」里点开这一项；业务员在右侧「觉提出的决策」里
function where(who: string, family: string, L: ReturnType<typeof useLabels>) {
  return who.startsWith("sales:") ? "在右侧「觉提出的决策」里签字。" : `在左侧「待签」里点「${L.family(family)}」。`;
}

function Dot({ i, step }: { i: number; step: number }) {
  return (
    <span className={`num flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
      i < step ? "bg-accent text-white" : i === step ? "bg-attn text-white" : "shadow-[inset_0_0_0_1px_rgba(60,60,67,.25)]"}`}>
      {i < step ? "✓" : i + 1}
    </span>
  );
}
