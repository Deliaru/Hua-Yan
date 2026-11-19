// V12.18 钉钉式工作面：化言像一位同事，把轮到你的事一条条推给你（觉提出、Agent 准备好、你处理完都在这条会话里）。
// 化言只是这些事的出口，每条都写清来源（觉发现 / 谁的 Agent 准备好了），不替人做决定；点「去处理」在中间打开原来的审阅与签字区。
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ACTION, hhmm, useApp, useData, useLabels } from "../ctx";
import type { Question, RequirementSummary, SessionSummary } from "../types";
import { useInbox } from "./Inbox";
import { myTurn, todo, usePlay } from "./Play";
import { WHY, useAsk, useObject } from "./Task";

// 「弹力面料与整理研发刘工」→「刘工」：同事之间这么叫
const short = (name: string) => name.replace("（模拟）", "").slice(-2);

function Avatar() {
  return <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] bg-gradient-to-br from-[#2f7cf6] to-[#5856d6] text-[14px] font-semibold text-white">化</span>;
}

// 这条事从哪来：觉发现的，谁的 Agent 准备好的
function source(q: Question, me: string, name: (id: string) => string) {
  const found = q.discoverer.startsWith("jue") ? "觉发现" : "流程推进";
  const owner = !q.owner_id ? "" : q.owner_id === me ? "你的 Agent" : name(q.owner_id);
  return q.prepared_at ? `${found} · ${owner}准备好了` : `${found} · ${owner}正在准备`;
}

function Bubble({ q, time, src, children, tone = "white" }: {
  q?: Question; time?: string; src?: string; children: React.ReactNode; tone?: "white" | "done";
}) {
  const { me } = useApp();
  const L = useLabels();
  return (
    <div className="flex gap-2 px-3 py-1.5">
      <Avatar />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-ink-3">{["化言", time && hhmm(time), src ?? (q && source(q, me, L.name))].filter(Boolean).join(" · ")}</p>
        <div className={`mt-0.5 rounded-[4px_12px_12px_12px] px-3 py-2 text-[13px] leading-[19px] ${tone === "done" ? "bg-fill text-ink-2" : "bg-white shadow-[0_1px_2px_rgba(0,0,0,.08)]"}`}>
          {children}
        </div>
      </div>
    </div>
  );
}

const Go = ({ on, glow, onClick }: { on: boolean; glow: boolean; onClick: () => void }) => (
  <button type="button" onClick={onClick}
          className={`mt-2 w-full rounded-[8px] py-1.5 text-[13px] font-semibold ${on ? "bg-fill text-ink-2" : "bg-accent text-white"} ${glow && !on ? "glow" : ""}`}>
    {on ? "正在处理 →" : "去处理"}</button>
);

// handoffs：觉从客户自助对话转给业务员、客户还在等回话的会话（只有业务员有）
export function HuayanFeed({ selected, guided, select, reqs, handoffs: allHandoffs = [], chosen, openHandoff }: {
  selected: string | null; guided?: string | null; select: (q: Question) => void; reqs: RequirementSummary[];
  handoffs?: SessionSummary[]; chosen?: string | null; openHandoff?: (id: string) => void;
}) {
  const { me, refresh, fail, version, go } = useApp();
  const L = useLabels();
  const inbox = useInbox();
  const { preparing, failures } = inbox;
  // 历史只留人处理过的（觉自动答掉的不算）
  const done = (useData(() => api.doneQuestions(me), [me, version]) ?? []).filter((q) => q.resolution && !/^(jue|system)/.test(q.resolution.by));
  const [older, setOlder] = useState(false);
  const base = useObject(reqs);
  const object = (q: Question) => {   // 同一种现象常有好几张单：带上客户，分得清是哪一单
    const r = reqs.find((x) => x.id === (q.refs.requirement_id ?? (q.refs.requirement_ids ?? "").split(",")[0]));
    return r?.customer_ids.length ? `${base(q)} · ${r.customer_ids.map(L.name).join("、")}` : base(q);
  };
  const end = useRef<HTMLDivElement>(null);
  const hey = short(L.name(me));
  const ask = useAsk();
  // 业务流程演示里轮到我的这一步指着哪件事：那条消息的「去处理」发亮；它不是一条要定的事（如录试样）就单独推一条
  const play = usePlay();
  const turn = myTurn(play, me).mine;
  const f = turn?.focus ?? null;
  const hits = (q: Question) => !!f && (q.id === f || q.refs.session_id === f || q.refs.requirement_id === f
    || (q.refs.requirement_ids ?? "").split(",").includes(f));
  // 处理过的收起只露最近 2 条；在准备的合成一条放最后；等你定的一件一条
  const history = done.slice().sort((a, b) => (a.resolved_at ?? "").localeCompare(b.resolved_at ?? ""));
  const shown = older ? history : history.slice(-2);
  // 业务流程演示按台词一步步走：只推当前这一步的事，其余（前面关卡留下的）先收着，免得点了岔出录制
  const script = !!play?.roadshow && !play.oneshot;
  const ready = script ? inbox.ready.filter(hits) : inbox.ready;
  const handoffs = script ? allHandoffs.filter((x) => x.id === f) : allHandoffs;
  const parked = inbox.ready.length + allHandoffs.length - ready.length - handoffs.length;
  const items = [
    ...shown.map((q) => ({ q, at: q.resolved_at ?? q.created_at, kind: "done" as const })),
    ...ready.map((q) => ({ q, at: q.prepared_at!, kind: "ready" as const })).sort((a, b) => a.at.localeCompare(b.at)),
  ];
  const loose = turn && f && !ready.some(hits) && !preparing.some(hits) && !handoffs.some((x) => x.id === f) ? turn : null;
  const open = ready.length + handoffs.length + (loose ? 1 : 0);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [items.length, preparing.length, handoffs.length, !!loose]);
  return (
    <div className="flex flex-col">
      <div className="sticky top-[41px] z-10 flex items-center gap-2 border-b border-sep bg-[#f5f6f8] px-3 py-2.5">
        <Avatar />
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold">化言</p>
          <p className="truncate text-[11.5px] text-ink-2">{open ? `有 ${open} 件等你定` : "现在没有要你定的事"}</p>
        </div>
      </div>
      <div className="flex flex-col bg-[#f5f6f8] py-2">
        {history.length > shown.length && <button type="button" className="mx-auto mb-1 rounded-full bg-white px-3 py-0.5 text-[12px] text-ink-2"
            onClick={() => setOlder(true)}>更早处理过的 {history.length - shown.length} 件</button>}
        {!items.length && !preparing.length && <p className="px-4 py-6 text-center text-[12.5px] text-ink-3">轮到你的事会从这里推给你。</p>}
        {handoffs.map((x) => (
          <Bubble key={`h:${x.id}`} time={x.last!.ts} src="觉转来">
            <p>{hey}，{L.name(x.customer_id)}在自助对话里提了商务上的事，觉把会话转给你了，前面的原话和条件都在，不用重问。</p>
            <p className="mt-1.5 font-semibold">「{x.last!.text}」</p>
            <Go on={x.id === chosen} glow={x.id === f} onClick={() => openHandoff?.(x.id)} />
          </Bubble>
        ))}
        {items.map(({ q, at, kind }) => kind === "done" ? (
          <Bubble key={`d:${q.id}`} q={q} time={at} tone="done">
            <p className="line-through decoration-ink-3/40">{ask(q)}</p>
            <p className="mt-0.5 text-[12px]">✓ {q.resolution ? `${L.name(q.resolution.by)} ${ACTION[q.resolution.action] ?? q.resolution.action}` : "已处理"} · {object(q)}</p>
          </Bubble>
        ) : (
          <Bubble key={`r:${q.id}`} q={q} time={at}>
            <p>{hey}，{WHY[q.family] ?? (q.family === "qi_grant" ? "别人那一层碰到了你签过的一条判断，但看不到原文，要你决定给不给他们用。" : "这件事要你拿个主意。")}</p>
            <p className="mt-1.5 font-semibold">{ask(q)}</p>
            <p className="text-[12px] text-ink-2">{object(q)}</p>
            <Go on={q.id === selected} glow={q.id === guided || hits(q)} onClick={() => select(q)} />
          </Bubble>
        ))}
        {!!preparing.length && <Bubble q={preparing[0]} time={preparing.at(-1)!.created_at}>
          <p>{hey}，还有 {preparing.length} 件快到你这了，Agent 在备材料，好了叫你：</p>
          <ul className="mt-1 list-disc pl-4 text-[12px] text-ink-2">{preparing.map((q) => <li key={q.id}>{object(q)}
            {failures[q.id] && <button className="ml-1 text-danger" onClick={() => api.agentRetry(q.id, me).then(refresh, fail)}>接口失败，现在重跑</button>}</li>)}</ul>
          <p className="mt-1 text-[12px] text-ink-3"><span className="typing" />准备中</p>
        </Bubble>}
        {script && parked > 0 && <p className="px-4 py-1 text-center text-[12px] text-ink-3">另有 {parked} 件不在这段演示里，先放着（工作台里能看到）。</p>}
        {loose && <Bubble src="流程推进">
          <p>{hey}，轮到你了：<b>{todo(loose)}</b>。{loose.brief}。</p>
          <Go on={false} glow onClick={() => go(me.split(":")[0], loose.focus)} />
        </Bubble>}
        <div ref={end} />
      </div>
    </div>
  );
}

// 侧栏两页：化言的消息 / 原来的需求单与我的判断（工作台）
export function ImSide({ feed, desk, badge }: { feed: React.ReactNode; desk: React.ReactNode; badge?: number }) {
  const [tab, setTab] = useState<"feed" | "desk">("feed");
  return (
    <div className="flex flex-col">
      <div className="sticky top-0 z-20 flex items-center gap-0.5 border-b border-sep bg-white px-2 py-1.5">
        <span className="col-head !h-auto !border-0 !bg-none !bg-transparent !px-1.5"><span className="col-no">1</span></span>
        {([["feed", "消息"], ["desk", "工作台"]] as const).map(([k, label]) => (
          <button key={k} type="button" onClick={() => setTab(k)}
                  className={`relative h-7 flex-1 rounded-[7px] text-[13px] ${tab === k ? "bg-fill font-semibold" : "text-ink-2 hover:bg-fill"}`}>
            {label}{k === "feed" && !!badge && <span className="absolute right-3 top-1 h-4 min-w-4 rounded-full bg-danger px-1 text-[10.5px] leading-4 text-white">{badge}</span>}
          </button>
        ))}
      </div>
      {tab === "feed" ? feed : <div className="pt-2">{desk}</div>}
    </div>
  );
}
