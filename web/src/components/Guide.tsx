// 演示导览：工具栏正中的一枚胶囊，点开看全部步骤；按系统当前状态说明主线走到哪一步、现在轮到谁、该在哪里做什么。
// 只用于给评委看懂流程：步骤由会话、需求单状态与问题总线上的开放问题推断，可签条件仍由门面判断。
// 导览是旁白视角，不随当前身份：需求单状态按研发身份读取，界面上只显示步骤，不显示需求单内容。
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { Question } from "../types";
import { STEPS } from "../pages/Overview";
import { ChevronDown } from "./Icons";

const SHORT = ["客户描述", "追问补全", "推荐或升级", "查现成产品", "转产品需求", "研发接单", "化学转译", "试样与沉淀", "说明书", "发布回流"];

// 每类决策落在主线哪一步、签字人在工作面上做什么
const DO: Record<string, [number, string]> = {
  ask_slot: [1, "觉判断还缺关键信息，趁客户还在，按右侧提示追问，把客户的回答录进对话"],
  escalate_need: [2, "现有产品都不合适，业务员的 Agent 已起草升级说明；看一遍，在签字区签字转产品经理 Agent"],
  reuse_product: [3, "产品经理 Agent 在历史案例里找到可复用的产品；研发审定是否直接用，用则不必立项"],
  opportunity: [4, "几位客户说的可能是同一件事；研发判断是否合并成一张单"],
  accept_requirement: [5, "产品经理 Agent 已把客户场景转成产品需求（L2）；研发看懂后接单（= 立项），看不懂就退回"],
  ask_back: [6, "研发要的信息客户没说过；业务员回头问客户，答复会自动回填需求单"],
  distortion: [6, "觉发现转译和客户原话对不上；研发核对后处理"],
  confirm_translation: [6, "研发的 Agent 已把需求写成化学要点（L3），每条标明依据了谁的知识；研发逐条看、可修改，然后确认"],
  contribution: [7, "研发改过的转译可以沉淀为自己的知识，以后被引用就给他记分；研发签字"],
  market_eval: [7, "试样通过后业务员把样品给客户，带回客户评价"],
  seal_points: [7, "研发决定哪些是窗户纸要封存、哪些作为对外要点放出"],
  seal_leak: [8, "觉发现说明书碰到了封存内容；研发的 Agent 改写，研发签字"],
  release: [9, "说明书只用产品需求和对外要点写成；研发审定发布，新品回到 L1 知识库"],
  decrypt_request: [7, "客户要看机理，业务员申请解密；由研发本人审批"],
  knowledge_conflict: [6, "两条知识说法冲突；研发判断以哪条为准"],
  leak_risk: [8, "觉发现几次对外回答拼起来可能泄露配方；研发处理"],
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
    return { sessions, reqs, view, open: [...open.values()].sort((a, b) => a.created_at.localeCompare(b.created_at)) };
  }, [me, version]);
  if (!state) return null;

  // 现在该做的事：先看已准备好、等人签字的决策；再看主人还在准备的；都没有就按会话与需求单状态推断
  const ready = state.open.find((q) => q.prepared_at != null && DO[q.family]);
  const preparing = state.open.find((q) => q.prepared_at == null && DO[q.family]);
  const req = state.view?.requirement;
  const owner = req?.assigned_rd ?? rd;
  let step: number, who: string | null, todo: string;
  if (ready) {
    [step, todo] = DO[ready.family];
    who = ready.signer_id ?? ready.owner_id;
  } else if (preparing) {
    step = DO[preparing.family][0];
    who = null;
    todo = `觉已提出「${L.family(preparing.family)}」，${preparing.owner_id ? L.name(preparing.owner_id) + " 的 Agent" : "产品经理 Agent"}正在准备，准备好后签字人的收件箱会出现待签项`;
  } else if (req?.status === "released") {
    [step, who, todo] = [9, sales, "主线已走完。业务员再开一位客户、说同样的现象，这次在 L1 直接命中新品，不再升级"];
  } else if (req?.status === "rd_confirmed") {
    [step, who, todo] = [7, owner, "研发去实验室做试样。演示里用需求单上的「试样通过（模拟实验室系统）」按钮代替实验室回传结果"];
  } else if (req?.status === "draft") {
    [step, who, todo] = [4, null, "产品经理 Agent 正在把客户场景转成产品需求（L2）"];
  } else if (state.sessions.length) {
    [step, who, todo] = [1, sales, "演示者扮演客户，在对话框里录入客户的话；觉在旁边判断是否要追问、推荐还是升级"];
  } else {
    [step, who, todo] = [0, sales, "点左侧「客户会话」右边的 ＋ 选一位客户开始。客户只会描述现象，比如「染完布面深一块浅一块」"];
  }
  const mine = who === me;
  const whoText = who ? (mine ? "轮到你" : `轮到 ${L.name(who)}`) : "Agent 准备中";

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(!open)} title="演示导览"
              className={`flex h-7 items-center gap-2 rounded-full pl-1 pr-2.5 text-[12px] transition-colors ${open ? "bg-fill" : "hover:bg-fill"}`}>
        <span className="num flex h-5 items-center rounded-full bg-attn px-1.5 text-[11px] font-semibold text-white">{step + 1}/{SHORT.length}</span>
        <span className="font-semibold">{SHORT[step]}</span>
        <span className="text-ink-3">·</span>
        <span className={mine ? "text-attn-ink" : "text-ink-2"}>{whoText}</span>
        <span className="text-ink-3"><ChevronDown /></span>
      </button>
      {open && (
        <div className="popover anim-fade left-1/2 top-full mt-2 w-[400px] -translate-x-1/2 !p-0">
          <p className="eyebrow px-4 pb-2 pt-3">演示导览 · 一条需求怎样走完三层</p>
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
                    <button className="btn btn-primary" onClick={() => { switchTo(who!); setOpen(false); }}>切换到 {L.name(who)}</button>
                  </div>
                )}
              </li>
            ) : (
              <li key={name} className={`flex items-center gap-2 px-3 py-[3px] text-[12.5px] ${i < step ? "text-ink-2" : "text-ink-3"}`}>
                <Dot i={i} step={step} />{name}
              </li>
            ))}
          </ol>
          <p className="border-t border-sep px-4 py-2 text-[11px] text-ink-3">按系统当前状态推断；完整流程图见「架构总览」</p>
        </div>
      )}
    </div>
  );
}

function Dot({ i, step }: { i: number; step: number }) {
  return (
    <span className={`num flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
      i < step ? "bg-accent text-white" : i === step ? "bg-attn text-white" : "shadow-[inset_0_0_0_1px_rgba(60,60,67,.25)]"}`}>
      {i < step ? "✓" : i + 1}
    </span>
  );
}
