// V12.13「要你定」：一件待办先用一句话问人、说清为什么到你这，签字区（各岗位原有的审阅组件）挂在下面。
// 界面上不出现层级编号、「授予」和内部编号：层级写成岗位，对象写成产品或现象。
import { useState } from "react";
import { useLabels } from "../ctx";
import type { Question } from "../types";
import { useGlow } from "./Guide";
import { Score } from "./ui";

export const LAYER_WHO: Record<string, string> = { "0": "客户", "1": "业务员", "2": "产品经理", "3": "研发" };

const ASK: Record<string, string> = {
  accept_requirement: "接不接这张单？", distortion: "转述可能走样了，核对一下", confirm_translation: "Agent 写的化学要点对不对？",
  reuse_product: "现成产品能直接用吗？", opportunity: "这几位客户说的是同一件事吗？", contribution: "这次的改动要不要记成你的经验？",
  market_eval: "客户怎么评价样品？", seal_points: "哪些能对外说，哪些只留在研发？", seal_leak: "说明书可能说多了，改一下",
  release: "说明书能发布了吗？", trial_rework: "试样没过，需求要不要重新梳理？", trial_risk: "这次试样有风险，先处理吗？",
  stale_capability: "你以前的判断可能过时了，还成立吗？", qi_review: "资料改了，你的判断还成立吗？",
  decrypt_request: "客户想看保密内容，批不批？", knowledge_conflict: "试样结果和适用表对不上，改不改？",
  leak_risk: "有人在反复打听保密内容，要不要冻结？", mechanism_followup: "客户在追问产品内部，要不要接手？",
  escalate_need: "要不要转研发？", scope_update: "要不要扩大产品的适用范围？", sheet_mismatch: "说明书要跟上研发的判断吗？",
  capability_recall: "要不要回访过去没解决的客户？", contribution_pm: "这次的产品需求要不要记成你的经验？",
};

const WHY: Record<string, string> = {
  accept_requirement: "产品经理 Agent 把客户的话整理成了需求，要你判断立不立项。",
  distortion: "觉发现需求里的说法和客户原话对不上。",
  confirm_translation: "接单后你的 Agent 把需求写成了化学要点，你确认了才算数。",
  reuse_product: "产品经理 Agent 找到一款可能能用的产品，能用就不用立项。",
  opportunity: "几张单说的是同类现象，产品经理 Agent 建议合成一个课题。",
  contribution: "你改过 Agent 写的化学要点；记下来，以后别人用到会记在你名下。",
  seal_points: "试样过了，要分清哪些写进说明书、哪些只留在研发。",
  seal_leak: "觉发现说明书里有研发才能看的内容。",
  release: "说明书只用产品需求和你放出的要点写成，你看过才发布。",
  trial_rework: "试样没过，可能是需求里漏了条件。",
  qi_review: "你签过的判断所依据的资料改了，用到它的地方已经先停下，等你看。",
  decrypt_request: "业务员替客户申请看保密内容，只有你能批。",
  scope_update: "研发判过这款产品能用在说明书没写的场合。",
  sheet_mismatch: "研发的判断和说明书写的不一致。",
  capability_recall: "研发有了新判断，过去没解决的客户可能用得上。",
};

export function useAsk() {
  const L = useLabels();
  return (q: Question) => {
    if (q.family !== "qi_grant") return ASK[q.family] ?? L.scrub(q.title);
    if ("requester" in q.refs) return `${L.name(q.refs.requester)}想看你这条判断的原文，给不给？`;
    if (q.refs.form === "statement") return `${LAYER_WHO[q.refs.audience]}那边答不上来，给他们一句能说的话？`;
    return `让${LAYER_WHO[q.refs.audience]}直接用你这条判断？`;
  };
}

// 这件事说的是谁：需求单写现象，知识写产品
export function useObject(reqs: { id: string; phenomenon: string | null }[]) {
  const L = useLabels();
  return (q: Question) => {
    const r = reqs.find((x) => x.id === (q.refs.requirement_id ?? (q.refs.requirement_ids ?? "").split(",")[0]));
    return r ? L.phen(r.phenomenon) : q.refs.product_id ? L.product(q.refs.product_id) : L.scrub(q.title);
  };
}

// title / why 不给就按决策类型写；试样录入这类不经过觉的事直接给 title
export function TaskHead({ q, title, why }: { q?: Question; title?: string; why?: React.ReactNode }) {
  const ask = useAsk();
  const reason = why ?? (q && WHY[q.family]);
  return (
    <div className="flex items-end justify-between gap-3 px-1">
      <div className="min-w-0">
        <p className="eyebrow !text-attn-ink">要你定</p>
        <h2 className="mt-0.5 text-[19px] font-semibold leading-7">{title ?? ask(q!)}</h2>
        {reason && <p className="mt-0.5 text-[13px] leading-5 text-ink-2">{reason}</p>}
      </div>
      {q && <Score q={q} />}
    </div>
  );
}

export function TaskCard({ q, title, why, children }: { q?: Question; title?: string; why?: React.ReactNode; children: React.ReactNode }) {
  const glow = useGlow(`sign:${q?.family}`);
  return (
    <section className={`flex flex-col gap-2 ${glow ? "guide-scope" : ""}`}>
      <TaskHead q={q} title={title} why={why} />
      <div className="group attn-ring">{children}</div>
    </section>
  );
}

// 没有要你定的事时，写一句现在在等什么
export function Waiting({ children }: { children: React.ReactNode }) {
  return <p className="rounded-xl bg-fill px-5 py-3.5 text-[14px] text-ink-2">{children}</p>;
}

// 其余内容默认收起：一排标签，点哪个展开哪个
export function More({ items }: { items: [string, React.ReactNode, boolean][] }) {
  const [open, setOpen] = useState<string | null>(null);
  const shown = items.filter(([, , show]) => show);
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12.5px] text-ink-3">更多</span>
        {shown.map(([label]) => (
          <button key={label} type="button" onClick={() => setOpen(open === label ? null : label)}
                  className={`chip ${open === label ? "!bg-ink !text-white" : ""}`}>{label}</button>
        ))}
      </div>
      {shown.filter(([label]) => label === open).map(([label, node]) => <div key={label} className="anim-fade">{node}</div>)}
    </section>
  );
}
