// 主管：收件箱处理泄露风险待签卡（业务员、证据计数，「冻结上层知识检索」/「现在不需要」）；v8 Q9.8 下方列出已冻结的人，可解冻。
// V11.3 研发负责人掌握进展：侧栏「进展」列出全部需求单，点开看这件事的前情和现在在等谁。
// V12.11 加两块：风险与例外（泄露、去密、试样风险、能力走偏与依据变化；超期、Agent 没准备成、挂起待复核）与能力谱系（全部能力的依据、
// 授予、使用与变化，改版时看影响面）。研发负责人不当额外审批人，只掌握进展、处理例外；主管是 L2，研发层的内容只见归属。
import { useState } from "react";
import type { ExceptionRow } from "../types";
import { REQ_STATUS, Side, useApp, useData, useLabels } from "../ctx";
import { InboxSidebar, useInbox } from "../components/Inbox";
import { Act, EmptyState, Group, PageHead, SideHead } from "../components/ui";
import { Backstory } from "../components/Backstory";
import { RouteStrip } from "../components/Route";
import { api } from "../api";
import { SignArea } from "./Rd";

function Frozen() {
  const { me } = useApp();
  const L = useLabels();
  const rows = useData(() => api.frozenActors(me), [me]) ?? [];
  if (!rows.length) return null;
  return (
    <Group title="已冻结上层知识检索">
      {rows.map((r) => (
        <div key={r.actor_id} className="row !items-start">
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-semibold">{r.name}<span className="ml-2 text-[12px] font-normal text-ink-3">{r.frozen_at.slice(5, 16).replace("T", " ")} 冻结</span></p>
            {r.evidence.map((e, i) => <p key={i} className="text-[12.5px] leading-5 text-ink-2">{L.scrub(e)}</p>)}
            <p className="text-[12.5px] text-ink-2">冻结以来被挡下的检索 {r.n_denied} 次；涉及客户：{r.customers.map(L.name).join("、") || "无"}</p>
          </div>
          <Act kind="plain" label="解冻" done="已解冻" run={() => api.unfreeze(r.actor_id, me)} />
        </div>
      ))}
    </Group>
  );
}

export function Supervisor() {
  const { me } = useApp();
  const L = useLabels();
  const { all, ready } = useInbox();
  const reqs = (useData(() => api.requirements(me), [me]) ?? []).filter((r) => r.status !== "merged").reverse();
  const [qid, setQid] = useState<string | null>(null);
  const [rid, setRid] = useState<string | null>(null);
  const q = rid ? null : all.find((x) => x.id === qid) ?? ready[0] ?? null;
  const req = reqs.find((r) => r.id === rid);
  return (
    <>
      <Side>
        <InboxSidebar selected={q?.id ?? null} reqs={[]} select={(x) => { setQid(x.id); setRid(null); }} />
        <SideHead aside={<span className="num">{reqs.length}</span>}>进展</SideHead>
        {reqs.map((r) => (
          <button key={r.id} onClick={() => setRid(r.id)} className={`side-row ${r.id === rid ? "on" : ""}`}>
            <p className="text-[13px] font-semibold">{L.phen(r.phenomenon)}</p>
            <p className="truncate text-[12px] text-ink-2">{[r.customer_ids.map(L.name).join("、"), REQ_STATUS[r.status]].filter(Boolean).join(" · ")}</p>
          </button>
        ))}
        {!reqs.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">还没有需求单</p>}
      </Side>
      <div className="mx-auto flex max-w-[760px] flex-col gap-6 px-8 pb-24 pt-7">
        {req ? <>
          <PageHead title={L.phen(req.phenomenon)} subtitle={[req.customer_ids.map(L.name).join("、"), REQ_STATUS[req.status]].filter(Boolean).join(" · ")} />
          <Backstory key={req.id} id={req.id} />
          <RouteStrip objectId={req.id} />
        </> : q ? <SignArea key={q.id} q={q} view={null} />
          : <EmptyState title="没有待处理的风险" text="觉发现某位业务员的检索集中在同一产品的上层知识时，会在这里提出是否冻结其上层知识检索。" />}
        <Frozen />
        <Exceptions />
        <Lineage />
      </div>
    </>
  );
}

const FAMILY: Record<string, string> = { leak_risk: "泄露风险", seal_leak: "对外说明去密", seal_points: "封存与放出", trial_risk: "试样风险",
  stale_capability: "能力走偏", qi_review: "依据变化复核", knowledge_conflict: "知识冲突" };
const FORM: Record<string, string> = { applicable: "适用", ask: "追问", statement: "可说的话", decrypt: "机理说明", phrase: "说法", translation: "转化对照", share: "同层共享" };
const STATUS: Record<string, string> = { active: "生效", proposed: "待批准", suspended: "挂起", revoked: "已撤销" };
const CHANGE: Record<string, string> = { evidence_changed: "依据变了", capability_suspended: "挂起", capability_revoked: "撤销", recommendation_withdrawn: "推荐撤下改道" };
const wait = (h: number) => (h < 1 ? `${Math.max(1, Math.round(h * 60))} 分钟` : h < 48 ? `${h} 小时` : `${Math.round(h / 24)} 天`);

function Exceptions() {
  const { me } = useApp();
  const L = useLabels();
  const b = useData(() => api.exceptions(me), [me]);
  if (!b) return null;
  const line = (r: ExceptionRow, extra?: string) => (
    <div key={r.id} className="row !items-start text-[12.5px]">
      <span className="w-[86px] shrink-0"><span className="tag">{FAMILY[r.family] ?? r.family}</span></span>
      <span className="min-w-0 flex-1">{L.scrub(r.title)}
        <span className="block text-ink-2">{r.owner_id && `${L.name(r.owner_id)}在办`}{r.signer_id && r.signer_id !== r.owner_id && ` · ${L.name(r.signer_id)}签字`}{extra && ` · ${extra}`}</span></span>
      <span className={`shrink-0 ${r.status === "open" ? "text-attn-ink" : "text-ink-2"}`}>
        {r.status === "open" ? `等了 ${wait(r.waited_hours)}` : `${r.by ? L.name(r.by) : ""}已处理 · 用了 ${wait(r.waited_hours)}`}</span>
    </div>);
  const empty = !b.risk.length && !b.overdue.length && !b.failures.length && !b.suspended.length;
  return (
    <Group title="风险与例外" foot={`你不审批每一件事，只看例外：风险类决策谁在办、等了多久；超过 ${b.overdue_hours} 小时没处理的；Agent 没准备成的；依据变了正在挂起复核的能力。只给标题与归属。`}>
      {b.risk.map((r) => line(r))}
      {b.overdue.filter((r) => !b.risk.some((x) => x.id === r.id)).map((r) => line(r, "超期"))}
      {b.failures.map((r) => line(r, `Agent 没准备成：${r.error}`))}
      {b.suspended.map((c) => <div key={c.id} className="row text-[12.5px]"><span className="w-[86px] shrink-0"><span className="tag tag-danger">挂起复核</span></span>
        <span className="min-w-0 flex-1">{FORM[c.form] ?? c.form}{c.product && ` · ${c.product}`} · {L.name(c.granted_by)}签出；挂起期间不再用于推荐，复核由{L.name(c.granted_by)}看本次原文后签字</span></div>)}
      {b.frozen.length > 0 && <div className="row text-[12.5px] text-ink-2">已冻结上层知识检索：{b.frozen.map(L.name).join("、")}</div>}
      {empty && <div className="row text-ink-2">现在没有风险与例外</div>}
    </Group>
  );
}

function Lineage() {
  const { me } = useApp();
  const L = useLabels();
  const rows = useData(() => api.lineage(me), [me]) ?? [];
  const [all, setAll] = useState(false);
  const shown = rows.filter((r) => all || !r.seed);
  return (
    <Group title="能力谱系" aside={<button className="text-[12px] text-accent" onClick={() => setAll(!all)}>{all ? "只看新签的" : `含种子里的 ${rows.filter((r) => r.seed).length} 项`}</button>}
           foot="每项能力从哪几条结论来、谁确认、谁授予与批准、用过几次（其中几单在进研发之前就答了）、经历过什么变化。研发层的能力你只看到产品与归属。">
      {shown.map((r) => {
        const changed = r.status === "suspended" || r.status === "revoked";
        return <div key={r.id} className={`row !items-start text-[12.5px] ${changed ? "bg-red-50" : ""}`}>
          <span className="w-[96px] shrink-0"><span className="tag tag-accent">{FORM[r.form] ?? r.form}</span> {typeof r.audience === "number" ? `L${r.audience}` : "指定客户"}</span>
          <span className="min-w-0 flex-1">
            {[r.product_id && L.product(r.product_id), r.phenomenon && L.phen(r.phenomenon)].filter(Boolean).join(" · ") || "—"}
            {r.payload?.text && `「${L.scrub(r.payload.text)}」`}
            <span className="block text-ink-2">依据 {r.basis.length} 条结论（{[...new Set(r.basis.map((u) => L.name(u.confirmed_by ?? u.owner)))].join("、")}确认）
              {r.docs.length > 0 && `，出自 ${r.docs.length} 份来源`} · {L.name(r.granted_by)}授予{r.approved_by && r.approved_by !== "seed" && ` · ${L.name(r.approved_by)}批准`}</span>
            {r.changes.length > 0 && <span className="block text-danger">{r.changes.map((x) => `${x.ts.slice(5, 16).replace("T", " ")} ${CHANGE[x.kind] ?? x.kind}`).join(" → ")}
              {changed && r.used > 0 && `；受影响 ${r.used} 段会话`}</span>}
          </span>
          <span className="shrink-0 text-right"><span className={r.status === "active" ? "text-ok" : changed ? "text-danger" : "text-ink-2"}>{STATUS[r.status] ?? r.status}</span>
            <span className="block text-ink-2">用过 {r.used} 次{r.answered_for_rd > 0 && ` · 替研发答 ${r.answered_for_rd} 单`}</span></span>
        </div>;
      })}
      {!shown.length && <div className="row text-ink-2">这一局还没有新签的能力</div>}
    </Group>
  );
}
