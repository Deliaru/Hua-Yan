// 客户子工作面（L0，v6）：客户自助描述问题，觉直接追问研发开工需要的条件（E1），能解决的当场拿到推荐卡（说明书 + 公开案例）；
// 「我要报价」交给归属业务员；解决不了的需求带原话直达研发。右栏「这件事接下来会去哪」来自 route_of。客户没有 Agent。
import { useEffect, useState } from "react";
import { api } from "../api";
import { SESSION_STATUS, Side, hhmm, useApp, useData, useLabels } from "../ctx";
import type { Route, SessionView } from "../types";
import { OpenRouteMenu, RouteStrip, SessionConditions, useRouteHint } from "../components/Route";
import { useGlow } from "../components/Guide";
import { EmptyState, Group, PageHead, SideHead } from "../components/ui";

export function Customer() {
  const { me, focus } = useApp();
  const L = useLabels();
  const all = useData(() => api.sessions(), []) ?? [];
  const mine = all.filter((s) => s.customer_id === me).reverse();
  const [chosen, choose] = useState<string | null>(focus);
  useEffect(() => { if (focus) choose(focus); }, [focus]);
  const current = mine.find((s) => s.id === chosen) ?? mine[0] ?? null;
  return (
    <>
      <Side>
        <SideHead aside={<OpenRouteMenu customer={me} onOpened={(sid) => choose(sid)} />}>我的需求</SideHead>
        {mine.map((s) => (
          <button key={s.id} onClick={() => choose(s.id)} className={`side-row ${s.id === current?.id ? "on" : ""}`}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[13px] font-semibold">{s.phenomenon ? L.phen(s.phenomenon) : "尚未识别现象"}</span>
              <span className="shrink-0 text-[12px] text-ink-2">{SESSION_STATUS[s.status] ?? s.status}</span>
            </div>
            <p className="truncate text-[12px] text-ink-2">{s.origin === "customer" ? "自助" : `业务员 ${L.name(s.sales_id)} 陪同`}</p>
          </button>
        ))}
        {!mine.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">点 ＋ 新开一个需求</p>}
      </Side>
      {current ? <Desk key={current.id} sid={current.id} />
        : <EmptyState title="向化言描述你的问题" text="点侧栏「我的需求」右侧的 ＋，选一个开场（A–D），或直接用自己的话描述现象。客户只需说现象，研发开工需要的条件由觉来问。" />}
    </>
  );
}

function Desk({ sid }: { sid: string }) {
  const { me } = useApp();
  const L = useLabels();
  const v = useData(() => api.session(sid, me), [sid, me]);
  const route = useData(() => api.route(sid, me), [sid, me]);
  const hint = useRouteHint(me, v?.turns.find((t) => t.speaker === "customer")?.text);
  if (!v) return null;
  return (
    <>
      <div className="mr-[372px]">
        <div className="mx-auto flex max-w-[1000px] flex-col gap-5 px-8 pb-28 pt-7">
          <PageHead title={v.turns.length ? "我的问题" : "描述你的问题"}
                    subtitle={`${L.name(me)} · ${SESSION_STATUS[v.status] ?? v.status}`} />
          <p className="text-[12.5px] leading-5 text-ink-2">
            <span className="tag mr-2">L0 · 客户</span>你只看得到说明书、用法和公开案例；化言只问会改变推荐或研发判断的条件。</p>
          <RouteStrip objectId={sid} />
          {route?.why && <WhyRd r={route} sid={sid} />}
          <div className="grid grid-cols-[minmax(320px,6fr)_minmax(280px,5fr)] items-start gap-5">
            <Chat v={v} route={route} />
            <SessionConditions sessionId={sid} />
          </div>
          {v.card && <Card v={v} />}
        </div>
      </div>
      <aside className="inspector fixed bottom-0 right-0 top-[52px] z-10 flex w-[372px] flex-col gap-5 overflow-y-auto border-l border-sep px-5 py-5">
        {route && <Outcome r={route} />}
        {hint && (
          <Group title={`开场 ${hint.id} · 接下来去哪里看`}>
            <div className="row text-[13px] leading-5">{hint.hint}</div>
          </Group>
        )}
      </aside>
    </>
  );
}

// 对话：客户的话、知识助手的回答、觉的追问；末尾是客户输入框（「演示自动填入」只填进输入框）
function Chat({ v, route }: { v: SessionView; route: Route | null }) {
  const { refresh } = useApp();
  const [said, setSaid] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const line = useData(() => api.routeNext(v.session_id), [v.session_id, v.turns.length])?.text ?? null;
  const send = (text: string) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setErr(null);
    api.addTurn(v.session_id, "customer", text.trim()).then(() => { setSaid(""); refresh(); },
      (e) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
  };
  const replies = (turnId: string) => v.replies.filter((r) => r.turn_id === turnId);
  const canQuote = v.status === "recommended" && route?.path === "自助解决";
  const glowSay = useGlow("say"), glowQuote = useGlow("quote");   // 演示讲解：轮到客户说下一句 / 点「我要报价」
  return (
    <section>
      <div className="group-title">对话</div>
      <div className="group">
        <ol className="flex flex-col gap-2.5 px-4 py-3">
          {!v.turns.length && <li className="text-[13px] leading-5 text-ink-2">只说你看到的现象就行，比如「白地被沾色了」。</li>}
          {v.turns.map((t) => (
            <li key={t.id} className="anim-rise flex flex-col gap-1.5">
              <div className={`flex ${t.speaker === "customer" ? "justify-end" : ""}`}>
                <p className={`max-w-[85%] rounded-[14px] px-3 py-1.5 text-[14px] leading-[21px] ${
                  t.speaker === "customer" ? "bg-accent text-white"
                    : t.speaker === "assistant" ? "bg-attn-bg shadow-[0_0_0_.5px_rgba(176,80,10,.25)]" : "bg-bg"}`}>
                  {t.speaker === "sales" && <span className="mr-1 text-[11px] font-semibold text-accent">业务员</span>}
                  {t.speaker === "assistant" && <span className="mr-1 text-[11px] font-semibold text-attn-ink">化言想确认</span>}{t.text}</p>
              </div>
              {replies(t.id).map((r, j) => (
                <p key={j} className="max-w-[85%] rounded-[14px] bg-bg px-3 py-1.5 text-[13.5px] leading-[21px]">
                  <span className="mr-1 text-[11px] font-semibold text-ink-2">化言</span>{r.text}</p>
              ))}
              <span className={`num text-[10.5px] text-ink-3 ${t.speaker === "customer" ? "text-right" : ""}`}>{hhmm(t.ts)}</span>
            </li>
          ))}
        </ol>
        {v.asks.map((a) => (    // v8：研发的回问直达客户，直接在下面回答
          <p key={a.question_id} className="mx-4 mb-2 rounded-[10px] bg-attn-bg px-3 py-1.5 text-[13.5px] leading-[21px]">
            <span className="mr-1 text-[11px] font-semibold text-attn-ink">研发想确认</span>{a.ask_text}</p>
        ))}
        <form onSubmit={(e) => { e.preventDefault(); send(said); }} className="flex items-center gap-2 border-t border-sep bg-[#fafafb] py-2 pl-4 pr-2.5">
          <input value={said} onChange={(e) => setSaid(e.target.value)} aria-label="我说" disabled={busy}
                 placeholder="描述现象，或回答化言的问题……" className="min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-3" />
          {line && !said && <button type="button" className={`chip ${glowSay ? "glow" : ""}`} disabled={busy} onClick={() => setSaid(line)}>演示自动填入</button>}
          <button className={`btn btn-primary !h-[26px] !px-3 ${glowSay && said ? "glow" : ""}`} disabled={busy || !said.trim()}>{busy ? "……" : "发送"}</button>
        </form>
        {canQuote && (
          <div className="flex items-center gap-3 border-t border-sep px-4 py-2.5">
            <span className="flex-1 text-[12.5px] text-ink-2">想采购或要报价？觉会交给你的业务员，他看得到你说过的每一句。</span>
            <button className={`btn btn-plain ${glowQuote ? "glow" : ""}`} disabled={busy} onClick={() => send("这个产品想要个报价")}>我要报价</button>
          </div>
        )}
        {err && <p role="alert" className="px-4 pb-2 text-[12px] text-danger">{err}</p>}
      </div>
    </section>
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
        <Step i={1} title="你说清楚了是什么问题">
          化言把你的原话「{r.quote}」识别为「{L.phen(w.phenomenon)}」类问题，原话会原样跟着需求走到研发。
        </Step>
        <Step i={2} title="研发开工需要的条件已经齐了">
          {ready ? <>这类问题研发开工前必须知道 {ready.n_required} 项，现在 {ready.n_known} 项都已明确
            {ready.n_asked_by_jue ? `，其中 ${ready.n_asked_by_jue} 项是觉直接向你追问所得` : ""}（见下方「研发开工需要的条件」）。研发拿到后不用再回头找人补问。</> : "……"}
        </Step>
        <Step i={3} title="现有产品都解决不了">
          {n ? <>声明能处理「{L.phen(w.phenomenon)}」的已发布产品有 {n} 个，按你的条件逐一核对：</> : <>按你的现象和条件，现有产品里没有一个声明能处理。</>}
          {!!n && (
            <ul className="mt-1.5 flex flex-col gap-1">
              {w.excluded.map((x) => (
                <li key={x.product_id} className="rounded-[8px] bg-bg px-3 py-1.5">
                  <span className="font-semibold text-ink">{L.product(x.product_id)}</span>
                  <span className="ml-2 text-danger">不适用</span>
                  {x.mismatch.map((m) => (
                    <span key={m.slot} className="block text-[12.5px]">
                      {L.slot(m.slot)}：说明书写明只适用于 {m.allowed.join("、")}，你的是 <b className="font-semibold text-ink">{m.value}</b></span>
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
        <p>· <b className="font-semibold text-ink">不用产品经理逐单转述</b>：产品经理 Agent 在后台把你的原话转成产品需求，每一句都带着你的原话。</p>
        <p>· <b className="font-semibold text-ink">真正的判断留给研发</b>：是否立项由研发决定；若研发判断某个现有产品其实适用，产品经理会扩展它的适用范围，下次同类问题你在这里就能直接拿到推荐。</p>
      </div>
    </section>
  );
}

// 推荐卡：L0 只有说明书、用法、公开案例（按层级由门面裁剪）
function Card({ v }: { v: SessionView }) {
  const L = useLabels();
  const card = v.card!;
  return (
    <Group title="化言推荐" foot={card.note ? L.scrub(card.note) : "说明书、用法与公开案例；研发的机理与配方不对外。"}>
      <div className="row"><p className="flex-1 text-[17px] font-semibold">{L.product(card.product_id)}</p></div>
      {card.sections.map((s) => (
        <div key={s.ku_id} className="row !items-start">
          <div className="min-w-0">
            <p className="text-[12px] text-ink-2">{s.title}</p>
            <p className="text-[14px] leading-[21px]">{s.text}</p>
          </div>
        </div>
      ))}
    </Group>
  );
}

// 「你的问题去了哪里」：由轨迹推出
function Outcome({ r }: { r: Route }) {
  const L = useLabels();
  const rd = r.roles.rd.by[0], sales = r.roles.sales.by[0];
  const text: Record<string, string> = {
    自助解决: "你的问题已解决：现有产品适用，推荐卡在左侧。",
    交业务员: `已转给业务员 ${L.name(sales)}。他看得到你说过的每一句和已推荐的产品，不会再让你重说一遍。`,
    入研: `已直达研发 ${L.name(rd)}。中间没有人再转述一遍，研发看到的每一条都带着你的原话。`,
    研发不立项: "研发看过你的需求并给出了判断，结果见左侧。",
    产品机会: "你的需求和其他客户的同类需求合并为一个课题，研发正在跟进。",
    复用: "研发审定了一个现成产品，推荐卡在左侧。",
    追问中: "化言还在确认研发开工需要的条件，回答左侧的问题即可。",
  };
  return (
    <Group title="这件事接下来会去哪">
      <div className="row text-[14px] leading-[22px]">{text[r.path] ?? r.path}</div>
      {!!r.basis.length && r.basis.map((b) => (
        <div key={b.question_id} className="row !min-h-0 !py-2 text-[12.5px] text-ink-2">
          <span className="w-[72px] shrink-0 font-semibold text-ink">{L.family(b.family)}</span>
          <span>{b.action === "auto" ? "觉自动执行" : b.status === "open" ? "进行中" : "已处理"}</span>
        </div>
      ))}
    </Group>
  );
}
