// 外壳：工具栏（身份切换、新开一轮、状态条）+ 侧栏 source list（架构总览、演示工作面、沉浸工作面、觉视图、三层对照、评测、知识与积分）。
// 演示工作面是只读的讲解页；沉浸工作面是真实的工作面，导览带着走演示主线。
// 没有产品经理页面：产品经理 Agent 的产出只在研发工作面、三层对照、觉视图上出现（REPLAN 3.2 第 5 条）。
import { useEffect, useState } from "react";
import { api } from "./api";
import { AppCtx, useLabels } from "./ctx";
import type { Meta, Role, RunStatus } from "./types";
import { Popover } from "./components/Controls";
import { ChevronDown, Close, NavArch, NavDesk, NavEval, NavJue, NavLayers, NavLedger, NavStory, Refresh } from "./components/Icons";
import { Logo } from "./components/Logo";
import { Sales } from "./pages/Sales";
import { Rd } from "./pages/Rd";
import { Supervisor } from "./pages/Supervisor";
import { JuePage } from "./pages/Jue";
import { Layers } from "./pages/Layers";
import { Eval } from "./pages/Eval";
import { Ledger } from "./pages/Ledger";
import { Overview } from "./pages/Overview";
import { Story } from "./pages/Story";
import { Guide, useGuide } from "./components/Guide";
import { RECORDING_NOTE } from "./components/ui";

const PAGES = [
  ["overview", "架构总览", NavArch],
  ["story", "演示工作面", NavStory],
  ["desk", "沉浸工作面", NavDesk],
  ["jue", "觉视图", NavJue],
  ["layers", "三层对照", NavLayers],
  ["eval", "评测", NavEval],
  ["ledger", "知识与积分", NavLedger],
] as const;
type Page = (typeof PAGES)[number][0];
const HUMANS: Role[] = ["sales", "rd", "supervisor"];
const ROLE_NAME: Record<string, string> = { sales: "业务员", rd: "研发", supervisor: "主管" };

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const fromHash = () => PAGES.find(([k]) => `#${k}` === location.hash)?.[0] ?? "overview";
  const [page, setPageState] = useState<Page>(fromHash);
  const setPage = (p: Page) => { location.hash = p; setPageState(p); };
  useEffect(() => {
    const sync = () => setPageState(fromHash());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const [me, setMe] = useState<string | null>(() => new URLSearchParams(location.search).get("as"));   // ?as=rd:R02 直接以某人身份打开
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [side, setSide] = useState<HTMLElement | null>(null);
  const guide = useGuide();

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  useEffect(() => { api.meta().then(setMeta, fail); }, []);
  if (busy) return <p role="status" className="p-10 text-ink-2">{busy}</p>;
  if (!meta) return error ? <p className="p-10 text-danger">{error}</p> : null;

  const people = meta.actors.filter((a) => HUMANS.includes(a.role));
  const actor = people.find((a) => a.id === me) ?? people[0];
  const restart = (label: string, p: Promise<unknown>) => {
    setError(null);
    setBusy(label);
    p.then(() => api.meta()).then((m) => { setMeta(m); setVersion((v) => v + 1); }).catch(fail).finally(() => setBusy(null));
  };
  const ctx = {
    meta, me: actor.id, role: actor.role, agentOnline: !meta.status.gateway_mock, version, side,
    refresh: () => setVersion((v) => v + 1), fail, switchTo: setMe,
  };
  const key = `${meta.status.run_id}:${actor.id}`;

  return (
    <AppCtx.Provider value={ctx}>
      <header className="bar fixed inset-x-0 top-0 z-30 flex h-[52px] items-center gap-3 border-b border-sep px-4">
        <div className="w-[200px]"><Logo /></div>
        {page === "desk" && <div className="absolute left-1/2 -translate-x-1/2"><Guide /></div>}
        <div className="ml-auto flex items-center gap-1.5">
          <StatusMenu s={meta.status} />
          <CheckpointMenu onLoad={(name) => restart(`正在载入检查点「${name}」……`, api.loadCheckpoint(name))} />
          <Popover align="right" trigger={(toggle) => (
            <button onClick={toggle} className={`flex h-8 items-center gap-2 rounded-[8px] pl-1 pr-2 hover:bg-fill ${
              page === "desk" && guide.who && guide.who !== actor.id ? "glow" : ""}`}>
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#8e8e93] text-[11px] font-semibold text-white">
                {ROLE_NAME[actor.role][0]}
              </span>
              <span className="text-[13px]"><Name id={actor.id} /></span>
              <span className="text-ink-2"><ChevronDown /></span>
            </button>
          )}>
            {(close) => HUMANS.map((r) => (
              <div key={r}>
                <p className="px-2.5 pb-0.5 pt-1.5 text-[12px] text-ink-2">{ROLE_NAME[r]}</p>
                {people.filter((a) => a.role === r).map((a) => (
                  <button key={a.id} className={`menu-item ${a.id === guide.who && a.id !== actor.id ? "font-semibold text-accent" : ""}`} onClick={() => { setMe(a.id); close(); }}>
                    <span className="w-3">{a.id === actor.id ? "✓" : ""}</span><Name id={a.id} />
                  </button>
                ))}
              </div>
            ))}
          </Popover>
          <button className="btn btn-plain gap-1.5" title="清空你这个浏览器里的会话与需求单，从头开始（其他试用者不受影响）"
                  onClick={() => confirm("重置进度：清空你这个浏览器里的客户会话、需求单和签字记录，从头开始（其他试用者不受影响）。确定吗？") && restart("正在重置进度……", api.reset())}>
            <Refresh />重置进度</button>
        </div>
      </header>

      <aside className="sidebar fixed bottom-0 left-0 top-[52px] z-20 flex w-[232px] flex-col overflow-y-auto border-r border-sep pb-4 pt-2">
        {PAGES.map(([k, label, Icon]) => (
          <button key={k} onClick={() => setPage(k)} className={`side-row nav-row ${page === k ? "on" : ""}`}>
            <Icon /><span className="text-[13px] font-semibold">{label}</span>
          </button>
        ))}
        <div ref={setSide} className="flex-1" />
        <p className="mx-[18px] mt-4 flex items-center gap-1.5 text-[11px] leading-4 text-ink-3"
           title="占位种子与程序生成的对话，不含任何真实客户、企业与配方">
          <i className="h-1.5 w-1.5 rounded-full bg-ink-3" />全部为模拟数据
        </p>
      </aside>

      <main className="ml-[232px] pt-[52px]">
        {page === "overview" && <Overview toStory={() => { setPage("story"); window.scrollTo(0, 0); }} />}
        {page === "story" && <Story toDesk={() => setPage("desk")} />}
        {page === "desk" && (actor.role === "sales" ? <Sales key={key} /> : actor.role === "rd" ? <Rd key={key} /> : <Supervisor key={key} />)}
        {page === "jue" && <JuePage key={key} />}
        {page === "layers" && <Layers key={meta.status.run_id} />}
        {page === "eval" && <Eval />}
        {page === "ledger" && <Ledger key={key} />}
      </main>

      {error && (
        <div className="popover anim-fade fixed right-4 top-[60px] flex max-w-[360px] items-start gap-2 px-3 py-2.5 text-[13px]">
          <span className="flex-1 text-danger">{error}</span>
          <button onClick={() => setError(null)} className="icon-btn !h-5 !w-5"><Close /></button>
        </div>
      )}
    </AppCtx.Provider>
  );
}

function Name({ id }: { id: string }) {
  return <>{useLabels().name(id)}</>;
}

// 状态指示：常驻工具栏，一行写运行方式，点开逐项看（铁律 6：降级可见，降级项标黄）
// 回放时大模型与 OneJev 的输出来自录制缓存，逐项写「录制回放」，不写「在线」；觉（Jue-K）是本地推理，回放时也在实时运行

function StatusMenu({ s }: { s: RunStatus }) {
  const R = "录制回放";
  const jev: Record<string, string> = { onejev: "OneJev", mock: "桩", llm: "大模型降级" };
  const jue: Record<string, string> = { jue_k: "Jue-K · 本地实时", jue_proto: "规则原型", onejev: "OneJev" };
  // [项, 值, 种类]：ok 正常运行，warn 降级，replay 录制回放
  type Kind = "ok" | "warn" | "replay";
  const llm = (on: string): [string, Kind] => s.gateway_mock ? ["离线 · 规则", "warn"] : s.replay ? [`${on} · ${R}`, "replay"] : [`${on} · 在线`, "ok"];
  const items: [string, string, Kind][] = [
    ["数据", "模拟", "ok"],
    ...(s.seeds_placeholder ? [["种子", "占位", "warn"] as [string, string, Kind]] : []),
    ["Agent", ...llm("大模型")],
    ["抽取", ...(s.extractor === "llm" ? llm("大模型") : ["规则", "warn"] as [string, Kind])],
    ["Jev", ...(s.system1_impl !== "onejev" ? [jev[s.system1_impl] ?? s.system1_impl, "warn"] as [string, Kind]
      : s.replay ? [`OneJev · ${R}`, "replay"] as [string, Kind] : ["OneJev · 在线", "ok"] as [string, Kind])],
    ["觉", jue[s.realtime_model] ?? s.realtime_model, s.realtime_model === "jue_proto" ? "warn" : "ok"],
  ];
  const degraded = items.filter(([, , k]) => k === "warn").length;
  const mode = s.replay ? "录制回放" : s.gateway_mock ? "离线演示" : "现场运行";
  const sub = s.replay ? "非在线运行" : degraded ? `${degraded} 项降级` : "全部正常";
  const TAG: Record<Kind, string> = { ok: "text-ink", warn: "tag tag-warn", replay: "tag" };
  return (
    <Popover align="right" trigger={(toggle) => (
      <button onClick={toggle} className="flex h-7 items-center gap-2 rounded-full px-2.5 text-[12px] hover:bg-fill">
        <i className={`h-[7px] w-[7px] rounded-full ${s.replay ? "bg-[#8e8e93]" : degraded ? "bg-[#f5b400]" : "bg-[#30c25b]"}`} />
        <span className="font-semibold">{mode}</span>
        <span className="text-ink-2">{sub}</span>
        <span className="text-ink-3"><ChevronDown /></span>
      </button>
    )}>
      {() => (
        <div className="w-[300px] p-1">
          <p className="eyebrow px-2 pb-1.5 pt-1">运行状态</p>
          {items.map(([k, v, kind]) => (
            <div key={k} className="flex items-center justify-between rounded-[6px] px-2 py-1 text-[13px]">
              <span className="text-ink-2">{k}</span>
              <span className={TAG[kind]}>{v}</span>
            </div>
          ))}
          {s.replay && <p className="mx-2 mt-2 rounded-[8px] bg-fill px-2.5 py-2 text-[12px] leading-[18px] text-ink">{RECORDING_NOTE}</p>}
          <p className="px-2 pt-1.5 text-[11px] leading-4 text-ink-3">
            {s.replay ? "录制回放：Agent、抽取与 Jev 的输出是录制时的真实结果，只能按演示台词走；觉在本地实时计算。" : ""}
            黄色为降级运行，结果上同样标注来源。</p>
        </div>
      )}
    </Popover>
  );
}

// 载入检查点（WP-I2）：只在服务以演示配置启动、接口返回检查点列表时出现
function CheckpointMenu({ onLoad }: { onLoad: (name: string) => void }) {
  const [names, setNames] = useState<string[]>([]);
  useEffect(() => { api.checkpoints().then(setNames, () => setNames([])); }, []);
  if (!names.length) return null;
  return (
    <Popover align="right" trigger={(toggle) => <button onClick={toggle} className="btn btn-plain">载入检查点<ChevronDown /></button>}>
      {(close) => names.map((n) => <button key={n} className="menu-item" onClick={() => { onLoad(n); close(); }}>{n}</button>)}
    </Popover>
  );
}
