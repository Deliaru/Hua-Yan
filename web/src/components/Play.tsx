// V11.5 游戏模式的关卡条（工具栏中间）：第几关、导演送来什么、到谁的工作面、要你做什么、通关了没有；
// 点开看九关、这一关的机制与旁白要点，以及暂停 / 倍速 / 重开本关 / 下一关。进度由服务端的导演保存，几个浏览器共用一局。
import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import type { PlayState } from "../types";
import { Popover } from "./Controls";
import { ChevronDown } from "./Icons";

const TO: Record<string, string> = { customer: "客户面", sales: "业务员面", pm: "产品经理面", rd: "研发面" };
const SPEEDS: [number, string][] = [[10, "慢"], [60, "1 秒 = 1 分钟"], [600, "1 秒 = 10 分钟"]];

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
  const { fail, refresh, me, go } = useApp();
  const s = usePlay();
  const [busy, setBusy] = useState<string | null>(null);
  if (!s) return null;
  const lv = s.levels[s.level];
  const run = (label: string, p: Promise<PlayState>) => {
    setBusy(label);
    p.then(() => refresh()).catch(fail).finally(() => setBusy(null));
  };
  const mine = s.lines.filter((x) => x.customer === me);       // 我扮的客户接下来可以说的话
  const notes = s.notes.filter((x) => x.who === me);           // 外部世界给我的结果（试样）
  const myTurn = !s.passed && lv.ready && (mine.length > 0 || notes.length > 0 || lv.to === me.split(":")[0]);
  const state = busy ?? (!lv.ready ? "这一关还没接上导演" : s.passed ? "已通关" : s.paused ? "已暂停" : myTurn ? "轮到你" : "进行中");
  return (
    <Popover trigger={(toggle) => (
      <button onClick={toggle} className={`flex h-8 max-w-[640px] items-center gap-2 rounded-[8px] px-2.5 text-[13px] hover:bg-fill ${
        s.passed ? "bg-[rgba(48,194,91,.11)]" : myTurn ? "bg-attn-bg" : ""}`}>
        <span className="tag tag-accent">第 {lv.id} 关</span>
        <span className="truncate font-semibold">{lv.title}</span>
        <span className="truncate text-ink-2">· {lv.brief} → {TO[lv.to]}</span>
        <span className={`shrink-0 ${s.passed ? "text-[#1f8a3d]" : myTurn ? "font-semibold text-attn-ink" : "text-ink-2"}`}>{state}</span>
        <ChevronDown />
      </button>
    )}>
      {() => (
        <div className="flex w-[420px] flex-col gap-3 p-3 text-[13px] leading-5">
          <div>
            <p className="eyebrow">导演送来</p><p>{lv.brief}，到{TO[lv.to]}。</p>
            <p className="eyebrow mt-2">你要做的决定</p><p>{lv.decide}</p>
            {mine.map((x) => (
              <div key={x.session_id} className="mt-2 rounded-[8px] bg-attn-bg px-2.5 py-2">
                <p className="eyebrow">你扮的客户可以这样说</p>
                <p>「{x.text}」</p>
                <button className="btn btn-plain mt-1" disabled={!!busy}
                        onClick={() => run("…", api.addTurn(x.session_id, "customer", x.text).then(() => s))}>照这句说</button>
                <span className="ml-2 text-[12px] text-ink-3">也可以在客户面用自己的话说</span>
              </div>
            ))}
            {notes.map((x, i) => (
              <div key={i} className="mt-2 rounded-[8px] bg-attn-bg px-2.5 py-2">
                <p className="eyebrow">外部世界（模拟）</p><p>{x.text}</p>
              </div>
            ))}
            <p className="eyebrow mt-2">会用到</p><p className="text-ink-2">{lv.mechanism}</p>
            <p className="eyebrow mt-2">看点</p><p className="text-ink-2">{lv.point}</p>
            <p className="mt-2 text-[12px] text-ink-3">没人玩的岗位和客户由导演代办，前情里标「模拟」。业务时间 {s.now.slice(5, 16).replace("T", " ")} · 第 {s.round} 局</p>
            {s.error && <p role="alert" className="mt-1 text-[12px] text-danger">导演这一拍没做成：{s.error}</p>}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <button className="btn btn-plain" onClick={() => run("…", api.playControl({ paused: !s.paused }))}>{s.paused ? "继续" : "暂停"}</button>
            {SPEEDS.map(([v, label]) => (
              <button key={v} className={`btn btn-plain ${s.speed === v ? "!text-accent" : ""}`} onClick={() => run("…", api.playControl({ speed: v }))}>{label}</button>
            ))}
          </div>
          <div className="flex gap-1.5">
            <button className="btn btn-plain" disabled={!!busy}
                    onClick={() => confirm("重开本关：开新的一局，前面几关由导演代办补上，这一关从头来。确定吗？") && run("正在重开本关……", api.playRestart())}>重开本关</button>
            <button className="btn btn-primary" disabled={!s.passed || !!busy} onClick={() => run("…", api.playNext())}>下一关</button>
            <button className="btn btn-plain ml-auto" onClick={() => go("settle")}>看这一局的结算</button>
          </div>
          <div className="flex flex-col border-t border-sep pt-2">
            {s.levels.map((x, i) => (
              <p key={x.id} className={`flex gap-2 py-0.5 ${i === s.level ? "font-semibold" : i < s.level ? "text-ink-2" : "text-ink-3"}`}>
                <span className="w-4">{s.done.includes(x.id) ? "✓" : i === s.level ? "›" : ""}</span>
                <span>{x.id}. {x.title}</span>{!x.ready && <span className="text-[11.5px] text-ink-3">（待接上）</span>}
              </p>
            ))}
          </div>
        </div>
      )}
    </Popover>
  );
}
