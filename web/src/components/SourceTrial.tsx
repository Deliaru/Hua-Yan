import { useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import type { SourceCitation, SourceTrialRecord, SourceTrialText } from "../types";
import { Act } from "./ui";
import { SourceImage } from "./SourceImage";

type ViewImage = (span: string, page: number) => void;

function Citations({ items, onView }: { items: SourceCitation[]; onView: ViewImage }) {
  if (!items.length) return null;
  return <details className="mt-1 text-[12px] text-ink-2">
    <summary className="cursor-pointer">查看依据与出处（{items.length}）</summary>
    {items.map((c, i) => <div key={i} className="mt-2">
      <p className="break-all">{c.fragment} · 页{c.pages.join("、")}{c.cell && ` · r${c.cell[0]}c${c.cell[1]}`}</p>
      <pre className="whitespace-pre-wrap font-sans">{c.quote}</pre>
      <div className="mt-1 flex flex-wrap gap-2">{c.pages.map((page) => <button key={page} type="button"
        className="btn btn-quiet" onClick={() => onView(c.span, page)}>查看第{page}页／区域</button>)}</div>
    </div>)}
  </details>;
}

function Texts({ title, items, onView }: { title: string; items: SourceTrialText[]; onView: ViewImage }) {
  if (!items.length) return null;
  return <div className="mt-3"><h4 className="font-semibold">{title}</h4>
    {items.map((t, i) => <div key={i} className="mt-2"><p className="whitespace-pre-wrap">{t.text}</p><Citations items={t.evidence} onView={onView} /></div>)}
  </div>;
}

export function SourceTrial({ docId }: { docId: string }) {
  const { me } = useApp();
  const [record, setRecord] = useState<SourceTrialRecord | null>(null);
  const [target, setTarget] = useState<{ span: string; page: number } | null>(null);
  const view: ViewImage = (span, page) => setTarget({ span, page });
  return <div className="my-3 rounded-lg border border-line p-3 text-[13px] leading-5">
    <div className="flex flex-wrap items-center gap-3">
      <span className="break-all">试样资料：{docId}</span>
      <Act kind="plain" label={record ? "重新读取试样记录" : "读取试样记录"} run={async () => {
        setRecord(null); setRecord(await api.sourceTrial(docId, me));
      }} />
      {record && <button type="button" className="btn btn-quiet" onClick={() => setRecord(null)}>收起</button>}
    </div>
    {record && <div className="mt-3">
      <p className="text-ink-2">L{record.level} · 规则整理 · 读取草稿。读取不代表专业确认、用途授予或产品适用判断。</p>
      <Texts title="报告信息" items={record.metadata} onView={view} />
      <Texts title="试样目的" items={record.purpose} onView={view} />
      <Texts title="共同条件" items={record.common_conditions} onView={view} />
      {record.groups.map((g) => <details key={g.group} open className="mt-4 border-t border-line pt-3">
        <summary className="cursor-pointer font-semibold">{g.group}组条件与观察</summary>
        {!!g.formula.length && <div className="mt-2 overflow-x-auto"><table className="w-full text-left">
          <thead><tr><th>配方原名</th><th>数值</th><th>原单位</th><th>基准原文</th></tr></thead>
          <tbody>{g.formula.map((x, i) => <tr key={i} className="border-t border-line align-top">
            <td className="py-2 pr-3">{x.name}<Citations items={x.evidence} onView={view} /></td><td className="pr-3">{x.value}</td>
            <td className="pr-3">{x.unit ?? "未记载"}</td><td>{x.basis ?? "未注明"}</td>
          </tr>)}</tbody>
        </table></div>}
        <Texts title="配方说明／原对象及列" items={g.formula_notes} onView={view} />
        {!!g.curve_labels.length && <div className="mt-3"><h4 className="font-semibold">已读曲线标签</h4>
          <p className="text-ink-2">以下按读取记录列出，不代表曲线连线或工艺执行顺序。</p>
          {g.curve_labels.map((r, i) => <p key={i} className="mt-1 whitespace-pre-wrap">
            {r.stage ?? "阶段待判断"} · {r.value}{r.unit}{r.conditions.length ? ` · ${r.conditions.join("；")}` : ""}
            {r.status === "needs_reading" && " · 待补读"} · 原文：{r.quote} · {r.span}
          </p>)}
        </div>}
        <Citations items={g.curve_evidence} onView={view} />
        <Texts title="现场操作原文" items={g.operations} onView={view} />
      </details>)}
      <div className="mt-4 border-t border-line pt-3"><h4 className="font-semibold">时间对照</h4>
        {[record.time.a, record.time.b, record.time.reported_saving].map((r, i) => r && <p key={i}>
          {r.group ? `${r.group}组` : "报告结果"} · {r.quote}
        </p>)}
        <p>{record.time.calculated_saving !== null ? `标注时间差值：${record.time.formula} = ${record.time.calculated_saving}${record.time.unit}` : "未记载可比较的完整A/B总时长。"}</p>
        <p className="text-ink-2">{record.time.basis}</p><Citations items={record.time.evidence} onView={view} />
      </div>
      <Texts title="品质观察" items={record.quality} onView={view} />
      <Texts title="成本原文" items={record.cost} onView={view} />
      <Texts title="报告结果与分析原文" items={record.reported_results} onView={view} />
      <Texts title="后续工作原文" items={record.follow_up} onView={view} />
      <Texts title="整理核对备注" items={record.review_notes} onView={view} />
      {!!record.pending.length && <div className="mt-3"><h4 className="font-semibold">待补读与判断</h4>
        <ul className="list-disc space-y-1 pl-5">{record.pending.map((p, i) => <li key={i}>{p}</li>)}</ul>
      </div>}
    </div>}
    {target && <SourceImage key={`${me}:${docId}:${target.span}:${target.page}`} docId={docId}
      span={target.span} page={target.page} onClose={() => setTarget(null)} />}
  </div>;
}
