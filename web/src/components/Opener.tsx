// V12.11 岗位开场卡：进一个工作面先出一张「化言给你的三样新东西」，业务员、产品经理、研发另带一条时间色条（现状 → 这一局，推算），
// 讲完点「开始操作」收起，本次浏览不再弹出（右上角可以再打开）。只在打开演示说明时出现，真实试用里不出现。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";

const NEW: Record<string, { who: string; items: [string, string][] }> = {
  customer: { who: "客户", items: [
    ["说现象就够", "不用懂化学；化言会在你还在时问到研发开工需要的条件，每一句都留着你的原话"],
    ["能当场答的当场答", "研发签过、授予客户层的判断直接给你推荐；答不了的不猜，带着原话直达研发"],
    ["事情有下文", "进展随时能看；研发的新判断、新品出来，会主动回来找你"]] },
  sales: { who: "业务员", items: [
    ["觉替你记着该问什么", "客户还在时提示最关键的一两个条件，不用懂化学也能一次问到点上"],
    ["不用记录、不用转述", "产品经理 Agent 起草需求单，客户原话随单直达研发；你只做客户与商务"],
    ["你的 Agent 随叫随到", "可以主动委托它查资料、起草答复；它只在你这一层检索，越权的只告诉你谁知道"]] },
  pm: { who: "产品经理", items: [
    ["不再逐单转述", "逐单转译由产品经理 Agent 在后台做；你只做产品范围与商业判断"],
    ["零散的事汇成机会", "几位客户在说同一件事时，觉把它们合成一个产品机会交给你"],
    ["说明书跟上研发", "研发判断和说明书对不上时，觉请你更新；新品发布回到公开层"]] },
  rd: { who: "研发", items: [
    ["收到的单条件是齐的", "每句需求都回到客户原话，缺的条件趁客户还在就问了"],
    ["判断一次，下一单直接用", "你确认、授予的判断成为组织能力，替你答下一单；用一次记一次在你名下"],
    ["资料与方案替你备好", "Agent 在资料库里带原页查证，从历史试样推一个值得验证的方案；签字永远是你"]] },
  supervisor: { who: "研发负责人", items: [
    ["不当额外审批人", "日常的事各岗位自己闭合，你只处理例外"],
    ["风险与例外一眼看到", "泄露风险、对外说明去密、超期事项、挂起复核的能力，谁在办、等了多久"],
    ["能力谱系", "每项能力的依据、谁签的、用过几次；资料改版时看影响面"]] },
};
const GAIN = "#248a3d";

export function Opener({ role }: { role: string }) {
  const { me, meta, notes } = useApp();
  const key = `huayan-opener-${role}`;
  const [open, setOpen] = useState(() => sessionStorage.getItem(key) !== "0");
  const timed = ["sales", "pm", "rd"].includes(role);
  const bar = useData(() => (timed && open ? api.timeBar(me) : Promise.resolve(null)), [me, open, role]);
  const card = NEW[role];
  if (!card || !notes || (meta.trial && !meta.play)) return null;
  if (!open) return <button className="fixed right-[388px] top-[60px] z-20 chip" onClick={() => { sessionStorage.removeItem(key); setOpen(true); }}>化言给你的三样新东西</button>;
  const close = () => { sessionStorage.setItem(key, "0"); setOpen(false); };
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/25" onClick={close}>
      <div className="w-[640px] rounded-[16px] bg-white px-7 py-6 shadow-[0_18px_50px_rgba(0,0,0,.2)]" onClick={(e) => e.stopPropagation()}>
        <p className="eyebrow">{card.who}</p>
        <p className="mt-1 text-[22px] font-semibold">化言给你的三样新东西</p>
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
