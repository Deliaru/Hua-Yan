// 产品经理工作台（L2）：问题队列、和产品经理助手对话、需求单（L3 知识只显示归属）、积分榜。
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { EmptyState, Group, PendingGroup, QuestionSection, RequirementDetail, Shell, useRequirementChoice } from "../components/Cards";
import { AgentConversation, AgentDock } from "../components/Dock";

// 没有需求单时的空状态；离线时提供「载入离线主线」。
export function NoRequirement() {
  const { meta, live, refresh, fail } = useApp();
  return live ? (
    <EmptyState title="还没有需求单" text="L1 解决不了的需求会出现在左侧问题队列，告诉助手处理即可。" />
  ) : (
    <EmptyState title="还没有需求单"
                text={meta.mainline_available ? "角色助手离线。载入离线主线，由脚本代替起草与确认，结果照常展示。" : "角色助手离线；离线主线由 WP-I 提供。"}
                action={meta.mainline_available && (
                  <button onClick={() => api.offlineMainline().then(refresh, fail)} className="btn btn-primary">载入离线主线</button>
                )} />
  );
}

export function Ledger() {
  const L = useLabels();
  const ledger = useData(() => api.ledger(), []);
  const rows = Object.entries(ledger ?? {}).sort((a, b) => b[1] - a[1]);
  if (!rows.length) return null;
  return (
    <Group title="积分榜" foot="知识被引用即给归属人记分。">
      {rows.map(([who, points], i) => (
        <div key={who} className="row">
          <span className="num w-4 text-[13px] text-ink-3">{i + 1}</span>
          <span className="flex-1 text-[14px]">{L.name(who)}</span>
          <span className={`num text-[15px] ${i === 0 ? "font-semibold" : ""}`}>{points}</span>
          <span className="text-[12px] text-ink-2">分</span>
        </div>
      ))}
    </Group>
  );
}

export function Pm() {
  const { live } = useApp();
  const { current, section } = useRequirementChoice();
  return (
    <Shell sidebar={<><QuestionSection role="pm" />{section}</>}>
      <PendingGroup />
      {live && <AgentConversation sessionId={null} />}
      {current ? <RequirementDetail id={current} /> : <NoRequirement />}
      <Ledger />
      {live && <AgentDock sessionId={null} />}
    </Shell>
  );
}
