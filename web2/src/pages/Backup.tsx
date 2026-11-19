// V12.11 答辩备用页：评委追问时随时点开。Jue-K 学习曲线（docs/reports/jue_k、jue_evolution 的离线报告）、跨文档覆盖图（整批编译的读稿，
// 研发按统一读取入口只看到自己能读的试样）、动态别名（在契画布第三站确认）、部署图（读取工具可整体换成企业 RAG，可本地部署）。
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { Group, PageHead } from "../components/ui";

type Cover = { rows: { doc_id: string; title: string; product: string; conditions: Record<string, string>; temperature_c: number[] | null; result: string | null }[];
  hypotheses: { product: string; conditions: Record<string, string>; text: string; n: number }[]; read_by: string };
const TONE: Record<string, string> = { pass: "bg-[#248a3d]", fail: "bg-[#d70015]", mixed: "bg-[#e08a2b]" };
const RESULT: Record<string, string> = { pass: "通过", fail: "失败", mixed: "有好有坏" };

function Coverage() {
  const { me } = useApp();
  const L = useLabels();
  const c = useData<Cover | null>(() => (me.startsWith("rd:") ? api.coverageMap(me) : Promise.resolve(null)), [me]);
  if (!c) return <p className="px-4 py-3 text-[12.5px] text-ink-2">以研发身份打开（研发按统一读取入口只看到自己能读的试样）。</p>;
  const products = [...new Set(c.rows.map((r) => r.product))];
  const temp = (r: Cover["rows"][number]) => (r.temperature_c ? `${r.temperature_c[0]}${r.temperature_c[1] !== r.temperature_c[0] ? `—${r.temperature_c[1]}` : ""}℃` : "温度未写");
  return <div className="flex flex-col gap-4 px-4 py-3 text-[12.5px]">
    {products.map((p) => {
      const mine = c.rows.filter((r) => r.product === p);
      const conds = [...new Set(mine.map((r) => Object.values(r.conditions).join(" · ") || "条件未对齐"))];
      const temps = [...new Set(mine.map(temp))].sort();
      return <div key={p}>
        <p className="font-semibold">{L.product(p)}<span className="ml-2 font-normal text-ink-2">{mine.length} 条观察</span></p>
        <table className="mt-1 border-collapse">
          <thead><tr><th />{temps.map((t) => <th key={t} className="px-2 pb-1 font-normal text-ink-2">{t}</th>)}</tr></thead>
          <tbody>{conds.map((k) => <tr key={k}>
            <td className="pr-3 text-ink-2">{k}</td>
            {temps.map((t) => <td key={t} className="border border-sep px-2 py-1">
              <span className="flex flex-wrap gap-[3px]">{mine.filter((r) => (Object.values(r.conditions).join(" · ") || "条件未对齐") === k && temp(r) === t).map((r) =>
                <i key={r.doc_id + t} title={`${r.title} · ${RESULT[r.result ?? ""] ?? "没写结果"}`} className={`h-2.5 w-2.5 rounded-[2px] ${TONE[r.result ?? ""] ?? "bg-slate-300"}`} />)}</span>
            </td>)}
          </tr>)}</tbody>
        </table>
      </div>;
    })}
    <div><p className="font-semibold">研究假设 {c.hypotheses.length} 条（同产品、可比条件下结果不同，交研发判断，不自动改适用范围）</p>
      {c.hypotheses.map((h, i) => <p key={i} className="text-ink-2">{h.product ? L.product(h.product) : "产品未写"} · {Object.values(h.conditions).join(" · ") || "条件未对齐"}：{h.text}（{h.n} 份）</p>)}</div>
    <p className="text-ink-3">{c.read_by}。绿 通过 · 红 失败 · 橙 有好有坏 · 灰 没写结果</p>
  </div>;
}

const DEPLOY: [string, string][] = [
  ["企业内网：化言应用", "门面 HuayanApp 与工作面服务；正式状态（契的结论与能力、需求单、会话、事件）只由门面写入，落在本地运行目录"],
  ["读取工具（可整体替换）", "原件、页面、指纹、检索索引留在读取侧；可以换成企业现有的 RAG 或文档系统，契只认文件指纹与块位置"],
  ["本地模型", "图文检索嵌入 EmbeddingGemma 2（本机 GPU，不可用时退回关键词并标注）；觉的 Jue-K 是本地小模型，发现事项不调用大模型"],
  ["模型网关", "所有大模型调用经 OpenAI 兼容网关、带调用方、计量与指纹缓存；可指向云端或企业本地部署的大模型"],
  ["Jev（OneJev / Clef）", "决策与核对的概率模型，独立服务；不可用时走大模型降级并在界面标明"],
];

export function Backup() {
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-6 px-8 pb-24 pt-7">
      <PageHead title="答辩备用" subtitle="评委追问时点开：觉怎样学习、资料库里试过什么没试过什么、别名怎样确认、化言怎样部署。" />
      <Group title="觉在学习：Jue-K 学习曲线" foot="离线报告 docs/reports/jue_k 与 jue_evolution（模拟数据）：人的每次处置成为样本，按「家族 × 判断层」重训；研发层的结果不改变客户层追问的排序。实况页「觉雷达」里写着这一局新增的样本数。">
        <div className="grid grid-cols-2 gap-4 px-4 py-3">
          <img src="reports/jue_k/learning_curve.png" alt="Jue-K 学习曲线" className="w-full rounded-lg bg-white p-2" />
          <img src="reports/jue_k/reliability.png" alt="可靠性图" className="w-full rounded-lg bg-white p-2" />
        </div>
      </Group>
      <Group title="跨文档覆盖图：每个产品试过哪里、没试过哪里"><Coverage /></Group>
      <Group title="动态别名" foot="整批编译认不出的说法，模型提议是某个已有取值的另一种说法；研发在契画布第三站逐条确认后，下一份报告编译、从需求单检索都认得它。">
        <p className="px-4 py-3 text-[12.5px]">入口：契画布 → ③ 编译 → 动态别名。</p>
      </Group>
      <Group title="部署图">
        <div className="grid grid-cols-5 gap-2.5 px-4 py-3 text-[12.5px]">
          {DEPLOY.map(([t, d]) => <div key={t} className="rounded-[10px] border border-line bg-white px-3 py-2"><p className="font-semibold">{t}</p><p className="mt-1 leading-5 text-ink-2">{d}</p></div>)}
        </div>
      </Group>
    </div>
  );
}
