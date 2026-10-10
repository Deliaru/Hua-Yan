// 三个工作台共用的组件。视觉规范见 index.css 顶部：橙色 accent 只表示「需要决策」，黑色 ink 只表示选中，降级用红色。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { PendingAction, Question, RecommendationCard, RequirementView, RunStatus } from "../types";
import { Segmented } from "./Controls";

const FAMILY: Record<string, string> = {
  escalate_need: "升级", opportunity: "机会汇聚", knowledge_conflict: "知识冲突",
  leak_risk: "泄露风险", ask_back: "回问", decrypt_request: "解密申请",
};
export const REQ_STATUS: Record<string, string> = {
  draft: "产品经理起草中", pm_confirmed: "待研发转译", rd_confirmed: "研发已确认", released: "已发布", rejected: "已失效",
};
const p2 = (x: number | null) => (x == null ? "—" : x.toFixed(2));

// 左栏卡片栈 + 中间主栏，布局同 JUE 决策台。
export function Layout({ rail, children }: { rail: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex">
      <aside className="rail rail-mask sticky top-0 -mt-16 flex h-screen w-[340px] shrink-0 flex-col gap-3 overflow-y-auto pb-36 pl-3 pr-6 pt-[76px] xl:w-[380px]">
        {rail}
      </aside>
      <main className="mx-auto w-full min-w-0 max-w-[860px] px-6 pb-40 pt-6 xl:px-10">{children}</main>
    </div>
  );
}

export function PageHead({ kicker, title }: { kicker: string; title: string }) {
  const { meta } = useApp();
  return (
    <>
      <StatusBar status={meta.status} />
      <p className="on-sky mt-5 text-[13px] tracking-wide">{kicker}</p>
      <h1 className="on-sky mt-1 font-serif text-[44px] font-medium leading-tight">{title}</h1>
    </>
  );
}

// 状态条：每页顶部；降级（规则、桩、离线、回放、占位种子）标红。
export function StatusBar({ status: s }: { status: RunStatus }) {
  const items: [string, boolean][] = [
    [s.simulated_data ? "模拟数据" : "真实数据", !s.simulated_data],
    [s.seeds_placeholder ? "种子：占位" : "种子：正式", s.seeds_placeholder],
    [`Jev：${s.system1_impl}`, s.system1_impl !== "onejev"],
    [`觉：实时 ${s.realtime_model} / 定时 ${s.scheduled_model}`, !["jue_proto", "jue_k"].includes(s.realtime_model)],
    [`抽取：${s.extractor}`, s.extractor !== "llm"],
    [s.gateway_mock ? "角色助手：离线" : "角色助手：大模型 fast", s.gateway_mock],
    [s.replay ? "记录回放" : "现场运行", s.replay],
  ];
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map(([text, degraded]) => (
        <span key={text} className={`pill px-2.5 py-0.5 text-[12px] ${degraded ? "text-red-600" : "text-black/60"}`}>{text}</span>
      ))}
    </div>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="glass mt-3 p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="text-[15px] font-medium">{title}</p>
        {aside}
      </div>
      {children}
    </section>
  );
}

export const Empty = ({ children }: { children: React.ReactNode }) => (
  <p className="text-[13px] leading-5 text-black/55">{children}</p>
);

export function RailTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <p className="mt-1 flex items-baseline gap-2 px-1 text-[13px] text-black/60">
      {children}
      {!!count && <span className="num font-semibold text-accent">{count}</span>}
    </p>
  );
}

export function QuestionCard({ q }: { q: Question }) {
  const source = q.discoverer === "jev" ? "Jev 升级" : q.discoverer === "human" ? "人工提出" : `觉 · ${q.discoverer}`;
  return (
    <div className="glass anim-rise px-4 pb-3.5 pt-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[15px] leading-[26px]">
          <span className="tag mr-1.5">{FAMILY[q.family] ?? q.family}</span>
          {q.title}
        </p>
        {q.p_need != null && <span className="num pt-0.5 text-[15px] font-semibold text-accent">{p2(q.p_need)}</span>}
      </div>
      {q.evidence.map((e, i) => (
        <p key={i} className="mt-1 line-clamp-2 text-[13px] leading-5 text-black/55">
          {e.summary}{e.quote && `「${e.quote}」`}
        </p>
      ))}
      <div className="num mt-2.5 flex flex-wrap items-center gap-1.5">
        <span className="chip">{source}</span>
        {q.urgency != null && <span className="chip">紧急度 {p2(q.urgency)}</span>}
        <span className="chip">{q.scored_by}</span>
        <span className="chip">{q.id}</span>
      </div>
    </div>
  );
}

// 确认卡：委托人的签字，是界面上唯一让结果生效的按钮。
export function PendingCard({ a }: { a: PendingAction }) {
  const { me, refresh, fail } = useApp();
  const [busy, setBusy] = useState(false);
  const decide = (approve: boolean) => {
    setBusy(true);
    (approve ? api.approve(a.id, me) : api.reject(a.id, me)).then(refresh, fail).finally(() => setBusy(false));
  };
  return (
    <div className="glass anim-rise px-4 pb-3.5 pt-3">
      <p className="text-[15px] leading-[26px]"><span className="tag mr-1.5 !text-accent">待确认</span>{a.summary}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <span className="chip">{a.tool}</span>
        {Object.entries(a.args).map(([k, v]) => <span key={k} className="chip">{k}={String(v)}</span>)}
      </div>
      <div className="mt-3 flex gap-2">
        <button disabled={busy} onClick={() => decide(true)}
                className="rounded-full bg-ink px-4 py-1 text-[13px] text-white disabled:opacity-30">确认</button>
        <button disabled={busy} onClick={() => decide(false)}
                className="rounded-full bg-white px-4 py-1 text-[13px] text-black/60 hover:text-black/80 disabled:opacity-30">拒绝</button>
      </div>
    </div>
  );
}

export function PendingStack() {
  const { me, live } = useApp();
  const actions = useData(() => (live ? api.pending(me) : Promise.resolve([])), [me, live]);
  if (!live) return <div className="glass p-4"><Empty>离线：确认由脚本代替，已标注。</Empty></div>;
  return (
    <>
      <RailTitle count={actions?.length}>待我确认</RailTitle>
      {actions?.length ? actions.map((a) => <PendingCard key={a.id} a={a} />)
        : <div className="glass p-4"><Empty>暂无待确认动作。</Empty></div>}
    </>
  );
}

export function QuestionStack({ role }: { role: string }) {
  const { me } = useApp();
  const qs = useData(() => api.questions(role, me), [role, me]);
  // Jev 升级没有概率与紧急度，视为 1（Jev 已判定）
  const score = (q: Question) => (q.p_need ?? 1) * (q.urgency ?? 1);
  const sorted = [...(qs ?? [])].sort((a, b) => score(b) - score(a));
  return (
    <>
      <RailTitle count={sorted.length}>问题队列</RailTitle>
      {sorted.length ? sorted.map((q) => <QuestionCard key={q.id} q={q} />)
        : <div className="glass p-4"><Empty>暂无待处理问题。</Empty></div>}
    </>
  );
}

export function RecCard({ card }: { card: RecommendationCard }) {
  const L = useLabels();
  return (
    <div className="sheet p-5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-serif text-[20px]">推荐 {L.product(card.product_id)}</p>
        <span className="tag">披露 {card.version}</span>
      </div>
      {card.note && <p className="mt-1 text-[12px] text-black/55">{card.note}</p>}
      {card.sections.map((s) => (
        <div key={s.ku_id} className="cell mt-3 p-3">
          <p className="flex items-center gap-2 text-[13px] text-black/60">{s.title}<span className="chip">L{s.level}</span></p>
          <p className="mt-1 text-[14px] leading-6">{s.text}</p>
        </div>
      ))}
    </div>
  );
}

// 需求条目：文本、可展开的客户原话、依据（归属人 · 知识标题或「L3 转化知识」· 被引用次数）、起草与确认人。
export function ReqItems({ view, field }: { view: RequirementView; field: "product_lang" | "chem_lang" }) {
  const L = useLabels();
  const [open, setOpen] = useState<number | null>(null);
  const req = view.requirement;
  const cited = Object.fromEntries(view.cited.map((c) => [c.ku_id, c]));
  const [drafted, confirmed] = field === "product_lang"
    ? [req.drafted_by, req.pm_confirmed_by] : [req.chem_drafted_by, req.rd_confirmed_by];
  const items = req[field];
  return (
    <div>
      <p className="mb-2 text-[12px] text-black/55">起草 {L.name(drafted)} · 确认 {confirmed ? L.name(confirmed) : "未确认"}</p>
      {!items.length && <Empty>暂无条目。</Empty>}
      {items.map((item, i) => (
        <div key={i} className="cell mt-2 p-3">
          <p className="text-[14px] leading-6">
            <span className="num mr-2 text-black/55">{i + 1}</span>
            {item.slot ? <><span className="tag mr-1.5">{L.slot(item.slot)}</span>{item.text.replace(/^条件：/, "")}</> : item.text}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {item.ku_refs.map((ref) => {
              const c = cited[ref];
              return (
                <span key={ref} className="chip" title={c.text ?? "无权查看原文，只显示归属"}>
                  {L.name(c.owner)} · {c.text != null ? c.title : "L3 转化知识"} · 被引用 {c.n_cited} 次
                </span>
              );
            })}
            {!!item.quote_refs.length && (
              <button onClick={() => setOpen(open === i ? null : i)} className="chip hover:text-black/90">
                客户原话 {item.quote_refs.length} {open === i ? "⌃" : "⌄"}
              </button>
            )}
          </div>
          {open === i && item.quote_refs.map((ref) => (
            <p key={ref} className="anim-fade mt-2 border-l-2 border-black/15 pl-3 text-[13px] leading-5 text-black/70">
              {view.quotes[ref]} <span className="text-black/55">· {ref}</span>
            </p>
          ))}
        </div>
      ))}
    </div>
  );
}

export function RequirementPanel({ id, initial = "product_lang" }: { id: string; initial?: "product_lang" | "chem_lang" }) {
  const { me } = useApp();
  const L = useLabels();
  const [layer, setLayer] = useState(initial);
  const view = useData(() => api.requirement(id, me), [id, me]);
  if (!view) return null;
  const req = view.requirement;
  return (
    <Section title={`${req.id} · ${L.phen(req.phenomenon)}`} aside={<span className="chip">{REQ_STATUS[req.status]}</span>}>
      <p className="text-[14px] leading-6"><span className="text-black/55">产品方向　</span>{req.direction}</p>
      <div className="mt-3">
        <Segmented size="sm" value={layer} onChange={setLayer}
                   items={[["product_lang", "L2 产品需求"], ["chem_lang", "L3 化学语言"]] as const} />
      </div>
      <div className="mt-2"><ReqItems view={view} field={layer} /></div>
      {layer === "chem_lang" && req.hypotheses.map((h) => (
        <p key={h} className="mt-2 text-[13px] leading-5 text-black/60">研发方向假设：{h}</p>
      ))}
      {req.public_points && (
        <p className="mt-3 text-[14px] leading-6">
          <span className="text-black/55">对外要点（{L.name(req.rd_confirmed_by)} 确认）　</span>{req.public_points}
        </p>
      )}
      {req.sheet && (
        <div className="sheet mt-3 p-4">
          <p className="font-serif text-[15px]">说明书草稿</p>
          <p className="mt-1 text-[14px] leading-6">{req.sheet.sheet}</p>
          <p className="mt-1 text-[13px] leading-5 text-black/60">用法：{req.sheet.usage}</p>
        </div>
      )}
      {req.product_id && <p className="mt-3 text-[12px] text-black/55">关联产品 {L.product(req.product_id)}（{req.product_id}）</p>}
    </Section>
  );
}

// 当前身份可见的需求单（不含已失效的），选中项默认为最新一张。
export function useRequirementChoice() {
  const { me } = useApp();
  const [chosen, choose] = useState<string | null>(null);
  const reqs = useData(() => api.requirements(me), [me]);
  const list = (reqs ?? []).filter((r) => r.status !== "rejected").reverse();
  const current = list.find((r) => r.id === chosen)?.id ?? list[0]?.id ?? null;
  const picker = list.length > 1 && (
    <Segmented size="sm" wrap value={current!} onChange={choose}
               items={list.map((r) => [r.id, `${r.id} · ${REQ_STATUS[r.status]}`] as const)} />
  );
  return { current, picker };
}
