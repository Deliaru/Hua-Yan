// 共用的小组件：分组、行、标记、可展开小节、签字按钮。规范见 index.css 顶部。
import { useState } from "react";
import { useApp, scoreText, isModel, useLabels } from "../ctx";
import type { Question, TemperatureFill } from "../types";
import { ChevronRight } from "./Icons";

export function TemperatureCondition({ value }: { value: TemperatureFill | null }) {
  const range = value?.celsius;
  return (
    <div className="border-b border-sep px-5 py-3.5">
      <p className="eyebrow">工艺温度</p>
      <p className="mt-0.5 text-[16px] font-semibold">{range
        ? range[0] === range[1] ? `${range[0]}℃` : `${range[0]}—${range[1]}℃`
        : value ? "温度待补充" : "尚未提供"}</p>
      {value && <p className="mt-1 text-[12px] text-ink-2">「{value.quote}」</p>}
    </div>
  );
}

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

// 分级标识：L1 场景语言 / L2 产品需求语言 / L3 化学语言（颜色与架构总览的回流色带一致）
export const LAYER_NAME = { 1: "场景语言", 2: "产品需求语言", 3: "化学语言" } as const;
const LAYER_COLOR = { 1: "#2a9fd0", 2: "#5b7cfa", 3: "#9b4fe0" } as const;

export function LayerChip({ layer }: { layer: 1 | 2 | 3 }) {
  const c = LAYER_COLOR[layer];
  return (
    <span className="inline-flex h-5 shrink-0 items-center gap-1 rounded-[5px] px-1.5 text-[11.5px] font-semibold"
          style={{ color: c, background: `${c}17`, boxShadow: `inset 0 0 0 1px ${c}33` }}>
      L{layer}<span className="font-normal">· {LAYER_NAME[layer]}</span>
    </span>
  );
}

export function LayerNote({ layer, children }: { layer: 1 | 2 | 3; children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-[12.5px] leading-5 text-ink-2">
      <LayerChip layer={layer} /><span className="min-w-0">{children}</span>
    </p>
  );
}

// 回放部署的如实说明（状态菜单、架构总览、演示工作面共用）
export const RECORDING_NOTE = "现有回放基于自部署 OneJev、gemini-3.8-flash-high 真实录制。如需真实在线试用，可点右上角运行状态里的「接入自己的模型」，用你的大模型（与可选的 OneJev）密钥真实运行；也可自行部署并接入 Jev 与大模型网关，Jue-K 模型已在仓库中提供。";

export function ReplayNote() {
  const { meta } = useApp();
  if (!meta.status.replay) return null;
  return (
    <p className="flex items-start gap-2 rounded-[10px] bg-fill px-3.5 py-2.5 text-[12.5px] leading-5 text-ink-2">
      <span className="tag shrink-0">录制回放</span><span>{RECORDING_NOTE}</span>
    </p>
  );
}

// 「Agent 起草」：草稿未经人修改
// Agent 离线时草稿由规则骨架生成，标「离线 · 规则生成」而不是「Agent 起草」（铁律 6：降级必须标注）
export function AgentMark({ who = "Agent 起草" }: { who?: string }) {
  const { agentOnline, meta } = useApp();
  if (!agentOnline) return <span className="tag tag-warn" title="Agent 离线，这段由规则骨架生成">离线 · 规则生成</span>;
  return <span className="tag tag-agent" title={meta.status.replay ? "录制回放：这段是录制时 Agent 的真实输出" : undefined}>{who}</span>;
}

// 觉的打分：模型打分显示概率与细条，规则打分显示「到点」（不冒充概率）
// 异常类决策（决策目录 kind: anomaly）：规则打分命中阈值才提出；其余推进类到点即提出
export const ANOMALY = new Set(["distortion", "seal_leak", "knowledge_conflict", "leak_risk", "qi_review"]);

export function Score({ q }: { q: Pick<Question, "p_need" | "scored_by" | "family"> }) {
  const L = useLabels();
  if (q.scored_by === "human") return <span className="tag" title="由人发起，不经觉打分">人工提出</span>;
  if (!isModel(q.scored_by) || q.p_need == null) return ANOMALY.has(q.family)
    ? <span className="tag" title="规则打分超过阈值">规则 · 命中</span>
    : <span className="tag" title="上一步已签字，规则到点即提出">规则 · 到点</span>;
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
      <button type="button" onClick={() => setOpen(!open)} className="link !items-start text-left"><span className="pt-[3px]"><ChevronRight open={open} /></span>{label}</button>
      {open && <div className="anim-fade mt-1.5 flex flex-col gap-1 pl-4">{children}</div>}
    </div>
  );
}

// 签字按钮：直接调门面原子方法；门面拒绝时把它给的原因显示在按钮旁，不在前端自己算可签条件。
// done：成功后按钮换成这句话（用于签字后对象状态不在本人视图里的动作，如申请解密）
export function Act({ label, run, kind = "primary", disabled, done, glow }: {
  label: string; run: () => Promise<unknown>; kind?: "primary" | "plain" | "quiet" | "chip"; disabled?: boolean; done?: string; glow?: boolean;
}) {
  const { refresh } = useApp();
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = () => {
    setBusy(true);
    setErr(null);
    run().then(() => { setOk(true); refresh(); }, (e) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
  };
  if (ok && done) return <span className="text-[12px] text-ink-2">{done}</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <button type="button" disabled={busy || disabled} onClick={go} className={`${kind === "chip" ? "chip" : `btn btn-${kind}`} ${glow ? "glow" : ""}`}>{busy ? "处理中……" : label}</button>
      {err && <span role="alert" className="text-[12px] text-danger">{err}</span>}
    </span>
  );
}

// 多行输入（草稿、理由）
// 缺失条件勾选：试样失败（需求条件缺失）与客户评价不通过共用
export function SlotPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const { meta } = useApp();
  return (
    <div className="flex flex-wrap gap-1.5">
      {meta.slots.map((s) => (
        <button key={s.id} type="button" className={`chip ${value.includes(s.id) ? "tag-attn" : ""}`}
          onClick={() => onChange(value.includes(s.id) ? value.filter((x) => x !== s.id) : [...value, s.id])}>{s.label}</button>
      ))}
    </div>
  );
}

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
