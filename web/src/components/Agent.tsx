// Agent 协作栏（右侧）与签字区里的 Agent 提议（契约 ⑭，REPLAN D21）。
// 对话常驻底部、历史可折叠；对话里没有签字按钮，Agent 提议的生效动作只出现在工作面签字区。
import { useState } from "react";
import { api } from "../api";
import { useGuideArg } from "./Guide";
import { useApp, useData } from "../ctx";
import type { AgentMessage, AgentRun, MemoryEntry } from "../types";
import { ArrowUp, ChevronRight } from "./Icons";
import { Group } from "./ui";
import { LiveLine, RunLine } from "./Process";

// 当前身份与这条会话（业务员）或收件箱（研发）的对话；批注按 target 挂到工作面对应位置。
// v8：thread = 工作面打开的对象，助手收件箱按对象分段时取这一段
export function useConversation(sessionId: string | null, thread: string | null = null) {
  const { me, agentOnline } = useApp();
  return useData(() => (agentOnline ? api.conversation(me, sessionId, thread) : Promise.resolve(null)),
                 [me, sessionId, thread, agentOnline]);
}

export function notesFor(messages: AgentMessage[] | undefined, target: string) {
  return (messages ?? []).filter((m) => m.target === target);
}

// 挂在条目旁的批注
export function Notes({ notes }: { notes: AgentMessage[] }) {
  if (!notes.length) return null;
  return (
    <div className="mt-1.5 flex flex-col gap-1">
      {notes.map((m, i) => (
        <p key={i} className="rounded-[6px] bg-[rgba(118,118,128,.08)] px-2 py-1 text-[12px] leading-[18px] text-ink-2">
          <span className="font-semibold text-ink">Agent</span>　{m.text}
        </p>
      ))}
    </div>
  );
}

export function AgentPanel({ sessionId, focus, external, title, children }: {
  sessionId: string | null; focus: string | null; external?: boolean; title: string; children?: React.ReactNode;
}) {
  const { me, agentOnline, refresh, meta } = useApp();
  const conv = useConversation(sessionId, focus);
  // 每轮回复的过程（步骤、工具、用时），按回复在对话里的位置对应
  const runs = useData(() => (conv ? api.agentProcess(conv.id, me) : Promise.resolve({} as Record<string, AgentRun>)), [conv?.id, me]);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const scripted = useGuideArg("chat");   // 回放部署：台词里人要对 Agent 说的话
  // 系统消息是派单记录（带内部编号）；带 target 的批注已挂在工作面上，历史里只留人与 Agent 的对话
  const history = (conv?.messages ?? []).map((m, i) => ({ ...m, i })).filter((m) => m.role !== "system");
  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setErr(null);
    api.chat(me, t, sessionId, focus).then(() => { setText(""); setOpen(true); refresh(); },
      (e) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
  };
  return (
    <aside className="inspector fixed bottom-0 right-0 top-[52px] z-10 flex w-[372px] flex-col border-l border-sep">
      <div className="flex items-center gap-2 px-5 pb-1 pt-4">
        <span className="eyebrow">{title}</span>
      </div>
      <div className="flex-1 overflow-y-auto px-5 pb-6 pt-3">
        <div className="flex flex-col gap-5">{children}</div>
      </div>
      <div className="px-4 pb-4">
        <AgentMemory />
        <AgentTip />
        <div className="dock overflow-hidden">
          <button type="button" onClick={() => setOpen(!open)} disabled={!history.length}
                  className="flex w-full items-center gap-2 px-3.5 pb-1 pt-2.5 text-left">
            <span className="shrink-0 whitespace-nowrap text-[12px] font-semibold">与 Agent 协作</span>
            {meta.mode.llm_model && <span className="min-w-0 truncate text-[11px] text-ink-2" title="Agent 使用的大模型">
              {meta.mode.llm_model}{meta.status.replay ? " · 录制" : ""}</span>}
            {external && <span className="shrink-0 whitespace-nowrap text-[11px] text-ink-3">不发给客户</span>}
            {!!history.length && <span className="ml-auto flex shrink-0 items-center gap-1 whitespace-nowrap text-[11px] text-ink-2">
              {history.length} 条<ChevronRight open={open} /></span>}
          </button>
          {open && (
            <div className="anim-fade flex max-h-[240px] flex-col gap-1.5 overflow-y-auto border-b border-sep px-3.5 pb-2.5 pt-1">
              {history.map((m) => (
                <div key={m.i} className="contents">
                  <p className={`max-w-[88%] rounded-[12px] px-2.5 py-1.5 text-[13px] leading-5 ${
                    m.role === "principal" ? "self-end bg-[#ececf0]" : "self-start bg-[#f6f6f8]"}`}>{m.text}</p>
                  {m.role === "assistant" && runs?.[m.i] && <RunLine {...runs[m.i]} />}
                </div>
              ))}
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-end gap-2 px-3.5 pb-2.5 pt-1">
            <textarea value={text} rows={2} aria-label="与 Agent 协作" disabled={!agentOnline || busy}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                      placeholder={!agentOnline ? "Agent 离线" : external ? "如：把这句说得客气点" : "如：第 2 条加上不能影响色光"}
                      className="flex-1 resize-none bg-transparent text-[13px] leading-5 outline-none placeholder:text-ink-3" />
            {scripted && text !== scripted && (
              <button type="button" className="chip glow mb-0.5 shrink-0" onClick={() => setText(scripted)}>演示自动填入</button>
            )}
            <button aria-label="发给 Agent" disabled={!agentOnline || busy || !text.trim()}
                    className={`${scripted && text === scripted ? "glow" : ""} mb-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-white transition-opacity disabled:opacity-15`}>
              <ArrowUp />
            </button>
          </form>
          {(busy || err) && <p role={err ? "alert" : "status"} className={`px-3.5 pb-2.5 text-[12px] ${err ? "text-danger" : "text-ink-2"}`}>
            {err ?? <LiveLine />}</p>}
        </div>
      </div>
    </aside>
  );
}

// v8：助手的记忆（助手自己记、每天收工归纳）。人能看、能删；没有记忆时不显示。
const KIND: Record<MemoryEntry["kind"], string> = { habit: "习惯", fact: "事实", lesson: "教训" };

function AgentMemory() {
  const { me, agentOnline, refresh, fail } = useApp();
  const memory = useData(() => (agentOnline ? api.memory(me) : Promise.resolve([] as MemoryEntry[])), [me, agentOnline]);
  const [open, setOpen] = useState(false);
  if (!memory?.length) return null;
  return (
    <div className="mb-2.5 rounded-[10px] bg-[rgba(118,118,128,.06)] px-3 py-2 text-[12px] leading-[18px]">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-1 text-left font-semibold">
        Agent 记得的 {memory.length} 条<ChevronRight open={open} />
      </button>
      {open && <ul className="mt-1 flex max-h-[180px] flex-col gap-1 overflow-y-auto">
        {memory.map((m) => (
          <li key={m.id} className="flex items-start gap-2 text-ink-2" title={m.why}>
            <span className="shrink-0 text-ink-3">{KIND[m.kind]}</span>
            <span className="flex-1">{m.text}</span>
            <button type="button" className="shrink-0 text-accent" onClick={() => api.forget(m.id, me).then(refresh, fail)}>删除</button>
          </li>
        ))}
      </ul>}
    </div>
  );
}

// 常驻的小提示：觉派单之外，Agent 也是随时可用的常规助手（看到的正好是本人能看的那一层）。不需要点。
const CAN: Record<string, string> = {
  sales: "查说明书和用法、帮你理解客户需求（已知什么、还缺什么）、起草追问话术和升级说明；够不着的知识会告诉你该找哪位研发。",
  rd: "调取客户逐轮原话与需求单、检索案例 / 机理 / 实验记录、和你一起分析需求，逐条起草和修改化学语言。",
};

function AgentTip() {
  const { role, meta } = useApp();
  if (!CAN[role]) return null;
  return (
    <div className="agent-tip mb-2.5 rounded-[10px] px-3 py-2 text-[12px] leading-[18px] text-ink-2">
      <p className="mb-0.5 font-semibold text-ink">你的 Agent 随时可用，不只等觉派单</p>
      {CAN[role]}<span className="text-ink-3"> Agent 只起草，生效靠你签字。{meta.status.replay && "当前为演示模式，只能发送台词里的话（点「演示自动填入」）。"}</span>
    </div>
  );
}

// 签字区：Agent 在对话里提议的生效动作。只显示内容本身，确认 / 拒绝调 agents/approve / reject。
export function PendingActions() {
  const { me, agentOnline, refresh, fail } = useApp();
  const actions = useData(() => (agentOnline ? api.pending(me) : Promise.resolve([])), [me, agentOnline]);
  const [busy, setBusy] = useState<string | null>(null);
  const pending = (actions ?? []).filter((a) => a.status === "pending");
  if (!pending.length) return null;
  const decide = (id: string, ok: boolean) => {
    setBusy(id);
    (ok ? api.approve(id, me) : api.reject(id, me)).then(refresh, fail).finally(() => setBusy(null));
  };
  return (
    <Group title={<span className="text-attn-ink">Agent 提议 · 待你确认</span>} foot="确认后才生效；谁确认，谁负责。">
      {pending.map((a) => (
        <div key={a.id} className="row attn-edge">
          <p className="min-w-0 flex-1 text-[14px] leading-[21px]">{a.summary}</p>
          <button disabled={busy === a.id} onClick={() => decide(a.id, false)} className="btn btn-plain">拒绝</button>
          <button disabled={busy === a.id} onClick={() => decide(a.id, true)} className="btn btn-primary">确认</button>
        </div>
      ))}
    </Group>
  );
}
