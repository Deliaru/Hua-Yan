// V12.9 契画布：一份报告的一生。一行八站，点开每一站都是这一局里的真对象（门面 report_life，只给研发，先过统一读取入口）：
// 资料库 → 读取 → 编译 → 契纳入 → 专业生效 → 四屏 → 使用与记分 → 变化。依据变化后挂起、撤下的能力和会话沿谱系标红。
// 第六站另有普通 RAG 对照：同一句话交 eval/rag_baseline 真跑一次，和化言这一局里的实际经过并排。
import { useState } from "react";
import { api } from "../api";
import { hhmm, useApp, useData, useLabels } from "../ctx";
import type { AliasCandidate, Capability, RagCompare, ReportLife } from "../types";
import { EmptyState, Group, PageHead } from "../components/ui";
import { SourceImage } from "../components/SourceImage";

const STATIONS = ["资料库", "读取", "编译", "契纳入", "专业生效", "四屏", "使用与记分", "变化"] as const;
const OUTCOME: Record<string, string> = {
  admitted: "进了候选", pending_evidence: "作为已有结论的补充依据，待确认", unaligned: "交人处理", dropped: "引文在原文里查不到，丢弃",
  duplicates: "与已有结论重复", conflicts: "与已有结论冲突，交人",
};
const FORM: Record<string, string> = { applicable: "适用", ask: "追问", statement: "可说的话", decrypt: "机理说明", phrase: "说法" };
const AUDIENCE = (a: number | string) => (typeof a === "number" ? `L${a}` : "指定客户");
const CHANGE = new Set(["evidence_changed", "capability_suspended", "recommendation_withdrawn", "capability_revoked", "claim_withdrawn"]);
const KIND: Record<string, string> = {
  claim_confirmed: "研发确认结论", capability_granted: "授予能力", scope_extended: "产品经理批准适用范围", capability_used: "能力被使用",
  evidence_changed: "原文依据变了", capability_suspended: "能力挂起", recommendation_withdrawn: "推荐撤下改道", capability_revoked: "能力撤销",
  claim_withdrawn: "结论撤回",
};
const DEFAULT_QUESTION = "深一块浅一块，纯涤的布，气流缸，135度保温";

function CapLine({ c, red }: { c: Capability; red?: boolean }) {
  const L = useLabels();
  const p = c.payload;
  const conds = Object.entries(p.conditions ?? {}).map(([s, v]) => `${L.slot(s)} ${v.join("/")}`);
  return <div className={`row !items-start text-[12.5px] ${red ? "bg-red-50" : ""}`}>
    <span className="w-[86px] shrink-0"><span className="tag tag-accent">{FORM[c.form] ?? c.form}</span> {AUDIENCE(c.audience)}</span>
    <span className="min-w-0 flex-1">
      {p.product_id && `${L.product(p.product_id)} · `}{p.phenomenon && `${L.phen(p.phenomenon)} · `}{conds.join("，")}
      {p.temperature_c && ` · ${p.temperature_c[0] === p.temperature_c[1] ? `${p.temperature_c[0]}℃` : `${p.temperature_c[0]}—${p.temperature_c[1]}℃`}`}
      {p.slot && `追问 ${L.slot(p.slot)}`}{p.text && `「${p.text}」`}
      {p.limits && <span className="mt-0.5 block whitespace-pre-wrap text-ink-2">限制原文：{p.limits.replace(/\n/g, "；")}</span>}
    </span>
    <span className={`shrink-0 ${c.status === "active" ? "text-ok" : c.status === "suspended" ? "text-danger" : "text-ink-2"}`}>
      {({ active: "生效", proposed: "待批准", suspended: "挂起", revoked: "已撤销" } as Record<string, string>)[c.status]}
      {c.approved_by && c.approved_by !== "seed" && ` · ${L.name(c.approved_by)}批准`}
    </span>
  </div>;
}

export function Canvas() {
  const { me, go } = useApp();
  const L = useLabels();
  const reports = useData(() => api.qiReports(me), [me]) ?? [];
  const [chosen, choose] = useState<string | null>(null);
  const doc = chosen ?? reports[0]?.doc_id ?? null;
  const life = useData(() => (doc ? api.reportLife(doc, me) : Promise.resolve(null)), [doc, me]);
  const [station, setStation] = useState(0);
  if (!reports.length) return <div className="mx-auto max-w-[1280px] px-8 pt-7">
    <EmptyState title="还没有你能读、又编译出过结论的报告" text="契画布按统一读取入口只列你有权读的报告；报告归属同层的其他研发时看不到。" /></div>;
  if (!life) return null;
  const changed = life.events.some((e) => CHANGE.has(e.kind));
  const red = new Set(life.events.filter((e) => CHANGE.has(e.kind)).map((e) => e.capability_id));
  const n = (k: string) => life.compiled.filter((r) => (r.report[k] ?? []).length).length;
  const summary = [
    life.library.library_docs ? `${life.library.docs} 份 · ${life.library.pages} 页` : `${life.library.docs} 份来源`,
    `${life.pages.length} 页 · 指纹`,
    `提出 ${life.compiled.length} · 进候选 ${n("admitted")} · 交人 ${n("unaligned")}`,
    `结论 ${life.units.length} · 能力 ${life.capabilities.length}`,
    `${[...new Set(life.capabilities.filter((c) => c.status !== "proposed").map((c) => `${FORM[c.form] ?? c.form}${AUDIENCE(c.audience)}`))].join(" / ") || "尚未生效"}`,
    "同一份报告，各身份所见",
    `用了 ${life.used.n} 次 · 替研发答 ${life.used.answered_for_rd} 单`,
    changed ? "改版 → 挂起 → 复核" : "依据未变",
  ];
  const openScreens = () => api.setSpotlight({ doc_id: life.doc.doc_id }).then(() => go("screens"));
  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-5 px-8 pb-24 pt-7">
      <PageHead title="契画布：一份报告的一生"
                subtitle="原件里的一句话怎样变成组织能力：读取侧留原件与指纹，契只收候选、经研发确认和授予才生效；之后每一次使用、每一次改版都记在这条谱系上。"
                aside={<select value={doc ?? ""} onChange={(e) => choose(e.target.value)}
                               className="w-[340px] max-w-[40%] shrink-0 rounded border border-line px-2 py-1 text-[13px]" aria-label="选一份报告">
                  {([["这一局的报告", false], ["资料库整批编译", true]] as const).map(([label, lib]) => {
                    const rows = reports.filter((r) => r.library === lib);
                    return rows.length > 0 && <optgroup key={label} label={`${label}（${rows.length} 份）`}>
                      {rows.map((r) => <option key={r.doc_id} value={r.doc_id}>{r.title}（{r.n_units} 条结论、{r.n_caps} 项能力）</option>)}
                    </optgroup>;
                  })}
                </select>} />
      <div className="grid grid-cols-8 gap-1.5">
        {STATIONS.map((s, i) => (
          <button key={s} type="button" onClick={() => setStation(i)}
                  className={`rounded-lg border px-2.5 py-2 text-left text-[12px] ${station === i ? "border-accent bg-sky-50" : "border-line bg-white"}
                    ${i === 7 && changed ? "!border-danger/50" : ""}`}>
            <span className="block text-[11px] text-ink-2">{"①②③④⑤⑥⑦⑧"[i]} {s}</span>
            <span className={`mt-0.5 block font-medium leading-4 ${i === 7 && changed ? "text-danger" : ""}`}>{summary[i]}</span>
          </button>
        ))}
      </div>
      {station === 0 && <Group title="资料库" foot="内部资料默认 L3、归属到人；读取只在统一入口按「来源类别 × 当前角色层级」检查一次。">
        <div className="row">这一局接入 {life.library.docs} 份来源（内部 {life.library.internal} 份）
          {life.library.library_docs > 0 && `；其中资料库 ${life.library.library_docs} 份、${life.library.pages} 页，扫描页已由视觉模型转写，待补读 ${life.library.pending} 页`}。</div>
        <div className="row">这份报告：{life.doc.title} · {life.doc.source} · L{life.doc.level} · 归属{L.name(life.doc.owner)}</div>
      </Group>}
      {station === 1 && <Reading life={life} />}
      {station === 2 && <Group title="编译：每条提议的核对结果" foot="编译只出候选结论与能力提议，从不降密；对不上原文、现象或条件的交人处理，不进契。">
        {life.compiled.map((r) => <div key={r.title} className="row !items-start text-[12.5px]">
          <span className="min-w-0 flex-1 font-medium">{r.title}</span>
          <span className="shrink-0 text-ink-2">{Object.entries(r.report).filter(([, v]) => v.length).map(([k, v]) =>
            k === "unaligned_details" ? (v as { reasons?: string[] }[]).flatMap((x) => x.reasons ?? []).join("、")
              : k === "unaligned" ? null : OUTCOME[k] ?? k).filter(Boolean).join("；")}</span>
        </div>)}
        {!life.compiled.length && <div className="row text-ink-2">这份报告的编译提议不是在这一局开局时导入的，核对结果没有记在这一局里。</div>}
      </Group>}
      {station === 2 && <Aliases />}
      {station === 3 && <Group title="契纳入：候选结论、能力提议与限制原文" foot="读不清、结构表达不了的条件留在限制原文里交研发，不当成「不限」。">
        {life.units.map((u) => <div key={u.id} className="row !items-start text-[12.5px]">
          <span className="w-[110px] shrink-0"><span className="tag">{u.status === "candidate" ? "候选" : u.status === "active" ? "已确认" : "已撤回"}</span> L{u.level}</span>
          <span className="min-w-0 flex-1">{u.title ?? `${L.name(u.owner)}的结论（同层归属，仅显示归属）`}
            {u.text && <span className="mt-0.5 block whitespace-pre-wrap text-ink-2">{u.text}</span>}</span>
        </div>)}
        {life.capabilities.map((c) => <CapLine key={c.id} c={c} red={red.has(c.id)} />)}
      </Group>}
      {station === 4 && <Group title="专业生效：确认绑定指纹、授予、批准" foot="确认、授予、范围批准都要有权的人签字；Agent 只能准备。">
        {life.units.filter((u) => u.confirmed_by).map((u) => <div key={u.id} className="row !items-start text-[12.5px]">
          <span className="w-[110px] shrink-0">{L.name(u.confirmed_by)}确认</span>
          <span className="min-w-0 flex-1 break-all text-ink-2">本次审过的依据指纹：{u.evidence.join("，")}</span></div>)}
        {life.events.filter((e) => ["claim_confirmed", "capability_granted", "scope_extended"].includes(e.kind)).map((e, i) =>
          <div key={i} className="row text-[12.5px]"><span className="w-[110px] shrink-0 text-ink-2">{hhmm(e.ts)}</span>
            <span>{L.name(e.actor)}：{KIND[e.kind]}{e.note ? `——${e.note}` : ""}</span></div>)}
        {life.capabilities.filter((c) => c.status !== "proposed").map((c) => <CapLine key={c.id} c={c} red={red.has(c.id)} />)}
      </Group>}
      {station === 5 && <>
        <Group title="四屏并排" foot="同一份报告、同一句话，每屏用自己的身份读，裁剪在服务端；游戏模式里四个窗口各选一个身份，跟着同一个焦点。">
          <div className="row"><button type="button" className="btn btn-plain" onClick={openScreens}>把这份报告设为四屏焦点并打开</button></div>
        </Group>
        <RagPanel />
      </>}
      {station === 6 && <Group title="使用与记分">
        <div className="row">这份报告授出的能力被使用 {life.used.n} 次，涉及 {life.used.sessions.length} 段会话；其中 {life.used.answered_for_rd} 单在进研发之前就答了。</div>
        <div className="row">记分：{Object.entries(life.points).map(([k, v]) => `${({ used: "被使用", cited: "被引用", contributed: "贡献", trial_pass: "试样通过", shared: "共享" } as Record<string, string>)[k] ?? k} ${v} 分`).join("，") || "还没有记分"}</div>
        {life.events.filter((e) => e.kind === "capability_used").map((e, i) => <div key={i} className="row text-[12.5px]">
          <span className="w-[110px] shrink-0 text-ink-2">{hhmm(e.ts)}</span><span>{L.name(e.actor)}的会话用上了这份判断</span></div>)}
      </Group>}
      {station === 7 && <Group title="变化：改版 → 挂起 → 撤下改道 → 复核 → 重匹配" foot="来源指纹变了，用过它的能力立刻停下等人复核；复核签字后重新生效，受影响的会话重新匹配。">
        {life.events.filter((e) => CHANGE.has(e.kind) || (e.kind === "claim_confirmed" && changed)).map((e, i) =>
          <div key={i} className={`row text-[12.5px] ${CHANGE.has(e.kind) ? "text-danger" : ""}`}>
            <span className="w-[110px] shrink-0">{hhmm(e.ts)}</span>
            <span>{KIND[e.kind]}{e.session_id ? `（${e.session_id.replace("sess:", "会话 ")}）` : ""}{e.kind === "claim_confirmed" ? `：${L.name(e.actor)}复核后保留` : ""}</span>
          </div>)}
        {!changed && <div className="row text-ink-2">这份报告的依据还没变过。</div>}
      </Group>}
    </div>
  );
}

function Reading({ life }: { life: ReportLife }) {
  const [page, setPage] = useState<number | null>(null);
  const library = life.library.library_docs > 0 && /^p\d+$/.test(life.pages[0]?.span ?? "");
  return <Group title="读取：原件的每一页与指纹" foot="原件、页面、读数与指纹留在读取侧，契的正式状态里只存指针；依据变了，指纹对不上，确认就要重来。">
    {life.pages.map((x) => <div key={x.span} className="row !items-start text-[12.5px]">
      <span className="w-[110px] shrink-0">{x.span} · {x.fingerprint.slice(0, 8)}</span>
      <span className="min-w-0 flex-1 line-clamp-2 whitespace-pre-wrap text-ink-2">{x.excerpt}</span>
      {library && <button type="button" className="link shrink-0" onClick={() => setPage(+x.span.slice(1))}>看原页</button>}
    </div>)}
    {page && <SourceImage docId={life.doc.doc_id} page={page} onClose={() => setPage(null)} />}
  </Group>;
}

function RagPanel() {
  const { me, fail } = useApp();
  const L = useLabels();
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [result, setResult] = useState<RagCompare | null>(null);
  const [busy, setBusy] = useState(false);
  const run = () => { setBusy(true); api.ragCompare(question, me).then(setResult, fail).finally(() => setBusy(false)); };
  return <Group title="普通 RAG 对照：同一批资料、同一个模型" foot="普通 RAG：资料库全部资料（内部 + 公开）进检索，前 5 页原文直接交模型作答，不经过觉、Jev、契与分层（eval/rag_baseline，caller baseline:rag）。">
    <div className="row gap-2">
      <input value={question} onChange={(e) => setQuestion(e.target.value)} className="flex-1 rounded border border-line px-2 py-1 text-[13px]" />
      <button type="button" className="btn btn-primary" disabled={busy || !question.trim()} onClick={run}>{busy ? "真跑中……" : "真跑一次"}</button>
    </div>
    {result && <div className="grid grid-cols-2 gap-4 px-4 py-3 text-[12.5px]">
      <div>
        <p className="font-semibold">普通 RAG 的回答 <span className="font-normal text-ink-2">（{result.rag.model}）</span></p>
        <p className="mt-1 whitespace-pre-wrap">{result.rag.answer || "（模型没有回答）"}</p>
        <p className="mt-2 text-ink-2">它检索到的：{result.rag.hits.map((h) => `${h.title} 第 ${h.page} 页（L${h.level}）`).join("；") || "没有命中（这一局没有接入资料库）"}</p>
      </div>
      <div>
        <p className="font-semibold">化言这一局里的实际经过</p>
        {result.huayan ? <>
          <p className="mt-1">走向：{result.huayan.path}</p>
          {result.huayan.story.map((l, i) => <p key={i} className="mt-0.5 text-ink-2">{hhmm(l.ts)} {l.subject === "human" || l.subject === "agent" ? L.name(l.who) : ""}{l.text}</p>)}
        </> : <p className="mt-1 text-ink-2">这一局还没有客户说过这句话。</p>}
      </div>
    </div>}
  </Group>;
}

// 动态别名：词表认不出的说法，模型提议是某个已有取值的另一种说法；研发确认（可改成同槽位的另一个取值）后成为 phrase 能力，
// 下一份报告编译、从需求单检索都认得它。模型会错（如「J 型染缸 → 卷染机」），所以逐条由研发签。
function Aliases() {
  const { me, meta, fail, refresh } = useApp();
  const L = useLabels();
  const rows = useData<AliasCandidate[] | null>(() => api.aliases(me).catch(() => null), [me]);
  const [pick, setPick] = useState<Record<string, string>>({});
  if (!rows?.length) return null;
  const confirm = (r: AliasCandidate) => api.confirmAlias(r.text, r.slot, pick[r.text] ?? r.value, me).then(refresh, fail);
  return <Group title={`动态别名：整批编译认不出的说法（${rows.filter((r) => r.confirmed).length}/${rows.length} 已确认）`}
                foot="只列出自你能读的资料的说法；确认一次 = 一条你签的结论 + 一项研发层的「说法」能力。">
    {rows.map((r) => <div key={`${r.text}|${r.slot}`} className="row !items-start text-[12.5px]">
      <span className="min-w-0 flex-1"><span className="font-medium">「{r.text}」</span> → {L.slot(r.slot)}
        <span className="mt-0.5 block text-ink-2">{r.reason}（见于 {r.docs.length} 份）</span></span>
      {r.confirmed ? <span className="shrink-0 text-ok">已确认为「{r.confirmed}」</span> : <span className="flex shrink-0 gap-1.5">
        <select value={pick[r.text] ?? r.value} onChange={(e) => setPick({ ...pick, [r.text]: e.target.value })}
                className="rounded border border-line px-1 py-0.5">
          {meta.slots.find((s) => s.id === r.slot)?.values.map((v) => <option key={v}>{v}</option>)}
        </select>
        <button type="button" className="btn btn-plain" onClick={() => confirm(r)}>确认</button>
      </span>}
    </div>)}
  </Group>;
}
