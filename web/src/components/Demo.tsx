// V6-5.5 演示讲解栏：进入后替换左侧导航，中、右两栏仍是真实的四个子工作面。
// 每点一次「下一步」，服务端按 demo/story.yaml 真的执行这一步（与浏览器里点按钮同一入口），再切到该看的工作面与对象。
// 讲解五段：发生了什么 / 过去怎么做 / 解放了谁的什么 / ↑ 降本增效 / ★ 体验与影响力。账本只放实测；估算卡的参数由企业自填，标「估算」。
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";
import type { StoryState } from "../types";
import { Close } from "./Icons";

type View = StoryState["view"];
const MONEY = "#248a3d";
const FAME = "#5856d6";
const WORKBENCHES = [["customer", "客户"], ["sales", "业务员"], ["pm", "产品经理"], ["rd", "研发"]] as const;

export function DemoPanel({ onExit, onView, side }: {
  onExit: () => void;
  onView: (v: View, rebuilt: boolean) => Promise<void>;
  side: (el: HTMLElement | null) => void;
}) {
  const { fail, go } = useApp();
  const [story, setStory] = useState<StoryState | null>(null);
  const [mode, setMode] = useState<"day" | "route">("day");
  const [running, setRunning] = useState<string | null>(null);
  // 进入（或刷新）时回到当前这一步该看的工作面
  useEffect(() => { api.story().then((s) => { setStory(s); if (s.view) onView(s.view, false); }, fail); }, []);
  if (!story) return null;

  const { steps, chapters, done } = story;
  const act = (label: string, p: Promise<StoryState>, rebuilt: boolean) => {
    setRunning(label);
    p.then(async (s) => { setStory(s); await onView(s.view, rebuilt); }).catch(fail).finally(() => setRunning(null));
  };
  const goto = (i: number) => act(`正在从头执行到第 ${i} 步……`, api.storyGoto(i), true);
  const next = () => act("正在执行……", api.storyNext(), false);
  const step = done ? steps[done - 1] : null;
  const upcoming = steps[done];
  const chapterOf = (id: string) => chapters.find((c) => c.id === id)!;
  const firstOf = (id: string) => steps.findIndex((s) => s.chapter === id);

  return (
    <div className="flex flex-col gap-4 px-4 pb-6 pt-3">
      <div className="flex items-center justify-between">
        <p className="text-[15px] font-semibold">演示讲解</p>
        <button className="btn btn-quiet !h-7 gap-1 !text-[12px]" onClick={onExit}><Close />退出讲解</button>
      </div>
      <div className="flex rounded-[8px] bg-fill p-0.5 text-[13px]">
        {([["day", "一个上午"], ["route", "按路径看"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setMode(k)}
                  className={`h-7 flex-1 rounded-[6px] ${mode === k ? "bg-white font-semibold shadow-[0_0_0_.5px_rgba(0,0,0,.08),0_1px_2px_rgba(0,0,0,.08)]" : "text-ink-2"}`}>{label}</button>
        ))}
      </div>

      <Ledger />

      {step ? (
        <section className="group flex flex-col gap-3 px-4 py-4">
          <p className="eyebrow">第 {done} / {steps.length} 步 · {step.chapter === "开场" || step.chapter === "收尾" ? step.chapter : `路径 ${step.chapter}`}：{chapterOf(step.chapter).title}</p>
          <h3 className="text-[16px] font-semibold leading-6">{step.title}</h3>
          <Part label="发生了什么">{step.happened}</Part>
          {step.before && <Part label="过去怎么做" muted>{step.before}</Part>}
          {step.freed && <Part label="解放了谁的什么" strong>{step.freed}</Part>}
          {step.money && <Value mark="↑" label="降本增效" color={MONEY}>{step.money}</Value>}
          {step.fame && <Value mark="★" label="体验与影响力" color={FAME}>{step.fame}</Value>}
        </section>
      ) : (
        <section className="group flex flex-col gap-2.5 px-4 py-4 text-[13.5px] leading-[22px]">
          <h3 className="text-[16px] font-semibold leading-6">一家企业的一个上午</h3>
          <p>左边讲解，右边是真实的工作面。每点一次按钮，系统都会<b>真的执行</b>这一步：客户发言、觉提出决策、Agent 起草、人签字——然后切到该看的人和那份需求。</p>
          <p className="text-ink-2"><b className="text-ink">一个上午</b>：从头到尾连着看 6 个需求。<b className="text-ink">按路径看</b>：在目录里直接点 A / B / C / C′ / D 某一条。</p>
          <p className="text-[12px] text-ink-3">开始时会清空你这个浏览器里的演示进度，从 9:00 重新开始（其他人不受影响）。</p>
        </section>
      )}

      <div className="flex gap-2">
        {done > 1 && <button className="btn btn-plain !h-10 !rounded-[9px]" disabled={!!running} onClick={() => goto(done - 1)}>上一步</button>}
        {upcoming ? (
          <button className="btn btn-primary !h-10 min-w-0 flex-1 !rounded-[9px] !text-[14px]" disabled={!!running}
                  onClick={() => (done ? next() : goto(1))}>
            <span className="truncate">{running ?? (done ? `下一步：${upcoming.title}` : "开始")}</span>
          </button>
        ) : (
          <button className="btn btn-plain !h-10 flex-1 !rounded-[9px]" disabled={!!running} onClick={() => goto(1)}>{running ?? "从头再看一遍"}</button>
        )}
      </div>
      {done > 0 && <p className="-mt-2 text-[12px] leading-[18px] text-ink-3">也可以不点按钮，直接在右边的工作面上自己操作；讲解栏不锁步骤。</p>}

      {step?.chapter === "收尾" && <><Estimator /><Fame /><Landing /></>}

      {mode === "day" ? (
        <section>
          <p className="group-title">步骤目录 · 点任意一步跳过去</p>
          <div className="group py-1">
            {steps.map((s, i) => (
              <div key={i}>
                {(i === 0 || steps[i - 1].chapter !== s.chapter) && (
                  <p className="px-4 pb-0.5 pt-2 text-[11px] font-semibold tracking-[.04em] text-ink-3">
                    {s.chapter === "开场" || s.chapter === "收尾" ? s.chapter : `路径 ${s.chapter}`} · {chapterOf(s.chapter).title}</p>
                )}
                <button disabled={!!running} onClick={() => goto(i + 1)}
                        className={`flex w-full items-start gap-2 px-4 py-1 text-left text-[13px] leading-5 hover:bg-black/[.03] ${i + 1 === done ? "font-semibold text-accent" : i < done ? "text-ink-2" : ""}`}>
                  <span className="w-3 shrink-0 text-[11px]">{i + 1 === done ? "●" : i < done ? "✓" : ""}</span>{s.title}
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section>
          <p className="group-title">按路径看 · 点哪条看哪条</p>
          <div className="flex flex-col gap-2">
            {chapters.filter((c) => c.id !== "开场").map((c) => {
              const on = step?.chapter === c.id;
              const n = steps.filter((s) => s.chapter === c.id).length;
              return (
                <button key={c.id} disabled={!!running} onClick={() => goto(firstOf(c.id) + 1)}
                        className={`group row-btn flex items-center gap-3 px-3.5 py-2.5 text-left ${on ? "!shadow-[0_0_0_1.5px_var(--color-accent)]" : ""}`}>
                  <span className={`flex h-7 w-9 shrink-0 items-center justify-center rounded-[7px] text-[13px] font-semibold ${on ? "bg-accent text-white" : "bg-fill"}`}>
                    {c.id === "收尾" ? "∑" : c.id}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-semibold leading-5">{c.title}</span>
                    <span className="text-[12px] text-ink-3">{n} 步</span>
                  </span>
                </button>
              );
            })}
          </div>
          <p className="group-foot">前面的步骤会先在后台自动跑完再停在这一条的开头（例如 C′ 要先有 C 的判断），保证每条路径看到的都是真实状态。</p>
        </section>
      )}

      <section>
        <p className="group-title">自己去工作面看看</p>
        <div className="flex flex-wrap gap-1.5">
          {WORKBENCHES.map(([page, label]) => <button key={page} className="chip" onClick={() => go(page)}>{label}</button>)}
        </div>
      </section>
      <details className="group px-1 py-1">
        <summary className="cursor-pointer px-3 py-1.5 text-[12.5px] text-ink-2">当前工作面的列表（会话、收件箱、需求单）</summary>
        <div ref={side} />
      </details>
    </div>
  );
}

function Part({ label, children, muted, strong }: { label: string; children: React.ReactNode; muted?: boolean; strong?: boolean }) {
  return (
    <div>
      <p className="text-[11.5px] font-semibold tracking-[.04em] text-ink-3">{label}</p>
      <p className={`text-[13.5px] leading-[22px] ${muted ? "text-ink-2" : ""} ${strong ? "font-semibold" : ""}`}>{children}</p>
    </div>
  );
}

function Value({ mark, label, color, children }: { mark: string; label: string; color: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-[9px] px-3 py-2" style={{ background: `${color}12` }}>
      <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white" style={{ background: color }}>{mark}</span>
      <p className="text-[13px] leading-[21px]"><b style={{ color }}>{label}　</b>{children}</p>
    </div>
  );
}

// 生产力账本：本会话此刻的事件日志实测计数（服务端算，界面不推算）；比上一次多出的数字标出来
function Ledger() {
  const items = useData(() => api.demoLedger(), []);
  const prev = useRef<Record<string, number>>({});
  const [delta, setDelta] = useState<Record<string, number>>({});
  useEffect(() => {
    if (!items) return;
    setDelta(Object.fromEntries(items.map((x) => [x.label, x.value - (prev.current[x.label] ?? x.value)])));
    prev.current = Object.fromEntries(items.map((x) => [x.label, x.value]));
  }, [items]);
  if (!items) return null;
  return (
    <section>
      <p className="group-title">生产力账本 · 实测</p>
      <div className="group grid grid-cols-3">
        {items.map((x, i) => (
          <div key={x.label} title={x.note} className={`relative px-3 py-2.5 ${i % 3 ? "border-l border-sep" : ""} ${i >= 3 ? "border-t border-sep" : ""}`}>
            <p className="flex items-baseline gap-1">
              <span className="text-[22px] font-semibold leading-7 tabular-nums">{x.value}</span>
              {x.base != null && <span className="text-[12px] text-ink-3">/ 传统 {x.base}</span>}
              {delta[x.label] > 0 ? <span className="anim-fade text-[11.5px] font-semibold" style={{ color: MONEY }}>
                +{delta[x.label]}</span> : null}
            </p>
            <p className="text-[11.5px] leading-4 text-ink-2">{x.label}</p>
          </div>
        ))}
      </div>
      <p className="group-foot">本浏览器这个上午真实发生的计数（悬停看口径）；「传统」按黑线流程定义，不是测量。</p>
    </section>
  );
}

// 估算卡：比例来自同一批模拟需求的结构对照，金额全部由企业自填参数算出；不写我方编的节约金额
function Estimator() {
  const report = useData(() => api.report<{ rd_tickets: { v5: number; v6: number } }>("v6_routes"), []);
  const [p, setP] = useState({ monthly: 30, hours: 4, cost: 200, scopes: 0, sales: 0 });
  const [ratio, setRatio] = useState<number | null>(null);
  if (!report) return null;
  const { v5, v6 } = report.rd_tickets;
  const r = ratio ?? Math.round((1 - v6 / v5) * 100);
  const saved = (p.monthly * r) / 100;
  const hours = saved * p.hours;
  const yuan = (hours * p.cost * 12) / 10000;
  const sales = p.scopes * p.sales;
  const field = (key: keyof typeof p, label: string, unit: string) => (
    <label className="flex items-center gap-2 text-[13px]">
      <span className="flex-1 text-ink-2">{label}</span>
      <input type="number" min={0} value={p[key]} onChange={(e) => setP({ ...p, [key]: Number(e.target.value) })}
             className="field !w-[76px] !px-2 !py-1 text-right tabular-nums" />
      <span className="w-9 text-[12px] text-ink-3">{unit}</span>
    </label>
  );
  return (
    <section>
      <p className="group-title flex items-center gap-2">放到贵司算一算 <span className="tag tag-warn">估算</span></p>
      <div className="group flex flex-col gap-2 px-4 py-3.5">
        {field("monthly", "每月进研发的需求单", "张")}
        {field("hours", "每张单研发前期处理（补问、澄清、评估）", "小时")}
        {field("cost", "研发小时成本", "元")}
        <label className="flex items-center gap-2 text-[13px]">
          <span className="flex-1 text-ink-2">少进研发的比例（同一批需求 v5 {v5} 张 → v6 {v6} 张）</span>
          <input type="number" min={0} max={100} value={r} onChange={(e) => setRatio(Number(e.target.value))}
                 className="field !w-[76px] !px-2 !py-1 text-right tabular-nums" />
          <span className="w-9 text-[12px] text-ink-3">%</span>
        </label>
        <div className="my-1 h-px bg-sep" />
        {field("scopes", "可选：每年扩适用范围次数", "次")}
        {field("sales", "可选：每扩一次带来的年销售额", "万元")}
        <div className="mt-1 rounded-[9px] px-3 py-2.5 text-[13.5px] leading-[23px]" style={{ background: `${MONEY}12` }}>
          <p>每月少进研发约 <b>{Math.round(saved)}</b> 张单，释放研发前期工时约 <b>{Math.round(hours)}</b> 小时（约 <b>{(hours / 160).toFixed(1)}</b> 人的全职时间）</p>
          <p>折合约 <b style={{ color: MONEY }}>{yuan.toFixed(1)} 万元 / 年</b>{sales > 0 && <>；老产品扩范围新增销售约 <b style={{ color: MONEY }}>{sales} 万元 / 年</b></>}</p>
        </div>
        <p className="text-[11.5px] leading-[18px] text-ink-3">比例来自 6 个模拟需求的结构对照（见「评测」页岗位对照），默认参数只是示例，金额全部由上面自填的参数算出；需要试点验证。</p>
      </div>
    </section>
  );
}

const FAME_ITEMS = [
  ["行业需求语言", "「这类问题研发开工前必须知道什么」沉淀成功能化学上下游通用的需求描述，化言是第一个把它做成标准的。"],
  ["配方不出门，知识敢开放", "分层保密：客户只看说明书、用法与公开案例，机理与配方永不对外——所以敢把知识服务直接开给下游。"],
  ["专家经验有署名有回报", "每条转化知识记在本人名下，被引用就记分；研发、产品经理的判断成了看得见的个人资产。"],
  ["嵌进现有协作，上下游都能接", "嵌入钉钉 / 飞书，不替换现有系统；下游客户、业务员、研发在各自熟悉的入口里协作。"],
];

function Fame() {
  return (
    <section>
      <p className="group-title">体验与影响力 · 上下游为什么愿意接入</p>
      <div className="group flex flex-col gap-2.5 px-4 py-3.5">
        {FAME_ITEMS.map(([title, text]) => (
          <div key={title} className="flex gap-2.5">
            <span className="mt-0.5 text-[13px]" style={{ color: FAME }}>★</span>
            <p className="text-[13px] leading-[21px]"><b>{title}</b>　{text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Landing() {
  return (
    <section>
      <p className="group-title">落地 · 接在已有系统上</p>
      <div className="group flex flex-col gap-2 px-4 py-3.5 text-[13px] leading-[21px]">
        <p><b>不重做 RAG。</b>企业已有的向量知识库接在唯一检索入口 <code className="text-[12px]">KnowledgeBase.search</code> 的排序一步后面；权限、审计、引用记分照常生效。</p>
        <p><b>试样结果回流。</b>ELN 里的试样结果经门面的试样录入回到需求单与知识库。</p>
        <p><b>嵌入钉钉 / 飞书。</b>四个工作面就是四个角色在现有协作工具里的入口。</p>
        <Value mark="↑" label="降本增效" color={MONEY}>不推翻已有 IT 投入；企业的 RAG 越强，化言越强。</Value>
        <p className="text-[11.5px] leading-[18px] text-ink-3">以上未实际对接，给出的是接入路径与代码接缝（与 README 第 6 节一致）。</p>
      </div>
    </section>
  );
}
