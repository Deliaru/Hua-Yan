// 业务员工作面（L1）：中间是沟通记录（紧凑时间轴，末尾录入客户的话）与场景需求卡，底部「发给客户」操作坞，都不经过 Agent；
// 右侧是觉的决策（推荐还是升级、现成产品、回问、客户评价）与「与 Agent 协作」。
import { useEffect, useState } from "react";
import { HuayanFeed, ImSide } from "../components/Im";
import { api } from "../api";
import { SESSION_STATUS, Side, hhmm, useApp, useData, useLabels } from "../ctx";
import type { AgentMessage, AskHint, Question, RecommendationCard, SessionSummary, SessionView } from "../types";
import { AgentPanel, Notes, PendingActions, notesFor, useConversation } from "../components/Agent";
import { useGlow, useGuideArg, useGuide } from "../components/Guide";
import { Popover } from "../components/Controls";
import { Plus } from "../components/Icons";
import { Act, AgentMark, EmptyState, Field, Group, PageHead, Score, SideHead, SlotPicker, TemperatureCondition } from "../components/ui";
import { More, useAsk } from "../components/Task";
import { RouteStrip, WorkloadCard } from "../components/Route";
import { AuthorizedReplies } from "../components/AuthorizedReplies";
import { Backstory } from "../components/Backstory";
import { Narration, TimeBar } from "../components/Narration";
import { RelayLoss } from "../components/RelayLoss";

// V11.3 收件箱：有待你处理的决策的会话排在「轮到你」，其余在「全部会话」
function SalesSidebar({ mine, current, guided, choose, todo }: {
  mine: SessionSummary[]; current: string | null; guided: string | null; choose: (id: string) => void; todo: Record<string, number>;
}) {
  const { meta, me, refresh, fail } = useApp();
  const L = useLabels();
  const start = (customer: string) => api.startSession(customer, me).then((s) => { choose(s.id); refresh(); }, fail);
  const glow = useGlow("new-session");
  const pickCustomer = useGuideArg("new-session");
  const row = (s: SessionSummary) => (
    <button key={s.id} onClick={() => choose(s.id)}
            className={`side-row ${s.id === current ? "on" : ""} ${s.id === guided && s.id !== current ? "glow" : ""}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[13px] font-semibold">{s.customer_id ? L.name(s.customer_id) : "样例客户"}</span>
        {todo[s.id] ? <span className="num tag tag-attn shrink-0">待处理 {todo[s.id]}</span>
          : s.origin === "customer" ? <span className="tag tag-attn shrink-0">商务 · 觉转来</span>
          : <span className="shrink-0 text-[12px] text-ink-2">{SESSION_STATUS[s.status] ?? s.status}</span>}
      </div>
      <p className="truncate text-[12px] text-ink-2">{s.phenomenon ? L.phen(s.phenomenon) : "尚未识别现象"}</p>
    </button>
  );
  return (
    <>
      <SideHead aside={
        <Popover trigger={(toggle) => <button onClick={toggle} className={`icon-btn !h-6 !w-6 ${glow ? "glow" : ""}`} title="新建客户会话"><Plus /></button>}>
          {(close) => (
            <>
              <p className="px-2.5 pb-1 pt-0.5 text-[12px] text-ink-2">新建客户会话</p>
              {meta.actors.filter((a) => a.role === "customer").map((c) => (
                <button key={c.id} className={`menu-item ${c.id === pickCustomer ? "glow font-semibold" : ""}`} onClick={() => { start(c.id); close(); }}>{L.name(c.id)}</button>
              ))}
            </>
          )}
        </Popover>
      }>等你处理</SideHead>
      {mine.filter((s) => todo[s.id]).map(row)}
      {!mine.some((s) => todo[s.id]) && <p className="px-[18px] py-1 text-[13px] text-ink-3">没有待你处理的事</p>}
      <SideHead>全部会话</SideHead>
      {mine.filter((s) => !todo[s.id]).map(row)}
      {!mine.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">点上方 ＋ 新建一个客户会话</p>}
    </>
  );
}

// 主管冻结了本人的上层知识检索：只读状态由门面给出，界面不自己判断权限
function useFrozen() {
  const { me } = useApp();
  return useData(() => api.frozen(me), [me])?.frozen ?? false;
}

export function useMySessions() {
  const { me } = useApp();
  const all = useData(() => api.sessions(), []);
  return (all ?? []).filter((s) => s.sales_id === me).reverse();
}

export function Sales() {
  const { me, focus } = useApp();
  const [chosen, choose] = useState<string | null>(focus);
  useEffect(() => { if (focus) choose(focus); }, [focus]);
  const own = useMySessions();
  const all = useData(() => api.sessions(), []) ?? [];
  // 导览指向的会话（轮到本人时）：没手动选过就直接打开它，选过别的就在侧栏高亮它
  const g = useGuide();
  const questions = useData(() => api.questions(me), [me]);
  // V12.7 回访过去没解决的自助客户：那段会话还没有业务员，带着交给你的决策一起列进来
  const asked = new Set((questions ?? []).map((q) => q.refs.session_id));
  const mine = [...own, ...all.filter((s) => s.sales_id !== me && asked.has(s.id)).reverse()];
  // 签字类台词（如客户评价）只写了需求单：按要签的那项决策挂在哪段会话来定位
  const signAt = (questions ?? []).find((q) => `sign:${q.family}` === g.target && q.refs.session_id)?.refs.session_id;
  const guided = g.who !== me ? null : (g.customer ? mine.find((s) => s.customer_id === g.customer)?.id : undefined)
    ?? mine.find((s) => s.id === signAt)?.id ?? null;
  // 演示讲解按台词打开那段会话；其余不自己打开：化言把轮到你的会话推到左边消息里，点「去处理」才打开
  useEffect(() => { if (guided && g.customer) choose(null); }, [guided]);
  const current = mine.find((s) => s.id === chosen) ?? (g.customer ? mine.find((s) => s.id === guided) : null) ?? null;
  const sid = current?.id ?? null;
  const view = useData(() => (sid ? api.session(sid, me) : Promise.resolve(null)), [sid, me]);
  const mineQs = (questions ?? []).filter((q) => !q.refs.session_id || q.refs.session_id === sid);
  const handoffs = own.filter((s) => s.origin === "customer" && s.last?.speaker === "customer").reverse();
  const todo: Record<string, number> = {};
  for (const q of questions ?? []) if (q.refs.session_id) todo[q.refs.session_id] = (todo[q.refs.session_id] ?? 0) + 1;
  return (
    <>
      <Side><ImSide badge={(questions ?? []).filter((q) => q.prepared_at != null).length + handoffs.length}
        feed={<HuayanFeed selected={(questions ?? []).find((q) => q.refs.session_id === sid)?.id ?? null} reqs={[]}
                          select={(q) => q.refs.session_id && choose(q.refs.session_id)} handoffs={handoffs} chosen={sid} openHandoff={choose} />}
        desk={<SalesSidebar mine={mine} current={sid} guided={guided} choose={choose} todo={todo} />} /></Side>
      {current && view ? <SessionDesk key={sid} summary={current} v={view} questions={mineQs} />
        : <EmptyState title={mine.length ? "在左边化言的消息里点「去处理」" : "还没有客户会话"}
                      text={mine.length ? "轮到你的会话化言会推给你；所有会话在「工作台」里。" : "点侧栏「工作台」里「全部会话」右侧的 ＋，选一个客户开始，把客户的原话录进来。"} />}
    </>
  );
}

const need = (h: AskHint) => (h.scored_by === "rule" ? "到点" : `${Math.round(h.p_need * 100)}%`);

function SessionDesk({ summary, v, questions }: { summary: SessionSummary; v: SessionView; questions: Question[] }) {
  const L = useLabels();
  const { notes } = useApp();
  const conv = useConversation(v.session_id);
  // 「发给客户」预填 Agent 的回复草稿；草稿更新时覆盖
  const [reply, setReply] = useState(v.reply_draft);
  useEffect(() => setReply(v.reply_draft), [v.reply_draft]);
  const [lit, setLit] = useState<string | null>(null); // 点槽位：时间轴里对应的那句原话高亮
  const frozen = useFrozen();
  return (
    <>
      <div className="mr-[372px] pb-[260px]">
        <div className="mx-auto flex max-w-[1000px] flex-col gap-5 px-8 pt-7">
          <PageHead title={summary.customer_id ? L.name(summary.customer_id) : "样例客户"}
                    subtitle={`${summary.phenomenon ? L.phen(summary.phenomenon) : "尚未识别现象"} · ${SESSION_STATUS[v.status] ?? v.status}`} />
          {summary.origin === "customer" && (
            <p className="rounded-[10px] bg-attn-bg px-3.5 py-2.5 text-[13px] leading-5 text-attn-ink">
              {summary.sales_id ? "客户在自助对话里提出了商务诉求，觉把这件事交给你。下面是客户的完整原话、已明确的条件和已推荐的产品，不需要你重新询问、重新记录。"
                : "这位客户自助问过、当时没有解决。研发后来签出的判断覆盖了他当时说的条件，觉请你回访；下面是他当时的原话和条件。"}</p>
          )}
          {frozen && <p className="rounded border border-attn-ink/30 px-3 py-2 text-[13px] text-attn-ink">你的上层知识检索已被主管冻结：检索不再显示上层知识的归属、读不到研发授予的结论，推荐只披露到用法，暂不能申请解密；日常跟单不受影响。</p>}
          <PendingActions />
          <AuthorizedReplies sessionId={v.session_id} />
          <div className="grid grid-cols-[minmax(280px,5fr)_minmax(320px,6fr)] items-start gap-5">
            <Timeline v={v} lit={lit} />
            <NeedCard v={v} phenomenon={summary.phenomenon} lit={lit} setLit={setLit} />
          </div>
          <More items={[
            ["前情", <Backstory id={v.session_id} />, true],
            ["旁白", <Narration id={v.session_id} />, notes],
            ["流转", <RouteStrip objectId={v.session_id} />, notes],
          ]} />
        </div>
      </div>
      <Composer v={v} reply={reply} setReply={setReply} replyNotes={notesFor(conv?.messages, `${v.session_id}/reply`)} />
      <AgentPanel title="要你定" sessionId={v.session_id} focus={v.session_id} external>
        {v.card || v.reuse || questions.length
          ? <Decisions v={v} questions={questions} fill={setReply} replyEmpty={!reply.trim()} escalateNotes={notesFor(conv?.messages, `${v.session_id}/escalate`)} />
          : <p className="text-[13px] leading-5 text-ink-3">现在没有要你定的事。客户每说一句，觉都会再看一遍：该推荐、该转研发、该回头问的时候出现在这里。</p>}
        <TimeBar />
        <RelayLoss />
        <WorkloadCard />
      </AgentPanel>
    </>
  );
}

// 沟通记录：紧凑时间轴；末尾一行「客户说」由演示者录入（不经过 Agent）
function Timeline({ v, lit }: { v: SessionView; lit: string | null }) {
  const { refresh } = useApp();
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  const glow = useGlow("customer");
  // 演示台词里这位客户还有下一句时才给「演示自动填入」；没有就只能由演示者自己输入
  const line = useData(() => api.nextLine(v.session_id), [v.session_id, v.turns.length])?.text ?? null;
  const [err, setErr] = useState<string | null>(null);
  const run = (p: Promise<unknown>, done?: () => void) => {
    setBusy(true);
    setErr(null);
    p.then(() => done?.(), (e) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
  };
  const submit = () => said.trim() && run(api.addTurn(v.session_id, "customer", said.trim()), () => { setSaid(""); refresh(); });
  const replies = (turnId: string) => v.replies.filter((r) => r.turn_id === turnId);
  return (
    <section>
      <div className="group-title">沟通记录</div>
      <div className="group">
        {!v.turns.length && <p className="px-4 py-5 text-[13px] leading-5 text-ink-2">还没有发言。客户只说宏观现象即可，比如「染完以后布面深一块浅一块」。</p>}
        <ol className="flex flex-col py-1">
          {v.turns.map((t) => {
            const sales = t.speaker === "sales";
            const on = lit === t.id;
            return (
              <li key={t.id} className={`anim-rise flex gap-3 px-4 py-2 transition-colors ${on ? "bg-[rgba(10,108,223,.07)]" : ""}`}>
                <span className="num w-9 shrink-0 pt-[2px] text-[11px] text-ink-3">{hhmm(t.ts)}</span>
                <div className="min-w-0 flex-1">
                  <p className={`text-[11px] font-semibold ${sales ? "text-accent" : "text-ink-2"}`}>{sales ? "业务员" : t.speaker === "assistant" ? "化言（自助时代问）" : "客户"}</p>
                  <p className={`text-[14px] leading-[21px] ${on ? "font-semibold" : ""}`}>{t.text}</p>
                  {replies(t.id).map((r, j) => (
                    <p key={j} className="mt-1 text-[12px] leading-[18px] text-ink-2">知识助手：{r.text}
                      {r.blocked && <span className="tag tag-danger ml-1.5">研发保密 · 已拦截</span>}</p>
                  ))}
                </div>
              </li>
            );
          })}
        </ol>
        <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="flex items-center gap-2 border-t border-sep bg-[#fafafb] py-2 pl-4 pr-2.5">
          <span className="w-9 shrink-0 text-[11px] font-semibold text-ink-2">客户</span>
          <input value={said} onChange={(e) => setSaid(e.target.value)} aria-label="客户说" disabled={busy}
                 placeholder="客户说……（照原话录入）" className="min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-3" />
          {line && <button type="button" className={`chip ${glow && !said.trim() ? "glow" : ""}`} disabled={busy}
                           onClick={() => setSaid(line)}>演示自动填入</button>}
          <button className={`btn btn-plain !h-[26px] !px-2.5 ${glow && said.trim() ? "glow" : ""}`} disabled={busy || !said.trim()}>录入</button>
        </form>
        {err && <p role="alert" className="px-4 pb-2 text-[12px] text-danger">{err}</p>}
      </div>
    </section>
  );
}

// 发给客户：唯一的对外通道。Agent 草稿预填，觉的追问提词挂在上方；门面拦截时原因写在下方、不发出。
function Composer({ v, reply, setReply, replyNotes }: {
  v: SessionView; reply: string; setReply: (t: string) => void; replyNotes: AgentMessage[];
}) {
  const { me, agentOnline, refresh } = useApp();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fromAgent = !!v.reply_draft && reply === v.reply_draft;
  const ask = useGlow("reply"), rec = useGlow("send-rec"), sendNow = useGlow("send");
  const example = useGuideArg("send");     // 自己玩：关卡里写好的示范话
  const glow = ask || rec || sendNow;
  const pick = ask && !reply.trim();   // 导览：先挑追问提词（或让 Agent 起草），有了话再「发出」
  const send = () => {
    if (!reply.trim() || busy) return;
    setBusy(true);
    setErr(null);
    api.addTurn(v.session_id, "sales", reply.trim()).then(() => { setReply(""); refresh(); },
      (e) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
  };
  return (
    <div className="pointer-events-none fixed bottom-0 left-[var(--side-w)] right-[372px] z-10 bg-gradient-to-t from-bg from-60% to-transparent pt-12">
      <div className="pointer-events-auto mx-auto max-w-[1000px] px-8 pb-5">
        {!!v.hints.length && (
          <div className="mb-2.5 flex flex-wrap items-center gap-2">
            <span className="eyebrow mr-1">觉建议追问</span>
            {v.hints.map((h) => (
              <button key={h.slot} type="button" onClick={() => setReply(h.ask_text)}
                      className={`anim-rise flex h-[30px] items-center gap-2 rounded-full bg-attn-bg pl-3 pr-2.5 ${pick ? "glow" : ""} text-[13px] shadow-[0_0_0_.5px_rgba(176,80,10,.28)] transition-colors hover:bg-[#fff0d9]`}>
                <span className="font-semibold text-attn-ink">{h.label}</span>
                <span>{h.ask_text}</span>
                <span className="num text-[11px] text-attn-ink">{need(h)}</span>
              </button>
            ))}
          </div>
        )}
        <form className="dock" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <div className="flex items-center gap-2 px-4 pt-2.5">
            <span className="text-[12px] font-semibold">发给客户</span>
            {fromAgent && <AgentMark />}
            {!reply && !agentOnline && <span className="text-[12px] text-ink-3">Agent 离线，无草稿</span>}
            <span className="ml-auto flex gap-1.5">
              {example && !reply && <button type="button" className="chip glow" onClick={() => setReply(example)}>填入示范</button>}
              <Act kind="chip" label="帮我回一句" glow={pick && !v.hints.length} disabled={!agentOnline} run={() => api.chat(me, "帮我回一句", v.session_id, v.session_id)} />
              <Act kind="chip" label="直接推荐" run={() => api.recommend(v.session_id)} />
            </span>
          </div>
          <textarea value={reply} rows={2} aria-label="发给客户" onChange={(e) => setReply(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); } }}
                    placeholder="写给客户的话，或点上方的追问提词"
                    className="block w-full resize-none bg-transparent px-4 py-1.5 text-[14px] leading-[22px] outline-none placeholder:text-ink-3" />
          <div className="flex items-center gap-3 pb-2.5 pl-4 pr-3">
            <div className="min-w-0 flex-1">
              {err ? <p role="alert" className="text-[12px] text-danger">{err}，未发出</p> : <Notes notes={replyNotes} />}
            </div>
            <span className="kbd">Ctrl ↵</span>
            <button className={`btn btn-primary ${glow && reply.trim() ? "glow" : ""}`} disabled={!reply.trim() || busy}>{busy ? "发送中……" : "发出"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// 场景需求卡：业务员工作面的主角。每一格绑定客户原话，点一下在左边时间轴里高亮那句；觉建议追问的槽位显示为待问。
function NeedCard({ v, phenomenon, lit, setLit }: {
  v: SessionView; phenomenon: string | null; lit: string | null; setLit: (t: string | null) => void;
}) {
  const L = useLabels();
  const asking = v.hints.filter((h) => !v.slots.some((s) => s.slot === h.slot && s.value));
  const cell = "border-b border-r border-sep px-5 py-3.5 text-left [&:nth-child(2n)]:border-r-0";
  return (
    <section>
      <div className="group-title flex items-baseline justify-between">
        <span>场景需求卡</span><span className="font-normal text-ink-3">每一格绑定客户原话</span>
      </div>
      <div className="group">
        <div className="relative overflow-hidden border-b border-sep px-5 py-4">
          <i className="absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-[#7ee0ff] via-[#5b7cfa] to-[#b25cf0]" />
          <p className="eyebrow">现象</p>
          <p className={`mt-1 text-[20px] font-semibold leading-7 ${phenomenon ? "" : "text-ink-3"}`}>{phenomenon ? L.phen(phenomenon) : "等客户描述"}</p>
          <p className="mt-0.5 text-[12px] text-ink-2">已确认 {v.slots.filter((s) => s.value).length} 项{asking.length ? ` · 待问 ${asking.length} 项` : ""}</p>
        </div>
        <TemperatureCondition value={v.temperature} />
        <div className="grid grid-cols-2">
          {v.slots.map((s) => {
            const on = lit === s.turn_id;
            return (
              <button key={s.slot} type="button" onClick={() => setLit(on ? null : s.turn_id)}
                      className={`anim-rise transition-colors ${cell} ${on ? "bg-[rgba(10,108,223,.06)]" : "hover:bg-[rgba(0,0,0,.02)]"}`}>
                <p className="eyebrow">{L.slot(s.slot)}</p>
                <p className={`mt-0.5 text-[16px] font-semibold leading-6 ${s.value ? "" : "text-ink-3"}`}>{s.value ?? "客户不清楚"}</p>
                <p className={`mt-1 truncate text-[12px] ${on ? "text-accent" : "text-ink-2"}`}>「{s.quote}」</p>
              </button>
            );
          })}
          {asking.map((h) => (
            <div key={h.slot} className={cell}>
              <p className="eyebrow">{h.label}</p>
              <p className="mt-0.5 text-[16px] leading-6 text-ink-3">待问</p>
              <p className="mt-1 text-[12px] text-attn-ink">觉建议追问 · {need(h)}</p>
            </div>
          ))}
        </div>
        {!v.slots.length && !asking.length && <p className="px-5 py-4 text-[13px] text-ink-2">还没有识别出条件；客户每说一句，这里逐格长出来。</p>}
      </div>
    </section>
  );
}

function Decisions({ v, questions, fill, replyEmpty, escalateNotes }: {
  v: SessionView; questions: Question[]; fill: (t: string) => void; replyEmpty: boolean; escalateNotes: AgentMessage[];
}) {
  const L = useLabels();
  const ask = useAsk();
  const by = (f: string) => questions.filter((q) => q.family === f);
  const handled = new Set(["escalate_need", "ask_back", "market_eval", "mechanism_followup", "capability_recall"]);
  return (
    <>
      {v.card && v.reuse?.status !== "adopted" && <RecCard card={v.card} sid={v.session_id} fill={fill} replyEmpty={replyEmpty} />}
      {by("escalate_need").map((q) => <EscalateCard key={q.id} q={q} v={v} notes={escalateNotes} />)}
      {v.reuse && <ReuseLine v={v} fill={fill} />}
      {by("ask_back").map((q) => (
        <Group key={q.id} title={<span className="text-attn-ink">回问 · 研发需要知道</span>}
               foot={v.reply_draft ? "话术已由 Agent 填进「发给客户」，由你发出。" : "Agent 离线，没有话术：用你自己的话问客户，答复会回填需求单。"}>
          <div className="row attn-edge !items-start">
            <div className="min-w-0 flex-1">
              <p className="text-[14px] font-semibold">{q.refs.slot ? `问客户：${L.slot(q.refs.slot)}` : L.scrub(q.title)}</p>
              {q.evidence.map((e, i) => <p key={i} className="text-[13px] leading-5 text-ink-2">{L.scrub(e.summary)}</p>)}
            </div>
            <Score q={q} />
          </div>
        </Group>
      ))}
      {by("market_eval").map((q) => <MarketEval key={q.id} q={q} />)}
      {by("mechanism_followup").map((q) => <Followup key={q.id} q={q} />)}
      {by("capability_recall").map((q) => <Recall key={q.id} q={q} />)}
      {questions.filter((q) => !handled.has(q.family)).map((q) => (
        <Group key={q.id} title={L.family(q.family)}>
          <div className="row !items-start">
            <div className="min-w-0 flex-1">
              <p className="text-[14px]">{ask(q)}</p>
              {q.evidence.map((e, i) => <p key={i} className="text-[12px] text-ink-2">{L.scrub(e.summary)}</p>)}
            </div>
            <Score q={q} />
          </div>
        </Group>
      ))}
    </>
  );
}

function RecCard({ card, sid, fill, replyEmpty }: { card: RecommendationCard; sid: string; fill: (t: string) => void; replyEmpty: boolean }) {
  const { me } = useApp();
  const glow = useGlow("send-rec") && replyEmpty;
  const L = useLabels();
  const decrypted = card.version === "full_mechanism";
  const frozen = useFrozen();
  return (
    <Group title="推荐" foot={card.note ? L.scrub(card.note) : undefined}>
      <div className="row">
        <p className="flex-1 text-[16px] font-semibold">{L.product(card.product_id)}</p>
        <span className="tag">{L.version(card.version)}</span>
      </div>
      {card.sections.map((s) => (
        <div key={s.ku_id} className="row !items-start">
          <div className="min-w-0">
            <p className="text-[12px] text-ink-2">{s.title}</p>
            <p className="text-[14px] leading-[21px]">{s.text}</p>
          </div>
        </div>
      ))}
      <div className="row flex-wrap">
        <button type="button" className={`btn btn-plain ${glow ? "glow" : ""}`} onClick={() => fill(card.sections.map((s) => s.text).join(""))}>填进发给客户</button>
        {!decrypted && !frozen && <Act kind="quiet" label="申请解密" done="已申请解密，等研发审批" run={() => api.requestDecrypt(sid, me)} />}
        {decrypted && <span className="text-[12px] text-ink-2">研发审定的机理说明，由你转交客户</span>}
      </div>
    </Group>
  );
}

// 推荐还是升级：觉提出、业务员签字（D8）。升级说明可直接改。
function EscalateCard({ q, v, notes }: { q: Question; v: SessionView; notes: AgentMessage[] }) {
  const { me } = useApp();
  const L = useLabels();
  const [note, setNote] = useState(v.escalate_note);
  useEffect(() => setNote(v.escalate_note), [v.escalate_note]);
  const ready = q.prepared_at != null;
  const glow = useGlow("sign:escalate_need");
  const sign = async () => {
    if (note !== v.escalate_note) await api.escalateNote(v.session_id, note, me);
    await api.escalate(v.session_id, me);
  };
  return (
    <Group className={glow ? "guide-scope" : ""} title={<span className="text-attn-ink">建议转产品经理 Agent</span>} aside={<Score q={q} />}>
      <div className="row attn-edge !items-start !py-3">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          {q.evidence.map((e, i) => <p key={i} className="text-[13px] leading-5 text-ink-2">{L.scrub(e.summary)}</p>)}
          {ready ? (
            <>
              <p className="flex items-center gap-2 text-[12px] text-ink-2">升级说明 {note === v.escalate_note && note && <AgentMark />}</p>
              <Field value={note} onChange={setNote} rows={3} label="升级说明" />
              <Notes notes={notes} />
              <div className="flex flex-wrap gap-2">
                <Act label="转产品经理 Agent" run={sign} />
                <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me)} />
              </div>
            </>
          ) : <p className="text-[13px] text-ink-2">Agent 正在起草升级说明</p>}
        </div>
      </div>
    </Group>
  );
}

// 现成产品建议（D17、D22）：业务员不签字，研发审定后转来
function ReuseLine({ v, fill }: { v: SessionView; fill: (t: string) => void }) {
  const { me } = useApp();
  const L = useLabels();
  const frozen = useFrozen();
  const r = v.reuse!;
  const name = r.product_name.replace("（模拟）", "");
  if (r.status === "pending") return <p className="text-[13px] text-ink-2">产品经理 Agent 找到现成产品（{name}），研发审定中</p>;
  if (r.status === "declined") return <p className="text-[13px] text-ink-2">研发未采用现成产品，已转接单</p>;
  if (r.status === "none") return <p className="text-[13px] text-ink-2">产品经理 Agent 已查，无现成产品，已转研发</p>;
  const approver = v.card?.note.match(/研发 \S+ 审定/)?.[0];
  return (
    <Group title="现成产品" foot={`依据：${r.basis.join("；")}`}>
      <div className="row">
        <p className="flex-1 text-[16px] font-semibold">{name}</p>
        {approver && <span className="tag">{L.scrub(approver)}</span>}
      </div>
      {r.usage && <div className="row !items-start"><span className="w-10 shrink-0 text-[13px] text-ink-2">用法</span><span className="text-[14px]">{r.usage}</span></div>}
      <div className="row !items-start">
        <span className="w-10 shrink-0 text-[13px] text-ink-2">说明</span>
        <span className="text-[14px] leading-[21px]">{r.customer_note}</span>
      </div>
      <div className="row flex-wrap">
        <button type="button" className="btn btn-plain" onClick={() => fill(r.customer_note)}>填进发给客户</button>
        {!frozen && <Act kind="quiet" label="申请解密" done="已申请解密，等研发审批" run={() => api.requestDecrypt(v.session_id, me)} />}
      </div>
    </Group>
  );
}

// v8 Q9.8：客户追问产品内部，交业务员接手（措辞中性：分不出正当与否）
function Followup({ q }: { q: Question }) {
  const { me } = useApp();
  const L = useLabels();
  return (
    <Group title={<span className="text-attn-ink">客户追问产品内部</span>} aside={<Score q={q} />}>
      <div className="row attn-edge !items-start !py-3">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <p className="text-[14px]">{L.scrub(q.title)}</p>
          {q.evidence.map((e, i) => <p key={i} className="text-[12.5px] leading-5 text-ink-2">{L.scrub(e.summary)}</p>)}
          <p className="text-[12.5px] text-ink-2">建议：讲用法与公开的合规信息；客户确有正当需要，就在推荐卡上替客户申请解密，交研发审批。配方永不对外。</p>
          <div className="flex flex-wrap gap-2">
            <Act label="接手" done="已接手" run={() => api.resolve(q.id, "take_over", me)} />
            <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me)} />
          </div>
        </div>
      </div>
    </Group>
  );
}

// V12.7 能力回流唤醒：研发新签出的判断覆盖了这位客户当时的条件，业务员签字回访；签字后按新判断重新匹配，客户端收到回访
function Recall({ q }: { q: Question }) {
  const { me } = useApp();
  const L = useLabels();
  const [note, setNote] = useState(`您之前问的问题，研发新确认了${L.product(q.refs.product_id)}可以处理，已经推荐在您的需求里，有问题随时找我。`);
  return (
    <Group title={<span className="text-attn-ink">回访过去没解决的客户</span>} aside={<Score q={q} />}>
      <div className="row attn-edge !items-start !py-3">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <p className="text-[14px]">{L.scrub(q.title)}</p>
          {q.evidence.slice(-1).map((e, i) => <p key={i} className="text-[12.5px] leading-5 text-ink-2">{L.scrub(e.summary)}</p>)}
          <Field value={note} onChange={setNote} rows={2} placeholder="回访时对客户说的话" />
          <div className="flex flex-wrap gap-2">
            <Act label="回访客户" done="已回访" disabled={!note.trim()} run={() => api.resolve(q.id, "sign", me, note)} />
            <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me)} />
          </div>
        </div>
      </div>
    </Group>
  );
}

// 客户评价（Q12）：业务员签字录入
function MarketEval({ q }: { q: Question }) {
  const { me } = useApp();
  const L = useLabels();
  const [note, setNote] = useState("");
  const [missing, setMissing] = useState<string[]>([]);
  const req = q.refs.requirement_id;
  const glow = useGlow("sign:market_eval");
  const scripted = useGuideArg("sign:market_eval");   // 回放部署：台词里的客户评价原因
  return (
    <Group className={glow ? "guide-scope" : ""} title={<span className="text-attn-ink">客户评价</span>} aside={<Score q={q} />}>
      <div className="row attn-edge !items-start !py-3">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <p className="text-[14px]">{L.scrub(q.title)}</p>
          <Field value={note} onChange={setNote} placeholder="原因（客户怎么说）" />
          {scripted && note !== scripted && <div><button type="button" className="chip glow" onClick={() => setNote(scripted)}>演示自动填入</button></div>}
          <p className="text-[12.5px] text-ink-2">不通过时，按客户反馈勾选当初没问到的条件：</p>
          <SlotPicker value={missing} onChange={setMissing} />
          <div className="flex flex-wrap gap-2">
            <Act label="通过" run={() => api.marketEval(req, "pass", note, me)} />
            <Act kind="plain" label="不通过" run={() => api.marketEval(req, "fail", note, me, missing)} />
            <Act kind="quiet" label="现在不需要" run={() => api.resolve(q.id, "dismiss", me)} />
          </div>
        </div>
      </div>
    </Group>
  );
}
