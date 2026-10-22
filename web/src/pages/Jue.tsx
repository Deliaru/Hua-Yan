// 觉视图（REPLAN 3.2 第 6 条、3.6）：一条需求线程上觉的历次判断。先一句结论（判断多少次、提出几次、调用大模型几次），
// 主体是「决策日志」：每次提出一张卡，写清觉为什么提出、打了多少分、交给谁准备、谁签了字；
// 追问是提示类（不建问题、不需签字），同一时刻的追问提示合成一张卡。原来的泳道概率图收进「概率曲线」。
// 泳道图：Jue-K / OneJev 打分画曲线与虚线阈值，规则打分画阶跃并标「规则 · 到点」，不标概率。泳道与点由接口按查看者裁剪，界面不再过滤。
import { useState } from "react";
import { api } from "../api";
import { ACTION, REQ_STATUS, hhmm, isModel, pct, useApp, useData, useLabels } from "../ctx";
import type { JueTimeline, TimelineNode, TimelinePoint } from "../types";
import { Popover } from "../components/Controls";
import { ChevronDown } from "../components/Icons";
import { Disclosure, EmptyState, Group, LayerChip, PageHead } from "../components/ui";

// 业务员选自己的会话，研发选需求单（需求单线程含其全部会话）；按时间顺序，默认第一条（演示主线所在的线程）
export function JuePage() {
  const { me, role } = useApp();
  const L = useLabels();
  const sessions = useData(() => (role === "sales" ? api.sessions() : Promise.resolve([])), [role]) ?? [];
  const reqs = useData(() => (role === "rd" ? api.requirements(me) : Promise.resolve([])), [role, me]) ?? [];
  const targets = role === "sales"
    ? sessions.filter((s) => s.sales_id === me)
      .map((s) => ({ id: s.id, label: `${s.customer_id ? L.name(s.customer_id) : "样例客户"} · ${s.phenomenon ? L.phen(s.phenomenon) : "尚未识别现象"}` }))
    : reqs.map((r) => ({ id: r.id, label: `${L.phen(r.phenomenon)} · ${REQ_STATUS[r.status]}` }));
  return <Jue targets={targets} />;
}

function Jue({ targets }: { targets: { id: string; label: string }[] }) {
  const { me } = useApp();
  const [chosen, choose] = useState<string | null>(null);
  const target = targets.find((t) => t.id === chosen) ?? targets[0] ?? null;
  const tl = useData(() => (target ? api.timeline(target.id, me) : Promise.resolve(null)), [target?.id, me]);
  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-6 px-8 pb-24 pt-7">
      <PageHead title="觉视图"
                subtitle="觉是本地小模型：看着整条需求链，只在「此刻需要有人决定」时提出，交给主人准备、签字人签字；流程就这样一步步推进。"
                aside={target && (
                  <Popover align="right" trigger={(toggle) => (
                    <button onClick={toggle} className="btn btn-plain">{target.label}<ChevronDown /></button>
                  )}>
                    {(close) => targets.map((t) => (
                      <button key={t.id} className="menu-item" onClick={() => { choose(t.id); close(); }}>
                        <span className="w-3">{t.id === target.id ? "✓" : ""}</span>{t.label}
                      </button>
                    ))}
                  </Popover>
                )} />
      {!target ? <EmptyState title="还没有需求线程" text="觉视图跟着演示进度走：到「沉浸工作面」按导览走几步，这里就会出现觉的每一次判断；想先看完整的例子，看「演示工作面」。" />
        : tl && <Timeline tl={tl} />}
    </div>
  );
}

const W = 1000, LEFT = 150, RIGHT = 24, LANE = 76, TOP = 28;

// 觉在什么情况下提出（按决策目录的前置条件写成人话；具体打分见卡片右上角）
const WHY: Record<string, string> = {
  ask_slot: "客户只说了现象，这项信息会改变候选产品或是研发必问，客户还没说",
  escalate_need: "现象已明确，L1 匹配倾向「现有产品都不合适」，业务员还没升级",
  reuse_product: "刚升级：先查有没有说明书没写、但案例里用过的现成产品",
  accept_requirement: "产品需求（L2）已起草，等研发接单；接单即立项",
  opportunity: "同一主题的需求反复升级、又没有产品可用：可能是一个值得合并立项的机会",
  ask_back: "化学语言（L3）转译中，这项信息的不同取值会改变引用的知识，客户还没说",
  confirm_translation: "化学要点（L3）已起草，等研发确认",
  contribution: "研发改过、且没被已有知识覆盖的条目，值得沉淀为研发本人的知识",
  market_eval: "试样通过，等业务员带回客户的评价",
  seal_points: "客户评价通过，决定哪些封存、哪些对外放出",
  release: "说明书已按放出的要点包装好，等研发审定发布",
  distortion: "转译遗漏约束或缺少原话依据",
  seal_leak: "对外说明命中了封存项或 L3 术语",
  knowledge_conflict: "某产品在某个条件下试样反复失败，说明书可能要更新",
  trial_risk: "转译已确认、即将试样，客户没说清的条件可能让试样失败",
  stale_capability: "研发签出的适用判断被用过之后，结果开始在某个条件上集中失败",
  leak_risk: "某位业务员集中打听同一产品的原理、替客户反复申请解密",
  mechanism_followup: "客户拿到推荐后追问产品内部（配方、机理、成分）",
};

// 决策所在的层（追问、升级、客户评价在 L1；现成产品、接单、机会汇聚在 L2；其余在 L3）
const LAYER: Record<string, 1 | 2 | 3> = {
  ask_slot: 1, escalate_need: 1, market_eval: 1, reuse_product: 2, accept_requirement: 2, opportunity: 2,
  ask_back: 3, confirm_translation: 3, contribution: 3, seal_points: 3, release: 3,
};

// 日志的一条：一个被提出的问题，或同一时刻的一组追问提示
type Item = { at: string; node?: TimelineNode; hints?: TimelinePoint[] };

function Timeline({ tl }: { tl: JueTimeline }) {
  const hints = tl.points.filter((p) => p.raised && p.family === "ask_slot");
  const items: Item[] = [
    ...tl.nodes.map((n) => ({ at: n.created_at, node: n })),
    ...[...new Set(hints.map((p) => p.at))].map((at) => ({ at, hints: hints.filter((p) => p.at === at) })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  return (
    <>
      <div className="flex items-end justify-between gap-8">
        <h2 className="max-w-[640px] text-[22px] font-semibold leading-[32px] tracking-[-0.01em]">
          觉判断 {tl.n_judgments} 次，只在 {items.length} 个时刻提出，人签字 {tl.n_signatures} 次；{tl.n_llm_calls ? `觉调用大模型 ${tl.n_llm_calls} 次` : "觉没有调用大模型"}
        </h2>
        <div className="shrink-0 text-right">
          <p className="num text-[32px] font-semibold leading-10 tracking-[-0.02em]">{items.length} / {tl.n_judgments}</p>
          <p className="text-[12px] text-ink-2">提出 / 判断 · 其余时刻不打扰</p>
        </div>
      </div>
      <section>
        <div className="group-title">决策日志 · 按提出时间</div>
        {items.length ? (
          <ol className="relative flex flex-col gap-3 pl-[76px] before:absolute before:bottom-3 before:left-[63px] before:top-3 before:w-px before:bg-sep">
            {items.map((it) => it.node
              ? <Entry key={it.node.question_id} n={it.node} point={tl.points.find((p) => p.family === it.node!.family && p.raised && p.at === it.node!.created_at)} />
              : <Hint key={it.at} at={it.at} ps={it.hints!} />)}
          </ol>
        ) : <div className="group"><div className="row text-[13px] text-ink-2">觉还没有在这条线程上提出决策。</div></div>}
      </section>
      <div className="px-1">
        <Disclosure label="概率曲线：觉的每一次判断（每个决策一条泳道）"><Chart tl={tl} /></Disclosure>
      </div>
    </>
  );
}

function Head({ family, at, score }: { family: string; at: string; score: React.ReactNode }) {
  const L = useLabels();
  return (
    <>
      <span className="num absolute -left-[76px] top-3 w-[48px] text-right text-[12px] text-ink-3">{hhmm(at)}</span>
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[14px] font-semibold">{LAYER[family] && <LayerChip layer={LAYER[family]} />}{L.family(family)}</p>
        <span className="shrink-0 text-[12px]">{score}</span>
      </div>
      <p className="mt-0.5 text-[12.5px] leading-[19px] text-ink-2">{WHY[family] ?? ""}</p>
    </>
  );
}

// 追问提示：觉在这一刻认为该问的信息与概率；提示类，问不问由业务员定
function Hint({ at, ps }: { at: string; ps: TimelinePoint[] }) {
  const L = useLabels();
  return (
    <li className="relative">
      <span className="absolute -left-[17px] top-[15px] h-[9px] w-[9px] rounded-full bg-ink-3 ring-4 ring-bg" />
      <div className="group px-4 py-3">
        <Head family="ask_slot" at={at} score={<span className="text-ink-3">阈值 {pct(ps[0].threshold)}</span>} />
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px]">
          {ps.map((p) => (
            <span key={p.object_id} className="tag">{L.slot(p.object_id.split("/").pop()!)}<span className="num ml-1 font-semibold">{pct(p.p_need!)}</span></span>
          ))}
          <span className="text-ink-3">提示业务员，问不问由人定，无需签字</span>
        </p>
      </div>
    </li>
  );
}

function Entry({ n, point }: { n: TimelineNode; point?: TimelinePoint }) {
  const L = useLabels();
  const state = n.resolved_at ? "done" : n.prepared_at ? "ready" : "preparing";
  // 主人直接回答（如产品经理 Agent 查无现成产品）时没有「准备完成」这一步
  const steps: [string, string | null, boolean][] = [
    ["提出", hhmm(n.created_at), true],
    ...(n.resolved_at && !n.prepared_at ? [] : [[`${L.name(n.owner_id)} 准备`, n.prepared_at && hhmm(n.prepared_at), !!n.prepared_at] as [string, string | null, boolean]]),
    [n.signer_id ? `${L.name(n.resolved_at ? n.by : n.signer_id)} ${n.resolved_at ? ACTION[n.action ?? ""] ?? "已处置" : "签字"}` : "提示类，无需签字",
     n.resolved_at && hhmm(n.resolved_at), !!n.resolved_at],
  ];
  return (
    <li className="relative">
      <span className={`absolute -left-[17px] top-[15px] h-[9px] w-[9px] rounded-full ring-4 ring-bg ${state === "done" ? "bg-ink-3" : "bg-attn"}`} />
      <div className={`group px-4 py-3 ${state === "done" ? "" : "attn-edge"}`}>
        <Head family={n.family} at={n.created_at} score={point && isModel(point.scored_by) && point.p_need != null
          ? <span className="num font-semibold text-ink">{L.scorer(point.scored_by)} {pct(point.p_need)} <span className="font-normal text-ink-3">· 阈值 {pct(point.threshold)}</span></span>
          : <span className="text-ink-3">规则 · 到点</span>} />
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px]">
          {steps.map(([label, at, on], i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <span className="text-ink-3">→</span>}
              <span className={`tag ${on ? (i === steps.length - 1 ? "!text-ink" : "") : "!bg-transparent !font-normal text-ink-3 ring-1 ring-sep"}`}>
                {label}{at && <span className="num ml-1 font-normal opacity-70">{at}</span>}
              </span>
            </span>
          ))}
        </p>
      </div>
    </li>
  );
}

function Chart({ tl }: { tl: JueTimeline }) {
  const L = useLabels();
  const [sel, setSel] = useState<TimelineNode | null>(null);
  const lanes = [...new Set([...tl.points.map((p) => p.family), ...tl.nodes.map((n) => n.family)])];
  const isos = [...tl.points.map((p) => p.at), ...tl.nodes.flatMap((n) => [n.created_at, n.prepared_at, n.resolved_at])]
    .filter((t): t is string => !!t);
  const times = isos.map((t) => Date.parse(t));
  const t0 = Math.min(...times), t1 = Math.max(...times);
  const x = (iso: string) => LEFT + ((Date.parse(iso) - t0) / Math.max(t1 - t0, 1)) * (W - LEFT - RIGHT);
  const H = TOP + lanes.length * LANE + 8;
  // 刻度：每个出现过的业务时刻一条（时间按接口给的时区显示）
  const ticks = [...new Map(isos.map((t) => [Date.parse(t), t])).values()];
  return (
    <>
      <Group foot="黑线是觉每次判断给出的概率（规则打分画成到点即升的阶跃），橙色虚线是阈值，橙点 = 这一次判断提出了问题；下方横条是问题的全过程：○ 提出 · ◆ 准备完成 · ■ 签字。点横条看详情。">
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label="觉的判断时间线">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={TOP - 6} y2={H - 8} stroke="rgba(60,60,67,.08)" />
              <text x={x(t)} y={16} textAnchor="middle" fontSize={11} fill="rgba(60,60,67,.6)">{hhmm(t)}</text>
            </g>
          ))}
          {lanes.map((fam, i) => (
            <Lane key={fam} y={TOP + i * LANE} family={fam} label={L.family(fam)} x={x}
                  points={tl.points.filter((p) => p.family === fam)}
                  nodes={tl.nodes.filter((n) => n.family === fam)} sel={sel} onSel={setSel} />
          ))}
        </svg>
      </Group>
      {sel && <NodeDetail n={sel} />}
    </>
  );
}

function Lane({ y, family, label, x, points, nodes, sel, onSel }: {
  y: number; family: string; label: string; x: (iso: string) => number; points: TimelinePoint[]; nodes: TimelineNode[];
  sel: TimelineNode | null; onSel: (n: TimelineNode) => void;
}) {
  const L = useLabels();
  const h = LANE - 30;                   // 曲线区高度
  const top = y + 8;
  const py = (p: number) => top + (1 - p) * h;
  const objects = [...new Set(points.map((p) => p.object_id))];
  const model = points.some((p) => isModel(p.scored_by));
  const threshold = points[0]?.threshold;
  return (
    <g>
      <line x1={0} x2={W} y1={y + LANE - 4} y2={y + LANE - 4} stroke="rgba(60,60,67,.13)" />
      <text x={0} y={top + 12} fontSize={13} fontWeight={600} fill="#1d1d1f">{label}</text>
      <text x={0} y={top + 29} fontSize={11} fill="rgba(60,60,67,.6)">
        {model ? `${L.scorer(points.find((p) => isModel(p.scored_by))!.scored_by)} 打分` : points.length ? "规则 · 到点" : ""}
      </text>
      {model && threshold != null && (
        <>
          <line x1={LEFT} x2={W - RIGHT} y1={py(threshold)} y2={py(threshold)} stroke="#ff9500" strokeDasharray="4 4" strokeWidth={1} />
          <text x={W - RIGHT} y={py(threshold) - 3} textAnchor="end" fontSize={10} fill="#c93400">阈值 {pct(threshold)}</text>
        </>
      )}
      {objects.map((o) => {
        const ps = points.filter((p) => p.object_id === o).sort((a, b) => a.at.localeCompare(b.at));
        return isModel(ps[0].scored_by) ? <Curve key={o} ps={ps} x={x} py={py} /> : <Step key={o} ps={ps} x={x} py={py} />;
      })}
      {nodes.map((n) => {
        const ny = y + LANE - 14;
        const on = sel?.question_id === n.question_id;
        const end = n.resolved_at ?? n.prepared_at ?? n.created_at;
        return (
          <g key={n.question_id} onClick={() => onSel(n)} className="cursor-pointer">
            <line x1={x(n.created_at)} x2={x(end)} y1={ny} y2={ny} stroke={on ? "#0071e3" : "rgba(60,60,67,.45)"} strokeWidth={on ? 3 : 2} />
            <circle cx={x(n.created_at)} cy={ny} r={5} fill="#fff" stroke="#c93400" strokeWidth={1.6} />
            {n.prepared_at && <rect x={x(n.prepared_at) - 4} y={ny - 4} width={8} height={8} transform={`rotate(45 ${x(n.prepared_at)} ${ny})`} fill="#ff9500" />}
            {n.resolved_at && <rect x={x(n.resolved_at) - 4.5} y={ny - 4.5} width={9} height={9} rx={1.5} fill={on ? "#0071e3" : "#1d1d1f"} />}
            <rect x={x(n.created_at) - 6} y={ny - 8} width={Math.max(x(end) - x(n.created_at), 0) + 12} height={16} fill="transparent" />
          </g>
        );
      })}
    </g>
  );
}

// 模型打分：曲线（前置条件不成立的 null 断开，不当成 0）
function Curve({ ps, x, py }: { ps: TimelinePoint[]; x: (iso: string) => number; py: (p: number) => number }) {
  const segs: TimelinePoint[][] = [[]];
  ps.forEach((p) => (p.p_need == null ? segs.push([]) : segs[segs.length - 1].push(p)));
  return (
    <g>
      {segs.filter((s) => s.length).map((s, i) => (
        <polyline key={i} fill="none" stroke="#1d1d1f" strokeWidth={1.6}
                  points={s.map((p) => `${x(p.at)},${py(p.p_need!)}`).join(" ")} />
      ))}
      {ps.filter((p) => p.p_need != null).map((p, i) => (
        <g key={i}>
          <circle cx={x(p.at)} cy={py(p.p_need!)} r={p.raised ? 4.5 : 3} fill={p.raised ? "#ff9500" : "#1d1d1f"} />
          <text x={x(p.at) + 6} y={py(p.p_need!) - 4} fontSize={10} fill="rgba(60,60,67,.6)">{pct(p.p_need!)}</text>
        </g>
      ))}
    </g>
  );
}

// 规则打分：阶跃，到点即升，不标概率
function Step({ ps, x, py }: { ps: TimelinePoint[]; x: (iso: string) => number; py: (p: number) => number }) {
  const on = (p: TimelinePoint) => (p.p_need != null && p.p_need >= p.threshold ? 1 : 0);
  let d = "";
  ps.forEach((p, i) => {
    d += i === 0 ? `M${x(p.at)},${py(on(p))}` : `H${x(p.at)}V${py(on(p))}`;
  });
  return (
    <g>
      <path d={d} fill="none" stroke="#1d1d1f" strokeWidth={1.6} />
      {ps.filter((p) => p.raised).map((p, i) => <circle key={i} cx={x(p.at)} cy={py(1)} r={4.5} fill="#ff9500" />)}
    </g>
  );
}

function NodeDetail({ n }: { n: TimelineNode }) {
  const L = useLabels();
  const rows: [string, string][] = [
    ["决策", L.family(n.family)],
    ["主人（准备）", L.name(n.owner_id)],
    ["签字人", n.signer_id ? L.name(n.signer_id) : "提示类，无需签字"],
    ["提出", hhmm(n.created_at)],
    ["准备完成", n.prepared_at ? hhmm(n.prepared_at) : "准备中"],
    ["处置", n.resolved_at ? `${hhmm(n.resolved_at)} · ${L.name(n.by)} ${ACTION[n.action ?? ""] ?? ""}` : "待签"],
  ];
  return (
    <Group title="节点">
      {rows.map(([k, v]) => (
        <div key={k} className="row"><span className="w-28 shrink-0 text-[13px] text-ink-2">{k}</span><span className="text-[14px]">{v}</span></div>
      ))}
    </Group>
  );
}
