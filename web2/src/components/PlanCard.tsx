// V12.5 方案推演：研发 Agent 从历史试样推出的候选方案。只是本单准备材料，不是能力，不进客户侧；接单研发采用或让 Agent 改写。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import { Act } from "./ui";
import { SourceImage } from "./SourceImage";

function Section({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return <div className="mt-3">
    <p className="font-medium">{title}</p>
    <ul className="mt-1 list-disc space-y-1 pl-5">{items.map((x, i) => <li key={i} className="whitespace-pre-wrap">{x}</li>)}</ul>
  </div>;
}

export function PlanCard({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const L = useLabels();
  const plan = useData(() => api.plan(reqId, me), [reqId, me]);
  const [page, setPage] = useState<{ doc: string; page: number } | null>(null);
  if (!plan) return null;
  return <section className="rounded-xl border border-line bg-white p-5 text-[13px]">
    <h3 className="font-semibold">候选方案（从历史试样推出）{plan.preloaded && <span className="tag tag-attn ml-2">预先准备</span>}</h3>
    {plan.preloaded && <p className="mt-1 text-ink-2">这份方案是之前一次真实运行里研发 Agent 推出、保存下来的，演示时直接放进来。</p>}
    <p className="mt-1 text-ink-2">{plan.by.startsWith("agent:") ? `${L.name(plan.by.slice(6))}的研发 Agent` : L.name(plan.by)}起草 · {plan.at.slice(5, 16).replace("T", " ")}。
      方案是草稿，不是能力，不进客户侧；要改就在右栏让 Agent 改写。</p>
    <Section title="历史试样对照" items={plan.comparison} />
    <Section title="可以迁移到本单的条件" items={plan.transferable} />
    <Section title="不确定的参数与建议的验证试样" items={plan.open_items} />
    <div className="mt-3">
      <p className="font-medium">依据</p>
      <div className="mt-1 flex flex-wrap gap-1.5">{plan.evidence.map((ref) => {
        const [doc, span] = ref.split("@")[0].split("#");
        return /^p\d+$/.test(span)          // 资料库一页一块；其他来源的块名照原样列出
          ? <button key={ref} type="button" className="chip" onClick={() => setPage({ doc, page: Number(span.slice(1)) })}>{doc} 第 {span.slice(1)} 页</button>
          : <span key={ref} className="chip">{doc}#{span}</span>;
      })}</div>
    </div>
    <div className="mt-4 row gap-2">
      {plan.adopted_by ? <span className="text-ink-2">{L.name(plan.adopted_by)}已采用 · {plan.adopted_at!.slice(5, 16).replace("T", " ")}</span>
        : <Act label="采用这个方案" run={() => api.adoptPlan(reqId, me)} />}
    </div>
    {page && <SourceImage docId={page.doc} page={page.page} onClose={() => setPage(null)} />}
  </section>;
}
