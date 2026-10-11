// Agent 协作栏（右侧）与签字区里的 Agent 提议（契约 ⑭，REPLAN D21）。
// 对话常驻底部、历史可折叠；对话里没有签字按钮，Agent 提议的生效动作只出现在工作面签字区。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";
import type { AgentMessage } from "../types";
import { ArrowUp, ChevronRight } from "./Icons";
import { Group } from "./ui";

// 当前身份与这条会话（业务员）或收件箱（研发）的对话；批注按 target 挂到工作面对应位置
export function useConversation(sessionId: string | null) {
  const { me, agentOnline } = useApp();
  return useData(() => (agentOnline ? api.conversation(me, sessionId) : Promise.resolve(null)), [me, sessionId, agentOnline]);
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
  const { me, agentOnline, refresh } = useApp();
  const conv = useConversation(sessionId);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const history = (conv?.messages ?? []).filter((m) => m.role !== "system" || !m.target);
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
        <div className="dock overflow-hidden">
          <button type="button" onClick={() => setOpen(!open)} disabled={!history.length}
                  className="flex w-full items-center gap-2 px-3.5 pb-1 pt-2.5 text-left">
            <span className="text-[12px] font-semibold">与 Agent 协作</span>
            {external && <span className="text-[11px] text-ink-3">不会发给客户</span>}
            {!!history.length && <span className="ml-auto flex items-center gap-1 text-[11px] text-ink-2">
              {history.length} 条<ChevronRight open={open} /></span>}
          </button>
          {open && (
            <div className="anim-fade flex max-h-[240px] flex-col gap-1.5 overflow-y-auto border-b border-sep px-3.5 pb-2.5 pt-1">
              {history.map((m, i) => m.role === "system" ? (
                <p key={i} className="self-center text-[11px] text-ink-3">{m.text}</p>
              ) : (
                <p key={i} className={`max-w-[88%] rounded-[12px] px-2.5 py-1.5 text-[13px] leading-5 ${
                  m.role === "principal" ? "self-end bg-[#ececf0]" : "self-start bg-[#f6f6f8]"}`}>{m.text}</p>
              ))}
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-end gap-2 px-3.5 pb-2.5 pt-1">
            <textarea value={text} rows={2} aria-label="与 Agent 协作" disabled={!agentOnline || busy}
                      onChange={(e) => setText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                      placeholder={!agentOnline ? "Agent 离线" : external ? "如：把这句说得客气点" : "如：第 2 条加上不能影响色光"}
                      className="flex-1 resize-none bg-transparent text-[13px] leading-5 outline-none placeholder:text-ink-3" />
            <button aria-label="发给 Agent" disabled={!agentOnline || busy || !text.trim()}
                    className="mb-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-white transition-opacity disabled:opacity-15">
              <ArrowUp />
            </button>
          </form>
          {(busy || err) && <p role={err ? "alert" : "status"} className={`px-3.5 pb-2.5 text-[12px] ${err ? "text-danger" : "text-ink-2"}`}>
            {err ?? "Agent 处理中……"}</p>}
        </div>
      </div>
    </aside>
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
