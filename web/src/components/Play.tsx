// V11.5 游戏模式的进度条（工具栏中间）。V11.12：各岗位自己的业务开局一起送来，关卡（一条完整的业务流程）一步过了才送下一步。
// 收起时写轮到你的事；点开按岗位列业务、单列关卡各步，点一件就以等它的那个人进他的工作面（路演时一个人轮流演各岗位）。
// 下面是暂停 / 继续，换一局（看演示 / 自己玩）与重开这一局。进度由服务端的导演保存，几个浏览器共用一局。
import { useEffect, useState } from "react";
import { NO_GUIDE, publish } from "./Guide";
import { api, GAME, gameLink } from "../api";
import { useApp, useLabels } from "../ctx";
import type { PlayLevel, PlayState } from "../types";
import { Popover } from "./Controls";
import { ChevronDown } from "./Icons";

const TO: Record<string, string> = { customer: "客户面", sales: "业务员面", pm: "产品经理面", rd: "研发面", supervisor: "研发负责人面" };
const ROLES: [string, string][] = [["customer", "客户"], ["sales", "业务员"], ["pm", "产品经理"], ["rd", "研发"], ["supervisor", "研发负责人"]];
const SPEEDS: [number, string][] = [[10, "慢"], [60, "1 秒 = 1 分钟"], [600, "1 秒 = 10 分钟"]];
const MARK = { passed: "✓", open: "›", waiting: "" };

export function usePlay(): PlayState | null {
  const { meta, version } = useApp();
  const [s, setS] = useState<PlayState | null>(null);
  useEffect(() => {
    if (!meta.play) return;
    const load = () => api.playState().then(setS, () => {});
    load();
    const timer = setInterval(load, 1000);
    return () => clearInterval(timer);
  }, [meta.play, version]);
  return s;
}

// 这件事由谁做：写了人就是那个人；还没落到人手上的，用这个岗位的第一个人（身份不对时只 go 会被打回自己的页）
function whoFor(x: PlayLevel, me: string, actors: { id: string; role: string }[]) {
  return x.who ?? (me.startsWith(`${x.to}:`) ? me : actors.find((a) => a.role === x.to && a.id !== "supervisor:CEO" && a.id !== "pm:agent")?.id);
}
const IM = new Set(["sales", "pm", "rd", "supervisor"]);

// 现在轮到我的那一步：业务流程演示（一个人走所有岗位）严格按顺序一件一件走，前一件还在路上就等它；多人一局各做各的
export function myTurn(s: PlayState | null, me: string) {
  const open = s && !s.oneshot ? s.levels.filter((x) => x.status === "open") : [];
  const landed = s?.roadshow ? open.slice(0, 1).filter((x) => x.who) : open.filter((x) => x.who);
  return { open, landed, mine: landed.find((x) => x.who === me) };
}

function useEnter() {
  const { me, meta, go, become } = useApp();
  return (x: PlayLevel) => {
    const who = whoFor(x, me, meta.actors);
    const page = who?.split(":")[0] ?? x.to;     // 产品经理那件事可能先等研发：进等它的那个人的工作面
    const focus = IM.has(page) ? null : x.focus;   // 岗位工作面不直接打开那件事：化言把它推到消息里，点「去处理」才打开
    return who && who !== me ? become(who, page, focus) : go(page, focus);
  };
}

// 关卡里这一步（hint）→ 工作面上该发亮的地方与「演示自动填入」的内容：发话是「发出」框，判已有产品适用是「不接：现成产品能用」，
// 批范围 / 合并课题是产品经理的签字区，录试样是试样按钮，客户是输入框，其余是「要你定」卡片的主按钮（示范文字写在下一步条上）
function TARGET(x: PlayLevel): [string, string | null] {
  const h = (x.hint ?? {}) as Record<string, string>;
  if (x.to === "customer" || x.who?.startsWith("customer:")) return ["say", null];
  if (h.say) return ["send", h.say];
  if (h.reuse) return ["reuse-no", h.reuse];
  if (h.decline) return ["decline", JSON.stringify(h.decline)];
  if (h.scope) return ["scope", h.scope];
  if (h.merge) return ["merge", h.merge];
  if (h.trial) {   // 试样结果由导演按世界规律给：没过就指「录入不通过」，并带上原因和缺的条件
    const t = h.trial as unknown as { result: string; missing: string[] } | true;
    return t !== true && t.result === "fail" ? ["trial-fail", t.missing.join(",")] : ["trial", null];
  }
  return ["task", null];
}
const NOTE_KEYS = ["review", "recall", "sheet", "note"];
// 一件事要几个岗位接力时，按正在等的那个人这一步写要做什么
const STEP: Record<string, string> = { say: "回客户一句话", decline: "判断现成产品就能用，不接单", scope: "批准扩大产品的适用范围",
  merge: "把几位客户的需求合成一个课题", reuse: "这次不采用现成产品：点「演示自动填入」写理由，再点「不采用」", accept: "接单", trial: "录试样结果",
  confirm: "确认化学要点：研发 Agent 已按客户原话写好，看一遍点确认",
  rework: "试样没过、缺条件：点「退回重新转译」，化言会回头问客户缺的那一条，答复填回这张单",
  review: "复核资料改版后的结论", recall: "回访过去没解决的客户", sheet: "按研发的判断更新说明书" };
export const todo = (x: PlayLevel) => {
  const t = (x.hint?.trial ?? null) as { result: string; labels: string } | null;
  if (t && typeof t === "object") return t.result === "fail"
    ? `录试样结果：这次没过，原因是「${t.labels}」当初没问到。点「需求条件缺失」，勾上「${t.labels}」，再点「录入不通过」`
    : "录试样结果：这次过了，点「试样通过」";
  return STEP[Object.keys(x.hint ?? {})[0]] ?? x.decide;
};

// 自己玩：工作面顶上一条「下一步」。轮到你时写要做什么，并让工作面上「要你定」的主按钮（客户是输入框）呼吸高亮；
// 轮到别人时写轮到谁、做什么，点一下就换成他进他的工作面。
export function NextStep() {
  const { me, meta, fail, refresh, go } = useApp();
  const L = useLabels();
  const s = usePlay();
  const enter = useEnter();
  // 还没落到具体的人手上（who 为空）的事在路上：客户还在说、Agent 还在准备，不算轮到谁
  const { open, landed, mine } = myTurn(s, me);
  const next = mine ?? landed[0];
  const line = s?.lines.find((x) => x.customer === me);
  const [target, arg] = mine ? TARGET(mine) : [null, null];
  const note = mine?.hint && NOTE_KEYS.map((k) => (mine.hint as Record<string, unknown>)[k]).find((v) => typeof v === "string") as string | undefined;
  useEffect(() => { publish(target ? { who: me, target, arg, customer: null } : NO_GUIDE); }, [me, target, arg]);
  // 轮到你的下一件换了：直接打开那件事（同一件不重复跳，看别处时不被拉回）
  useEffect(() => { const page = me.split(":")[0]; if (mine?.focus) go(page, IM.has(page) ? null : mine.focus); }, [mine?.id, mine?.focus]);
  if (!s || s.oneshot) return null;
  const all = s.done.length === s.levels.length;
  const who = next?.who ?? undefined;
  return (
    <div className="sticky top-[52px] z-20 flex items-center gap-3 border-b border-sep bg-attn-bg px-6 py-2.5 text-[14px]">
      <span className="tag tag-accent shrink-0">下一步</span>
      {all ? <><span className="flex-1">整条业务都走完了。</span><button className="btn btn-primary" onClick={() => go("settle")}>看这一局省了什么</button></>
        : !next ? <span className="flex-1 text-ink-2">{s.paused ? "这一局停着，点右边「继续」。"
            : `事情在路上（客户在说、Agent 在准备）：${open.map((x) => x.title).join("、") || "导演正在送下一件事"}。到了谁手上，这里马上告诉你。`}</span>
        : mine ? <>
            <span className="min-w-0 flex-1"><b>轮到你：{todo(mine)}</b><span className="text-ink-2"> · {mine.brief}。{IM.has(me.split(":")[0]) ? "化言推到左边消息里了，点「去处理」打开，再点发亮的地方。" : "页面上呼吸发亮的就是要点的。"}</span></span>
            {note && <button className="chip shrink-0" title={`${note}（点一下复制）`} onClick={() => navigator.clipboard.writeText(note)}>
              示范：「{note.slice(0, 14)}…」复制</button>}
            {line && <button className="btn btn-primary glow shrink-0" onClick={() => api.addTurn(line.session_id, "customer", line.text).then(refresh, fail)}>
              照这句说：「{line.text.slice(0, 18)}{line.text.length > 18 ? "…" : ""}」</button>}
          </>
        : <>
            <span className="min-w-0 flex-1">轮到 <b>{L.name(who)}</b>（{ROLES.find(([r]) => r === who?.split(":")[0])?.[1]}）：{todo(next)}</span>
            <button className="btn btn-primary glow shrink-0" onClick={() => enter(next)}>换成{L.name(who)}，去处理</button>
          </>}
      {s.paused && !all && <button className="btn btn-plain shrink-0" onClick={() => api.playControl({ paused: false }).then(refresh, fail)}>继续</button>}
    </div>
  );
}

export function PlayBar() {
  const { fail, refresh, me, go } = useApp();
  const L = useLabels();
  const s = usePlay();
  const [busy, setBusy] = useState<string | null>(null);
  if (!s) return null;
  const run = (label: string, p: Promise<unknown>) => {
    setBusy(label);
    p.then(() => refresh()).catch(fail).finally(() => setBusy(null));
  };
  const restart = (p: { real?: boolean; roadshow?: boolean; oneshot?: boolean }) =>
    confirm("开新的一局：业务和关卡第 1 步重新送来，这一局的进度不保留。确定吗？") && run("正在开新的一局……", api.playRestart(p));
  const mine = s.lines.filter((x) => x.customer === me);       // 我扮的客户接下来可以说的话
  const notes = s.notes.filter((x) => x.who === me);           // 外部世界给我的结果（试样）
  const turn = s.levels.filter((x) => x.status === "open" && (x.who === me || (!x.who && x.to === me.split(":")[0])));
  const open = s.levels.filter((x) => x.status === "open").length;
  const all = s.done.length === s.levels.length;
  const enter = useEnter();
  const row = (x: PlayLevel) => (
    <button key={x.id} onClick={() => enter(x)} disabled={x.status === "waiting"}
            className={`flex w-full gap-2 rounded-[6px] px-1.5 py-0.5 text-left hover:bg-fill disabled:hover:bg-transparent ${
              x.status === "open" ? (turn.includes(x) ? "font-semibold text-attn-ink" : "") : "text-ink-3"}`}
            title={x.status === "open" ? `${x.decide}${x.who ? ` · 以${L.name(x.who)}进入` : ""}` : x.status === "waiting" ? "前一步过了才送来" : "已通过"}>
      <span className="w-3 shrink-0">{MARK[x.status]}</span>
      <span className="shrink-0">{x.id}</span><span className="truncate">{x.title}</span>
    </button>
  );
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <Popover trigger={(toggle) => (
        <button onClick={toggle} className={`flex h-8 min-w-0 max-w-[min(640px,100%)] items-center gap-2 rounded-[8px] px-2.5 text-[13px] hover:bg-fill ${
          all ? "bg-[rgba(48,194,91,.11)]" : turn.length ? "bg-attn-bg" : ""}`}>
          <span className="tag tag-accent">{s.oneshot ? `CEO 视角总结${s.act ? ` · 第 ${s.act} 幕` : ""}` : "业务流程演示"}</span>
          {turn[0] ? <><span className="truncate font-semibold">{turn[0].id} · {turn[0].title}</span>
                       <span className="truncate text-ink-2">· {turn[0].brief}</span></>
                   : <span className="truncate text-ink-2">{all ? "业务和关卡都过了" : `进行中 ${open} 件`}</span>}
          <span className={`shrink-0 ${turn.length ? "font-semibold text-attn-ink" : "text-ink-2"}`}>
            {busy ?? (s.paused ? "已暂停" : turn.length ? `轮到你 ${turn.length} 件` : "")}</span>
          <ChevronDown />
        </button>
      )}>
        {() => (
          <div className="flex w-[460px] flex-col gap-3 p-3 text-[13px] leading-5">
            {turn.map((x) => (
              <div key={x.id}>
                <p className="eyebrow">{x.id} · 轮到你</p>
                <p>{x.brief}，到{TO[x.to]}。<span className="text-ink-2">要你做的：{x.decide}</span></p>
                <p className="text-[12px] text-ink-2">会用到：{x.mechanism} · 看点：{x.point}</p>
              </div>
            ))}
            {mine.map((x) => (
              <div key={x.session_id} className="rounded-[8px] bg-attn-bg px-2.5 py-2">
                <p className="eyebrow">你扮的客户可以这样说</p>
                <p>「{x.text}」</p>
                <button className="btn btn-plain mt-1" disabled={!!busy}
                        onClick={() => run("…", api.addTurn(x.session_id, "customer", x.text))}>照这句说</button>
                <span className="ml-2 text-[12px] text-ink-3">也可以在客户面用自己的话说</span>
              </div>
            ))}
            {notes.map((x, i) => (
              <div key={i} className="rounded-[8px] bg-attn-bg px-2.5 py-2">
                <p className="eyebrow">外部世界（模拟）</p><p>{x.text}</p>
              </div>
            ))}
            <div className="grid grid-cols-2 gap-x-3 gap-y-2 border-t border-sep pt-2">
              <div className="flex flex-col">
                <p className="eyebrow">各岗位的业务</p>
                {ROLES.map(([role, label]) => {
                  const items = s.levels.filter((x) => x.kind === "business" && x.to === role);
                  return items.length > 0 && <div key={role}><p className="mt-1 text-[12px] text-ink-2">{label}</p>{items.map(row)}</div>;
                })}
              </div>
              <div className="flex flex-col">
                <p className="eyebrow">关卡：一条完整的业务流程</p>
                <p className="mt-1 text-[12px] text-ink-2">同一份试样报告，一步过了才送下一步</p>
                {s.levels.filter((x) => x.kind === "stage").map(row)}
              </div>
            </div>
            <p className="text-[12px] text-ink-3">
              {s.oneshot ? "CEO 视角总结：导演按三幕把所有岗位的事做完，你在组织运行实况里看每一次交接。" : "业务流程演示：各岗位的事都留给你，导演只扮演客户和外部世界（试样结果、资料改版）。"}
              点一件就以等它的那个人进他的工作面。业务时间 {s.now.slice(5, 16).replace("T", " ")} · 第 {s.round} 局</p>
            {s.error && <p role="alert" className="text-[12px] text-danger">导演这一拍没做成：{s.error}</p>}
            <div className="flex flex-wrap items-center gap-1.5">
              <button className="btn btn-plain" onClick={() => run("…", api.playControl({ paused: !s.paused }))}>{s.paused ? "继续" : "暂停"}</button>
              <span className="ml-3 text-ink-2">换一局</span>
              {([[true, "CEO 视角总结"], [false, "业务流程演示"]] as const).map(([watch, label]) => (
                <button key={label} className={`btn btn-plain ${s.oneshot === watch ? "!text-accent" : ""}`} disabled={!!busy}
                        onClick={() => restart({ oneshot: watch, roadshow: !watch })}>{label}</button>))}
              <button className="btn btn-plain" disabled={!!busy} title="每个岗位由一个真人扮演；没人扮的岗位和客户由导演做"
                      onClick={() => restart({ roadshow: false, oneshot: false })}>多人一局</button>
              <button className="btn btn-plain ml-auto" disabled={!!busy} onClick={() => restart({})}>重开这一局</button>
            </div>
            <div className="flex items-center gap-2 text-[12px]">
              <span className="text-ink-2">{GAME ? "你在别人开的这一局里。" : "让别人加入这一局（每人选一个岗位）："}</span>
              {!GAME && <><code className="min-w-0 flex-1 truncate rounded bg-fill px-1.5 py-0.5">{gameLink()}</code>
                <button className="btn btn-plain" onClick={() => navigator.clipboard.writeText(gameLink())}>复制链接</button></>}
            </div>
          </div>
        )}
      </Popover>
      {s.paused && !busy && (   // 暂停时导演不动、业务时间不走，「继续」放在外面一眼看得到
        <button className="btn btn-primary !h-[28px] shrink-0" title={s.oneshot ? "一镜到底：导演接着往下演" : "导演和业务时间接着走"}
                onClick={() => run("…", api.playControl({ paused: false }))}>继续</button>)}
    </div>
  );
}
