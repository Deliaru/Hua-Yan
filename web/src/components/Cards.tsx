// 三个工作台共用的组件：外壳（侧栏 + 内容列）、分组、问题行、确认卡、推荐、需求条目。规范见 index.css 顶部。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { PendingAction, Question, RecommendationCard, RequirementSummary, RequirementView, RunStatus } from "../types";
import { Segmented } from "./Controls";
import { ChevronRight } from "./Icons";

const FAMILY: Record<string, string> = {
  escalate_need: "升级", opportunity: "机会汇聚", knowledge_conflict: "知识冲突",
  leak_risk: "泄露风险", ask_back: "回问", decrypt_request: "解密申请",
};
export const REQ_STATUS: Record<string, string> = {
  draft: "产品经理起草中", pm_confirmed: "待研发转译", rd_confirmed: "研发已确认", released: "已发布", rejected: "已失效",
};
export const pct = (x: number) => `${Math.round(x * 100)}%`;

// 外壳：工具栏下方，左侧 272 宽侧栏（窗口栏材质），右侧内容列。
export function Shell({ sidebar, children, wide }: { sidebar: React.ReactNode; children: React.ReactNode; wide?: boolean }) {
  return (
    <>
      <aside className="sidebar fixed bottom-0 left-0 top-[52px] z-20 flex w-[272px] flex-col border-r border-sep">
        <div className="flex-1 overflow-y-auto pb-4">{sidebar}</div>
        <StatusFooter />
      </aside>
      <main className="ml-[272px] pt-[52px]">
        <div className={`mx-auto flex ${wide ? "max-w-[1280px]" : "max-w-[760px]"} flex-col gap-7 px-10 pb-40 pt-8`}>{children}</div>
      </main>
    </>
  );
}

// 状态区：侧栏底部常驻，逐项写出降级（铁律 6），不用红色警报。
function StatusFooter() {
  const { meta, live } = useApp();
  const s: RunStatus = meta.status;
  const degraded = [
    s.seeds_placeholder && "种子占位",
    s.system1_impl !== "onejev" && (s.system1_impl === "mock" ? "Jev 用桩" : "Jev 大模型降级"),
    [s.realtime_model, s.scheduled_model].includes("jue_proto") && s.system1_impl !== "onejev" && "觉用规则打分",
    s.extractor !== "llm" && "抽取用规则",
    s.gateway_mock && "角色助手离线",
    s.replay && "记录回放",
  ].filter(Boolean) as string[];
  return (
    <div className="border-t border-sep px-[18px] py-3 text-[12px] leading-[18px] text-ink-2">
      <p className="flex items-center gap-1.5 font-semibold text-ink">
        <i className={`h-[7px] w-[7px] rounded-full ${degraded.length ? "border-[1.5px] border-ink-3" : "bg-[#34c759]"}`} />
        {s.replay ? "记录回放" : live ? "现场运行" : "离线演示"} · {degraded.length ? `${degraded.length} 项降级` : "全部正常"}
      </p>
      <p className="mt-0.5">{degraded.join(" · ")}</p>
      {!live && <p className="mt-0.5">确认由离线脚本代替，已标注</p>}
    </div>
  );
}

export function PageHead({ title, subtitle, aside }: { title: string; subtitle?: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[26px] font-semibold leading-8 tracking-[-0.01em]">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] text-ink-2">{subtitle}</p>}
      </div>
      {aside}
    </div>
  );
}

// 分组：标题写在分组外上方，脚注写在下方（系统设置 / iOS grouped 风格）。
export function Group({ title, aside, foot, children, flush }: {
  title?: React.ReactNode; aside?: React.ReactNode; foot?: React.ReactNode; children: React.ReactNode; flush?: boolean;
}) {
  return (
    <section>
      {(title || aside) && (
        <div className="group-title flex items-baseline justify-between gap-3">
          <span>{title}</span>{aside && <span className="font-normal">{aside}</span>}
        </div>
      )}
      {flush ? children : <div className="group">{children}</div>}
      {foot && <p className="group-foot">{foot}</p>}
    </section>
  );
}

export const Empty = ({ children }: { children: React.ReactNode }) => (
  <div className="row text-[13px] text-ink-2">{children}</div>
);

// 内容区空状态：居中一行标题、一行说明、可选主按钮。
export function EmptyState({ title, text, action }: { title: string; text: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <p className="text-[17px] font-semibold">{title}</p>
      <p className="mt-1.5 max-w-[360px] text-[13px] leading-5 text-ink-2">{text}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function SideHead({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return <div className="side-head"><span>{children}</span>{aside}</div>;
}

// 「需要决策」的概率：百分比 + 细进度条，橙色只用在这里。
export function Need({ p }: { p: number }) {
  return (
    <span className="flex shrink-0 flex-col items-end gap-1">
      <span className="num text-[12px] font-semibold text-attn-ink">{pct(p)}</span>
      <span className="h-[3px] w-8 overflow-hidden rounded-full bg-fill">
        <span className="block h-full rounded-full bg-attn" style={{ width: pct(p) }} />
      </span>
    </span>
  );
}

// 侧栏里的问题行：家族、标题、首条证据、需要决策的概率。
export function QuestionRow({ q }: { q: Question }) {
  const L = useLabels();
  const e = q.evidence[0];
  return (
    <div className="side-row" title={`${q.id} · ${L.discoverer(q.discoverer)} · ${L.scorer(q.scored_by)}`}>
      <div className="flex items-start gap-2.5">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5">
            <span className="tag tag-attn">{FAMILY[q.family] ?? q.family}</span>
            <span className="truncate text-[13px] font-semibold">{q.title}</span>
          </p>
          <p className="mt-1 line-clamp-2 text-[12px] leading-[17px] text-ink-2">
            {q.evidence.map((x) => L.evidence(x.summary)).join(" · ") || (e?.quote ?? "")}
          </p>
          <p className="mt-0.5 text-[12px] text-ink-3">{q.id} · {L.discoverer(q.discoverer)} · {L.scorer(q.scored_by)}</p>
          {q.urgency != null && <p className="text-[12px] text-ink-3">紧急度 {pct(q.urgency)}{q.refs.requirement_id ? ` · ${q.refs.requirement_id}` : ""}</p>}
          {q.status !== "open" && <p className="text-[12px] text-ink-2">{q.status === "resolved" ? "已处理" : q.status}</p>}
        </div>
        {q.p_need != null && <Need p={q.p_need} />}
      </div>
    </div>
  );
}

export function QuestionSection({ role }: { role: string }) {
  const { me } = useApp();
  const qs = useData(() => api.questions(role, me), [role, me]);
  // Jev 升级没有概率与紧急度，视为 1（Jev 已判定）
  const score = (q: Question) => (q.p_need ?? 1) * (q.urgency ?? 1);
  const sorted = [...(qs ?? [])].sort((a, b) => score(b) - score(a));
  return (
    <>
      <SideHead aside={!!sorted.length && <span className="num">{sorted.length}</span>}>问题队列</SideHead>
      {sorted.length ? sorted.map((q) => <QuestionRow key={q.id} q={q} />)
        : <p className="px-[18px] py-1 text-[13px] text-ink-3">暂无待处理问题</p>}
    </>
  );
}

// 确认卡：委托人的签字，是界面上唯一让结果生效的按钮。助手运行时出现在内容区顶部。
function PendingRow({ a }: { a: PendingAction }) {
  const { me, refresh, fail } = useApp();
  const [busy, setBusy] = useState(false);
  const decide = (approve: boolean) => {
    if (busy) return;
    setBusy(true);
    (approve ? api.approve(a.id, me) : api.reject(a.id, me)).then(refresh, fail).finally(() => setBusy(false));
  };
  return (
    <div className="row">
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-semibold">{a.summary}</p>
        <p className="mt-0.5 truncate text-[12px] text-ink-2">
          {[a.tool, ...Object.entries(a.args).map(([k, v]) => `${k} ${String(v)}`)].join(" · ")}
        </p>
        {busy && <p role="status" className="mt-1 text-[12px] text-ink-2">处理中……</p>}
      </div>
      <button disabled={busy} onClick={() => decide(false)} className="btn btn-plain">拒绝</button>
      <button disabled={busy} onClick={() => decide(true)} className="btn btn-primary">确认</button>
    </div>
  );
}

export function PendingGroup() {
  const { me, live } = useApp();
  const actions = useData(() => (live ? api.pending(me) : Promise.resolve([])), [me, live]);
  if (!actions?.length) return null;
  return (
    <Group title={<span className="text-attn-ink">待我确认 · {actions.length}</span>} foot="确认后才生效；谁确认，谁负责。">
      {actions.map((a) => <PendingRow key={a.id} a={a} />)}
    </Group>
  );
}

export function RecGroup({ card }: { card: RecommendationCard }) {
  const L = useLabels();
  return (
    <Group title="推荐" foot={card.note || undefined}>
      <div className="row !py-3.5">
        <p className="flex-1 text-[17px] font-semibold">{L.product(card.product_id)}</p>
        <span className="tag">披露：{L.version(card.version)}</span>
      </div>
      {card.sections.map((s) => (
        <div key={s.ku_id} className="row !items-start">
          <div className="min-w-0">
            <p className="text-[12px] text-ink-2">{s.title.replace(`${L.product(card.product_id)} · `, "")}</p>
            <p className="mt-0.5 text-[14px] leading-[22px]">{s.text}</p>
          </div>
        </div>
      ))}
    </Group>
  );
}

// 可展开的小节：chevron + 蓝色文字。
function Disclosure({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button onClick={() => setOpen(!open)} className="link"><ChevronRight open={open} />{label}</button>
      {open && <div className="anim-fade mt-1.5 flex flex-col gap-1 pl-4">{children}</div>}
    </div>
  );
}

// 需求条目：文本、依据（归属人 · 知识标题或「L3 转化知识」· 被引用次数）、客户原话、起草与确认人。
export function ReqItems({ view, field }: { view: RequirementView; field: "product_lang" | "chem_lang" }) {
  const L = useLabels();
  const req = view.requirement;
  const cited = Object.fromEntries(view.cited.map((c) => [c.ku_id, c]));
  const [drafted, confirmed] = field === "product_lang"
    ? [req.drafted_by, req.pm_confirmed_by] : [req.chem_drafted_by, req.rd_confirmed_by];
  const items = req[field];
  return (
    <Group foot={`起草 ${L.name(drafted)} · ${confirmed ? `确认 ${L.name(confirmed)}` : "尚未确认"}`}>
      {!items.length && <Empty>暂无条目</Empty>}
      {items.map((item, i) => {
        const owners = [...new Set(item.ku_refs.map((r) => L.name(cited[r].owner)))];
        return (
          <div key={i} className="row !items-start !py-3">
            <span className="num w-4 shrink-0 pt-px text-[13px] text-ink-3">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <p className="text-[14px] leading-[22px]">
                {item.slot ? <><span className="text-ink-2">{L.slot(item.slot)}　</span>{item.text.replace(/^条件：/, "")}</> : item.text}
              </p>
              {!!item.ku_refs.length && (
                <Disclosure label={`依据 ${item.ku_refs.length} 条 · ${owners.slice(0, 2).join("、")}${owners.length > 2 ? " 等" : ""}`}>
                  {item.ku_refs.map((ref) => {
                    const c = cited[ref];
                    return (
                      <div key={ref} className="text-[12px] leading-[18px] text-ink-2">
                        <span className="text-ink">{L.name(c.owner)}</span>
                        {c.text == null ? <span className="text-ink-3">L3 转化知识 · 原文不可见</span> : c.title}
                        <span className="text-ink-3">　被引用 {c.n_cited} 次</span>
                        {c.text != null && <p className="mt-1 whitespace-pre-wrap">{c.text}</p>}
                      </div>
                    );
                  })}
                </Disclosure>
              )}
              {!!item.quote_refs.length && (
                <Disclosure label={`客户原话 ${item.quote_refs.length}`}>
                  {item.quote_refs.map((ref) => (
                    <p key={ref} className="text-[13px] leading-5 text-ink-2">「{view.quotes[ref]}」</p>
                  ))}
                </Disclosure>
              )}
            </div>
          </div>
        );
      })}
    </Group>
  );
}

export function RequirementDetail({ id, initial = "product_lang" }: { id: string; initial?: "product_lang" | "chem_lang" }) {
  const { me } = useApp();
  const L = useLabels();
  const [layer, setLayer] = useState(initial);
  const view = useData(() => api.requirement(id, me), [id, me]);
  if (!view) return null;
  const req = view.requirement;
  return (
    <>
      <PageHead title={L.phen(req.phenomenon)}
                subtitle={[`需求单 · ${REQ_STATUS[req.status]}`, req.product_id && `关联产品 ${L.product(req.product_id)}`]
                  .filter(Boolean).join(" · ")} />
      <p className="-mt-2 text-[17px] leading-[26px]">{req.direction}</p>
      <div>
        <div className="mb-3">
          <Segmented value={layer} onChange={setLayer} wide
                     items={[["product_lang", "产品需求"], ["chem_lang", "化学语言"]] as const} />
        </div>
        <ReqItems view={view} field={layer} />
      </div>
      {layer === "chem_lang" && !!req.hypotheses.length && (
        <Group title="研发方向假设">
          {req.hypotheses.map((h) => <div key={h} className="row text-[14px]">{h}</div>)}
        </Group>
      )}
      {req.public_points && (
        <Group title="对外要点" foot={`${L.name(req.rd_confirmed_by)} 确认`}>
          <div className="row text-[14px] leading-[22px]">{req.public_points}</div>
        </Group>
      )}
      {req.sheet && (
        <Group title="说明书草稿">
          <div className="row !py-3 text-[14px] leading-[22px]">{req.sheet.sheet}</div>
          <div className="row !items-start text-[13px] leading-5">
            <span className="w-10 shrink-0 text-ink-2">用法</span><span>{req.sheet.usage}</span>
          </div>
        </Group>
      )}
    </>
  );
}

// 当前身份可见的需求单（不含已失效的），选中项默认为最新一张；侧栏用作 source list。
export function useRequirementChoice() {
  const { me } = useApp();
  const L = useLabels();
  const [chosen, choose] = useState<string | null>(null);
  const reqs = useData(() => api.requirements(me), [me]);
  const list = (reqs ?? []).filter((r) => r.status !== "rejected").reverse();
  const current = list.find((r) => r.id === chosen)?.id ?? list[0]?.id ?? null;
  const section = (
    <>
      <SideHead>需求单</SideHead>
      {list.length ? list.map((r: RequirementSummary) => (
        <button key={r.id} onClick={() => choose(r.id)} className={`side-row ${r.id === current ? "on" : ""}`} title={r.id}>
          <p className="text-[13px] font-semibold">{L.phen(r.phenomenon)}</p>
          <p className="text-[12px] text-ink-2">{REQ_STATUS[r.status]}</p>
        </button>
      )) : <p className="px-[18px] py-1 text-[13px] text-ink-3">暂无需求单</p>}
    </>
  );
  return { current, section };
}
