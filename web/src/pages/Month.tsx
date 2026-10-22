// v8 Q9.5「化言的一个月」：模拟业务月的主管页。主视图是「一件事」：一段客户来访串上它的需求单、觉的问题
// （觉提出 → 助手准备 → 人签字）、试样与结局；同一件事在另一组（同客户、同来访时刻）怎么走，并排对照。
// 顶部三块讲价值：觉（两组差在哪）、契（研发的判断今天被用了多少次、挡住了什么）、流程（失真对照）。
// 泳道降为「谁在忙」标签页。数据来自门面 timeline(day, by)（只给主管，研发的话只给存根），每 5 秒刷新。
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { MonthCase, MonthDay, MonthItem, MonthProgress, MonthSession, MonthStep } from "../types";
import { Group, PageHead, EmptyState } from "../components/ui";

const VIEWER = "supervisor:M01";
const OPEN = 9 * 60, SPAN = 9 * 60;                   // 9:00–18:00
const GROUP_NAME: Record<string, string> = { jue: "觉组", sm: "状态机组（最强手写规则）" };
const SHORT: Record<string, string> = { jue: "觉组", sm: "状态机组" };
const SPEAKER: Record<string, string> = { customer: "客户", sales: "业务员", system: "化言", assistant: "化言" };

const minutes = (iso: string) => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));
const pos = (iso: string) => `${Math.min(100, Math.max(0, ((minutes(iso) - OPEN) / SPAN) * 100))}%`;
const hhmm = (iso: string) => iso.slice(11, 16);
const when = (iso: string, day: string) => (iso.slice(0, 10) === day ? "" : `${iso.slice(5, 10)} `) + hhmm(iso);
const name = (s?: string | null) => (s ?? "").replace("（模拟）", "");
const other = (run: string) => (run.includes("month-jue-") ? run.replace("month-jue-", "month-sm-") : run.replace("month-sm-", "month-jue-"));
const groupOf = (run: string) => (run.includes("month-jue-") ? "jue" : "sm");

export function Month() {
  const [runs, setRuns] = useState<MonthProgress[]>([]);
  const [run, setRun] = useState<string | null>(null);
  const [day, setDay] = useState<string | null>(null);          // null = 跟随运行的最新一天
  const [data, setData] = useState<MonthDay | null>(null);
  const [peer, setPeer] = useState<MonthDay | null>(null);
  const [tab, setTab] = useState<"cases" | "lanes">("cases");
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => { const t = setInterval(() => setTick((n) => n + 1), 5000); return () => clearInterval(t); }, []);
  useEffect(() => {
    api.monthRuns().then((r) => { setRuns(r); setRun((cur) => cur ?? r.find((x) => x.group === "jue")?.run_id ?? r[0]?.run_id ?? null); },
      (e) => setError(String(e)));
  }, [tick]);
  const progress = runs.find((r) => r.run_id === run) ?? null;
  const peerRun = run && runs.some((r) => r.run_id === other(run)) ? other(run) : null;
  const shown = day ?? progress?.at.slice(0, 10) ?? null;
  useEffect(() => {
    if (!run || !shown) return;
    api.monthTimeline(run, shown, VIEWER).then((d) => { setData(d); setError(null); }, (e) => setError(e instanceof Error ? e.message : String(e)));
    if (peerRun) api.monthTimeline(peerRun, shown, VIEWER).then(setPeer, () => setPeer(null));
    else setPeer(null);
  }, [run, peerRun, shown, day === null ? tick : 0]);

  if (!runs.length) return <EmptyState title="还没有业务月的运行" text="先运行 scripts/run_month.py；运行开始后这里每 5 秒刷新一次。" />;
  const tags = [...new Set(runs.map((r) => r.run_id!.replace(/^month-(jue|sm)-/, "")))];
  const tag = run?.replace(/^month-(jue|sm)-/, "");
  return (
    <div className="flex flex-col gap-5 px-8 pb-24 pt-6">
      <PageHead title="化言的一个月"
        subtitle="同一批客户、同一个世界、同一套人设，两组唯一的差别是「觉的发现由谁打分」：觉组用会学习的 Jue-K，状态机组用三条手写规则里最强的一条。主管视角，研发的话只给存根。"
        aside={<div className="flex flex-wrap justify-end gap-1.5">
          {tags.length > 1 && tags.map((t) => (
            <button key={t} onClick={() => { setRun(`month-${groupOf(run ?? "")}-${t}`); setDay(null); }}
                    className={`chip num whitespace-nowrap ${t === tag ? "!bg-ink !text-white" : ""}`}>{t.includes("-d2-") ? "冒烟" : t}</button>))}
          {["jue", "sm"].map((g) => {
            const id = `month-${g}-${tag}`;
            return runs.some((r) => r.run_id === id) && (
              <button key={g} onClick={() => setRun(id)}
                      className={`chip whitespace-nowrap ${id === run ? "!bg-accent !text-white" : ""}`}>看{SHORT[g]}</button>);
          })}</div>} />
      {progress && <StatusStrip runs={runs.filter((r) => r.run_id === run || r.run_id === peerRun)} />}
      {error && <p className="text-[13px] text-danger">{error}</p>}
      {data && <>
        <div className="flex flex-wrap items-center gap-1.5">
          {data.days.map((d, i) => (
            <button key={d} onClick={() => setDay(d)}
                    className={`chip num ${d === shown ? "!bg-accent !text-white" : ""}`}>D{i + 1} · {d.slice(5)}</button>))}
          <button onClick={() => setDay(null)} className={`chip ${day === null ? "!bg-accent !text-white" : ""}`}>跟随最新</button>
        </div>
        <Value data={data} peer={peer} group={groupOf(run!)} />
        <div className="flex gap-1.5">
          <button onClick={() => setTab("cases")} className={`chip ${tab === "cases" ? "!bg-ink !text-white" : ""}`}>一件一件事</button>
          <button onClick={() => setTab("lanes")} className={`chip ${tab === "lanes" ? "!bg-ink !text-white" : ""}`}>谁在忙（泳道）</button>
        </div>
        {tab === "cases" ? <Cases data={data} peer={peer} group={groupOf(run!)} /> : <Lanes data={data} />}
      </>}
    </div>
  );
}

function StatusStrip({ runs }: { runs: MonthProgress[] }) {
  return (
    <div className="group">
      {runs.map((p) => {
        const live = Date.now() - Date.parse(p.updated) < 3 * 60 * 1000;
        const pct = Math.round((p.tick / p.ticks) * 100);
        const min = (s: number) => (s >= 3600 ? `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分` : `${Math.floor(s / 60)} 分`);
        return (
          <div key={p.run_id} className="row flex-wrap !gap-x-5 !gap-y-1 text-[12.5px]">
            <span className="flex w-[150px] items-center gap-1.5 font-semibold">
              <i className={`h-[7px] w-[7px] rounded-full ${live ? "bg-[#30c25b]" : "bg-[#8e8e93]"}`} />
              {SHORT[p.group]} · {live ? "运行中" : p.tick >= p.ticks ? "已跑完" : "已停"}</span>
            <span className="num">第 {p.day}/{p.days} 天 {hhmm(p.at)}</span>
            <span className="flex items-center gap-2"><span className="h-1.5 w-28 overflow-hidden rounded-full bg-fill">
              <i className="block h-full bg-accent" style={{ width: `${pct}%` }} /></span><span className="num">{pct}%</span></span>
            <span className="num">已用 {min(p.elapsed_s)}{live ? ` · 还要约 ${min(p.eta_s)}` : ""}</span>
            <span className="num">调用 {p.calls}{p.failed ? `（失败 ${p.failed}）` : ""}</span>
            <span className="num">待办 {p.open_questions}</span>
            <span className="text-ink-2">觉：{p.jue === "jue_k" ? "Jue-K" : "规则"}</span>
          </div>);
      })}
    </div>
  );
}

// 顶部三块：觉、契、流程 ---------------------------------------------------------------------------------
const reqFail = (d: MonthDay) => d.cases.filter((c) => c.story.some((s) => s.kind === "trial" && s.tone === "fail" && s.text?.includes("需求条件"))).length;
const interrupts = (d: MonthDay) => d.discoveries.filter((s) => s.family === "trial_risk" || s.family === "stale_capability").length;
const caught = (d: MonthDay) => d.discoveries.filter((s) => s.family === "trial_risk" && s.action === "签字" && s.note?.startsWith("试样前回问")).length;

function Value({ data, peer, group }: { data: MonthDay; peer: MonthDay | null; group: string }) {
  const jue = group === "jue" ? data : peer, sm = group === "jue" ? peer : data;
  const row = (label: string, f: (d: MonthDay) => number, good: "low" | "high") => {
    const a = jue ? f(jue) : null, b = sm ? f(sm) : null;
    const win = a !== null && b !== null && a !== b && (good === "low" ? a < b : a > b);
    return (
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className="text-ink-2">{label}</span>
        <span className="num"><b className={win ? "text-accent" : ""}>{a ?? "—"}</b><span className="text-ink-3"> 对 {b ?? "—"}</span></span>
      </div>);
  };
  const qi = data.qi;
  return (
    <div className="grid grid-cols-3 gap-5">
      <Group title="觉：两组差在哪（当天）" aside={<span className="text-ink-3">觉组 对 状态机组</span>}>
        <div className="row flex-col !items-stretch gap-1.5">
          {row("试样前拦下（先回问再试样）", caught, "high")}
          {row("因需求条件缺失而失败的试样", reqFail, "low")}
          {row("为预判打扰研发的次数", interrupts, "low")}
          <p className="text-[11.5px] leading-4 text-ink-3">流程推进（接单、确认、升级）两组都是规则，不算觉的功劳；这里只比觉的发现。</p>
        </div>
      </Group>
      <Group title="契：研发的判断今天在干活">
        <div className="row flex-col !items-stretch gap-1.5 text-[13px]">
          <div className="flex items-baseline justify-between"><span className="text-ink-2">被下层用上</span><b className="num">{qi.used_total} 次</b></div>
          <p className="text-[12px] leading-5 text-ink-2">{Object.entries(qi.used_by_owner).map(([k, v]) => `${name(k)} ${v}`).join(" · ") || "—"}</p>
          <div className="flex items-baseline justify-between"><span className="text-ink-2">对外 {qi.outbound} 句里泄露上层原文</span>
            <b className={`num ${qi.leaked ? "text-danger" : "text-[#30a14e]"}`}>{qi.leaked} 句</b></div>
          <div className="flex items-baseline justify-between"><span className="text-ink-2">拦下越层读取</span><b className="num">{qi.denied} 次</b></div>
          <div className="flex items-baseline justify-between"><span className="text-ink-2">人签的授予 / 撤销</span><b className="num">{qi.grants.length}</b></div>
          {qi.grants.slice(0, 3).map((g, k) => (
            <p key={k} className="text-[11.5px] leading-4 text-ink-3">{hhmm(g.at)} {name(g.by)} {g.kind}{g.form ? ` ${g.form}` : ""}{g.audience !== null ? ` → L${g.audience}` : ""}
              {g.capability ? ` · 授予后已被用 ${g.uses_since} 次` : ""}</p>))}
          <p className="text-[12px] text-ink-2">今天记分：{Object.entries(qi.points).filter(([k]) => k !== "seed").map(([k, v]) => `${name(k)} ${v}`).join(" · ") || "—"}</p>
        </div>
      </Group>
      <Group title="流程：需求到研发手里还剩多少">
        <div className="row flex-col !items-stretch gap-2 text-[13px]">
          <p className="leading-5">真正要升级到研发的需求，研发因信息不全而退回的比例：</p>
          <div className="flex items-baseline justify-between"><span className="text-ink-2">业务员转述（现状）</span><b className="num">95.1%</b></div>
          <div className="flex items-baseline justify-between"><span className="text-ink-2">化言（Jue-K 追问 + 分层转译）</span><b className="num text-accent">19.5%</b></div>
          <p className="text-[11.5px] leading-4 text-ink-3">300 张需求卡里应升级的 41 张；转述噪声为假设参数（docs/reports/distortion_300）。这个月里没有人转述：客户原话直达需求单，每条带原话。</p>
        </div>
      </Group>
    </div>
  );
}

// 一件一件事 ----------------------------------------------------------------------------------------------
const STATE: Record<string, [string, string]> = { done: ["已解决", "tag-ok"], open: ["进行中", "tag-attn"], fail: ["失败", "tag-danger"] };

function differs(a: MonthCase, b?: MonthCase) {
  if (!b) return false;
  const fam = (c: MonthCase) => c.story.filter((s) => s.kind === "decision" && s.discovery && s.family !== "ask_slot").map((s) => s.family).sort().join();
  return a.outcome.state !== b.outcome.state || fam(a) !== fam(b);
}

function Cases({ data, peer, group }: { data: MonthDay; peer: MonthDay | null; group: string }) {
  const [filter, setFilter] = useState("all");
  const [pick, setPick] = useState<string | null>(null);
  const peerOf = useMemo(() => new Map((peer?.cases ?? []).map((c) => [c.key, c])), [peer]);
  const list = data.cases.filter((c) => filter === "all" || (filter === "diff" ? differs(c, peerOf.get(c.key))
    : filter === "escalated" ? c.requirements.length > 0 : c.outcome.state === filter));
  const order = { fail: 0, open: 1, done: 2 };
  list.sort((a, b) => (differs(b, peerOf.get(b.key)) ? 1 : 0) - (differs(a, peerOf.get(a.key)) ? 1 : 0)
    || order[a.outcome.state] - order[b.outcome.state] || a.started_at.localeCompare(b.started_at));
  const chosen = data.cases.find((c) => c.id === pick) ?? null;
  const count = (f: string) => data.cases.filter((c) => f === "diff" ? differs(c, peerOf.get(c.key)) : f === "escalated" ? c.requirements.length > 0 : c.outcome.state === f).length;
  return (
    <div className="flex flex-col gap-5">
      <Discoveries data={data} peer={peer} group={group} onPick={setPick} />
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] items-start gap-5">
        <Group title={`当天有动静的事 ${data.cases.length} 件`}
               aside={<div className="flex gap-1">{[["all", "全部"], ["diff", "两组不同"], ["open", "进行中"], ["fail", "失败"], ["escalated", "到了研发"]].map(([k, l]) => (
                 <button key={k} onClick={() => setFilter(k)} className={`chip !h-6 !px-2 text-[12px] ${filter === k ? "!bg-accent !text-white" : ""}`}>
                   {l}{k !== "all" ? ` ${count(k)}` : ""}</button>))}</div>}>
          <div className="max-h-[900px] overflow-y-auto">
            {list.map((c) => <CaseRow key={c.id} c={c} peer={peerOf.get(c.key)} group={group} active={c.id === pick} onClick={() => setPick(c.id)} day={data.day} />)}
            {!list.length && <div className="row text-[13px] text-ink-3">没有符合的事</div>}
          </div>
        </Group>
        <div className="sticky top-[70px]">
          {chosen ? <div className="max-h-[calc(100vh-90px)] overflow-y-auto rounded-[10px]"><Story c={chosen} peer={peerOf.get(chosen.key)} group={group} day={data.day} onClose={() => setPick(null)} /></div>
            : <Group title="点左边一件事，看它从头到尾怎么走"><Legend /></Group>}
        </div>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="row flex-col !items-start gap-2 text-[12.5px] leading-5 text-ink-2">
      <p><Chip tone="jue">觉发现</Chip> 觉从模式里提出的问题（追问、回问、试样风险、判断过时、机会、泄密……），打分会学习</p>
      <p><Chip tone="flow">流程</Chip> 状态到了就提出（接单、确认、升级），两组一样</p>
      <p><Chip tone="human">人签字</Chip> 人在工作面上按了按钮；<Chip tone="auto">自动</Chip> 低风险的推进由觉直接执行</p>
      <p><Chip tone="wait">等谁</Chip> 截至当天结束还没人处理；<Chip tone="fail">失败</Chip> 试样失败、冻结等</p>
      <p>每个问题都走同一条线：<b>觉提出 → 助手准备材料 → 人签字 → 状态改变 → 觉再看</b>。</p>
    </div>);
}

function Chip({ tone, children, title }: { tone: string; children: React.ReactNode; title?: string }) {
  const cls: Record<string, string> = {
    jue: "bg-accent/12 text-accent", flow: "bg-fill text-ink-2", human: "bg-[#30c25b]/15 text-[#1f8a3d]",
    auto: "bg-accent/8 text-accent ring-1 ring-accent/30", wait: "bg-attn/15 text-[#a35a00] ring-1 ring-attn/40",
    fail: "bg-danger/12 text-danger", ok: "bg-[#30c25b]/15 text-[#1f8a3d]", qi: "bg-[#8e8e93]/15 text-ink-2",
  };
  return <span title={title} className={`inline-flex h-[20px] items-center whitespace-nowrap rounded-[5px] px-1.5 text-[11.5px] ${cls[tone]}`}>{children}</span>;
}

// 一件事的阶段链：只留决定与关键事实，追问合成一个「追问 n 次」
function chain(c: MonthCase) {
  const out: { tone: string; text: string; title: string }[] = [];
  const asks = c.story.filter((s) => s.kind === "decision" && s.family === "ask_slot").length;
  if (asks) out.push({ tone: "jue", text: `追问 ${asks} 次`, title: "觉按信息价值决定问什么" });
  const push = (x: { tone: string; text: string; title: string }) => {      // 连着一样的合成一个「×n」
    const last = out[out.length - 1];
    const base = last?.text.replace(/ ×\d+$/, "");
    if (last && base === x.text && last.tone === x.tone) last.text = `${base} ×${Number(last.text.match(/×(\d+)$/)?.[1] ?? 1) + 1}`;
    else out.push(x);
  };
  for (const s of c.story) {
    if (s.kind === "decision" && s.family !== "ask_slot") {
      const t = s.status === "open" ? "wait" : s.discovery ? "jue" : "flow";
      const who = s.status === "open" ? (s.family === "ask_back" ? "等客户" : `等${name(s.prepared_at ? s.signer : s.owner) || "人"}`)
        : s.family === "ask_back" ? "客户已答" : s.action === "自动执行" ? "自动" : s.by && s.by !== "觉" ? name(s.by).replace(/^.*研发|^产品经理|^业务员/, "") : "";
      push({ tone: t, text: `${short(s)}${who ? ` · ${who}` : ""}`, title: `${s.label}${s.note ? `：${s.note}` : ""}` });
    } else if (["recommend", "trial", "product_released", "requirement_created", "market_eval", "access_frozen"].includes(s.kind)) {
      push({ tone: s.tone === "fail" || s.kind === "access_frozen" ? "fail" : s.kind === "requirement_created" ? "flow" : "ok", text: s.text ?? s.kind, title: s.text ?? "" });
    }
  }
  return out;
}

const SHORT_LABEL: Record<string, string> = {
  route_rd: "直达研发", escalate_need: "升级", reuse_product: "查现成产品", accept_requirement: "接单", confirm_translation: "确认转译",
  ask_back: "回问客户", trial_risk: "试样风险", trial_rework: "退回重译", market_eval: "客户评价", distortion: "失真", leak_risk: "泄密风险", mechanism_followup: "追问产品内部",
  handoff_sales: "交业务员", contribution: "沉淀", contribution_pm: "沉淀", seal_points: "封存与放出", release: "发布",
  opportunity: "机会汇聚", stale_capability: "判断过时", knowledge_conflict: "知识冲突", qi_grant: "授予", qi_review: "复核",
  scope_update: "扩展适用范围", seal_leak: "对外去密",
};
const short = (s: MonthStep) => SHORT_LABEL[s.family ?? ""] ?? s.label ?? s.family ?? "";

function CaseRow({ c, peer, group, active, onClick, day }: { c: MonthCase; peer?: MonthCase; group: string; active: boolean; onClick: () => void; day: string }) {
  const [label, cls] = STATE[c.outcome.state];
  const diff = differs(c, peer);
  return (
    <button onClick={onClick} className={`row w-full flex-col !items-stretch gap-1.5 text-left ${active ? "bg-accent/6" : "hover:bg-fill/60"}`}>
      <div className="flex items-baseline gap-2 text-[13px]">
        <span className="num text-[12px] text-ink-3">{when(c.started_at, day)}</span>
        <b className="font-semibold">{name(c.customer_name)}</b>
        <span className="text-ink-2">{c.phenomenon}</span>
        {c.requirements.length > 0 && <span className="num text-[11.5px] text-ink-3">{c.requirements.join(" ")}</span>}
        <span className="ml-auto flex shrink-0 gap-1">{diff && <span className="tag tag-accent">两组不同</span>}<span className={`tag ${cls}`}>{label}</span></span>
      </div>
      <p className="truncate text-[12.5px] text-ink-2">「{c.opening}」</p>
      <div className="flex flex-wrap items-center gap-1">
        {chain(c).map((x, k) => <span key={k} className="flex items-center gap-1">{k > 0 && <i className="text-[10px] text-ink-3">›</i>}<Chip tone={x.tone} title={x.title}>{x.text}</Chip></span>)}
      </div>
      <p className="text-[12px]"><span className="text-ink-3">结局：</span>{c.outcome.text}{c.outcome.since ? <span className="text-ink-3">（自 {when(c.outcome.since, day)}）</span> : ""}</p>
      {peer && diff && <p className="text-[12px] text-ink-3">{SHORT[group === "jue" ? "sm" : "jue"]}这件事：{peer.outcome.text}</p>}
    </button>
  );
}

function Story({ c, peer, group, day, onClose }: { c: MonthCase; peer?: MonthCase; group: string; day: string; onClose: () => void }) {
  const [both, setBoth] = useState(true);
  return (
    <Group title={`${name(c.customer_name)} · ${c.phenomenon}`}
           aside={<span className="flex gap-3">{peer && <button className="link" onClick={() => setBoth(!both)}>{both ? "只看本组" : `对照${SHORT[group === "jue" ? "sm" : "jue"]}`}</button>}
             <button className="link" onClick={onClose}>关闭</button></span>}>
      <div className={`grid gap-0 ${peer && both ? "grid-cols-2 divide-x divide-sep" : "grid-cols-1"}`}>
        <StoryCol c={c} title={SHORT[group]} day={day} />
        {peer && both && <StoryCol c={peer} title={SHORT[group === "jue" ? "sm" : "jue"]} day={day} />}
      </div>
    </Group>
  );
}

function StoryCol({ c, title, day }: { c: MonthCase; title: string; day: string }) {
  const [label, cls] = STATE[c.outcome.state];
  const steps: MonthStep[] = [];
  for (const s of c.story) {                      // 追问不逐条列；连着的契合成一行
    if (s.kind === "decision" && s.family === "ask_slot") continue;
    const last = steps[steps.length - 1];
    if (s.kind === "capability_used" && last?.kind === "capability_used") {
      if (!last.text?.includes(s.text ?? "")) last.text = `${last.text}、${s.text}`;
    } else steps.push(s.kind === "capability_used" ? { ...s } : s);
  }
  return (
    <div className="flex min-w-0 flex-col">
      <div className="row flex-wrap !gap-1.5 text-[12px]">
        <b>{title}</b><span className={`tag ${cls}`}>{label}</span><span className="text-ink-2">{c.outcome.text}</span>
        <span className="text-ink-3">· {c.sales ? `业务员 ${name(c.sales)}` : "客户自助"}</span>
      </div>
      {steps.map((s, k) => <StoryStep key={k} s={s} day={day} />)}
    </div>
  );
}

function StoryStep({ s, day }: { s: MonthStep; day: string }) {
  const time = <span className="num w-[76px] shrink-0 whitespace-nowrap text-[11.5px] text-ink-3">{when(s.at, day)}</span>;
  if (s.kind === "turn") return (
    <div className="row !items-start !gap-2 text-[13px]">{time}
      <span className={`w-10 shrink-0 text-[12px] ${s.speaker === "customer" ? "text-ink" : "text-accent"}`}>{SPEAKER[s.speaker ?? ""] ?? s.speaker}</span>
      <span className="min-w-0 leading-5">{s.text}</span></div>);
  if (s.kind === "capability_used") return (
    <div className="row !items-start !gap-2 !py-1 text-[12px]">{time}<Chip tone="qi">契</Chip>
      <span className="min-w-0 leading-5 text-ink-2">用上了{s.text}；对方只得到能力，看不到原文</span></div>);
  if (s.kind === "decision") {
    const tone = s.discovery ? "jue" : "flow";
    return (
      <div className="row flex-col !items-stretch !gap-1 text-[13px]">
        <div className="flex items-start gap-2">{time}
          <span className="flex min-w-0 flex-wrap items-center gap-1.5">
            <Chip tone={tone}>{s.discovery ? "觉发现" : "流程"}</Chip>
            <span>觉提出：<b className="font-medium">{s.label}</b></span>
            {s.discovery && s.p !== null && s.p !== undefined && <span className="num text-[11.5px] text-ink-3">（{s.scored_by === "jue_k" ? "Jue-K" : "规则"} {s.p.toFixed(2)}）</span>}
          </span></div>
        {s.ask && <p className="ml-[84px] text-[12.5px] text-ink-2">化言替研发问客户：「{s.ask}」</p>}
        {s.owner && s.signer && <p className="ml-[84px] text-[12px] text-ink-3">
          {s.prepared_at ? `${when(s.prepared_at, day)} ${name(s.owner)}${s.owner.includes("Agent") ? "" : "的助手"}准备好材料` : `等${name(s.owner)}准备材料`}</p>}
        <p className="ml-[84px] text-[12.5px]">
          {s.status === "open" ? <Chip tone="wait">{s.family === "ask_back" ? "等客户回答" : `等${name(s.prepared_at ? s.signer : s.owner)}${s.prepared_at ? "签字" : "准备"}`}</Chip>
            : <><Chip tone={s.action === "自动执行" ? "auto" : s.by === "觉" ? "flow" : "human"}>{s.action === "自动执行" ? "觉自动执行" : `${name(s.by)} ${s.action}`}</Chip>
              <span className="num ml-1.5 text-[11.5px] text-ink-3">{s.done_at ? when(s.done_at, day) : ""}</span>
              {s.note && <span className="ml-1.5 text-ink-2">{s.family === "ask_back" ? `客户答：${s.note}` : s.note}</span>}</>}
        </p>
      </div>);
  }
  return (
    <div className="row !items-start !gap-2 text-[13px]">{time}
      <Chip tone={s.tone === "fail" || s.kind === "access_frozen" ? "fail" : s.tone === "ok" || s.kind === "recommend" ? "ok" : "flow"}>{FACT[s.kind] ?? "事实"}</Chip>
      <span className="min-w-0 leading-5">{s.text}{s.by && s.by !== "觉" ? <span className="text-ink-3"> · {name(s.by)}</span> : ""}</span></div>);
}

const FACT: Record<string, string> = { recommend: "推荐", requirement_created: "建单", requirement_translated: "转译", requirement_returned: "退回",
  trial: "试样", market_eval: "客户评价", project_opened: "立项", product_released: "发布", sales_assigned: "交业务员",
  access_frozen: "冻结", access_unfrozen: "解冻", decrypt_request: "解密", decrypt_approve: "解密" };

// 觉主动发现：当天两组各自提出了哪些不针对某一件事的发现（机会、判断过时、泄密、知识冲突、失真……）
function Discoveries({ data, peer, group, onPick }: { data: MonthDay; peer: MonthDay | null; group: string; onPick: (id: string) => void }) {
  const cols = [[group, data], ...(peer ? [[group === "jue" ? "sm" : "jue", peer]] : [])] as [string, MonthDay][];
  return (
    <Group title="觉的发现（当天）" aside={<span className="text-ink-3">没有人触发也会提出：从累积的模式里看出来</span>}>
      <div className={`grid ${cols.length > 1 ? "grid-cols-2 divide-x divide-sep" : ""}`}>
        {cols.map(([g, d]) => (
          <div key={g} className="min-w-0">
            <div className="row text-[12px] font-semibold">{SHORT[g]} · {d.discoveries.length} 个</div>
            <div className="max-h-[220px] overflow-y-auto">
              {d.discoveries.map((s, k) => (
                <button key={k} disabled={!s.case || g !== group} onClick={() => s.case && onPick(s.case)}
                        className="row w-full !items-start !gap-2 !py-1.5 text-left text-[12.5px] enabled:hover:bg-fill/60">
                  <span className="num w-[40px] shrink-0 text-[11.5px] text-ink-3">{hhmm(s.at)}</span>
                  <Chip tone={s.status === "open" ? "wait" : "jue"}>{short(s)}</Chip>
                  <span className="min-w-0 leading-5">{s.title}
                    <span className="text-ink-3"> · {s.scored_by === "jue_k" ? "Jue-K" : "规则"}{s.p !== null && s.p !== undefined ? ` ${s.p.toFixed(2)}` : ""}
                      {s.status === "open" ? " · 待处理" : ` · ${name(s.by)} ${s.action}${s.note ? `：${s.note.slice(0, 30)}` : ""}`}</span></span>
                </button>))}
              {!d.discoveries.length && <div className="row text-[12.5px] text-ink-3">当天没有</div>}
            </div>
          </div>))}
      </div>
    </Group>
  );
}

// 谁在忙（泳道）：只画人和觉，点是一个动作 ----------------------------------------------------------------
function tone(i: MonthItem) {
  if (i.kind === "question_published") return ["trial_risk", "stale_capability", "leak_risk", "knowledge_conflict", "opportunity"].includes(i.family ?? "")
    ? "bg-attn" : "bg-accent";
  if (i.kind === "trial" && i.text.includes("失败")) return "bg-danger";
  if (["access_frozen", "capability_suspended", "evidence_changed"].includes(i.kind)) return "bg-danger";
  if (i.kind === "question_resolved" && !i.actor.startsWith("jue")) return "bg-[#30c25b]";
  if (i.kind === "product_released") return "bg-[#30c25b]";
  return "bg-[#b9b9c0]";
}

function pack(sessions: MonthSession[]) {
  const rows: number[] = [];
  return sessions.map((s) => {
    const a = minutes(s.start), b = Math.max(minutes(s.end), a + 12);
    let r = rows.findIndex((end) => end <= a);
    if (r < 0) { r = rows.length; rows.push(0); }
    rows[r] = b;
    return { s, r };
  });
}

function Lanes({ data }: { data: MonthDay }) {
  const [pick, setPick] = useState<MonthItem | null>(null);
  const items = data.items.filter((i) => i.lane !== "qi" && i.kind !== "question_prepared" && i.kind !== "auto_executed");
  const byLane = useMemo(() => {
    const m: Record<string, MonthItem[]> = {};
    for (const i of items) (m[i.lane] ??= []).push(i);
    return m;
  }, [data]);
  const packed = useMemo(() => pack(data.sessions), [data]);
  const custRows = Math.max(1, ...packed.map((x) => x.r + 1));
  const hours = Array.from({ length: 10 }, (_, k) => 9 + k);
  const lanes = data.lanes.filter((l) => l.id !== "qi");
  return (
    <Group title="谁在忙" aside={<span className="text-ink-3">一个点 = 一个动作 · 蓝：觉提出 · 橙：预判与异常 · 绿：人签字 · 红：失败、冻结 · 横条：一段客户来访</span>}>
      <div className="relative overflow-x-auto px-4 py-3">
        <div className="min-w-[960px]">
          <div className="relative ml-[150px] h-5 text-[11px] text-ink-3">
            {hours.map((h) => <span key={h} className="num absolute -translate-x-1/2" style={{ left: `${((h * 60 - OPEN) / SPAN) * 100}%` }}>{h}:00</span>)}
          </div>
          {lanes.map((l) => {
            const cust = l.id === "customer";
            const height = cust ? custRows * 10 + 8 : 22;
            return (
              <div key={l.id} className="flex items-stretch border-t border-sep">
                <div className="w-[150px] shrink-0 truncate py-1 pr-2 text-[12px] text-ink-2" title={l.label}>
                  {name(l.label)}<span className="ml-1 text-ink-3">{(cust ? data.sessions.length : byLane[l.id]?.length) || ""}</span></div>
                <div className="relative flex-1" style={{ height }}>
                  {hours.map((h) => <i key={h} className="absolute inset-y-0 w-px bg-sep" style={{ left: `${((h * 60 - OPEN) / SPAN) * 100}%` }} />)}
                  {cust && packed.map(({ s, r }) => (
                    <i key={s.id} title={`${s.id} ${s.customer} ${s.phenomenon ?? ""} → ${s.status}`}
                       className={`absolute h-[7px] rounded-full ${s.status === "recommended" ? "bg-[#30c25b]/70" : s.status === "escalated" ? "bg-accent/70" : "bg-[#b9b9c0]"}`}
                       style={{ left: pos(s.start), top: 4 + r * 10, width: `max(6px, calc(${pos(s.end)} - ${pos(s.start)}))` }} />))}
                  {!cust && (byLane[l.id] ?? []).map((i) => (
                    <button key={i.id} title={`${hhmm(i.at)} ${i.text}`} onClick={() => setPick(i)}
                            className={`absolute h-[9px] w-[9px] -translate-x-1/2 rounded-full ring-1 ring-white ${tone(i)}`}
                            style={{ left: pos(i.at), top: 6 }} />))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {pick && <div className="row text-[13px]"><span className="num text-ink-3">{hhmm(pick.at)}</span>{pick.text}<button className="link ml-auto" onClick={() => setPick(null)}>关闭</button></div>}
    </Group>
  );
}
