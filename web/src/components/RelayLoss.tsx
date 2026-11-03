// V12.11 原话直达与失真对照：需求单上每一格都点得回客户原话（业务员面的槽位、产品经理面的每条产品需求都带原话）；
// 旁边放同批需求卡按旧流程逐级转述到研发时还剩多少（失真对照 docs/reports/distortion_300，应升级的那些卡，模拟数据）。
// 只在打开演示说明时出现，真实试用里不出现。
import { api } from "../api";
import { useApp, useData } from "../ctx";
import { Group } from "./ui";

type M = { completeness: number; returned: number };
type Report = { by_route: { escalate: { n_cards: number; metrics: Record<string, M> } } };
const ROWS: [string, string][] = [["G1 业务员转述", "旧流程：业务员凭印象转述"], ["G2 一次性翻译", "只有 Agent：开场白一次翻成化学语言"], ["G3 化言", "化言：觉追问、原话随单、回问补齐"]];
const pct = (x: number) => `${Math.round(x * 1000) / 10}%`;

export function RelayLoss() {
  const { meta, notes } = useApp();
  const r = useData(() => api.report<Report>("distortion_300"), []);
  if (!notes || (meta.trial && !meta.play) || !r) return null;
  const e = r.by_route.escalate;
  return (
    <Group title="需求到研发手里还剩多少" foot={`同一批 ${e.n_cards} 张应升级的需求卡（模拟），三种做法各走一遍。关键信息 = 现象 + 研发必问的条件且取值正确。`}>
      <div className="flex flex-col gap-2 px-4 py-3 text-[12.5px]">
        {ROWS.map(([k, label]) => <div key={k}>
          <p className="text-ink-2">{label}</p>
          <div className="mt-0.5 flex items-center gap-2">
            <div className="h-[8px] flex-1 overflow-hidden rounded bg-fill"><div className="h-full" style={{ width: pct(e.metrics[k].completeness), background: k.startsWith("G3") ? "#248a3d" : "#e08a2b" }} /></div>
            <span className="num w-[150px] shrink-0 text-right">关键信息 {pct(e.metrics[k].completeness)} · 退回 {pct(e.metrics[k].returned)}</span>
          </div>
        </div>)}
      </div>
    </Group>
  );
}
