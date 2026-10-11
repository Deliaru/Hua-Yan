// 处理过程：点一个按钮后，觉、模型、Jev、各角色 Agent 依次做了什么、用了多久（服务端会话层记录，处理中轮询）。
// 别人的 Agent 只显示「谁、做什么、用时」，工具名由服务端去掉；回放时模型与 Jev 是瞬间返回，括号里标录制时的用时。
import { useEffect, useState, useSyncExternalStore } from "react";
import { api, writes } from "../api";
import { useApp, useLabels, FAMILY, PREPARING } from "../ctx";
import type { Activity, ProgressEvent } from "../types";
import { ChevronDown } from "./Icons";

const PATH: Record<string, string> = {
  sessions: "新建客户会话", turn: "对话发言", recommend: "推荐", escalate: "升级", "reuse/adopt": "采用现成产品",
  "reuse/decline": "不采用现成产品", "reuse-note": "修改给客户的说明", merge: "合并同类需求", accept: "接单", return: "退回",
  "req-item": "修改需求条目", confirm: "确认化学要点", contribute: "沉淀知识", "market-eval": "录入客户评价",
  points: "封存 / 放出", sheet: "保存说明书", release: "发布", trial: "录入试样结果", "decrypt/request": "申请解密",
  "decrypt/decide": "解密审批", "reply-draft": "保存回复草稿", "escalate-note": "保存升级说明", resolve: "签字",
  "agents/chat": "和 Agent 对话", "agents/approve": "确认 Agent 提议", "agents/reject": "拒绝 Agent 提议",
  reset: "重置进度", "demo/load": "载入检查点",
};
const CALLER: Record<string, string> = {
  "agent:extract": "把客户原话抽成需求卡", "agent:l1_answer": "L1 回答客户", "jev:match": "Jev 匹配产品", "jev:disclose": "Jev 选择披露版本",
};
const TOOL: Record<string, string> = {
  search_knowledge: "查知识", get_knowledge: "读知识全文", list_my_questions: "看待办问题", save_reply_draft: "写回复草稿",
  save_escalate_note: "写升级说明", get_need_card: "看需求卡", request_decrypt: "提议申请解密", get_session: "读客户原话",
  match_translations: "匹配转化对照", find_products: "查候选产品", get_requirement: "读需求单", my_contributions: "查贡献积分",
  propose_reuse: "写复用建议", draft_product_need: "起草产品需求（L2）", propose_merge: "写合并建议", edit_item: "改需求条目",
  remove_item: "删需求条目", set_direction: "改产品方向", edit_reuse_note: "改给客户的说明", draft_chem_need: "起草化学语言（L3）",
  package_sheet: "包装说明书", edit_sheet: "改说明书", leak_check: "泄密检查", confirm_translation: "提议确认化学要点",
  save_contribution_draft: "写沉淀草稿", contribute_translation: "提议沉淀知识", save_points_draft: "起草封存 / 放出",
  set_public_points: "提议确认对外要点", record_trial: "提议录入试样",
};
const ROLE: Record<string, string> = { sales: "业务员", rd: "研发", pm: "产品经理" };

const sec = (ms: number) => (ms < 1000 ? `${Math.max(1, Math.round(ms))}ms` : `${(ms / 1000).toFixed(1)}s`);
const callerText = (c = "") => CALLER[c] ?? (c.startsWith("jev:") ? "Jev 判断" : "思考");

// ── 处理中的写操作：工具栏轮询，全页共享 ───────────────────────
let current: { act: Activity | null; at: number } = { act: null, at: 0 };
const subs = new Set<() => void>();
const publish = (act: Activity | null) => { current = { act, at: Date.now() }; subs.forEach((fn) => fn()); };
export const useActivity = () => useSyncExternalStore((fn) => { subs.add(fn); return () => { subs.delete(fn); }; }, () => current);
export const useWriting = () => useSyncExternalStore(writes.subscribe, writes.count) > 0;

function usePoll(me: string) {
  const writing = useWriting();
  useEffect(() => {
    const load = () => api.progress(me).then(publish, () => undefined);
    load();
    if (!writing) return;
    const id = setInterval(load, 700);
    return () => clearInterval(id);
  }, [writing, me]);
  return writing;
}

// 让进行中的计时每 0.2 秒走一次
function useNow(on: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!on) return;
    const id = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(id);
  }, [on]);
  return now;
}

// ── 把事件整理成行 ─────────────────────────────────────────
interface Row { depth: 0 | 1; state: "done" | "run" | "fail"; text: string; meta: string }

export function buildRows(events: ProgressEvent[], viewer: string, name: (id: string) => string, liveMs: number | null): Row[] {
  const rows: Row[] = [];
  const open = new Map<string, { row: Row; t: number }>();     // 等待返回的模型 / Jev 调用
  // mine = 当前查看者自己的 Agent：逐步列出；别人的 Agent 只在标题行写进度与汇总
  let agent: { row: Row; t: number; steps: number; tools: number; recorded: number; cached: boolean; mine: boolean; wait: { model: string; t: number } | null } | null = null;
  let jue: Row | null = null;
  let jueN = 0, jueCount = 0, jueMs = 0;
  let family: Record<string, string> = {};
  const took = (e: ProgressEvent) => (e.cached ? `录制时 ${sec(e.latency_ms ?? 0)}` : sec(e.latency_ms ?? 0));
  for (const e of events) {
    const depth = agent ? 1 : 0;
    if (e.kind === "jue") {
      jueCount += 1; jueN += e.n ?? 0; jueMs += e.latency_ms ?? 0;
      if (!jue) { jue = { depth: 0, state: "done", text: "", meta: "" }; rows.push(jue); }
      jue.text = `觉 · 判断 ${jueCount} 次，共 ${jueN} 个决策点`;
      jue.meta = `Jue-K 本地 · 不调用大模型 · ${sec(jueMs)}`;
    } else if (e.kind === "dispatch") {
      family = { ...family, [e.actor!]: e.family! };
    } else if (e.kind === "agent_start") {
      const f = family[e.actor!];
      const who = e.actor === "pm:agent" ? "产品经理 Agent" : e.actor === viewer ? "你的 Agent" : `${name(e.actor!)}的 Agent`;
      const what = f ? `觉派单 · ${PREPARING[f]?.replace(/^正在/, "") ?? `准备「${FAMILY[f] ?? f}」`}` : "按你的指令处理";
      const row: Row = { depth: 0, state: "run", text: `${who} · ${what}`, meta: "" };
      rows.push(row);
      agent = { row, t: e.t, steps: 0, tools: 0, recorded: 0, cached: false, mine: e.actor === viewer, wait: null };
      delete family[e.actor!];
    } else if (e.kind === "agent_end" && agent) {
      const wall = (e.t - agent.t) * 1000;
      agent.row.state = "done";
      agent.row.meta = `${agent.steps} 步 · ${agent.tools} 次工具 · ${agent.cached ? `录制时 ${sec(agent.recorded)}` : sec(wall)}`;
      agent = null;
    } else if (agent && !agent.mine && e.kind === "llm_start") {
      agent.wait = { model: e.model!, t: e.t };
    } else if (agent && !agent.mine && e.kind === "llm") {
      agent.wait = null; agent.recorded += e.latency_ms ?? 0; agent.cached ||= !!e.cached;
    } else if (e.kind === "llm_start" || e.kind === "s1_start") {
      // Jev 不走 OneJev 而走大模型时是降级，照实写（铁律 6）
      const jev = e.caller?.startsWith("jev:");
      const label = e.kind === "s1_start" ? `${callerText(e.caller)}（OneJev）` : agent ? `思考 · 第 ${agent.steps + 1} 步`
        : `${callerText(e.caller)}${jev ? "（大模型降级）" : ""}`;
      const row: Row = { depth, state: "run", text: label, meta: `等待 ${e.model} 返回` };
      rows.push(row);
      open.set(`${e.kind}:${e.caller}`, { row, t: e.t });
    } else if (e.kind === "llm" || e.kind === "s1") {
      const key = `${e.kind}_start:${e.caller}`;
      const o = open.get(key);
      if (!o) continue;
      open.delete(key);
      o.row.state = e.ok === false ? "fail" : "done";
      o.row.meta = `${e.model} · ${e.ok === false ? "失败" : took(e)}`;
      if (agent && e.kind === "llm") { agent.recorded += e.latency_ms ?? 0; agent.cached ||= !!e.cached; }
    } else if (e.kind === "step" && agent) {
      agent.steps = Math.max(agent.steps, e.step ?? 0);
      if (!("tool" in e)) { agent.tools += 1; continue; }      // 别人的 Agent：不给工具名，只计数
      if (!e.tool) continue;                                    // 最后一步是回复，不是工具
      agent.tools += 1;
      const flag = e.blocked ? " · 有内容被权限拦截" : e.pending ? " · 已挂起，等你确认" : e.ok === false ? " · 被拒绝" : "";
      rows.push({ depth: 1, state: e.ok === false ? "fail" : "done", text: `调用工具：${TOOL[e.tool] ?? e.tool}${flag}`, meta: "" });
    }
  }
  // 仍在等待的那一步显示已等多久
  if (liveMs != null) for (const { row, t } of open.values()) row.meta += ` · 已等 ${sec(Math.max(0, liveMs - t * 1000))}`;
  if (agent && liveMs != null) agent.row.meta = `第 ${agent.steps + 1} 步${agent.wait ? ` · 等待 ${agent.wait.model} 返回` : ""} · 已用 ${sec(liveMs - agent.t * 1000)}`;
  return rows;
}

export function recordedMs(events: ProgressEvent[]) {
  const cached = events.filter((e) => (e.kind === "llm" || e.kind === "s1") && e.cached);
  return cached.length ? cached.reduce((s, e) => s + (e.latency_ms ?? 0), 0) : null;
}

export function ProcessRows({ rows, compact }: { rows: Row[]; compact?: boolean }) {
  return (
    <ol className="flex flex-col">
      {rows.map((r, i) => (
        <li key={i} className={`flex items-start gap-2 py-[3px] text-[12.5px] leading-[18px] ${r.depth ? "pl-5" : ""}`}>
          <span className="mt-[3px] flex w-3 shrink-0 justify-center">
            {r.state === "run" ? <i className="spinner" /> : r.state === "fail"
              ? <span className="text-[11px] font-bold text-danger">!</span> : <span className="text-[11px] text-ink-2">✓</span>}
          </span>
          <span className={`min-w-0 flex-1 ${compact ? "text-ink" : r.depth ? "text-ink-2" : "font-semibold"}`}>
            {r.text}{compact && r.meta && <span className="block text-[11.5px] text-ink-2 num">{r.meta}</span>}</span>
          {!compact && r.meta && <span className="shrink-0 text-right text-[11.5px] text-ink-2 num">{r.meta}</span>}
        </li>
      ))}
    </ol>
  );
}

// ── 工具栏：处理中自动展开，完成后收成一行摘要 ──────────────────
export function ActivityMenu() {
  const { me, meta } = useApp();
  const name = useLabels().name;
  const writing = usePoll(me);
  const { act, at } = useActivity();
  const [open, setOpen] = useState(false);
  const [auto, setAuto] = useState(false);
  const now = useNow(writing);
  // 处理超过 0.8 秒自动展开；自动展开的在完成 3 秒后收起，手动打开的不收
  useEffect(() => {
    if (!writing) return;
    const id = setTimeout(() => { setOpen(true); setAuto(true); }, 800);
    return () => clearTimeout(id);
  }, [writing]);
  useEffect(() => {
    if (writing || !auto) return;
    const id = setTimeout(() => { setOpen(false); setAuto(false); }, 3000);
    return () => clearTimeout(id);
  }, [writing, auto]);
  if (!act && !writing) return null;

  const live = act?.running ? act.elapsed_ms + (now - at) : null;
  const rows = act ? buildRows(act.events, me, name, live) : [];
  const llm = act?.events.filter((e) => e.kind === "llm").length ?? 0;
  const agents = act?.events.filter((e) => e.kind === "agent_start").length ?? 0;
  const rec = act && !act.running ? recordedMs(act.events) : null;
  const label = act ? PATH[act.path.replace("/api/", "")] ?? act.path : "";
  const waiting = writing && !act?.running;            // 已发出，服务端还没开始记录这一次
  const head = writing ? `正在处理「${label || "……"}」` : `${act?.error ? "未完成" : "已完成"}「${label}」`;
  const summary = [llm && `${llm} 次模型调用`, agents && `${agents} 个 Agent`].filter(Boolean).join(" · ");
  const time = live != null ? sec(live) : act ? sec(act.elapsed_ms) : "";

  return (
    <div className="relative">
      <button onClick={() => { setOpen(!open); setAuto(false); }}
              className={`flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[12px] hover:bg-fill ${writing ? "bg-[rgba(10,108,223,.08)]" : ""}`}>
        {writing ? <i className="spinner" /> : <span className="text-ink-2">✓</span>}
        <span className={writing ? "font-semibold text-accent" : "text-ink-2"}>
          {writing ? `处理中 ${time}` : rec != null ? `录制时 ${sec(rec)}` : time}</span>
        <span className="text-ink-3"><ChevronDown /></span>
      </button>
      {open && (
        <div className="popover anim-fade left-0 top-[34px] w-[440px] p-0">
          <div className="border-b border-sep px-3.5 pb-2 pt-2.5">
            <div className="flex items-baseline gap-2">
              <p className="flex-1 text-[13.5px] font-semibold">{head}</p>
              <span className="text-[12px] text-ink-2 num">{rec != null ? `录制时 ${sec(rec)}` : time}</span>
            </div>
            <p className="mt-0.5 text-[12px] text-ink-2">
              {summary || "没有调用大模型"}{meta.mode.llm_model && llm ? ` · ${meta.mode.llm_model}` : ""}
              {rec != null && ` · 本次回放 ${time}`}</p>
          </div>
          <div className="max-h-[60vh] overflow-y-auto px-3.5 py-2">
            {waiting && !rows.length ? <p className="py-1 text-[12.5px] text-ink-2">已发出，等待服务开始处理……</p> : <ProcessRows rows={rows} />}
            {act?.error && !writing && <p className="mt-1.5 text-[12px] text-danger">{act.error}</p>}
          </div>
          <p className="border-t border-sep px-3.5 py-2 text-[11.5px] leading-4 text-ink-2">
            {meta.status.replay ? "录制回放：步骤是录制时的真实过程，瞬间返回；「录制时」是当时的用时。" : "按发生顺序列出；"}
            别人的 Agent 只显示在做什么和用时，不显示内容。</p>
        </div>
      )}
    </div>
  );
}

// ── Agent 对话里每轮回复的过程（可展开）────────────────────────
export function RunLine({ events, ms }: { events: ProgressEvent[]; ms: number }) {
  const { me } = useApp();
  const name = useLabels().name;
  const [open, setOpen] = useState(false);
  const steps = Math.max(0, ...events.filter((e) => e.kind === "step").map((e) => e.step ?? 0));
  const tools = events.filter((e) => e.kind === "step" && e.tool).map((e) => TOOL[e.tool!] ?? e.tool!);
  const rec = recordedMs(events);
  return (
    <div className="self-start pl-1">
      <button onClick={() => setOpen(!open)} className="text-left text-[11.5px] leading-4 text-ink-2 hover:text-ink">
        {steps} 步 · {rec != null ? `录制时 ${sec(rec)}` : sec(ms)}
        {tools.length ? ` · ${[...new Set(tools)].slice(0, 3).join("、")}${new Set(tools).size > 3 ? " 等" : ""}` : ""} {open ? "▾" : "▸"}
      </button>
      {open && <div className="mt-1 rounded-[8px] bg-[#f6f6f8] px-2 py-1">
        <ProcessRows compact rows={buildRows(events, me, name, null).filter((r) => r.depth === 1)} /></div>}
    </div>
  );
}

// 对话框底部的进行中提示：当前在做的那一步
export function LiveLine() {
  const { me } = useApp();
  const name = useLabels().name;
  const { act, at } = useActivity();
  const now = useNow(!!act?.running);
  if (!act?.running) return <>Agent 处理中……</>;
  const live = act.elapsed_ms + (now - at);
  const rows = buildRows(act.events, me, name, live);
  const last = [...rows].reverse().find((r) => r.state === "run") ?? rows[rows.length - 1];
  return <>Agent 处理中 · {sec(live)}{last ? ` · ${last.text}${last.meta ? `（${last.meta}）` : ""}` : ""}</>;
}
