// 业务员工作台（L1）：和业务员助手对话；离线时直接录入客户与业务员发言，走规则抽取、觉与 Mock Jev。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { SessionDetail } from "../types";
import { EmptyState, Group, PageHead, PendingGroup, QuestionRow, RecGroup, Shell, SideHead } from "../components/Cards";
import { Popover, Segmented } from "../components/Controls";
import { AgentConversation, AgentDock, Bubble, Dock, type Suggestion } from "../components/Dock";
import { Lock, Plus } from "../components/Icons";

const SESSION_STATUS: Record<string, string> = { open: "进行中", recommended: "已推荐", escalated: "已升级" };

export function Sales() {
  const { meta, me, live, refresh, fail } = useApp();
  const L = useLabels();
  const customers = meta.actors.filter((a) => a.role === "customer");
  const [chosen, choose] = useState<string | null>(null);
  const [speaker, setSpeaker] = useState<"customer" | "sales">("customer");
  const all = useData(() => api.sessions(), []);
  const mine = (all ?? []).filter((s) => s.sales_id === me).reverse();
  const current = mine.find((s) => s.id === chosen) ?? mine[0] ?? null;
  const sid = current?.id ?? null;
  const detail = useData(() => (sid ? api.session(sid, me) : Promise.resolve(null)), [sid, me]);

  const start = (customer: string) => api.startSession(customer, me).then((s) => {
    choose(s.id);
    refresh();
  }, fail);

  const sidebar = (
    <>
      <SideHead aside={
        <Popover trigger={(toggle) => <button onClick={toggle} className="icon-btn !h-6 !w-6" title="新建客户会话"><Plus /></button>}>
          {(close) => (
            <>
              <p className="px-2.5 pb-1 pt-0.5 text-[12px] text-ink-2">新建客户会话</p>
              {customers.map((c) => (
                <button key={c.id} className="menu-item" onClick={() => { start(c.id); close(); }}>{L.name(c.id)}</button>
              ))}
            </>
          )}
        </Popover>
      }>客户会话</SideHead>
      {mine.map((s) => (
        <button key={s.id} onClick={() => choose(s.id)} title={s.id} className={`side-row ${s.id === sid ? "on" : ""}`}>
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-[13px] font-semibold">{L.name(s.customer_id)}</span>
            <span className={`shrink-0 text-[12px] text-ink-2`}>
              {SESSION_STATUS[s.status] ?? s.status}</span>
          </div>
          <p className="truncate text-[12px] text-ink-2">{s.phenomenon ? L.phen(s.phenomenon) : "尚未识别现象"}</p>
        </button>
      ))}
      {!mine.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">点 ＋ 新建一个客户会话</p>}
      {!!detail?.ask_back.length && (
        <>
          <SideHead>回问</SideHead>
          {detail.ask_back.map((q) => <QuestionRow key={q.id} q={q} />)}
        </>
      )}
    </>
  );

  // 觉的追问提示放在输入框上方，点一下填进输入框（业务员来问）
  const suggestions: Suggestion[] = (detail?.view.hints ?? []).map((h) => ({ key: h.slot, label: h.label, text: h.ask_text, p: h.p_need }));

  return (
    <Shell sidebar={sidebar}>
      <PendingGroup />
      {current && detail ? <SessionBody d={detail} customer={L.name(current.customer_id)} /> : (
        <EmptyState title="还没有客户会话" text="点侧栏「客户会话」右侧的 ＋，选一个客户开始。客户只需描述宏观现象，系统负责追问、整理与推荐。" />
      )}
      {sid && (live ? <AgentDock sessionId={sid} suggestions={suggestions} /> : (
        <Dock
          placeholder={speaker === "customer" ? "输入客户的话……" : "输入业务员的话……"}
          onSend={(t) => api.addTurn(sid, speaker, t).then(refresh, fail)}
          suggestions={suggestions}
          onPick={() => setSpeaker("sales")}
          accessory={<Segmented value={speaker} onChange={setSpeaker} items={[["customer", "客户"], ["sales", "业务员"]] as const} />}
        />
      ))}
    </Shell>
  );
}

function SessionBody({ d, customer }: { d: SessionDetail; customer: string }) {
  const { live } = useApp();
  const L = useLabels();
  const v = d.view;
  const replies = (turnId: string) => v.replies.filter((r) => r.turn_id === turnId);
  return (
    <>
      <PageHead title={customer} subtitle={`${L.phen(d.phenomenon)} · ${SESSION_STATUS[v.status] ?? v.status}`} />

      {live ? <AgentConversation sessionId={v.session_id} /> : (
        <section className="flex flex-col gap-1.5">
          {!v.turns.length && <p className="text-[13px] text-ink-2">还没有发言。客户只说宏观现象即可，比如「染完以后布面深一块浅一块」。</p>}
          {v.turns.map((t, i) => {
            const changed = i === 0 || v.turns[i - 1].speaker !== t.speaker || replies(v.turns[i - 1].id).length > 0;
            return (
              <div key={t.id} className="flex flex-col gap-1.5">
                <Bubble who={changed ? (t.speaker === "customer" ? "客户" : "业务员") : undefined} mine={t.speaker === "sales"}>{t.text}</Bubble>
                {replies(t.id).map((r, j) => (
                  <Bubble key={j} who="知识助手">
                    {r.text}
                    {r.blocked && (
                      <span className="tag tag-danger ml-2 gap-1 align-[1px]"><Lock />研发保密 · 已拦截</span>
                    )}
                  </Bubble>
                ))}
              </div>
            );
          })}
        </section>
      )}

      <Group title="场景需求卡" foot="每一项都绑定客户原话；客户说不清的如实标注。">
        <div className="row">
          <span className="w-20 shrink-0 text-[13px] text-ink-2">现象</span>
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-semibold">{L.phen(d.phenomenon)}</p>
            {d.phenomenon_quote && <p className="text-[12px] text-ink-3">「{d.phenomenon_quote}」</p>}
          </div>
        </div>
        {v.slots.map((s) => (
          <div key={s.slot} className="row">
            <span className="w-20 shrink-0 text-[13px] text-ink-2">{L.slot(s.slot)}</span>
            <div className="min-w-0 flex-1">
              <p className={`text-[14px] ${s.value ? "font-semibold" : "text-ink-3"}`}>{s.value ?? "客户不清楚"}</p>
              <p className="text-[12px] text-ink-3">「{s.quote}」</p>
            </div>
          </div>
        ))}
      </Group>

      {v.card ? <RecGroup card={v.card} /> : v.status === "escalated" && (
        <Group title="处理">
          <div className="row">
            <p className="flex-1 text-[14px]">没有适用的现有产品，已转给产品经理处理。</p>
            <span className="tag">已升级</span>
          </div>
        </Group>
      )}
    </>
  );
}
