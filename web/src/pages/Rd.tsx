// 研发工作台（L3）：问题队列、和研发助手对话、需求单的化学语言、会话原文（内部版）、我的知识与积分。
import { api } from "../api";
import { useApp, useData } from "../ctx";
import { Group, PendingGroup, QuestionSection, RecGroup, RequirementDetail, Shell, useRequirementChoice } from "../components/Cards";
import { AgentConversation, AgentDock, Bubble } from "../components/Dock";
import { NoRequirement } from "./Pm";

function SessionSource({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const view = useData(() => api.requirement(reqId, me), [reqId, me]);
  const ids = view?.requirement.session_ids ?? [];
  const sessions = useData(() => Promise.all(ids.map((sid) => api.session(sid, me))), [ids.join(","), me]);
  if (!sessions?.length) return null;
  return (
    <>
      {sessions.map((d) => (
        <Group key={d.view.session_id} title="会话原文" aside="研发可见内部版">
          <div className="flex flex-col gap-1.5 p-4">
            {d.view.turns.map((t, i) => (
              <Bubble key={t.id} mine={t.speaker === "sales"}
                      who={i === 0 || d.view.turns[i - 1].speaker !== t.speaker ? (t.speaker === "customer" ? "客户" : "业务员") : undefined}>
                {t.text}
              </Bubble>
            ))}
          </div>
        </Group>
      ))}
      {sessions.map((d) => d.view.card && <RecGroup key={d.view.session_id} card={d.view.card} />)}
    </>
  );
}

function MyKnowledge() {
  const { me } = useApp();
  const stats = useData(() => api.contributions(me), [me]);
  const ledger = useData(() => api.ledger(), []);
  const mine = (stats ?? []).filter((s) => s.owner === me);
  if (!mine.length) return null;
  return (
    <Group title="我的知识" aside={<>总积分 <span className="num font-semibold text-ink">{ledger?.[me] ?? 0}</span></>}
           foot="被引用即记分；L3 原文只对研发可见，下层只看到归属。">
      {mine.map((s) => (
        <div key={s.ku_id} className="row">
          <span className="tag w-7 justify-center">L{s.level}</span>
          <span className="min-w-0 flex-1 truncate text-[14px]">{s.title}</span>
          <span className="num shrink-0 text-[13px] text-ink-2">{s.n_cited} 次引用 · {s.points} 分</span>
          {!!s.used_by.length && <span className="text-[12px] text-ink-3">用于 {s.used_by.join("、")}</span>}
        </div>
      ))}
    </Group>
  );
}

export function Rd() {
  const { live } = useApp();
  const { current, section } = useRequirementChoice();
  return (
    <Shell sidebar={<><QuestionSection role="rd" />{section}</>}>
      <PendingGroup />
      {live ? <AgentConversation sessionId={null} /> : <Group title="派单与确认记录"><div className="p-4"><AgentConversation sessionId={null} /></div></Group>}
      {current ? (
        <>
          <RequirementDetail id={current} initial="chem_lang" />
          <SessionSource reqId={current} />
        </>
      ) : <NoRequirement />}
      <MyKnowledge />
      {live && <AgentDock sessionId={null} />}
    </Shell>
  );
}
