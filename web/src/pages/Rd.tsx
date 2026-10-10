// 研发工作台（L3）：问题队列、和研发助手对话、需求单的化学语言、会话原文（内部版）、我的知识与积分。
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { Empty, Layout, PageHead, PendingStack, QuestionStack, RecCard, RequirementPanel, Section, useRequirementChoice } from "../components/Cards";
import { AgentConversation, AgentDock, Dock } from "../components/Dock";
import { OfflineNote } from "./Pm";

function SessionSource({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const view = useData(() => api.requirement(reqId, me), [reqId, me]);
  const ids = view?.requirement.session_ids ?? [];
  const sessions = useData(() => Promise.all(ids.map((sid) => api.session(sid, me))), [ids.join(","), me]);
  return (
    <Section title="会话原文" aside={<span className="chip">研发可见内部版</span>}>
      {!sessions?.length && <Empty>这张需求单没有关联会话。</Empty>}
      {sessions?.map((d) => (
        <div key={d.view.session_id} className="mt-2 first:mt-0">
          <p className="mb-1.5 text-[12px] text-black/55">{d.view.session_id}</p>
          {d.view.turns.map((t) => (
            <p key={t.id} className="text-[14px] leading-6">
              <span className="mr-2 text-[12px] text-black/55">{t.speaker === "customer" ? "客户" : "业务员"}</span>{t.text}
            </p>
          ))}
          {d.view.card && <div className="mt-2"><RecCard card={d.view.card} /></div>}
        </div>
      ))}
    </Section>
  );
}

function MyKnowledge() {
  const { me } = useApp();
  const stats = useData(() => api.contributions(me), [me]);
  const ledger = useData(() => api.ledger(), []);
  const mine = (stats ?? []).filter((s) => s.owner === me);
  return (
    <Section title="我的知识" aside={<span className="num chip">总积分 {ledger?.[me] ?? 0}</span>}>
      {!mine.length && <Empty>还没有归属于你的知识。</Empty>}
      {mine.map((s) => (
        <div key={s.ku_id} className="flex items-baseline justify-between gap-3 border-b border-black/5 py-1.5 text-[14px] last:border-0">
          <span className="min-w-0"><span className="chip mr-2">L{s.level}</span>{s.title}</span>
          <span className="num shrink-0 text-black/60">被引用 {s.n_cited} 次 · {s.points} 分</span>
        </div>
      ))}
    </Section>
  );
}

export function Rd() {
  const { live, me } = useApp();
  const L = useLabels();
  const { current, picker } = useRequirementChoice();
  const rail = (
    <>
      <QuestionStack role="rd" />
      <PendingStack />
    </>
  );
  return (
    <Layout rail={rail}>
      <PageHead kicker={`研发工作台 · L3 · ${L.name(me)}`} title="把产品需求转成化学语言" />
      {live ? <AgentConversation sessionId={null} /> : <OfflineNote />}
      <div className="mt-3">{picker}</div>
      {current ? (
        <>
          <RequirementPanel id={current} initial="chem_lang" />
          <SessionSource reqId={current} />
        </>
      ) : <Section title="需求单"><Empty>暂无需求单。</Empty></Section>}
      <MyKnowledge />
      {live ? <AgentDock sessionId={null} /> : <Dock placeholder="角色助手离线" onSend={() => Promise.resolve()} disabled />}
    </Layout>
  );
}
