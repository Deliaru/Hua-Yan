// 驾驶舱：化言和产业组织的流程图，从左到右：客户 → 化言 → 各岗位 → 说明书与组织能力，再回到客户与化言。
// 光点按业务流程演示里的事件逐个走、循环播放（开场时这一局还没跑，用演示脚本里的事件顺序）。
import { api } from "../api";
import { useEffect, useState } from "react";
import { useApp, useData } from "../ctx";
import { usePlay } from "../components/Play";
import { Headline } from "./Ceo";

const CAPS: [string, string][] = [
  ["Jue-K 本地决策模型", "觉的发现不调大模型"],
  ["Jev 概率核对", "推荐与依据重排"],
  ["L0–L3 分层知识", "配方永不降层"],
  ["证据指纹复核", "来源一改能力即停"],
  ["原话保真抽取", "未知与否定不丢"],
  ["角色 Agent Loop", "原子工具 · 只起草"],
  ["条件完整才复用", "对不上照样回研发"],
];


export function Home() {
  const { me, version } = useApp();
  const s = usePlay();
  const data = useData(() => api.playSettle().catch(() => null), [me, version]);
  const passed = s ? s.done.length : 0;
  const total = s ? s.levels.length : 0;
  const stats: [string, string][] = [
    ["这一局走过的业务与关卡", total ? `${passed} / ${total}` : "—"],
    ["客户需求", data ? `${data.cases.length} 件` : "—"],
    ["直接复用了研发的判断", data ? `${data.cases.filter((c) => c.reused).length} 件` : "—"],
    ["客户当场拿到答复（自助或复用）", data ? `${data.cases.filter((c) => c.path === "自助解决" || c.reused).length} 件` : "—"],
    ["条件不符改道回研发", data ? `${data.cases.filter((c) => c.rerouted).length} 件` : "—"],
  ];
  return (
    <div className="home min-h-[calc(100vh-52px)] pb-16">
      <div className="mx-auto max-w-[1280px] px-8 pt-8">
        <OrgFlow />
        <div className="mt-6 text-center">
          <p className="text-[34px] font-bold tracking-wide text-[#eaf0fb]">用 AI <span className="text-[#3fd0ff]">重构产业</span></p>
          <p className="mt-2 text-[20px] font-semibold text-[#eaf0fb]">从<span className="text-[#3fd0ff]">岗位智能</span>迈向<span className="text-[#3fd0ff]">组织智能</span></p>
          <p className="mx-auto mt-3 max-w-[900px] text-[14px] leading-7 text-[rgba(222,231,247,.6)]">面向产业的组织智能运行架构：以组织级 Agent Harness，重构企业的决策、协作与能力积累。</p>
        </div>
        <div className="mt-7 grid grid-cols-3 gap-4">
          {DIFF.map(([vs, head, body]) => (
            <div key={vs} className="rounded-[14px] border border-[rgba(63,208,255,.25)] bg-[rgba(63,208,255,.05)] px-5 py-4">
              <p className="text-[12px] font-semibold tracking-wider text-[rgba(63,208,255,.8)]">对比 {vs}</p>
              <p className="mt-1.5 text-[18px] font-bold leading-7 text-[#eaf0fb]">{head}</p>
              <p className="mt-2 text-[13px] leading-6 text-[rgba(222,231,247,.65)]">{body}</p>
            </div>
          ))}
        </div>
        <p className="mt-5 text-center text-[16px] font-semibold text-[#eaf0fb]">企业已有的 Agent，都能接进化言：<span className="text-[#3fd0ff]">觉</span>给它们派活，<span className="text-[#3fd0ff]">契</span>管它们能用什么，<span className="text-[#3fd0ff]">人</span>来签字。</p>
        <p className="mt-2 text-center text-[13px] text-[rgba(222,231,247,.5)]">第一个现场：传化功能化学「市场 — 产品 — 研发」</p>
        <div className="mt-8 grid grid-cols-5 gap-3">
          {stats.map(([k, v]) => (
            <div key={k} className="rounded-[12px] border border-[rgba(255,255,255,.1)] bg-[rgba(255,255,255,.04)] px-4 py-3">
              <p className="num text-[24px] font-semibold text-[#eaf0fb]">{v}</p>
              <p className="text-[12px] text-[rgba(222,231,247,.6)]">{k}</p>
            </div>
          ))}
        </div>
        {data && <div className="mt-4">
          <Headline data={data} set="given" p={data.params.given} volume={1} tag="模拟" assumed={(k) => data.params.given.assumed.includes(k)} />
        </div>}
        <div className="mt-8 grid grid-cols-7 gap-2 border-t border-[rgba(255,255,255,.1)] pt-5">
          {CAPS.map(([t, sub], i) => (
            <div key={t} className="px-1">
              <p className="text-[10.5px] font-semibold tracking-[.12em] text-[#3fd0ff]">0{i + 1}</p>
              <p className="mt-0.5 text-[14px] font-semibold text-[#eaf0fb]">{t}</p>
              <p className="text-[12px] text-[rgba(222,231,247,.55)]">{sub}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- 流程图 ----------
type Edge = "c-h" | "h-c" | "h-s" | "s-h" | "h-p" | "p-h" | "h-r" | "r-h" | "p-sheet" | "r-cap" | "cap-h" | "sheet-c";
const PATH: Record<Edge, string> = {
  "c-h": "M 170 215 L 318 215", "h-c": "M 318 250 L 170 250",
  "h-s": "M 542 175 C 640 175, 650 95, 735 95", "s-h": "M 735 112 C 660 112, 640 192, 542 192",
  "h-p": "M 542 222 L 735 222", "p-h": "M 735 240 L 542 240",
  "h-r": "M 542 265 C 640 265, 650 355, 735 355", "r-h": "M 735 372 C 660 372, 640 282, 542 282",
  "p-sheet": "M 885 222 C 960 222, 990 150, 1060 150", "r-cap": "M 885 365 C 960 365, 990 330, 1060 330",
  "cap-h": "M 1150 372 C 1150 450, 470 455, 432 386", "sheet-c": "M 1150 118 C 1150 30, 105 30, 105 186",
};
const LABEL: Partial<Record<Edge, [number, number, string]>> = {
  "cap-h": [790, 440, "下一单直接复用"], "sheet-c": [630, 46, "说明书更新到公开层，客户自己就能查到"],
  "c-h": [244, 205, "原话"], "h-c": [244, 268, "答复"], "h-p": [640, 214, "轮到你的事"], "r-cap": [975, 372, "签字授予"],
};
const DIFF = [
  ["岗位 AI 助手", "岗位 AI 让一个人更快，化言把整件事做成",
   "化言盯的是整件事：问题及时发现，需求问清楚，研发的判断用得上，结果回到下一单。"],
  ["多 Agent 系统", "多 Agent 等人派活，化言自己找活干",
   "觉发现该做的事，交给负责的人；Agent 准备材料，人来判断、签字。每一步都有主人，查得到。"],
  ["流程 / 规则系统", "规则只会报警，觉会学着判断",
   "觉一直看着业务，提出此刻该做的决定：还缺哪条信息、这单该不该找研发、几个需求是不是同一个课题。它从人的处理结果里学习，越用越准。"],
];
// 演示脚本里的事件：哪件事、走哪条线、亮哪个部件、说了什么
const EVENTS: [string, Edge | null, string | null, string][] = [
  ["常规问题客户自助", "c-h", null, "印染厂 A：「布染出来深一块浅一块，这个助剂能不能用？」"],
  ["常规问题客户自助", null, "jue", "觉：面料、设备、温度没说，当场追问补齐"],
  ["常规问题客户自助", "h-c", "qi", "契：按研发授权过的说明当场推荐，三个岗位零打扰"],
  ["商务诉求交业务员", "c-h", null, "印染厂 B：「这个产品想要个报价」"],
  ["商务诉求交业务员", "h-s", "jue", "觉：商务诉求转业务员，原话和条件一起交到手上"],
  ["商务诉求交业务员", "s-h", null, "业务员不用重问，直接报价"],
  ["商务诉求交业务员", "h-c", null, "报价回到客户"],
  ["新问题直达研发", "c-h", null, "印染厂 C：「布一洗就掉色」"],
  ["新问题直达研发", null, "jev", "Jev：现有产品都不适用 1.00"],
  ["新问题直达研发", "h-r", "agent", "产品经理 Agent 转成需求单，带原话和出处直达研发"],
  ["新问题直达研发", "r-cap", null, "研发判定现成的 TF-288B 能用，签字"],
  ["新问题直达研发", "h-p", "jue", "觉：研发判了说明书没写的用法，要不要扩大适用范围？"],
  ["新问题直达研发", "p-sheet", null, "产品经理批准范围，说明书补上这种用法"],
  ["试样失败，当天回问补齐", "r-h", null, "研发：第一次试样失败，勾出缺的条件「染料类别」"],
  ["试样失败，当天回问补齐", "h-c", null, "化言直接回问客户"],
  ["试样失败，当天回问补齐", "c-h", null, "客户：「活性染料」"],
  ["试样失败，当天回问补齐", "h-r", null, "答复回填原单，第二次试样通过"],
  ["产品机会", "c-h", null, "两家涤纶厂都说白布不白"],
  ["产品机会", "h-p", "jue", "觉：同类需求合成一个课题"],
  ["产品机会", "p-h", null, "产品经理一次拍板立项"],
  ["老结论首次放行", "h-r", "agent", "化言读出 2024 年真实试样报告：汽流缸 133℃ 匀染良好"],
  ["老结论首次放行", "r-cap", null, "研发对着原文确认，签字授予"],
  ["老结论首次放行", "h-p", null, "产品经理批准扩进适用范围"],
  ["同条件下一单复用", "c-h", null, "新客户：涤纶、气流缸、133℃"],
  ["同条件下一单复用", "cap-h", "qi", "契：条件完整满足，研发签过的判断直接复用"],
  ["同条件下一单复用", "h-c", null, "客户当场拿到推荐，研发零打扰"],
  ["条件不符回研发", "c-h", null, "另一位客户：135℃"],
  ["条件不符回研发", "h-r", "qi", "超出研发确认的 133℃，照样回研发，带方案包安排试样"],
  ["报告改版复核", null, "qi", "契：报告来源改版，依赖它的能力立即挂起"],
  ["报告改版复核", "h-r", null, "研发复核：结论不变，保留"],
  ["研发判断回流到过去的客户", "cap-h", "jue", "觉在历史里找回当时没解决的印染厂 A"],
  ["研发判断回流到过去的客户", "h-s", null, "业务员主动回访"],
  ["研发判断回流到过去的客户", "h-c", null, "老客户拿到推荐"],
  ["说明书跟上研发判断", "h-p", "jue", "觉：研发确认的 133℃ 超出了说明书"],
  ["说明书跟上研发判断", "p-sheet", null, "产品经理签字，说明书更新"],
  ["说明书跟上研发判断", "sheet-c", null, "下一位客户看说明书就知道"],
];
const ENDS: Record<Edge, [string, string]> = {
  "c-h": ["c", "h"], "h-c": ["h", "c"], "h-s": ["h", "s"], "s-h": ["s", "h"], "h-p": ["h", "p"], "p-h": ["p", "h"],
  "h-r": ["h", "r"], "r-h": ["r", "h"], "p-sheet": ["p", "sheet"], "r-cap": ["r", "cap"], "cap-h": ["cap", "h"], "sheet-c": ["sheet", "c"],
};
const PARTS: [string, string, string][] = [["jue", "觉", "发现值得决策的事"], ["jev", "Jev", "决策与核对概率"], ["qi", "契", "分层组织记忆"], ["agent", "Agent", "备材料、起草稿"]];
const ROLE_BOX: [string, string, string, number][] = [["s", "业务员", "商务与报价", 103], ["p", "产品经理", "范围与商业判断", 231], ["r", "研发", "专业判断与签字", 363]];

function OrgFlow() {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setTimeout(() => setI((i + 1) % EVENTS.length), 1600); return () => clearTimeout(t); }, [i]);
  const [title, edge, part, text] = EVENTS[i];
  const on = new Set(edge ? ENDS[edge] : ["h"]);
  const box = (k: string) => on.has(k) ? "rgba(63,208,255,.95)" : "rgba(255,255,255,.16)";
  const glow = (k: string) => on.has(k) ? "drop-shadow(0 0 10px rgba(63,208,255,.6))" : undefined;
  const n = 1 + [...new Set(EVENTS.slice(0, i + 1).map((e) => e[0]))].length - 1;
  return (
    <div>
      <svg viewBox="0 0 1240 470" className="w-full">
        <defs><marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="rgba(222,231,247,.45)" /></marker></defs>
        {/* 每条线上一直有光在流；正在发生的那条更亮、更快，切换时渐变过去 */}
        {(Object.keys(PATH) as Edge[]).map((e, k) => (
          <g key={e} className={`edge ${e === edge ? "on" : ""}`}>
            <path d={PATH[e]} fill="none" markerEnd="url(#arr)" className="edge-base" strokeDasharray={["cap-h", "sheet-c"].includes(e) ? "5 6" : undefined} />
            {[0, 1, 2].map((m) => (
              <path key={m} d={PATH[e]} pathLength={1000} fill="none" className="streak"
                    style={{ animationDelay: `${-((k * 0.37 + m / 3) % 1) * 1.4}s` }} />
            ))}
          </g>
        ))}
        {(Object.entries(LABEL) as [Edge, [number, number, string]][]).map(([e, [x, y, t]]) => (
          <text key={e} x={x} y={y} textAnchor="middle" fontSize="11.5" fill={e === edge ? "#3fd0ff" : "rgba(222,231,247,.5)"}>{t}</text>
        ))}
        {/* 客户 */}
        <g className="node-glow" style={{ filter: glow("c") }}>
          <rect x="30" y="186" width="140" height="92" rx="14" fill="#0f1c33" stroke={box("c")} strokeWidth="1.5" className="node-box" />
          <text x="100" y="226" textAnchor="middle" fill="#eaf0fb" fontSize="19" fontWeight="700">客户</text>
          <text x="100" y="252" textAnchor="middle" fill="rgba(222,231,247,.6)" fontSize="12">印染厂 · 说一次现象</text>
        </g>
        {/* 化言 */}
        <g className="node-glow" style={{ filter: glow("h") }}>
          <rect x="318" y="70" width="224" height="316" rx="18" fill="#10203d" stroke={box("h")} strokeWidth="1.8" className="node-box" />
          <text x="430" y="104" textAnchor="middle" fill="#fff" fontSize="20" fontWeight="800">化言</text>
          <text x="430" y="124" textAnchor="middle" fill="rgba(222,231,247,.6)" fontSize="11.5">组织级 Agent Harness</text>
          {PARTS.map(([k, t, sub], j) => (
            <g key={k} transform={`translate(336 ${142 + j * 58})`}>
              <rect width="188" height="46" rx="10" className="node-box" fill={part === k ? "rgba(63,208,255,.22)" : "rgba(255,255,255,.04)"} stroke={part === k ? "#3fd0ff" : "rgba(255,255,255,.1)"} />
              <text x="14" y="29" className="node-box" fill={part === k ? "#3fd0ff" : "#eaf0fb"} fontSize="16" fontWeight="700">{t}</text>
              <text x="70" y="28" fill="rgba(222,231,247,.65)" fontSize="11.5">{sub}</text>
            </g>
          ))}
        </g>
        {/* 岗位 */}
        {ROLE_BOX.map(([k, t, sub, y]) => (
          <g key={k} className="node-glow" style={{ filter: glow(k) }}>
            <rect x="735" y={y - 40} width="150" height="80" rx="14" fill="#0f1c33" stroke={box(k)} strokeWidth="1.5" className="node-box" />
            <text x="810" y={y - 4} textAnchor="middle" fill="#eaf0fb" fontSize="18" fontWeight="700">{t}</text>
            <text x="810" y={y + 20} textAnchor="middle" fill="rgba(222,231,247,.6)" fontSize="12">只做：{sub}</text>
          </g>
        ))}
        {/* 说明书与组织能力 */}
        <g className="node-glow" style={{ filter: glow("sheet") }}>
          <rect x="1060" y="112" width="170" height="76" rx="14" fill="#0f1c33" stroke={box("sheet")} strokeWidth="1.5" className="node-box" />
          <text x="1145" y="146" textAnchor="middle" fill="#eaf0fb" fontSize="16" fontWeight="700">说明书 · 公开层</text>
          <text x="1145" y="170" textAnchor="middle" fill="rgba(222,231,247,.6)" fontSize="12">L0 · 客户自己可查</text>
        </g>
        <g className="node-glow" style={{ filter: glow("cap") }}>
          <rect x="1060" y="288" width="170" height="84" rx="14" fill="#0f1c33" stroke={box("cap")} strokeWidth="1.5" className="node-box" />
          <text x="1145" y="322" textAnchor="middle" fill="#eaf0fb" fontSize="16" fontWeight="700">组织能力</text>
          <text x="1145" y="346" textAnchor="middle" fill="rgba(222,231,247,.6)" fontSize="12">契 L0–L3 · 配方永不降层</text>
        </g>
      </svg>
      <div className="mx-auto mt-1 flex max-w-[980px] items-center gap-3 rounded-[12px] border border-[rgba(63,208,255,.3)] bg-[rgba(63,208,255,.06)] px-4 py-2.5">
        <span className="shrink-0 rounded-full bg-[rgba(63,208,255,.16)] px-2.5 py-0.5 text-[12px] font-semibold text-[#3fd0ff]">第 {n} 件 · {title}</span>
        <span key={i} className="caption min-w-0 flex-1 truncate text-[15px] text-[#eaf0fb]">{text}</span>
        <span className="num shrink-0 text-[11px] text-[rgba(222,231,247,.45)]">业务流程演示 · {i + 1}/{EVENTS.length} · 循环</span>
      </div>
    </div>
  );
}
