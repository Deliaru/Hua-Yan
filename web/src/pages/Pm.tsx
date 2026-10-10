// 产品经理工作台（L2）：问题队列、和产品经理助手对话、需求单（L3 知识只显示归属）、积分榜。
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { Empty, Layout, PageHead, PendingStack, QuestionStack, RequirementPanel, Section, useRequirementChoice } from "../components/Cards";
import { AgentConversation, AgentDock, Dock } from "../components/Dock";

export function OfflineNote() {
  const { meta, live, refresh, fail } = useApp();
  if (live) return null;
  return (
    <div className="glass mt-4 flex items-center justify-between gap-4 p-4">
      <p className="text-[14px] leading-6 text-black/70">角色助手离线：需求单的起草与确认由离线主线脚本代替，结果照常展示。</p>
      <button disabled={!meta.mainline_available} onClick={() => api.offlineMainline().then(refresh, fail)}
              title={meta.mainline_available ? "" : "离线主线在 WP-I 提供"}
              className="shrink-0 rounded-full bg-ink px-4 py-1 text-[13px] text-white disabled:opacity-30">载入离线主线</button>
    </div>
  );
}

export function Ledger() {
  const L = useLabels();
  const ledger = useData(() => api.ledger(), []);
  const rows = Object.entries(ledger ?? {}).sort((a, b) => b[1] - a[1]);
  return (
    <Section title="积分榜" aside={<span className="chip">知识被引用即记分</span>}>
      {!rows.length && <Empty>还没有知识被引用。</Empty>}
      {rows.map(([who, points], i) => (
        <div key={who} className="flex items-baseline justify-between border-b border-black/5 py-1.5 text-[14px] last:border-0">
          <span><span className="num mr-3 text-black/55">{i + 1}</span>{L.name(who)}</span>
          <span className="num font-medium">{points}</span>
        </div>
      ))}
    </Section>
  );
}

export function Pm() {
  const { live } = useApp();
  const { current, picker } = useRequirementChoice();
  const rail = (
    <>
      <QuestionStack role="pm" />
      <PendingStack />
    </>
  );
  return (
    <Layout rail={rail}>
      <PageHead kicker="产品经理工作台 · L2" title="把场景需求转成产品语言" />
      {live ? <AgentConversation sessionId={null} /> : <OfflineNote />}
      <div className="mt-3">{picker}</div>
      {current ? <RequirementPanel id={current} /> : <Section title="需求单"><Empty>暂无需求单。</Empty></Section>}
      <Ledger />
      {live ? <AgentDock sessionId={null} /> : <Dock placeholder="角色助手离线" onSend={() => Promise.resolve()} disabled />}
    </Layout>
  );
}
