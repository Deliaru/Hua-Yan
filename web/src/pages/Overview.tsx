// 架构总览：分层转译的业务流程图（可逐步播放一条需求）、三处设计取舍、效率对照（数字取自 docs/reports/ 的真实运行）。
// 流程图里的示例话术是模拟数据，只说明用法；橙色菱形是「觉提出 → 人签字」的决策点。
import { useEffect, useState } from "react";
import { api } from "../api";
import { useData } from "../ctx";
import { Group, PageHead, ReplayNote } from "../components/ui";

const X = [250, 432, 614, 796, 978, 1160];
const Y = { 1: 164, 2: 296, 3: 428 } as const;
type Kind = "human" | "agent" | "store";
interface Node { id: string; col: number; lane: 1 | 2 | 3; title: string; sub: string; by: string; kind: Kind; step: number }

const NODES: Node[] = [
  { id: "talk", col: 0, lane: 1, title: "客户对话", sub: "只会描述宏观现象", by: "业务员直接面对客户", kind: "human", step: 0 },
  { id: "card", col: 1, lane: 1, title: "场景需求卡", sub: "每一格绑定客户原话", by: "实时抽取", kind: "agent", step: 1 },
  { id: "match", col: 2, lane: 1, title: "分级检索 + Jev", sub: "按权限检索、给匹配概率", by: "L1 知识", kind: "agent", step: 2 },
  { id: "rec", col: 3, lane: 1, title: "推荐卡", sub: "按客户画像决定披露", by: "业务员发给客户", kind: "human", step: 9 },
  { id: "kb", col: 5, lane: 1, title: "L1 知识库", sub: "新品说明书上架", by: "研发审定发布", kind: "store", step: 9 },
  { id: "case", col: 1, lane: 2, title: "历史案例 · L2 对照", sub: "说明书没写的用法", by: "归属到人", kind: "store", step: 3 },
  { id: "reuse", col: 2, lane: 2, title: "现成产品复用", sub: "先查，能复用就不立项", by: "产品经理 Agent", kind: "agent", step: 3 },
  { id: "l2", col: 3, lane: 2, title: "L2 转译", sub: "场景语言 → 产品需求", by: "产品经理 Agent 起草", kind: "agent", step: 4 },
  { id: "pack", col: 5, lane: 2, title: "反向包装", sub: "只用对外要点写说明书", by: "产品经理 Agent 起草", kind: "agent", step: 8 },
  { id: "ledger", col: 1, lane: 3, title: "转化知识 · 归属人", sub: "被引用即给归属人记分", by: "贡献账本", kind: "store", step: 5 },
  { id: "accept", col: 3, lane: 3, title: "研发接单", sub: "= 立项", by: "研发签字", kind: "human", step: 5 },
  { id: "l3", col: 4, lane: 3, title: "L3 转译", sub: "产品需求 → 化学语言", by: "研发 Agent 起草", kind: "agent", step: 6 },
  { id: "seal", col: 5, lane: 3, title: "试样 · 沉淀 · 封存", sub: "窗户纸只对 L3 可见", by: "研发审定", kind: "human", step: 7 },
];

// 边：style = flow 主线 / branch 支线 / data 知识引用 / back 回问 / wheel 回流
interface Edge { d: string; step: number; style: "flow" | "branch" | "data" | "back" | "wheel"; mark?: [number, number, string, "start" | "middle" | "end"] }
const EDGES: Edge[] = [
  { d: "M316 164H366", step: 1, style: "flow" },
  { d: "M400 134Q341 104 282 134", step: 1, style: "back", mark: [341, 119, "追问", "middle"] },
  { d: "M498 164H548", step: 2, style: "flow" },
  { d: "M680 164H730", step: 9, style: "flow" },
  { d: "M614 194V266", step: 3, style: "flow", mark: [614, 214, "升级", "start"] },
  { d: "M650 266C650 230 760 230 760 194", step: 99, style: "branch", mark: [705, 230, "审定", "end"] },
  { d: "M498 296H548", step: 3, style: "data" },
  { d: "M680 296H730", step: 4, style: "flow" },
  { d: "M796 326V398", step: 5, style: "flow", mark: [796, 344, "接单", "start"] },
  { d: "M730 428H498", step: 5, style: "data" },
  { d: "M862 428H912", step: 6, style: "flow" },
  { d: "M978 398V362H250V194", step: 6, style: "back", mark: [380, 362, "回问 · 研发需要知道", "start"] },
  { d: "M1044 428H1094", step: 7, style: "flow", mark: [1069, 428, "确认", "middle"] },
  { d: "M1160 398V326", step: 8, style: "flow", mark: [1160, 362, "放出", "end"] },
  { d: "M1160 266V194", step: 9, style: "flow", mark: [1160, 230, "发布", "end"] },
  { d: "M1160 134V122Q1160 112 1148 112H626Q614 112 614 122V134", step: 9, style: "wheel" },
];

const LANES = [
  { lane: 1, name: "场景语言", who: "业务员 · 客户", see: "看不到 L2 / L3 原文" },
  { lane: 2, name: "产品语言", who: "产品经理 Agent", see: "L3 知识只见归属" },
  { lane: 3, name: "化学语言", who: "研发", see: "封存项只本层可见" },
] as const;

// 播放一条需求（示例，模拟数据）
export const STEPS: { node: string; text: string; how: string }[] = [
  { node: "talk", text: "「染完以后，布面上深一块浅一块，怎么办？」", how: "客户只描述现象。今天这句话会被业务员按自己的理解转述，到研发手里已经走样。" },
  { node: "card", text: "面料：锦纶氨纶「锦纶氨纶混纺」· 设备：气流缸「我们是气流缸」", how: "觉判断缺面料、值得问，提示业务员趁客户还在就追问；每一格都绑定客户原话。" },
  { node: "match", text: "检索到 2 个候选产品，Jev：「都不合适」概率最高", how: "觉提出「是否转产品经理 Agent」，业务员的 Agent 起草升级说明，业务员签字。" },
  { node: "reuse", text: "已查 3 个历史案例：无现成产品", how: "产品经理 Agent 先查 L2 知识；能复用就由研发审定后直接转给业务员，不必立项。" },
  { node: "l2", text: "「需要在低浴比下仍能保持匀染效果的助剂」", how: "产品经理 Agent 把场景语言转成产品需求，每句标明依据了谁的历史案例。" },
  { node: "accept", text: "研发接单 = 立项", how: "接单是 L2 的生效点；被引用的历史案例给归属人记分。" },
  { node: "l3", text: "「对酸性染料有缓染作用、与染料竞争染座的组分；氨纶段亲和力低，需控制沾色」", how: "研发 Agent 起草、研发修改确认；觉发现缺染浴 pH，提出回问，业务员回头问客户，答复回填需求单。" },
  { node: "seal", text: "研发改过的转译沉淀为自己的知识；窗户纸封存，对外要点放出", how: "试样通过、业务员带回客户评价后，研发审定哪些封存、哪些放出。" },
  { node: "pack", text: "说明书只用产品需求与对外要点写成", how: "觉检查说明书是否命中封存项或 L3 术语；命中则研发 Agent 改写，产品经理 Agent 拿不到封存内容。" },
  { node: "kb", text: "研发审定发布，新品回到 L1 知识库", how: "下一位客户同样描述，业务员在 L1 直接命中新品，不再升级——这一轮系统又多会了一件事。" },
];

export function Overview() {
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-8 px-8 pb-16 pt-7">
      <PageHead title="架构总览"
                subtitle="化言把一条会失真的传话链，变成逐层转译、每句可回查、由觉推动、人来签字的协同流程。" />
      <ReplayNote />
      <FlowDiagram />
      <Innovations />
      <Efficiency />
    </div>
  );
}

// ── 流程图 ───────────────────────────────────────────────
function FlowDiagram() {
  const [step, setStep] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => {
      if (step === STEPS.length - 1) setPlaying(false);
      else setStep((s) => (s ?? -1) + 1);
    }, step === null ? 0 : 2800);
    return () => clearTimeout(t);
  }, [playing, step]);
  const shown = (s: number) => step === null || s <= step;
  const active = step === null ? null : STEPS[step].node;
  const jump = (id: string) => {
    const i = STEPS.findIndex((s) => s.node === id);
    if (i >= 0) { setPlaying(false); setStep(i); }
  };
  const cur = step === null ? null : STEPS[step];
  return (
    <section>
      <div className="group-title flex items-baseline justify-between">
        <span>业务流程 · 一条需求怎样走完三层</span>
        <span className="font-normal text-ink-3">示例话术为模拟数据</span>
      </div>
      <div className="group">
        <div className="overflow-x-auto"><svg viewBox="0 0 1250 504" className="block w-full min-w-[980px] select-none" role="img" aria-label="化言分层转译流程图">
          <defs>
            {([["gray", "rgba(60,60,67,.55)"], ["attn", "#e07a00"], ["wheel", "#5b7cfa"]] as const).map(([k, c]) => (
              <marker key={k} id={`ar-${k}`} viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 1 9 5 0 9z" fill={c} />
              </marker>
            ))}
            <linearGradient id="wheel" x1="1" x2="0"><stop offset="0" stopColor="#b25cf0" /><stop offset=".5" stopColor="#5b7cfa" /><stop offset="1" stopColor="#3fb8e8" /></linearGradient>
            <filter id="lift" x="-10%" y="-20%" width="120%" height="150%"><feDropShadow dx="0" dy="1" stdDeviation="1.4" floodOpacity=".08" /></filter>
          </defs>

          <JueBand />

          {LANES.map(({ lane, name, who, see }) => {
            const top = Y[lane] - 60;
            return (
              <g key={lane}>
                <rect x={16} y={top} width={1218} height={120} rx={14} fill={lane === 1 ? "#fbfbfc" : lane === 2 ? "#f8f8fa" : "#f5f5f8"} />
                <text x={36} y={top + 34} fontSize={20} fontWeight={600} fill="var(--color-ink)">L{lane}</text>
                <text x={36} y={top + 56} fontSize={13} fontWeight={600} fill="var(--color-ink)">{name}</text>
                <text x={36} y={top + 74} fontSize={11} fill="var(--color-ink-2)">{who}</text>
                <text x={36} y={top + 92} fontSize={11} fill="var(--color-ink-3)">{see}</text>
              </g>
            );
          })}

          {EDGES.map((e, i) => <EdgeView key={i} e={e} on={shown(e.step)} />)}
          {NODES.map((n) => <NodeView key={n.id} n={n} on={shown(n.step)} active={active === n.id} onClick={() => jump(n.id)} />)}
          <g opacity={shown(9) ? 1 : .2} className="transition-opacity duration-500">
            <rect x={808} y={102} width={158} height={20} rx={10} fill="#fff" stroke="url(#wheel)" strokeWidth={1} />
            <text x={887} y={116} fontSize={11} fontWeight={600} textAnchor="middle" fill="#4a5fd6">下一位客户 L1 直接命中</text>
          </g>
        </svg></div>

        <div className="flex items-start gap-5 border-t border-sep px-5 py-4">
          <div className="flex shrink-0 items-center gap-1.5">
            <button className="btn btn-primary w-[112px]" onClick={() => {
              if (playing) setPlaying(false);
              else { if (step === STEPS.length - 1) setStep(null); setPlaying(true); }
            }}>{playing ? "暂停" : step === null ? "播放一条需求" : step === STEPS.length - 1 ? "重新播放" : "继续"}</button>
            <button className="btn btn-plain !px-2.5" disabled={!step} onClick={() => { setPlaying(false); setStep((s) => Math.max(0, (s ?? 0) - 1)); }}>‹</button>
            <button className="btn btn-plain !px-2.5" disabled={step === STEPS.length - 1}
                    onClick={() => { setPlaying(false); setStep((s) => (s ?? -1) + 1); }}>›</button>
          </div>
          {cur ? (
            <div key={step} className="anim-fade min-w-0 flex-1">
              <p className="flex items-center gap-2 text-[12px] text-ink-2">
                <span className="num font-semibold text-accent">{step! + 1} / {STEPS.length}</span>
                <span>{NODES.find((n) => n.id === cur.node)!.title} · L{NODES.find((n) => n.id === cur.node)!.lane}</span>
              </p>
              <p className="mt-0.5 text-[16px] font-semibold leading-6">{cur.text}</p>
              <p className="mt-0.5 text-[13px] leading-5 text-ink-2">{cur.how}</p>
            </div>
          ) : (
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-5 gap-y-1.5 pt-1 text-[12px] text-ink-2">
              <Legend kind="human" label="人签字生效" />
              <Legend kind="agent" label="Agent 起草" />
              <Legend kind="store" label="知识（带归属）" />
              <span className="flex items-center gap-1.5"><Diamond />觉提出、人签字的决策点</span>
              <span className="flex items-center gap-1.5"><i className="h-0 w-5 border-t-[1.5px] border-dashed border-[#e07a00]" />回到客户补信息</span>
              <span className="flex items-center gap-1.5"><i className="h-[2px] w-5 rounded bg-gradient-to-r from-[#3fb8e8] via-[#5b7cfa] to-[#b25cf0]" />新品回流 L1</span>
              <span className="text-ink-3">点任一节点跳到那一步</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function JueBand() {
  const chips = ["状态改变", "觉提出决策", "主人准备 · Agent 起草", "签字人签字 · 按钮"];
  const widths = chips.map((c) => 26 + c.length * 12.5);
  const gap = 34;
  const start = 330;
  const xs = widths.map((_, i) => start + widths.slice(0, i).reduce((a, b) => a + b + gap, 0));
  const mid = (i: number) => xs[i] + widths[i] / 2;
  return (
    <g>
      <rect x={16} y={14} width={1218} height={72} rx={14} fill="var(--color-attn-bg)" stroke="rgba(176,80,10,.2)" strokeWidth={.75} />
      <text x={36} y={44} fontSize={15} fontWeight={600} fill="var(--color-attn-ink)">觉 · 决策点发现器</text>
      <text x={36} y={64} fontSize={11} fill="var(--color-ink-2)">零大模型调用 · 规则或 Jue-K 打分</text>
      {chips.map((c, i) => (
        <g key={c}>
          <rect x={xs[i]} y={26} width={widths[i]} height={26} rx={13} fill="#fff" stroke="rgba(176,80,10,.28)" strokeWidth={.75} />
          <text x={mid(i)} y={43} fontSize={12} textAnchor="middle" fill="var(--color-ink)" fontWeight={i === 1 || i === 3 ? 600 : 400}>{c}</text>
          {i < chips.length - 1 && <path d={`M${xs[i] + widths[i] + 4} 39H${xs[i + 1] - 5}`} stroke="#e07a00" strokeWidth={1.2} markerEnd="url(#ar-attn)" />}
        </g>
      ))}
      <path d={`M${mid(3)} 52V70H${mid(0)}V56`} fill="none" stroke="#e07a00" strokeWidth={1.2} strokeDasharray="3 3" markerEnd="url(#ar-attn)" />
      <text x={(mid(0) + mid(3)) / 2} y={67} fontSize={10.5} textAnchor="middle" fill="var(--color-attn-ink)" style={{ paintOrder: "stroke" }}
            stroke="var(--color-attn-bg)" strokeWidth={6}>觉再看一遍</text>
      <text x={1214} y={44} fontSize={11.5} textAnchor="end" fill="var(--color-ink-2)">流程不写死在代码里：</text>
      <text x={1214} y={62} fontSize={11.5} textAnchor="end" fill="var(--color-ink-2)">每一步都是觉提出、人签字</text>
    </g>
  );
}

function EdgeView({ e, on }: { e: Edge; on: boolean }) {
  const stroke = e.style === "back" ? "#e07a00" : e.style === "wheel" ? "url(#wheel)" : e.style === "data" ? "rgba(60,60,67,.35)" : "rgba(60,60,67,.55)";
  const marker = e.style === "back" ? "ar-attn" : e.style === "wheel" ? "ar-wheel" : "ar-gray";
  const dash = e.style === "back" ? "4 3" : e.style === "data" ? "1.5 3" : e.style === "branch" ? "5 3" : undefined;
  return (
    <g opacity={on ? 1 : .18} className="transition-opacity duration-500">
      <path d={e.d} fill="none" stroke={stroke} strokeWidth={e.style === "wheel" ? 2 : 1.3} strokeDasharray={dash}
            strokeLinecap="round" markerEnd={`url(#${marker})`} />
      {e.mark && (() => {
        const [x, y, label, anchor] = e.mark;
        const tx = anchor === "start" ? x + 10 : anchor === "end" ? x - 10 : x;
        const ty = anchor === "middle" ? y - 10 : y + 4;
        return (
          <g>
            <rect x={x - 4.5} y={y - 4.5} width={9} height={9} transform={`rotate(45 ${x} ${y})`} fill="var(--color-attn)" stroke="#fff" strokeWidth={1.5} />
            <text x={tx} y={ty} fontSize={11.5} fontWeight={600} textAnchor={anchor} fill="var(--color-attn-ink)"
                  stroke="#fafafb" strokeWidth={4} style={{ paintOrder: "stroke" }}>{label}</text>
          </g>
        );
      })()}
    </g>
  );
}

function NodeView({ n, on, active, onClick }: { n: Node; on: boolean; active: boolean; onClick: () => void }) {
  const x = X[n.col], y = Y[n.lane];
  const clickable = STEPS.some((s) => s.node === n.id);
  return (
    <g transform={`translate(${x} ${y})`} opacity={on ? 1 : .25} onClick={clickable ? onClick : undefined}
       className={`transition-opacity duration-500 ${clickable ? "cursor-pointer" : ""}`}>
      {active && <rect x={-72} y={-36} width={144} height={72} rx={14} fill="rgba(10,108,223,.1)" className="anim-fade" />}
      <rect x={-66} y={-30} width={132} height={60} rx={10} filter={n.kind === "store" ? undefined : "url(#lift)"}
            fill={n.kind === "store" ? "#eceef3" : "#fff"}
            stroke={active ? "var(--color-accent)" : n.kind === "agent" ? "rgba(60,60,67,.42)" : n.kind === "human" ? "rgba(0,0,0,.16)" : "none"}
            strokeWidth={active ? 1.8 : 1} strokeDasharray={n.kind === "agent" && !active ? "4 3" : undefined} />
      <text y={-9} fontSize={13} fontWeight={600} textAnchor="middle" fill="var(--color-ink)">{n.title}</text>
      <text y={7} fontSize={11} textAnchor="middle" fill="var(--color-ink-2)">{n.sub}</text>
      <text y={22} fontSize={10.5} textAnchor="middle" fill={n.kind === "human" ? "var(--color-accent)" : "var(--color-ink-3)"}>{n.by}</text>
    </g>
  );
}

function Legend({ kind, label }: { kind: Kind; label: string }) {
  const cls = kind === "human" ? "border border-[rgba(0,0,0,.2)] bg-white" : kind === "agent" ? "border border-dashed border-[rgba(60,60,67,.5)] bg-white" : "bg-[#eceef3]";
  return <span className="flex items-center gap-1.5"><i className={`h-3 w-5 rounded-[4px] ${cls}`} />{label}</span>;
}

function Diamond() {
  return <i className="inline-block h-2 w-2 rotate-45 bg-attn" />;
}

// ── 三处取舍 ─────────────────────────────────────────────
function Innovations() {
  const items = [
    ["分层转译，而不是一次翻译", "一次性翻译变不出客户没说的信息。化言让每一层只用本层能看的知识，把需求逐层换成下一层能直接用的语言；每一句都能回到客户原话和知识归属人。", "L1 → L2 → L3 → 反向包装"],
    ["觉推动流程，人签字生效", "下一步该谁决定什么，写在决策目录里，不写死在代码里。觉在每次状态改变后判断此刻是否需要有人决策（模型打分给概率，规则打分到点即提出），Agent 起草，人按按钮签字。", "发现环节零大模型调用"],
    ["权责对等，知识愿意沉淀", "知识被引用即给归属人记分；研发改过的转译沉淀为自己的知识；上层知识对下层只显示归属不显示原文，解密由研发本人审批。", "安全靠结构，不靠提示词"],
  ];
  return (
    <section>
      <div className="group-title">三处设计取舍</div>
      <div className="grid grid-cols-3 gap-4">
        {items.map(([t, d, k], i) => (
          <div key={t} className="group flex flex-col px-5 py-4">
            <p className="num text-[12px] font-semibold text-ink-3">0{i + 1}</p>
            <p className="mt-1 text-[16px] font-semibold leading-6">{t}</p>
            <p className="mt-1.5 flex-1 text-[13px] leading-[21px] text-ink-2">{d}</p>
            <p className="mt-3 text-[12px] font-semibold text-accent">{k}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── 效率对照（真实运行）───────────────────────────────────
type Num = number | null;
interface Distortion { n_cards: number; placeholder_seeds: boolean; metrics: Record<string, Record<string, Num>> }
interface Detect { hits: number; positives: number; false_alarms: number; mean_lead_hours: Num; jue_llm_calls: number }
interface Week { detection: Record<string, Detect>; consequences: Record<string, { escalations_after: number; l1_hits_after: number }> }

const GROUPS: [string, string][] = [["G1 业务员转述", "业务员转述（现状）"], ["G2 一次性翻译", "一次性翻译 Agent"], ["G3 化言", "化言"]];
const METRICS: [string, string, boolean][] = [
  ["completeness", "关键信息完整率", true],
  ["returned", "研发需退回重问的比例", false],
  ["mistranslation", "错译率", false],
  ["traceable", "可回查到客户原话", true],
];

function Efficiency() {
  const d = useData(() => api.report<Distortion>("distortion").catch(() => null), []);
  const w = useData(() => api.report<Week>("week").catch(() => null), []);
  return (
    <section>
      <div className="group-title flex items-baseline justify-between">
        <span>效率提升 · 真实运行的对照</span>
        <span className="font-normal text-ink-3">详见「评测」</span>
      </div>
      {d ? (
        <div className="grid grid-cols-4 gap-4">
          {METRICS.map(([k, label, up]) => <MetricCard key={k} d={d} k={k} label={label} up={up} />)}
        </div>
      ) : <div className="group px-5 py-4 text-[13px] text-ink-3">失真对照报告尚未生成（docs/reports/distortion/）。</div>}
      {w && <WeekCard w={w} />}
      {d && (
        <p className="group-foot">
          {d.n_cards} 张程序生成的需求卡 + 模拟客户，同一批卡上三组方案对照{d.placeholder_seeds ? "；种子为占位数据" : ""}。定时发现取自一个模拟业务周。全部为模拟数据。
        </p>
      )}
    </section>
  );
}

function MetricCard({ d, k, label, up }: { d: Distortion; k: string; label: string; up: boolean }) {
  const vals = GROUPS.map(([g]) => d.metrics[g]?.[k] ?? null);
  const ours = vals[2];
  const bi = vals[0] != null ? 0 : 1;
  const base = vals[bi];
  return (
    <div className="group px-5 py-4">
      <p className="text-[12px] text-ink-2">{label}<span className="ml-1 text-ink-3">{up ? "越高越好" : "越低越好"}</span></p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="num text-[28px] font-semibold leading-8 tracking-[-0.02em]">{ours == null ? "—" : `${Math.round(ours * 100)}%`}</span>
        {ours != null && base != null && base !== ours && (
          <span className="num text-[12px] font-semibold text-accent">
            {up ? "↑" : "↓"} {Math.abs(Math.round((ours - base) * 100))} 个百分点
            <span className="ml-1 font-normal text-ink-3">较{bi ? "一次性翻译" : "现状"}</span>
          </span>
        )}
      </p>
      <div className="mt-3 flex flex-col gap-2">
        {GROUPS.map(([g, name], i) => {
          const v = vals[i];
          return (
            <div key={g}>
              <div className="flex justify-between text-[11.5px]">
                <span className={i === 2 ? "font-semibold" : "text-ink-2"}>{name}</span>
                <span className="num text-ink-2">{v == null ? "不适用" : `${Math.round(v * 100)}%`}</span>
              </div>
              <div className="mt-1 h-[6px] overflow-hidden rounded-full bg-fill">
                <div className={`h-full rounded-full ${i === 2 ? "bg-accent" : "bg-[rgba(60,60,67,.3)]"}`} style={{ width: `${(v ?? 0) * 100}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WeekCard({ w }: { w: Week }) {
  const jk = w.detection.jue_k ?? w.detection.jue_proto;
  const rule = w.detection.rule_alert;
  const handled = w.consequences["jue_k/handle"];
  const ignored = w.consequences["jue_k/ignore"];
  if (!jk || !rule) return null;
  const cell = (label: string, a: string, b: string) => (
    <div className="px-5 py-4">
      <p className="text-[12px] text-ink-2">{label}</p>
      <p className="num mt-1 text-[22px] font-semibold leading-7">{a}</p>
      <p className="num text-[12px] text-ink-3">规则告警：{b}</p>
    </div>
  );
  return (
    <div className="group mt-4 grid grid-cols-[1.3fr_1fr_1fr_1fr_1.3fr] divide-x divide-[var(--color-sep)]">
      <div className="px-5 py-4">
        <p className="text-[12px] text-ink-2">定时发现 · 模拟业务周</p>
        <p className="mt-1 text-[15px] font-semibold leading-6">觉比规则告警更早、更准地发现同类需求、知识冲突与套问</p>
      </div>
      {cell("命中注入问题", `${jk.hits} / ${jk.positives}`, `${rule.hits} / ${rule.positives}`)}
      {cell("误报", `${jk.false_alarms}`, `${rule.false_alarms}`)}
      {cell("平均提前", `${jk.mean_lead_hours ?? "—"} 小时`, `${rule.mean_lead_hours ?? "—"} 小时`)}
      <div className="px-5 py-4">
        <p className="text-[12px] text-ink-2">处置之后</p>
        {handled && ignored ? (
          <>
            <p className="num mt-1 text-[22px] font-semibold leading-7">同类升级 {ignored.escalations_after} → {handled.escalations_after}</p>
            <p className="num text-[12px] text-ink-3">L1 直接命中 {handled.l1_hits_after} 次 · 觉调用大模型 {jk.jue_llm_calls} 次</p>
          </>
        ) : <p className="mt-1 text-[13px] text-ink-3">—</p>}
      </div>
    </div>
  );
}
