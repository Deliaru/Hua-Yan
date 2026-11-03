// V12.3 资料库检索：研发在需求单上看本单 Agent 检索过什么、命中了哪几页，也可以自己检索。
// 只能检索到自己有权读的资料（门面按统一入口先筛）；扫描页是模型转写，数值和表格用「单独问图」核对，对不上时两个都看。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";
import type { SourceHit, SourceImageAnswer, SourceSearch } from "../types";
import { SourceImage } from "./SourceImage";

const TRANSCRIBED = "【模型转写";

function Hit({ hit }: { hit: SourceHit }) {
  const { me } = useApp();
  const [image, setImage] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<SourceImageAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const transcribed = hit.excerpt.startsWith(TRANSCRIBED);
  const ask = () => {
    setBusy(true); setErr(null);
    api.sourceAskImage(hit.doc_id, hit.page, question, me).then(setAnswer, (e: Error) => setErr(e.message)).finally(() => setBusy(false));
  };
  return <li className="rounded-lg border border-line px-3 py-2">
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-medium">{hit.title}</span>
      <span className="text-ink-2">第 {hit.page} 页 · L{hit.level}</span>
      {hit.keyword_rank && <span className="chip">关键词第 {hit.keyword_rank}</span>}
      {hit.semantic_rank && <span className="chip">语义第 {hit.semantic_rank}</span>}
      {transcribed && <span className="chip tag-attn">扫描页 · 模型转写</span>}
      <button type="button" className="link" onClick={() => setImage(true)}>看原页</button>
    </div>
    <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[12.5px] text-ink-2">{transcribed ? hit.excerpt.split("\n").slice(1).join("\n") : hit.excerpt}</p>
    {!!hit.queries && hit.queries.length > 1 && <p className="text-[12px] text-ink-2">{hit.queries.length} 种问法都找到了这一页</p>}
    {!!hit.neighbors.length && <details className="mt-1 text-[12px] text-ink-2">
      <summary className="cursor-pointer">前后页（续表、续段常在这里）</summary>
      {hit.neighbors.map((n) => <p key={n.page} className="mt-1 line-clamp-2 whitespace-pre-wrap">第 {n.page} 页：{n.excerpt.replace(/^【模型转写[^】]*】\n/, "")}</p>)}
    </details>}
    <div className="mt-1.5 flex flex-wrap items-center gap-2">
      <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="单独问原图，如：表 3-1 里 Zn²⁺ 那一行的 λmax"
        className="min-w-[260px] flex-1 rounded border border-line px-2 py-1 text-[12.5px]" />
      <button type="button" className="btn btn-quiet" disabled={busy || !question.trim()} onClick={ask}>{busy ? "读图中……" : "单独问图"}</button>
    </div>
    {err && <p role="alert" className="text-[12px] text-danger">{err}</p>}
    {answer && <p className="mt-1 whitespace-pre-wrap rounded bg-slate-50 px-2 py-1.5 text-[12.5px]">
      <span className="text-ink-2">{answer.read_by}：</span>{answer.answer}
    </p>}
    {image && <SourceImage docId={hit.doc_id} page={hit.page} onClose={() => setImage(false)} />}
  </li>;
}

export function LibrarySearch({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const trace = useData(() => api.agentTrace(`conv:${me}:${reqId}`, me), [reqId, me]);
  const asked = [...new Set((trace ?? []).filter((s) => s.tool === "search_sources").map((s) => String(s.args.query)))];
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<{ query: string; data: SourceSearch } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = (q: string) => {
    setErr(null);
    api.sourceSearch(q, me, reqId).then((data) => setResult({ query: q, data }), (e: Error) => setErr(e.message));
  };
  return <section className="rounded-xl border border-line bg-white p-5 text-[13px]">
    <h3 className="font-semibold">资料库检索</h3>
    <p className="mt-1 text-ink-2">只在你有权读的资料里检索；命中只是依据，存进本单后仍要你确认。</p>
    {!!asked.length && <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="text-ink-2">研发 Agent 在本单检索过：</span>
      {asked.map((q) => <button key={q} type="button" className={`chip ${result?.query === q ? "tag-attn" : ""}`} onClick={() => run(q)}>{q}</button>)}
    </div>}
    <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (query.trim()) run(query.trim()); }}>
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="用客户的说法或专业说法都可以，如：气流缸 颜色不匀"
        className="flex-1 rounded border border-line px-2 py-1" />
      <button type="submit" className="btn btn-plain">检索</button>
    </form>
    {err && <p role="alert" className="mt-1 text-[12px] text-danger">{err}</p>}
    {result && <div className="mt-3">
      <p className="text-ink-2">「{result.query}」命中 {result.data.hits.length} 页，按关键词与语义两路名次融合排序{result.data.note && `；${result.data.note}`}</p>
      {!!result.data.queries && result.data.queries.length > 1 && <p className="text-[12px] text-ink-2">
        同时用本单的说法查了：{result.data.queries.slice(1).map((x) => `「${x}」`).join("、")}</p>}
      <ul className="mt-2 flex flex-col gap-2">{result.data.hits.map((h) => <Hit key={h.pointer} hit={h} />)}</ul>
    </div>}
  </section>;
}
