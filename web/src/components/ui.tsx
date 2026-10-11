// 共用的小组件：分组、行、标记、可展开小节、签字按钮。规范见 index.css 顶部。
import { useState } from "react";
import { useApp, scoreText, isModel, useLabels } from "../ctx";
import type { Question } from "../types";
import { ChevronRight } from "./Icons";

export function PageHead({ title, subtitle, aside }: { title: string; subtitle?: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold leading-7 tracking-[-0.01em]">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] text-ink-2">{subtitle}</p>}
      </div>
      {aside}
    </div>
  );
}

// 分组：标题写在分组外上方，脚注写在下方（系统设置风格）。
export function Group({ title, aside, foot, children, className = "" }: {
  title?: React.ReactNode; aside?: React.ReactNode; foot?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={className}>
      {(title || aside) && (
        <div className="group-title flex items-baseline justify-between gap-3">
          <span>{title}</span>{aside && <span className="font-normal">{aside}</span>}
        </div>
      )}
      <div className="group">{children}</div>
      {foot && <p className="group-foot">{foot}</p>}
    </section>
  );
}

export const Empty = ({ children }: { children: React.ReactNode }) => (
  <div className="row text-[13px] text-ink-2">{children}</div>
);

export function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex flex-col items-center py-24 text-center">
      <p className="text-[17px] font-semibold">{title}</p>
      <p className="mt-1.5 max-w-[380px] text-[13px] leading-5 text-ink-2">{text}</p>
    </div>
  );
}

export function SideHead({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return <div className="side-head"><span>{children}</span>{aside}</div>;
}

// 「Agent 起草」：草稿未经人修改
export const AgentMark = ({ who = "Agent 起草" }: { who?: string }) => <span className="tag tag-agent">{who}</span>;

// 觉的打分：模型打分显示概率与细条，规则打分显示「到点」（不冒充概率）
export function Score({ q }: { q: Pick<Question, "p_need" | "scored_by"> }) {
  const L = useLabels();
  if (!isModel(q.scored_by) || q.p_need == null) return <span className="tag" title="规则前置条件成立">规则 · 到点</span>;
  return (
    <span className="flex shrink-0 items-center gap-1.5" title={`${L.scorer(q.scored_by)} 打分`}>
      <span className="h-[3px] w-8 overflow-hidden rounded-full bg-fill">
        <span className="block h-full rounded-full bg-attn" style={{ width: scoreText(q) }} />
      </span>
      <span className="num text-[12px] font-semibold text-attn-ink">{scoreText(q)}</span>
      <span className="text-[11px] text-ink-3">{L.scorer(q.scored_by)}</span>
    </span>
  );
}

export function Disclosure({ label, children, initial = false }: { label: React.ReactNode; children: React.ReactNode; initial?: boolean }) {
  const [open, setOpen] = useState(initial);
  return (
    <div className="mt-1">
      <button type="button" onClick={() => setOpen(!open)} className="link"><ChevronRight open={open} />{label}</button>
      {open && <div className="anim-fade mt-1.5 flex flex-col gap-1 pl-4">{children}</div>}
    </div>
  );
}

// 签字按钮：直接调门面原子方法；门面拒绝时把它给的原因显示在按钮旁，不在前端自己算可签条件。
export function Act({ label, run, kind = "primary", disabled }: {
  label: string; run: () => Promise<unknown>; kind?: "primary" | "plain" | "quiet" | "chip"; disabled?: boolean;
}) {
  const { refresh } = useApp();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = () => {
    setBusy(true);
    setErr(null);
    run().then(refresh, (e) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button type="button" disabled={busy || disabled} onClick={go} className={kind === "chip" ? "chip" : `btn btn-${kind}`}>{busy ? "处理中……" : label}</button>
      {err && <span role="alert" className="text-[12px] text-danger">{err}</span>}
    </span>
  );
}

// 多行输入（草稿、理由）
export function Field({ value, onChange, placeholder, rows = 2, label }: {
  value: string; onChange: (v: string) => void; placeholder?: string; rows?: number; label?: string;
}) {
  return (
    <textarea aria-label={label ?? placeholder} value={value} rows={rows} placeholder={placeholder}
              onChange={(e) => onChange(e.target.value)} className="field" />
  );
}

// 按「。；！？\n」切句，与 LeakHit.index 的切法一致（契约 ⑦）
export function splitSentences(text: string) {
  return text.match(/[^。；！？\n]+[。；！？\n]?/g) ?? [];
}

// 命中泄密检查的句子画红色下划线
export function Marked({ text, hits }: { text: string; hits: number[] }) {
  return (
    <>
      {splitSentences(text).map((s, i) => (
        <span key={i} className={hits.includes(i) ? "leak" : undefined}>{s}</span>
      ))}
    </>
  );
}
