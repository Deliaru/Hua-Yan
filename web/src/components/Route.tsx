// v6 共用组件：需求轨迹条（RouteStrip）、开工条件（E1 / E2 / E3）、「被拿掉的无效工作 / 保留的专业判断」（E6）、开场入口。
// 数据全部来自门面（route_of、readiness、session_readiness、workload），界面不做权限判断、不自己推算状态。
import { useState } from "react";
import { api } from "../api";
import { ACTION, useApp, useData, useLabels } from "../ctx";
import type { Condition, Readiness, Route, RouteState } from "../types";
import { Popover } from "./Controls";
import { ChevronRight, Plus } from "./Icons";
import { Group, Score } from "./ui";
import { NO_GUIDE, publish, useGuide } from "./Guide";

const ROLES = [["customer", "客户"], ["sales", "业务员"], ["pm", "产品经理"], ["rd", "研发"]] as const;
const STATE_TEXT: Record<RouteState, string> = { human: "人处理过", auto: "Agent / 觉代办", pending: "待处理", none: "未经过" };
const PATH_NOTE: Record<string, string> = {
  自助解决: "现有产品能解决：客户答完觉的追问就拿到推荐，没有占用任何人",
  交业务员: "客户有商务诉求：觉按归属交给业务员，原话与推荐原样带过去",
  入研: "现有产品解决不了：需求带客户原话直达研发，产品经理 Agent 在后台转译",
  研发不立项: "研发判断后不立项；判为已有产品适用时，产品经理把这次判断变成产品边界",
  产品机会: "几位客户的同类需求，由产品经理附商业判断汇成一个课题",
  复用: "产品经理 Agent 找到现成产品，研发审定后直接交付",
  追问中: "觉还在追问研发开工需要的条件",
  转研发中: "条件已问清、现有产品都不合适：产品经理 Agent 正在整理，随后直达研发",
};

export const PAGE_OF: Record<string, string> = { customer: "customer", sales: "sales", pm: "pm", rd: "rd" };

function Dot({ state }: { state: RouteState }) {
  const base = "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full";
  if (state === "human") return <span className={`${base} bg-accent`}><i className="h-2 w-2 rounded-full bg-white" /></span>;
  if (state === "auto") return <span className={`${base} border-[1.5px] border-dashed border-accent`} />;
  if (state === "pending") return <span className={`${base} border-2 border-attn`} />;
  return <span className={`${base} border-[1.5px] border-[rgba(60,60,67,.22)]`} />;
}

// 一份需求经过了谁、绕过了谁。点格子跳到那个角色的子工作面，打开同一对象（服务端按身份裁剪）
export function RouteStrip({ objectId }: { objectId: string }) {
  const { me, go, notes } = useApp();
  const L = useLabels();
  const r = useData<Route>(() => api.route(objectId, me), [objectId, me]);
  const [open, setOpen] = useState(false);
  const g = useGuide();   // 演示讲解指向的角色格（route:<角色>），点过即熄
  if (!r || !notes) return null;   // 演示说明
  const focusOf = (role: string) => (role === "rd" || role === "pm") && r.requirement_id ? r.requirement_id : r.session_id;
  const who = (role: string) => r.roles[role as keyof Route["roles"]].by.find((id) => id !== "pm:agent");
  const decisions = r.basis.filter((b) => b.action);
  return (
    <section className="group">
      <div className="flex items-center gap-3 border-b border-sep px-5 py-2.5">
        <span className="eyebrow">需求轨迹</span>
        <span className="tag tag-accent">{r.path}</span>
        <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-2">{PATH_NOTE[r.path] ?? ""}</span>
        <span className="num shrink-0 text-[12px] text-ink-2">人工节点 {r.n_human_steps} 个</span>
      </div>
      <p className="px-5 pt-2 text-[11.5px] text-ink-3">点任一角色，切到这个角色的工作面看这件事：能做什么、要做什么、正在做什么</p>
      <div className="grid grid-cols-4">
        {ROLES.map(([role, label], i) => {
          const cell = r.roles[role];
          return (
            <button key={role} type="button" onClick={() => { if (g.target?.startsWith("route:")) publish(NO_GUIDE); go(PAGE_OF[role], focusOf(role), who(role)); }}
                    className={`group/cell relative flex items-start gap-2.5 px-5 py-3 text-left hover:bg-[rgba(0,0,0,.03)] ${g.target === `route:${role}` ? "glow rounded-[8px]" : ""}`}
                    title={`切到${label}子工作面，看${label}在这件事里能做什么、要做什么、在做什么`}>
              {i < 3 && <i className="absolute left-[42px] right-[-18px] top-[23px] h-px bg-sep" />}
              <span className="relative z-[1] bg-white"><Dot state={cell.state} /></span>
              <span className="min-w-0">
                <span className="flex items-center gap-0.5 text-[13px] font-semibold">{label}
                  <span className="text-ink-3 group-hover/cell:text-accent"><ChevronRight /></span></span>
                <span className={`block text-[12px] ${cell.state === "pending" ? "text-attn-ink" : "text-ink-2"}`}>
                  {STATE_TEXT[cell.state]}</span>
                {!!cell.by.length && cell.state !== "none" && (
                  <span className="block truncate text-[12px] text-ink-3">{cell.by.map(L.name).join("、")}</span>)}
              </span>
            </button>
          );
        })}
      </div>
      {!!decisions.length && (
        <div className="border-t border-sep px-5 py-2">
          <button type="button" className="link !text-[12px]" onClick={() => setOpen(!open)}>
            <ChevronRight open={open} />觉提出的决策与处置 {decisions.length} 项</button>
          {open && decisions.map((b) => (
            <p key={b.question_id} className="anim-fade mt-1 flex items-center gap-2 text-[12.5px] leading-5">
              <span className="w-[84px] shrink-0 font-semibold">{L.family(b.family)}</span>
              <span className="shrink-0 text-ink-2">{ACTION[b.action ?? ""] ?? b.action}{b.by && b.by !== "jue:auto" ? ` · ${L.name(b.by)}` : ""}</span>
              <span className="min-w-0 flex-1 truncate text-ink-2">{b.note}</span>
              <Score q={{ p_need: b.p_need, scored_by: b.scored_by, family: b.family }} />
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

// 一项必问条件：取值 + 原话 + 来源（开场就说了 / 觉追问所得）
function ConditionRow({ c }: { c: Condition }) {
  return (
    <div className="row !min-h-[46px] !items-start !py-2.5">
      <span className={`mt-[3px] flex h-[16px] w-[16px] shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
        c.value ? "bg-[#30c25b] text-white" : "shadow-[inset_0_0_0_1.5px_rgba(60,60,67,.25)]"}`}>{c.value ? "✓" : ""}</span>
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-2 text-[13.5px]">
          <span className="text-ink-2">{c.label}</span>
          <span className={c.value ? "font-semibold" : "text-ink-3"}>{c.value ?? "还不知道"}</span>
        </p>
        {c.quote && <p className="truncate text-[12px] text-ink-3">「{c.quote}」</p>}
      </div>
      {c.value && <span className={`tag shrink-0 ${c.asked_by_jue ? "tag-attn" : ""}`}>{c.in_opening ? "开场就说了" : c.asked_by_jue ? "觉追问所得" : "客户补充"}</span>}
    </div>
  );
}

// E1：客户 / 业务员看到的「研发开工需要的条件」，逐项亮起
export function SessionConditions({ sessionId }: { sessionId: string }) {
  const { me } = useApp();
  const L = useLabels();
  const r = useData(() => api.sessionReadiness(sessionId, me), [sessionId, me]);
  if (!r) return null;
  return (
    <Group title="研发开工需要的条件" aside={r.phenomenon ? `${r.n_known} / ${r.n_required} 已明确` : undefined}
           foot={r.phenomenon ? `「${L.phen(r.phenomenon)}」这类问题，研发开工前必须知道这几项。觉只问会改变下游判断的那几项，不按固定问卷问。`
             : "客户描述出现象后，这里列出研发开工必须知道的条件。"}>
      {r.items.map((c) => <ConditionRow key={c.slot} c={c} />)}
      {!r.items.length && <div className="row text-[13px] text-ink-3">等客户描述现象</div>}
    </Group>
  );
}

// E2 + E3：研发单头的开工门槛；展开「如果只靠开场白」
export function ReadinessCard({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const r = useData<Readiness>(() => api.readiness(reqId, me), [reqId, me]);
  const [open, setOpen] = useState(false);
  if (!r) return null;
  const missing = r.items.filter((c) => !c.value);
  const blockers = [r.n_open_ask_back && `未答回问 ${r.n_open_ask_back} 项`, r.n_open_distortion && `未处理失真 ${r.n_open_distortion} 处`].filter(Boolean);
  const lacking = r.items.filter((c) => !c.in_opening);
  return (
    <section className="group">
      <div className={`flex items-center gap-3 px-5 py-3 ${r.ready ? "" : "attn-edge"}`}>
        <span className={`flex h-7 shrink-0 items-center rounded-full px-3 text-[13px] font-semibold ${
          r.ready ? "bg-[rgba(48,194,91,.13)] text-[#1d7a3a]" : "bg-attn-bg text-attn-ink"}`}>
          开工门槛：{r.ready ? "已齐" : `缺 ${[...missing.map((c) => c.label), ...blockers].join("、")}`}</span>
        <span className="min-w-0 flex-1 text-[12.5px] text-ink-2">
          必问条件 {r.n_known}/{r.n_required} 已明确，每项带客户原话；{r.n_items_with_quote}/{r.n_items} 条转译带原话
        </span>
      </div>
      {r.items.map((c) => <ConditionRow key={c.slot} c={c} />)}
      <div className="border-t border-sep px-5 py-2.5">
        <button type="button" className="link !text-[12.5px]" onClick={() => setOpen(!open)}>
          <ChevronRight open={open} />如果只靠开场白</button>
        {open && (
          <div className="anim-fade mt-2 rounded-[10px] bg-bg px-4 py-3 text-[13px] leading-[21px]">
            <p>客户第一句话里只有 <b className="num">{r.n_in_opening}/{r.n_required}</b> 项必问条件。
              {lacking.length ? <>按旧流程，研发拿到单后还要回头找业务员补问「{lacking.map((c) => c.label).join("、")}」，
                再等业务员去问客户、转述回来；漏问或转述走样，开发就偏，试样不达标就返工。</> : "这位客户开场就说全了。"}</p>
            <p className="mt-1.5 text-ink-2">这次其中 {r.n_asked_by_jue} 项由觉在客户对话里直接问出，研发拿到时已经齐了。数字取自本单客户的原话，不是模拟噪声。</p>
          </div>
        )}
      </div>
    </section>
  );
}

// E6：右栏「被拿掉的无效工作 / 保留的专业判断」
export function WorkloadCard({ title = "你的时间用在了哪里" }: { title?: string }) {
  const { me, notes } = useApp();
  const w = useData(() => api.workload(me), [me]);
  if (!w || !notes) return null;   // 演示说明
  return (
    <Group title={title} foot="本轮事件日志计数。必要的协作都保留，拿掉的是因信息缺失、转述、重复才被迫发生的工作。">
      <div className="px-4 pb-1 pt-3"><p className="eyebrow">被拿掉的无效工作</p></div>
      {w.removed.map((x) => (
        <div key={x.label} className="row !min-h-0 !items-start !py-2">
          <div className="min-w-0 flex-1">
            <p className="text-[13px]">{x.label}</p>
            <p className="text-[11.5px] leading-4 text-ink-3">{x.note}</p>
          </div>
          <span className="num text-[15px] font-semibold text-[#1d7a3a]">{x.n}</span>
        </div>
      ))}
      <div className="border-t border-sep px-4 pb-1 pt-3"><p className="eyebrow">保留的专业判断</p></div>
      {w.kept.map((x) => (
        <div key={x.label} className="row !min-h-0 !py-2">
          <p className="min-w-0 flex-1 text-[13px]">{x.label}</p>
          <span className="num text-[15px] font-semibold">{x.n}</span>
        </div>
      ))}
    </Group>
  );
}

// 开场入口（替代线性主线）：只代客户说出第一句话，之后由看的人自己在各工作面操作
export function OpenRouteMenu({ customer, onOpened }: { customer: string; onOpened: (sessionId: string, customer: string) => void }) {
  const { fail, refresh } = useApp();
  const routes = useData(() => api.demoRoutes(), []) ?? [];
  const open = (id: string) => api.openRoute(id, customer).then((o) => { onOpened(o.session_id, o.customer_id); refresh(); }, fail);
  const blank = () => api.startSession(customer).then((o) => { onOpened(o.id, customer); refresh(); }, fail);
  return (
    <Popover trigger={(toggle) => (
      <button onClick={toggle} className="icon-btn !h-6 !w-6" title="新开一个需求"><Plus /></button>
    )}>
      {(close) => (
        <div className="w-[320px]">
          <button className="menu-item !h-auto flex-col !items-start !py-1.5" onClick={() => { blank(); close(); }}>
            <span className="text-[13px] font-semibold">用自己的话说</span>
            <span className="text-[12px] text-ink-2">空白开始，像客户一样只描述现象</span>
          </button>
          <p className="px-2.5 pb-1 pt-1.5 text-[12px] text-ink-2">或选一个开场（只预填客户第一句话，后面真实走系统）</p>
          {routes.map((r) => (
            <button key={r.id} className="menu-item !h-auto flex-col !items-start !py-1.5" onClick={() => { open(r.id); close(); }}>
              <span className="text-[13px]"><b className="mr-1.5">{r.id}</b>{r.title}</span>
              <span className="text-[12px] text-ink-2">「{r.lines[0]}」</span>
            </button>
          ))}
        </div>
      )}
    </Popover>
  );
}

// 开场之后的下一步提示：按会话的客户与第一句话找到开场，只提示，不锁步骤
export function useRouteHint(customerId: string | null, firstLine: string | undefined) {
  const routes = useData(() => api.demoRoutes(), []) ?? [];
  if (!firstLine) return null;
  return routes.find((r) => r.customer === customerId && r.lines[0] === firstLine) ?? routes.find((r) => r.lines[0] === firstLine) ?? null;
}
