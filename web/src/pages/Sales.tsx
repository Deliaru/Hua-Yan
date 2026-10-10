// 业务员工作台（L1）：和业务员助手对话；离线时直接录入客户与业务员发言，走规则抽取、觉与 Mock Jev。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { SessionDetail } from "../types";
import { Empty, Layout, PageHead, PendingStack, QuestionCard, RailTitle, RecCard, Section } from "../components/Cards";
import { Segmented } from "../components/Controls";
import { AgentConversation, AgentDock, Dock } from "../components/Dock";

const SESSION_STATUS: Record<string, string> = { open: "进行中", recommended: "已推荐", escalated: "已升级" };

export function Sales() {
  const { meta, me, live, refresh, fail } = useApp();
  const L = useLabels();
  const customers = meta.actors.filter((a) => a.role === "customer");
  const [customer, setCustomer] = useState(customers[0].id);
  const [chosen, choose] = useState<string | null>(null);
  const [speaker, setSpeaker] = useState<"customer" | "sales">("customer");
  const all = useData(() => api.sessions(), []);
  const mine = (all ?? []).filter((s) => s.sales_id === me).reverse();
  const sid = mine.find((s) => s.id === chosen)?.id ?? mine[0]?.id ?? null;
  const detail = useData(() => (sid ? api.session(sid, me) : Promise.resolve(null)), [sid, me]);

  const start = () => api.startSession(customer, me).then((s) => {
    choose(s.id);
    refresh();
  }, fail);

  const rail = (
    <>
      <RailTitle>客户会话</RailTitle>
      {mine.map((s) => (
        <button key={s.id} onClick={() => choose(s.id)}
                className={`glass glass-hover px-4 py-3 text-left ${s.id === sid ? "ring-2 ring-ink/80" : ""}`}>
          <p className="text-[15px]">{L.name(s.customer_id)}</p>
          <p className="mt-1 flex gap-1.5"><span className="chip">{s.id}</span><span className="chip">{L.phen(s.phenomenon)}</span>
            <span className="chip">{SESSION_STATUS[s.status] ?? s.status}</span></p>
        </button>
      ))}
      <div className="glass p-4">
        <p className="mb-2 text-[13px] text-black/60">新建客户会话</p>
        <Segmented size="sm" wrap value={customer} onChange={setCustomer} items={customers.map((c) => [c.id, c.name] as const)} />
        <button onClick={start} className="mt-3 rounded-full bg-ink px-4 py-1 text-[13px] text-white">新建</button>
      </div>
      {detail?.ask_back.map((q) => <QuestionCard key={q.id} q={q} />)}
      <PendingStack />
    </>
  );

  return (
    <Layout rail={rail}>
      <PageHead kicker={sid ? `${sid} · ${L.name(mine.find((s) => s.id === sid)?.customer_id)}` : "业务员工作台 · L1"}
                title={detail ? L.phen(detail.phenomenon) : "选择或新建客户会话"} />
      {!live && (
        <div className="glass mt-4 p-4 text-[14px] leading-6 text-black/70">
          角色助手离线：直接在底部输入客户和业务员的发言，系统照常抽取、提示追问、推荐或升级。
        </div>
      )}
      {detail && <SessionBody d={detail} />}
      {sid && (live ? <AgentDock sessionId={sid} /> : (
        <Dock
          placeholder={speaker === "customer" ? "客户说……" : "业务员说……"}
          onSend={(t) => api.addTurn(sid, speaker, t).then(refresh, fail)}
          accessory={<Segmented size="sm" value={speaker} onChange={setSpeaker}
                                items={[["customer", "客户"], ["sales", "业务员"]] as const} />}
        />
      ))}
    </Layout>
  );
}

function SessionBody({ d }: { d: SessionDetail }) {
  const { live } = useApp();
  const L = useLabels();
  const v = d.view;
  const replies = (turnId: string) => v.replies.filter((r) => r.turn_id === turnId);
  return (
    <>
      {live ? <AgentConversation sessionId={v.session_id} /> : (
        <Section title="对话">
          {!v.turns.length && <Empty>还没有发言。客户只说宏观现象即可，比如「染完以后布面深一块浅一块」。</Empty>}
          <div className="flex flex-col gap-2">
            {v.turns.map((t) => (
              <div key={t.id} className="flex flex-col gap-2">
                <p className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-[14px] leading-6 ${
                  t.speaker === "customer" ? "self-start bg-white" : "self-end bg-ink text-white"}`}>
                  <span className="mr-2 text-[12px] opacity-60">{t.speaker === "customer" ? "客户" : "业务员"}</span>{t.text}
                </p>
                {replies(t.id).map((r, i) => (
                  <div key={i} className="cell self-start max-w-[85%] px-3.5 py-2 text-[14px] leading-6">
                    <span className="mr-2 text-[12px] text-black/55">知识助手</span>{r.text}
                    {r.blocked && <span className="chip ml-2 bg-red-500/10 text-red-600">研发保密 · 已拦截</span>}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Section>
      )}

      {!!v.hints.length && (
        <Section title="觉的追问提示">
          <div className="grid gap-2 sm:grid-cols-2">
            {v.hints.map((h) => (
              <div key={h.slot} className="cell p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="tag">{h.label}</span>
                  <span className="num text-[15px] font-semibold text-accent">{h.p_need.toFixed(2)}</span>
                </div>
                <p className="mt-1.5 text-[14px] leading-6">{h.ask_text}</p>
                <p className="mt-1 text-[12px] text-black/55">{h.scored_by} 打分</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="场景需求卡" aside={<span className="chip">L1 · 绑定原话</span>}>
        <p className="text-[14px] leading-6">
          <span className="text-black/55">现象　</span>{L.phen(d.phenomenon)}
          {d.phenomenon_quote && <span className="chip ml-2">原话「{d.phenomenon_quote}」</span>}
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {v.slots.map((s) => (
            <div key={s.slot} className="cell p-3">
              <p className="text-[12px] text-black/55">{L.slot(s.slot)}</p>
              <p className="mt-0.5 text-[20px] font-medium">{s.value ?? "客户不清楚"}</p>
              <p className="mt-1 text-[12px] text-black/55">原话「{s.quote}」</p>
            </div>
          ))}
        </div>
        {!v.slots.length && <Empty>尚未抽取到条件。</Empty>}
      </Section>

      <div className="mt-3">
        {v.card ? <RecCard card={v.card} /> : v.status === "escalated" && (
          <div className="glass p-4 text-[14px] leading-6">
            <span className="tag mr-1.5 !text-accent">已升级</span>
            没有适用的现有产品，已转给产品经理处理（{v.escalation_question_id}）。
          </div>
        )}
      </div>
    </>
  );
}
