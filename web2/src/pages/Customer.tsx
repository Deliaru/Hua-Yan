// V12.6 Client-View（替换原客户子工作面，L0）：手机外框里的客户端，与 CEO 面对称——一个在企业外，一个在企业顶层。
// 数据全部来自现有门面与客户层视图：「化言听懂了」读会话的结构化条件（NeedState）与开工条件；追问理由读觉的追问提示；
// 进度读 route_of 与 case_story（门面按客户层裁剪）；推荐卡读按 L0 渲染的卡片与适用范围；机理申请交产品归属研发审批；
// 主动消息读 client_messages。手机外框右侧的演示说明（需求轨迹、为什么直达研发、化言在背后做了什么）只在「演示说明」打开时出现。
import { useEffect, useState } from "react";
import { api } from "../api";
import { hhmm, useApp, useData, useLabels } from "../ctx";
import type { ClientMessage, Route, SessionView, StoryLine } from "../types";
import { OpenRouteMenu, RouteStrip, SessionConditions, useRouteHint } from "../components/Route";
import { useGlow } from "../components/Guide";
import { AuthorizedReplies } from "../components/AuthorizedReplies";
import { Group } from "../components/ui";
import { Backstory } from "../components/Backstory";
import { Narration } from "../components/Narration";

// 客户看到的状态：说清现在轮到谁
const MY_STATUS: Record<string, string> = { open: "等你补充情况", recommended: "已有推荐", escalated: "研发在处理", closed: "已记录" };
const SUBJECT: Record<string, string> = { jue: "觉", jev: "Jev", qi: "契", agent: "Agent", system: "系统" };

// 主动消息的标题：研发批准的机理说明 / 业务员按研发新判断回访 / 你提过的需求做成了新品
const headline = (m: ClientMessage, who: string) => ({
  decrypt: `${who} 给你说明了「${m.product}」的作用原理`,
  callback: `${who} 回访：研发新确认「${m.product}」能处理你之前的问题`,
  release: `你提过的需求做成了新品「${m.product}」`,
}[m.kind]);

export function Customer() {
  const { me, focus, notes } = useApp();
  const all = useData(() => api.sessions(), []) ?? [];
  const mine = all.filter((s) => s.customer_id === me).reverse();
  const messages = useData(() => api.clientMessages(me), [me]) ?? [];
  const [chosen, choose] = useState<string | null>(focus);
  useEffect(() => { if (focus) choose(focus); }, [focus]);
  const current = mine.find((s) => s.id === chosen) ?? null;
  return (
    <div className="flex items-start justify-center gap-8 px-8 pb-10 pt-6">
      <div className="flex shrink-0 flex-col items-center gap-2">
        <Phone>
          {current ? <Need key={current.id} sid={current.id} phenomenon={current.phenomenon} messages={messages.filter((m) => m.session_id === current.id)} onBack={() => choose(null)} />
            : <Home mine={mine} messages={messages} onOpen={choose} />}
        </Phone>
        <p className="text-[12px] text-ink-3">客户端 · 只看得到说明书、用法、公开案例和研发批准给你的说明</p>
      </div>
      {notes && current && <Notes sid={current.id} />}
    </div>
  );
}

function Phone({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex h-[min(840px,calc(100vh-110px))] w-[400px] flex-col overflow-hidden rounded-[52px] border-[11px] border-[#1c1c1e] bg-[#f2f2f7] shadow-[0_18px_50px_rgba(0,0,0,.18)]">
      <div className="flex h-[34px] shrink-0 items-center justify-between bg-white px-7 text-[12px] font-semibold">
        <span>化言</span><i className="h-[22px] w-[96px] rounded-full bg-[#1c1c1e]" /><span>传化功能化学</span>
      </div>
      {children}
    </div>
  );
}

// 首页：主动消息在上，我的需求在下
function Home({ mine, messages, onOpen }: { mine: { id: string; status: string; phenomenon: string | null; origin: string; sales_id: string | null }[];
  messages: ClientMessage[]; onOpen: (sid: string) => void }) {
  const { me } = useApp();
  const L = useLabels();
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="flex items-center justify-between bg-white px-5 pb-3 pt-2">
        <div><p className="text-[22px] font-bold">你好，{L.name(me)}</p><p className="text-[12.5px] text-ink-2">说一次现象就够，剩下的化言来问</p></div>
        <OpenRouteMenu customer={me} onOpened={(sid) => onOpen(sid)} />
      </div>
      {!!messages.length && <div className="px-4 pt-4">
        <p className="px-1 pb-1.5 text-[12px] font-semibold text-ink-2">新消息</p>
        {messages.map((m) => <button key={`${m.session_id}:${m.at}`} onClick={() => onOpen(m.session_id)}
          className="mb-2 block w-full rounded-[16px] bg-white px-4 py-3 text-left shadow-[0_1px_2px_rgba(0,0,0,.06)]">
          <p className="text-[13px] font-semibold"><span className="mr-1.5 text-accent">●</span>{headline(m, L.name(m.by))}</p>
          {m.text && <p className="mt-0.5 line-clamp-2 text-[12.5px] text-ink-2">{m.text}</p>}
        </button>)}
      </div>}
      <div className="px-4 pt-4">
        <p className="px-1 pb-1.5 text-[12px] font-semibold text-ink-2">我的需求</p>
        {mine.map((s) => <button key={s.id} onClick={() => onOpen(s.id)}
          className="mb-2 flex w-full items-center gap-3 rounded-[16px] bg-white px-4 py-3 text-left shadow-[0_1px_2px_rgba(0,0,0,.06)]">
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] font-semibold">{s.phenomenon ? L.phen(s.phenomenon) : "尚未识别现象"}</span>
            <span className="block text-[12px] text-ink-2">{s.origin === "customer" ? "自助" : `业务员 ${L.name(s.sales_id)} 陪同`}</span>
          </span>
          <span className={`shrink-0 text-[12px] ${s.status === "open" ? "font-semibold text-attn-ink" : "text-ink-2"}`}>{MY_STATUS[s.status] ?? s.status}</span>
        </button>)}
        {!mine.length && <p className="px-1 py-6 text-center text-[13px] leading-6 text-ink-3">点右上角 ＋ 新开一个需求<br />只说你看到的现象就行，比如「白地被沾色了」</p>}
      </div>
    </div>
  );
}

// 一件需求：顶部「现在在谁手上」，下面分「对话」「进度」两页
function Need({ sid, phenomenon, messages, onBack }: { sid: string; phenomenon: string | null; messages: ClientMessage[]; onBack: () => void }) {
  const { me } = useApp();
  const L = useLabels();
  const v = useData(() => api.session(sid, me), [sid, me]);
  const route = useData(() => api.route(sid, me), [sid, me]);
  const story = useData(() => api.caseStory(sid, me), [sid, me]);
  const [tab, setTab] = useState<"chat" | "track">("chat");
  if (!v) return null;
  return (
    <>
      <div className="shrink-0 border-b border-sep bg-white px-4 pb-2 pt-1">
        <div className="flex items-center gap-2">
          <button type="button" className="link !text-[14px]" onClick={onBack}>‹ 返回</button>
          <p className="min-w-0 flex-1 truncate text-center text-[15px] font-semibold">{phenomenon ? L.phen(phenomenon) : v.turns.length ? "尚未识别现象" : "描述你的问题"}</p>
          <span className="w-[42px]" />
        </div>
        {route && <Holder r={route} />}
        <div className="mt-2 grid grid-cols-2 rounded-[9px] bg-fill p-[2px] text-[13px]">
          {([["chat", "对话"], ["track", "进度"]] as const).map(([k, label]) => (
            <button key={k} type="button" onClick={() => setTab(k)}
              className={`rounded-[7px] py-1 ${tab === k ? "bg-white font-semibold shadow-[0_1px_2px_rgba(0,0,0,.1)]" : "text-ink-2"}`}>{label}</button>))}
        </div>
      </div>
      {tab === "chat" ? <Chat v={v} route={route} messages={messages} story={story?.story ?? []} />
        : <Track story={story?.story ?? []} />}
    </>
  );
}

// 像查快递一样：现在在谁手上、他拿到了什么
function Holder({ r }: { r: Route }) {
  const L = useLabels();
  const role = (["rd", "pm", "sales"] as const).find((k) => r.roles[k].state === "pending");
  const who = role ? r.roles[role].by.find((id) => id !== "pm:agent") : undefined;
  const text: Record<string, string> = {
    追问中: "化言在问清研发开工需要的条件",
    转研发中: "现有产品都不合适，化言正在把你的原话和条件整理好交研发",
    自助解决: "现有产品适用，推荐已给你",
    复用: "研发审定了一个现成产品，推荐已给你",
    交业务员: `已交给 ${L.name(r.roles.sales.by[0])} 跟进中，他看得到你说过的每一句`,
    入研: `在 ${L.name(r.roles.rd.by[0])} 手上，拿到的是你的原话和已问清的条件；研发安排试样，确认后再答复您`,
    研发不立项: "研发看过并给出了判断",
    产品机会: "和其他客户的同类需求合成一个课题，研发在跟进",
  };
  return <p className="mt-1.5 rounded-[9px] bg-[rgba(0,122,255,.08)] px-3 py-1.5 text-[12.5px] leading-[18px]">
    <span className="font-semibold text-accent">现在 · </span>
    {text[r.path] ?? r.path}{role && who && !["交业务员", "入研"].includes(r.path) ? `；现在在 ${L.name(who)} 手上` : ""}
  </p>;
}

// 进度：前情按时间倒排，每行写是谁（人 / 觉 / Jev / Agent）做的
function Track({ story }: { story: StoryLine[] }) {
  const L = useLabels();
  return (
    <ol className="flex-1 overflow-y-auto bg-white px-5 py-4">
      {[...story].reverse().map((s, i) => (
        <li key={i} className="relative flex gap-3 pb-4">
          <span className={`mt-[3px] h-[11px] w-[11px] shrink-0 rounded-full ${i === 0 ? "bg-accent ring-4 ring-[rgba(0,122,255,.15)]" : "bg-[#c7c7cc]"}`} />
          {i < story.length - 1 && <i className="absolute bottom-0 left-[5px] top-[16px] w-px bg-sep" />}
          <div className="min-w-0">
            <p className={`text-[13px] leading-[19px] ${i === 0 ? "font-semibold" : ""}`}>
              {s.subject === "human" ? s.role === "customer" ? "你" : L.name(s.who) : s.who === "huayan" ? "化言" : SUBJECT[s.subject] ?? s.subject}
              <span className="font-normal text-ink-2"> {L.scrub(s.text)}</span></p>
            <p className="num text-[11px] text-ink-3">{s.ts.slice(5, 10)} {hhmm(s.ts)}</p>
          </div>
        </li>
      ))}
      {!story.length && <p className="text-center text-[13px] text-ink-3">说出现象后，这里像查快递一样列出每一步</p>}
    </ol>
  );
}

// 「化言听懂了」：研发开工要的条件逐项亮起，没问清的标「待问」并写为什么要问
function Understood({ v }: { v: SessionView }) {
  const { me } = useApp();
  const L = useLabels();
  const r = useData(() => api.sessionReadiness(v.session_id, me), [v.session_id, me, v.turns.length]);
  const [open, setOpen] = useState(true);
  if (!r?.phenomenon) return null;
  const required = new Set(r.items.map((c) => c.slot));
  const extra = v.slots.filter((s) => s.status === "filled" && !required.has(s.slot));
  const t = v.temperature;
  return (
    <div className="mx-3 mt-3 rounded-[16px] bg-white px-4 py-2.5 shadow-[0_1px_2px_rgba(0,0,0,.06)]">
      <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => setOpen(!open)}>
        <span className="text-[13.5px] font-semibold">化言听懂了</span>
        <span className="text-[12.5px] text-ink-2">「{L.phen(r.phenomenon)}」· {r.n_known}/{r.n_required} 项已明确</span>
        <span className="ml-auto text-[12px] text-ink-3">{open ? "收起" : "展开"}</span>
      </button>
      {open && <div className="mt-1.5 flex flex-col gap-1">
        {r.items.map((c) => (
          <div key={c.slot} className="flex items-baseline gap-2 text-[12.5px]">
            <span className={`h-[7px] w-[7px] shrink-0 rounded-full ${c.value ? "bg-[#30c25b]" : "bg-attn"}`} />
            <span className="w-[64px] shrink-0 text-ink-2">{c.label}</span>
            {c.value ? <span className="min-w-0 flex-1"><b className="font-semibold">{c.value}</b>{c.quote && <span className="text-ink-3"> ← 「{c.quote}」</span>}</span>
              : <span className="text-attn-ink">待问</span>}
          </div>
        ))}
        {extra.map((s) => (
          <div key={s.slot} className="flex items-baseline gap-2 text-[12.5px]">
            <span className="h-[7px] w-[7px] shrink-0 rounded-full bg-[#30c25b]" /><span className="w-[64px] shrink-0 text-ink-2">{L.slot(s.slot)}</span>
            <span className="min-w-0 flex-1"><b className="font-semibold">{s.value}</b><span className="text-ink-3"> ← 「{s.quote}」</span></span>
          </div>
        ))}
        {t && <div className="flex items-baseline gap-2 text-[12.5px]">
          <span className={`h-[7px] w-[7px] shrink-0 rounded-full ${t.status === "filled" ? "bg-[#30c25b]" : "bg-ink-3"}`} /><span className="w-[64px] shrink-0 text-ink-2">工艺温度</span>
          <span className="min-w-0 flex-1">{t.status === "filled" && t.celsius ? <b className="font-semibold">{t.celsius[0] === t.celsius[1] ? `${t.celsius[0]}℃` : `${t.celsius[0]}—${t.celsius[1]}℃`}</b>
            : <span className="text-ink-2">你说不清楚，已记下</span>}<span className="text-ink-3"> ← 「{t.quote}」</span></span>
        </div>}
      </div>}
    </div>
  );
}

// 对话：客户的话、化言的回答与追问（带为什么问）、研发的回问、推荐卡、研发批准的说明、试样反馈；末尾是输入框
function Chat({ v, route, messages, story }: { v: SessionView; route: Route | null; messages: ClientMessage[]; story: StoryLine[] }) {
  const { refresh, me } = useApp();
  const L = useLabels();
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const line = useData(() => api.routeNext(v.session_id), [v.session_id, v.turns.length])?.text ?? null;
  const readiness = useData(() => api.sessionReadiness(v.session_id, me), [v.session_id, me, v.turns.length]);
  const send = (text: string) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr(null);
    api.addTurn(v.session_id, "customer", text.trim()).then(() => { setSaid(""); refresh(); },
      (e) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
  };
  const replies = (turnId: string) => v.replies.filter((r) => r.turn_id === turnId);
  const canQuote = v.status === "recommended" && route?.path === "自助解决";
  const last = v.turns[v.turns.length - 1];
  const hint = last?.speaker === "assistant" ? v.hints.find((h) => last.text === h.ask_text) ?? v.hints[0] : undefined;
  const required = new Set(readiness?.items.map((c) => c.slot) ?? []);
  const rd = route?.roles.rd.by[0];
  const handed = !!v.requirement || route?.path === "入研" || route?.path === "产品机会";
  const glowSay = useGlow("say"), glowQuote = useGlow("quote");   // 演示讲解：轮到客户说下一句 / 点「我要报价」
  return (
    <>
      <div className="flex-1 overflow-y-auto pb-3">
        <Understood v={v} />
        <ol className="flex flex-col gap-2 px-3 pt-3">
          {!v.turns.length && <li className="px-2 text-center text-[13px] leading-5 text-ink-2">只说你看到的现象就行，比如「白地被沾色了」。研发开工要知道的条件，化言会一项项问你。</li>}
          {v.turns.map((t) => (
            <li key={t.id} className="anim-rise flex flex-col gap-1">
              <div className={`flex ${t.speaker === "customer" ? "justify-end" : ""}`}>
                <p className={`max-w-[82%] rounded-[18px] px-3.5 py-2 text-[14px] leading-[20px] ${
                  t.speaker === "customer" ? "bg-accent text-white" : t.speaker === "assistant" ? "bg-white shadow-[0_0_0_1px_rgba(176,80,10,.25)]" : "bg-white"}`}>
                  {t.speaker === "sales" && <span className="mr-1 text-[11px] font-semibold text-accent">业务员</span>}
                  {t.speaker === "assistant" && <span className="mr-1 text-[11px] font-semibold text-attn-ink">化言想确认</span>}{t.text}</p>
              </div>
              {t === last && hint && <p className="ml-2 max-w-[82%] text-[11.5px] leading-4 text-ink-2">
                为什么问：{required.has(hint.slot) ? `研发处理「${L.phen(readiness?.phenomenon)}」前必须知道${hint.label}，现在问清，研发就不用再回头找你`
                  : `${hint.label}会决定推荐哪个产品`}<span className="text-ink-3"> · 觉打分 {hint.p_need.toFixed(2)}（{L.scorer(hint.scored_by)}）</span></p>}
              {replies(t.id).map((r, j) => (
                <p key={j} className="max-w-[82%] rounded-[18px] bg-white px-3.5 py-2 text-[13.5px] leading-[20px]">
                  <span className="mr-1 text-[11px] font-semibold text-ink-2">化言</span>{r.text}</p>
              ))}
              <span className={`num px-2 text-[10.5px] text-ink-3 ${t.speaker === "customer" ? "text-right" : ""}`}>{hhmm(t.ts)}</span>
            </li>
          ))}
        </ol>
        {!v.card && route && ["转研发中", "入研", "产品机会"].includes(route.path) && (   // 自助客户不对着沉默干等
          <p className="mx-3 mb-1 max-w-[82%] rounded-[18px] bg-white px-3.5 py-2 text-[13.5px] leading-[20px]">
            <span className="mr-1 text-[11px] font-semibold text-ink-2">化言</span>
            按你说的条件，现有产品都不合适。你的原话和已问清的条件会直接交给研发，有进展会在这里告诉你。</p>)}
        {v.asks.slice(0, 1).map((a) => (    // 研发的回问直达客户，一次问一条
          <p key={a.question_id} className="mx-3 mb-1 max-w-[82%] rounded-[18px] bg-white px-3.5 py-2 text-[13.5px] leading-[20px] shadow-[0_0_0_1px_rgba(176,80,10,.25)]">
            <span className="mr-1 text-[11px] font-semibold text-attn-ink">研发想确认</span>{a.ask_text}</p>
        ))}
        {v.card && <Card v={v} story={story} />}
        {messages.map((m) => (
          <div key={m.at} className="mx-3 mt-2 rounded-[16px] bg-white px-4 py-3 shadow-[0_0_0_1px_rgba(0,122,255,.25)]">
            <p className="text-[12px] font-semibold text-accent">{headline(m, L.name(m.by))}</p>
            {m.text && <p className="mt-1 whitespace-pre-wrap text-[13.5px] leading-[20px]">{m.text}</p>}
          </div>
        ))}
        <div className="mx-3"><AuthorizedReplies sessionId={v.session_id} /></div>
        {(v.card || handed) && <div className="mx-3 mt-2 rounded-[16px] bg-white px-4 py-2.5">
          <p className="text-[12.5px] text-ink-2">{handed ? `试样或用过之后告诉我们结果，原话会直接到 ${L.name(rd)} 的需求单上` : "用过之后告诉我们效果"}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <button type="button" className="chip" disabled={busy} onClick={() => send("试过了，效果不错")}>试过了，效果不错</button>
            <button type="button" className="chip" disabled={busy} onClick={() => setSaid("试过了，还是有问题：")}>还是有问题…</button>
          </div>
        </div>}
        {canQuote && (
          <div className="mx-3 mt-2 flex items-center gap-3 rounded-[16px] bg-white px-4 py-2.5">
            <span className="flex-1 text-[12.5px] text-ink-2">想采购或要报价？化言交给你的业务员，他看得到你说过的每一句。</span>
            <button className={`btn btn-plain ${glowQuote ? "glow" : ""}`} disabled={busy} onClick={() => send("这个产品想要个报价")}>我要报价</button>
          </div>
        )}
      </div>
      {err && <p role="alert" className="shrink-0 bg-white px-4 pt-1 text-[12px] text-danger">{err}</p>}
      <form onSubmit={(e) => { e.preventDefault(); send(said); }} className="flex shrink-0 items-center gap-2 border-t border-sep bg-white px-3 pb-5 pt-2">
        <input value={said} onChange={(e) => setSaid(e.target.value)} aria-label="我说" disabled={busy}
               placeholder="描述现象，或回答化言的问题……" className={`min-w-0 flex-1 rounded-full bg-fill px-3.5 py-1.5 text-[14px] outline-none placeholder:text-ink-3 ${glowSay && !said ? "glow" : ""}`} />
        {line && !said && <button type="button" className={`chip ${glowSay ? "glow" : ""}`} disabled={busy} onClick={() => setSaid(line)}>演示填入</button>}
        <button className={`btn btn-primary !h-[30px] !rounded-full !px-3.5 ${glowSay && said ? "glow" : ""}`} disabled={busy || !said.trim()}>{busy ? "……" : "发送"}</button>
      </form>
    </>
  );
}

// 推荐卡：L0 只有说明书、用法、公开案例（门面按层级裁剪）；写清按你的哪些条件推荐、适用到哪里，超出范围会请研发确认；可申请了解原理
function Card({ v, story }: { v: SessionView; story: StoryLine[] }) {
  const { me, refresh, fail } = useApp();
  const L = useLabels();
  const card = v.card!;
  const kinds = new Set(story.map((s) => s.kind));
  const [open, setOpen] = useState(false);
  const known = v.slots.filter((s) => s.status === "filled");
  const ask = () => api.requestDecrypt(v.session_id, me).then(refresh, fail);
  return (
    <div className="mx-3 mt-2 overflow-hidden rounded-[16px] bg-white shadow-[0_1px_2px_rgba(0,0,0,.06)]">
      <div className="bg-[rgba(48,194,91,.1)] px-4 py-2.5">
        <p className="text-[11.5px] font-semibold text-[#1d7a3a]">化言推荐</p>
        <p className="text-[17px] font-semibold">{L.product(card.product_id)}</p>
        {!!known.length && <p className="mt-0.5 text-[12px] text-ink-2">按你说的 {known.map((s) => `${L.slot(s.slot)}「${s.value}」`).join("、")}</p>}
      </div>
      <div className="px-4 py-2 text-[12.5px] leading-[19px]">
        {card.note ? <p><span className="font-semibold">适用范围：</span>{L.scrub(card.note).replace(/；?能力依据 \S+/, "")}</p>
          : <p><span className="font-semibold">适用范围：</span>按说明书写明的适用条件</p>}
        <p className="text-ink-2">超出这个范围的情况，化言会请研发确认，不会直接推给你。</p>
      </div>
      <button type="button" className="link block w-full border-t border-sep px-4 py-2 text-left !text-[12.5px]" onClick={() => setOpen(!open)}>
        {open ? "收起说明书与用法" : `看说明书与用法（${card.sections.length} 项）`}</button>
      {open && card.sections.map((s) => (
        <div key={s.ku_id} className="border-t border-sep px-4 py-2">
          <p className="text-[11.5px] text-ink-2">{s.title}</p><p className="text-[13px] leading-[19px]">{s.text}</p>
        </div>
      ))}
      <div className="flex items-center gap-2 border-t border-sep px-4 py-2 text-[12.5px]">
        {kinds.has("decrypt_approve") ? <span className="text-ink-2">研发已批准给你说明原理，见下方</span>
          : kinds.has("decrypt_request") ? <span className="text-ink-2">已申请了解原理，等产品的研发审批</span>
          : <><span className="flex-1 text-ink-2">想知道它为什么有效？研发审批后单独说明给你</span>
              <button type="button" className="btn btn-plain !h-[26px]" onClick={ask}>申请了解原理</button></>}
      </div>
    </div>
  );
}

// 手机外框右侧的演示说明：需求轨迹、为什么直达研发、化言在背后做了什么、研发开工要的条件、开场提示
function Notes({ sid }: { sid: string }) {
  const { me } = useApp();
  const v = useData(() => api.session(sid, me), [sid, me]);
  const route = useData(() => api.route(sid, me), [sid, me]);
  const hint = useRouteHint(me, v?.turns.find((t) => t.speaker === "customer")?.text);
  return (
    <div className="flex min-w-0 max-w-[620px] flex-1 flex-col gap-5">
      <p className="text-[12.5px] leading-5 text-ink-2"><span className="tag mr-2">L0 · 客户</span>
        客户只看得到说明书、用法和公开案例；化言只问会改变推荐或研发判断的条件。右侧是演示说明，真实客户看不到。</p>
      <RouteStrip objectId={sid} />
      <Backstory id={sid} title="化言在背后做了什么" />
      <Narration id={sid} />
      {route?.why && <WhyRd r={route} sid={sid} />}
      <SessionConditions sessionId={sid} />
      {hint && <Group title={`开场 ${hint.id} · 接下来去哪里看`}><div className="row text-[13px] leading-5">{hint.hint}</div></Group>}
    </div>
  );
}

// 为什么这份需求能直达研发：三个条件逐条摆出依据（客户原话、开工条件、被排除的现有产品与 Jev 概率），再说明中间为什么不需要人签字
function WhyRd({ r, sid }: { r: Route; sid: string }) {
  const { me } = useApp();
  const L = useLabels();
  const ready = useData(() => api.sessionReadiness(sid, me), [sid, me]);
  const w = r.why!;
  const auto = w.by === "jue:auto";
  const n = w.excluded.length + w.candidates.length;
  const pct = (p: number) => `${Math.round(p * 100)}%`;
  const Step = ({ i, title, children }: { i: number; title: string; children: React.ReactNode }) => (
    <div className="flex gap-3 px-5 py-3">
      <span className="mt-[1px] flex h-[20px] w-[20px] shrink-0 items-center justify-center rounded-full bg-[#30c25b] text-[11px] font-semibold text-white">✓</span>
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-semibold">{i}. {title}</p>
        <div className="mt-1 text-[13px] leading-[21px] text-ink-2">{children}</div>
      </div>
    </div>
  );
  return (
    <section className="group">
      <div className="border-b border-sep px-5 py-3">
        <p className="text-[16px] font-semibold">为什么这份需求可以直接交给研发？</p>
        <p className="mt-0.5 text-[13px] text-ink-2">三个条件同时满足，{auto ? "觉按决策模板自动交给研发，中间不需要任何人签字或转述" : `业务员 ${L.name(w.by)} 签字后交给研发`}。</p>
      </div>
      <div className="divide-y divide-[var(--color-sep)]">
        <Step i={1} title="客户说清楚了是什么问题">
          化言把客户原话「{r.quote}」识别为「{L.phen(w.phenomenon)}」类问题，原话会原样跟着需求走到研发。
        </Step>
        <Step i={2} title="研发开工需要的条件已经齐了">
          {ready ? <>这类问题研发开工前必须知道 {ready.n_required} 项，现在 {ready.n_known} 项都已明确
            {ready.n_asked_by_jue ? `，其中 ${ready.n_asked_by_jue} 项是觉直接向客户追问所得` : ""}。研发拿到后不用再回头找人补问。</> : "……"}
        </Step>
        <Step i={3} title="现有产品都解决不了">
          {n ? <>声明能处理「{L.phen(w.phenomenon)}」的已发布产品有 {n} 个，按客户的条件逐一核对：</> : <>按客户的现象和条件，现有产品里没有一个声明能处理。</>}
          {!!n && (
            <ul className="mt-1.5 flex flex-col gap-1">
              {w.excluded.map((x) => (
                <li key={x.product_id} className="rounded-[8px] bg-bg px-3 py-1.5">
                  <span className="font-semibold text-ink">{L.product(x.product_id)}</span>
                  <span className="ml-2 text-danger">不适用</span>
                  {x.mismatch.map((m) => (
                    <span key={m.slot} className="block text-[12.5px]">
                      {L.slot(m.slot)}：说明书写明只适用于 {m.allowed.join("、")}，客户的是 <b className="font-semibold text-ink">{m.value}</b></span>
                  ))}
                </li>
              ))}
              {w.candidates.map((c) => (
                <li key={c.product_id} className="rounded-[8px] bg-bg px-3 py-1.5">
                  <span className="font-semibold text-ink">{L.product(c.product_id)}</span>
                  <span className="ml-2">条件不冲突，但 Jev 判断适合的概率只有 {pct(c.p)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1.5">Jev 判断「现有产品都不合适」的概率 <b className="num font-semibold text-ink">{pct(w.p_none)}</b>
            {w.scored_by !== "onejev" && <span className="tag tag-warn ml-2">{L.scorer(w.scored_by)} · 降级</span>}</p>
        </Step>
      </div>
      <div className="border-t border-sep bg-[#fafafb] px-5 py-3 text-[13px] leading-[21px] text-ink-2">
        <p className="font-semibold text-ink">中间为什么不需要人？</p>
        <p>· <b className="font-semibold text-ink">不经业务员</b>：过去业务员签字升级，只是把上面这三条判断再搬运一遍；转述还会丢信息。</p>
        <p>· <b className="font-semibold text-ink">不用产品经理逐单转述</b>：产品经理 Agent 在后台把客户原话转成产品需求，每一句都带着客户原话。</p>
        <p>· <b className="font-semibold text-ink">真正的判断留给研发</b>：是否立项由研发决定；若研发判断某个现有产品其实适用，产品经理会扩展它的适用范围，下次同类问题客户就能直接拿到推荐。</p>
      </div>
    </section>
  );
}
