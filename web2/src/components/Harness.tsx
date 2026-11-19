// V12.11 活的架构图：ARCHITECTURE.md 第 0 节的组织级 Agent Harness，每个组件写这一局的实数（门面 harness_counts，只有计数）。
// 一圈是「业务信息 → 业务对象与状态 → 觉 → 问题总线 → 角色 Agent → 专业判断 → 行动 → 回到状态」，契在旁边供给能力、收回确认与授予，
// 人在上面设定、判断与签字；底下是模型网关，觉对大模型的调用恒为 0。每 3 秒重读一次，变了的数闪一下。
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { HarnessCounts } from "../types";

function Num({ v, label }: { v: number; label: string }) {
  const last = useRef(v);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (v !== last.current) { last.current = v; setFlash(true); const t = setTimeout(() => setFlash(false), 900); return () => clearTimeout(t); }
  }, [v]);
  return <span className={`flex items-baseline gap-1 rounded px-1 transition-colors duration-700 ${flash ? "bg-[rgba(36,138,61,.18)]" : ""}`}>
    <span className="num text-[17px] font-semibold">{v}</span><span className="text-[11.5px] text-ink-2">{label}</span></span>;
}

function Box({ title, sub, nums, tone = "", wide }: { title: string; sub: string; nums: [number, string][]; tone?: string; wide?: boolean }) {
  return <div className={`flex flex-col gap-1 rounded-[10px] border px-3 py-2 ${tone || "border-line bg-white"} ${wide ? "col-span-2" : ""}`}>
    <p className="text-[13px] font-semibold">{title}</p>
    <p className="text-[11.5px] leading-4 text-ink-2">{sub}</p>
    <div className="mt-auto flex flex-wrap gap-x-2">{nums.map(([v, l]) => <Num key={l} v={v} label={l} />)}</div>
  </div>;
}

const Arrow = ({ d = "→" }: { d?: string }) => <span className="flex items-center justify-center text-[18px] text-ink-3">{d}</span>;

export function Harness({ viewer }: { viewer: string }) {
  const [c, setC] = useState<HarnessCounts | null>(null);
  useEffect(() => {
    const load = () => api.harness(viewer).then(setC, () => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [viewer]);
  if (!c) return null;
  const JUE = "border-[rgba(201,52,0,.35)] bg-[rgba(201,52,0,.04)]", QI = "border-[rgba(10,108,223,.4)] bg-[rgba(10,108,223,.04)]";
  return (
    <div className="flex flex-col gap-2.5">
      <Box title="人" sub="设定目标与约束 · 专业判断 · 确认与授予；也可随时主动委托、主动决定" tone="border-[rgba(36,138,61,.4)] bg-[rgba(36,138,61,.05)]"
           nums={[[c.human.signs, "次签字"], [c.human.confirms, "条结论确认"], [c.human.grants, "项能力授予"], [c.human.decisions, "次主动决定"]]} />
      <div className="grid grid-cols-[1fr_200px] gap-2.5">
        <div className="rounded-[12px] border border-dashed border-line p-2.5">
          <p className="pb-2 text-[12px] font-semibold text-ink-2">协同中枢（组织级 Agent Harness：一组运行职责，由现有组件承担，不另设总调度 Agent）</p>
          <div className="grid grid-cols-[1fr_24px_1fr_24px_1fr_24px_1fr] gap-y-2">
            <Box title="业务信息" sub="客户对话 · 试样与评价 · 资料变更" nums={[[c.info.turns, "句对话"], [c.info.trials, "次试样"], [c.info.source_changes, "次资料变更"]]} />
            <Arrow />
            <Box title="业务对象与状态" sub="会话 · 需求单 · 产品，落盘续跑" nums={[[c.state.sessions, "段会话"], [c.state.requirements, "张需求单"], [c.state.products, "个产品"]]} />
            <Arrow />
            <Box title="觉" sub="形成 · 维持 · 筛选 · 提交值得决策的事" tone={JUE}
                 nums={[[c.jue.evaluations, "次评估"], [c.jue.raised, "件提出"], [c.jue.hints, "次追问提示"], [c.jue.auto, "次自动推进"]]} />
            <Arrow />
            <Box title="问题总线" sub="事项 · 主人 · 签字人" nums={[[c.bus.open, "件待办"], [c.bus.prepared, "件已准备"], [c.bus.resolved, "件已处理"]]} />
            <Box title="行动" sub="门面原子方法 · 授权内自动执行" nums={[[c.act.events, "条事件"]]} />
            <Arrow d="←" />
            <Box title="专业判断" sub="人 · Jev（匹配、披露、核对）· 规则" tone={QI}
                 nums={[[c.jev.calls, "次 Jev"], [c.jev.matches, "次匹配"], [c.jev.recommends, "次推荐"]]} />
            <Arrow d="←" />
            <Box title="角色 Agent" sub="借委托人权限调原子工具，准备材料与草稿" wide
                 nums={[[c.agent.tools, "次工具调用"], [c.agent.rejected, "次被门面拒绝"], [c.agent.blocked, "次越权命中"]]} />
            <Arrow d="↑" />
          </div>
        </div>
        <Box title="契" sub="依据 → 结论 → 能力；阅读视图 / 能力视图。确认与授予回到这里，能力限定觉能提出的事" tone={QI}
             nums={[[c.qi.claims, "条结论"], [c.qi.candidates, "条候选"], [c.qi.capabilities, "项能力生效"], [c.qi.suspended, "项挂起"], [c.qi.used, "次被使用"]]} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-[10px] border border-line bg-white px-3 py-2 text-[12px]">
        <span className="font-semibold">模型网关</span>
        {Object.entries(c.gateway).map(([k, n]) => <span key={k} className="num">{k} {n} 次</span>)}
        {!Object.keys(c.gateway).length && <span className="text-ink-2">这一局没有调用大模型（离线回放或规则模式）</span>}
        <span className="num font-semibold text-[#c93400]">觉 {c.jue.llm} 次</span>
        <span className="text-ink-2">所有大模型调用都经网关、带调用方；觉的发现只用规则、OneJev / Clef 与本地 Jue-K</span>
      </div>
    </div>
  );
}
