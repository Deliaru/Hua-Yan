// 架构总览的两张图（REPLAN-v6 0′.1、0′.5、V6-4）：
// ① 因果链：需求说不清 → 返工 / 岗位交叉 / 重复 → 研发产能被占 → 长期创新受损；化言的每个机制挂在它切断的那一环上，点了跳到工作面证据点。
// ② 工作流程：上为传统流程（黑线逐道穿过），下为化言（红线，按需求性质分流的 A–D 与 C′），人实心、Agent / 觉虚线，点节点跳到对应子工作面。
// 纯 SVG 手写，不引新库。
import { useApp } from "../ctx";

const INK = "var(--color-ink)", INK2 = "var(--color-ink-2)", INK3 = "var(--color-ink-3)";
const RED = "#d93a2b", RED_BG = "#fdeeec";

interface Box { x: number; y: number; w: number; h: number; title: string; sub: string[]; tone?: "loss" | "root" | "end" }
interface Tag { x: number; y: number; label: string; page: string; focusNote: string }

const BOXES: Box[] = [
  { x: 20, y: 150, w: 200, h: 92, title: "需求在源头没说清", sub: ["客户只会说现象", "必问条件没人负责问全"], tone: "root" },
  { x: 268, y: 150, w: 196, h: 92, title: "逐手转述，层层失真", sub: ["业务员 → 产品经理 → 研发", "每转一手丢一部分、变一部分"] },
  { x: 520, y: 24, w: 250, h: 92, title: "① 信息不全的需求进研发", sub: ["开发目标偏差 → 试样不达标", "→ 返工（研发最大的损耗点）"], tone: "loss" },
  { x: 520, y: 150, w: 250, h: 92, title: "② 研发回头补问、澄清、纠偏", sub: ["跨岗反复对接 → 岗位职责交叉", "这是现象，不是根因"] },
  { x: 520, y: 276, w: 250, h: 92, title: "③ 每次判断留在个人脑子里", sub: ["同类问题下次重来", "短平快需求重复进研发"] },
  { x: 826, y: 150, w: 170, h: 92, title: "研发产能被占满", sub: ["短期返工与重复工作"] },
  { x: 1036, y: 150, w: 152, h: 92, title: "中长期课题被挤压", sub: ["企业长期创新", "能力受损"], tone: "end" },
];
const ARROWS = ["M220 196H262", "M464 196C494 196 490 70 514 70", "M464 196H514", "M464 196C494 196 490 322 514 322",
  "M770 70C800 70 796 196 820 196", "M770 196H820", "M770 322C800 322 796 196 820 196", "M996 196H1030"];

// 化言切断的环节：标签挂在对应框下方，点了跳到工作面证据点
const TAGS: Tag[] = [
  { x: 120, y: 262, label: "觉追问必问条件", page: "customer", focusNote: "E1" },
  { x: 366, y: 262, label: "带原话的分层转译", page: "layers", focusNote: "" },
  { x: 594, y: 136, label: "开工门槛", page: "rd", focusNote: "E2" },
  { x: 700, y: 136, label: "回问", page: "rd", focusNote: "" },
  { x: 645, y: 262, label: "退回归产品经理纠偏", page: "pm", focusNote: "" },
  { x: 584, y: 388, label: "C′ 扩适用范围", page: "pm", focusNote: "E4" },
  { x: 706, y: 388, label: "D 汇成课题", page: "pm", focusNote: "E5" },
  { x: 911, y: 262, label: "研发的时间卡", page: "rd", focusNote: "E6" },
];

export function CausalChain() {
  const { go } = useApp();
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <h2 className="text-[26px] font-semibold leading-[36px] tracking-[-0.01em]">研发没时间做中长期课题，根子在需求不明确</h2>
        <p className="max-w-[900px] text-[15px] leading-[25px] text-ink-2">
          基于功能化学一线业务需求交流：「需求不明确，产品开发了不达标一直返工，才没有精力做中长期课题。」岗位职责交叉是这条链的结果，不是原因。
          化言不是把这条链搬到线上，而是在研发开工前把需求说清楚，并让组织记住每一次判断。
        </p>
      </div>
      <div className="group">
        <div className="overflow-x-auto"><svg viewBox="0 0 1210 420" className="block w-full min-w-[980px] select-none" role="img" aria-label="需求不明确到长期创新受损的因果链，以及化言切断的环节">
          <defs>
            <marker id="ch-ar" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 1 9 5 0 9z" fill="rgba(60,60,67,.55)" />
            </marker>
          </defs>
          {ARROWS.map((d) => <path key={d} d={d} fill="none" stroke="rgba(60,60,67,.45)" strokeWidth={1.3} markerEnd="url(#ch-ar)" />)}
          {BOXES.map((b) => (
            <g key={b.title}>
              <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={12}
                    fill={b.tone === "loss" ? RED_BG : b.tone === "end" ? "#f1f1f4" : "#fff"}
                    stroke={b.tone === "loss" ? "rgba(217,58,43,.45)" : "rgba(0,0,0,.14)"} strokeWidth={1} />
              <text x={b.x + 16} y={b.y + 30} fontSize={14.5} fontWeight={600} fill={b.tone === "loss" ? RED : INK}>{b.title}</text>
              {b.sub.map((t, i) => <text key={t} x={b.x + 16} y={b.y + 54 + i * 18} fontSize={12} fill={INK2}>{t}</text>)}
            </g>
          ))}
          {TAGS.map((t) => {
            const w = 22 + t.label.length * 12.4;
            return (
              <g key={t.label} className="cursor-pointer" onClick={() => go(t.page)}>
                <title>{`点击查看：${t.focusNote ? `工作面证据点 ${t.focusNote}` : "对应页面"}`}</title>
                <rect x={t.x - w / 2} y={t.y - 13} width={w} height={26} rx={13} fill="#fff" stroke={RED} strokeWidth={1.2} />
                <text x={t.x} y={t.y + 4.5} fontSize={12} fontWeight={600} textAnchor="middle" fill={RED}>{t.label}</text>
              </g>
            );
          })}
          <text x={20} y={30} fontSize={12} fill={INK3}>红色标签 = 化言在这一环切断，点击跳到工作面里的证据</text>
          <g>
            <rect x={826} y={290} width={362} height={78} rx={12} fill="var(--color-attn-bg)" stroke="rgba(176,80,10,.25)" strokeWidth={.8} />
            <text x={844} y={318} fontSize={14} fontWeight={600} fill="var(--color-attn-ink)">觉 = 研发注意力的分配层</text>
            <text x={844} y={340} fontSize={12} fill={INK2}>只有说清楚的、真正新的需求才占用研发；</text>
            <text x={844} y={358} fontSize={12} fill={INK2}>研发每判断一次，组织就学会一次。</text>
          </g>
        </svg></div>
      </div>
    </section>
  );
}

// ── 工作流程：传统黑线 vs 化言红线 ─────────────────────────
const LANES = ["客户", "业务员", "产品经理", "研发"];
const LANE_Y = (i: number) => 34 + i * 62;
type Kind = "human" | "auto";
interface N { x: number; lane: number; label: string; kind: Kind; page?: string; w?: number }

const OLD: N[] = [
  { x: 200, lane: 0, label: "描述现象", kind: "human" },
  { x: 345, lane: 1, label: "记录、转述", kind: "human" },
  { x: 490, lane: 2, label: "再转述", kind: "human" },
  { x: 635, lane: 3, label: "开发 · 试样", kind: "human" },
  { x: 780, lane: 2, label: "评价", kind: "human" },
  { x: 925, lane: 1, label: "开单", kind: "human" },
  { x: 1070, lane: 0, label: "拿到产品", kind: "human" },
];

// 化言：A–D 四个分区 + C′ 回流
const ZONES = [
  { x: 150, label: "A 常规问题", note: "客户自助解决" },
  { x: 410, label: "B 商务诉求", note: "回到业务员" },
  { x: 670, label: "C 新需求 · C′", note: "直达研发，判一次组织记住" },
  { x: 950, label: "D 重复短平快", note: "汇成一个课题" },
];
const NEW: N[] = [
  { x: 205, lane: 0, label: "说现象", kind: "human", page: "customer" },
  { x: 330, lane: 0, label: "觉追问 · 推荐", kind: "auto", page: "customer", w: 112 },
  { x: 465, lane: 0, label: "要报价", kind: "human", page: "customer" },
  { x: 465, lane: 1, label: "报价 · 开单", kind: "human", page: "sales" },
  { x: 700, lane: 0, label: "说现象", kind: "human", page: "customer" },
  { x: 700, lane: 2, label: "Agent 转译 L2", kind: "auto", page: "pm", w: 112 },
  { x: 700, lane: 3, label: "门槛已齐 · 接单", kind: "human", page: "rd", w: 116 },
  { x: 840, lane: 2, label: "签扩适用范围", kind: "human", page: "pm", w: 108 },
  { x: 990, lane: 0, label: "客户甲", kind: "human", page: "customer", w: 64 },
  { x: 1070, lane: 0, label: "客户乙", kind: "human", page: "customer", w: 64 },
  { x: 1030, lane: 2, label: "签机会 + 商业判断", kind: "human", page: "pm", w: 128 },
  { x: 1030, lane: 3, label: "一张合并单", kind: "human", page: "rd", w: 100 },
];
const at = (n: N) => [n.x, LANE_Y(n.lane)] as const;

function Lanes() {
  return (
    <>
      {LANES.map((l, i) => (
        <g key={l}>
          <rect x={8} y={LANE_Y(i) - 28} width={1194} height={56} rx={10} fill={i % 2 ? "#f7f7f9" : "#fbfbfc"} />
          <text x={24} y={LANE_Y(i) + 5} fontSize={13} fontWeight={600} fill={INK}>{l}</text>
        </g>
      ))}
    </>
  );
}

function Caption({ title, sub, top }: { title: string; sub: string; top?: boolean }) {
  return (
    <p className={`px-4 pt-3 text-[12.5px] text-ink-2 ${top ? "border-t border-sep" : ""}`}>
      <span className={`mr-2 font-semibold ${top ? "text-danger" : "text-ink"}`}>{title}</span>{sub}</p>
  );
}

function NodeBox({ n, color }: { n: N; color: string }) {
  const { go } = useApp();
  const [x, y] = at(n);
  const w = n.w ?? 92;
  return (
    <g className={n.page ? "cursor-pointer" : ""} onClick={n.page ? () => go(n.page!) : undefined}>
      {n.page && <title>点击切到对应子工作面</title>}
      <rect x={x - w / 2} y={y - 15} width={w} height={30} rx={8}
            fill={n.kind === "human" ? "#fff" : "rgba(255,255,255,.7)"} stroke={color}
            strokeWidth={n.kind === "human" ? 1.4 : 1.1} strokeDasharray={n.kind === "auto" ? "4 3" : undefined} />
      {n.kind === "human" && <circle cx={x - w / 2 + 11} cy={y} r={3.5} fill={color} />}
      <text x={x + (n.kind === "human" ? 5 : 0)} y={y + 4.5} fontSize={12} fontWeight={600} textAnchor="middle" fill={INK}>{n.label}</text>
    </g>
  );
}

export function Workflow() {
  const oldPath = OLD.map(at).map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join("");
  return (
    <section className="flex flex-col gap-3">
      <div className="group-title flex items-baseline justify-between">
        <span>工作流程 · 同一批需求，两种走法</span>
        <span className="font-normal text-ink-3">实心圆点 = 人处理；虚线框 = Agent / 觉代办；点节点切到对应子工作面</span>
      </div>
      <div className="group">
        <Caption title="传统流程（黑线）" sub="每张单都按岗位顺序逐道穿过，每转一手丢一部分；信息不全就回头补问、返工" />
        <div className="overflow-x-auto"><svg viewBox="0 0 1210 280" className="block w-full min-w-[980px] select-none" role="img" aria-label="传统流程">
          <defs>
            <marker id="wf-k" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 1 9 5 0 9z" fill="#1c1c1e" /></marker>
          </defs>
          <Lanes />
          <path d={oldPath} fill="none" stroke="#1c1c1e" strokeWidth={1.6} />
          <path d="M600 222C500 268 350 262 343 112" fill="none" stroke="#1c1c1e" strokeWidth={1.2} strokeDasharray="4 3" markerEnd="url(#wf-k)" />
          <text x={470} y={262} fontSize={11.5} textAnchor="middle" fill={INK} stroke="#f7f7f9" strokeWidth={5} style={{ paintOrder: "stroke" }}>信息不全：回头补问 → 返工</text>
          {OLD.map((x) => <NodeBox key={x.label + x.x} n={x} color="#1c1c1e" />)}
        </svg></div>
        <Caption title="化言（红线）" sub="觉按需求性质分流：只有说清楚的、真正新的需求才占用研发；研发判一次，组织记住" top />
        <div className="overflow-x-auto"><svg viewBox="0 0 1210 305" className="block w-full min-w-[980px] select-none" role="img" aria-label="化言工作流程">
          <defs>
            <marker id="wf-r2" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 1 9 5 0 9z" fill={RED} /></marker>
          </defs>
          <Lanes />
          {ZONES.map((z, i) => (
            <g key={z.label}>
              {i > 0 && <path d={`M${z.x} 8V258`} stroke="rgba(60,60,67,.15)" strokeDasharray="2 4" />}
              <text x={z.x + 12} y={282} fontSize={12.5} fontWeight={600} fill={RED}>{z.label}</text>
              <text x={z.x + 12} y={298} fontSize={11.5} fill={INK2}>{z.note}</text>
            </g>
          ))}
          <g fill="none" stroke={RED} strokeWidth={1.6} markerEnd="url(#wf-r2)">
            <path d="M251 34H268" />
            <path d="M465 49V80" />
            <path d="M700 49V139" /><path d="M700 181V203" />
            <path d="M758 220C800 220 840 210 840 185" strokeDasharray="5 3" />
            <path d="M840 151C840 90 760 50 735 40" strokeDasharray="5 3" />
            <path d="M990 49C990 110 1010 130 1020 140" /><path d="M1070 49C1070 110 1050 130 1040 140" />
            <path d="M1030 181V203" />
          </g>
          <text x={845} y={110} fontSize={11} fill={RED} stroke="#fbfbfc" strokeWidth={4} style={{ paintOrder: "stroke" }}>C′ 下次同类需求自助解决</text>
          {NEW.map((x, i) => <NodeBox key={i} n={x} color={RED} />)}
        </svg></div>
      </div>
    </section>
  );
}
