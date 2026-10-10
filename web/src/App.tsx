import { useEffect, useState } from "react";
import { api } from "./api";
import { AppCtx } from "./ctx";
import type { Meta, Role } from "./types";
import { Popover, Segmented } from "./components/Controls";
import { ChevronDown, Close, Refresh } from "./components/Icons";
import { Sales } from "./pages/Sales";
import { Pm } from "./pages/Pm";
import { Rd } from "./pages/Rd";

const PAGES = [
  ["sales", "业务员"],
  ["pm", "产品经理"],
  ["rd", "研发"],
] as const;
type Page = (typeof PAGES)[number][0];
const short = (name: string) => name.replace("（模拟）", "");

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
  if (!meta) return error ? <p className="p-10 text-danger">{error}</p> : null;

  const people = meta.actors.filter((a) => a.role === page);
  const me = who[page] ?? people[0].id;
  const myName = short(people.find((a) => a.id === me)!.name);
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
      <header className="bar fixed inset-x-0 top-0 z-30 flex h-[52px] items-center border-b border-sep px-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] bg-gradient-to-b from-[#3a3a3c] to-ink text-[13px] font-semibold text-white">化</span>
          <span className="text-[14px] font-semibold">化言</span>
          <span className="tag" title="全部为模拟数据：占位种子与程序生成的对话，不含任何真实客户与配方">模拟数据</span>
        </div>
        <div className="absolute left-1/2 -translate-x-1/2">
          <Segmented items={PAGES} value={page} onChange={setPage} wide />
        </div>
        <div className="ml-auto flex items-center gap-1">
          <Popover align="right" trigger={(toggle) => (
            <button onClick={toggle} className="flex h-8 items-center gap-2 rounded-[8px] pl-1 pr-2 hover:bg-fill">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#8e8e93] text-[11px] font-semibold text-white">
                {myName.endsWith("工") ? myName.at(-2) : myName.at(-1)}
              </span>
              <span className="text-[13px]">{myName}</span>
              <span className="text-ink-2"><ChevronDown /></span>
            </button>
          )}>
            {(close) => people.map((a) => (
              <button key={a.id} className="menu-item" onClick={() => { setWho({ ...who, [page]: a.id }); close(); }}>
                <span className="w-3">{a.id === me ? "✓" : ""}</span>{short(a.name)}
              </button>
            ))}
          </Popover>
          <button className="icon-btn" title={`新开一轮（当前 ${meta.status.run_id}）`}
                  onClick={() => api.reset().then(ctx.refresh, fail)}>
            <Refresh />
          </button>
        </div>
      </header>

      {page === "sales" && <Sales key={me} />}
      {page === "pm" && <Pm key={me} />}
      {page === "rd" && <Rd key={me} />}

      {error && (
        <div className="popover anim-fade fixed right-4 top-[60px] flex max-w-[360px] items-start gap-2 px-3 py-2.5 text-[13px]">
          <span className="flex-1 text-danger">{error}</span>
          <button onClick={() => setError(null)} className="icon-btn !h-5 !w-5"><Close /></button>
        </div>
      )}
    </AppCtx.Provider>
  );
}
