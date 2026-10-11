// 知识与积分：本人的知识、被引用次数与积分，以及全员积分榜。「谁的知识被用了，谁得分」。
// 产品经理 Agent 不记积分；历史 L2 知识的归属人（产品经理 P01）被引用照常记分。
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { Empty, Group, PageHead } from "../components/ui";

export function Ledger() {
  const { me } = useApp();
  const L = useLabels();
  const stats = useData(() => api.contributions(me), [me]) ?? [];
  const totals = useData(() => api.ledger(), []) ?? {};
  const mine = stats.filter((s) => s.owner === me);
  const board = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  return (
    <div className="mx-auto flex max-w-[860px] flex-col gap-7 px-8 pb-24 pt-7">
      <PageHead title="知识与积分" subtitle="知识被引用即给归属人记分；上层知识对下层只显示归属，不显示原文。" />
      <Group title="我的知识" aside={<>总积分 <span className="num font-semibold text-ink">{totals[me] ?? 0}</span></>}>
        {mine.map((s) => (
          <div key={s.ku_id} className="row">
            <span className="tag w-7 justify-center">L{s.level}</span>
            <span className="min-w-0 flex-1 truncate text-[14px]">{s.title}</span>
            <span className="num shrink-0 text-[13px] text-ink-2">被引用 {s.n_cited} 次 · {s.points} 分</span>
          </div>
        ))}
        {!mine.length && <Empty>还没有归属于你的知识</Empty>}
      </Group>
      <Group title="被引用的知识" foot="积分只给人；产品经理 Agent 引用历史案例时，分数记在原归属人名下。">
        {stats.filter((s) => s.n_cited > 0).map((s) => (
          <div key={s.ku_id} className="row">
            <span className="w-28 shrink-0 truncate text-[13px] text-ink-2">{L.name(s.owner)}</span>
            <span className="tag w-7 justify-center">L{s.level}</span>
            <span className="min-w-0 flex-1 truncate text-[14px]">{s.title}</span>
            <span className="num shrink-0 text-[13px] text-ink-2">被引用 {s.n_cited} 次 · {s.points} 分</span>
          </div>
        ))}
        {!stats.some((s) => s.n_cited > 0) && <Empty>还没有知识被引用</Empty>}
      </Group>
      <Group title="积分榜">
        {board.map(([who, pts], i) => (
          <div key={who} className={`row ${who === me ? "bg-[rgba(0,113,227,.06)]" : ""}`}>
            <span className="num w-5 text-[13px] text-ink-3">{i + 1}</span>
            <span className="flex-1 text-[14px]">{L.name(who)}</span>
            <span className="num text-[14px] font-semibold">{pts}</span>
          </div>
        ))}
        {!board.length && <Empty>还没有积分</Empty>}
      </Group>
    </div>
  );
}
