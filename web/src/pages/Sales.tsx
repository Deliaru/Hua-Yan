// 业务员工作台（L1）：和业务员助手对话；离线时直接录入客户与业务员发言，走规则抽取、觉与 Mock Jev。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { SessionDetail } from "../types";
import { Empty, Layout, PageHead, PendingStack, QuestionCard, RailTitle, RecCard, Section } from "../components/Cards";
import { Segmented } from "../components/Controls";
import { AgentConversation, AgentDock, Bubble, Dock } from "../components/Dock";

const SESSION_STATUS: Record<string, [string, string]> = {
  open: ["进行中", ""], recommended: ["已推荐", ""], escalated: ["已升级", ""],
};
const short = (name: string) => name.replace("（模拟）", "");

export function OfflineBanner({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="card flex items-center gap-3 !py-4">
      <span className="tag tag-red shrink-0">离线</span>
      <p className="flex-1 text-[15px] leading-6 text-ink/70">{children}</p>
      {action}
    </div>
  );
}

export function Sales() {
  const { meta, me, live, refresh, fail } = useApp();
  const L = useLabels();
  const customers = meta.actors.filter((a) => a.role === "customer");
  const [customer, setCustomer] = useState(customers[0].id);
  const [chosen, choose] = useState<string | null>(null);
  const [speaker, setSpeaker] = useState<"customer" | "sales">("customer");
  const all = useData(() => api.sessions(), []);
  const mine = (all ?? []).filter((s) => s.sales_id === me).reverse();
  const current = mine.find((s) => s.id === chosen) ?? mine[0] ?? null;
  const sid = current?.id ?? null;
  const detail = useData(() => (sid ? api.session(sid, me) : Promise.resolve(null)), [sid, me]);

  const start = () => api.startSession(customer, me).then((s) => {
    choose(s.id);
    refresh();
  }, fail);

  const rail = (
    <>
      <RailTitle count={mine.length}>客户会话</RailTitle>
      {mine.map((s) => {
        const [label, tone] = SESSION_STATUS[s.status] ?? [s.status, ""];
        return (
          <button key={s.id} onClick={() => choose(s.id)}
                  className={`card card-hover press text-left ${s.id === sid ? "card-on" : ""}`}>
            <div className="flex items-center justify-between gap-2">
              <p className="flex items-center gap-2 text-[15px] font-medium">
                {s.id === sid && <i className="h-1.5 w-1.5 rounded-full bg-ink" />}{short(L.name(s.customer_id))}</p>
              <span className={`tag ${tone}`}>{label}</span>
            </div>
            <p className="mt-1.5 text-[14px] text-ink/70">{L.phen(s.phenomenon)}</p>
            <p className="meta mt-0.5">{s.id}</p>
          </button>
        );
      })}
      <div className="card">
        <p className="label mb-3">新建客户会话</p>
        <Segmented size="sm" wrap value={customer} onChange={setCustomer}
                   items={customers.map((c) => [c.id, short(c.name)] as const)} />
        <button onClick={start} className="btn btn-ink mt-4 w-full">新建会话</button>
      </div>
      {!!detail?.ask_back.length && <RailTitle count={detail.ask_back.length}>回问</RailTitle>}
      {detail?.ask_back.map((q) => <QuestionCard key={q.id} q={q} />)}
      <PendingStack />
    </>
  );

  return (
    <Layout rail={rail}>
      <PageHead kicker={current ? `${current.id} · ${short(L.name(current.customer_id))}` : "业务员工作台 · L1"}
                title={detail ? L.phen(detail.phenomenon) : "选择或新建客户会话"} />
      {!live && <OfflineBanner>角色助手离线：直接在底部输入客户和业务员的发言，系统照常抽取、提示追问、推荐或升级。</OfflineBanner>}
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
          <div className="flex flex-col gap-3">
            {v.turns.map((t) => (
              <div key={t.id} className="flex flex-col gap-3">
                <Bubble who={t.speaker === "customer" ? "客户" : "业务员"} mine={t.speaker === "sales"}>{t.text}</Bubble>
                {replies(t.id).map((r, i) => (
                  <Bubble key={i} who="知识助手">
                    {r.text}
                    {r.blocked && <span className="tag tag-red ml-2 align-middle">研发保密 · 已拦截</span>}
                  </Bubble>
                ))}
              </div>
            ))}
          </div>
        </Section>
      )}

      {!!v.hints.length && (
        <Section title="觉的追问提示" aside={<span className="meta">按需要决策的概率</span>}>
          <div className="grid gap-2 sm:grid-cols-2">
            {v.hints.map((h) => (
              <div key={h.slot} className="cell !px-4 !py-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="label">{h.label}</p>
                  <p className="num text-[24px] font-medium leading-none text-accent">{h.p_need.toFixed(2)}</p>
                </div>
                <p className="mt-1 text-[15px] leading-6">{h.ask_text}</p>
                <p className="meta mt-1">{h.scored_by} 打分</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="场景需求卡" aside={<span className="tag">L1 · 每一格绑定客户原话</span>}>
        <div className="cell !px-4 !py-3">
          <p className="label">现象</p>
          <p className="mt-1 text-[24px] font-medium leading-tight">{L.phen(d.phenomenon)}</p>
          {d.phenomenon_quote && <p className="meta mt-1">「{d.phenomenon_quote}」</p>}
        </div>
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          {v.slots.map((s) => (
            <div key={s.slot} className="cell !px-4 !py-3">
              <p className="label">{L.slot(s.slot)}</p>
              <p className={`mt-1 text-[24px] font-medium leading-tight ${s.value ? "" : "text-ink/35"}`}>{s.value ?? "客户不清楚"}</p>
              <p className="meta mt-1">「{s.quote}」</p>
            </div>
          ))}
        </div>
        {!v.slots.length && <p className="meta mt-3">尚未抽取到条件。</p>}
      </Section>

      {v.card ? <RecCard card={v.card} /> : v.status === "escalated" && (
        <div className="card anim-rise flex items-center gap-3">
          <span className="tag tag-accent shrink-0">已升级</span>
          <p className="flex-1 text-[15px] leading-6">没有适用的现有产品，已转给产品经理处理。</p>
          <span className="meta">{v.escalation_question_id}</span>
        </div>
      )}
    </>
  );
}
