// V11.5 游戏模式的进度条（工具栏中间）。V11.12：各岗位自己的业务开局一起送来，关卡（一条完整的业务流程）一步过了才送下一步。
// 收起时写轮到你的事；点开按岗位列业务、单列关卡各步，点一件就以等它的那个人进他的工作面（路演时一个人轮流演各岗位）。
// 下面是暂停 / 倍速 / 重开这一局，以及路演局、报告的选择。进度由服务端的导演保存，几个浏览器共用一局。
import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp, useLabels } from "../ctx";
import type { PlayLevel, PlayState } from "../types";
import { Popover } from "./Controls";
import { ChevronDown } from "./Icons";

const TO: Record<string, string> = { customer: "客户面", sales: "业务员面", pm: "产品经理面", rd: "研发面" };
const ROLES: [string, string][] = [["customer", "客户"], ["sales", "业务员"], ["pm", "产品经理"], ["rd", "研发"]];
const SPEEDS: [number, string][] = [[10, "慢"], [60, "1 秒 = 1 分钟"], [600, "1 秒 = 10 分钟"]];
const MARK = { passed: "✓", open: "›", waiting: "" };

export function usePlay(): PlayState | null {
  const { meta, version } = useApp();
  const [s, setS] = useState<PlayState | null>(null);
  useEffect(() => {
    if (!meta.play) return;
    const load = () => api.playState().then(setS, () => {});
    load();
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [meta.play, version]);
  return s;
}

export function PlayBar() {
  const { fail, refresh, me, go, become } = useApp();
  const L = useLabels();
  const s = usePlay();
  const [busy, setBusy] = useState<string | null>(null);
  if (!s) return null;
  const run = (label: string, p: Promise<unknown>) => {
    setBusy(label);
    p.then(() => refresh()).catch(fail).finally(() => setBusy(null));
  };
  const restart = (p: { real?: boolean; roadshow?: boolean }) =>
    confirm("开新的一局：业务和关卡第 1 步重新送来，这一局的进度不保留。确定吗？") && run("正在开新的一局……", api.playRestart(p));
  const mine = s.lines.filter((x) => x.customer === me);       // 我扮的客户接下来可以说的话
  const notes = s.notes.filter((x) => x.who === me);           // 外部世界给我的结果（试样）
  const turn = s.levels.filter((x) => x.status === "open" && (x.who === me || (!x.who && x.to === me.split(":")[0])));
  const open = s.levels.filter((x) => x.status === "open").length;
  const all = s.done.length === s.levels.length;
  const enter = (x: PlayLevel) => (x.who && x.who !== me ? become(x.who) : go(x.to));
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
    <Popover trigger={(toggle) => (
      <button onClick={toggle} className={`flex h-8 max-w-[640px] items-center gap-2 rounded-[8px] px-2.5 text-[13px] hover:bg-fill ${
        all ? "bg-[rgba(48,194,91,.11)]" : turn.length ? "bg-attn-bg" : ""}`}>
        <span className="tag tag-accent">{s.roadshow ? "路演局" : `第 ${s.round} 局`}</span>
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
            {s.roadshow ? "路演局：各岗位的事都留给你，导演只扮演外部世界（客户、试样结果、资料改版）和事到你手上之前别的岗位那几步。"
                        : "没人玩的岗位和客户由导演代办，前情里标「模拟」。"}
            点一件就以等它的那个人进他的工作面。业务时间 {s.now.slice(5, 16).replace("T", " ")} · 第 {s.round} 局</p>
          {s.error && <p role="alert" className="text-[12px] text-danger">导演这一拍没做成：{s.error}</p>}
          <div className="flex flex-wrap items-center gap-1.5">
            <button className="btn btn-plain" onClick={() => run("…", api.playControl({ paused: !s.paused }))}>{s.paused ? "继续" : "暂停"}</button>
            {SPEEDS.map(([v, label]) => (
              <button key={v} className={`btn btn-plain ${s.speed === v ? "!text-accent" : ""}`} onClick={() => run("…", api.playControl({ speed: v }))}>{label}</button>
            ))}
            <button className="btn btn-plain ml-auto" onClick={() => go("settle")}>看这一局的结算</button>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
            <span className="text-ink-2">这一局</span>
            {([[true, "路演局"], [false, "导演代办没人玩的岗位"]] as const).map(([v, label]) => (
              <button key={label} className={`btn btn-plain ${s.roadshow === v ? "!text-accent" : ""}`} disabled={!!busy || s.roadshow === v}
                      onClick={() => restart({ roadshow: v })}>{label}</button>
            ))}
            {s.real_ready && <>
              <span className="ml-2 text-ink-2">关卡的报告</span>
              {([[false, "模拟报告"], [true, "真实试样报告"]] as const).map(([v, label]) => (
                <button key={label} className={`btn btn-plain ${s.real === v ? "!text-accent" : ""}`} disabled={!!busy || s.real === v}
                        onClick={() => restart({ real: v })}>{label}</button>
              ))}
            </>}
            <button className="btn btn-plain ml-auto" disabled={!!busy} onClick={() => restart({})}>重开这一局</button>
          </div>
        </div>
      )}
    </Popover>
  );
}
