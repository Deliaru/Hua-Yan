import { useEffect, useState } from "react";
import { api } from "./api";
import { AppCtx } from "./ctx";
import type { Meta, Role } from "./types";
import { Backdrop } from "./components/Backdrop";
import { Segmented } from "./components/Controls";
import { Sales } from "./pages/Sales";
import { Pm } from "./pages/Pm";
import { Rd } from "./pages/Rd";

const PAGES = [
  ["sales", "业务员 · L1"],
  ["pm", "产品经理 · L2"],
  ["rd", "研发 · L3"],
] as const;
type Page = (typeof PAGES)[number][0];

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [page, setPage] = useState<Page>("sales");
  const [who, setWho] = useState<Partial<Record<Role, string>>>({});
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  useEffect(() => {
    api.meta().then(setMeta, fail);
  }, [version]);
  if (!meta) return error ? <p className="p-10 text-red-600">{error}</p> : null;

  const people = meta.actors.filter((a) => a.role === page);
  const me = who[page] ?? people[0].id;
  const ctx = {
    meta,
    me,
    live: !meta.status.gateway_mock,
    version,
    refresh: () => setVersion((v) => v + 1),
    fail,
  };

  return (
    <AppCtx.Provider value={ctx}>
      <div className="min-h-full">
        <Backdrop />
        <div className="edge edge-top">{[...Array(6)].map((_, i) => <i key={i} />)}</div>
        <div className="edge edge-bottom">{[...Array(6)].map((_, i) => <i key={i} />)}</div>
        <header className="sticky top-0 z-20 grid h-[76px] grid-cols-[1fr_auto_1fr] items-center gap-4 px-5">
          <div className="flex min-w-0 items-center gap-3">
            <span className="pill flex h-11 w-11 shrink-0 items-center justify-center font-serif text-[18px]">化</span>
            <span className="on-sky font-serif text-[22px]">化言</span>
          </div>
          <Segmented items={PAGES} value={page} onChange={setPage} />
          <div className="flex items-center justify-self-end gap-2">
            <Segmented size="sm" items={people.map((a) => [a.id, a.name.replace("（模拟）", "")] as const)} value={me}
                       onChange={(id) => setWho({ ...who, [page]: id })} />
            <button
              className="btn pill press !h-9 text-ink/70 hover:text-ink"
              title={`当前 ${meta.status.run_id}；重建门面，开始新的 run`}
              onClick={() => api.reset().then(ctx.refresh, fail)}
            >
              新开一轮
            </button>
          </div>
        </header>

        {page === "sales" && <Sales key={me} />}
        {page === "pm" && <Pm key={me} />}
        {page === "rd" && <Rd key={me} />}

        {error && (
          <button onClick={() => setError(null)}
                  className="card anim-rise fixed right-5 top-20 z-40 max-w-[360px] !py-3 text-left text-[14px] text-red-600">
            {error}
            <span className="ml-2 text-ink/40">✕</span>
          </button>
        )}
      </div>
    </AppCtx.Provider>
  );
}
