// 产品经理工作台（L2）：问题队列、和产品经理助手对话、需求单（L3 知识只显示归属）、积分榜。
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { Empty, Layout, PageHead, PendingStack, QuestionStack, RequirementPanel, Section, useRequirementChoice } from "../components/Cards";
import { AgentConversation, AgentDock, Dock } from "../components/Dock";
import { OfflineBanner } from "./Sales";

export function OfflineNote() {
  const { meta, live, refresh, fail } = useApp();
  if (live) return null;
  return (
    <OfflineBanner action={
      <button disabled={!meta.mainline_available} onClick={() => api.offlineMainline().then(refresh, fail)}
              title={meta.mainline_available ? "" : "离线主线在 WP-I 提供"} className="btn btn-ink shrink-0">载入离线主线</button>}>
      角色助手离线：需求单的起草与确认由离线主线脚本代替，结果照常展示。
    </OfflineBanner>
  );
}

export function Ledger() {
  const L = useLabels();
  const ledger = useData(() => api.ledger(), []);
  const rows = Object.entries(ledger ?? {}).sort((a, b) => b[1] - a[1]);
  return (
    <Section title="积分榜" aside={<span className="meta">知识被引用即给归属人记分</span>}>
      {!rows.length && <Empty>还没有知识被引用。</Empty>}
      <div className="flex flex-col gap-2">
        {rows.map(([who, points], i) => (
          <div key={who} className="cell flex items-center gap-3 !px-4 !py-3">
            <span className={`num flex h-6 w-6 items-center justify-center rounded-full text-[13px] ${
              i === 0 ? "bg-ink text-white" : "bg-ink/[.07] text-ink/60"}`}>{i + 1}</span>
            <span className="flex-1 text-[15px]">{L.name(who).replace("（模拟）", "")}</span>
            <span className="num text-[24px] font-medium leading-none">{points}</span>
            <span className="meta">分</span>
          </div>
        ))}
      </div>
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
      {picker && <div>{picker}</div>}
      {current ? <RequirementPanel id={current} /> : <Section title="需求单"><Empty>暂无需求单。</Empty></Section>}
      <Ledger />
      {live ? <AgentDock sessionId={null} /> : <Dock placeholder="角色助手离线" onSend={() => Promise.resolve()} disabled />}
    </Layout>
  );
}
