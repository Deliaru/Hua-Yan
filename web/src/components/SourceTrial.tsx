import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import type { SourceCitation, SourceTrialRecord, SourceTrialText } from "../types";
import { SourceImage, SourceImageCard } from "./SourceImage";

type ImageTarget = { span?: string; page: number; label: string; group?: string };
type ViewImage = (span: string, page: number) => void;
const rootSpan = (span: string) => span.split("/")[0];

function Citations({ items, onView }: { items: SourceCitation[]; onView: ViewImage }) {
  if (!items.length) return null;
  return <details className="mt-1 text-[12px] text-ink-2">
    <summary className="cursor-pointer">查看出处（{items.length}处）</summary>
    {items.map((c, i) => <div key={i} className="mt-2 rounded bg-white p-2">
      <p className="break-all">{c.fragment} · 页{c.pages.join("、")}{c.cell && ` · r${c.cell[0]}c${c.cell[1]}`}</p>
      <p className="whitespace-pre-wrap">{c.quote}</p>
      <div className="mt-1 flex flex-wrap gap-2">{c.pages.map((page) => <button key={page} type="button"
        className="btn btn-quiet" onClick={() => onView(rootSpan(c.span), page)}>查看第{page}页／区域</button>)}</div>
    </div>)}
  </details>;
}

function Texts({ title, items, onView }: { title: string; items: SourceTrialText[]; onView: ViewImage }) {
  if (!items.length) return null;
  return <section className="mt-4"><h4 className="mb-2 font-semibold">{title}</h4>
    {items.map((t, i) => <div key={i} className="mt-2 rounded-lg bg-slate-50 p-3">
      <p className="whitespace-pre-wrap">{t.text}</p><Citations items={t.evidence} onView={onView} />
    </div>)}
  </section>;
}

function TrialComparison({ record, preferredSpans, children }: {
  record: SourceTrialRecord; preferredSpans: string[]; children?: React.ReactNode;
}) {
  const { me } = useApp();
  const [target, setTarget] = useState<{ span: string; page: number } | null>(null);
  const [chosen, setChosen] = useState<ImageTarget | null>(null);
  const [group, setGroup] = useState<string | null>(null);
  const view: ViewImage = (span, page) => setTarget({ span, page });
  const texts = [...record.metadata, ...record.purpose, ...record.common_conditions, ...record.quality,
    ...record.cost, ...record.follow_up, ...record.reported_results, ...record.review_notes];
  const citations = [...texts.flatMap((t) => t.evidence), ...record.time.evidence,
    ...record.groups.flatMap((g) => [...g.curve_evidence, ...g.formula.flatMap((f) => f.evidence),
      ...g.formula_notes.flatMap((t) => t.evidence), ...g.operations.flatMap((t) => t.evidence)])];
  const regions: ImageTarget[] = [];
  for (const g of record.groups) {
    const refs = [...g.curve_evidence, ...g.formula.flatMap((f) => f.evidence)];
    for (const c of refs) for (const page of [...c.pages].reverse()) {
      const span = rootSpan(c.span);
      if (!regions.some((r) => r.span === span && r.page === page))
        regions.push({ span, page, group: g.group, label: `${g.group}组${g.curve_evidence.some((x) => rootSpan(x.span) === span) ? "配方与曲线" : "配方"} · 第${page}页` });
    }
  }
  const rank = (span: string) => preferredSpans.includes(span) ? preferredSpans.indexOf(span) : preferredSpans.length;
  // 主对象优先；跨页曲线先展示末页，避免先显示只有标题的区域。
  for (const c of citations) for (const page of [...c.pages].reverse()) {
    const span = rootSpan(c.span);
    if (preferredSpans.includes(span) && !regions.some((r) => r.span === span && r.page === page))
      regions.push({ span, page, label: `引用区域 · 第${page}页` });
  }
  regions.sort((a, b) => rank(a.span!) - rank(b.span!));
  const pages = [...new Set(citations.flatMap((c) => c.pages))].sort((a, b) => a - b);
  const options: ImageTarget[] = [...regions, ...pages.map((page) => ({ page, label: `第${page}页整页` }))];
  const image = chosen ?? options[0];
  const active = group ?? regions[0]?.group ?? record.groups[0]?.group;
  const g = record.groups.find((item) => item.group === active);
  return <div className="mt-4 grid items-start gap-5 lg:grid-cols-[1.08fr_0.92fr]">
    <div className="min-w-0">
      {children}
      <p className="mt-3 text-[12px] text-ink-2">L{record.level} · 规则整理的读取草稿，仍待专业确认。</p>
      <Texts title="共同条件" items={record.common_conditions} onView={view} />
      {!!record.groups.length && <section className="mt-4 rounded-xl border border-line p-3">
        <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="试样组别">
          {record.groups.map((item) => <button key={item.group} type="button" aria-pressed={active === item.group}
            className={`rounded-lg border px-3 py-2 font-semibold ${active === item.group ? "border-accent bg-accent/10 text-accent" : "border-line text-ink-2"}`}
            onClick={() => { setGroup(item.group); setChosen(regions.find((r) => r.group === item.group) ?? null); }}>
            {item.group}组 · {item.group === "A" ? "原工艺对照" : "试样条件"}
          </button>)}
        </div>
        {g && <>
          {!!g.formula.length && <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full border-collapse text-left text-[12px]">
              <thead className="bg-slate-50"><tr>{["配方原名", "数值", "原单位", "基准"].map((h) => <th key={h} className="border-b border-line px-3 py-2">{h}</th>)}</tr></thead>
              <tbody>{g.formula.map((x, i) => <tr key={i} className="border-b border-line last:border-0">
                <td className="px-3 py-2">{x.name}<Citations items={x.evidence} onView={view} /></td>
                <td className="px-3 py-2 tabular-nums">{x.value}</td><td className="px-3 py-2">{x.unit ?? <span className="rounded bg-amber-100 px-2 py-1 text-amber-800">未记载</span>}</td>
                <td className="px-3 py-2">{x.basis ?? <span className="text-amber-700">未注明</span>}</td>
              </tr>)}</tbody>
            </table>
          </div>}
          <Texts title="配方说明／原对象及列" items={g.formula_notes} onView={view} />
          {!!g.curve_labels.length && <div className="mt-4">
            <h4 className="font-semibold">已读曲线标签</h4><p className="mt-1 text-[12px] text-ink-2">保留阶段与原单位；排列不代表曲线连线或工艺执行顺序，请对照右侧原图。</p>
            <div className="mt-2 flex flex-wrap gap-2">{g.curve_labels.map((r, i) => <span key={i}
              className={`rounded-lg border px-2.5 py-2 ${r.status === "needs_reading" ? "border-amber-300 bg-amber-50 text-amber-800" : "border-line bg-slate-50"}`}>
              <span className="text-[11px]">{r.stage ?? "阶段待判断"}</span><strong className="ml-2">{r.value}{r.unit}</strong>
              {!!r.conditions.length && <span className="block text-[12px]">{r.conditions.join("；")}</span>}
              {r.status === "needs_reading" && <span className="block text-[11px]">待补读</span>}
            </span>)}</div><Citations items={g.curve_evidence} onView={view} />
          </div>}
          <Texts title="现场操作原文" items={g.operations} onView={view} />
        </>}
      </section>}
      <section className="mt-4 rounded-xl border border-line p-3"><h4 className="mb-2 font-semibold">时间对照</h4>
        {[record.time.a, record.time.b, record.time.reported_saving].map((r, i) => r && <p key={i} className="mt-1">{r.group ? `${r.group}组` : "报告结果"} · {r.quote}</p>)}
        <p className="mt-2">{record.time.calculated_saving !== null ? `标注时间差值：${record.time.formula} = ${record.time.calculated_saving}${record.time.unit}` : "未记载可比较的完整A/B总时长。"}</p>
        <p className="mt-2 text-ink-2">{record.time.basis}</p><Citations items={record.time.evidence} onView={view} />
      </section>
      <Texts title="品质观察" items={record.quality} onView={view} />
      {!!record.pending.length && <section className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-900">
        <h4 className="font-semibold">待补读与判断 · {record.pending.length}项</h4>
        <ul className="mt-2 list-disc space-y-2 pl-5">{record.pending.slice(0, 3).map((p, i) => <li key={i}>{p}</li>)}</ul>
        {record.pending.length > 3 && <details className="mt-3"><summary className="cursor-pointer">查看其余{record.pending.length - 3}项待补读</summary>
          <ul className="mt-2 list-disc space-y-2 pl-5">{record.pending.slice(3).map((p, i) => <li key={i}>{p}</li>)}</ul>
        </details>}
      </section>}
      <details className="mt-4 rounded-lg border border-line p-3"><summary className="cursor-pointer text-ink-2">报告信息与其他记录</summary>
        <Texts title="报告信息" items={record.metadata} onView={view} /><Texts title="试样目的" items={record.purpose} onView={view} />
        <Texts title="成本原文" items={record.cost} onView={view} /><Texts title="报告结果与分析原文" items={record.reported_results} onView={view} />
        <Texts title="后续工作原文" items={record.follow_up} onView={view} /><Texts title="整理核对备注" items={record.review_notes} onView={view} />
      </details>
    </div>
    <aside className="order-first min-w-0 space-y-3 lg:sticky lg:top-4 lg:order-last">
      <h4 className="font-semibold">原生依据图 · 对照审阅</h4>
      <div className="flex flex-wrap gap-2" role="group" aria-label="依据图像切换">{options.map((option) => <button key={`${option.span ?? "page"}:${option.page}`} type="button"
        aria-pressed={image?.span === option.span && image?.page === option.page}
        className={`rounded-lg border px-2.5 py-2 text-[12px] ${image?.span === option.span && image?.page === option.page ? "border-accent bg-accent/10 text-accent" : "border-line bg-white text-ink-2"}`}
        onClick={() => { setChosen(option); if (option.group) setGroup(option.group); }}>{option.label}</button>)}</div>
      {image ? <SourceImageCard key={`${me}:${record.source_id}:${image.span}:${image.page}`} docId={record.source_id} {...image} />
        : <p className="rounded-lg bg-slate-50 p-4 text-ink-2">这份记录没有已登记的页码，无法定位原图；请查看下方原文依据。</p>}
    </aside>
    {target && <SourceImage key={`${me}:${record.source_id}:${target.span}:${target.page}`} docId={record.source_id} {...target} onClose={() => setTarget(null)} />}
  </div>;
}

export function SourceTrial({ docId, autoLoad = false, preferredSpans = [], children }: {
  docId: string; autoLoad?: boolean; preferredSpans?: string[]; children?: React.ReactNode;
}) {
  const { me } = useApp();
  const [record, setRecord] = useState<SourceTrialRecord | null>(null);
  const [opened, setOpened] = useState(autoLoad);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setRecord(null); setError(null);
    if (opened) api.sourceTrial(docId, me).then(
      (data) => { if (alive) setRecord(data); },
      (e: Error) => { if (alive) setError(e.message); },
    );
    return () => { alive = false; };
  }, [docId, me, opened, reload]);
  return <section className="my-3 min-w-0 rounded-xl border border-line bg-white p-4 text-[13px] leading-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-semibold">试样资料 · {docId}</h3>
      <div className="flex gap-2"><button type="button" className="btn btn-quiet" onClick={() => { setOpened(true); setReload(reload + 1); }}>
        {opened ? "重新读取试样记录" : "读取试样记录"}</button>
        {opened && !autoLoad && <button type="button" className="btn btn-quiet" onClick={() => setOpened(false)}>收起</button>}
      </div>
    </div>
    {opened && !record && !error && <div className="mt-4">{children}<p role="status" className="mt-3 text-ink-2">正在读取结构化条件与原图定位……</p></div>}
    {error && <div className="mt-4">{children}<p role="alert" className="mt-3 rounded-lg bg-amber-50 p-3 text-amber-800">{error}</p></div>}
    {record && <TrialComparison key={`${me}:${docId}:${reload}`} record={record} preferredSpans={preferredSpans}>{children}</TrialComparison>}
  </section>;
}
