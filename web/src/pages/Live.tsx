// V12.8 组织运行实况（路演主屏，主管只读）：四页——
// 实况：这一局每件事按主体分到泳道（觉 / Jev / 契 / Agent / 人），同一现象的几件事串在一张图上，格子里写 Jev 的概率，点人的格子进那个岗位；
// 觉雷达：觉正在看的对象、分数条与门槛线、选择不报的事；有 Jue-K 模型的格并排一根 Jue-K 分（这一局用规则时只作对照），旁边「觉在学习」；
// 决策目录：27 类决策按阶段排，这一局触发过的亮起，写明觉对大模型的调用为 0；
// 问题总线：一件事从觉提出、派给谁、Agent 用了哪些工具（哪次被门面拒绝）、还缺什么，到谁签字。
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Harness } from "../components/Harness";
import { usePlay } from "../components/Play";
import { FAMILY, hhmm, useApp, useData, useLabels } from "../ctx";
import type { BusItem, CatalogItem, LiveCase, RadarRow, Role, StoryLine } from "../types";
import { EmptyState, Group, PageHead } from "../components/ui";

const VIEWER = "supervisor:CEO";
const TABS = [["lanes", "实况"], ["radar", "觉雷达"], ["catalog", "决策目录"], ["bus", "问题总线"], ["arch", "活的架构图"]] as const;
type Tab = (typeof TABS)[number][0];
const LANES = [["jue", "觉"], ["jev", "Jev"], ["qi", "契"], ["agent", "Agent"], ["human", "人"]] as const;
const LANE_OF: Record<StoryLine["subject"], string> = { jue: "jue", jev: "jev", qi: "qi", agent: "agent", system: "agent", human: "human" };
const LANE_TONE: Record<string, string> = {
  jue: "bg-violet-50 text-violet-900", jev: "bg-sky-50 text-sky-900", qi: "bg-emerald-50 text-emerald-900",
  agent: "bg-slate-50 text-slate-800", human: "bg-amber-50 text-amber-900",
};
const ROLE_NAME: Record<Role, string> = { customer: "客户", sales: "业务员", pm: "产品经理", rd: "研发", supervisor: "研发负责人" };
const CALLER: Record<string, string> = { jue: "觉", agent: "Agent", ingest: "读取与编译", sim: "导演与模拟客户", jev: "Jev 降级", baseline: "对照组" };
// 决策目录按业务阶段排；新加的模板没归进来时放在「其他」
const STAGES: [string, string[]][] = [
  ["客户对话", ["ask_slot", "escalate_need", "route_rd", "handoff_sales", "mechanism_followup"]],
  ["需求单与转译", ["accept_requirement", "reuse_product", "distortion", "ask_back", "confirm_translation", "contribution", "contribution_pm"]],
  ["试样与发布", ["trial_risk", "trial_rework", "market_eval", "seal_points", "seal_leak", "release"]],
  ["产品与说明书", ["opportunity", "scope_update", "knowledge_conflict", "sheet_mismatch"]],
  ["契：能力的授予与复核", ["qi_grant", "qi_review", "stale_capability", "capability_recall"]],
  ["信息控制", ["leak_risk"]],
];

// 实况页要跟着导演走：每 3 秒重读一次
function useTick(ms = 3000) {
  const [n, setN] = useState(0);
  useEffect(() => { const t = setInterval(() => setN((x) => x + 1), ms); return () => clearInterval(t); }, [ms]);
  return n;
}

export function Live() {
  const [tab, setTab] = useState<Tab>(() => (localStorage.getItem("huayan-live-tab") as Tab) || "lanes");
  const pick = (t: Tab) => { localStorage.setItem("huayan-live-tab", t); setTab(t); };
  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-5 px-8 pb-24 pt-7">
      <PageHead title="组织运行实况"
                subtitle="这一局里信息怎样自己变成了事、事怎样在觉、Jev、契、Agent 和人之间流转。全部读这一局的事件与问题总线，不另存；主管只读。"
                aside={<div className="flex gap-1">{TABS.map(([k, label]) => (
                  <button key={k} type="button" onClick={() => pick(k)} className={`chip ${tab === k ? "tag-accent" : ""}`}>{label}</button>))}</div>} />
      {tab === "lanes" && <><Act /><Lanes /></>}
      {tab === "radar" && <Radar />}
      {tab === "catalog" && <Catalog />}
      {tab === "bus" && <Bus />}
      {tab === "arch" && <Harness viewer={VIEWER} />}
    </div>
  );
}

// ---------- 实况：泳道 ----------
function jevText(l: StoryLine) {
  const j = l.jev;
  if (!j) return null;
  if (j.p != null) return `p ${j.p.toFixed(2)}`;
  const top = Math.max(0, ...Object.values(j.p_choice ?? {}));
  return (j.p_none ?? 0) > top ? `都不适用 ${j.p_none!.toFixed(2)}` : `最好的候选 ${top.toFixed(2)}`;
}

function Lanes() {
  const { go } = useApp();
  const L = useLabels();
  const tick = useTick();
  const data = useData(() => api.live(VIEWER), [tick]);
  if (!data) return null;
  if (!data.cases.length) return <EmptyState title="这一局还没有事" text="导演送来第一件事后，这里按时间画出它经过的每一步。" />;
  const topics = new Map<string, LiveCase[]>();
  for (const c of data.cases) topics.set(c.phenomenon ?? "", [...(topics.get(c.phenomenon ?? "") ?? []), c]);
  const open = (c: LiveCase, l: StoryLine) => {
    if (!l.role) return;
    const focus = ["sales", "customer"].includes(l.role) ? c.session_id : c.requirement_id ?? c.session_id;
    go(l.role, focus, l.who.includes(":agent") || l.who.startsWith("agent:") ? undefined : l.who);
  };
  const who = (l: StoryLine) => l.who === "huayan" ? "化言" : l.subject === "human" || l.subject === "agent" ? L.name(l.who) : "";
  const newest = data.cases.flatMap((c) => c.story.map((l) => l.ts)).sort().at(-1);   // 最新的一步（交接点）高亮
  return <>{[...topics].map(([phen, cases]) => {
    const lines = cases.flatMap((c, i) => c.story.map((l) => ({ c, i, l }))).sort((a, b) => a.l.ts.localeCompare(b.l.ts));
    // 排格：按时间往后排，换了泳道的下一步可以和上一步同列，同一泳道里不重叠，先后次序不乱
    const last: Record<string, number> = {};
    let col = 0;
    const placed = lines.map((x) => {
      const lane = LANE_OF[x.l.subject];
      col = Math.max(col, (last[lane] ?? -1) + 1);
      last[lane] = col;
      return { ...x, lane, col };
    });
    return (
      <Group key={phen} title={`${phen ? L.phen(phen) : "尚未识别现象"} · ${cases.length} 件事`}>
        <ScrollEnd>
          <div className="grid w-max gap-y-1.5" style={{ gridTemplateColumns: `68px repeat(${col + 1}, 148px)`, gridTemplateRows: `repeat(${LANES.length}, auto)` }}>
            {LANES.map(([lane, label], row) => (
              <div key={lane} style={{ gridRow: row + 1, gridColumn: 1 }}
                   className="sticky left-0 z-10 flex items-center bg-white pl-3 pr-2 text-[12px] font-semibold text-ink-2">{label}</div>
            ))}
            {placed.map(({ c, i, l, lane, col: k }, n) => (
              <button key={n} type="button" onClick={() => open(c, l)} disabled={!l.role} title={l.text}
                      style={{ gridRow: LANES.findIndex(([x]) => x === lane) + 1, gridColumn: k + 2 }}
                      className={`mx-0.5 rounded-md px-2 py-1 text-left text-[11.5px] leading-4 ${LANE_TONE[lane]} ${l.role ? "hover:ring-1 hover:ring-accent" : "cursor-default"}
                        ${l.ts === newest ? "animate-pulse ring-2 ring-[#c93400]" : ""}`}>
                <span className="block text-[10.5px] opacity-70">{hhmm(l.ts)} · {c.customer_id ? L.name(c.customer_id) : `第 ${i + 1} 件`}</span>
                <span className="line-clamp-2">{who(l) && `${who(l)} `}{l.text}</span>
                {jevText(l) && <span className="mt-0.5 block font-semibold">{jevText(l)}{l.jev?.version ? ` · ${L.version(l.jev.version)}` : ""}</span>}
              </button>
            ))}
          </div>
        </ScrollEnd>
        {cases.map((c, i) => {
          const spared = c.old_roles.filter((r) => !c.now_roles.includes(r));
          return <div key={c.session_id} className="row text-[12.5px] text-ink-2">
            <span className="font-medium text-ink">{c.customer_id ? L.name(c.customer_id) : `第 ${i + 1} 件`}</span>
            <span>{c.path}</span>
            <span>{spared.length ? `这件事没打扰：${spared.join("、")}` : "旧流程里经手的岗位，这次也经手了"}（旧流程 {c.old_roles.join(" → ") || "—"}，推算）</span>
            {!!c.waiting.length && <span className="tag tag-attn">等 {c.waiting.map((w) => w.decision).join("、")}</span>}
          </div>;
        })}
      </Group>
    );
  })}</>;
}

// 实况看的是「现在」：泳道默认滚到最右，新的一步出现时跟着滚
function ScrollEnd({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useRef(0);
  useEffect(() => {
    const el = ref.current!;
    if (el.scrollWidth !== width.current) el.scrollLeft = el.scrollWidth;
    width.current = el.scrollWidth;
  });
  return <div ref={ref} className="overflow-x-auto py-3 pr-3">{children}</div>;
}

// ---------- 觉雷达 ----------
function Bar({ p, threshold, label, tone }: { p: number; threshold: number; label: string; tone: string }) {
  return <div className="flex items-center gap-2 text-[11.5px]">
    <span className="w-[46px] shrink-0 text-ink-2">{label}</span>
    <div className="relative h-2.5 w-[180px] rounded-full bg-slate-100">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.round(p * 100)}%` }} />
      <div className="absolute -top-1 h-[18px] w-px bg-ink" style={{ left: `${Math.round(threshold * 100)}%` }} title={`门槛 ${threshold}`} />
    </div>
    <span className="w-8 tabular-nums">{p.toFixed(2)}</span>
  </div>;
}

function RadarItem({ r }: { r: RadarRow }) {
  const L = useLabels();
  const used = r.scored_by === "jue_k" ? "Jue-K" : L.scorer(r.scored_by);
  return <div className="row !items-start !py-2.5">
    <div className="min-w-0 flex-1">
      <p className="text-[13px]">{L.scrub(r.title)}{r.who && <span className="ml-1.5 text-ink-2">· {r.who}</span>}</p>
      <p className="mt-0.5 text-[12px] leading-[17px] text-ink-2">{L.scrub(r.why)}</p>
    </div>
    <div className="flex shrink-0 flex-col gap-1">
      <Bar p={r.p} threshold={r.threshold} label={used} tone={r.p >= r.threshold ? "bg-accent" : "bg-slate-400"} />
      {r.scored_by === "jue_k" && <Bar p={r.rule} threshold={r.threshold} label="规则" tone="bg-slate-300" />}
      {r.scored_by !== "jue_k" && r.jue_k != null && <Bar p={r.jue_k} threshold={r.threshold} label="Jue-K" tone="bg-violet-400" />}
    </div>
  </div>;
}

function Radar() {
  const L = useLabels();
  const tick = useTick();
  const r = useData(() => api.jueRadar(VIEWER), [tick]);
  const seen = useRef<number | null>(null);
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    if (!r) return;
    if (seen.current != null && r.learning.samples > seen.current) setFresh(true);
    seen.current = r.learning.samples;
  }, [r?.learning.samples]);
  if (!r) return null;
  const status = (x: RadarRow) => x.question ? (x.question.status === "open" ? "open" : "done")
    : x.p >= x.threshold ? (x.family === "ask_slot" ? "open" : "done") : "below";
  const groups: [string, string, RadarRow[]][] = [
    ["open", "越过门槛，已报出、等人处理", r.rows.filter((x) => status(x) === "open")],
    ["below", "觉在看、选择不报（低于门槛）", r.rows.filter((x) => status(x) === "below")],
    ["done", "已处理过", r.rows.filter((x) => status(x) === "done")],
  ];
  const engine = (m: "scheduled" | "realtime") => r.engine[m] === "jue_k" ? "Jue-K 打分（没有模型的格用规则）" : "规则打分";
  const shadow = Object.values(r.engine).some((e) => e !== "jue_k");
  const cells = [...new Set([...r.jue_k_cells.scheduled, ...r.jue_k_cells.realtime])];
  const last = r.learning.last;
  return <>
    <p className="text-[13px] text-ink-2">
      这一局觉的打分：定时扫描用{engine("scheduled")}，对话中实时判断用{engine("realtime")}；觉的发现环节只用规则、本地模型，不调用大模型。
      Jue-K 已训练的格：{cells.map((c) => `${L.family(c.split("|")[0])}（${c.split("|")[1]}）`).join("、") || "无"}
      {shadow && "；这一局用规则打分的格，紫色的 Jue-K 分只作对照，没有参与决策"}。竖线是报出的门槛。
    </p>
    <div className={`rounded-xl border px-4 py-3 text-[13px] ${fresh ? "border-accent bg-sky-50" : "border-line bg-white"}`}>
      <span className="font-semibold">觉在学习</span>
      <span className="ml-2">这一局人处置了觉提出的 {r.learning.samples} 件事，每次处置都记成一条学习样本
        {r.learning.trained != null && `（Jue-K 现有训练集 ${r.learning.trained.toLocaleString()} 条，来自模拟运行，下次重训纳入）`}。</span>
      {last && <span className="ml-1 text-ink-2">{fresh ? "刚才" : "最近一次"}：{L.name(last.by)}{last.action === "dismiss" ? "判断" : "处置"}了「{L.family(last.family)}」（{hhmm(last.at)}）
        {fresh && `，成为觉的第 ${r.learning.samples} 个学习样本`}。</span>}
    </div>
    {groups.map(([k, title, rows]) => !!rows.length && (
      <Group key={k} title={`${title} · ${rows.length}`}>
        {(k === "done" ? rows.slice(-8) : rows).sort((a, b) => b.p - a.p).map((x) => <RadarItem key={`${x.family}${x.object_id}`} r={x} />)}
      </Group>
    ))}
    {!r.rows.length && <EmptyState title="觉还没看到值得判断的事" text="客户开口、需求单生成或能力生效后，觉会在这里给出分数。" />}
  </>;
}

// ---------- 决策目录墙 ----------
function Catalog() {
  const L = useLabels();
  const tick = useTick();
  const c = useData(() => api.catalog(VIEWER), [tick]);
  const before = useRef<Record<string, string | null>>({});
  const [lit, setLit] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!c) return;
    const changed = c.templates.filter((t) => t.last && before.current[t.family] !== undefined && before.current[t.family] !== t.last).map((t) => t.family);
    before.current = Object.fromEntries(c.templates.map((t) => [t.family, t.last]));
    if (changed.length) { setLit(new Set(changed)); const t = setTimeout(() => setLit(new Set()), 2500); return () => clearTimeout(t); }
  }, [c]);
  if (!c) return null;
  const by = new Map(c.templates.map((t) => [t.family, t]));
  const placed = new Set(STAGES.flatMap(([, f]) => f));
  const stages: [string, CatalogItem[]][] = [...STAGES.map(([s, fs]) => [s, fs.flatMap((f) => by.get(f) ?? [])] as [string, CatalogItem[]]),
    ["其他", c.templates.filter((t) => !placed.has(t.family))]];
  const calls = Object.entries(c.llm_calls);
  return <>
    <p className="text-[13px] text-ink-2">
      觉的决策目录共 {c.templates.length} 类，每类写明谁准备、谁签字；这一局触发过的亮起，刚触发的闪一下。
      这一局的大模型调用：{calls.map(([k, n]) => `${CALLER[k] ?? k} ${n} 次`).join(" · ")}。
    </p>
    {stages.map(([stage, items]) => !!items.length && (
      <section key={stage}>
        <p className="group-title">{stage}</p>
        <div className="grid grid-cols-4 gap-2">
          {items.map((t) => (
            <div key={t.family} className={`rounded-lg border px-3 py-2 text-[12.5px] transition-colors ${lit.has(t.family) ? "border-accent bg-sky-100"
              : t.n ? "border-accent/40 bg-sky-50" : "border-line bg-white text-ink-2"}`}>
              <p className="font-medium text-ink">{FAMILY[t.family] ?? t.decision}</p>
              <p className="mt-0.5 text-[11.5px]">{ROLE_NAME[t.owner_role]}{t.signer_role ? ` 准备 → ${ROLE_NAME[t.signer_role]} 签字` : " 收到提示"}</p>
              <p className="mt-1 flex flex-wrap items-center gap-1 text-[11.5px]">
                <span>{t.n ? `这一局 ${t.n} 次${t.last ? ` · 最近 ${hhmm(t.last)}` : ""}` : "这一局未触发"}</span>
                {t.jue_k.map((cell) => <span key={cell} className="tag tag-accent !h-[17px] !text-[10.5px]">Jue-K {cell.split("|")[1]}</span>)}
                {t.off && <span className="tag !h-[17px] !text-[10.5px]">本实例停用</span>}
              </p>
            </div>
          ))}
        </div>
      </section>
    ))}
  </>;
}

// ---------- 问题总线 ----------
const STATUS: Record<BusItem["status"], string> = { open: "待处理", resolved: "已处理", dismissed: "现在不需要" };

function Bus() {
  const L = useLabels();
  const tick = useTick();
  const items = useData(() => api.bus(VIEWER), [tick]) ?? [];
  const [chosen, choose] = useState<string | null>(null);
  const id = chosen ?? items[0]?.id ?? null;
  const life = useData(() => (id ? api.busLife(id, VIEWER) : Promise.resolve(null)), [id, tick]);
  if (!items.length) return <EmptyState title="问题总线上还没有事" text="觉提出第一件需要人决定的事后，这里列出它的一生。" />;
  const q = life?.question;
  const rejected = life?.steps.filter((s) => s.error || s.blocked) ?? [];
  return <div className="grid grid-cols-[340px_1fr] gap-5">
    <div className="flex max-h-[72vh] flex-col gap-1 overflow-y-auto">
      {items.map((x) => (
        <button key={x.id} type="button" onClick={() => choose(x.id)}
                className={`side-row !items-start !py-2 text-left ${x.id === id ? "bg-slate-100" : ""}`}>
          <span className="min-w-0 flex-1">
            <span className="block text-[11.5px] text-ink-2">{hhmm(x.created_at)} · {L.family(x.family)} · {STATUS[x.status]}</span>
            <span className="line-clamp-2 text-[12.5px]">{L.scrub(x.title)}</span>
          </span>
        </button>
      ))}
    </div>
    {q && life && <div className="flex flex-col gap-3 text-[13px]">
      <p className="text-[16px] font-semibold">{L.scrub(q.title)}</p>
      <Group title="一生">
        <div className="row !items-start"><span className="w-20 shrink-0 text-ink-2">{hhmm(q.created_at)} 觉</span>
          <span>提出「{life.decision ?? L.family(q.family)}」，打分 {q.p_need?.toFixed(2) ?? "—"}（{L.scorer(q.scored_by)}）；依据：{q.evidence.map((e) => L.scrub(e.summary)).join("；")}</span></div>
        <div className="row !items-start"><span className="w-20 shrink-0 text-ink-2">派单</span>
          <span>{q.owner_id ? `交${L.name(q.owner_id)}准备` : "请客户在自助页回答"}{q.signer_id ? `，${L.name(q.signer_id)}签字` : "（提示类，不需签字）"}</span></div>
        {life.steps.map((s, i) => (
          <div key={i} className="row !items-start"><span className="w-20 shrink-0 text-ink-2">{hhmm(s.at)} Agent</span>
            <span className={s.error || s.blocked ? "text-danger" : ""}>调用 {s.tool}{s.blocked ? "：越权，被挡下" : s.error ? `：被门面拒绝——${s.error}` : ""}</span></div>
        ))}
        {life.errors.map((e, i) => (
          <div key={`e${i}`} className="row !items-start"><span className="w-20 shrink-0 text-ink-2">{hhmm(e.at)} 核对</span>
            <span className="text-attn-ink">{e.kind === "prepare_missing" ? `以对象为准还缺：${e.detail}，退回 Agent 再做` : `${e.kind}：${e.detail ?? ""}`}</span></div>
        ))}
        {q.prepared_at && <div className="row"><span className="w-20 shrink-0 text-ink-2">{hhmm(q.prepared_at)}</span><span>准备好，进签字人的待签</span></div>}
        {life.gap && <div className="row"><span className="w-20 shrink-0 text-ink-2">还缺</span><span className="text-attn-ink">{life.gap}</span></div>}
        {q.resolution && <div className="row !items-start"><span className="w-20 shrink-0 text-ink-2">{q.resolved_at && hhmm(q.resolved_at)} 结案</span>
          <span>{L.name(q.resolution.by)}{q.resolution.action === "dismiss" ? "判断现在不需要" : "签字"}{q.resolution.note ? `：${q.resolution.note}` : ""}</span></div>}
      </Group>
      {!!rejected.length && <p className="text-[12.5px] text-ink-2">Agent 被门面拒绝 {rejected.length} 次；之后的步骤是它按拒绝原因自己改正的。正式状态只有门面能写，签字只有人能签。</p>}
      {!life.steps.length && <p className="text-[12.5px] text-ink-2">这件事没有 Agent 工具调用（离线模式由规则起草，或不需要准备）。工具参数与结果里有委托人那一层的原文，这里只列工具名与拒绝原因。</p>}
    </div>}
  </div>;
}

// 一镜到底：当前这一幕与这一件（导演的进度），主屏停在实况时台下知道现在讲到哪
const ACTS: Record<number, string> = { 1: "信息自己变成了事", 2: "一份报告的一生", 3: "研发成果的两条回流" };
function Act() {
  const s = usePlay();
  if (!s?.oneshot) return null;
  const now = s.levels.find((x) => x.status === "open");
  return <div className="flex items-baseline gap-3 rounded-[10px] bg-attn-bg px-4 py-2.5">
    <span className="text-[15px] font-semibold text-attn-ink">{s.act ? `第 ${s.act} 幕 · ${ACTS[s.act]}` : "一镜到底"}</span>
    <span className="text-[13px]">{now ? `${now.title}：${now.brief}` : "三幕都走完了"}</span>
  </div>;
}
