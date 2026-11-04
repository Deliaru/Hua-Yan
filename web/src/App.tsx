// 外壳：工具栏（身份切换、新开一轮、状态条）+ 侧栏 source list。
// v6：四个角色子工作面（客户 / 业务员 / 产品经理 / 研发）是侧栏二级项，进入即以该角色身份请求；不再靠导览线性走主线，
// 看的人在四个角色之间自由切换，靠「同一份需求在哪些工作面出现、在哪些没出现」看流程被缩短。
// 旧主线（v5 演示故事 + 带导览的沉浸工作面）沿 v5 流程，与 v6 冲突，V6-5.5 起不在侧栏出现；代码与 #story / #desk 地址保留。
// V6-5.5「演示讲解」：左侧导航换成讲解栏（components/Demo.tsx），中、右两栏仍是真实工作面。
// V9.1 试用实例（meta.trial）：进入先选身份，之后身份固定（服务端以它为主体），只显示这个身份的工作面；不出现讲解与重置。
import { useEffect, useState } from "react";
import { PlayBar } from "./components/Play";
import { api } from "./api";
import { AppCtx, useLabels } from "./ctx";
import type { Meta, Role, RunMode, RunStatus } from "./types";
import { Popover } from "./components/Controls";
import { ChevronDown, Close, NavArch, NavCustomer, NavDesk, NavEval, NavJue, NavLayers, NavLedger, NavPm, NavRd, NavSales, NavStory, Refresh } from "./components/Icons";
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
import { Customer } from "./pages/Customer";
import { Pm } from "./pages/Pm";
import { Month } from "./pages/Month";
import { Ceo } from "./pages/Ceo";
import { Settle } from "./pages/Settle";
import { Live } from "./pages/Live";
import { Canvas } from "./pages/Canvas";
import { Screens } from "./pages/Screens";
import { Backup } from "./pages/Backup";
import { Guide, useGuide } from "./components/Guide";
import { RECORDING_NOTE } from "./components/ui";
import { ModeDialog } from "./components/Mode";
import { ActivityMenu } from "./components/Process";
import { DemoPanel } from "./components/Demo";
import { Opener } from "./components/Opener";

// [页面, 标题, 图标, 分组]：分组 null 为一级项
const PAGES = [
  ["overview", "架构总览", NavArch, null],
  ["live", "组织运行实况", NavJue, null],
  ["qi", "契画布", NavLayers, null],
  ["screens", "四屏并排", NavLayers, null],
  ["backup", "答辩备用", NavEval, null],
  ["customer", "客户", NavCustomer, "工作面"],
  ["sales", "业务员", NavSales, "工作面"],
  ["pm", "产品经理", NavPm, "工作面"],
  ["rd", "研发", NavRd, "工作面"],
  ["supervisor", "研发负责人", NavDesk, "工作面"],
  ["ceo", "CEO 面", NavEval, null],
  ["settle", "这一局的结算", NavLedger, null],
  ["jue", "觉视图", NavJue, null],
  ["month", "化言的一个月", NavLedger, null],
  ["layers", "三层对照", NavLayers, null],
  ["eval", "评测", NavEval, null],
  ["ledger", "知识与积分", NavLedger, null],
  ["story", "演示故事", NavStory, "旧主线回放（v5）"],
  ["desk", "沉浸工作面", NavDesk, "旧主线回放（v5）"],
] as const;
type Page = (typeof PAGES)[number][0];
const HIDDEN: Page[] = ["story", "desk"];   // 不在侧栏出现的旧页面
const TRIAL_PAGES: Page[] = ["jue", "ledger"];   // V11.0 试用实例：除自己的工作面，只留觉视图与知识账本；架构总览、模拟月、三层对照、评测是演示页
const HUMANS: Role[] = ["sales", "pm", "rd", "supervisor"];   // 觉视图、三层对照、知识与积分、旧沉浸工作面可选的身份（产品经理为真人 P01，不含 Agent）
const ROLE_PAGES: Partial<Record<Page, Role>> = { customer: "customer", sales: "sales", pm: "pm", rd: "rd", supervisor: "supervisor", ceo: "supervisor", qi: "rd" };
const ROLE_NAME: Record<string, string> = { customer: "客户", sales: "业务员", pm: "产品经理", rd: "研发", supervisor: "研发负责人" };
const TRIAL_ROLES: Role[] = ["sales", "pm", "rd", "supervisor", "customer"];
const DEFAULT_WHO: Record<Role, string> = { customer: "customer:C03", sales: "sales:S01", pm: "pm:P01", rd: "rd:R01", supervisor: "supervisor:M01" };

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const fromHash = () => PAGES.find(([k]) => `#${k}` === location.hash)?.[0] ?? "overview";
  const [rawPage, setPageState] = useState<Page>(fromHash);
  const setPage = (p: Page) => { location.hash = p; setPageState(p); };
  useEffect(() => {
    const sync = () => setPageState(fromHash());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const [me, setMe] = useState<string | null>(() => new URLSearchParams(location.search).get("as"));   // ?as=rd:R02 直接以某人身份打开（觉视图等通用页）
  const [who, setWho] = useState<Record<string, string>>({});   // v6：每个角色子工作面当前是哪个人
  const [focus, setFocus] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [side, setSide] = useState<HTMLElement | null>(null);
  const [modeOpen, setModeOpen] = useState(false);
  const [demo, setDemoState] = useState(() => localStorage.getItem("huayan-demo") === "1");   // 讲解模式，刷新不丢
  const setDemo = (on: boolean) => { localStorage.setItem("huayan-demo", on ? "1" : "0"); setDemoState(on); };
  const [notesOn, setNotesState] = useState(() => localStorage.getItem("huayan-notes") === "1");   // 演示说明，刷新不丢
  const setNotes = (on: boolean) => { localStorage.setItem("huayan-notes", on ? "1" : "0"); setNotesState(on); };
  const guide = useGuide();

  const fail = (e: unknown) => {
    const message = e instanceof Error ? e.message : String(e);
    setError(message);
    // 服务端已不认这个浏览器的身份（如别处点了换身份）：重取 meta，回到选身份，不再停在加载中反复请求
    if (message === "请先选择你在试用中的身份") api.meta().then(setMeta);
  };
  useEffect(() => { api.meta().then(setMeta, fail); }, []);
  // V9.2 试用实例：别人的提交与后台准备完成后，几秒内自动刷新（只看事件数是否变了，不排会话锁）
  const trialOn = !!meta?.trial?.actor;
  useEffect(() => {
    if (!trialOn) return;
    let last = "";
    const timer = setInterval(() => api.trialStamp().then((s) => {
      const now = `${s.events}:${s.failures}:${s.sessions}`;
      if (last && now !== last) setVersion((v) => v + 1);
      last = now;
    }, () => {}), 4000);
    return () => clearInterval(timer);
  }, [trialOn]);
  if (busy) return <p role="status" className="p-10 text-ink-2">{busy}</p>;
  if (!meta) return error ? <p className="p-10 text-danger">{error}</p> : null;
  const trial = meta.trial;
  const trialActor = meta.actors.find((a) => a.id === trial?.actor);
  const enter = (id: string | null) => api.trialRole(id).then(() => api.meta()).then((m) => {
    setMeta(m); setFocus(null); setVersion((v) => v + 1);
    const role = m.actors.find((a) => a.id === m.trial?.actor)?.role;
    const own = PAGES.find(([k]) => ROLE_PAGES[k] === role)?.[0];
    if (own) setPage(own);
  }, fail);
  if (trial && !trialActor) return <RolePicker meta={meta} onPick={enter} error={error} />;
  // 试用实例里只出现自己的工作面、觉视图与知识账本；地址栏指到别处时回到自己的工作面
  // V11.9 结算页只在游戏模式出现，谁都能看
  // V12.8 实况是路演画面：游戏模式里主管身份可见（四屏并排时主屏用主管身份开一个窗口），真实试用里不出现
  // 契画布给研发、四屏给各身份，也只在游戏模式里出现
  const visible = (k: Page) => k === "settle" ? !!meta.play : k === "live" ? !trialActor || (!!meta.play && trialActor.role === "supervisor")
    : k === "qi" ? !trialActor || (!!meta.play && trialActor.role === "rd") : k === "screens" || k === "backup" ? !trialActor || !!meta.play
    : !trialActor || ROLE_PAGES[k] === trialActor.role || TRIAL_PAGES.includes(k);
  const page: Page = visible(rawPage) ? rawPage : PAGES.find(([k]) => ROLE_PAGES[k] === trialActor!.role)?.[0] ?? "jue";
  const inDemo = demo && !trial;

  const pageRole = ROLE_PAGES[page];
  const human = (r: Role) => meta.actors.filter((a) => a.role === r && a.id !== "pm:agent");
  const people = pageRole ? human(pageRole) : meta.actors.filter((a) => HUMANS.includes(a.role) && a.id !== "pm:agent");
  const actor = trialActor ?? (pageRole ? people.find((a) => a.id === (who[pageRole] ?? (page === "ceo" ? "supervisor:CEO" : DEFAULT_WHO[pageRole]))) ?? people[0]
    : people.find((a) => a.id === me) ?? people[0]);
  const pick = (id: string) => (pageRole ? setWho((w) => ({ ...w, [pageRole]: id })) : setMe(id));
  const restart = (label: string, p: Promise<unknown>) => {
    setError(null);
    setFocus(null);   // 重建后旧会话、旧需求单都不在了
    setBusy(label);
    p.then(() => api.meta()).then((m) => { setMeta(m); setVersion((v) => v + 1); }).catch(fail).finally(() => setBusy(null));
  };
  const ctx = {
    meta, me: actor.id, role: actor.role, agentOnline: !meta.status.gateway_mock, version, side,
    refresh: () => setVersion((v) => v + 1), fail, switchTo: setMe, become: (id: string) => enter(id), focus, startDemo: () => setDemo(true), openMode: () => setModeOpen(true),
    notes: notesOn || inDemo,
    go: (p: string, f?: string | null, id?: string) => {
      const role = ROLE_PAGES[p as Page];
      if (role && id && id.startsWith(`${role}:`)) setWho((w) => ({ ...w, [role]: id }));
      if (!role && id) setMe(id);
      setFocus(f ?? null);
      setPage(p as Page);
      window.scrollTo(0, 0);
    },
  };
  const key = `${meta.status.run_id}:${actor.id}`;
  const sideW = inDemo ? 400 : 232;
  // 讲解每执行一步：从头重建过的要重读 meta（run_id 变了），再切到该看的工作面与对象
  const onView = async (v: { page: string; focus: string | null; who: string | null } | null, rebuilt: boolean) => {
    if (rebuilt) setMeta(await api.meta());
    setVersion((n) => n + 1);
    if (v) ctx.go(v.page, v.focus, v.who ?? undefined);
  };

  return (
    <AppCtx.Provider value={ctx}>
      <header className="bar fixed inset-x-0 top-0 z-30 flex h-[52px] items-center gap-3 border-b border-sep px-4">
        <div className="w-[200px]"><Logo /></div>
        <ActivityMenu />
        {/* 导览占中间的剩余空间居中：两侧再宽也不会叠上 */}
        <div className="flex min-w-0 flex-1 justify-center">{meta.play ? <PlayBar /> : page === "desk" && <Guide />}</div>
        <div className="flex items-center gap-1.5">
          {!inDemo && <button onClick={() => setNotes(!notesOn)} className={`btn btn-plain ${notesOn ? "!text-accent" : ""}`}
                              title="化言在背后做了什么：知识层级、需求经过了谁、你的时间用在了哪里。真实用户日常看不到这些，讲解时再打开">
            {notesOn ? "收起演示说明" : "演示说明"}</button>}
          <StatusMenu s={meta.status} m={meta.mode} trial={!!trial} play={!!meta.play} onMode={() => setModeOpen(true)} />
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
            {(close) => trial ? (
              <div className="w-[220px] p-1">
                <p className="px-2.5 pb-1 pt-1.5 text-[12px] text-ink-2">试用身份：{ROLE_NAME[actor.role]}</p>
                <button className="menu-item" onClick={() => { close(); enter(null); }}>换一个身份…</button>
              </div>
            ) : (pageRole ? [pageRole] : HUMANS).map((r) => (
              <div key={r}>
                <p className="px-2.5 pb-0.5 pt-1.5 text-[12px] text-ink-2">{ROLE_NAME[r]}</p>
                {people.filter((a) => a.role === r).map((a) => (
                  <button key={a.id} className={`menu-item ${a.id === guide.who && a.id !== actor.id ? "font-semibold text-accent" : ""}`} onClick={() => { pick(a.id); close(); }}>
                    <span className="w-3">{a.id === actor.id ? "✓" : ""}</span><Name id={a.id} />
                  </button>
                ))}
              </div>
            ))}
          </Popover>
          {!trial && <button className="btn btn-plain gap-1.5" title="清空你这个浏览器里的会话与需求单，从头开始（其他试用者不受影响）"
                  onClick={() => confirm("重置进度：清空你这个浏览器里的客户会话、需求单和签字记录，从头开始（其他试用者不受影响）。确定吗？") && restart("正在重置进度……", api.reset())}>
            <Refresh />重置进度</button>}
        </div>
      </header>

      <aside style={{ width: sideW }} className="sidebar fixed bottom-0 left-0 top-[52px] z-20 flex flex-col overflow-y-auto border-r border-sep pb-4 pt-2">
        {inDemo ? <DemoPanel onExit={() => setDemo(false)} onView={onView} side={setSide} /> : <>
        {!trial && <button onClick={() => setDemo(true)} className="side-row nav-row">
          <NavStory /><span className="text-[13px] font-semibold">演示讲解</span><span className="tag tag-accent ml-auto !h-[18px] !text-[11px]">推荐</span>
        </button>}
        {PAGES.filter(([k]) => !HIDDEN.includes(k) && visible(k)).map(([k, label, Icon, group], i, shown) => (
          <div key={k}>
            {group && shown[i - 1]?.[3] !== group && <p className="side-head !pb-1 !pt-3">{group}</p>}
            <button onClick={() => { setFocus(null); setPage(k); }} className={`side-row nav-row ${page === k ? "on" : ""} ${group ? "!pl-[30px]" : ""}`}>
              <Icon /><span className="text-[13px] font-semibold">{label}</span>
            </button>
          </div>
        ))}
        <div ref={setSide} className="flex-1" />
        </>}
        {!trial && <p className="mx-[18px] mt-4 flex items-center gap-1.5 text-[11px] leading-4 text-ink-3"
           title="占位种子与程序生成的对话，不含任何真实客户、企业与配方">
          <i className="h-1.5 w-1.5 rounded-full bg-ink-3" />全部为模拟数据
        </p>}
      </aside>

      <main style={{ marginLeft: sideW, ["--side-w" as string]: `${sideW}px` }} className="pt-[52px]">
        {page === "overview" && <Overview />}
        {page === "customer" && <Customer key={key} />}
        {page === "sales" && <Sales key={key} />}
        {page === "pm" && <Pm key={key} />}
        {page === "rd" && <Rd key={key} />}
        {page === "supervisor" && <Supervisor key={key} />}
        {["customer", "sales", "pm", "rd", "supervisor"].includes(page) && <Opener key={`opener-${page}`} role={page} />}
        {page === "story" && <Story toDesk={() => setPage("desk")} />}
        {page === "desk" && (actor.role === "sales" ? <Sales key={key} /> : actor.role === "rd" ? <Rd key={key} /> : <Supervisor key={key} />)}
        {page === "jue" && <JuePage key={key} />}
        {page === "layers" && <Layers key={meta.status.run_id} />}
        {page === "eval" && <Eval />}
        {page === "ledger" && <Ledger key={key} />}
        {page === "month" && <Month />}
        {page === "ceo" && <Ceo key={key} />}
        {page === "live" && <Live key={key} />}
        {page === "qi" && <Canvas key={key} />}
        {page === "screens" && <Screens key={key} />}
        {page === "backup" && <Backup key={key} />}
        {page === "settle" && <Settle key={key} />}
      </main>

      {modeOpen && <ModeDialog mode={meta.mode} onClose={() => setModeOpen(false)}
                               onDone={(demoTab) => {
                                 setModeOpen(false);
                                 if (demoTab) { localStorage.setItem("huayan-demo-tab", demoTab); setDemo(true); }
                                 restart("正在切换运行方式……", Promise.resolve());
                               }} />}
      {error && (
        <div className="popover anim-fade fixed right-4 top-[60px] flex max-w-[360px] items-start gap-2 px-3 py-2.5 text-[13px]">
          <span className="flex-1 text-danger">{error}</span>
          <button onClick={() => setError(null)} className="icon-btn !h-5 !w-5"><Close /></button>
        </div>
      )}
    </AppCtx.Provider>
  );
}

// 试用实例的入口：选一次身份，服务端记住；之后读写都以这个身份为主体
function RolePicker({ meta, onPick, error }: { meta: Meta; onPick: (id: string) => void; error: string | null }) {
  return (
    <div className="mx-auto max-w-[560px] px-6 pt-20">
      <Logo />
      <h1 className="mt-6 text-[22px] font-semibold">选择你在这次试用中的身份</h1>
      <p className="mt-1.5 text-[13px] text-ink-2">大家处理的是同一份业务。选定后，这个浏览器里的查看和操作都以这个身份进行。</p>
      {TRIAL_ROLES.map((r) => {
        const people = meta.actors.filter((a) => a.role === r && a.id !== "pm:agent");
        return people.length ? (
          <div key={r} className="mt-5">
            <p className="eyebrow pb-1.5">{ROLE_NAME[r]}</p>
            <div className="flex flex-wrap gap-2">
              {people.map((a) => <button key={a.id} className="btn btn-plain" onClick={() => onPick(a.id)}>{a.name.replace("（模拟）", "")}</button>)}
            </div>
          </div>
        ) : null;
      })}
      {error && <p className="mt-5 text-[13px] text-danger">{error}</p>}
    </div>
  );
}

function Name({ id }: { id: string }) {
  return <>{useLabels().name(id)}</>;
}

// 状态指示：常驻工具栏，一行写运行方式，点开逐项看（铁律 6：降级可见，降级项标黄）
// 回放时大模型与 OneJev 的输出来自录制缓存，逐项写「录制回放」，不写「在线」；觉（Jue-K）是本地推理，回放时也在实时运行
// 自带密钥（BYOK）时写试用者填的模型名；没接 OneJev 时 Jev 是大模型降级，标黄

function StatusMenu({ s, m, trial, play, onMode }: { s: RunStatus; m: RunMode; trial: boolean; play: boolean; onMode: () => void }) {
  const R = "录制回放";
  const byok = m.kind === "byok";
  const rec = m.kind === "recorded";       // V12.12 路演：主线从彩排录制出，录制里没有的实时调用
  const jev: Record<string, string> = { onejev: "OneJev", mock: "桩", llm_fallback: "大模型降级" };
  const jue: Record<string, string> = { jue_k: "Jue-K · 本地实时", jue_proto: "规则原型", onejev: "OneJev" };
  // [项, 值, 种类]：ok 正常运行，warn 降级，replay 录制回放
  type Kind = "ok" | "warn" | "replay";
  // 写出所用模型名：回放是录制时的模型，自带密钥是试用者填的模型
  const llm = (): [string, Kind] => s.gateway_mock ? ["离线 · 规则", "warn"] : s.replay ? [`${m.llm_model} · ${R}`, "replay"]
    : rec ? [`${m.llm_model} · 录制优先`, "replay"] : [`${m.llm_model} · ${byok ? "自带密钥" : "在线"}`, "ok"];
  const items: [string, string, Kind][] = [
    ["数据", play ? "模拟 · 游戏" : trial ? "共享试用" : "模拟", "ok"],
    ...(s.seeds_placeholder ? [["种子", "占位", "warn"] as [string, string, Kind]] : []),
    ["Agent", ...llm()],
    ["抽取", ...(s.extractor === "llm" ? llm() : ["规则", "warn"] as [string, Kind])],
    ["Jev", ...(s.system1_impl !== "onejev" ? [jev[s.system1_impl] ?? s.system1_impl, "warn"] as [string, Kind]
      : s.replay ? [`${m.jev_model} · ${R}`, "replay"] as [string, Kind]
      : rec ? [`${m.jev_model} · 录制优先`, "replay"] as [string, Kind]
      : byok ? [`${m.jev_model} · 自带接口${m.jev_fallback ? "，失败降级" : ""}`, "ok"] as [string, Kind] : [`${m.jev_model} · 在线`, "ok"] as [string, Kind])],
    ["觉", jue[s.realtime_model] ?? s.realtime_model, s.realtime_model === "jue_proto" ? "warn" : "ok"],
  ];
  const degraded = items.filter(([, , k]) => k === "warn").length;
  const mode = s.replay ? "录制回放" : byok ? "自带密钥" : s.gateway_mock ? (trial ? "离线运行" : "离线演示") : "现场运行";
  const sub = s.replay ? "非在线运行" : rec ? "主线回放彩排录制" : degraded ? `${degraded} 项降级` : byok ? "真实运行" : "全部正常";
  const TAG: Record<Kind, string> = { ok: "text-ink", warn: "tag tag-warn", replay: "tag" };
  return (
    <>
    <Popover align="right" trigger={(toggle) => (
      <button onClick={toggle} className="flex h-7 items-center gap-2 rounded-full px-2.5 text-[12px] hover:bg-fill">
        <i className={`h-[7px] w-[7px] rounded-full ${s.replay ? "bg-[#8e8e93]" : degraded ? "bg-[#f5b400]" : "bg-[#30c25b]"}`} />
        <span className="font-semibold">{mode}</span>
        <span className="text-ink-2">{sub}</span>
        <span className="text-ink-3"><ChevronDown /></span>
      </button>
    )}>
      {(close) => (
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
            {rec ? "录制优先：彩排时用真实模型跑过的那条主线，同样的输入直接用录下的真实结果；现场新打的字、新委托 Agent 的事录制里没有，实时调用模型。觉在本地实时计算。" : ""}
            {byok ? "自带密钥：Agent、抽取与 Jev 真实调用你填的接口；觉在本地实时计算。" : ""}
            黄色为降级运行，结果上同样标注来源。</p>
          {m.kind !== "local" && <button className="btn btn-plain mx-2 mb-1 mt-2.5 w-[calc(100%-16px)]" onClick={() => { close(); onMode(); }}>
            {byok ? "切换运行方式…" : "接入自己的模型（BYOK）…"}</button>}
        </div>
      )}
    </Popover>
    {/* 回放时常驻的入口：评委一眼能看到在哪里接入真实模型、切到在线运行 */}
    {m.kind === "replay" && (
      <button onClick={onMode} title="用你自己的大模型（与可选的 OneJev）密钥在线真实运行；只影响你这个浏览器"
              className="btn btn-plain !text-accent">接入真实模型</button>
    )}
    </>
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
