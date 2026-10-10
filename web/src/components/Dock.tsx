// 底部常驻的胶囊输入框，样式取自 JUE wp/e 的 web/src/components/ChatDock.tsx。
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
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex flex-col items-center gap-2 pb-5 pl-[340px] xl:pl-[380px]">
      {busy && <span className="pill anim-fade px-3 py-1 text-[12px] text-black/60">处理中…</span>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="pointer-events-auto flex w-[640px] max-w-[92%] items-center gap-2 rounded-full bg-white/60 py-1.5 pl-2 pr-1.5 shadow-[0_8px_30px_rgba(29,29,31,.10)] ring-1 ring-white/50 backdrop-blur-2xl"
      >
        {accessory}
        <input
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          className="ml-3 flex-1 bg-transparent text-[14px] outline-none placeholder:text-black/55"
        />
        <button disabled={disabled || !text.trim() || busy}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-white disabled:opacity-30">↑</button>
      </form>
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
             aside={conv && <button onClick={() => setShowTrace(!showTrace)} className="chip">工具轨迹 {steps?.length ?? 0}</button>}>
      {!conv?.messages.length && <Empty>用自然语言告诉助手要做什么；派给你的问题也会出现在这里。</Empty>}
      <div className="flex flex-col gap-2">
        {conv?.messages.map((m, i) =>
          m.role === "system" ? (
            <p key={i} className="text-center text-[12px] text-black/55">🔔 {m.text}</p>
          ) : (
            <p key={i} className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-[14px] leading-6 ${
              m.role === "principal" ? "self-end bg-ink text-white" : "self-start bg-white"}`}>{m.text}</p>
          ),
        )}
      </div>
      {showTrace && (
        <div className="cell anim-fade mt-3 p-3">
          {steps?.map((s) => (
            <div key={s.step} className="py-1 text-[13px] leading-5">
              <span className="num mr-2 text-black/55">{s.step}</span>
              <span className="chip mr-1.5">{s.tool ?? "回复"}</span>
              <span className="text-black/60">{Object.entries(s.args).map(([k, v]) => `${k}=${String(v)}`).join("，")}</span>
              {s.result_summary && <span> → {s.result_summary}</span>}
              {s.blocked.map((b) => <p key={b} className="ml-6 text-red-600">{b}：无权查看</p>)}
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
