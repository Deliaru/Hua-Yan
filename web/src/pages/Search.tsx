// 资料检索：单独一页。左边命中列表（关键词与语义两路），右边直接看原页图像，可前后翻页、单独问图。
// 只能检索到自己有权读的资料（门面按统一入口先筛）。
import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import type { SourceHit, SourceImage, SourceImageAnswer, SourceSearch } from "../types";
import { PageHead } from "../components/ui";

const TRANSCRIBED = /^【模型转写[^】]*】\n/;
const EXAMPLES = ["TF-213HE 试样工艺曲线", "气流缸 颜色不匀", "涤纶 133℃ 保温", "锦纶 固色 渗色沾色"];

// 摘录里把查询的词标出来
function Mark({ text, query }: { text: string; query: string }) {
  const words = query.split(/\s+/).filter((w) => w.length > 1);
  if (!words.length) return <>{text}</>;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "g");
  return <>{text.split(re).map((x, i) => i % 2 ? <mark key={i} className="rounded bg-amber-100 px-0.5">{x}</mark> : x)}</>;
}

function Viewer({ hit }: { hit: SourceHit }) {
  const { me } = useApp();
  const [page, setPage] = useState(hit.page);
  const [image, setImage] = useState<SourceImage | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<SourceImageAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setPage(hit.page), [hit.pointer]);
  useEffect(() => {
    setImage(null); setErr(null); setAnswer(null);
    api.sourceImage(hit.doc_id, page, me).then(setImage, (e: Error) => setErr(e.message));
  }, [hit.doc_id, page, me]);
  const ask = () => {
    setBusy(true); setErr(null);
    api.sourceAskImage(hit.doc_id, page, question, me).then(setAnswer, (e: Error) => setErr(e.message)).finally(() => setBusy(false));
  };
  return <div className="sticky top-[110px] flex max-h-[calc(100vh-130px)] flex-col gap-2 overflow-auto rounded-xl border border-line bg-white p-4">
    <div className="flex items-center gap-2">
      <b className="min-w-0 flex-1 truncate">{hit.title}</b>
      <button className="btn btn-plain" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
      <span className="num text-[13px]">第 {page} 页</span>
      <button className="btn btn-plain" onClick={() => setPage(page + 1)}>下一页</button>
    </div>
    {!image && !err && <p className="text-ink-2">正在读取原页……</p>}
    {err && <p role="alert" className="text-danger">{err}</p>}
    {image && <img src={image.image_url} width={image.width} height={image.height} alt={`${hit.title} 第 ${page} 页原页`} className="h-auto w-full rounded border border-line" />}
    <div className="flex gap-2">
      <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="对着这一页问，如：保温段是多少度、多少分钟"
        className="min-w-0 flex-1 rounded border border-line px-2 py-1 text-[13px]" />
      <button className="btn btn-quiet" disabled={busy || !question.trim()} onClick={ask}>{busy ? "读图中……" : "问这一页"}</button>
    </div>
    {answer && <p className="whitespace-pre-wrap rounded bg-slate-50 px-2 py-1.5 text-[13px]"><span className="text-ink-2">{answer.read_by}：</span>{answer.answer}</p>}
  </div>;
}

export function Search() {
  const { me } = useApp();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<{ query: string; data: SourceSearch } | null>(null);
  const [pick, setPick] = useState<SourceHit | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = (q: string) => {
    setQuery(q); setErr(null); setBusy(true);
    api.sourceSearch(q, me).then((data) => { setResult({ query: q, data }); setPick(data.hits[0] ?? null); }, (e: Error) => setErr(e.message))
      .finally(() => setBusy(false));
  };
  return <div className="mx-auto flex max-w-[1400px] flex-col gap-4 px-8 pb-24 pt-7">
    <PageHead title="资料检索" subtitle={<>在企业资料库（试样报告、说明书、MSDS、化验单）里找原文，右边直接看原页。只搜你这个岗位有权读的资料，没权读的不会出现（试样报告原件归研发）。</>} />
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (query.trim()) run(query.trim()); }}>
      <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="产品型号、现象、条件都可以，如：TF-213HE 试样工艺曲线"
        className="flex-1 rounded-lg border border-line px-3 py-2 text-[15px]" />
      <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "检索中……" : "检索"}</button>
    </form>
    <div className="flex flex-wrap items-center gap-1.5 text-[13px]"><span className="text-ink-2">试试：</span>
      {EXAMPLES.map((x) => <button key={x} className="chip" onClick={() => run(x)}>{x}</button>)}</div>
    {err && <p role="alert" className="text-danger">{err}</p>}
    {result && <p className="text-[13px] text-ink-2">「{result.query}」命中 {result.data.hits.length} 页{result.data.note && `；${result.data.note}`}</p>}
    {result && <div className="grid grid-cols-[minmax(0,5fr)_minmax(0,7fr)] items-start gap-4">
      <ul className="flex flex-col gap-2">{result.data.hits.map((h) => {
        const text = h.excerpt.replace(TRANSCRIBED, "");
        return <li key={h.pointer}>
          <button onClick={() => setPick(h)} className={`w-full rounded-xl border bg-white px-3 py-2 text-left text-[13px] ${pick?.pointer === h.pointer ? "border-accent ring-1 ring-accent" : "border-line hover:border-accent"}`}>
            <span className="flex flex-wrap items-center gap-2"><b>{h.title}</b><span className="text-ink-2">第 {h.page} 页</span>
              {TRANSCRIBED.test(h.excerpt) && <span className="chip tag-attn">扫描页 · 模型转写</span>}</span>
            <span className="mt-1 line-clamp-4 block whitespace-pre-wrap text-ink-2"><Mark text={text} query={result.query} /></span>
          </button>
        </li>;
      })}
        {!result.data.hits.length && <li className="text-ink-2">没找到。换个说法，或者这类资料你这个岗位读不到。</li>}
      </ul>
      {pick ? <Viewer hit={pick} /> : <div />}
    </div>}
  </div>;
}
