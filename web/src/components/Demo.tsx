// V6-5.5 演示讲解栏：进入后替换左侧导航，中、右两栏仍是真实的四个子工作面。
// 每点一次「下一步」，服务端按 demo/story.yaml 先执行开场（客户来了、说出第一句）；要人做的动作（替客户回答、签字、接单）
// 切到对应工作面，由看的人亲手点呼吸高亮的按钮（或「替我做这一步」），做完讲解栏自动收尾，切到该看的工作面与对象。
// 讲解五段：发生了什么 / 过去怎么做 / 解放了谁的什么 / ↑ 降本增效 / ★ 体验与影响力；讲完可引导点需求轨迹的某个角色格（look）。
// 账本只放实测；估算卡的参数由企业自填，标「估算」。
// 三种运行方式同一份讲解：录制回放（真实模型的录制输出）、接入自己的模型（每一步真实调用，判断可能和剧本不同，如实标出）、本地离线。
// 「自己试」页签：用自己的话当客户、让研发的 Agent 改草稿，需要接入自己的模型。
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { RunMode, StoryGuide, StoryState } from "../types";
import { NO_GUIDE, publish } from "./Guide";
import { Close } from "./Icons";

type View = StoryState["view"];
type Tab = "day" | "route" | "try";
const GAIN = "#248a3d";
const FAME = "#5856d6";
const LOOK = "#0a6cdf";
const WORKBENCHES = [["customer", "客户"], ["sales", "业务员"], ["pm", "产品经理"], ["rd", "研发"]] as const;

export function DemoPanel({ onExit, onView, side }: {
  onExit: () => void;
  onView: (v: View, rebuilt: boolean) => Promise<void>;
  side: (el: HTMLElement | null) => void;
}) {
  const { fail, go, meta, version } = useApp();
  const [story, setStory] = useState<StoryState | null>(null);
  const [mode, setModeState] = useState<Tab>(() => (localStorage.getItem("huayan-demo-tab") as Tab | null) ?? "day");
  const setMode = (t: Tab) => { localStorage.setItem("huayan-demo-tab", t); setModeState(t); };
  const [running, setRunning] = useState<string | null>(null);
  const live = meta.mode.kind === "byok";
  // 等人操作时看要做的那个工作面，否则看这一步讲解对应的工作面
  const viewOf = (s: StoryState) => (s.begun && s.guide ? s.guide.view : s.view);
  // 进入（或刷新）时回到该看的工作面；「自己试」时留在看的人自己打开的地方
  useEffect(() => { api.story().then((s) => { setStory(s); const v = viewOf(s); if (v && mode !== "try") onView(v, false); }, fail); }, []);
  // 讲解栏指向工作面上的按钮：等人操作时指要点的按钮；讲完这一步指需求轨迹上该看的角色格（点过即熄）
  const g = story?.begun ? story.guide : null;
  const look = story && !story.begun && story.done ? story.steps[story.done - 1].look : undefined;
  useEffect(() => publish(g ? { who: g.who, target: g.target, arg: g.arg, customer: null } : look ? { ...NO_GUIDE, target: `route:${look.role}` } : NO_GUIDE),
            [g?.target, g?.who, g?.arg, look?.role, story?.done]);
  useEffect(() => () => publish(NO_GUIDE), []);
  // 看的人在工作面上做了一步：还有下一个动作就切过去指给他；都做完了就收尾，切到讲解
  useEffect(() => {
    if (!story?.begun || running) return;
    api.story().then((s) => {
      if (s.begun && !s.guide) return finish();
      if (s.guide?.view && guideKey(s.guide) !== guideKey(story.guide)) onView(s.guide.view, false);
      setStory(s);
    }, fail);
  }, [version]);
  if (!story) return null;

  const { steps, chapters, done } = story;
  const act = (label: string, p: Promise<StoryState>, rebuilt: boolean) => {
    setRunning(label);
    p.then(async (s) => { setStory(s); await onView(viewOf(s), rebuilt); }).catch(fail).finally(() => setRunning(null));
  };
  const goto = (i: number) => act(live ? `正在用你的模型补跑到第 ${i} 步……` : `正在从头执行到第 ${i} 步……`, api.storyGoto(i), true);
  const next = () => act(live ? "正在用你的模型真实执行……" : "正在执行……", api.storyBegin(), false);
  function finish() { act(live ? "正在用你的模型真实执行……" : "正在执行……", api.storyNext(), false); }
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
      <RunBadge m={meta.mode} offline={meta.status.gateway_mock} />
      <div className="flex rounded-[8px] bg-fill p-0.5 text-[13px]">
        {([["day", "一个上午"], ["route", "按路径看"], ["try", "自己试"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setMode(k)}
                  className={`h-7 flex-1 rounded-[6px] ${mode === k ? "bg-white font-semibold shadow-[0_0_0_.5px_rgba(0,0,0,.08),0_1px_2px_rgba(0,0,0,.08)]" : "text-ink-2"}`}>{label}</button>
        ))}
      </div>

      <Ledger />

      {mode === "try" ? <Try live={live} offline={meta.status.gateway_mock} /> : <>
      {story.last?.diverged && step && !story.begun && (
        <section className="rounded-[10px] px-3.5 py-3 text-[13px] leading-[21px] attn-edge">
          <p className="font-semibold text-attn-ink">真实运行和剧本不同</p>
          <p className="mt-0.5">{story.last.diverged}。</p>
          <p className="mt-1 text-ink-2">这是你的模型真实判断的结果。可以在右边的工作面接着操作（比如替客户回答觉的追问）再点「下一步」；也可以在目录里点这一章重看。下面的讲解按剧本写。</p>
        </section>
      )}
      {story.begun && upcoming ? (
        <section className="group flex flex-col gap-3 px-4 py-4">
          <p className="eyebrow">第 {done + 1} / {steps.length} 步 · {where(upcoming.chapter)}：{chapterOf(upcoming.chapter).title}</p>
          <h3 className="text-[16px] font-semibold leading-6">{upcoming.title}</h3>
          <GuideCard g={story.guide} />
          <p className="text-[12px] leading-[18px] text-ink-2">要点的按钮在右边工作面上呼吸高亮，做完讲解会自动接上。
            {meta.status.replay && "录制回放里请用「演示自动填入」的原文提交，改写过的内容不在录制里。"}</p>
        </section>
      ) : step ? (
        <section className="group flex flex-col gap-3 px-4 py-4">
          <p className="eyebrow">第 {done} / {steps.length} 步 · {where(step.chapter)}：{chapterOf(step.chapter).title}</p>
          <h3 className="text-[16px] font-semibold leading-6">{step.title}</h3>
          <Part label="发生了什么">{step.happened}</Part>
          {step.before && <Part label="过去怎么做" muted>{step.before}</Part>}
          {step.freed && <Part label="解放了谁的什么" strong>{step.freed}</Part>}
          {step.money && <Value mark="↑" label="降本增效" color={GAIN}>{step.money}</Value>}
          {step.fame && <Value mark="★" label="体验与影响力" color={FAME}>{step.fame}</Value>}
          {step.look && <Value mark="›" label="顺手看看" color={LOOK}>{step.look.text}</Value>}
        </section>
      ) : (
        <section className="group flex flex-col gap-2.5 px-4 py-4 text-[13.5px] leading-[22px]">
          <h3 className="text-[16px] font-semibold leading-6">一家企业的一个上午</h3>
          <p>左边讲解，右边是真实的工作面。每一步都<b>真的执行</b>：客户发言、觉提出决策、Agent 起草、人签字。轮到人做的事（替客户回答、签字、接单）由你在工作面上亲手点，要点的按钮会<b>呼吸高亮</b>。</p>
          <p className="text-ink-2">工作面顶部的<b className="text-ink">需求轨迹</b>四格都能点：切到那个角色，看他在这件事里能做什么、要做什么、正在做什么。</p>
          <p className="text-ink-2"><b className="text-ink">一个上午</b>：从头到尾连着看 6 个需求。<b className="text-ink">按路径看</b>：在目录里直接点 A / B / C / C′ / D 某一条。</p>
          <p className="text-[12px] text-ink-3">开始时会清空你这个浏览器里的演示进度，从 9:00 重新开始（其他人不受影响）。</p>
        </section>
      )}

      <div className="flex gap-2">
        {done > 1 && <button className="btn btn-plain !h-10 !rounded-[9px]" disabled={!!running} onClick={() => goto(done - 1)}>上一步</button>}
        {story.begun ? (
          <button className="btn btn-plain !h-10 min-w-0 flex-1 !rounded-[9px]" disabled={!!running} onClick={finish}>
            <span className="truncate">{running ?? "替我做这一步"}</span>
          </button>
        ) : upcoming ? (
          <button className="btn btn-primary !h-10 min-w-0 flex-1 !rounded-[9px] !text-[14px]" disabled={!!running}
                  onClick={() => (done ? next() : goto(1))}>
            <span className="truncate">{running ?? (done ? `下一步：${upcoming.title}` : "开始")}</span>
          </button>
        ) : (
          <button className="btn btn-plain !h-10 flex-1 !rounded-[9px]" disabled={!!running} onClick={() => goto(1)}>{running ?? "从头再看一遍"}</button>
        )}
      </div>
      {running && live && <p className="-mt-2 text-[12px] leading-[18px] text-ink-2">每一步约 5 秒到 1 分多钟；左上角的过程面板能看到每一次模型调用与 Agent 的每一步。</p>}
      {!running && !story.begun && story.last && story.last.calls > 0 && (
        <p className="-mt-2 text-[12px] leading-[18px] text-ink-2">
          {live ? `这一步调用你的模型 ${story.last.calls} 次 · ${story.last.tokens.toLocaleString()} token · 模型用时 ${story.last.seconds} 秒`
            : meta.status.replay ? `这一步有 ${story.last.calls} 次模型输出，来自录制（${meta.mode.llm_model}）` : `这一步调用模型 ${story.last.calls} 次`}</p>
      )}
      {done > 0 && !story.begun && <p className="-mt-2 text-[12px] leading-[18px] text-ink-3">也可以不按讲解，直接在右边的工作面上自己操作；讲解栏不锁步骤。</p>}

      {step?.chapter === "收尾" && <><Estimator /><Fame /></>}
      {step?.chapter === "落地" && <Landing />}

      {mode === "day" ? (
        <section>
          <p className="group-title">步骤目录 · 点任意一步跳过去</p>
          <div className="group py-1">
            {steps.map((s, i) => (
              <div key={i}>
                {(i === 0 || steps[i - 1].chapter !== s.chapter) && (
                  <p className="px-4 pb-0.5 pt-2 text-[11px] font-semibold tracking-[.04em] text-ink-3">
                    {where(s.chapter)} · {chapterOf(s.chapter).title}</p>
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
          <p className="group-foot">{live ? "接入你的模型时只补跑这一条和它依赖的路径（例如 C′ 先跑 C），不从头全跑；补跑也是真实调用。"
            : "前面的步骤会先在后台自动跑完再停在这一条的开头（例如 C′ 要先有 C 的判断），保证每条路径看到的都是真实状态。"}</p>
        </section>
      )}
      </>}

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

const where = (chapter: string) => (["开场", "收尾", "落地"].includes(chapter) ? chapter : `路径 ${chapter}`);
const guideKey = (g: StoryGuide | null) => (g ? `${g.target}|${g.who}|${g.view?.focus}` : "");

// 轮到看的人做的那一步：你现在是谁、点哪个按钮（与工作面上呼吸高亮的按钮一致）
function GuideCard({ g }: { g: StoryGuide | null }) {
  const L = useLabels();
  if (!g?.view) return (
    <div className="rounded-[9px] px-3 py-2.5 text-[13.5px] leading-[22px] attn-edge">
      这一步的前提在这次运行里没有出现（真实运行和剧本不同）。点「替我做这一步」看具体原因，或在目录里点这一章重看。</div>
  );
  const name = L.name(g.who!);
  const [role, todo] = ((): [string, string] => {
    switch (g.target) {
      case "say": return [`客户 ${name}`, `点对话框底部的「演示自动填入」，再点「发送」。客户这句说：「${g.arg}」`];
      case "quote": return [`客户 ${name}`, "客户想买了：点对话框下方的「我要报价」。"];
      case "decline": {
        const d = JSON.parse(g.arg!) as { product: string };
        return [`研发 ${name}`, `在「待你签字」里点「不立项：已有产品适用」，再点「演示自动填入」（选${L.product(d.product)}、填好判断依据），最后点「不立项：已有产品适用」签字。`];
      }
      case "scope": return [`产品经理 ${name}`, "在「签字：扩展适用范围」里点「演示自动填入」写好依据，再点「扩展适用范围」签字。"];
      case "merge": return [`产品经理 ${name}`, "在「签字：作为一个课题交研发」里点「演示自动填入」写好商业判断，再点「合并为一个课题」签字。"];
      default: return [`研发 ${name}`, "在「待你签字」里点「接单立项」。"];
    }
  })();
  return (
    <div className="rounded-[9px] px-3 py-2.5 attn-edge">
      <p className="text-[12px] font-semibold text-attn-ink">轮到你 · 你现在是{role}</p>
      <p className="mt-0.5 text-[13.5px] leading-[22px]">{todo}</p>
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
              {delta[x.label] > 0 ? <span className="anim-fade text-[11.5px] font-semibold" style={{ color: GAIN }}>
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
        <div className="mt-1 rounded-[9px] px-3 py-2.5 text-[13.5px] leading-[23px]" style={{ background: `${GAIN}12` }}>
          <p>每月少进研发约 <b>{Math.round(saved)}</b> 张单，释放研发前期工时约 <b>{Math.round(hours)}</b> 小时（约 <b>{(hours / 160).toFixed(1)}</b> 人的全职时间）</p>
          <p>折合约 <b style={{ color: GAIN }}>{yuan.toFixed(1)} 万元 / 年</b>{sales > 0 && <>；老产品扩范围新增销售约 <b style={{ color: GAIN }}>{sales} 万元 / 年</b></>}</p>
        </div>
        <p className="text-[11.5px] leading-[18px] text-ink-3">比例来自 6 个模拟需求的结构对照（见「评测」页岗位对照），默认参数只是示例，金额全部由上面自填的参数算出；需要试点验证。</p>
      </div>
    </section>
  );
}

const FAME_ITEMS = [
  ["行业需求语言", "「这类问题研发开工前必须知道什么」沉淀成功能化学上下游通用、可复用的需求描述。"],
  ["配方不出门，知识敢开放", "分层保密：客户只看说明书、用法与公开案例，机理与配方永不对外——所以敢把知识服务直接开给下游。"],
  ["专家经验有署名有回报", "每条转化知识记在本人名下，被引用就记分；研发、产品经理的判断成为看得见的贡献。"],
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
        <Value mark="↑" label="降本增效" color={GAIN}>不推翻已有 IT 投入；企业的 RAG 越强，化言越强。</Value>
        <p className="text-[11.5px] leading-[18px] text-ink-3">以上为接入路径与代码接缝，正式对接在试点阶段完成（见 README 第 11 节）。</p>
      </div>
    </section>
  );
}

// 运行方式：录制回放 / 你的模型真实运行 / 本地离线（降级如实标注）
function RunBadge({ m, offline }: { m: RunMode; offline: boolean }) {
  const { openMode } = useApp();
  if (m.kind === "byok") return <p className="-mt-2 text-[12px] text-ink-2"><span className="tag tag-accent mr-1.5">真实运行</span>{m.llm_model} · 每一步真实调用你的模型</p>;
  if (m.kind === "replay") return (
    <p className="-mt-2 flex items-center gap-1.5 text-[12px] text-ink-2"><span className="tag">录制回放</span>{m.llm_model} 的真实录制
      <button className="link !text-[12px]" onClick={openMode}>接入你的模型 →</button></p>
  );
  return <p className="-mt-2 text-[12px] text-ink-2"><span className={`tag ${offline ? "tag-warn" : ""}`}>{offline ? "离线规则" : "本地运行"}</span></p>;
}

// 自己试：讲解之外，用自己的话当客户、用一句话让研发的 Agent 改草稿；录制回放只能沿讲解走，要先接入自己的模型
function Try({ live, offline }: { live: boolean; offline: boolean }) {
  const { go, openMode } = useApp();
  const cards: [string, string, string, () => void][] = [
    ["用自己的话当客户", "客户工作面「我的需求」右侧点 ＋ →「用自己的话说」，像客户一样只描述现象，比如「布面发硬」「染完有白点」「颜色和打样不一样」。",
      "看觉追问了哪些条件（右侧逐项亮起）、最后为什么是当场推荐，还是带着原话直达研发。", () => go("customer", null, "customer:C01")],
    ["换一种说法说同一件事", "把「深一块浅一块」说成「一缸布颜色有深有浅，不匀」，或者用方言、错别字。",
      "看你的模型能不能认出是同一个现象，追问是否一样；每个条件都标着是从哪句原话里听出来的。", () => go("customer", null, "customer:C02")],
    ["让研发的 Agent 改草稿", "需求进研发后（讲解里的 C、D，或你自己提的），到研发工作面，在右下角「与 Agent 协作」里说一句：「第 2 条改成要求低泡」「根据客户原话补一条耐碱的约束」。",
      "Agent 借研发的权限起草，写在需求单对应的位置；生效要研发本人签字。", () => go("rd")],
  ];
  return (
    <>
      {!live && (
        <section className="rounded-[10px] px-3.5 py-3 text-[13px] leading-[21px] attn-edge">
          <p className="font-semibold">{offline ? "当前是离线规则运行" : "自己试需要接入你的模型"}</p>
          <p className="mt-0.5 text-ink-2">{offline ? "能试，但听懂原话用的是规则词表，Agent 不运行。"
            : "录制回放只能沿讲解一步步走；自由操作需要你自己的大模型（OpenAI 兼容接口），每一步真实调用。"}</p>
          {!offline && <button className="btn btn-primary mt-2.5" onClick={openMode}>接入你的模型</button>}
        </section>
      )}
      {cards.map(([title, how, look, open], i) => (
        <section key={title} className="group flex flex-col gap-2 px-4 py-3.5">
          <p className="flex items-center gap-2 text-[14px] font-semibold"><span className="flex h-5 w-5 items-center justify-center rounded-full bg-fill text-[11px]">{i + 1}</span>{title}</p>
          <p className="text-[13px] leading-[21px]">{how}</p>
          <Part label="看什么">{look}</Part>
          <button className="btn btn-plain self-start" onClick={open}>去工作面 →</button>
        </section>
      ))}
      <p className="text-[12px] leading-[18px] text-ink-3">左上角的过程面板能看到每一次模型调用与 Agent 的每一步工具调用；顶部账本照常实时计数。</p>
    </>
  );
}
