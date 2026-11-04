// 看演示的导览：顶上一条「看演示」告诉讲的人这一幕看什么、去哪页、讲完点继续；每页顶上一张「怎么看这一页」；
// 流程回放里每件事走完，下面一张总结：亮点、和过去比强在哪、旧流程推算的数。
import { api } from "../api";
import { useApp, useData } from "../ctx";
import type { PlayLevel } from "../types";
import { usePlay } from "./Play";

const ACTS: Record<number, [string, string]> = {
  1: ["需求进来，化言接住每一位客户", "六件不同的业务同时进来：常规问题当场答、商务交业务员、新问题带着原话直达研发、条件没问清先回问、同类需求合成课题。"],
  2: ["研发判一次，组织记住", "化言读一份真实试样报告编出候选结论，研发确认一次、写清条件；条件相同的下一单直接用上，条件不符照样回研发，报告一改相关能力就停下复核。"],
  3: ["判断回流到过去的客户和说明书", "研发那次判断不只答下一单：觉在历史里找回当时没解决的客户，说明书也跟着更新到公开层。"],
};

// 进实况的某一页（已在实况页时由 Live 监听切换）
export function openLive(go: (page: string) => void, tab: string) {
  localStorage.setItem("huayan-live-tab2", tab);
  window.dispatchEvent(new Event("huayan-live-tab"));
  go("live");
}

export function WatchStep() {
  const { go, fail, refresh } = useApp();
  const s = usePlay();
  if (!s || !s.oneshot) return null;
  const all = s.done.length === s.levels.length;
  const act = s.act ?? 1;
  const [title, text] = ACTS[act] ?? ["", ""];
  const tour: [string, () => void][] = [
    ["① 流程回放：点「播放」，跟着顶上那句讲", () => openLive(go, "flow")],
    ["② 泳道：看每一步是觉、Jev、契、Agent 还是人做的", () => openLive(go, "lanes")],
    ["③ CEO 面：同一批事，旧流程和化言各花多少时间", () => go("ceo")],
  ];
  return (
    <div className="sticky top-[52px] z-20 flex flex-col gap-1.5 border-b border-sep bg-attn-bg px-6 py-2.5 text-[14px]">
      <div className="flex items-center gap-3">
        <span className="tag tag-accent shrink-0">看演示</span>
        {all ? <><span className="flex-1"><b>三幕都讲完了。</b>最后去结算页，一句话收尾：同样这批事，比旧流程省了多少人工、多少等待。</span>
            <button className="btn btn-primary glow" onClick={() => go("settle")}>看这一局省了什么</button></>
          : <><span className="min-w-0 flex-1"><b>第 {act} / 3 幕：{title}</b><span className="text-ink-2"> · {text}</span></span>
            {s.paused ? <button className="btn btn-primary glow shrink-0" onClick={() => api.playControl({ paused: false }).then(refresh, fail)}>
                {s.done.length ? "讲完了，进下一幕" : "开始第 1 幕"}</button>
              : <span className="shrink-0 text-ink-2">导演在跑这一幕，跑完自动停下……</span>}</>}
      </div>
      {!all && s.paused && !!s.done.length && <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className="text-ink-2">这一幕跑完了，按顺序讲：</span>
        {tour.map(([label, run]) => <button key={label} className="chip" onClick={run}>{label}</button>)}
      </div>}
    </div>
  );
}

// 每页顶上：零基础的人怎么看这一页
export function HowTo({ items }: { items: string[] }) {
  return (
    <div className="rounded-[12px] border border-sep bg-white px-4 py-3 text-[13px] leading-[20px]">
      <b className="text-[13.5px]">怎么看这一页</b>
      <ol className="mt-1 list-decimal pl-5 text-ink-2">{items.map((x) => <li key={x}>{x}</li>)}</ol>
    </div>
  );
}

// 一件事走完后的总结：亮点、和过去比、旧流程推算的数
export function CaseSummary({ level, sid }: { level: PlayLevel; sid?: string }) {
  const { me } = useApp();
  const est = useData(() => (sid ? api.oldFlow(sid, me) : Promise.resolve(null)), [sid, me]);
  const o = est?.old;
  return (
    <div className="mt-2 rounded-[10px] bg-emerald-50 px-3 py-2 text-[13px] leading-[20px] text-emerald-950">
      <p><b>这件事说明了：{level.point}</b><span className="text-emerald-800"> · 用到 {level.mechanism}</span></p>
      {level.vs && <p>和过去比：{level.vs}</p>}
      {o && est && <p className="text-emerald-800">旧流程推算：经过 {o.roles.length} 个岗位、交接 {o.handoffs} 次{o.backs ? `、回头补问 ${o.backs} 次` : ""}{o.reworks ? `、返工 ${o.reworks} 轮` : ""}，
        人工 {o.work_hours.toFixed(1)} 小时、等待 {o.wait_hours.toFixed(1)} 小时 → 化言：{est.now.roles.length ? `只经过 ${est.now.roles.join("、")}，` : "没有打扰任何岗位，"}人做了 {est.now.human_steps} 步。</p>}
    </div>
  );
}
