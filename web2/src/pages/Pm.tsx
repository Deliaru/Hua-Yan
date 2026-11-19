// 产品经理子工作面（L2，v6 REPLAN 0.2）：真人产品经理不回到每张单上，只做三件只有人能做的事——
// 维护产品适用范围（scope_update）、判断产品机会（opportunity，签字附商业判断）、纠正研发退回的需求（例外纠偏 + 沉淀）。
// 逐单 L2 转译由产品经理 Agent 在后台完成，这里只读显示「无需你转述」。
import { useEffect, useState } from "react";
import { HuayanFeed, ImSide } from "../components/Im";
import { api } from "../api";
import { REQ_STATUS, Side, useApp, useData, useLabels } from "../ctx";
import type { Question, RequirementView } from "../types";
import { RouteStrip, WorkloadCard } from "../components/Route";
import { Backstory } from "../components/Backstory";
import { Narration, TimeBar } from "../components/Narration";
import { RelayLoss } from "../components/RelayLoss";
import { useGuideArg } from "../components/Guide";
import { Act, AgentMark, EmptyState, Field, Group, SideHead } from "../components/ui";
import { Md } from "../components/Md";
import { More, TaskHead, useAsk, useObject } from "../components/Task";

const GROUPS: [string, string, (q: Question) => boolean][] = [
  ["适用范围", "研发判过「现成产品能用」", (q) => q.family === "scope_update"],
  ["产品机会", "几位客户的同类需求", (q) => q.family === "opportunity"],
  ["说明书跟上研发", "研发判断超出说明书", (q) => q.family === "sheet_mismatch"],
  ["研发退回的", "研发退回的需求", (q) => q.family === "accept_requirement" || q.family === "contribution_pm"],
];
const reqOf = (q: Question) => q.refs.requirement_id ?? (q.refs.requirement_ids ?? "").split(",").filter(Boolean)[0] ?? null;
// 为什么到你这：适用范围写明是哪款产品、哪个现象；其余用决策类型的通用说法
const whyOf = (q: Question, L: ReturnType<typeof useLabels>) => q.family === "scope_update"
  ? `研发判过 ${L.product(q.refs.product_id)} 能解决「${L.phen(q.refs.phenomenon)}」，说明书还没写这种用法。` : undefined;
// V9.6：适用范围问题的对象是待批准的适用能力（knowledge:cap:<id>），产品、现象、条件与限制原文在 refs 里
const scopeOf = (q: Question) => ({ product: q.refs.product_id, phenomenon: q.refs.phenomenon,
  conditions: JSON.parse(q.refs.conditions || "{}") as Record<string, string[]>, limits: q.refs.limits ?? "",
  temperature: JSON.parse(q.refs.temperature_c || "null") as [number, number] | null });

export function Pm() {
  const { me, focus, notes } = useApp();
  const L = useLabels();
  const ask = useAsk();
  const qs = useData(() => api.questions(me), [me]) ?? [];
  const reqs = (useData(() => api.requirements(me), [me]) ?? []).slice().reverse();
  const object = useObject(reqs);
  const [qid, setQid] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);   // 刚签完的那项：问题已结案，主区显示签字的效果
  useEffect(() => { if (focus) { const q = qs.find((x) => x.id === focus || reqOf(x) === focus); if (q) { setQid(q.id); setDone(null); } } }, [focus, qs.length]);
  const q = qs.find((x) => x.id === qid) ?? null;   // 不自己打开：化言推到左边消息里，点了才开
  const mineReqs = new Set(qs.map(reqOf));
  const background = reqs.filter((r) => r.status === "draft" && !mineReqs.has(r.id));
  return (
    <>
      <Side>
        <ImSide badge={qs.filter((x) => x.prepared_at != null).length} feed={<HuayanFeed selected={q?.id ?? null} reqs={reqs}
          select={(x) => { setQid(x.id); setDone(null); }} />} desk={<>
        {GROUPS.map(([title, sub, pick]) => {
          const items = qs.filter(pick);
          return (
            <div key={title}>
              <SideHead aside={!!items.length && <span className="num text-attn-ink">{items.length}</span>}>{title}</SideHead>
              {items.map((x) => (
                <button key={x.id} onClick={() => { setQid(x.id); setDone(null); }} className={`side-row ${x.id === q?.id ? "on" : ""}`}>
                  <p className="truncate text-[13px] font-semibold">{ask(x)}</p>
                  <p className="truncate text-[12px] text-ink-2">{object(x)}{!x.prepared_at && x.owner_id !== me && " · Agent 在准备"}</p>
                </button>
              ))}
              {!items.length && <p className="px-[18px] py-1 text-[12.5px] text-ink-3">无 · {sub}</p>}
            </div>
          );
        })}
        <SideHead>Agent 在后台写需求</SideHead>
        {background.map((r) => (
          <div key={r.id} className="px-[18px] py-1.5">
            <p className="truncate text-[13px]">{L.phen(r.phenomenon)}</p>
            <p className="text-[12px] text-ink-3">{r.customer_ids.map(L.name).join("、")} · 无需你转述</p>
          </div>
        ))}
        {!background.length && <p className="px-[18px] py-1 text-[12.5px] text-ink-3">无</p>}
        </>} />
      </Side>
      <div className="mr-[372px]">
        <div className="mx-auto flex max-w-[1000px] flex-col gap-5 px-8 pb-24 pt-7">
          {done && <DoneBanner text={done} />}
          {q ? <Pane key={q.id} q={q} onDone={(t) => { setDone(t); setQid(null); }} />
            : !done && <EmptyState title={qs.length ? "在左边化言的消息里点「去处理」" : "现在没有要你定的事"} text="逐单转述由产品经理 Agent 在后台做。你只处理几类事：扩大产品的适用范围、判断产品机会、更新说明书、纠正研发退回的需求。有了会出现在左边。" />}
        </div>
      </div>
      <aside className="inspector fixed bottom-0 right-0 top-[52px] z-10 flex w-[372px] flex-col overflow-y-auto border-l border-sep">
        <div className="col-head"><span className="col-no">3</span>你的时间去哪了<span className="col-sub">岗位视角</span></div>
        <div className="flex flex-col gap-5 px-5 py-5">
        <TimeBar />
        <RelayLoss />
        <WorkloadCard title="你的判断产生了什么" />
        {!notes && <p className="text-[12.5px] leading-5 text-ink-3">你的判断让多少需求不再进研发，可以在工具栏打开「演示说明」查看。</p>}
        </div>
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
  const { notes } = useApp();
  const head = <TaskHead q={q} why={whyOf(q, L)} />;
  if (q.prepared_at == null && q.owner_id !== me) {
    return <>{head}<Group><div className="row text-[14px] text-ink-2">产品经理 Agent 正在准备，好了就能定。</div></Group></>;
  }
  return (
    <>
      {head}
      {q.family === "scope_update" && <Scope q={q} onDone={onDone} />}
      {q.family === "opportunity" && <Opportunity q={q} onDone={onDone} />}
      {q.family === "sheet_mismatch" && <SheetRevision q={q} onDone={onDone} />}
      {q.family === "accept_requirement" && view && <Correct q={q} view={view} onDone={onDone} />}
      {q.family === "contribution_pm" && view && <Contribute view={view} onDone={onDone} />}
      {rid && <More items={[
        ["前情", <Backstory id={rid} />, true],
        ["旁白", <Narration id={rid} />, notes],
        ["流转", <RouteStrip objectId={rid} />, notes],
      ]} />}
    </>
  );
}

// V12.7 说明书跟上研发判断：觉发现研发签出的适用超出说明书，产品经理 Agent 起草补充句，产品经理签字后接进说明书，客户层随即看到
function SheetRevision({ q, onDone }: { q: Question; onDone: (t: string) => void }) {
  const { me } = useApp();
  const L = useLabels();
  const draft = useData(() => api.sheetRevision(q.id, me), [q.id, me]);
  const [text, setText] = useState<string | null>(null);
  const value = text ?? draft?.text ?? "";
  return (
    <>
      <Group title="研发判断超出说明书的地方">
        <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">产品</span>
          <span className="text-[15px] font-semibold">{L.product(q.refs.product_id)}</span></div>
        <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">现象</span><span className="text-[14px]">{L.phen(q.refs.phenomenon)}</span></div>
        <div className="row !items-start"><span className="w-20 shrink-0 text-[13px] text-ink-2">超出</span>
          <span className="text-[14px] leading-[21px]">{q.refs.beyond}</span></div>
      </Group>
      <Group title="签字：更新说明书" foot="补充句接在说明书后面，客户层随即看到；只写对外可说的适用条件与工艺，含保密内容会被拒绝。">
        <div className="row !items-start">
          <div className="flex flex-1 flex-col gap-2">
            {draft?.by && <p className="text-[12.5px] text-ink-2"><AgentMark who="产品经理 Agent 起草，可以直接改" /></p>}
            <Field value={value} onChange={setText} rows={3} placeholder="例如：经试样确认，涤纶在汽流染色机上 133℃ 保温 30min 匀染良好。" />
            <div className="flex gap-2">
              <Act label="更新说明书" disabled={!value.trim()} run={() => api.resolve(q.id, "update_sheet", me, value).then(() =>
                onDone(`已更新 ${L.product(q.refs.product_id)} 的说明书，客户层看到的说明书与研发判断一致了。`))} />
              <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me).then(() => onDone("这次不改说明书。"))} />
            </div>
          </div>
        </div>
      </Group>
    </>
  );
}

// ① 维护产品适用范围：研发判一次，产品经理把它变成产品边界
function Scope({ q, onDone }: { q: Question; onDone: (t: string) => void }) {
  const { me } = useApp();
  const L = useLabels();
  const s = scopeOf(q);
  const rids = (q.refs.requirement_ids ?? "").split(",").filter(Boolean);
  const views = useData(() => Promise.all(rids.map((id) => api.requirement(id, me))), [rids.join(","), me]) ?? [];
  const routes = useData(() => Promise.all(rids.map((id) => api.route(id, me))), [rids.join(","), me]) ?? [];
  const judged = routes.flatMap((r) => r.basis.filter((b) => b.family === "accept_requirement" && b.note).map((b) => [b.by, b.note] as const));
  const [note, setNote] = useState("");
  const scripted = useGuideArg("scope");   // 演示讲解：签字的依据，由「演示自动填入」填好
  return (
    <>
      <Group title="研发的判断">
        <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">产品</span>
          <span className="text-[15px] font-semibold">{L.product(s.product)}</span></div>
        <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">现象</span>
          <span className="text-[15px]">{L.phen(s.phenomenon)}</span><span className="ml-2 text-[12px] text-ink-3">说明书的适用范围里还没有</span></div>
        <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">试过的条件</span>
          <span className="text-[14px]">{Object.entries(s.conditions).map(([k, v]) => `${L.slot(k)} ${v.join("、")}`).join("；") || "没限定"}</span></div>
        {s.temperature && <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">适用温度</span>
          <span className="text-[14px]">{s.temperature[0] === s.temperature[1] ? s.temperature[0] : s.temperature.join("—")}℃</span></div>}
        {s.limits && <div className="row !items-start"><span className="w-20 shrink-0 text-[13px] text-ink-2">研发写的限制</span>
          <span className="text-[14px] leading-[21px]">「{s.limits}」<span className="ml-1 text-[12px] text-ink-3">有限制的，客户自助时不会自动推荐，仍交研发对照</span></span></div>}
        {judged.map(([by, n], i) => (
          <div key={i} className="row !items-start"><span className="w-20 shrink-0 text-[13px] text-ink-2">{L.name(by)}</span>
            <span className="text-[14px] leading-[21px]">不立项：{n}</span></div>
        ))}
      </Group>
      {views.some((v) => Object.keys(v.quotes).length) && <Group title="客户原话">
        {views.flatMap((v) => Object.entries(v.quotes)).map(([id, t]) => <div key={id} className="row text-[14px]">「{t}」</div>)}
      </Group>}
      <Group title="签字：扩大适用范围" foot="批准后，条件相同的客户自己就能查到这款产品；温度没说的会先问，超出范围的仍交研发。">
        <div className="row !items-start">
          <div className="flex flex-1 flex-col gap-2">
            <Field value={note} onChange={setNote} rows={2} placeholder="为什么同意（必填）：例如研发试样确认适用，条件和说明书一致" />
            {scripted && note !== scripted && <div><button type="button" className="chip glow" onClick={() => setNote(scripted)}>演示自动填入</button></div>}
            <div className="flex gap-2">
              <Act label="扩大适用范围" disabled={!note.trim()} glow={!!scripted && note === scripted} run={() => api.extendScope(q.id, note, me).then(() =>
                onDone(`已批准 ${L.product(s.product)} 的「${L.phen(s.phenomenon)}」适用情境；后续需求按完整条件匹配。`))} />
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
  const scripted = useGuideArg("merge");   // 演示讲解：签字的商业判断，由「演示自动填入」填好
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
            <div className="flex-1 text-[13px] leading-5"><Md text={main.requirement.merge_note} /><AgentMark who="产品经理 Agent 起草" /></div></div>
        )}
        {q.evidence.map((e, i) => <div key={i} className="row text-[12.5px] text-ink-2">{L.scrub(e.summary)}</div>)}
      </Group>
      <Group title="签字：作为一个课题交研发" foot="立项 = 你的商业判断 + 研发的技术判断。你的判断随合并单交给研发，研发只收到一张单。">
        <div className="row !items-start">
          <div className="flex flex-1 flex-col gap-2">
            <Field value={note} onChange={setNote} rows={3} placeholder="商业判断（必填）：市场与客户、值不值得做、产品方向" />
            {scripted && note !== scripted && <div><button type="button" className="chip glow" onClick={() => setNote(scripted)}>演示自动填入</button></div>}
            <div className="flex gap-2">
              <Act label="合并为一个课题" disabled={!note.trim()} glow={!!scripted && note === scripted} run={() => api.merge(q.id, me, note).then(() =>
                onDone(`已合并为一个课题交研发，附你的商业判断。研发收件箱只有一张单——切到研发看。`))} />
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
