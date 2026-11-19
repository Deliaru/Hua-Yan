// 收件箱（研发、主管）：觉提出、签字人是本人的决策，按 prepared_at 分「Agent 在准备 / 等你定」（REPLAN 3.2 第 4 条）。
// 准备中只显示主人在做什么；V9.2 模型接口失败没准备成的，写明原因并可整项重跑。点开后「要你定」在工作面顶部。
// V12.13 每项写成一句问话；别人来要你的判断（授予）不挡客户的事，排在「不急的」里。
import { api } from "../api";
import { PREPARING, useApp, useData, useLabels } from "../ctx";
import type { Question, RequirementSummary } from "../types";
import { SideHead } from "./ui";
import { useAsk, useObject } from "./Task";

export function useInbox() {
  const { me } = useApp();
  const qs = useData(() => api.questions(me), [me]) ?? [];
  const failures = useData(() => api.agentFailures(me), [me]) ?? {};
  const preparing = qs.filter((q) => q.prepared_at == null);
  const ready = qs.filter((q) => q.prepared_at != null).sort((a, b) => +(a.family === "qi_grant") - +(b.family === "qi_grant"));
  return { all: qs, preparing, ready, failures };
}

export function ownerText(q: Question, me: string, name: (id: string) => string) {
  const who = q.owner_id === me ? "你的 Agent" : q.owner_id ? name(q.owner_id) : "主人";
  return `${who}${/[A-Za-z]$/.test(who) ? " " : ""}${PREPARING[q.family] ?? "正在准备"}`;
}

// guided：导览要签、但当前没打开的那一项，呼吸高亮
export function InboxSidebar({ selected, guided, select, reqs }: {
  selected: string | null; guided?: string | null; select: (q: Question) => void; reqs: RequirementSummary[];
}) {
  const { me, refresh, fail } = useApp();
  const L = useLabels();
  const { preparing, ready, failures } = useInbox();
  const ask = useAsk();
  const object = useObject(reqs);
  const retry = (id: string) => api.agentRetry(id, me).then(refresh, fail);
  const urgent = ready.filter((q) => q.family !== "qi_grant"), later = ready.filter((q) => q.family === "qi_grant");
  const item = (q: Question) => (
    <button key={q.id} onClick={() => select(q)} className={`side-row ${q.id === selected ? "on" : ""} ${q.id === guided ? "glow" : ""}`}>
      <p className="truncate text-[13px] font-semibold">{ask(q)}</p>
      <p className="truncate text-[12px] text-ink-2">{object(q)}</p>
    </button>
  );
  return (
    <>
      <SideHead aside={!!urgent.length && <span className="num text-attn-ink">{urgent.length}</span>}>等你定</SideHead>
      {urgent.map(item)}
      {!urgent.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">没有要你定的事</p>}
      {!!later.length && <SideHead aside={<span className="num">{later.length}</span>}>不急的 · 别人想用你的判断</SideHead>}
      {later.map(item)}
      <SideHead>Agent 在准备</SideHead>
      {preparing.map((q) => (
        <button key={q.id} onClick={() => select(q)} className={`side-row ${q.id === selected ? "on" : ""}`}>
          <p className="truncate text-[13px]">{ask(q)}</p>
          <p className="truncate text-[12px] text-ink-2">{object(q)}</p>
          <p className="mt-0.5 text-[12px] text-ink-2">{ownerText(q, me, L.name)}</p>
          {failures[q.id] && <p className="mt-0.5 text-[12px] text-danger" title={failures[q.id].error}>
            模型接口失败，没准备成，稍后自动重跑</p>}
        </button>
      ))}
      {preparing.filter((q) => failures[q.id]).map((q) => (
        <div key={`retry:${q.id}`} className="flex items-center gap-2 px-[18px] py-1 text-[12px] text-ink-2">
          <span className="truncate">{object(q)}</span>
          <button className="btn btn-plain ml-auto !h-6" onClick={() => retry(q.id)}>现在重跑</button>
        </div>
      ))}
      {!preparing.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">无</p>}
    </>
  );
}
