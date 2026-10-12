// 产品经理子工作面（L2，v6 REPLAN 0.2）：真人产品经理不回到每张单上，只做三件只有人能做的事——
// 维护产品适用范围（scope_update）、判断产品机会（opportunity，签字附商业判断）、纠正研发退回的需求（例外纠偏 + 沉淀）。
// 逐单 L2 转译由产品经理 Agent 在后台完成，这里只读显示「无需你转述」。
import { useEffect, useState } from "react";
import { api } from "../api";
import { REQ_STATUS, Side, useApp, useData, useLabels } from "../ctx";
import type { Question, RequirementView } from "../types";
import { RouteStrip, WorkloadCard } from "../components/Route";
import { Act, AgentMark, EmptyState, Field, Group, PageHead, Score, SideHead, LayerNote } from "../components/ui";

const GROUPS: [string, string, (q: Question) => boolean][] = [
  ["适用范围待定", "研发判过「已有产品适用」", (q) => q.family === "scope_update"],
  ["产品机会", "几位客户的同类需求", (q) => q.family === "opportunity"],
  ["待纠偏", "研发退回的需求", (q) => q.family === "accept_requirement" || q.family === "contribution_pm"],
];
const reqOf = (q: Question) => q.refs.requirement_id ?? (q.refs.requirement_ids ?? "").split(",").filter(Boolean)[0] ?? null;
const scopeOf = (q: Question) => {
  const m = q.object_id.match(/^knowledge:([^|]+)\|phenomenon=(.+)$/);
  return m ? { product: m[1], phenomenon: m[2] } : null;
};

export function Pm() {
  const { me, focus } = useApp();
  const L = useLabels();
  const qs = useData(() => api.questions(me), [me]) ?? [];
  const reqs = (useData(() => api.requirements(me), [me]) ?? []).slice().reverse();
  const [qid, setQid] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);   // 刚签完的那项：问题已结案，主区显示签字的效果
  useEffect(() => { if (focus) { const q = qs.find((x) => reqOf(x) === focus); if (q) setQid(q.id); } }, [focus, qs.length]);
  const q = qs.find((x) => x.id === qid) ?? (done ? null : qs.find((x) => x.prepared_at != null || x.owner_id === me) ?? null);
  const mineReqs = new Set(qs.map(reqOf));
  const background = reqs.filter((r) => r.status === "draft" && !mineReqs.has(r.id));
  return (
    <>
      <Side>
        {GROUPS.map(([title, sub, pick]) => {
          const items = qs.filter(pick);
          return (
            <div key={title}>
              <SideHead aside={!!items.length && <span className="num text-attn-ink">{items.length}</span>}>{title}</SideHead>
              {items.map((x) => (
                <button key={x.id} onClick={() => { setQid(x.id); setDone(null); }} className={`side-row ${x.id === q?.id ? "on" : ""}`}>
                  <p className="flex items-center gap-1.5"><span className={`tag ${x.prepared_at ? "tag-attn" : ""}`}>{L.family(x.family)}</span>
                    {!x.prepared_at && x.owner_id !== me && <span className="text-[12px] text-ink-3">Agent 准备中</span>}</p>
                  <p className="mt-1 truncate text-[13px] font-semibold">{L.scrub(x.title)}</p>
                </button>
              ))}
              {!items.length && <p className="px-[18px] py-1 text-[12.5px] text-ink-3">无 · {sub}</p>}
            </div>
          );
        })}
        <SideHead>Agent 后台转译中</SideHead>
        {background.map((r) => (
          <div key={r.id} className="px-[18px] py-1.5">
            <p className="truncate text-[13px]">{L.phen(r.phenomenon)}</p>
            <p className="text-[12px] text-ink-3">{r.customer_ids.map(L.name).join("、")} · 无需你转述</p>
          </div>
        ))}
        {!background.length && <p className="px-[18px] py-1 text-[12.5px] text-ink-3">无</p>}
      </Side>
      <div className="mr-[372px]">
        <div className="mx-auto flex max-w-[1000px] flex-col gap-5 px-8 pb-24 pt-7">
          {done && <DoneBanner text={done} />}
          {q ? <Pane key={q.id} q={q} onDone={(t) => { setDone(t); setQid(null); }} />
            : !done && <EmptyState title="产品经理不再逐单转述" text="逐单的 L2 转译由产品经理 Agent 在后台完成。你只处理三类事：扩展产品适用范围、判断产品机会、纠正研发退回的需求。它们由觉提出，出现在左侧。" />}
        </div>
      </div>
      <aside className="inspector fixed bottom-0 right-0 top-[52px] z-10 flex w-[372px] flex-col gap-5 overflow-y-auto border-l border-sep px-5 py-5">
        <WorkloadCard title="你的判断产生了什么" />
      </aside>
    </>
  );
}

function DoneBanner({ text }: { text: string }) {
  return <p className="anim-fade rounded-[10px] bg-[rgba(48,194,91,.11)] px-4 py-3 text-[14px] leading-[22px] text-[#1d6b34]">✓ {text}</p>;
}

function Pane({ q, onDone }: { q: Question; onDone: (text: string) => void }) {
  const { me } = useApp();
  const L = useLabels();
  const rid = reqOf(q);
  const view = useData(() => (rid ? api.requirement(rid, me) : Promise.resolve(null)), [rid, me]);
  const head = (
    <PageHead title={L.scrub(q.title)} subtitle={<span className="flex items-center gap-2">{L.family(q.family)}<Score q={q} /></span>} />
  );
  if (q.prepared_at == null && q.owner_id !== me) {
    return <>{head}<Group><div className="row text-[14px] text-ink-2">产品经理 Agent 正在准备，准备好后在这里签字。</div></Group></>;
  }
  return (
    <>
      {head}
      <LayerNote layer={2}>你在 L2：看得到产品需求与归属，研发的化学要点与封存项只显示「谁懂」、不显示原文。</LayerNote>
      {rid && <RouteStrip objectId={rid} />}
      {q.family === "scope_update" && <Scope q={q} onDone={onDone} />}
      {q.family === "opportunity" && <Opportunity q={q} onDone={onDone} />}
      {q.family === "accept_requirement" && view && <Correct q={q} view={view} onDone={onDone} />}
      {q.family === "contribution_pm" && view && <Contribute view={view} onDone={onDone} />}
    </>
  );
}

// ① 维护产品适用范围：研发判一次，产品经理把它变成产品边界
function Scope({ q, onDone }: { q: Question; onDone: (t: string) => void }) {
  const { me } = useApp();
  const L = useLabels();
  const s = scopeOf(q)!;
  const rids = (q.refs.requirement_ids ?? "").split(",").filter(Boolean);
  const views = useData(() => Promise.all(rids.map((id) => api.requirement(id, me))), [rids.join(","), me]) ?? [];
  const routes = useData(() => Promise.all(rids.map((id) => api.route(id, me))), [rids.join(","), me]) ?? [];
  const judged = routes.flatMap((r) => r.basis.filter((b) => b.family === "accept_requirement" && b.note).map((b) => [b.by, b.note] as const));
  const [note, setNote] = useState("");
  return (
    <>
      <Group title="研发的判断">
        <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">产品</span>
          <span className="text-[15px] font-semibold">{L.product(s.product)}</span></div>
        <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">现象</span>
          <span className="text-[15px]">{L.phen(s.phenomenon)}</span><span className="ml-2 text-[12px] text-ink-3">说明书的适用范围里还没有</span></div>
        {judged.map(([by, n], i) => (
          <div key={i} className="row !items-start"><span className="w-20 shrink-0 text-[13px] text-ink-2">{L.name(by)}</span>
            <span className="text-[14px] leading-[21px]">不立项：{n}</span></div>
        ))}
      </Group>
      <Group title="客户原话">
        {views.flatMap((v) => Object.entries(v.quotes)).map(([id, t]) => <div key={id} className="row text-[14px]">「{t}」</div>)}
      </Group>
      <Group title="签字：扩展适用范围" foot="签字后写进该产品的适用范围，并作为你名下的 L2 知识；此后同类需求在客户自助阶段就命中，被引用时给你记分。">
        <div className="row !items-start">
          <div className="flex flex-1 flex-col gap-2">
            <Field value={note} onChange={setNote} rows={2} placeholder="依据（必填）：例如研发判定适用、适用条件与说明书一致" />
            <div className="flex gap-2">
              <Act label="扩展适用范围" disabled={!note.trim()} run={() => api.extendScope(q.id, note, me).then(() =>
                onDone(`已把「${L.phen(s.phenomenon)}」加进 ${L.product(s.product)} 的适用范围。此后同类需求在客户自助阶段就直接得到推荐，研发不再收到这类单——去客户子工作面开 C′ 看。`))} />
              <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me)} />
            </div>
          </div>
        </div>
      </Group>
    </>
  );
}

// ② 判断产品机会：几位客户的原话并排，签字必须写商业判断，随合并单交研发
function Opportunity({ q, onDone }: { q: Question; onDone: (t: string) => void }) {
  const { me } = useApp();
  const L = useLabels();
  const rids = (q.refs.requirement_ids ?? "").split(",").filter(Boolean);
  const views = useData(() => Promise.all(rids.map((id) => api.requirement(id, me))), [rids.join(","), me]) ?? [];
  const [note, setNote] = useState("");
  const main = views.find((v) => v.requirement.merge_from.length) ?? views[0];
  return (
    <>
      <Group title={`${views.length} 位客户、同类需求`}>
        <div className="row !items-stretch gap-3">
          {views.map((v, n) => (
            <div key={v.requirement.id} className="min-w-0 flex-1 rounded-[8px] bg-bg px-3 py-2">
              <p className="text-[12px] font-semibold text-ink-2">客户 {n + 1}</p>
              {Object.values(v.quotes).map((t, j) => <p key={j} className="text-[13.5px] leading-5">「{t}」</p>)}
            </div>
          ))}
        </div>
        {main?.requirement.merge_note && (
          <div className="row !items-start"><span className="w-24 shrink-0 text-[13px] text-ink-2">是不是同一件事</span>
            <p className="flex-1 text-[13px] leading-5">{main.requirement.merge_note} <AgentMark who="产品经理 Agent 起草" /></p></div>
        )}
        {q.evidence.map((e, i) => <div key={i} className="row text-[12.5px] text-ink-2">{L.scrub(e.summary)}</div>)}
      </Group>
      <Group title="签字：作为一个课题交研发" foot="立项 = 你的商业判断 + 研发的技术判断。你的判断随合并单交给研发，研发只收到一张单。">
        <div className="row !items-start">
          <div className="flex flex-1 flex-col gap-2">
            <Field value={note} onChange={setNote} rows={3} placeholder="商业判断（必填）：市场与客户、值不值得做、产品方向" />
            <div className="flex gap-2">
              <Act label="合并为一个课题" disabled={!note.trim()} run={() => api.merge(q.id, me, note).then(() =>
                onDone(`已合并为一个课题交研发，附你的商业判断。研发收件箱只有一张单——切到研发看。`))} />
              <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me)} />
            </div>
          </div>
        </div>
      </Group>
    </>
  );
}

// ③ 纠正研发退回的需求：直接改 L2 条目，改完交研发
function Correct({ q, view, onDone }: { q: Question; view: RequirementView; onDone: (t: string) => void }) {
  const { me } = useApp();
  const req = view.requirement;
  return (
    <>
      <Group title="研发退回的理由">
        {req.return_notes.map((n, i) => <div key={i} className="row attn-edge text-[14px]">{n}</div>)}
      </Group>
      <Group title="产品需求（L2）" aside={REQ_STATUS[req.status]} foot="直接改有问题的条目；改过的条目可沉淀为你名下的知识，下次产品经理 Agent 转译会引用。">
        {req.product_lang.map((it, i) => <Item key={i} reqId={req.id} index={i} item={it} quotes={view.quotes} />)}
      </Group>
      <div className="flex gap-2">
        <Act label="修改完成，交研发" run={() => api.prepared(q.id, me).then(() => onDone("已交回研发接单。觉随后会问你是否把这次修正沉淀为知识。"))} />
      </div>
    </>
  );
}

function Item({ reqId, index, item, quotes }: { reqId: string; index: number; item: RequirementView["requirement"]["product_lang"][number]; quotes: Record<string, string> }) {
  const { me } = useApp();
  const L = useLabels();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.text);
  return (
    <div className="row !items-start">
      <span className="num w-5 shrink-0 pt-[2px] text-[13px] text-ink-3">{index + 1}</span>
      <div className="min-w-0 flex-1">
        {editing ? (
          <div className="flex flex-col gap-1.5">
            <Field value={text} onChange={setText} rows={2} label={`第 ${index + 1} 条`} />
            <span className="flex gap-2">
              <Act label="保存" run={() => api.editItem(reqId, index, { ...item, text }, me).then(() => setEditing(false))} />
              <button type="button" className="btn btn-quiet" onClick={() => { setText(item.text); setEditing(false); }}>取消</button>
            </span>
          </div>
        ) : <p className="text-[14px] leading-[21px]">{item.text}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ink-2">
          {item.edited_by == null ? <AgentMark who="产品经理 Agent 起草" /> : <span>{L.name(item.edited_by)} 修改</span>}
          {item.quote_refs.map((r) => <span key={r} className="text-ink-3">←「{quotes[r]}」</span>)}
          {!editing && <button type="button" className="link !text-[12px]" onClick={() => setEditing(true)}>修改</button>}
        </p>
      </div>
    </div>
  );
}

// 纠偏沉淀：本人改过的条目，写成「场景说法 → 产品需求说法」
function Contribute({ view, onDone }: { view: RequirementView; onDone: (t: string) => void }) {
  const { me } = useApp();
  const req = view.requirement;
  const mine = req.product_lang.map((it, i) => ({ it, i })).filter(({ it }) => it.edited_by === me && !it.ku_refs.some((r) => r.includes(":l2:")));
  return (
    <Group title="把你的修正沉淀为知识" foot="沉淀为你名下的 L2 转化知识；产品经理 Agent 下次转译同类需求会引用它，被引用时给你记分。">
      {mine.map(({ it, i }) => <ContributeRow key={i} reqId={req.id} index={i} text={it.text} quote={it.quote_refs.map((r) => view.quotes[r]).join("；")} onDone={onDone} />)}
      {!mine.length && <div className="row text-[13px] text-ink-2">没有待沉淀的条目</div>}
    </Group>
  );
}

function ContributeRow({ reqId, index, text, quote, onDone }: { reqId: string; index: number; text: string; quote: string; onDone: (t: string) => void }) {
  const { me } = useApp();
  const [scene, setScene] = useState(quote);
  const [term, setTerm] = useState(text);
  return (
    <div className="row !items-start">
      <div className="flex flex-1 flex-col gap-1.5">
        <p className="text-[12px] text-ink-2">第 {index + 1} 条</p>
        <Field value={scene} onChange={setScene} rows={1} label="客户的说法" />
        <Field value={term} onChange={setTerm} rows={2} label="产品需求说法" />
        <div><Act label="沉淀为我的知识" disabled={!scene.trim() || !term.trim()}
                  run={() => api.contributeL2(reqId, index, scene, term, me).then(() => onDone("已沉淀为你名下的 L2 知识。"))} /></div>
      </div>
    </div>
  );
}
