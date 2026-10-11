// 收件箱（研发、主管）：觉提出、签字人是本人的决策，按 prepared_at 分「准备中 / 待签」（REPLAN 3.2 第 4 条）。
// 准备中只显示主人在做什么，没有按钮；待签是橙色，点开后签字区在工作面顶部。
import { api } from "../api";
import { PREPARING, useApp, useData, useLabels } from "../ctx";
import type { Question, RequirementSummary } from "../types";
import { Score, SideHead } from "./ui";

export function useInbox() {
  const { me } = useApp();
  const qs = useData(() => api.questions(me), [me]) ?? [];
  const preparing = qs.filter((q) => q.prepared_at == null);
  const ready = qs.filter((q) => q.prepared_at != null);
  return { all: qs, preparing, ready };
}

export function ownerText(q: Question, me: string, name: (id: string) => string) {
  const who = q.owner_id === me ? "你的 Agent" : q.owner_id ? name(q.owner_id) : "主人";
  return `${who}${/[A-Za-z]$/.test(who) ? " " : ""}${PREPARING[q.family] ?? "正在准备"}`;
}

// guided：导览要签、但当前没打开的那一项，呼吸高亮
export function InboxSidebar({ selected, guided, select, reqs }: {
  selected: string | null; guided?: string | null; select: (q: Question) => void; reqs: RequirementSummary[];
}) {
  const { me } = useApp();
  const L = useLabels();
  const { preparing, ready } = useInbox();
  const object = (q: Question) => {
    const r = reqs.find((x) => x.id === q.refs.requirement_id);
    return r ? L.phen(r.phenomenon) : L.scrub(q.title);
  };
  return (
    <>
      <SideHead aside={!!ready.length && <span className="num text-attn-ink">{ready.length}</span>}>待签</SideHead>
      {ready.map((q) => (
        <button key={q.id} onClick={() => select(q)} className={`side-row ${q.id === selected ? "on" : ""} ${q.id === guided ? "glow" : ""}`}>
          <div className="flex items-center gap-1.5">
            <span className="tag tag-attn">{L.family(q.family)}</span>
            <span className="ml-auto"><Score q={q} /></span>
          </div>
          <p className="mt-1 truncate text-[13px] font-semibold">{object(q)}</p>
          {q.family === "opportunity" && q.evidence[0] && <p className="truncate text-[12px] text-ink-2">{L.scrub(q.evidence[0].summary)}</p>}
        </button>
      ))}
      {!ready.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">没有待签的决策</p>}
      <SideHead>准备中</SideHead>
      {preparing.map((q) => (
        <button key={q.id} onClick={() => select(q)} className={`side-row ${q.id === selected ? "on" : ""}`}>
          <p className="flex items-center gap-1.5"><span className="tag">{L.family(q.family)}</span>
            <span className="truncate text-[13px]">{object(q)}</span></p>
          <p className="mt-0.5 text-[12px] text-ink-2">{ownerText(q, me, L.name)}</p>
        </button>
      ))}
      {!preparing.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">无</p>}
    </>
  );
}
