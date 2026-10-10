// 底部输入栏（窗口栏材质，与内容列对齐）、iMessage 式气泡、和角色助手的对话。
import { useRef, useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";
import { Group, pct } from "./Cards";
import { ArrowUp, ChevronRight } from "./Icons";

export interface Suggestion { key: string; label: string; text: string; p: number }

export function Dock({ placeholder, onSend, accessory, suggestions = [], onPick }: {
  placeholder: string;
  onSend: (text: string) => Promise<unknown>;
  accessory?: React.ReactNode;
  suggestions?: Suggestion[];
  onPick?: () => void;
}) {
  const { fail } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    onSend(t).then(() => setText("")).catch(fail).finally(() => setBusy(false));
  };
  return (
    <div className="bar fixed bottom-0 left-[272px] right-0 z-20 border-t border-sep">
      <div className="mx-auto max-w-[760px] px-10 py-3">
        {busy && <p role="status" className="mb-2 text-[13px] text-ink-2">处理中……</p>}
        {!!suggestions.length && (
          <div className="mb-2.5 flex flex-wrap items-center gap-2">
            <span className="text-[12px] text-ink-2">觉建议追问</span>
            {suggestions.map((s) => (
              <button key={s.key} disabled={busy} onClick={() => { setText(s.text); onPick?.(); input.current?.focus(); }}
                      className="flex h-7 items-center gap-2 rounded-full bg-white px-3 text-[13px] shadow-[0_0_0_.5px_rgba(0,0,0,.1),0_1px_1px_rgba(0,0,0,.04)] hover:bg-[#fafafa]">
                <span className="text-ink-2">{s.label}</span>{s.text}<span className="num text-[12px] font-semibold text-attn-ink">{pct(s.p)}</span>
              </button>
            ))}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-center gap-2.5">
          {accessory}
          <div className="flex h-9 flex-1 items-center rounded-[18px] bg-white pl-4 pr-1 shadow-[0_0_0_.5px_rgba(0,0,0,.14)]">
            <input ref={input} value={text} disabled={busy} aria-label={placeholder} onChange={(e) => setText(e.target.value)} placeholder={placeholder}
                   className="h-full flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-3" />
            <button aria-label="发送" disabled={!text.trim() || busy}
                    className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-white transition-opacity disabled:opacity-25">
              <ArrowUp />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// 气泡：我方（业务员 / 委托人）蓝底白字在右，对方浅灰在左；说话人只在切换时标注。
export function Bubble({ who, mine, children }: { who?: string; mine?: boolean; children: React.ReactNode }) {
  return (
    <div className={`flex max-w-[72%] flex-col ${mine ? "items-end self-end" : "items-start self-start"}`}>
      {who && <span className="mb-1 px-3 text-[12px] text-ink-2">{who}</span>}
      <div className={`rounded-[18px] px-3.5 py-2 text-[14px] leading-[21px] ${mine ? "bg-accent text-white" : "bg-[#e9e9eb]"}`}>
        {children}
      </div>
    </div>
  );
}

// 和自己的角色助手的对话（契约 ⑭）：消息平铺、工具轨迹可展开；输入走底部 Dock。只在助手运行时使用。
export function AgentConversation({ sessionId }: { sessionId: string | null }) {
  const { me, live } = useApp();
  const [showTrace, setShowTrace] = useState(false);
  const conv = useData(() => api.conversation(me, sessionId), [me, sessionId]);
  const steps = useData(() => (conv ? api.trace(conv.id) : Promise.resolve([])), [conv?.id]);
  return (
    <section className="flex flex-col gap-2">
      {!conv?.messages.length && live && <p className="text-[13px] text-ink-2">用自然语言告诉助手要做什么；派给你的问题也会出现在这里。</p>}
      {conv?.messages.map((m, i) =>
        m.role === "system" ? (
          <p key={i} className="my-1 self-center text-[12px] text-ink-2">{m.text}</p>
        ) : (
          <Bubble key={i} mine={m.role === "principal"}>{m.text}</Bubble>
        ),
      )}
      {!!steps?.length && (
        <button onClick={() => setShowTrace(!showTrace)} className="link mt-1 self-start">
          <ChevronRight open={showTrace} />工具轨迹 {steps.length} 步
        </button>
      )}
      {showTrace && (
        <Group>
          {steps?.map((s, i) => (
            <div key={i} className="row !items-start text-[13px] leading-5">
              <span className="num w-4 shrink-0 text-ink-3">{s.step}</span>
              <div className="min-w-0 flex-1">
                <p><span className="font-semibold">{s.tool ?? "回复"}</span>
                  <span className="ml-2 text-ink-2">{Object.entries(s.args).map(([k, v]) => `${k}=${String(v)}`).join("，")}</span></p>
                {s.result_summary && <p className="text-ink-2">→ {s.result_summary}</p>}
                {s.blocked.map((b) => <p key={b} className="text-danger">{b}：无权查看</p>)}
              </div>
            </div>
          ))}
        </Group>
      )}
    </section>
  );
}

export function AgentDock({ sessionId, suggestions }: { sessionId: string | null; suggestions?: Suggestion[] }) {
  const { me, refresh } = useApp();
  return <Dock placeholder="对助手说……" suggestions={suggestions}
               onSend={(t) => api.chat(me, t, sessionId).then(refresh)} />;
}
