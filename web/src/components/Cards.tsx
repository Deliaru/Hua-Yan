// 三个工作台共用的组件。材质与字阶见 index.css 顶部：橙色 accent 只表示「需要决策」，实心 ink 只表示选中 / 主操作，降级用红色。
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

// 左栏卡片栈 + 中间主栏。左栏不铺底色，卡片直接浮在天空上，上下边缘交给全局渐进模糊。
export function Layout({ rail, children }: { rail: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 px-4">
      <aside className="sticky top-0 -mt-[76px] flex h-screen w-[360px] shrink-0 flex-col gap-2.5 overflow-y-auto pb-40 pt-[92px] xl:w-[380px]">
        {rail}
      </aside>
      <main className="mx-auto flex w-full min-w-0 max-w-[820px] flex-col gap-2.5 px-4 pb-44 pt-4 xl:px-8">{children}</main>
    </div>
  );
}

export function PageHead({ kicker, title }: { kicker: string; title: string }) {
  const { meta } = useApp();
  return (
    <div className="mb-3">
      <StatusBar status={meta.status} />
      <p className="on-sky mt-6 text-[14px] font-medium tracking-wide">{kicker}</p>
      <h1 className="on-sky mt-1 font-serif text-[40px] font-medium leading-tight">{title}</h1>
    </div>
  );
}

// 状态条：一枚胶囊；降级（规则、桩、离线、回放、占位种子）标红。
export function StatusBar({ status: s }: { status: RunStatus }) {
  const items: [string, boolean][] = [
    [s.simulated_data ? "模拟数据" : "真实数据", !s.simulated_data],
    [s.seeds_placeholder ? "种子占位" : "种子正式", s.seeds_placeholder],
    [`Jev ${s.system1_impl}`, s.system1_impl !== "onejev"],
    [`觉 实时 ${s.realtime_model} · 定时 ${s.scheduled_model}`, !["jue_proto", "jue_k"].includes(s.realtime_model)],
    [`抽取 ${s.extractor}`, s.extractor !== "llm"],
    [s.gateway_mock ? "角色助手离线" : "角色助手 大模型 fast", s.gateway_mock],
    [s.replay ? "记录回放" : "现场运行", s.replay],
  ];
  return (
    <div className="pill inline-flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-[13px] !rounded-[18px]">
      {items.map(([text, degraded]) => (
        <span key={text} className={`flex items-center gap-1.5 ${degraded ? "text-red-600" : "text-ink/55"}`}>
          <i className={`h-1.5 w-1.5 rounded-full ${degraded ? "bg-red-500" : "bg-emerald-500"}`} />{text}
        </span>
      ))}
    </div>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="card anim-rise">
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-[17px] font-medium">{title}</p>
        {aside}
      </div>
      {children}
    </section>
  );
}

export const Empty = ({ children }: { children: React.ReactNode }) => <p className="meta">{children}</p>;

export function RailTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <p className="on-sky mt-2 flex items-center gap-2 px-2 text-[14px] font-medium">
      {children}
      {!!count && <span className="num flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-[12px] text-white [text-shadow:none]">{count}</span>}
    </p>
  );
}

export function QuestionCard({ q }: { q: Question }) {
  const L = useLabels();
  // 证据摘要形如「fiber: 锦纶氨纶」时，把槽位 id 换成中文名
  const label = (summary: string) => summary.replace(/^(\w+): /, (_, slot) => `${L.slot(slot)}　`);
  const source = q.discoverer === "jev" ? "Jev 升级" : q.discoverer === "human" ? "人工提出" : `觉 · ${q.discoverer}`;
  return (
    <div className="card card-hover anim-rise">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="tag tag-accent">{FAMILY[q.family] ?? q.family}</span>
            <span className="meta">{source}</span>
          </div>
          <p className="mt-2.5 text-[15px] font-medium leading-[22px]">{q.title}</p>
        </div>
        {q.p_need != null && (
          <div className="shrink-0 text-right">
            <p className="num text-[24px] font-medium leading-none text-accent">{p2(q.p_need)}</p>
            <p className="meta mt-1">需要决策</p>
          </div>
        )}
      </div>
      {!!q.evidence.length && (
        <div className="mt-3 flex flex-col gap-1.5">
          {q.evidence.map((e, i) => (
            <div key={i} className="cell text-[14px] leading-5">
              <span className="text-ink/50">{label(e.summary)}</span>
              {e.quote && <span className="ml-2">「{e.quote}」</span>}
            </div>
          ))}
        </div>
      )}
      <p className="meta mt-3">
        {[q.urgency != null && `紧急度 ${p2(q.urgency)}`, q.scored_by, q.id].filter(Boolean).join(" · ")}
      </p>
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
    <div className="card anim-rise">
      <span className="tag tag-accent">待我确认</span>
      <p className="mt-2.5 text-[15px] font-medium leading-[22px]">{a.summary}</p>
      <p className="meta mt-1.5">{[a.tool, ...Object.entries(a.args).map(([k, v]) => `${k} ${String(v)}`)].join(" · ")}</p>
      <div className="mt-4 flex gap-2">
        <button disabled={busy} onClick={() => decide(true)} className="btn btn-ink flex-1">确认</button>
        <button disabled={busy} onClick={() => decide(false)} className="btn btn-soft flex-1">拒绝</button>
      </div>
    </div>
  );
}

export function PendingStack() {
  const { me, live } = useApp();
  const actions = useData(() => (live ? api.pending(me) : Promise.resolve([])), [me, live]);
  if (!live) return <div className="card"><p className="label">确认卡</p><p className="meta mt-1">离线：确认由脚本代替，已标注。</p></div>;
  return (
    <>
      <RailTitle count={actions?.length}>待我确认</RailTitle>
      {actions?.length ? actions.map((a) => <PendingCard key={a.id} a={a} />)
        : <div className="card"><Empty>暂无待确认动作。</Empty></div>}
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
        : <div className="card"><Empty>暂无待处理问题。</Empty></div>}
    </>
  );
}

export function RecCard({ card }: { card: RecommendationCard }) {
  const L = useLabels();
  return (
    <div className="sheet anim-rise">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="label">推荐产品</p>
          <p className="mt-1 font-serif text-[26px] leading-tight">{L.product(card.product_id)}</p>
        </div>
        <span className="tag">披露 {card.version}</span>
      </div>
      {card.note && <p className="meta mt-2">{card.note}</p>}
      <div className="mt-4 flex flex-col gap-2">
        {card.sections.map((s) => (
          <div key={s.ku_id} className="cell !px-4 !py-3">
            <p className="label">{s.title} · L{s.level}</p>
            <p className="mt-1 text-[15px] leading-6">{s.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// 需求条目：文本、依据（归属人 · 知识标题或「L3 转化知识」· 被引用次数）、可展开的客户原话、起草与确认人。
export function ReqItems({ view, field }: { view: RequirementView; field: "product_lang" | "chem_lang" }) {
  const L = useLabels();
  const [open, setOpen] = useState<number | null>(null);
  const req = view.requirement;
  const cited = Object.fromEntries(view.cited.map((c) => [c.ku_id, c]));
  const [drafted, confirmed] = field === "product_lang"
    ? [req.drafted_by, req.pm_confirmed_by] : [req.chem_drafted_by, req.rd_confirmed_by];
  const items = req[field];
  return (
    <div className="flex flex-col gap-2">
      <p className="meta">起草 {L.name(drafted)} · 确认 {confirmed ? L.name(confirmed) : "未确认"}</p>
      {!items.length && <Empty>暂无条目。</Empty>}
      {items.map((item, i) => (
        <div key={i} className="cell !px-4 !py-3">
          <div className="flex gap-3">
            <span className="num mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink/[.07] text-[12px] text-ink/60">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] leading-6">
                {item.slot ? <><span className="text-ink/50">{L.slot(item.slot)}　</span>{item.text.replace(/^条件：/, "")}</> : item.text}
              </p>
              {!!item.ku_refs.length && (
                <div className="mt-2 flex flex-col gap-1">
                  {item.ku_refs.map((ref) => {
                    const c = cited[ref];
                    const hidden = c.text == null;
                    return (
                      <p key={ref} className="meta flex items-center gap-1.5" title={c.text ?? "无权查看原文，只显示归属"}>
                        <i className={`h-1 w-1 rounded-full ${hidden ? "bg-ink/30" : "bg-ink/60"}`} />
                        <span className="text-ink/70">{L.name(c.owner)}</span>
                        <span>{hidden ? "L3 转化知识 · 原文不可见" : c.title}</span>
                        <span>· 被引用 {c.n_cited} 次</span>
                      </p>
                    );
                  })}
                </div>
              )}
              {!!item.quote_refs.length && (
                <button onClick={() => setOpen(open === i ? null : i)} className="meta mt-2 hover:text-ink/80">
                  客户原话 {item.quote_refs.length} {open === i ? "收起" : "展开"}
                </button>
              )}
              {open === i && item.quote_refs.map((ref) => (
                <p key={ref} className="anim-fade mt-1.5 border-l-2 border-ink/15 pl-3 text-[14px] leading-5 text-ink/70">
                  「{view.quotes[ref]}」
                </p>
              ))}
            </div>
          </div>
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
    <section className="card anim-rise">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="label">需求单 {req.id}</p>
          <p className="mt-1 text-[22px] font-medium leading-tight">{L.phen(req.phenomenon)}</p>
        </div>
        <span className={`tag ${req.status === "draft" || req.status === "pm_confirmed" ? "tag-accent" : ""}`}>{REQ_STATUS[req.status]}</span>
      </div>
      <div className="cell mt-4 !px-4 !py-3">
        <p className="label">产品方向</p>
        <p className="mt-1 text-[15px] leading-6">{req.direction}</p>
      </div>
      <div className="mb-3 mt-5">
        <Segmented size="sm" value={layer} onChange={setLayer}
                   items={[["product_lang", "L2 产品需求"], ["chem_lang", "L3 化学语言"]] as const} />
      </div>
      <ReqItems view={view} field={layer} />
      {layer === "chem_lang" && !!req.hypotheses.length && (
        <div className="mt-3 flex flex-col gap-1">
          {req.hypotheses.map((h) => <p key={h} className="meta">研发方向假设　{h}</p>)}
        </div>
      )}
      {req.public_points && (
        <div className="cell mt-3 !px-4 !py-3">
          <p className="label">对外要点 · {L.name(req.rd_confirmed_by)} 确认</p>
          <p className="mt-1 text-[15px] leading-6">{req.public_points}</p>
        </div>
      )}
      {req.sheet && (
        <div className="sheet mt-3">
          <p className="label">说明书草稿{req.product_id && ` · ${L.product(req.product_id)}`}</p>
          <p className="mt-2 text-[15px] leading-7">{req.sheet.sheet}</p>
          <p className="meta mt-2">用法　{req.sheet.usage}</p>
        </div>
      )}
    </section>
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
