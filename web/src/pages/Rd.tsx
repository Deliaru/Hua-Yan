// 研发工作面（L3）：左侧收件箱（侧栏），中间是签字区与三栏需求单（客户原话 / 产品需求 / 化学语言），右侧 Agent 协作。
// 按钮就是签字，直接调门面原子方法；可签条件由门面判断，拒绝时在按钮旁显示门面给的原因。
import { useEffect, useState } from "react";
import { api } from "../api";
import { REQ_STATUS, Side, useApp, useData, useLabels } from "../ctx";
import type { AgentMessage, CitedKnowledge, LeakHit, Question, ReqItem, RequirementView } from "../types";
import { AgentPanel, Notes, PendingActions, notesFor, useConversation } from "../components/Agent";
import { InboxSidebar, ownerText, useInbox } from "../components/Inbox";
import { Act, AgentMark, Disclosure, EmptyState, Field, Group, Marked, PageHead, Score, SideHead } from "../components/ui";

// 选中一项决策即打开它所说的需求单；也可以从侧栏直接打开需求单
export function Rd() {
  const { me } = useApp();
  const L = useLabels();
  const { all, ready } = useInbox();
  const reqs = (useData(() => api.requirements(me), [me]) ?? []).slice().reverse();
  const [qid, setQid] = useState<string | null>(null);
  const [chosenReq, setChosenReq] = useState<string | null>(null);
  const question = all.find((q) => q.id === qid) ?? (chosenReq ? null : ready[0] ?? null);
  const reqId = question?.refs.requirement_id ?? chosenReq ?? reqs[0]?.id ?? null;
  return (
    <>
      <Side>
        <InboxSidebar selected={question?.id ?? null} reqs={reqs} select={(q) => { setQid(q.id); setChosenReq(null); }} />
        <SideHead>需求单</SideHead>
        {reqs.map((r) => (
          <button key={r.id} onClick={() => { setChosenReq(r.id); setQid(null); }}
                  className={`side-row ${!question && r.id === reqId ? "on" : ""}`}>
            <p className="text-[13px] font-semibold">{L.phen(r.phenomenon)}</p>
            <p className="text-[12px] text-ink-2">{REQ_STATUS[r.status]}</p>
          </button>
        ))}
        {!reqs.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">暂无需求单</p>}
      </Side>
      <RdDesk question={question} reqId={reqId} />
    </>
  );
}

function RdDesk({ question, reqId }: { question: Question | null; reqId: string | null }) {
  const { me } = useApp();
  const view = useData(() => (reqId ? api.requirement(reqId, me) : Promise.resolve(null)), [reqId, me]);
  const conv = useConversation(null);
  return (
    <>
      <div className="mr-[372px]">
        <div className="mx-auto flex max-w-[1080px] flex-col gap-6 px-8 pb-24 pt-7">
          <PendingActions />
          {question && <SignArea key={question.id} q={question} view={view} />}
          {view ? <RequirementDesk view={view} notes={conv?.messages ?? []} />
            : !question && <EmptyState title="选一项待签的决策" text="收件箱里是觉提出、由你签字的决策；准备中的由产品经理 Agent 或你的 Agent 在起草。" />}
        </div>
      </div>
      <AgentPanel title="需求单来历" sessionId={null} focus={reqId}>
        {view && <ReqContext view={view} />}
      </AgentPanel>
    </>
  );
}

// ── 需求单：三栏并排 ───────────────────────────────────────
function RequirementDesk({ view, notes }: { view: RequirementView; notes: AgentMessage[] }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const cited = Object.fromEntries(view.cited.map((c) => [c.ku_id, c]));
  return (
    <>
      <PageHead title={L.phen(req.phenomenon)}
                subtitle={[`需求单 · ${REQ_STATUS[req.status]}`, `接单研发 ${L.name(req.assigned_rd)}`,
                  req.product_id && `关联产品 ${L.product(req.product_id)}`].filter(Boolean).join(" · ")}
                aside={req.status === "rd_confirmed" && (
                  <span className="flex gap-2">
                    <Act kind="plain" label="录入试样：通过（模拟 ELN）" run={() => api.trial(req.id, "pass", me)} />
                    <Act kind="quiet" label="不通过" run={() => api.trial(req.id, "fail", me)} />
                  </span>
                )} />
      <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] items-start gap-4">
        <Group title="客户原话">
          {Object.entries(view.quotes).map(([id, text]) => (
            <div key={id} className="row !items-start text-[13px] leading-5">「{text}」</div>
          ))}
          {!Object.keys(view.quotes).length && <div className="row text-[13px] text-ink-2">无</div>}
        </Group>
        <Group title="产品需求 · L2"
               foot={`产品经理 Agent 起草 · ${req.rd_accepted_by ? `${L.name(req.rd_accepted_by)} 已接单` : "研发接单后生效"}`}>
          {req.direction && <div className="row text-[14px] font-semibold leading-[21px]">{req.direction}</div>}
          {req.product_lang.map((it, i) => (
            <Item key={i} reqId={req.id} index={i} item={it} view={view} cited={cited} editable={false}
                  notes={notesFor(notes, `${req.id}/product/${i}`)} />
          ))}
          {!req.product_lang.length && <div className="row text-[13px] text-ink-2">产品经理 Agent 尚未起草</div>}
        </Group>
        <Group title="化学语言 · L3" foot={req.rd_confirmed_by ? `${L.name(req.rd_confirmed_by)} 已确认转译` : undefined}>
          {req.chem_lang.map((it, i) => (
            <Item key={i} reqId={req.id} index={i} item={it} view={view} cited={cited}
                  editable={req.status === "rd_accepted"} notes={notesFor(notes, `${req.id}/chem/${i}`)} />
          ))}
          {!req.chem_lang.length && <div className="row text-[13px] text-ink-2">接单后由你的 Agent 起草</div>}
          {!!req.hypotheses.length && (
            <div className="row !items-start">
              <div className="min-w-0">
                <p className="text-[12px] text-ink-2">方向假设</p>
                {req.hypotheses.map((h) => <p key={h} className="text-[13px] leading-5">{h}</p>)}
              </div>
            </div>
          )}
        </Group>
      </div>
      {(req.public_points || !!req.sealed.length) && (
        <div className="grid grid-cols-2 gap-4">
          <Group title="已放出的对外要点"><div className="row text-[14px] leading-[21px]">{req.public_points || "—"}</div></Group>
          <Group title="已封存（只有研发可见）">
            {req.sealed.map((s) => <div key={s} className="row text-[14px]">{s}</div>)}
            {!req.sealed.length && <div className="row text-[13px] text-ink-2">无</div>}
          </Group>
        </div>
      )}
    </>
  );
}

function Basis({ c }: { c: CitedKnowledge }) {
  const L = useLabels();
  const head = <><span className="text-ink">{L.name(c.owner)}</span> · {c.text == null ? `L${c.level} 知识（原文不可见）` : c.title} · 被引用 {c.n_cited} 次</>;
  return c.text == null ? <p className="text-[12px] text-ink-2">{head}</p> : (
    <Disclosure label={<span className="text-[12px]">{head}</span>}>
      <p className="whitespace-pre-wrap text-[12px] leading-[18px] text-ink-2">{c.text}</p>
    </Disclosure>
  );
}

function Item({ reqId, index, item, view, cited, editable, notes }: {
  reqId: string; index: number; item: ReqItem; view: RequirementView; cited: Record<string, CitedKnowledge>;
  editable: boolean; notes: AgentMessage[];
}) {
  const { me } = useApp();
  const L = useLabels();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.text);
  return (
    <div className="row !items-start !py-2.5">
      <span className="num w-4 shrink-0 pt-px text-[13px] text-ink-3">{index + 1}</span>
      <div className="min-w-0 flex-1">
        {editing ? (
          <div className="flex flex-col gap-1.5">
            <Field value={text} onChange={setText} rows={3} label={`第 ${index + 1} 条`} />
            <span className="flex gap-2">
              <Act label="保存" run={() => api.editItem(reqId, index, { ...item, text }, me).then(() => setEditing(false))} />
              <button type="button" className="btn btn-quiet" onClick={() => { setText(item.text); setEditing(false); }}>取消</button>
            </span>
          </div>
        ) : (
          <p className="text-[14px] leading-[21px]">
            {item.slot && <span className="text-ink-2">{L.slot(item.slot)}　</span>}{item.text}
            {item.edited_by == null ? <span className="ml-1.5 align-[1px]"><AgentMark /></span>
              : <span className="ml-1.5 text-[12px] text-ink-3">{L.name(item.edited_by)} 修改</span>}
            {editable && <button type="button" className="link ml-2" onClick={() => setEditing(true)}>修改</button>}
          </p>
        )}
        {item.ku_refs.map((r) => cited[r] && <Basis key={r} c={cited[r]} />)}
        {item.quote_refs.map((r) => <p key={r} className="text-[12px] text-ink-3">原话「{view.quotes[r]}」</p>)}
        <Notes notes={notes} />
      </div>
    </div>
  );
}

// 右侧：需求单的来历（升级说明、退回记录、合并判断），觉与 Agent 的批注挂在条目上
function ReqContext({ view }: { view: RequirementView }) {
  const L = useLabels();
  const req = view.requirement;
  return (
    <>
      {req.escalate_note && <Group title="业务员的升级说明"><div className="row text-[13px] leading-5">{req.escalate_note}</div></Group>}
      {req.reuse && (
        <Group title="现成产品">
          <div className="row text-[13px] leading-5">{req.reuse.product_id ? L.product(req.reuse.product_id) : L.scrub(req.reuse.note)}</div>
          {req.reuse.declined_reason && <div className="row text-[13px] text-ink-2">不采用：{req.reuse.declined_reason}</div>}
        </Group>
      )}
      {req.merge_note && <Group title="产品经理 Agent 的合并判断"><div className="row text-[13px] leading-5">{req.merge_note}</div></Group>}
      {!!req.return_notes.length && (
        <Group title="退回记录">{req.return_notes.map((n, i) => <div key={i} className="row text-[13px] leading-5">{n}</div>)}</Group>
      )}
    </>
  );
}

// ── 签字区：随当前选中的决策变化 ─────────────────────────────
export function SignArea({ q, view }: { q: Question; view: RequirementView | null }) {
  const { me } = useApp();
  const L = useLabels();
  const dismiss = <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me)} />;
  const head = (
    <div className="row attn-edge">
      <span className="tag tag-attn">{L.family(q.family)}</span>
      <p className="min-w-0 flex-1 truncate text-[14px] font-semibold">{L.scrub(q.title)}</p>
      <Score q={q} />
    </div>
  );
  if (q.prepared_at == null) {
    return (
      <Group title="签字区">
        <div className="row"><span className="tag">{L.family(q.family)}</span>
          <p className="flex-1 text-[14px] text-ink-2">{ownerText(q, me, L.name)}，准备好后才能签字</p></div>
      </Group>
    );
  }
  const req = view?.requirement;
  const evidence = q.evidence.map((e, i) => (
    <div key={i} className="row !items-start text-[13px] leading-5 text-ink-2">{L.scrub(e.summary)}{e.quote && `「${e.quote}」`}</div>
  ));
  const body = (() => {
    if (!req) return <>{evidence}<div className="row text-[13px] text-ink-2">证据 {q.evidence.length} 条</div><div className="row gap-2">{q.family === "knowledge_conflict" && <Act label="更新适用表" run={() => api.resolve(q.id, "update_sheet", me)} />}{q.family === "leak_risk" && <Act label="冻结权限" run={() => api.resolve(q.id, "freeze_access", me)} />}{dismiss}</div></>;
    switch (q.family) {
      case "reuse_product": return <ReuseReview q={q} view={view!} dismiss={dismiss} />;
      case "opportunity": return <MergeReview q={q} view={view!} dismiss={dismiss} />;
      case "accept_requirement": return <AcceptReview reqId={req.id} dismiss={dismiss} evidence={evidence} />;
      case "confirm_translation":
        return <>{evidence}<div className="row gap-2"><Act label="确认转译" run={() => api.confirm(req.id, me)} />{dismiss}</div></>;
      case "contribution": return <ContributionReview view={view!} dismiss={dismiss} />;
      case "seal_points": return <PointsReview view={view!} dismiss={dismiss} />;
      case "release": case "seal_leak": return <SheetReview view={view!} release={q.family === "release"} dismiss={dismiss} />;
      case "decrypt_request": return <DecryptReview q={q} dismiss={dismiss} evidence={evidence} />;
      default: return <>{evidence}<div className="row">{dismiss}</div></>;
    }
  })();
  return <Group title="签字区">{head}{body}</Group>;
}

function AcceptReview({ reqId, dismiss, evidence }: { reqId: string; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me } = useApp();
  const [reason, setReason] = useState("");
  return (
    <>
      {evidence}
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2">
          <p className="text-[13px] text-ink-2">接单即立项：被引用的 L2 知识给归属人记分。</p>
          <div className="flex flex-wrap gap-2"><Act label="接单" run={() => api.accept(reqId, me)} />{dismiss}</div>
          <Field value={reason} onChange={setReason} placeholder="退回理由（提交前做研发术语自查，产品经理 Agent 可见）" />
          <div><Act kind="plain" label="退回" disabled={!reason.trim()} run={() => api.returnReq(reqId, reason, me)} /></div>
        </div>
      </div>
    </>
  );
}

// 现成产品审定（D22）：产品、依据的 L2 案例原文、可改的给客户说明、自查结果
function ReuseReview({ q, view, dismiss }: { q: Question; view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const r = req.reuse!;
  const [note, setNote] = useState(r.customer_note);
  useEffect(() => setNote(r.customer_note), [r.customer_note]);
  const [reason, setReason] = useState("");
  const cases = view.cited.filter((c) => r.ku_refs.includes(c.ku_id));
  return (
    <>
      <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">产品</span>
        <span className="text-[15px] font-semibold">{L.product(r.product_id)}</span></div>
      <div className="row !items-start"><span className="w-20 shrink-0 text-[13px] text-ink-2">依据</span>
        <div className="min-w-0 flex-1">{cases.map((c) => <Basis key={c.ku_id} c={c} />)}
          {q.evidence.map((e, i) => <p key={i} className="text-[12px] text-ink-2">{L.scrub(e.summary)}</p>)}</div></div>
      <div className="row !items-start">
        <span className="w-20 shrink-0 pt-1 text-[13px] text-ink-2">给客户的说明</span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="flex items-center gap-2">{note === r.customer_note && <AgentMark who="产品经理 Agent 起草" />}
            <span className="text-[12px] text-ink-2">保存时做泄露自查，命中则门面拒绝并给出句序号</span></p>
          <Field value={note} onChange={setNote} rows={3} label="给客户的说明" />
          {note !== r.customer_note && <div><Act kind="plain" label="保存修改" run={() => api.reuseNote(req.id, note, me)} /></div>}
        </div>
      </div>
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <Act label="通过并转给业务员" disabled={note !== r.customer_note} run={() => api.adoptReuse(req.id, me)} />{dismiss}
          </div>
          <Field value={reason} onChange={setReason} placeholder="不采用的理由（随后觉提出是否接单）" />
          <div><Act kind="plain" label="不采用" disabled={!reason.trim()} run={() => api.declineReuse(req.id, reason, me)} /></div>
        </div>
      </div>
    </>
  );
}

// 机会汇聚（D19）：并排各单的客户原话与产品经理 Agent 的判断理由
function MergeReview({ q, view, dismiss }: { q: Question; view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const members = view.requirement.merge_from;
  const others = useData(() => Promise.all(members.map((id) => api.requirement(id, me))), [members.join(","), me]) ?? [];
  const all = [view, ...others];
  return (
    <>
      <div className="row text-[13px] text-ink-2">{all.length} 位客户、同类需求：{L.phen(view.requirement.phenomenon)}</div>
      <div className="row !items-stretch gap-3">
        {all.map((v, i) => (
          <div key={v.requirement.id} className="min-w-0 flex-1 rounded-[8px] bg-bg px-3 py-2">
            <p className="text-[12px] font-semibold text-ink-2">{i === 0 ? "主单" : `拟并入 ${i}`}</p>
            {Object.values(v.quotes).map((t, j) => <p key={j} className="text-[13px] leading-5">「{t}」</p>)}
          </div>
        ))}
      </div>
      <div className="row !items-start">
        <span className="w-20 shrink-0 text-[13px] text-ink-2">判断理由</span>
        <p className="flex-1 text-[13px] leading-5">{view.requirement.merge_note || "—"} <AgentMark who="产品经理 Agent 起草" /></p>
      </div>
      {q.evidence.map((e, i) => <div key={i} className="row text-[12px] text-ink-2">{L.scrub(e.summary)}</div>)}
      <div className="row gap-2"><Act label="合并" run={() => api.merge(q.id, me)} />{dismiss}</div>
    </>
  );
}

// 沉淀：逐条显示 Agent 提炼的转化知识，每条一个按钮
function ContributionReview({ view, dismiss }: { view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const req = view.requirement;
  return (
    <>
      {req.contribution_drafts.map((d, i) => (
        <div key={i} className="row !items-start">
          <span className="num w-8 shrink-0 text-[13px] text-ink-3">第 {d.item_index + 1} 条</span>
          <div className="min-w-0 flex-1">
            <p className="text-[14px]">「{d.scene_phrase}」→ {d.chem_term} <AgentMark /></p>
            {d.note && <p className="text-[12px] leading-[18px] text-ink-2">{d.note}</p>}
          </div>
          <Act kind="plain" label="沉淀为我的知识" run={() => api.contribute(req.id, d.item_index, d.scene_phrase, d.chem_term, me)} />
        </div>
      ))}
      {!req.contribution_drafts.length && <div className="row text-[13px] text-ink-2">Agent 没有提炼出可沉淀的条目</div>}
      <div className="row">{dismiss}</div>
    </>
  );
}

// 封存 / 放出两栏：左「对客户说」、右「封存（只有研发可见）」，自查命中的句子红色下划线
function PointsReview({ view, dismiss }: { view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const d = req.points_draft ?? { public: "", sealed: [], self_check: [] };
  const [pub, setPub] = useState(d.public);
  const [sealed, setSealed] = useState(d.sealed.join("\n"));
  useEffect(() => { setPub(d.public); setSealed(d.sealed.join("\n")); }, [d.public, d.sealed.join("\n")]);
  const untouched = pub === d.public && sealed === d.sealed.join("\n");
  return (
    <>
      <div className="row !items-start gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="flex items-center gap-2 text-[12px] font-semibold text-ink-2">对客户说 {untouched && <AgentMark />}</p>
          {untouched && !!d.self_check.length && (
            <p className="rounded-[8px] bg-bg px-2.5 py-1.5 text-[13px] leading-5"><Marked text={d.public} hits={d.self_check.map((h) => h.index)} /></p>
          )}
          <Field value={pub} onChange={setPub} rows={4} label="对客户说" />
          {untouched && d.self_check.map((h) => (
            <p key={h.index} className="text-[12px] text-danger">第 {h.index + 1} 句{L.leak(h.source)}</p>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="text-[12px] font-semibold text-ink-2">封存（只有研发可见，一行一项）</p>
          <Field value={sealed} onChange={setSealed} rows={4} label="封存" />
        </div>
      </div>
      <div className="row gap-2">
        <Act label="签字：封存 / 放出" run={() => api.points(req.id, pub, sealed.split("\n").map((s) => s.trim()).filter(Boolean), me)} />
        {dismiss}
      </div>
    </>
  );
}

// 发布审定 / 说明书改写：业务员将看到的说明书与用法 + 泄密检查结果
function SheetReview({ view, release, dismiss }: { view: RequirementView; release: boolean; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const leak = useData<LeakHit[]>(() => api.leak(req.id, me), [req.id, me]) ?? [];
  const s = req.sheet ?? { sheet: "", usage: "" };
  const [sheet, setSheet] = useState(s.sheet);
  const [usage, setUsage] = useState(s.usage);
  useEffect(() => { setSheet(s.sheet); setUsage(s.usage); }, [s.sheet, s.usage]);
  const changed = sheet !== s.sheet || usage !== s.usage;
  return (
    <>
      <div className="row !items-start">
        <span className="w-14 shrink-0 text-[13px] text-ink-2">说明书</span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          {!changed && <p className="text-[14px] leading-[22px]"><Marked text={s.sheet} hits={leak.map((h) => h.index)} /> <AgentMark who="产品经理 Agent 包装" /></p>}
          <Field value={sheet} onChange={setSheet} rows={3} label="说明书" />
        </div>
      </div>
      <div className="row !items-start">
        <span className="w-14 shrink-0 text-[13px] text-ink-2">用法</span>
        <div className="flex-1"><Field value={usage} onChange={setUsage} label="用法" /></div>
      </div>
      <div className="row !items-start text-[13px]">
        <span className="w-14 shrink-0 text-ink-2">泄密检查</span>
        <div className="flex-1">
          {leak.length ? leak.map((h) => <p key={h.index} className="text-danger">第 {h.index + 1} 句{L.leak(h.source)}</p>)
            : <p className="text-ink-2">未命中封存项与研发术语（规则匹配挡不住换说法，最后一道闸是你的审定）</p>}
        </div>
      </div>
      <div className="row gap-2">
        {changed && <Act kind="plain" label="保存说明书" run={() => api.sheet(req.id, { sheet, usage }, me)} />}
        {release && <Act label="审定发布" disabled={changed} run={() => api.release(req.id, me)} />}
        {dismiss}
      </div>
    </>
  );
}

function DecryptReview({ q, dismiss, evidence }: { q: Question; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me } = useApp();
  const [text, setText] = useState("");
  return (
    <>
      {evidence}
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2">
          <Field value={text} onChange={setText} rows={3} placeholder="给这一位客户的机理说明（经业务员转交；配方永不对外）" />
          <div className="flex flex-wrap gap-2">
            <Act label="批准解密" run={() => api.decideDecrypt(q.id, true, text, me)} />
            <Act kind="plain" label="拒绝" run={() => api.decideDecrypt(q.id, false, "", me)} />
            {dismiss}
          </div>
        </div>
      </div>
    </>
  );
}
