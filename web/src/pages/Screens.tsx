// V12.9 四屏并排：同一句话、同一份报告，不同身份看到的不一样。焦点（一句话、一份报告）存在服务端，几个窗口跟着同一个焦点。
// 检索层：同一句话按各自身份在资料库里检索（统一入口先划范围）；能力层：同一份报告编译出的能力，各身份按知识库的可见规则看到哪些。
// 演示模式一屏并排四列，每列带上那个身份去读；游戏模式里身份由服务端认定，每个窗口只显示自己，四个窗口并排就是四屏。
import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { Capability } from "../types";
import { Group, PageHead } from "../components/ui";

const SEARCHERS = ["rd:R01", "rd:R02", "sales:S01"];
const HOLDERS = ["rd:R02", "pm:agent", "sales:S01", "customer:C02"];
const FORM: Record<string, string> = { applicable: "适用", ask: "追问", statement: "可说的话", decrypt: "机理说明", phrase: "说法" };

function useSpotlight() {
  const [s, setS] = useState<{ query: string; doc_id: string | null }>({ query: "", doc_id: null });
  useEffect(() => {
    const load = () => api.spotlight().then(setS, () => {});
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, []);
  return [s, (p: { query?: string; doc_id?: string | null }) => api.setSpotlight(p).then(setS)] as const;
}

function Searched({ who, query }: { who: string; query: string }) {
  const L = useLabels();
  const r = useData(() => (query ? api.sourceSearch(query, who) : Promise.resolve(null)), [query, who]);
  return <Group title={`${L.name(who)} 搜到的`}>
    {!query && <div className="row text-ink-2">还没有焦点句子</div>}
    {r?.hits.slice(0, 6).map((h) => <div key={h.pointer} className="row !items-start text-[12.5px]">
      <span className="min-w-0 flex-1"><span className="font-medium">{h.title}</span> 第 {h.page} 页
        <span className="mt-0.5 block line-clamp-2 text-ink-2">{h.excerpt.replace(/^【模型转写[^】]*】\n/, "")}</span></span>
      <span className="shrink-0 text-ink-2">L{h.level}</span>
    </div>)}
    {r && !r.hits.length && <div className="row text-ink-2">在能读的资料里没有命中</div>}
  </Group>;
}

function CapText({ c }: { c: Capability }) {
  const L = useLabels();
  const p = c.payload;
  return <div className="row !items-start text-[12.5px]">
    <span className="w-[64px] shrink-0"><span className="tag tag-accent">{FORM[c.form] ?? c.form}</span></span>
    <span className="min-w-0 flex-1">{p.product_id && `${L.product(p.product_id)} · `}
      {Object.entries(p.conditions ?? {}).map(([s, v]) => `${L.slot(s)} ${v.join("/")}`).join("，")}
      {p.temperature_c && ` · ${p.temperature_c[0]}${p.temperature_c[0] === p.temperature_c[1] ? "" : `—${p.temperature_c[1]}`}℃`}
      {p.text && `「${p.text}」`}
      {p.limits && <span className="mt-0.5 block text-ink-2">限制：{p.limits.replace(/\n/g, "；")}</span>}</span>
  </div>;
}

function Holding({ who, doc }: { who: string; doc: string | null }) {
  const L = useLabels();
  const v = useData(() => (doc ? api.capabilityView(doc, who) : Promise.resolve(null)), [doc, who]);
  return <Group title={`${L.name(who)} 看到的（L${v?.level ?? "—"}）`}>
    {!doc && <div className="row text-ink-2">还没有焦点报告</div>}
    {v?.units.map((u) => <div key={u.id} className="row !items-start text-[12.5px]"><span className="min-w-0 flex-1">
      <span className="tag">结论原文</span> {u.title}<span className="mt-0.5 block whitespace-pre-wrap text-ink-2">{u.text}</span></span></div>)}
    {v?.capabilities.map((c) => <CapText key={c.id} c={c} />)}
    {v && !v.units.length && !v.capabilities.length && <div className="row text-ink-2">这一层还没有可用的能力</div>}
  </Group>;
}

export function Screens() {
  const { me, meta } = useApp();
  const [s, set] = useSpotlight();
  const [draft, setDraft] = useState<string | null>(null);
  const reports = useData(() => (me.startsWith("rd:") ? api.qiReports(me) : Promise.resolve([])), [me]) ?? [];
  const solo = !!meta.trial;           // 游戏模式：身份固定，每个窗口一屏
  const searchers = solo ? [me] : SEARCHERS;
  const holders = solo ? [me] : HOLDERS;
  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5 px-8 pb-24 pt-7">
      <PageHead title="四屏并排：同一句话、同一份报告，各身份所见不同"
                subtitle={solo ? "这个窗口按你的身份读；另开几个窗口选别的身份，跟着同一个焦点，就是四屏。" : "每一列带上那个身份去读，裁剪全在服务端；界面不做权限判断。"} />
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (draft != null) set({ query: draft.trim() }); }}>
        <input value={draft ?? s.query} onChange={(e) => setDraft(e.target.value)} placeholder="焦点句子，如：气流缸 133度 涤纶 色花"
               className="flex-1 rounded border border-line px-2 py-1 text-[13px]" />
        <button type="submit" className="btn btn-plain">设为焦点</button>
        {!!reports.length && <select value={s.doc_id ?? ""} onChange={(e) => set({ doc_id: e.target.value })} className="rounded border border-line px-2 py-1 text-[13px]">
          <option value="" disabled>焦点报告</option>
          {reports.map((r) => <option key={r.doc_id} value={r.doc_id}>{r.title}</option>)}
        </select>}
      </form>
      <p className="group-title">检索层：同一句话，各自搜到的</p>
      <div className={`grid gap-4 ${solo ? "" : "grid-cols-3"}`}>{searchers.map((w) => <Searched key={w} who={w} query={s.query} />)}</div>
      <p className="group-title">能力层：同一份报告，各自看到的</p>
      <div className={`grid gap-4 ${solo ? "" : "grid-cols-4"}`}>{holders.map((w) => <Holding key={w} who={w} doc={s.doc_id} />)}</div>
    </div>
  );
}
