// V12.11 岗位开场卡（教程）：进一个工作面先出一张「你的岗位在化言里」，业务员、产品经理、研发另带一条时间色条（现状 → 这一局，推算），
// 讲完点「开始操作」收起，本次浏览不再弹出（右上角可以再打开）。游戏模式总是出现，演示时随演示说明，真实试用里不出现。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";

// 初始教程：你在化言里是谁、能做什么、和传统流程有什么不同
const NEW: Record<string, { who: string; items: [string, string][] }> = {
  customer: { who: "客户", items: [
    ["你在化言里是谁", "提需求的人。不用先找业务员，直接对化言说你看到的现象，比如「深一块浅一块」。"],
    ["你能做什么", "说现象，回答化言追问的一两个条件，拿到推荐和说明书；随时看进度，想采购就点「我要报价」。"],
    ["和传统流程有什么不同", "过去：打电话给业务员 → 业务员问产品经理 → 再转研发，等几天，条件还在转述里丢了。现在：常规问题当场答；新问题带着你的原话直达研发。"]] },
  sales: { who: "业务员", items: [
    ["你在化言里是谁", "管客户和商务的人。技术问题化言先替你答，答不了的直接交研发。"],
    ["你能做什么", "报价、回访客户；跟客户聊时按觉的提示追问关键条件；随时委托你的 Agent 查资料、写话术。"],
    ["和传统流程有什么不同", "过去：技术问题全压在你身上，还要把客户需求记下来转述给产品经理。现在：不用记录、不用转述，客户原话随单直达研发。"]] },
  pm: { who: "产品经理", items: [
    ["你在化言里是谁", "管产品范围和商业判断的人。"],
    ["你能做什么", "几家客户说的同一件事要不要合成一个课题；研发判过能用的场合要不要写进产品范围；说明书要不要更新。"],
    ["和传统流程有什么不同", "过去：逐单把客户的话转述给研发、查资料答复业务员。现在：这些由产品经理 Agent 准备好，你只签判断。"]] },
  rd: { who: "研发", items: [
    ["你在化言里是谁", "专业判断的源头。"],
    ["你能做什么", "接单或判断现有产品就能用；录试样结果；确认从试样报告里读出的结论，并决定给谁用；资料改版时复核。"],
    ["和传统流程有什么不同", "过去：条件不全要回头找客户，同样的问题被反复问。现在：原话和条件齐了才到你手上；你判一次，下一位同条件的客户直接用上。"]] },
  supervisor: { who: "研发负责人", items: [
    ["你在化言里是谁", "只处理例外的人。"],
    ["你能做什么", "看风险与例外（资料改版引出的复核、超期、Agent 失败）；看每条能力是谁签的、用过几次。"],
    ["和传统流程有什么不同", "过去：逐件审批、开会问进展。现在：常规的事各岗位自己闭环，出了例外才来找你。"]] },
};
const GAIN = "#248a3d";

export function Opener({ role }: { role: string }) {
  const { me, meta, notes } = useApp();
  const key = `huayan-opener-${role}`;
  const [open, setOpen] = useState(() => sessionStorage.getItem(key) !== "0");
  const timed = ["sales", "pm", "rd"].includes(role);
  const bar = useData(() => (timed && open ? api.timeBar(me) : Promise.resolve(null)), [me, open, role]);
  const card = NEW[role];
  if (!card || (meta.trial ? !meta.play : !notes)) return null;   // 游戏模式总是先给教程；真实试用不弹
  if (!open) return <button className="fixed bottom-4 right-4 z-20 chip" onClick={() => { sessionStorage.removeItem(key); setOpen(true); }}>这个岗位怎么玩</button>;
  const close = () => { sessionStorage.setItem(key, "0"); setOpen(false); };
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/25" onClick={close}>
      <div className="w-[640px] rounded-[16px] bg-white px-7 py-6 shadow-[0_18px_50px_rgba(0,0,0,.2)]" onClick={(e) => e.stopPropagation()}>
        <p className="eyebrow">{card.who}</p>
        <p className="mt-1 text-[22px] font-semibold">你的岗位在化言里</p>
        <div className="mt-4 flex flex-col gap-3">
          {card.items.map(([title, text], i) => <div key={title} className="flex gap-3">
            <span className="num flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[14px] font-semibold text-white" style={{ background: GAIN }}>{i + 1}</span>
            <div><p className="text-[15px] font-semibold">{title}</p><p className="text-[13px] leading-5 text-ink-2">{text}</p></div>
          </div>)}
        </div>
        {bar && <div className="mt-5 flex flex-col gap-1.5 text-[12px]">
          <p className="text-ink-2">你的时间用在本职上的比例（现状从岗位对比图上量出，这一局按 {bar.cases} 件事推算）</p>
          {[["现状", bar.own_before], ["这一局", bar.own_after]].map(([label, own]) => <div key={label as string} className="flex items-center gap-2">
            <span className="w-[44px] text-ink-2">{label}</span>
            <div className="flex h-[18px] flex-1 overflow-hidden rounded-[5px] bg-[#e08a2b] text-[11px] font-semibold leading-[18px] text-white">
              <div style={{ width: `${own}%`, background: GAIN, transition: "width .8s" }} className="px-1.5">本职 {Math.round(own as number)}%</div>
            </div>
          </div>)}
        </div>}
        <div className="mt-5 flex justify-end"><button className="btn btn-primary" onClick={close}>开始操作</button></div>
      </div>
    </div>
  );
}
