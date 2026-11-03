// V11.8 CEO 面（CEO-VIEW C3、C4、C5）：同一批客户需求放在流水线上跑——旧线是传化原来的流程（按参数推算），
// 化言线是这些事实际走过的路径（门面 pipeline，这一局或模拟业务月）。第一屏是三个岗位的时间构成和三个头条数字，
// V12.10 加组织变化热力图（岗位 × 事：旧流程里谁做、化言里谁做）、AI 成本（网关计量折成钱，与省下的人工同一账本），
// 流水线加中间一条「只有 Agent，没有觉」（Story.tsx 三种做法的口径）。
// 来单量按参数放大成一个月，人工工位按「人数 × 现状交叉占用的比例」排队，觉、契、Agent 不排队。
// 账本与排队都在这里按参数算，改参数即重算；每个数带来源标签。撤销一条能力只是推演，不改任何状态。
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";
import type { CeoCase, CeoData, CeoParams, LlmUsage, MonthProgress, OldFlowStation } from "../types";
import { Group, PageHead } from "../components/ui";

export type Basis = "given" | "safe";   // 照参数文件 / 按最保守参数
type Role = "sales" | "pm" | "rd";
// 时间构成与头条数字只用到各件的旧流程推算与两个时刻；结算页（V11.9）给的就是这么多
export type Ledger = Pick<CeoData, "bars"> & { cases: Pick<CeoCase, "given" | "safe" | "arrived" | "answered">[] };
const GAIN = "#248a3d";
const CROSS = ["#e08a2b", "#c7a25a"];
const ROLE: Record<Role, string> = { sales: "销售", pm: "产品经理", rd: "研发" };
const OWN_GOAL: Record<Role, string> = { sales: "销售额、回款率、新客户数", pm: "产品线利润、新品上市数量", rd: "新品转化率、专利数、配方稳定性" };
// 旧流程工位 → 流水线上的工位（研发提供的流程图：需求 → 销售记录 → 产品经理转述 → 研发开发 → 产品经理评价 → 销售开单）
const LANE: Record<string, string> = {
  业务员答技术问题: "销售记录", 业务员记录需求: "销售记录", 产品经理查资料答复: "产品经理转述", 产品经理转述: "产品经理转述",
  研发看单判断: "研发开发", 补问一轮: "研发开发", 试样返工一轮: "研发开发", 产品经理评价: "产品经理评价", 业务员报价: "销售开单", 业务员开单: "销售开单",
};
const HUMAN_LANES = ["销售记录", "产品经理转述", "研发开发", "产品经理评价", "销售开单"];
const MACHINE = ["觉", "契", "Agent"];
const LANE_ROLE: Record<string, Role> = { 销售记录: "sales", 销售开单: "sales", 产品经理转述: "pm", 产品经理评价: "pm", 研发开发: "rd" };
const SPEEDS: [number, string][] = [[0.5, "慢"], [2.8, "一分钟一个月"], [8, "快"]];
const MONTH = 168;   // 一个月按 168 个工作小时排

export const Src = ({ s }: { s: string }) => (
  <span className={`tag !h-[18px] !px-1.5 !text-[11px] !font-normal ${s === "假设" ? "tag-warn" : s === "推算" ? "" : "tag-accent"}`}>{s}</span>
);
export const hours = (h: number) => (h < 1 ? `${Math.max(1, Math.round(h * 60))} 分钟` : h < 48 ? `${+h.toFixed(1)} 小时` : `${+(h / 24).toFixed(1)} 天`);
const work = (h: number) => (h < 8 ? hours(h) : `${+(h / 8).toFixed(1)} 个工作日`);   // 流水线按工作小时排，每天 8 小时
const money = (y: number) => (Math.abs(y) >= 1e4 ? `${+(y / 1e4).toFixed(1)} 万元` : `${Math.round(y)} 元`);
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0; };
const perCase = (cases: Ledger["cases"], set: Basis, f: (r: OldFlowStation) => number) =>
  cases.reduce((n, c) => n + c[set].old.stations.reduce((m, r) => m + f(r), 0), 0) / Math.max(cases.length, 1);

// ---------- 排队：每件货依次过工位；人工工位按岗位共用的人手先到先排，交接等待、补问往返、试样周期照参数 ----------
type Visit = { lane: string; role: Role | null; hours: number; wait: number; loop: boolean };
type Seg = Visit & { ready: number; start: number; end: number };
type Good = { i: number; c: CeoCase; arrive: number; plan: Visit[]; segs: Seg[]; done: number };
type Mode = "old" | "agent" | "now";   // 传化原来的流程 / 只有 Agent 没有觉 / 化言

function visits(c: CeoCase, set: Basis, p: CeoParams, mode: Mode, i: number, revoked: boolean): Visit[] {
  const draw = ((i * 0.6180339887) % 1);       // 期望次数的小数部分：第 i 件按黄金分割取整，同一批货分得均匀、每次一样
  let prev = "customer";
  const out: Visit[] = [];
  if (mode === "now") {
    for (const s of MACHINE) if (c.stations.some((x) => x.station === s)) out.push({ lane: s, role: null, hours: 1 / 60, wait: 0, loop: false });
    if (revoked) return [...out, { lane: "研发开发", role: "rd", hours: p.minutes.rd_review / 60, wait: p.wait_hours, loop: true }];
  }
  if (mode === "agent") out.push({ lane: "Agent", role: null, hours: 1 / 60, wait: 0, loop: false });
  for (const r of mode === "agent" ? c[set].agent.stations : c[set].old.stations) {
    const times = mode === "now" ? r.now_times ?? r.times : r.times;
    const n = Math.floor(times) + (times % 1 > draw ? 1 : 0);
    for (let k = 0; k < n; k++) {
      const wait = r.station === "补问一轮" ? 6 * p.wait_hours : r.station === "试样返工一轮" ? p.trial_wait_hours : r.role !== prev ? p.wait_hours : 0;
      out.push({ lane: LANE[r.station], role: r.role, hours: r.minutes / r.times / 60, wait, loop: r.station === "补问一轮" || r.station === "试样返工一轮" });
      prev = r.role;
    }
  }
  return out;
}

function simulate(cases: CeoCase[], set: Basis, p: CeoParams, n: number, mode: Mode, revoked: (c: CeoCase) => boolean): Good[] {
  const share = (role: Role) => 1 - p.time_split[role].own / 100;
  const free: Record<Role, number[]> = Object.fromEntries((["sales", "pm", "rd"] as Role[]).map((r) =>
    [r, Array(Math.max(1, Math.round(p[`${r}_people`] * share(r)))).fill(0)])) as Record<Role, number[]>;
  const goods: Good[] = Array.from({ length: n }, (_, i) => {
    const c = cases[i % cases.length];
    return { i, c, arrive: (i * MONTH) / n, plan: visits(c, set, p, mode, i, mode === "now" && revoked(c)), segs: [], done: (i * MONTH) / n };
  });
  // 先到先服务：每次取最早就绪的一步，交给这个岗位最早空出来的人（最小堆按就绪时刻排）
  const heap: [number, number][] = [];
  const swap = (a: number, b: number) => { [heap[a], heap[b]] = [heap[b], heap[a]]; };
  const push = (x: [number, number]) => {
    heap.push(x);
    for (let k = heap.length - 1; k && heap[(k - 1) >> 1][0] > heap[k][0]; k = (k - 1) >> 1) swap(k, (k - 1) >> 1);
  };
  const pop = () => {
    const top = heap[0], last = heap.pop()!;
    if (heap.length) {
      heap[0] = last;
      for (let k = 0, m = 0; ; k = m) {
        for (const c of [2 * k + 1, 2 * k + 2]) if (c < heap.length && heap[c][0] < heap[m][0]) m = c;
        if (m === k) break;
        swap(k, m);
      }
    }
    return top;
  };
  goods.forEach((g) => g.plan.length && push([g.arrive + g.plan[0].wait, g.i]));
  while (heap.length) {
    const [ready, i] = pop();
    const g = goods[i], v = g.plan[g.segs.length];
    let start = ready;
    if (v.role) {
      const pool = free[v.role], k = pool.indexOf(Math.min(...pool));
      start = Math.max(ready, pool[k]);
      pool[k] = start + v.hours;
    }
    g.segs.push({ ...v, ready, start, end: start + v.hours });
    g.done = start + v.hours;
    const next = g.plan[g.segs.length];
    if (next) push([g.done + next.wait, i]);
  }
  return goods;
}

export function Ceo() {
  const { me, meta, version, fail } = useApp();
  const [source, setSource] = useState<string>("this");   // this = 这一局 / 试用实例；其余是模拟业务月的运行号
  const runs = useData<MonthProgress[]>(() => api.monthRuns(), []) ?? [];
  const [data, setData] = useState<CeoData | null>(null);
  useEffect(() => {
    (source === "this" ? api.ceo(me) : api.monthCeo(source, me)).then(setData, fail);
  }, [source, me, version]);
  const [set, setSet] = useState<Basis>("given");
  const [edits, setEdits] = useState<Record<string, number>>({});   // CEO 拖动的规模与单价
  const [volume, setVolume] = useState(1);
  const [revoke, setRevoke] = useState<string>("");
  const [pick, setPick] = useState<CeoCase | null>(null);
  if (!data) return <p className="p-10 text-ink-2">正在汇总……</p>;
  if (!data.cases.length) return <p className="p-10 text-ink-2">还没有客户需求。</p>;
  const p = { ...data.params[set], ...edits } as CeoParams;
  const live = source === "this" && !!meta.trial && !meta.play;
  const tag = live ? "实测" : "模拟";
  const assumed = (k: string) => data.params.given.assumed.includes(k) && !(k in edits);
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-6 px-8 pb-24 pt-7">
      <PageHead title="CEO 面" subtitle={<>同一批客户需求，上面按传化原来的流程走（<Src s="推算" />），下面是化言实际走过的路径（<Src s={tag} />）。研发的话只给计数，不给内容。</>}
        aside={<div className="flex flex-wrap justify-end gap-1.5">
          <button className={`chip ${source === "this" ? "!bg-ink !text-white" : ""}`} onClick={() => { setSource("this"); setPick(null); }}>{meta.play ? "这一局" : meta.trial ? "试用实例" : "当前运行"}</button>
          {runs.filter((r) => r.group === "jue").map((r) => (
            <button key={r.run_id} className={`chip ${source === r.run_id ? "!bg-ink !text-white" : ""}`} onClick={() => { setSource(r.run_id!); setPick(null); }}>
              模拟业务月 · 第 {r.day} 天</button>))}
          <button className={`chip ${set === "safe" ? "!bg-[#248a3d] !text-white" : ""}`} onClick={() => { setSet(set === "safe" ? "given" : "safe"); setEdits({}); }}
                  title="转述少丢条件、研发早发现、工位快、交接等待短、人工与试样便宜：差距往小里算">按最保守参数</button>
        </div>} />
      <TimeBars data={data} set={set} />
      <Heatmap data={data} set={set} tag={tag} />
      <Headline data={data} set={set} p={p} volume={volume} tag={tag} assumed={assumed} />
      <AiCost data={data} set={set} p={p} volume={volume} assumed={assumed} />
      <Params p={p} set={(k, v) => setEdits({ ...edits, [k]: v })} volume={volume} setVolume={setVolume} assumed={assumed} />
      <Lines data={data} set={set} p={p} n={Math.max(1, Math.round(p.monthly_inquiries * volume))} revoke={revoke} setRevoke={setRevoke} onPick={setPick} tag={tag} />
      {pick && <CaseDetail c={pick} set={set} names={data.names} onClose={() => setPick(null)} />}
    </div>
  );
}

// ---------- 第一屏：三个岗位的时间构成，现状 → 化言 ----------
export function TimeBars({ data, set }: { data: Ledger; set: Basis }) {
  const strip = (own: number, segs: number[]) => (
    <div className="flex h-[20px] overflow-hidden rounded-[5px] bg-fill text-[11px] font-semibold leading-[20px] text-white transition-all">
      <div style={{ width: `${own}%`, background: GAIN, transition: "width .8s" }} className="truncate px-1.5">本职 {Math.round(own)}%</div>
      {segs.map((pct, i) => pct > 0 && <div key={i} style={{ width: `${pct}%`, background: CROSS[i], transition: "width .8s" }} className="truncate px-1">{Math.round(pct)}%</div>)}
    </div>
  );
  const bars = data.bars[set];
  return (
    <Group title="三个岗位的时间用在哪里" foot={<>现状比例从研发提供的《岗位工作范围对比（实际现状）》图上量出 <Src s={bars.rd.split_source} />，待确认是估计还是统计；化言一侧按这批事里交叉工位实际少发生的次数缩短 <Src s="推算" />。</>}>
      <div className="grid grid-cols-3 gap-5 px-4 py-3.5 text-[12.5px]">
        {(["sales", "pm", "rd"] as Role[]).map((r) => (
          <div key={r} className="flex flex-col gap-1.5">
            <p className="font-semibold">{ROLE[r]}</p>
            <p className="text-ink-2">现状</p>{strip(bars[r].own_before, bars[r].segments.map((x) => x.before))}
            <p className="text-ink-2">化言</p>{strip(bars[r].own_after, bars[r].segments.map((x) => x.after))}
            <p className="text-[11.5px] text-ink-2">本职对应：{OWN_GOAL[r]}</p>
          </div>
        ))}
      </div>
    </Group>
  );
}

// ---------- 三个头条数字：每个都能点开看算式与来源 ----------
// 一年省下的钱：各岗位每件少花的工时 × 时薪，加少返工的试样，都按每月件数 × 12
function savings(cs: Ledger["cases"], set: Basis, p: CeoParams, v: number) {
  const saved = (role: Role) => perCase(cs, set, (r) => (r.role === role ? r.minutes - (r.now_minutes ?? r.minutes) : 0));
  const reworks = perCase(cs, set, (r) => (r.station === "试样返工一轮" ? r.times - (r.now_times ?? r.times) : 0));
  const yearly = { rd: (12 * v * saved("rd") / 60) * p.rd_hour_cost, sales: (12 * v * saved("sales") / 60) * p.sales_hour_cost,
                   pm: (12 * v * saved("pm") / 60) * p.pm_hour_cost, trial: 12 * v * reworks * p.trial_cost };
  return { saved, reworks, yearly, total: yearly.rd + yearly.sales + yearly.pm + yearly.trial };
}

export function Headline({ data, set, p, volume, tag, assumed }: { data: Ledger; set: Basis; p: CeoParams; volume: number; tag: string; assumed: (k: string) => boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const cs = data.cases;
  const v = p.monthly_inquiries * volume;
  const { saved, reworks, yearly, total } = savings(cs, set, p, v);
  const rdHours = (v * saved("rd")) / 60;
  const oldWait = median(cs.map((c) => c[set].first_reply_hours));
  const nowWait = median(cs.filter((c) => c.answered).map((c) => (Date.parse(c.answered!) - Date.parse(c.arrived)) / 3.6e6));
  const P = ({ k, children }: { k: string; children: React.ReactNode }) => <span className="num">{children}{assumed(k) && <Src s="假设" />}</span>;
  const cards = [
    { label: "还给研发的时间", value: `每月 ${Math.round(rdHours)} 小时`, sub: `相当于多招 ${(Math.round((rdHours / p.work_hours_month) * 10) / 10 || 0).toFixed(1)} 名研发；研发本职 ${data.bars[set].rd.own_before}% → ${Math.round(data.bars[set].rd.own_after)}%`,
      formula: <>每件事研发少花 <span className="num">{saved("rd").toFixed(1)}</span> 分钟（这 {cs.length} 件事里补问、返工、看单实际少发生的次数 × 每次耗时 <Src s="推算" />）× 每月 <P k="monthly_inquiries">{Math.round(v)}</P> 件 ÷ 60；再 ÷ 每人每月 <P k="work_hours_month">{p.work_hours_month}</P> 工时</> },
    { label: "客户等第一个答复", value: `${hours(oldWait)} → ${hours(nowWait)}`, sub: nowWait > 0 ? `快约 ${Math.round(oldWait / nowWait)} 倍（中位数）` : "",
      formula: <>旧流程：业务员当场答或转产品经理查资料原路回来；要研发判断的经记录、转述到研发看单再原路回来，每次交接等 <P k="wait_hours">{p.wait_hours}</P> 小时 <Src s="推算" />。化言：客户第一句到推荐、业务员答复或研发本人处理的时刻 <Src s={tag} /></> },
    { label: "一年多出来的钱", value: money(total), sub: "研发、业务员与产品经理工时，加少失败的试样",
      formula: <>研发 {money(yearly.rd)}（时薪 <P k="rd_hour_cost">{p.rd_hour_cost}</P>）+ 业务员 {money(yearly.sales)}（<P k="sales_hour_cost">{p.sales_hour_cost}</P>）+ 产品经理 {money(yearly.pm)}（<P k="pm_hour_cost">{p.pm_hour_cost}</P>）+ 试样 {money(yearly.trial)}（每件少返工 <span className="num">{reworks.toFixed(2)}</span> 轮 × <P k="trial_cost">{p.trial_cost}</P> 元）。都按每月件数 × 12 <Src s="推算" />；更快响应多赢下的单不计入</> },
  ];
  return (
    <div className="grid grid-cols-3 gap-4">
      {cards.map((c, i) => (
        <button key={c.label} onClick={() => setOpen(open === i ? null : i)} className="group flex flex-col items-start gap-1 rounded-[12px] bg-white px-4 py-3.5 text-left shadow-[0_0_0_.5px_rgba(0,0,0,.08),0_1px_3px_rgba(0,0,0,.05)]">
          <p className="eyebrow">{c.label}</p>
          <p className="num text-[26px] font-semibold leading-8" style={{ color: GAIN }}>{c.value}</p>
          <p className="text-[12.5px] text-ink-2">{c.sub}</p>
          {open === i ? <p className="mt-1 border-t border-sep pt-2 text-[12px] leading-5 text-ink-2">{c.formula}</p>
            : <p className="text-[11.5px] text-accent">看算式</p>}
        </button>
      ))}
    </div>
  );
}

// ---------- 参数：来单量与规模、单价。默认照参数文件，假设的逐项标出 ----------
function Params({ p, set, volume, setVolume, assumed }: { p: CeoParams; set: (k: string, v: number) => void; volume: number; setVolume: (v: number) => void; assumed: (k: string) => boolean }) {
  const fields: [string, string][] = [["monthly_inquiries", "每月询问（件）"], ["sales_people", "业务员（人）"], ["pm_people", "产品经理（人）"], ["rd_people", "研发（人）"],
    ["rd_hour_cost", "研发时薪"], ["sales_hour_cost", "业务员时薪"], ["pm_hour_cost", "产品经理时薪"], ["trial_cost", "一轮试样（元）"],
    ["llm_input_price", "模型输入（元/百万 token）"], ["llm_output_price", "模型输出（元/百万 token）"]];
  return (
    <Group title="参数" foot="传化没给的数都是假设（黄标），可以直接改；改了账本和流水线立即重算。来单量只放大推算与模拟的数据。">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 px-4 py-3 text-[12.5px]">
        <label className="flex items-center gap-2 font-semibold">来单量 ×{volume}
          <input type="range" min={1} max={3} step={0.5} value={volume} onChange={(e) => setVolume(+e.target.value)} className="w-28" /></label>
        {fields.map(([k, label]) => (
          <label key={k} className="flex items-center gap-1.5 text-ink-2">{label}
            <input type="number" value={p[k]} onChange={(e) => set(k, +e.target.value)} className="field num !w-[72px] !py-0.5 !text-[12.5px]" />
            {assumed(k) && <Src s="假设" />}
          </label>
        ))}
      </div>
    </Group>
  );
}

// ---------- 两条流水线 ----------
function Lines({ data, set, p, n, revoke, setRevoke, onPick, tag }: {
  data: CeoData; set: Basis; p: CeoParams; n: number; revoke: string; setRevoke: (id: string) => void; onPick: (c: CeoCase) => void; tag: string;
}) {
  const revoked = (c: CeoCase) => !!revoke && c.used.includes(revoke) && (c.path === "自助解决" || c.reused);
  const old = useMemo(() => simulate(data.cases, set, p, n, "old", revoked), [data, set, p, n]);
  const agent = useMemo(() => simulate(data.cases, set, p, n, "agent", revoked), [data, set, p, n]);
  const now = useMemo(() => simulate(data.cases, set, p, n, "now", revoked), [data, set, p, n, revoke]);
  const horizon = Math.max(...old.map((g) => g.done), ...agent.map((g) => g.done), ...now.map((g) => g.done), MONTH);
  const [t, setT] = useState(0);
  const [speed, setSpeed] = useState(2.8);
  const [run, setRun] = useState(true);
  useEffect(() => {
    if (!run) return;
    const timer = setInterval(() => setT((x) => (x >= horizon ? x : Math.min(horizon, x + speed / 10))), 100);
    return () => clearInterval(timer);
  }, [run, speed, horizon]);
  const affected = data.cases.filter(revoked).length;
  const stat = (goods: Good[]) => ({
    lead: median(goods.map((g) => g.done - g.arrive)),
    month: goods.filter((g) => g.done <= MONTH).length,
    rd: goods.filter((g) => g.segs.some((s) => s.lane === "研发开发")).length,
    loops: goods.reduce((k, g) => k + g.segs.filter((s) => s.loop).length, 0),
  });
  const so = stat(old), sa = stat(agent), sn = stat(now);
  const people = (k: "old" | "agent" | "now") => (data.cases.reduce((m, c) => m + c[set][k].roles.length, 0) / data.cases.length).toFixed(1);
  const self = data.cases.filter((c) => c.path === "自助解决").length;
  const fresh = data.caps.filter((c) => c.new);
  return (
    <Group title="三条流水线" aside={<span className="flex items-center gap-2">
      <span className="num text-ink-2">第 {Math.floor(t / 8) + 1} 个工作日 {Math.floor(t % 8) + 9}:00</span>
      <button className="btn btn-plain !h-7" onClick={() => setRun(!run)}>{run ? "暂停" : "继续"}</button>
      <button className="btn btn-plain !h-7" onClick={() => setT(0)}>从头</button>
      {SPEEDS.map(([v, label]) => <button key={v} className={`btn btn-plain !h-7 ${speed === v ? "!text-accent" : ""}`} onClick={() => setSpeed(v)}>{label}</button>)}
    </span>} foot={<>每月 {n} 件按这 {data.cases.length} 件事的路径轮流放大 <Src s="推算" />；人工工位按「人数 × 现状交叉占用的比例」排队，排得越久颜色越深；点工位看停在那里的事，点一件看它的经过。</>}>
      <div className="flex flex-col gap-4 px-4 py-4">
        <Line title="传化原来的流程" src={<><Src s="推算" />{data.params.given.assumed.length > 0 && <Src s="假设" />}</>} goods={old} lanes={HUMAN_LANES} t={t} onPick={onPick} />
        <Line title="只有 Agent，没有觉" src={<Src s="推算" />} goods={agent} lanes={["Agent", ...HUMAN_LANES]} t={t} onPick={onPick}
              note="记录、转述、查资料由 Agent 起草；没人在客户还在时提示该问什么，到研发的需求照样缺条件（失真对照：应升级的卡一次性翻译与业务员转述退回同为 95.1%），研发签过的判断也不会替他答下一单" />
        <Line title="化言" src={<Src s={tag} />} goods={now} lanes={[...MACHINE, ...HUMAN_LANES]} t={t} onPick={onPick} />
        <div className="grid grid-cols-4 gap-3 border-t border-sep pt-3 text-[12.5px]">
          <Metric label="一件需求从进来到办完（中位数）" old={work(so.lead)} mid={work(sa.lead)} now={work(sn.lead)} />
          <Metric label="当月办完" old={`${so.month} / ${n} 件`} mid={`${sa.month} / ${n} 件`} now={`${sn.month} / ${n} 件`} />
          <Metric label="进研发" old={`${so.rd} 件`} mid={`${sa.rd} 件`} now={`${sn.rd} 件`} />
          <Metric label="补问与返工绕回" old={`${so.loops} 圈`} mid={`${sa.loops} 圈`} now={`${sn.loops} 圈`} />
          <Metric label="一件需求经过几个人（不含客户）" old={people("old")} mid={people("agent")} now={people("now")} />
          <Metric label="客户自助解决" old="0" mid="0" now={`${Math.round((self / data.cases.length) * 100)}%`} />
          <Metric label="研发这一局新签的判断" old="—" now={fresh.length ? `${fresh.length} 条，替他答了 ${data.cases.filter((c) => c.reused).length} 件` : "还没有"} />
          <div className="flex flex-col gap-1">
            <p className="text-ink-2">撤销一条能力（推演，不改状态）</p>
            <select className="field !py-0.5 !text-[12.5px]" value={revoke} onChange={(e) => setRevoke(e.target.value)}>
              <option value="">不撤销</option>
              {data.caps.map((c) => <option key={c.id} value={c.id}>{c.product} 治{c.phenomenon} · {c.granted_by.replace("（模拟）", "")}签{c.new ? "（这一局）" : ""}</option>)}
            </select>
            {revoke && <p className="text-attn-ink">这批里 {affected} 件（放大后每月约 {Math.round((affected / data.cases.length) * n)} 件）改道交研发</p>}
          </div>
        </div>
      </div>
    </Group>
  );
}

const Metric = ({ label, old, mid, now }: { label: string; old: string; mid?: string; now: string }) => (
  <div className="flex flex-col gap-0.5">
    <p className="text-ink-2">{label}</p>
    <p className="num"><span className="text-ink-3">{old}</span>{mid && <> → <span className="text-ink-2">{mid}</span></>} → <span className="font-semibold" style={{ color: GAIN }}>{now}</span></p>
  </div>
);

function Line({ title, src, goods, lanes, t, onPick, note }: { title: string; src: React.ReactNode; goods: Good[]; lanes: string[]; t: number; onPick: (c: CeoCase) => void; note?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  const at = (lane: string) => goods.flatMap((g) => g.segs.filter((s) => s.lane === lane && s.ready <= t && t < s.end).map((s) => ({ g, s })));
  const arrived = goods.filter((g) => g.arrive <= t).length, done = goods.filter((g) => g.done <= t).length;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="flex items-center gap-1.5 text-[13px] font-semibold">{title}{src}{note && <span className="text-[11.5px] font-normal text-ink-2">{note}</span>}</p>
      <div className="flex items-stretch gap-1.5">
        <Box label="需求" count={arrived} />
        {lanes.map((lane) => {
          const here = at(lane);
          const waiting = here.filter((x) => x.s.start > t);
          const longest = Math.max(0, ...waiting.map((x) => t - x.s.ready));
          return (
            <button key={lane} onClick={() => setOpen(open === lane ? null : lane)}
                    className={`flex min-h-[86px] flex-1 flex-col gap-1 rounded-[9px] px-2 py-1.5 text-left ${MACHINE.includes(lane) ? "border border-dashed border-[rgba(10,108,223,.4)] bg-[rgba(10,108,223,.04)]" : "bg-fill"} ${open === lane ? "ring-2 ring-accent" : ""}`}>
              <span className="text-[12px] font-semibold">{lane}</span>
              <span className="flex flex-wrap gap-[3px]">
                {here.slice(0, 40).map(({ g, s }) => {
                  const wait = s.start > t ? Math.min(1, (t - s.ready) / 8) : 0;   // 等得越久越深，一个工作日封顶
                  return <i key={`${g.i}-${s.ready}`} className="h-[7px] w-[7px] rounded-[2px]"
                            style={{ background: s.start > t ? `rgba(224,138,43,${0.35 + 0.65 * wait})` : s.loop ? "#d70015" : "#0a6cdf" }} />;
                })}
              </span>
              <span className="num mt-auto text-[11px] text-ink-2">{here.length ? `${here.length} 件${waiting.length ? `，排队最久 ${work(longest)}` : ""}` : ""}</span>
            </button>
          );
        })}
        <Box label="办完" count={done} />
      </div>
      {open && (
        <div className="flex flex-wrap gap-1.5 text-[12px]">
          {at(open).slice(0, 12).map(({ g }) => (
            <button key={g.i} className="chip" onClick={() => onPick(g.c)}>第 {g.i + 1} 件 · {g.c.path} · 「{g.c.quote.slice(0, 12)}」</button>
          ))}
          {!at(open).length && <span className="text-ink-2">此刻没有事停在这里</span>}
        </div>
      )}
    </div>
  );
}

const Box = ({ label, count }: { label: string; count: number }) => (
  <div className="flex w-[64px] flex-col items-center justify-center rounded-[9px] bg-white text-[12px] shadow-[0_0_0_.5px_rgba(0,0,0,.08)]">
    <span className="text-ink-2">{label}</span><span className="num text-[17px] font-semibold">{count}</span>
  </div>
);

// ---------- 单件经过：化言实际走过的工位与经手人（不带研发写的话），旧流程会怎么走 ----------
function CaseDetail({ c, set, names, onClose }: { c: CeoCase; set: Basis; names: Record<string, string>; onClose: () => void }) {
  const time = (s: string) => s.slice(5, 16).replace("T", " ");
  const est = c[set];
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.scrollIntoView({ behavior: "smooth", block: "start" }), [c.session_id]);
  return (
    <div ref={ref}><Group title={<>一件事的经过：「{c.quote}」</>} aside={<button className="text-[12px] text-accent" onClick={onClose}>收起</button>}>
      <div className="flex flex-col gap-3 px-4 py-3.5 text-[12.5px]">
        <div>
          <p className="eyebrow pb-1">化言实际走过（{c.path}{c.reused ? "，研发这一局签的判断替他答了" : ""}）</p>
          <div className="flex flex-wrap gap-1">
            {c.stations.filter((s) => s.station !== "客户").map((s, i) => (
              <span key={i} className={`tag !font-normal ${s.loop ? "tag-danger" : MACHINE.includes(s.station) ? "tag-accent" : ""}`}
                    title={`${time(s.enter)}–${time(s.leave)} · ${s.by.map((a) => names[a] ?? a).join("、")}`}>{s.station}{s.loop ? " ↺" : ""} <span className="num ml-1 text-ink-3">{time(s.enter)}</span></span>
            ))}
          </div>
        </div>
        <div>
          <p className="eyebrow pb-1">按传化原来的流程（推算）</p>
          <p className="text-ink-2">{est.old.stations.map((r) => `${r.station}${r.times !== 1 ? ` ×${r.times}` : ""}`).join(" → ")}</p>
          <p className="num text-ink-2">经过 {est.old.roles.join("、")}；交接 {est.old.handoffs} 次；人工 {est.old.work_hours} 小时，等待约 {est.old.wait_hours} 小时；客户等第一个答复约 {hours(est.first_reply_hours)}</p>
        </div>
      </div>
    </Group></div>
  );
}

// ---------- V12.10 组织变化热力图：岗位 × 事。旧流程里这些事全由人做；化言里人还做几次，空出来的由谁接走 ----------
const WORK = ["业务员答技术问题", "业务员记录需求", "产品经理查资料答复", "产品经理转述", "研发看单判断", "补问一轮", "试样返工一轮", "产品经理评价", "业务员报价", "业务员开单"];
// 空出来的那几次由谁接走：客户自助时契用研发签过的能力答；觉抽取需求、在客户还在时提示追问；产品经理 Agent 起草产品需求；试样少失败是没发生
const TAKEN: Record<string, string> = { 业务员答技术问题: "契", 业务员记录需求: "觉", 产品经理查资料答复: "契", 产品经理转述: "Agent", 研发看单判断: "契", 补问一轮: "觉" };
const ROWS: [string, Role | null][] = [["业务员", "sales"], ["产品经理", "pm"], ["研发", "rd"], ["觉", null], ["契", null], ["Agent", null]];

function Heatmap({ data, set, tag }: { data: CeoData; set: Basis; tag: string }) {
  const [view, setView] = useState<"old" | "now">("now");
  const rows = data.cases.flatMap((c) => c[set].old.stations);
  const sum = (name: string, f: (r: OldFlowStation) => number) => rows.filter((r) => r.station === name).reduce((n, r) => n + f(r), 0);
  const old = (name: string) => sum(name, (r) => r.times), now = (name: string) => sum(name, (r) => r.now_times ?? r.times);
  const cols = WORK.filter((w) => old(w) > 0);
  const top = Math.max(...cols.map(old), ...Object.values(data.signs), 1);
  const role = (w: string) => rows.find((r) => r.station === w)!.role;
  const n = (x: number) => (Number.isInteger(x) ? x : x.toFixed(1));
  const cell = (row: string, r: Role | null, w: string) => {
    if (r ? role(w) !== r : view === "old" || TAKEN[w] !== row) return <td key={w} className="border border-sep" />;
    const value = r ? (view === "old" ? old(w) : now(w)) : old(w) - now(w);
    if (!r && value <= 0) return <td key={w} className="border border-sep" />;
    const freed = r && view === "now" && value === 0;
    return <td key={w} className="border border-sep px-1 py-1.5 text-center num transition-colors duration-700"
               style={{ background: freed ? "transparent" : r ? `rgba(224,138,43,${0.12 + 0.75 * value / top})` : `rgba(10,108,223,${0.1 + 0.6 * value / top})` }}>
      {freed ? <span className="text-[11px] text-ok">空出</span> : value > 0 ? n(value) : ""}
      {r && view === "now" && value < old(w) && !freed && <span className="block text-[10.5px] text-ink-3">原 {n(old(w))}</span>}
    </td>;
  };
  return (
    <Group title="组织变化：岗位 × 事" aside={<span className="flex gap-1.5">
      {(["old", "now"] as const).map((k) => <button key={k} className={`chip ${view === k ? "!bg-ink !text-white" : ""}`} onClick={() => setView(k)}>{k === "old" ? "传化原来的流程" : "化言"}</button>)}
    </span>} foot={<>这 {data.cases.length} 件事，每格是这件事落在这个岗位上的次数：旧流程按参数推算 <Src s="推算" />，化言照这些事实际的经过数 <Src s={tag} />。
      人不再做的格子写「空出」，接走它的觉、契、Agent 在下面三行；试样少失败的那几轮没有人接，是没再发生。最右一列是化言里人留下来的事：签字与专业判断。</>}>
      <div className="overflow-x-auto px-4 py-3">
        <table className="w-full border-collapse text-[12px]">
          <thead><tr><th className="w-[72px]" />{cols.map((w) => <th key={w} className="px-1 pb-1.5 font-normal text-ink-2">{w}</th>)}
            <th className="px-1 pb-1.5 font-normal text-ink-2">签字与专业判断</th></tr></thead>
          <tbody>{ROWS.map(([label, r]) => <tr key={label}>
            <td className={`pr-2 font-semibold ${r ? "" : "text-accent"}`}>{label}</td>
            {cols.map((w) => cell(label, r, w))}
            <td className="border border-sep px-1 py-1.5 text-center num"
                style={{ background: r && view === "now" ? `rgba(36,138,61,${0.12 + 0.6 * (data.signs[r] ?? 0) / top})` : "transparent" }}>
              {r && view === "now" ? data.signs[r] ?? 0 : ""}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </Group>
  );
}

// ---------- V12.10 AI 成本：网关计量的 token 按单价折成钱，与省下的人工放在同一本账上 ----------
const cents = (y: number) => (y < 100 ? `${y.toFixed(2)} 元` : money(y));
const HUAYAN_CALLERS: Record<string, string> = { agent: "抽取与三个岗位助手", jev: "Jev 降级时的大模型", ingest: "读取与编译" };
function AiCost({ data, set, p, volume, assumed }: { data: CeoData; set: Basis; p: CeoParams; volume: number; assumed: (k: string) => boolean }) {
  const yuan = (u: LlmUsage, keys = Object.keys(u)) => keys.reduce((y, k) => y + (u[k].input_tokens * p.llm_input_price + u[k].output_tokens * p.llm_output_price) / 1e6, 0);
  const ours = Object.keys(data.ai).filter((k) => k in HUAYAN_CALLERS);           // 模拟客户（sim）与普通 RAG 对照（baseline）不是化言的成本
  const calls = ours.reduce((n, k) => n + data.ai[k].calls, 0);
  const each = yuan(data.ai, ours) / data.cases.length;
  const v = p.monthly_inquiries * volume;
  const saved = savings(data.cases, set, p, v).total, cost = 12 * v * each;
  const priced = assumed("llm_input_price") || assumed("llm_output_price");
  return (
    <Group title="AI 成本与省下的人工，同一本账" foot={<>token 来自网关计量 <Src s="实测" />，按每百万 token 输入 {p.llm_input_price} 元、输出 {p.llm_output_price} 元折算{priced && <Src s="假设" />}；
      这一局的总费用 ÷ {data.cases.length} 件事得出每件；一年按每月件数 × 12 <Src s="推算" />。觉打分不调用大模型，不计费。</>}>
      <div className="grid grid-cols-4 gap-4 px-4 py-3.5 text-[12.5px]">
        <div><p className="text-ink-2">每件需求的模型费用</p><p className="num text-[20px] font-semibold">{calls ? `${each.toFixed(2)} 元` : "—"}</p>
          <p className="text-ink-2">{calls ? `这一局 ${calls} 次调用` : "这一局没有调用大模型（离线回放或规则模式）"}</p></div>
        <div><p className="text-ink-2">一年的模型费用</p><p className="num text-[20px] font-semibold">{money(cost)}</p></div>
        <div><p className="text-ink-2">一年省下的人工与试样</p><p className="num text-[20px] font-semibold" style={{ color: GAIN }}>{money(saved)}</p>
          <p className="text-ink-2">{saved > 0 && cost > 0 ? `模型费用约占 ${((cost / saved) * 100).toFixed(1)}%` : ""}</p></div>
        <div className="text-ink-2">
          {ours.map((k) => <p key={k}>{HUAYAN_CALLERS[k]}：{data.ai[k].calls} 次 · {cents(yuan(data.ai, [k]))}</p>)}
          {data.compile && <p>整批编译资料库（一次性）：{Object.values(data.compile).reduce((n, r) => n + r.calls, 0)} 次 · {cents(yuan(data.compile))}</p>}
        </div>
      </div>
    </Group>
  );
}
