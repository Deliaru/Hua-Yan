// 底部常驻输入胶囊，源自 JUE wp/e 的 web/src/components/ChatDock.tsx；材质按 Hark 输入框重做（圆角 24、高 48、白 55% 磨砂）。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";
import { Empty, Section } from "./Cards";

export function Dock({ placeholder, onSend, accessory, disabled }: {
  placeholder: string;
  onSend: (text: string) => Promise<unknown>;
  accessory?: React.ReactNode;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    onSend(t).then(() => setText("")).finally(() => setBusy(false));
  };
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex flex-col items-center gap-2 pb-6 pl-[376px] xl:pl-[396px]">
      {busy && <span className="pill anim-fade px-3 py-1 text-[13px] text-ink/60">处理中…</span>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="pill pointer-events-auto flex h-12 w-[560px] max-w-[92%] items-center gap-1 !rounded-[24px] pl-1.5 pr-1.5 shadow-[0_8px_40px_rgba(29,29,31,.12)]"
      >
        {accessory}
        <input
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          className="h-full flex-1 bg-transparent pl-3 text-[15px] outline-none placeholder:text-ink/40"
        />
        <button disabled={disabled || !text.trim() || busy}
                className="press flex h-9 w-9 items-center justify-center rounded-full bg-ink text-[16px] text-white transition-opacity disabled:opacity-20">↑</button>
      </form>
    </div>
  );
}

// 气泡：委托人 / 业务员在右侧实心 ink，其余在左侧白色格子。
export function Bubble({ who, mine, children }: { who?: string; mine?: boolean; children: React.ReactNode }) {
  return (
    <div className={`flex max-w-[82%] flex-col gap-1 ${mine ? "self-end items-end" : "self-start items-start"}`}>
      {who && <span className="meta px-1">{who}</span>}
      <div className={`rounded-[20px] px-4 py-2.5 text-[15px] leading-6 ${mine ? "bg-ink text-[#f9f9fa]" : "bg-white/75"}`}>
        {children}
      </div>
    </div>
  );
}

// 和自己的角色助手的对话（契约 ⑭）：消息、工具轨迹；输入走底部 Dock。只在助手运行时使用。
export function AgentConversation({ sessionId }: { sessionId: string | null }) {
  const { me } = useApp();
  const [showTrace, setShowTrace] = useState(false);
  const conv = useData(() => api.conversation(me, sessionId), [me, sessionId]);
  const steps = useData(() => (conv ? api.trace(conv.id) : Promise.resolve([])), [conv?.id]);
  return (
    <Section title="和我的助手"
             aside={conv && <button onClick={() => setShowTrace(!showTrace)} className="btn btn-soft !h-8 !px-3 !text-[13px]">
               工具轨迹 {steps?.length ?? 0}</button>}>
      {!conv?.messages.length && <Empty>用自然语言告诉助手要做什么；派给你的问题也会出现在这里。</Empty>}
      <div className="flex flex-col gap-3">
        {conv?.messages.map((m, i) =>
          m.role === "system" ? (
            <p key={i} className="meta self-center rounded-full bg-white/50 px-3 py-1">{m.text}</p>
          ) : (
            <Bubble key={i} mine={m.role === "principal"}>{m.text}</Bubble>
          ),
        )}
      </div>
      {showTrace && (
        <div className="anim-fade mt-4 flex flex-col gap-1.5">
          {steps?.map((s) => (
            <div key={s.step} className="cell text-[14px] leading-5">
              <span className="num mr-2 text-ink/40">{s.step}</span>
              <span className="font-medium">{s.tool ?? "回复"}</span>
              <span className="ml-2 text-ink/50">{Object.entries(s.args).map(([k, v]) => `${k}=${String(v)}`).join("，")}</span>
              {s.result_summary && <p className="mt-0.5 text-ink/70">→ {s.result_summary}</p>}
              {s.blocked.map((b) => <p key={b} className="mt-0.5 text-red-600">{b}：无权查看</p>)}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

export function AgentDock({ sessionId }: { sessionId: string | null }) {
  const { me, refresh, fail } = useApp();
  return <Dock placeholder="对助手说……" onSend={(t) => api.chat(me, t, sessionId).then(refresh, fail)} />;
}
