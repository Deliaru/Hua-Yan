// 研发工作台（L3）：问题队列、和研发助手对话、需求单的化学语言、会话原文（内部版）、我的知识与积分。
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { Empty, Layout, PageHead, PendingStack, QuestionStack, RecCard, RequirementPanel, Section, useRequirementChoice } from "../components/Cards";
import { AgentConversation, AgentDock, Bubble, Dock } from "../components/Dock";
import { OfflineNote } from "./Pm";

function SessionSource({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const view = useData(() => api.requirement(reqId, me), [reqId, me]);
  const ids = view?.requirement.session_ids ?? [];
  const sessions = useData(() => Promise.all(ids.map((sid) => api.session(sid, me))), [ids.join(","), me]);
  return (
    <Section title="会话原文" aside={<span className="tag">研发可见内部版</span>}>
      {!sessions?.length && <Empty>这张需求单没有关联会话。</Empty>}
      {sessions?.map((d) => (
        <div key={d.view.session_id} className="flex flex-col gap-3">
          <p className="meta">{d.view.session_id}</p>
          {d.view.turns.map((t) => (
            <Bubble key={t.id} who={t.speaker === "customer" ? "客户" : "业务员"} mine={t.speaker === "sales"}>{t.text}</Bubble>
          ))}
          {d.view.card && <RecCard card={d.view.card} />}
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
    <Section title="我的知识" aside={
      <span className="flex items-baseline gap-1.5"><span className="meta">总积分</span>
        <span className="num text-[24px] font-medium leading-none">{ledger?.[me] ?? 0}</span></span>}>
      {!mine.length && <Empty>还没有归属于你的知识。</Empty>}
      <div className="grid gap-2 sm:grid-cols-2">
        {mine.map((s) => (
          <div key={s.ku_id} className="cell !px-4 !py-3">
            <div className="flex items-start justify-between gap-3">
              <p className="min-w-0 text-[15px] font-medium leading-6">{s.title}</p>
              <span className="tag shrink-0">L{s.level}</span>
            </div>
            <div className="mt-2 flex items-baseline gap-4">
              <span><span className="num text-[20px] font-medium">{s.n_cited}</span><span className="meta ml-1">次引用</span></span>
              <span><span className="num text-[20px] font-medium">{s.points}</span><span className="meta ml-1">分</span></span>
            </div>
          </div>
        ))}
      </div>
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
      <PageHead kicker={`研发工作台 · L3 · ${L.name(me).replace("（模拟）", "")}`} title="把产品需求转成化学语言" />
      {live ? <AgentConversation sessionId={null} /> : <OfflineNote />}
      {picker && <div>{picker}</div>}
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
