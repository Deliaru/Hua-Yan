import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import type { SourceImage as ImageResult, SourceTrialRecord, SourceTrialText } from "../types";
import { SourceImageCard } from "./SourceImage";

type ImageTarget = { span?: string; page: number; label: string; group?: string };
const rootSpan = (span: string) => span.split("/")[0];
const isVisualSpan = (span: string) => /^(table|chart|slide|figure)/i.test(span);

function CompactList({ title, items }: { title: string; items: SourceTrialText[] }) {
  if (!items.length) return null;
  return <section className="rounded-xl border border-line bg-slate-50/70 px-3.5 py-2.5">
    <h4 className="mb-1.5 text-[12.5px] font-semibold text-ink-2">{title}</h4>
    <ul className="list-disc space-y-1 pl-4 text-[13px] leading-5 text-ink">
      {items.map((t, i) => <li key={i} className="whitespace-pre-wrap">{t.text}</li>)}
    </ul>
  </section>;
}

function cleanPending(items: string[]) {
  const real = items
    .filter((p) => !/^(图片辅助读取|原生图与模型稿核对|读图运行说明)/.test(p))
    .map((p) => p.replace(/^table-\d+[^：]*：/, "").trim())
    .filter(Boolean);
  return [...new Set(real)];
}

function buildTargets(record: SourceTrialRecord, preferredSpans: string[]) {
  const texts = [...record.metadata, ...record.purpose, ...record.common_conditions, ...record.quality,
    ...record.cost, ...record.follow_up, ...record.reported_results, ...record.review_notes];
  const citations = [...texts.flatMap((t) => t.evidence), ...record.time.evidence,
    ...record.groups.flatMap((g) => [...g.curve_evidence, ...g.formula.flatMap((f) => f.evidence),
      ...g.formula_notes.flatMap((t) => t.evidence), ...g.operations.flatMap((t) => t.evidence)])];
  const regions: ImageTarget[] = [];
  for (const g of record.groups) {
    const curvePages = new Set(g.curve_evidence.flatMap((x) => x.pages));
    const formulaPages = new Set(g.formula.flatMap((f) => f.evidence.flatMap((x) => x.pages)));
    const refs = [...g.curve_evidence, ...g.formula.flatMap((f) => f.evidence)];
    for (const c of refs) for (const page of [...c.pages].reverse()) {
      const span = rootSpan(c.span);
      if (!isVisualSpan(span) || regions.some((r) => r.span === span && r.page === page)) continue;
      const hasCurve = curvePages.has(page), hasFormula = formulaPages.has(page);
      const kindLabel = hasCurve && hasFormula ? "配方与升温曲线" : hasCurve ? "升温曲线" : "配方表";
      regions.push({ span, page, group: g.group, label: `${g.group}组${kindLabel}` });
    }
  }
  for (const c of citations) for (const page of [...c.pages].reverse()) {
    const span = rootSpan(c.span);
    if (isVisualSpan(span) && preferredSpans.includes(span) && !regions.some((r) => r.span === span && r.page === page))
      regions.push({ span, page, label: `图表区域 · 第${page}页` });
  }
  const labelCounts = new Map<string, number>();
  for (const r of regions) labelCounts.set(r.label, (labelCounts.get(r.label) ?? 0) + 1);
  for (const r of regions) if ((labelCounts.get(r.label) ?? 0) > 1) r.label = `${r.label} · 第${r.page}页`;
  const rank = (span: string) => preferredSpans.includes(span) ? preferredSpans.indexOf(span) : preferredSpans.length;
  regions.sort((a, b) => rank(a.span!) - rank(b.span!));
  const pages = [...new Set(citations.flatMap((c) => c.pages))].sort((a, b) => a - b);
  const options: ImageTarget[] = [...regions, ...pages.map((page) => ({ page, label: `第${page}页原页` }))];
  return { regions, options };
}

function TrialComparison({ record, preferredSpans, firstImage, children }: {
  record: SourceTrialRecord; preferredSpans: string[]; firstImage?: ImageResult | null; children?: React.ReactNode;
}) {
  const { me } = useApp();
  const [chosen, setChosen] = useState<ImageTarget | null>(null);
  const [group, setGroup] = useState<string | null>(null);
  const { regions, options } = buildTargets(record, preferredSpans);
  const image = chosen ?? options[0];
  const active = group ?? regions[0]?.group ?? record.groups[0]?.group;
  const g = record.groups.find((item) => item.group === active);
  const timeLines = [record.time.a, record.time.b, record.time.reported_saving].filter(Boolean);
  const notices = cleanPending(record.pending);

  return <div className="mt-3 grid items-start gap-5 lg:grid-cols-2">
    <div className="min-w-0 space-y-3">
      {children}
      <CompactList title="共同条件（面料 · 浴比 · 设备 · 流程）" items={record.common_conditions} />

      {!!record.groups.length && <section className="rounded-xl border border-line bg-white p-3.5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="试样组别">
            {record.groups.map((item) => <button key={item.group} type="button" aria-pressed={active === item.group}
              className={`rounded-lg border px-3 py-1.5 text-[12.5px] font-semibold transition ${active === item.group ? "border-accent bg-accent text-white" : "border-line bg-slate-50 text-ink-2 hover:bg-slate-100"}`}
              onClick={() => { setGroup(item.group); setChosen(regions.find((r) => r.group === item.group) ?? null); }}>
              {item.group}组 · {item.group === "A" ? "原工艺对照" : "试样工艺"}
            </button>)}
          </div>
          <span className="text-[11.5px] text-ink-3">切换组别同步切换右侧原图</span>
        </div>

        {g && <div className="space-y-3">
          {!!g.formula.length && <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full border-collapse text-left text-[12.5px]">
              <thead className="bg-slate-50 text-ink-2">
                <tr>{["配方原名", "数值", "原单位", "基准"].map((h) => <th key={h} className="border-b border-line px-3 py-1.5 font-semibold">{h}</th>)}</tr>
              </thead>
              <tbody>{g.formula.map((x, i) => <tr key={i} className="border-b border-line last:border-0">
                <td className="px-3 py-1.5 font-medium">{x.name}</td>
                <td className="px-3 py-1.5 tabular-nums font-semibold">{x.value}</td>
                <td className="px-3 py-1.5">{x.unit ?? <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11.5px] font-medium text-amber-800">未记载</span>}</td>
                <td className="px-3 py-1.5 text-ink-2">{x.basis ?? "未注明"}</td>
              </tr>)}</tbody>
            </table>
          </div>}

          {!!g.operations.length && <div className="rounded-lg border-l-4 border-accent bg-accent/5 px-3 py-2 text-[13px] leading-5">
            <p className="mb-0.5 text-[11.5px] font-semibold text-accent">现场操作与结果原文</p>
            {g.operations.map((op, i) => <p key={i} className="whitespace-pre-wrap">{op.text}</p>)}
          </div>}
        </div>}
      </section>}

      {(!!timeLines.length || !!record.quality.length) && <section className="rounded-xl border border-line bg-white px-3.5 py-2.5 text-[12.5px] leading-5">
        <h4 className="mb-1 font-semibold text-ink">时间与品质记录</h4>
        {timeLines.map((r, i) => r && <p key={i} className="text-ink-2">{r.group ? `${r.group}组` : "报告结果"}：{r.quote}</p>)}
        {record.time.calculated_saving !== null && <p className="font-medium">标注时间差值：{record.time.formula} = {record.time.calculated_saving}{record.time.unit}</p>}
        {record.quality.map((q, i) => <p key={`q-${i}`} className="mt-1 whitespace-pre-wrap">{q.text}</p>)}
      </section>}

      {!!notices.length && <section className="rounded-xl border border-amber-200 bg-amber-50/80 px-3.5 py-2.5 text-[12.5px] leading-5 text-amber-900">
        <h4 className="font-semibold">原件留意提示</h4>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">{notices.map((p, i) => <li key={i}>{p}</li>)}</ul>
      </section>}
    </div>

    <aside className="order-first min-w-0 space-y-2.5 lg:order-last">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-[13.5px] font-semibold">原件图表对照</h4>
        <span className="text-[11.5px] text-ink-3">共 {options.length} 视图</span>
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="依据图像切换">
        {options.map((option) => {
          const on = image?.span === option.span && image?.page === option.page;
          return <button key={`${option.span ?? "page"}:${option.page}`} type="button" aria-pressed={on}
            className={`rounded-lg border px-2.5 py-1 text-[12px] font-medium transition ${on ? "border-accent bg-accent/10 text-accent" : "border-line bg-white text-ink-2 hover:bg-slate-50"}`}
            onClick={() => { setChosen(option); if (option.group) setGroup(option.group); }}>{option.label}</button>;
        })}
      </div>
      {image ? <SourceImageCard key={`${me}:${record.source_id}:${image.span}:${image.page}`} docId={record.source_id} {...image}
        initialImage={firstImage && firstImage.page === image.page && (firstImage.span ?? undefined) === image.span ? firstImage : undefined} />
        : <p className="rounded-lg bg-slate-50 p-4 text-ink-2">这份记录没有已登记的页码，无法定位原图。</p>}
    </aside>
  </div>;
}

export function SourceTrial({ docId, autoLoad = false, preferredSpans = [], children, rawEvidence }: {
  docId: string; autoLoad?: boolean; preferredSpans?: string[]; children?: React.ReactNode;
  rawEvidence?: React.ReactNode;
}) {
  const { me } = useApp();
  const [record, setRecord] = useState<SourceTrialRecord | null>(null);
  const [firstImage, setFirstImage] = useState<ImageResult | null>(null);
  const [opened, setOpened] = useState(autoLoad);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setRecord(null); setFirstImage(null); setError(null);
    if (opened) api.sourceTrial(docId, me).then(async (data) => {
      const first = buildTargets(data, preferredSpans).options[0];
      const img = first ? await api.sourceImage(data.source_id, first.page, me, first.span).then((d) => d, () => null) : null;
      if (alive) { setFirstImage(img); setRecord(data); }
    }, (e: Error) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [docId, me, opened, reload]);
  return <section className="my-2 min-w-0 rounded-xl border border-line bg-white p-4 text-[13px] leading-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="font-semibold">试样资料审阅 · {docId}</h3>
      <div className="flex gap-2"><button type="button" className="btn btn-quiet" onClick={() => { setOpened(true); setReload(reload + 1); }}>
        {opened ? "重新读取" : "读取试样记录"}</button>
        {opened && !autoLoad && <button type="button" className="btn btn-quiet" onClick={() => setOpened(false)}>收起</button>}
      </div>
    </div>
    {opened && !record && !error && <div className="mt-3">{children}<p role="status" className="mt-2 text-ink-2">正在读取结构化条件与原图……</p></div>}
    {error && <div className="mt-3">{children}<p role="alert" className="mt-2 rounded-lg bg-amber-50 p-3 text-amber-800">{error}</p>{rawEvidence}</div>}
    {record && <TrialComparison key={`${me}:${docId}:${reload}`} record={record} preferredSpans={preferredSpans} firstImage={firstImage}>{children}</TrialComparison>}
  </section>;
}
