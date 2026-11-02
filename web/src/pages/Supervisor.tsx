// 主管：收件箱处理泄露风险待签卡（业务员、证据计数，「冻结上层知识检索」/「现在不需要」）；v8 Q9.8 下方列出已冻结的人，可解冻。
// V11.3 研发负责人掌握进展：侧栏「进展」列出全部需求单，点开看这件事的前情和现在在等谁。
import { useState } from "react";
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
      </div>
    </>
  );
}
