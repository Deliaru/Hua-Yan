// 研发工作面（L3）：左侧收件箱；中间是需求单抬头、觉在这张单上提出的决策与签字区、批注、化学要点（每条右侧并排写来历：产品需求 ← 客户原话）；
// 右侧是这张单的来历与 Agent 协作。按钮就是签字，可签条件由门面判断，拒绝时在按钮旁显示门面给的原因。
import { useEffect, useState } from "react";
import { api } from "../api";
import { ACTION, REQ_STATUS, Side, hhmm, useApp, useData, useLabels } from "../ctx";
import type { AgentMessage, CitedKnowledge, GrantScope, LeakHit, Question, ReqItem, RequirementView } from "../types";
import { AgentPanel, Notes, PendingActions, notesFor, useConversation } from "../components/Agent";
import { ChevronRight } from "../components/Icons";
import { InboxSidebar, ownerText, useInbox } from "../components/Inbox";
import { useGlow, useGuide, useGuideArg } from "../components/Guide";
import { ANOMALY, Act, AgentMark, Disclosure, EmptyState, Field, Group, Marked, PageHead, Score, SideHead, LayerChip, SlotPicker } from "../components/ui";
import { ReadinessCard, RouteStrip, WorkloadCard } from "../components/Route";
import { SourceTrial } from "../components/SourceTrial";
import { LibrarySearch } from "../components/LibrarySearch";
import { PlanCard } from "../components/PlanCard";
import { Backstory } from "../components/Backstory";
import { Narration, TimeBar } from "../components/Narration";

// 决策所说的需求单：多数挂在一张单上；机会汇聚挂在主题上，refs 里是几张单（第一张为主单）
const reqsOf = (q: Question) => q.refs.requirement_id ? [q.refs.requirement_id] : (q.refs.requirement_ids ?? "").split(",").filter(Boolean);

// 选中一项决策即打开它所说的需求单；也可以从侧栏直接打开需求单（此时签字区显示这张单上待你签的决策）
export function Rd() {
  const { me, focus } = useApp();
  const L = useLabels();
  const { all, ready } = useInbox();
  const reqs = (useData(() => api.requirements(me), [me]) ?? []).slice().reverse();
  const [qid, setQid] = useState<string | null>(null);
  const [chosenReq, setChosenReq] = useState<string | null>(focus);   // v6：从轨迹条跳来时打开同一张单
  // V11.3 中间一次只放一件事：一张需求单（含它上面的决策），或「本人资料候选」「我授予的能力」
  const [panel, setPanel] = useState<"req" | "candidates" | "caps">("req");
  const showCandidates = panel !== "req";
  const setShowCandidates = (on: boolean) => { if (!on) setPanel("req"); };
  useEffect(() => { if (focus) { setChosenReq(focus); setQid(null); setShowCandidates(false); } }, [focus]);
  // 导览要你签的那项决策：没手动选过就直接打开它；导览换到新的一项时，回到它
  const g = useGuide();
  const guided = g.who === me ? ready.find((q) => `sign:${q.family}` === g.target) ?? null : null;
  useEffect(() => { if (guided) { setQid(null); setChosenReq(null); setShowCandidates(false); } }, [guided?.id]);
  const question = all.find((q) => q.id === qid)
    ?? (chosenReq ? ready.find((q) => reqsOf(q).includes(chosenReq)) ?? null : guided ?? ready[0] ?? null);
  // 不挂在需求单上的决策（解密申请、知识冲突、泄露风险）只显示签字区
  const reqId = showCandidates ? null : question ? reqsOf(question)[0] ?? null : chosenReq ?? (reqs.find((r) => r.status !== "merged") ?? reqs[0])?.id ?? null;
  return (
    <>
      <Side>
        <InboxSidebar selected={qid || (guided && question?.id === guided.id) ? question?.id ?? null : null} guided={guided && guided.id !== question?.id ? guided.id : null}
                      reqs={reqs} select={(q) => { setQid(q.id); setChosenReq(null); setShowCandidates(false); }} />
        <SideHead>资料审阅</SideHead>
        <button className={`side-row ${panel === "candidates" ? "on" : ""}`} onClick={() => setPanel("candidates")}>本人资料候选</button>
        <button className={`side-row ${panel === "caps" ? "on" : ""}`} onClick={() => setPanel("caps")}>我授予的能力</button>
        <SideHead>需求单</SideHead>
        {reqs.map((r) => (
          <button key={r.id} onClick={() => { setChosenReq(r.id); setQid(null); setShowCandidates(false); }}
                  className={`side-row ${r.id === reqId ? "on" : ""}`}>
            <p className="text-[13px] font-semibold">{L.phen(r.phenomenon)}</p>
            <p className="truncate text-[12px] text-ink-2">{[r.customer_ids.map(L.name).join("、"), REQ_STATUS[r.status]].filter(Boolean).join(" · ")}</p>
          </button>
        ))}
        {!reqs.length && <p className="px-[18px] py-1 text-[13px] text-ink-3">暂无需求单</p>}
      </Side>
      <RdDesk key={`${me}:${reqId}:${panel}`} question={showCandidates ? null : question} reqId={reqId} panel={panel} />
    </>
  );
}

function RdDesk({ question, reqId, panel }: { question: Question | null; reqId: string | null; panel: "req" | "candidates" | "caps" }) {
  const { me } = useApp();
  const view = useData(() => (reqId ? api.requirement(reqId, me) : Promise.resolve(null)), [reqId, me]);
  const conv = useConversation(null, reqId);
  const [itemIndex, setItemIndex] = useState<number | null>(null);
  const focus = itemIndex === null ? reqId : `${reqId}/chem/${itemIndex}`;
  const onThis = !!question && (!view || reqsOf(question).includes(view.requirement.id));
  return (
    <>
      <div className="mr-[372px]">
        <div className="mx-auto flex max-w-[1080px] flex-col gap-6 px-8 pb-24 pt-7">
          <PendingActions />
          {panel === "caps" ? <GrantedCapabilities />
            : panel === "candidates" ? <CandidateClaims key="my-candidates" reqId={null}
                empty={<EmptyState title="没有待你确认的资料候选" text="资料编译出的候选结论归属你时，会出现在这里等你确认。" />} />
            : view ? (
            <>
              <Backstory id={view.requirement.id} />
              <Narration id={view.requirement.id} />
              <RouteStrip objectId={view.requirement.id} />
              <ReqHead view={view} />
              <CandidateClaims key={reqId ?? ""} reqId={reqId} />
              <SourcePreparationCard reqId={view.requirement.id} />
              <LibrarySearch reqId={view.requirement.id} />
              <PlanCard reqId={view.requirement.id} />
              <ReadinessCard reqId={view.requirement.id} />
              <Trail view={view} sign={onThis && question ? <SignArea key={question.id} q={question} view={view} /> : null} />
              <RequirementSheet view={view} notes={conv?.messages ?? []} selectItem={setItemIndex} />
            </>
          ) : question ? <SignArea key={question.id} q={question} view={null} />
            : <EmptyState title="资料审阅与研发决策" text="从左侧选择待签决策、需求单，或资料审阅。" />}
        </div>
      </div>
      <AgentPanel title={view ? "这张单的来历" : "Agent 协作"} sessionId={null} focus={focus}>
        {itemIndex !== null && <div className="text-[13px] text-ink-2">
          正在协作：{view?.requirement.chem_lang[itemIndex]?.text}
          <button className="ml-2 text-accent" onClick={() => setItemIndex(null)}>返回整张单</button>
        </div>}
        {view && <ReqContext view={view} />}
        <TimeBar />
        <WorkloadCard />
      </AgentPanel>
    </>
  );
}

// ── 需求单抬头：要解决什么、已知条件、没能转译的客户信息 ─────────────
function SourcePreparationCard({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const L = useLabels();
  const draft = useData(() => api.sourcePreparation(reqId, me), [reqId, me]);
  const current = useData(() => api.sourcePreparationStatus(reqId, me), [reqId, me]);
  const claimStatus = { candidate: "待确认", active: "已确认", withdrawn: "已撤回" };
  const capabilityStatus = { proposed: "待确认或批准", active: "生效", suspended: "已挂起", revoked: "已撤销" };
  const forms: Record<string, string> = { ask: "追问", applicable: "适用情境", statement: "可说的话", decrypt: "解密", share: "查看原文" };
  if (!draft) return null;
  return <section className="rounded-xl border border-line bg-white p-5 text-[13px]">
    <h3 className="font-semibold">本单资料准备草稿</h3>
    <p className="mt-1 text-ink-2">保存于 {hhmm(draft.at)} · {draft.by}。保存草稿不代表专业确认；处理结果见下方当前状态。</p>
    <p className="mt-3">保存时条件：{Object.entries(draft.known_slots).map(([s, v]) => `${L.slot(s)}：${v}`).join("；") || "尚未填写"}</p>
    {Object.entries(draft.temperatures).map(([sid, t]) => <p key={sid}>
      {sid} 温度：{t?.status === "filled" ? `${t.celsius?.join("—")}℃` : t ? "明确未知" : "尚未询问"}
      {t && <span className="text-ink-2"> · 原话：{t.quote}</span>}
    </p>)}
    <p className="mt-3 font-medium">依据出处</p>
    {draft.evidence.map((ref, i) => <p key={i} className="break-all text-ink-2">{ref}</p>)}
    {[...new Set(draft.evidence.map((ref) => ref.split("#")[0]))].map((doc) => <SourceTrial key={`${me}:${doc}`} docId={doc} />)}
    <p className="mt-2">关联结论：{draft.claim_ids.join("、") || "未关联"}</p>
    {current && <div className="mt-2">
      <p className="font-medium">当前确认与用途状态</p>
      {current.claims.map((c) => <p key={c.id}>{c.id} · {claimStatus[c.status]}
        {c.confirmed_by && <span> · 确认人：{L.name(c.confirmed_by)}</span>}
      </p>)}
      {current.capabilities.map((c) => <p key={c.id}>
        {c.id} · {forms[c.form] ?? c.form} · {capabilityStatus[c.status]} ·
        {typeof c.audience === "number" ? `给 L${c.audience}` : `给 ${L.name(c.audience)}`}
        {c.approved_by && <span> · 批准人：{L.name(c.approved_by)}</span>}
      </p>)}
      {!current.capabilities.length && <p className="text-ink-2">尚无关联用途能力；确认观察不等于可用于推荐。</p>}
    </div>}
    {draft.compilation && <div className="mt-2">
      <p>操作观察 IR：{draft.compilation.ir_id} · {hhmm(draft.compilation.at)} 导入 {draft.compilation.report.admitted.length} 条待审候选</p>
      {!!draft.compilation.report.unaligned.length && <p>待对齐：{draft.compilation.report.unaligned.join("、")}</p>}
      {!!draft.compilation.report.dropped.length && <p>引文核对未通过：{draft.compilation.report.dropped.join("、")}</p>}
    </div>}
    <p className="mt-2 whitespace-pre-wrap">待核对与补充：{draft.pending || "未填写；仍需研发审阅"}</p>
    <p className="mt-3 text-ink-2">以上为保存时的材料；当前条件与候选状态请结合本单及上方审阅区核对。</p>
  </section>;
}

// 离线骨架把条件与未转译的信息也写成条目（「条件：…」「未转译：…」）；这里归到条件与提醒里显示，条目本身不变。
const isCond = (it: ReqItem) => it.text.startsWith("条件：");
const untranslated = (it: ReqItem) => it.text.startsWith("未转译：");
// 骨架条目写成「『场景词』→ 化学表述」；显示时拆开，正文只放表述
const splitArrow = (text: string) => {
  const m = text.match(/^(?:客户反映)?『([^』]+)』\s*→\s*([\s\S]+)$/);
  return m ? { term: m[1], body: m[2] } : { term: null, body: text };
};

function ReqHead({ view }: { view: RequirementView }) {
  const L = useLabels();
  const req = view.requirement;
  const gaps = [...new Set(req.product_lang.filter(untranslated).map((g) => g.text.replace("未转译：", "")))];
  return (
    <section className="flex flex-col gap-3">
      <PageHead title={L.phen(req.phenomenon)}
                subtitle={[`研发需求单 · ${REQ_STATUS[req.status]}`, `接单研发 ${L.name(req.assigned_rd)}`,
                  req.product_id && `关联产品 ${L.product(req.product_id)}`].filter(Boolean).join(" · ")} />
      <div className="group grid grid-cols-[1fr_auto]">
        <div className="px-5 py-4">
          <p className="eyebrow">要解决什么</p>
          <p className="mt-1 text-[17px] font-semibold leading-[25px]">{req.direction || "产品经理 Agent 尚未起草"}</p>
          {!!Object.keys(req.known_slots).length && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(req.known_slots).map(([slot, value]) => (
                <span key={slot} className="inline-flex h-7 items-center gap-1.5 rounded-[7px] bg-bg px-2.5 text-[13px]">
                  <span className="text-ink-2">{L.slot(slot)}</span><span className="font-semibold">{value}</span>
                </span>
              ))}
            </div>
          )}
          {gaps.map((g) => (
            <p key={g} className="mt-2.5 flex items-center gap-1.5 text-[12.5px] text-attn-ink">
              <i className="h-1.5 w-1.5 shrink-0 rounded-full bg-attn" />
              客户说的「{g}」产品经理 Agent 没能转成产品需求，留意是否漏了约束
            </p>
          ))}
        </div>
        {!!req.hypotheses.length && (
          <div className="w-[300px] border-l border-sep px-5 py-4">
            <p className="eyebrow">方向假设 · 只有研发可见</p>
            {req.hypotheses.map((h) => <p key={h} className="mt-1 text-[13px] leading-5 text-ink-2">{h}</p>)}
          </div>
        )}
      </div>
    </section>
  );
}

// ── 觉在这张单上提出的决策：取自觉视图接口（真实的提出、准备、签字三个时刻），签字区挂在下面 ─────
// 流程由觉提出的决策推动，不在前端写死步骤；试样不经过觉（模拟实验室系统回传），单列一行。
function Trail({ view, sign }: { view: RequirementView; sign: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const t = useData(() => api.timeline(req.id, me), [req.id, me]);
  const glowTrial = useGlow("trial");
  const ended = ({ reused: "已复用现成产品，没有立项", merged: "已并入另一张单", rejected: "已失效" } as Record<string, string>)[req.status];
  const nodes = (t?.nodes ?? []).slice().sort((a, b) => a.created_at.localeCompare(b.created_at));
  const doneNodes = nodes.filter((n) => n.resolved_at != null);
  const [all, setAll] = useState(false);
  // 需求单视图里没有试样状态：试样通过后觉会提出「客户评价」，以此判断试样已录入
  const trial = req.status === "rd_confirmed" && !nodes.some((n) => n.family === "market_eval" || n.family === "seal_points");
  return (
    <section className="flex flex-col gap-4">
      <div>
        <div className="group-title flex items-baseline justify-between">
          <span>觉在这张单上提出的决策</span>
          {t && <span className="num font-normal text-ink-3">
            觉判断 {t.n_judgments} 次 · 觉的大模型调用 {t.n_llm_calls} 次 · 提出 {t.n_questions} 个 · 人签字 {t.n_signatures} 次</span>}
        </div>
        <div className="group">
          {ended && <div className="row text-[14px] text-ink-2">这张单{ended}。</div>}
          {/* 已处置的默认折成一行，只展开还在进行的：签字区紧跟在下面，不用往下翻 */}
          {!!doneNodes.length && (
            <button type="button" onClick={() => setAll(!all)} className="row row-btn !min-h-[40px] text-[12.5px] text-ink-2">
              <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-accent text-[10px] font-semibold text-white">✓</span>
              <span className="min-w-0 flex-1 truncate">已处置 {doneNodes.length} 项：{doneNodes.map((n) => L.family(n.family)).join(" · ")}</span>
              <span className="link shrink-0">{all ? "收起" : "展开"}<ChevronRight open={all} /></span>
            </button>
          )}
          {nodes.filter((n) => all || n.resolved_at == null).map((n) => {
            const done = n.resolved_at != null, ready = !done && n.prepared_at != null;
            return (
              <div key={n.question_id} className={`row !min-h-[44px] ${ready ? "attn-edge" : ""}`}>
                <span className={`num flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                  done ? "bg-accent text-white" : ready ? "bg-attn text-white" : "shadow-[inset_0_0_0_1.5px_rgba(60,60,67,.25)]"}`}>{done ? "✓" : ""}</span>
                <span className="w-[92px] shrink-0 text-[14px] font-semibold">{L.family(n.family)}</span>
                <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-2">
                  {n.family === "ask_back" ? `已派 ${L.name(n.owner_id)} 回头问客户，答复回填需求单`
                    : `${n.owner_id ? `${L.name(n.owner_id)} 准备` : "产品经理 Agent 准备"} · ${n.signer_id ? `${L.name(n.signer_id)} 签字` : "无需签字"}`}
                </span>
                <span className="num shrink-0 text-[12px] text-ink-2">
                  提出 {hhmm(n.created_at)}
                  {n.prepared_at && ` · 准备好 ${hhmm(n.prepared_at)}`}
                  {done ? <span className="text-ink"> · {ACTION[n.action ?? ""] ?? "已处理"} {hhmm(n.resolved_at!)}</span>
                    : ready ? <span className="font-semibold text-attn-ink"> · 等待签字</span> : <span> · 准备中</span>}
                </span>
              </div>
            );
          })}
          {t && !nodes.length && !ended && <div className="row text-[13px] text-ink-2">觉还没有在这张单上提出决策。</div>}
          {trial && (
            <div className="row">
              <span className="h-[18px] w-[18px] shrink-0 rounded-full shadow-[inset_0_0_0_1.5px_rgba(60,60,67,.25)]" />
              <span className="w-[92px] shrink-0 text-[14px] font-semibold">试样</span>
              <span className="min-w-0 flex-1 text-[12.5px] text-ink-2">不经过觉：研发在实验室做试样，在这里录入结果（实验室系统尚未接入）</span>
              <Act kind="plain" label="试样通过" glow={glowTrial} run={() => api.trial(req.id, "pass", me)} />
            </div>
          )}
          {trial && <TrialFail reqId={req.id} />}
        </div>
      </div>
      {sign}
    </section>
  );
}

// Agent 在这张单上的批注：后端目前挂在整张单上，先集中显示在需求单顶部。
// 派单记录（system）是给 Agent 的内部提示，含编号与参数，不显示；回问去向等由上面的决策列表体现。
function SheetNotes({ reqId, notes }: { reqId: string; notes: AgentMessage[] }) {
  const L = useLabels();
  const mine = notes.filter((m) => m.role === "assistant" && m.target != null
    && (m.target === reqId || m.target === `requirement:${reqId}` || m.target.startsWith(`slot:${reqId}/`)));
  if (!mine.length) return null;
  return (
    <Group title="Agent 的批注">
      {mine.map((m, i) => (
        <div key={i} className="row !min-h-0 !items-start !py-2 text-[13px] leading-5">
          <span className="num w-11 shrink-0 text-ink-3">{hhmm(m.at)}</span>
          <span className="min-w-0 flex-1 text-ink-2">{L.scrub(m.text)}</span>
        </div>
      ))}
    </Group>
  );
}

// ── 需求单正文：化学要点为主，每条右侧并排写来历（产品需求 ← 客户原话） ─────
function RequirementSheet({ view, notes, selectItem }: { view: RequirementView; notes: AgentMessage[]; selectItem: (index: number) => void }) {
  const L = useLabels();
  const req = view.requirement;
  const cited = Object.fromEntries(view.cited.map((c) => [c.ku_id, c]));
  const points = req.chem_lang.map((it, i) => ({ it, i })).filter(({ it }) => !isCond(it));
  const l2 = req.product_lang.filter((it) => !isCond(it) && !untranslated(it));
  return (
    <section className="flex flex-col gap-6">
      <SheetNotes reqId={req.id} notes={notes} />
      {/* 放出与封存紧跟签字区：审定发布时要拿说明书对照这两栏 */}
      {(req.public_points || !!req.sealed.length) && (
        <div className="flex flex-col gap-1.5">
        <div className="grid grid-cols-2 gap-4">
          <Group title="已放出的对外要点"><div className="row text-[14px] leading-[21px]">{req.public_points || "—"}</div></Group>
          <Group title="已封存（只有研发可见）">
            {req.sealed.map((s) => <div key={s} className="row text-[14px]">{s}</div>)}
            {!req.sealed.length && <div className="row text-[13px] text-ink-2">无</div>}
          </Group>
        </div>
        <p className="px-1 text-[12px] text-ink-3">L3 向下只有两个出口：你放出的对外要点（包装成说明书交给 L1），和你本人批准的解密；封存项不会出现在任何下层。</p>
        </div>
      )}
      <div>
        <div className="group-title flex items-baseline justify-between">
          <span className="flex items-center gap-2"><LayerChip layer={3} />化学要点</span>
          <span className="font-normal text-ink-3">
            {req.rd_confirmed_by ? `${L.name(req.rd_confirmed_by)} 已确认` : req.status === "rd_accepted" ? "可直接修改；改过的条目可沉淀为你的知识" : ""}
          </span>
        </div>
        <p className="mb-2 px-1 text-[12px] leading-[18px] text-ink-3">只有研发可见。每条都带客户原话和依据了哪位研发的转化知识；产品经理 Agent 只见归属、看不到原文。</p>
        <div className="group">
          <div className="grid grid-cols-[1fr_280px] border-b border-sep bg-[#fafafb] text-[11px] font-semibold tracking-[.04em] text-ink-3">
            <span className="px-5 py-2">研发要做到什么</span>
            <span className="border-l border-sep px-4 py-2">来历：产品需求 ← 客户原话</span>
          </div>
          {points.map(({ it, i }, n) => (
            <Point key={i} n={n} index={i} item={it} view={view} cited={cited} l2={l2}
                   select={() => selectItem(i)}
                   editable={req.status === "rd_accepted"} notes={notesFor(notes, `${req.id}/chem/${i}`)} />
          ))}
          {!points.length && <p className="px-5 py-4 text-[13px] text-ink-2">接单后由你的 Agent 起草化学要点。</p>}
        </div>
      </div>
    </section>
  );
}

function Point({ n, index, item, view, cited, l2, editable, notes, select }: {
  n: number; index: number; item: ReqItem; view: RequirementView; cited: Record<string, CitedKnowledge>; l2: ReqItem[];
  editable: boolean; notes: AgentMessage[]; select: () => void;
}) {
  const { me } = useApp();
  const L = useLabels();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.text);
  // 回放部署：台词要求在含 contains 的条目末尾补上 append
  const scriptArg = useGuideArg("edit");
  const scripted = scriptArg ? JSON.parse(scriptArg) as { contains: string; append: string } : null;
  const mine = scripted && item.text.includes(scripted.contains) ? item.text + scripted.append : null;
  const { term, body } = splitArrow(item.text);
  const basis = item.ku_refs.map((r) => cited[r]).filter(Boolean);
  const from = l2.find((p) => p.quote_refs.some((q) => item.quote_refs.includes(q)));
  return (
    <div className="group/pt grid grid-cols-[1fr_280px] border-b border-sep last:border-b-0">
      <div className="flex gap-3 px-5 py-3.5">
        <span className="num w-5 shrink-0 pt-[2px] text-[13px] font-semibold text-ink-3">{n + 1}</span>
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex flex-col gap-1.5">
              <Field value={text} onChange={setText} rows={3} label={`第 ${n + 1} 条`} />
              <span className="flex gap-2">
                <Act label="保存" glow={!!mine && text === mine} run={() => api.editItem(view.requirement.id, index, { ...item, text }, me).then(() => setEditing(false))} />
                <button type="button" className="btn btn-quiet" onClick={() => { setText(item.text); setEditing(false); }}>取消</button>
              </span>
            </div>
          ) : <p className="text-[15px] leading-[23px]">{body}</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-2">
            {item.edited_by == null ? <AgentMark /> : <span>{L.name(item.edited_by)} 修改</span>}
            {basis.map((c) => <KnowledgeChip key={c.ku_id} c={c} />)}
            {editable && !editing && <button type="button" className="link !text-[12px]" onClick={() => setEditing(true)}>修改</button>}
            <button type="button" className="link !text-[12px] opacity-0 transition-opacity group-hover/pt:opacity-100 focus:opacity-100" onClick={select}>就此条问 Agent</button>
            {editable && mine && text !== mine && (
              <button type="button" className="chip glow" onClick={() => { setText(mine); setEditing(true); }}>演示自动填入</button>
            )}
          </div>
          <Notes notes={notes.filter((m) => m.role === "assistant")} />
        </div>
      </div>
      <div className="flex flex-col gap-1 border-l border-sep bg-[#fcfcfd] px-4 py-3.5 text-[12.5px] leading-[19px]">
        {term && <p className="text-ink-2">针对「<span className="text-ink">{term}</span>」</p>}
        {from && <p className="text-ink-2">← {splitArrow(from.text).body}</p>}
        {item.quote_refs.map((r) => <p key={r} className="text-ink-3">←「{view.quotes[r]}」</p>)}
      </div>
    </div>
  );
}

// 依据：谁的哪条知识；有原文时点开看，看不到原文时只显示归属
function KnowledgeChip({ c }: { c: CitedKnowledge }) {
  const L = useLabels();
  const { me } = useApp();
  const [open, setOpen] = useState(false);
  const label = `${L.name(c.owner)}的知识 · 被引用 ${c.n_cited} 次`;
  if (c.text == null) return <span className="tag" title={`L${c.level} 知识，原文不可见`}>{label}
    {c.level === 3 && me.startsWith("rd:") && <Act kind="quiet" label="申请查看" run={() => api.requestShare(c.ku_id, me)} />}</span>;
  return (
    <span className="relative">
      <button type="button" onClick={() => setOpen(!open)} className="tag tag-accent">{label}</button>
      {open && (
        <span className="popover anim-fade left-0 top-6 block w-[340px] p-3 text-[12.5px] leading-[19px]" onMouseLeave={() => setOpen(false)}>
          <span className="block font-semibold">{L.scrub(c.title)}</span>
          <span className="mt-1 block whitespace-pre-wrap text-ink-2">{c.text}</span>
        </span>
      )}
    </span>
  );
}

// 右侧：这张单的来历——客户原话、业务员的升级说明、现成产品结论、产品需求全文、合并判断、退回记录
function ReqContext({ view }: { view: RequirementView }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const route = useData(() => api.route(req.id, me), [req.id, me]);
  const business = (route?.basis ?? []).filter((b) => b.family === "opportunity" && b.action === "sign" && b.note);
  const l2 = req.product_lang.filter((it) => !isCond(it) && !untranslated(it));
  return (
    <>
      {req.session_ids.map((sid, n) => {
        // 原话按会话分组：合并后的单有几位客户的原话（turn id 形如 turn:<会话>:<序号>）
        const mine = Object.entries(view.quotes).filter(([id]) => id.startsWith(`turn:${sid}:`));
        return !!mine.length && (
          <Group key={sid} title={req.session_ids.length > 1 ? `客户 ${n + 1} 的原话` : "客户原话"}>
            {mine.map(([id, t]) => <div key={id} className="row !min-h-0 !py-2 text-[13px] leading-5">「{t}」</div>)}
          </Group>
        );
      })}
      {req.escalate_note && <Group title="业务员的升级说明"><div className="row text-[13px] leading-5">{req.escalate_note}</div></Group>}
      {req.reuse && (
        <Group title="现成产品">
          <div className="row text-[13px] leading-5">{req.reuse.product_id ? L.product(req.reuse.product_id) : L.scrub(req.reuse.note)}</div>
          {req.reuse.declined_reason && <div className="row text-[13px] text-ink-2">不采用：{req.reuse.declined_reason}</div>}
        </Group>
      )}
      {!!l2.length && (
        <Group title={<span className="flex items-center gap-2"><LayerChip layer={2} />产品需求</span>}
               foot={`产品经理 Agent 用 L2 知识把客户原话转成产品需求，看不到 L3 原文与封存项${req.rd_accepted_by ? ` · ${L.name(req.rd_accepted_by)} 已接单` : ""}`}>
          {l2.map((it, i) => <div key={i} className="row !min-h-0 !py-2 text-[13px] leading-5">{splitArrow(it.text).body}</div>)}
        </Group>
      )}
      {business.map((b) => (
        <Group key={b.question_id} title={`产品经理 ${L.name(b.by)} 的商业判断`}>
          <div className="row attn-edge text-[13px] leading-5">{b.note}</div>
        </Group>
      ))}
      {req.merge_note && <Group title="产品经理 Agent 的合并判断"><div className="row text-[13px] leading-5">{L.scrub(req.merge_note)}</div></Group>}
      {!!req.return_notes.length && (
        <Group title="退回记录">{req.return_notes.map((n, i) => <div key={i} className="row text-[13px] leading-5">{n}</div>)}</Group>
      )}
    </>
  );
}

// ── 签字区：随当前选中的决策变化 ─────────────────────────────
export function SignArea({ q, view }: { q: Question; view: RequirementView | null }) {
  const { me } = useApp();
  const L = useLabels();
  const glow = useGlow(`sign:${q.family}`);
  // v8 收口：推进类问题不给「忽略」，不想处理就先放着；异常类问题可以写理由越过
  const dismiss = ANOMALY.has(q.family) ? <Overrule q={q} /> : null;
  const head = (
    <div className="row attn-edge">
      <span className="tag tag-attn">{L.family(q.family)}</span>
      <p className="min-w-0 flex-1 truncate text-[14px] font-semibold">{L.scrub(q.title)}</p>
      <Score q={q} />
    </div>
  );
  if (q.prepared_at == null) {
    return (
      <Group title="待你签字">
        <div className="row"><span className="tag">{L.family(q.family)}</span>
          <p className="flex-1 text-[14px] text-ink-2">{ownerText(q, me, L.name)}，准备好后才能签字</p></div>
      </Group>
    );
  }
  const req = view?.requirement;
  const evidence = q.evidence.map((e, i) => (
    <div key={i} className="row !items-start text-[13px] leading-5 text-ink-2">{L.scrub(e.summary)}{e.quote && `「${e.quote}」`}</div>
  ));
  const body = (() => {
    if (q.family === "trial_rework") return <>{evidence}<div className="row gap-2">
      <Act label="退回重新转译" run={() => api.rework(q.refs.requirement_id, me)} />{dismiss}</div></>;
    if (q.family === "trial_risk") return <TrialRiskReview q={q} dismiss={dismiss} evidence={evidence} />;
    if (q.family === "stale_capability") return <StaleReview q={q} dismiss={dismiss} evidence={evidence} />;
    if (q.family === "qi_grant" && q.refs.form === "statement") return <StatementGrant q={q} dismiss={dismiss} evidence={evidence} />;
    if (q.family === "qi_grant" && q.refs.scope) return <ApplicableGrant key={q.id} q={q} dismiss={dismiss} evidence={evidence} />;
    if (q.family === "qi_grant") return <>{evidence}<div className="row gap-2">
      <Act label="签字授予" run={() => api.grantCapability(q.id, me)} />{dismiss}</div></>;
    if (q.family === "qi_review") return <QiEvidenceReview key={q.id} q={q} dismiss={dismiss} evidence={evidence} />;
    if (q.family === "decrypt_request") return <DecryptReview q={q} dismiss={dismiss} evidence={evidence} />;
    if (!req) return <>{evidence}<div className="row text-[13px] text-ink-2">证据 {q.evidence.length} 条</div><div className="row gap-2">{q.family === "knowledge_conflict" && <Act label="更新适用表" run={() => api.resolve(q.id, "update_sheet", me)} />}{q.family === "leak_risk" && <Act label="冻结上层知识检索" run={() => api.resolve(q.id, "freeze_access", me)} />}{dismiss}</div></>;
    switch (q.family) {
      case "reuse_product": return <ReuseReview q={q} view={view!} dismiss={dismiss} />;
      case "opportunity": return <MergeReview q={q} view={view!} dismiss={dismiss} />;
      case "accept_requirement": return <AcceptReview reqId={req.id} dismiss={dismiss} evidence={evidence} />;
      case "confirm_translation": return <ConfirmReview view={view!} dismiss={dismiss} />;
      case "contribution": return <ContributionReview view={view!} dismiss={dismiss} />;
      case "seal_points": return <PointsReview view={view!} dismiss={dismiss} />;
      case "release": case "seal_leak": return <SheetReview view={view!} release={q.family === "release"} dismiss={dismiss} />;
      default: return <>{evidence}<div className="row">{dismiss}</div></>;
    }
  })();
  return <Group title="待你签字" className={glow ? "guide-scope" : ""}>{head}{body}</Group>;
}

// 越过异常提示：理由留在结案说明里，作为觉的标签
function Overrule({ q }: { q: Question }) {
  const { me } = useApp();
  const [note, setNote] = useState("");
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2">
      <Field value={note} onChange={setNote} rows={1} placeholder="判断无须处理的理由" />
      <Act kind="quiet" label="越过" disabled={!note.trim()} run={() => api.resolve(q.id, "dismiss", me, note)} />
    </span>
  );
}

// 确认化学要点（confirm_translation）：签的是「下方化学要点就是研发要做的事」；这里说清转了什么、依据谁、还缺什么
function ConfirmReview({ view, dismiss }: { view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const cited = Object.fromEntries(view.cited.map((c) => [c.ku_id, c]));
  const points = req.chem_lang.filter((it) => !isCond(it));
  const owners = [...new Set(points.flatMap((it) => it.ku_refs.map((r) => cited[r]?.owner).filter(Boolean)))] as string[];
  const edited = points.filter((it) => it.edited_by != null).length;
  const known = Object.entries(req.known_slots);
  // 回问、失真提示只作参考：是否等客户答复再确认由研发判断
  const t = useData(() => api.timeline(req.id, me), [req.id, me]);
  const waiting = (t?.nodes ?? []).filter((n) => (n.family === "ask_back" || n.family === "distortion") && n.resolved_at == null);
  return (
    <>
      <div className="row !items-start flex-col !gap-1">
        <p className="text-[14px] font-semibold">化言已经为您辅助理解了客户的需求，请您确认</p>
        <p className="text-[13px] leading-5 text-ink-2">
          客户要的归结为下面 {points.length} 条化学要点{owners.length ? `，依据 ${owners.map(L.name).join("、")} 的转化知识` : ""}{edited ? `；您已改过 ${edited} 条` : ""}。
        </p>
      </div>
      {points.map((it, n) => (
        <div key={n} className="row !items-start text-[13px] leading-5">
          <span className="num w-5 shrink-0 text-ink-3">{n + 1}</span>
          <span className="min-w-0 flex-1 truncate">{splitArrow(it.text).body}</span>
        </div>
      ))}
      {!!known.length && <div className="row text-[13px] text-ink-2">已知条件：{known.map(([s, v]) => `${L.slot(s)} ${v}`).join("；")}</div>}
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2">
          <p className="text-[13px] text-ink-2">每条的来历（客户原话）在下方「化学要点 · L3」，理解有偏差可以直接「修改」。确认后按这几条安排试样。</p>
          {!!waiting.length && <p className="rounded-[8px] bg-attn-bg px-3 py-2 text-[13px] leading-5 text-attn-ink">
            还在等客户补充信息：{waiting.map((n) => n.family === "ask_back" ? `${L.name(n.owner_id)} 正在回头问客户（回问）` : "转译和客户原话对不上，待核对").join("；")}。
            可以等答复回填需求单后再确认，这期间可以先看、先改。</p>}
          <div className="flex flex-wrap gap-2"><Act label="确认" run={() => api.confirm(req.id, me)} />{dismiss}</div>
        </div>
      </div>
    </>
  );
}

function AcceptReview({ reqId, dismiss, evidence }: { reqId: string; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me, meta } = useApp();
  const L = useLabels();
  const { all } = useInbox();
  const distortions = all.filter((d) => d.family === "distortion" && d.refs.requirement_id === reqId);
  const [mode, setMode] = useState<"accept" | "applicable" | "other" | "ask" | "return">("accept");
  const [reason, setReason] = useState("");
  const [slots, setSlots] = useState<string[]>([]);
  const [product, setProduct] = useState(meta.products[0]?.id ?? "");
  const [limits, setLimits] = useState("");
  // V11.7 以本单的资料候选为依据：先读审阅原文，随不立项一起签字确认；依据来源改版时这条适用随之挂起等复核
  const claims = (useData(() => api.claims(reqId, me), [reqId, me]) ?? []).filter((c) => c.owner === me);
  const [basis, setBasis] = useState<string[]>([]);
  const [review, setReview] = useState<ClaimReview | null>(null);
  // 演示讲解：研发判「已有产品适用」要选的产品与依据，由「演示自动填入」填好（录制回放里须与录制一致）
  const scripted = useGuideArg("decline");
  const dec = scripted ? JSON.parse(scripted) as { product: string; reason: string } : null;
  const filled = !!dec && product === dec.product && reason === dec.reason;
  const tab = (k: typeof mode, label: string) => (
    <button type="button" onClick={() => { setMode(k); setReason(""); }}
            className={`h-7 rounded-[7px] px-3 text-[13px] ${mode === k ? "bg-white font-semibold shadow-[0_0_0_.5px_rgba(0,0,0,.14),0_1px_1.5px_rgba(0,0,0,.07)]" : "text-ink-2"} ${
              dec && k === "applicable" && mode !== k ? "glow" : ""}`}>{label}</button>
  );
  return (
    <>
      {evidence}
      <MatchedLimits reqId={reqId} />
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2.5">
          <div className="inline-flex w-fit gap-0.5 rounded-[9px] bg-fill p-0.5">
            {tab("accept", "接单立项")}{tab("applicable", "不立项：已有产品适用")}{tab("other", "不立项：其他原因")}{tab("ask", "先回问客户")}{tab("return", "退回补充")}
          </div>
          {mode === "accept" && <>
            <p className="text-[13px] text-ink-2">接单即立项：被引用的 L2 知识给归属人记分。</p>
            {distortions.length > 0 && <p className="text-[13px] leading-5 text-ink-2">供参考，同单的失真提示：{distortions.flatMap((d) => d.evidence.map((e) => L.scrub(e.summary))).join("；")}。要不要先回问客户由您判断。</p>}
            <div className="flex flex-wrap gap-2"><Act label="接单立项" run={() => api.accept(reqId, me)} />{dismiss}</div>
          </>}
          {mode === "applicable" && <>
            <p className="text-[13px] leading-5 text-ink-2">现有产品其实能解决，只是说明书没标注这种用法：客户会收到该产品的推荐；觉随后请产品经理把它加进产品适用范围，同类需求以后在客户自助阶段就解决，不再进研发。</p>
            <select value={product} onChange={(e) => setProduct(e.target.value)} className="field !h-8 w-fit !py-0" aria-label="适用的产品">
              {meta.products.map((p) => <option key={p.id} value={p.id}>{L.product(p.id)}</option>)}
            </select>
            <Field value={reason} onChange={setReason} placeholder="判断依据（产品经理可见，提交前做研发术语自查）" />
            <Field value={limits} onChange={setLimits} placeholder="限制条件（可空；原文保留，带限制的适用不在客户自助阶段自动推荐）" />
            {claims.length > 0 && <div className="flex flex-col gap-1.5 text-[13px]">
              <p className="text-ink-2">以本单资料候选为依据（可选；勾选后先读审阅原文，随不立项一起签字确认）：</p>
              {claims.map((c) => <label key={c.id} className="flex items-start gap-2">
                <input type="checkbox" checked={basis.includes(c.id)} onChange={(e) => {
                  setReview(null);
                  setBasis(e.target.checked ? [...basis, c.id] : basis.filter((id) => id !== c.id));
                }} /><span>{c.title}</span></label>)}
              {basis.length > 0 && !review && <div><Act kind="plain" label="读取所选结论的审阅依据" run={() => api.reviewClaims(basis, me).then(setReview)} /></div>}
              {review && <EvidenceReviewPanel review={review} compactSingle />}
            </div>}
            {dec && !filled && <div><button type="button" className="chip glow" onClick={() => { setProduct(dec.product); setReason(dec.reason); }}>演示自动填入</button></div>}
            <div><Act label="不立项：已有产品适用" disabled={!reason.trim() || (basis.length > 0 && !review)} glow={filled}
                      run={() => api.decline(reqId, reason, me, product, limits, basis, review?.reviewed_evidence)} /></div>
          </>}
          {mode === "other" && <>
            <Field value={reason} onChange={setReason} placeholder="不立项原因（客户会收到「已记录，暂无方案」）" />
            <div><Act kind="plain" label="不立项" disabled={!reason.trim()} run={() => api.decline(reqId, reason, me, null)} /></div>
          </>}
          {mode === "ask" && <>
            <p className="text-[13px] text-ink-2">缺的是客户才知道的条件：勾选后由业务员向客户回问，答完觉再提接单；不经过产品经理。</p>
            <SlotPicker value={slots} onChange={setSlots} />
            <div><Act kind="plain" label="先回问客户" disabled={!slots.length} run={() => api.askBeforeAccept(reqId, slots, me)} /></div>
          </>}
          {mode === "return" && <>
            <p className="text-[13px] text-ink-2">需求写得不清楚：退回给产品经理 Agent 按理由重写。</p>
            <Field value={reason} onChange={setReason} placeholder="退回理由（提交前做研发术语自查，产品经理可见）" />
            <div><Act kind="plain" label="退回" disabled={!reason.trim()} run={() => api.returnReq(reqId, reason, me)} /></div>
          </>}
        </div>
      </div>
    </>
  );
}

// V9.5：已有研发判断带限制、条件与本单相符的适用；不自动推荐，原文交研发对照
function MatchedLimits({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const L = useLabels();
  const limited = useData(() => api.matchedLimits(reqId, me), [reqId, me]) ?? [];
  return <>{limited.map((m) => (
    <div key={m.capability_id} className="row !items-start text-[13px] leading-5">
      <p className="rounded-[8px] bg-attn-bg px-3 py-2 text-attn-ink">
        {L.name(m.granted_by)} 判过 {L.product(m.product_id)} 适用同类情况，但带限制：「{m.limits}」。化言没有自动推荐，请对照本单判断。</p>
    </div>
  ))}</>;
}

// 现成产品审定（D22）：产品、依据的 L2 案例原文、可改的给客户说明、自查结果
function ReuseReview({ q, view, dismiss }: { q: Question; view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const r = req.reuse!;
  const [note, setNote] = useState(r.customer_note);
  useEffect(() => setNote(r.customer_note), [r.customer_note]);
  const scriptArg = useGuideArg("reuse-note");   // 回放部署：台词要求把说明里的一个词换掉
  const scripted = scriptArg ? r.customer_note.replace(...(JSON.parse(scriptArg) as [string, string])) : null;
  const [reason, setReason] = useState("");
  const cases = view.cited.filter((c) => r.ku_refs.includes(c.ku_id));
  return (
    <>
      <div className="row"><span className="w-20 shrink-0 text-[13px] text-ink-2">产品</span>
        <span className="text-[15px] font-semibold">{L.product(r.product_id)}</span></div>
      <MatchedLimits reqId={req.id} />
      <div className="row !items-start"><span className="w-20 shrink-0 text-[13px] text-ink-2">依据</span>
        <div className="min-w-0 flex-1">{cases.map((c) => <p key={c.ku_id} className="mb-1"><KnowledgeChip c={c} /></p>)}
          {q.evidence.map((e, i) => <p key={i} className="text-[12px] text-ink-2">{L.scrub(e.summary)}</p>)}</div></div>
      <div className="row !items-start">
        <span className="w-20 shrink-0 pt-1 text-[13px] text-ink-2">给客户的说明</span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="flex items-center gap-2">{note === r.customer_note && <AgentMark who="产品经理 Agent 起草" />}
            <span className="text-[12px] text-ink-2">保存时做泄露自查，命中则门面拒绝并给出句序号</span></p>
          <Field value={note} onChange={setNote} rows={3} label="给客户的说明" />
          {scripted && note !== scripted && <div><button type="button" className="chip glow" onClick={() => setNote(scripted)}>演示自动填入</button></div>}
          {note !== r.customer_note && <div><Act kind="plain" label="保存修改" glow={note === scripted} run={() => api.reuseNote(req.id, note, me)} /></div>}
        </div>
      </div>
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <Act label="通过并转给业务员" disabled={note !== r.customer_note} run={() => api.adoptReuse(req.id, me)} />{dismiss}
          </div>
          <Field value={reason} onChange={setReason} placeholder="不采用的理由（随后觉提出是否接单）" />
          <div><Act kind="plain" label="不采用" disabled={!reason.trim()} run={() => api.declineReuse(req.id, reason, me)} /></div>
        </div>
      </div>
    </>
  );
}

// 机会汇聚（D19）：并排各单的客户原话与产品经理 Agent 的判断理由
function MergeReview({ q, view, dismiss }: { q: Question; view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const members = view.requirement.merge_from;
  const others = useData(() => Promise.all(members.map((id) => api.requirement(id, me))), [members.join(","), me]) ?? [];
  const all = [view, ...others];
  return (
    <>
      <div className="row text-[13px] text-ink-2">{all.length} 位客户、同类需求：{L.phen(view.requirement.phenomenon)}</div>
      <div className="row !items-stretch gap-3">
        {all.map((v, i) => (
          <div key={v.requirement.id} className="min-w-0 flex-1 rounded-[8px] bg-bg px-3 py-2">
            <p className="text-[12px] font-semibold text-ink-2">{i === 0 ? "主单" : `拟并入 ${i}`}</p>
            {Object.values(v.quotes).map((t, j) => <p key={j} className="text-[13px] leading-5">「{t}」</p>)}
          </div>
        ))}
      </div>
      <div className="row !items-start">
        <span className="w-20 shrink-0 text-[13px] text-ink-2">判断理由</span>
        <p className="flex-1 text-[13px] leading-5">{view.requirement.merge_note || "—"} <AgentMark who="产品经理 Agent 起草" /></p>
      </div>
      {q.evidence.map((e, i) => <div key={i} className="row text-[12px] text-ink-2">{L.scrub(e.summary)}</div>)}
      <div className="row gap-2"><Act label="合并" run={() => api.merge(q.id, me)} />{dismiss}</div>
    </>
  );
}

// 沉淀：逐条显示 Agent 提炼的转化知识，每条一个按钮
function ContributionReview({ view, dismiss }: { view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const req = view.requirement;
  return (
    <>
      {req.contribution_drafts.map((d, i) => (
        <div key={i} className="row !items-start">
          <span className="num w-8 shrink-0 text-[13px] text-ink-3">第 {d.item_index + 1} 条</span>
          <div className="min-w-0 flex-1">
            <p className="text-[14px]">「{d.scene_phrase}」→ {d.chem_term} <AgentMark /></p>
            {d.note && <p className="text-[12px] leading-[18px] text-ink-2">{d.note}</p>}
          </div>
          <Act label="沉淀为我的知识" run={() => api.contribute(req.id, d.item_index, d.scene_phrase, d.chem_term, me)} />
        </div>
      ))}
      {!req.contribution_drafts.length && <div className="row text-[13px] text-ink-2">Agent 没有提炼出可沉淀的条目</div>}
      <div className="row">{dismiss}</div>
    </>
  );
}

// 封存 / 放出两栏：左「对客户说」、右「封存（只有研发可见）」，自查命中的句子红色下划线
function PointsReview({ view, dismiss }: { view: RequirementView; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const d = req.points_draft ?? { public: "", sealed: [], self_check: [] };
  const [pub, setPub] = useState(d.public);
  const [sealed, setSealed] = useState(d.sealed.join("\n"));
  useEffect(() => { setPub(d.public); setSealed(d.sealed.join("\n")); }, [d.public, d.sealed.join("\n")]);
  const untouched = pub === d.public && sealed === d.sealed.join("\n");
  return (
    <>
      <div className="row !items-start gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="flex items-center gap-2 text-[12px] font-semibold text-ink-2">对客户说 {untouched && <AgentMark />}</p>
          {untouched && !!d.self_check.length && (
            <p className="rounded-[8px] bg-bg px-2.5 py-1.5 text-[13px] leading-5"><Marked text={d.public} hits={d.self_check.map((h) => h.index)} /></p>
          )}
          <Field value={pub} onChange={setPub} rows={4} label="对客户说" />
          {untouched && d.self_check.map((h) => (
            <p key={h.index} className="text-[12px] text-danger">第 {h.index + 1} 句{L.leak(h.source)}</p>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="text-[12px] font-semibold text-ink-2">封存（只有研发可见，一行一项）</p>
          <Field value={sealed} onChange={setSealed} rows={4} label="封存" />
        </div>
      </div>
      <div className="row gap-2">
        <Act label="签字：封存 / 放出" run={() => api.points(req.id, pub, sealed.split("\n").map((s) => s.trim()).filter(Boolean), me)} />
        {dismiss}
      </div>
    </>
  );
}

// 发布审定 / 说明书改写：业务员将看到的说明书与用法 + 泄密检查结果
function SheetReview({ view, release, dismiss }: { view: RequirementView; release: boolean; dismiss: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const req = view.requirement;
  const leak = useData<LeakHit[]>(() => api.leak(req.id, me), [req.id, me]) ?? [];
  const s = req.sheet ?? { sheet: "", usage: "" };
  const [sheet, setSheet] = useState(s.sheet);
  const [usage, setUsage] = useState(s.usage);
  useEffect(() => { setSheet(s.sheet); setUsage(s.usage); }, [s.sheet, s.usage]);
  const changed = sheet !== s.sheet || usage !== s.usage;
  const opened = req.product_id === `proj:${req.id}`;     // 接单时新立的项目：名称、类别由研发发布时填写
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  return (
    <>
      {release && (
        <div className="row !items-start flex-col !gap-1">
          <p className="text-[14px] font-semibold">新品 {L.product(req.product_id)} 要上架了：下面是给业务员和客户看的说明书，请您把关</p>
          <p className="text-[13px] leading-5 text-ink-2">
            产品经理 Agent 只用您在「封存 / 放出」里放出的对外要点（紧接下方，与封存项并排）包装，读不到化学要点和封存项。请看两件事：有没有说出不该对外的（机理、配方、您封存的工艺），
            业务员照着讲客户能不能听懂；不对就直接改、保存。点「审定发布」后新品上架，同类客户在业务员那里会直接被推荐它，客户看到的就是这段话。
          </p>
        </div>
      )}
      <div className="row !items-start">
        <span className="w-14 shrink-0 text-[13px] text-ink-2">说明书</span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          {!changed && <p className="text-[14px] leading-[22px]"><Marked text={s.sheet} hits={leak.map((h) => h.index)} /> <AgentMark who="产品经理 Agent 包装" /></p>}
          <Field value={sheet} onChange={setSheet} rows={3} label="说明书" />
        </div>
      </div>
      <div className="row !items-start">
        <span className="w-14 shrink-0 text-[13px] text-ink-2">用法</span>
        <div className="flex-1"><Field value={usage} onChange={setUsage} label="用法" /></div>
      </div>
      <div className="row !items-start text-[13px]">
        <span className="w-14 shrink-0 text-ink-2">泄密检查</span>
        <div className="flex-1">
          {leak.length ? leak.map((h) => <p key={h.index} className="text-danger">第 {h.index + 1} 句{L.leak(h.source)}</p>)
            : <p className="text-ink-2">未命中封存项与研发术语（规则匹配挡不住换说法，最后一道闸是你的审定）</p>}
        </div>
      </div>
      {release && opened && (
        <div className="row !items-start">
          <span className="w-14 shrink-0 text-[13px] text-ink-2">新品</span>
          <div className="flex min-w-0 flex-1 gap-2">
            <div className="flex-1"><Field value={name} onChange={setName} rows={1} label="产品名称" placeholder="产品名称（必填）" /></div>
            <div className="w-40"><Field value={category} onChange={setCategory} rows={1} label="类别" placeholder="类别，如匀染剂" /></div>
          </div>
        </div>
      )}
      <div className="row gap-2">
        {changed && <Act kind="plain" label="保存说明书" run={() => api.sheet(req.id, { sheet, usage }, me)} />}
        {release && <Act label="审定发布" disabled={changed || (opened && !(name.trim() && category.trim()))}
          run={() => api.release(req.id, me, name, category)} />}
        {dismiss}
      </div>
    </>
  );
}

const CAUSES = { product: "产品", equipment: "设备", operation: "操作", requirement: "需求条件缺失" } as const;

function TrialFail({ reqId }: { reqId: string }) {
  const { me } = useApp();
  const [cause, setCause] = useState<keyof typeof CAUSES>("product");
  const [missing, setMissing] = useState<string[]>([]);
  return (
    <div className="row !items-start">
      <span className="w-[110px] shrink-0 text-[13px] text-ink-2">不通过的原因</span>
      <div className="flex flex-1 flex-col gap-2">
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(CAUSES).map(([k, label]) => (
            <button key={k} type="button" className={`chip ${cause === k ? "tag-attn" : ""}`}
              onClick={() => setCause(k as keyof typeof CAUSES)}>{label}</button>
          ))}
        </div>
        {cause === "requirement" && <SlotPicker value={missing} onChange={setMissing} />}
        <div><Act kind="quiet" label="录入不通过" run={() => api.trial(reqId, "fail", me, cause, cause === "requirement" ? missing : [])} /></div>
      </div>
    </div>
  );
}

function TrialRiskReview({ q, dismiss, evidence }: { q: Question; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me } = useApp();
  const [slots, setSlots] = useState<string[]>([]);
  return (
    <>
      {evidence}
      <div className="row !items-start">
        <span className="w-[110px] shrink-0 text-[13px] text-ink-2">先回问哪些条件</span>
        <div className="flex flex-1 flex-col gap-2">
          <SlotPicker value={slots} onChange={setSlots} />
          <div className="flex flex-wrap gap-2">
            <Act label="先回问" run={() => api.returnForConditions(q.refs.requirement_id, slots, me)} />{dismiss}
          </div>
        </div>
      </div>
    </>
  );
}

// 判断过时（stale_capability）：失败集中的取值默认勾掉，研发确认后收窄；也可整条撤销或保留
function StaleReview({ q, dismiss, evidence }: { q: Question; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const scope: Record<string, string[]> = JSON.parse(q.refs.scope);
  const failing = q.refs.fail_values ? q.refs.fail_values.split(",") : [];
  const [drop, setDrop] = useState<string[]>(failing.slice(0, 1));
  const toggle = (k: string) => setDrop(drop.includes(k) ? drop.filter((x) => x !== k) : [...drop, k]);
  const conditions = Object.fromEntries(Object.entries(scope)
    .map(([s, vs]) => [s, vs.filter((v) => !drop.includes(`${s}=${v}`))] as const)
    .filter(([s, vs]) => vs.length !== scope[s].length));
  return (
    <>
      {evidence}
      <div className="row !items-start">
        <span className="w-[110px] shrink-0 text-[13px] text-ink-2">收窄：去掉哪些取值</span>
        <div className="flex flex-1 flex-col gap-2">
          {Object.entries(scope).map(([s, vs]) => (
            <div key={s} className="flex flex-wrap items-center gap-2 text-[13px]">
              <span className="text-ink-2">{L.slot(s)}</span>
              {vs.map((v) => {
                const k = `${s}=${v}`;
                return (
                  <label key={k} className={failing.includes(k) ? "text-red-600" : ""}>
                    <input type="checkbox" checked={!drop.includes(k)} onChange={() => toggle(k)} /> {v}
                  </label>
                );
              })}
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <Act label="收窄" run={() => api.narrowCapability(q.refs.capability_id, conditions, me)} />
            <Act kind="plain" label="撤销" run={() => api.revokeCapability(q.refs.capability_id, me)} />{dismiss}
          </div>
        </div>
      </div>
    </>
  );
}

// V11.10 授予适用能力：默认范围只到试过的条件，研发可以放宽取值、温度，删掉不再限制的那行原文
function ApplicableGrant({ q, dismiss, evidence }: { q: Question; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me, meta } = useApp();
  const L = useLabels();
  const tested: GrantScope = JSON.parse(q.refs.scope);
  const [conditions, setConditions] = useState(tested.conditions);
  const [temp, setTemp] = useState(tested.temperature_c ? tested.temperature_c.map(String) : ["", ""]);
  const [limits, setLimits] = useState(tested.limits);
  // 试过的条件逐个可改；限制原文里写着「试样没有覆盖」的条件也能在这里补上取值
  const rows = meta.slots.filter((s) => s.id in tested.conditions || tested.limits.includes(`${s.label}：`));
  const toggle = (s: string, v: string) => {
    const vs = conditions[s] ?? [];
    const next = vs.includes(v) ? vs.filter((x) => x !== v) : [...vs, v];
    setConditions(Object.fromEntries(Object.entries({ ...conditions, [s]: next }).filter(([k, x]) => x.length || k in tested.conditions)));
  };
  const scope: GrantScope = { conditions, temperature_c: temp[0] && temp[1] ? [Number(temp[0]), Number(temp[1])] : null, limits };
  const changed = JSON.stringify(scope) !== JSON.stringify(tested);
  return (
    <>
      {evidence}
      <div className="row !items-start">
        <span className="w-[110px] shrink-0 text-[13px] text-ink-2">授予范围（默认只到试过的条件）</span>
        <div className="flex flex-1 flex-col gap-2 text-[13px]">
          {rows.map((s) => (
            <div key={s.id} className="flex flex-wrap items-center gap-2">
              <span className="text-ink-2">{L.slot(s.id)}</span>
              {s.values.map((v) => (
                <label key={v}><input type="checkbox" checked={(conditions[s.id] ?? []).includes(v)} onChange={() => toggle(s.id, v)} /> {v}</label>
              ))}
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-ink-2">温度</span>
            <input className="w-16 rounded border border-line px-1.5 py-0.5" value={temp[0]} onChange={(e) => setTemp([e.target.value, temp[1]])} />—
            <input className="w-16 rounded border border-line px-1.5 py-0.5" value={temp[1]} onChange={(e) => setTemp([temp[0], e.target.value])} />℃
            <span className="text-ink-3">两格都空 = 不限温度</span>
          </div>
          <span className="text-ink-2">限制原文（删掉一行，这一条就不再限制）</span>
          <Field value={limits} onChange={setLimits} rows={3} label="限制原文" />
          <div className="flex flex-wrap gap-2">
            <Act label={changed ? "按改过的范围签字授予" : "签字授予"} run={() => api.grantCapability(q.id, me, "", changed ? scope : undefined)} />{dismiss}
          </div>
        </div>
      </div>
    </>
  );
}

function StatementGrant({ q, dismiss, evidence }: { q: Question; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me } = useApp();
  const [text, setText] = useState("");
  return (
    <>
      {evidence}
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2">
          <Field value={text} onChange={setText} rows={2} placeholder={`写给 L${q.refs.audience} 可以说的一句话（不含结论原文与机理）`} />
          <div className="flex flex-wrap gap-2"><Act label="签字授予这句话" run={() => api.grantCapability(q.id, me, text)} />{dismiss}</div>
        </div>
      </div>
    </>
  );
}

function DecryptReview({ q, dismiss, evidence }: { q: Question; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const [text, setText] = useState("");
  return (
    <>
      <div className="row text-[14px]">
        <span className="w-12 shrink-0 text-[13px] text-ink-2">产品</span><span className="font-semibold">{L.product(q.refs.product_id)}</span>
        <span className="ml-6 w-12 shrink-0 text-[13px] text-ink-2">客户</span><span>{L.name(q.refs.customer_id)}</span>
      </div>
      {evidence}
      <div className="row !items-start">
        <div className="flex flex-1 flex-col gap-2">
          <Field value={text} onChange={setText} rows={3} placeholder="给这一位客户的机理说明（经业务员转交；配方永不对外）" />
          <div className="flex flex-wrap gap-2">
            <Act label="批准解密" run={() => api.decideDecrypt(q.id, true, text, me)} />
            <Act kind="plain" label="拒绝" run={() => api.decideDecrypt(q.id, false, "", me)} />
            {dismiss}
          </div>
        </div>
      </div>
    </>
  );
}


function GrantedCapabilities() {
  const { me } = useApp();
  const L = useLabels();
  const caps = useData(() => api.capabilities(me), [me]) ?? [];
  const status = { proposed: "待批准", active: "生效", suspended: "已挂起", revoked: "已撤销" };
  const forms: Record<string, string> = { ask: "追问", applicable: "适用情境", statement: "可说的话", decrypt: "解密", share: "查看原文" };
  const revoked = caps.filter((c) => c.status === "revoked");
  const card = (c: (typeof caps)[number]) => <div key={c.id} className="row !items-start">
      <div className="min-w-0 flex-1 text-[13px] leading-5">
        <p><span className="tag mr-2">{status[c.status]}</span>{forms[c.form] ?? c.form} · 给{typeof c.audience === "number" ? ["客户", "业务员", "产品经理", "研发"][c.audience] : L.name(c.audience)}</p>
        <p>{c.payload.product_id && L.product(c.payload.product_id)} {c.payload.phenomenon && L.phen(c.payload.phenomenon)} {c.payload.slot && L.slot(c.payload.slot)}{c.payload.text}{c.payload.ku_id}</p>
        {c.payload.conditions && <p>{Object.entries(c.payload.conditions).map(([k, v]) => `${L.slot(k)}：${v.join("、")}`).join("；")}</p>}
        {c.payload.temperature_c && <p>适用温度：{c.payload.temperature_c.join("—")}℃</p>}
        {c.payload.limits && <p>限制原文：{c.payload.limits}</p>}
        <p className="text-ink-3">依据：{c.based_on.join("、")}</p>
      </div>
      {c.status !== "revoked" && <Act kind="quiet" label="撤销" run={() => api.revokeCapability(c.id, me)} />}
    </div>;
  return <Group title="我授予的能力">
    {caps.filter((c) => c.status !== "revoked").map(card)}
    {revoked.length > 0 && <details className="border-t border-line">
      <summary className="cursor-pointer px-4 py-3 text-[13px] text-ink-2">查看已撤销记录（{revoked.length} 项）</summary>
      {revoked.map(card)}
    </details>}
    {!caps.length && <div className="row text-[13px] text-ink-2">还没有授予的能力</div>}
  </Group>;
}

type ClaimReview = Awaited<ReturnType<typeof api.reviewClaims>>;
type ReviewFragment = ClaimReview["fragments"][string][number];

function EvidenceSummary({ refs }: { refs: string[] }) {
  if (!refs.length) return <p className="mt-1.5 text-[12px] text-ink-3">依据：研发直接判断</p>;
  return <details className="mt-1.5 text-[12px] text-ink-2">
    <summary className="cursor-pointer">关联依据：{new Set(refs.map((r) => r.split("#")[0])).size} 份资料 · {refs.length} 处定位（点击查看引用编号）</summary>
    <div className="mt-1.5 space-y-1 rounded-lg bg-slate-50 p-2.5 font-mono text-[11.5px]">
      {refs.map((r, i) => <p key={i} className="break-all">{r}</p>)}
    </div>
  </details>;
}

function FragmentText({ text }: { text: string }) {
  const rows = text.split("\n").filter((r) => r.trim()).map((r) => r.split("\t"));
  return rows.length > 1 && rows[0].length > 1 && rows.every((r) => r.length === rows[0].length)
    ? <div className="mt-2 overflow-x-auto rounded-lg border border-line"><table className="w-full border-collapse text-left">
      <tbody>{rows.map((row, i) => <tr key={i} className={i === 0 ? "bg-slate-100 font-medium" : "bg-white"}>
        {row.map((cell, j) => <td key={j} className="whitespace-pre-wrap border border-line px-3 py-2 align-top">{cell}</td>)}
      </tr>)}</tbody></table></div>
    : <pre className="mt-2 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 font-sans leading-6">{text}</pre>;
}

function GroupedFragments({ fragments }: { fragments: ReviewFragment[] }) {
  const groups = new Map<string, ReviewFragment[]>();
  for (const f of fragments) {
    const key = `${f.doc_id}#${f.span.split("/")[0]}`;
    groups.set(key, [...(groups.get(key) ?? []), f]);
  }
  return <section className="mt-4 space-y-3"><h4 className="font-semibold">原文依据 · 按文档与对象合并展示</h4>
    {[...groups].map(([key, items]) => {
      const root = items[0].span.split("/")[0];
      const ordered = [...items].sort((a, b) => Number(b.span === root) - Number(a.span === root) || b.text.length - a.text.length);
      const unique: ReviewFragment[] = [];
      for (const f of ordered) if (!unique.some((shown) => shown.text.includes(f.text))) unique.push(f);
      return <div key={key} className="rounded-xl border border-line bg-white p-4 text-[13px] leading-5">
        <h5 className="font-semibold">{items[0].doc_id} · {root}</h5>
        {unique.map((f, i) => <FragmentText key={i} text={f.text} />)}
        {items.length > unique.length && <p className="mt-2 text-[12px] text-ink-2">已合并同对象内{items.length - unique.length}处重复／已包含的细部定位。</p>}
        <details className="mt-3 text-[12px] text-ink-2"><summary className="cursor-pointer">查看机器定位与证据指纹（共{items.length}条）</summary>
          {items.map((f, i) => <p key={i} className="mt-2 break-all rounded bg-slate-50 p-2 font-mono">{f.doc_id}#{f.span}@{f.fingerprint}</p>)}
        </details>
      </div>;
    })}
  </section>;
}

// 只投影展示数据；确认与复核始终提交原始review.reviewed_evidence。
function EvidenceReviewPanel({ review, compactSingle = false }: { review: ClaimReview; compactSingle?: boolean }) {
  const { me } = useApp();
  const L = useLabels();
  const fragments = review.claims.flatMap((c) => review.fragments[c.id]);
  const docs = [...new Set(fragments.map((f) => f.doc_id))];
  const [chosenDoc, setChosenDoc] = useState<string | null>(null);
  const doc = chosenDoc ?? docs[0];
  const current = fragments.filter((f) => f.doc_id === doc);
  const counts = new Map<string, number>();
  for (const f of current) { const root = f.span.split("/")[0]; counts.set(root, (counts.get(root) ?? 0) + 1); }
  const preferredSpans = [...counts.keys()].sort((a, b) =>
    Number(/^(table|chart|slide)/.test(b)) - Number(/^(table|chart|slide)/.test(a)) || counts.get(b)! - counts.get(a)!);
  const hideBody = compactSingle && review.claims.length === 1;
  const items = review.claims.map((c) => {
    const changed = c.evidence.join(";") !== review.reviewed_evidence[c.id].join(";");
    const pending = review.pending_evidence[c.id];
    if (hideBody && !changed && !pending) return null;
    return <div key={c.id} className="space-y-2">
      {!hideBody && <>
        <div>
          <h4 className="font-semibold">{c.title}</h4>
          <p className="mt-0.5 text-[12px] text-ink-2">归属 {L.name(c.owner)} · 请对照完整条件审阅</p>
        </div>
        <blockquote className="whitespace-pre-wrap rounded-r-lg border-l-4 border-accent bg-accent/5 px-3 py-2 leading-6">{c.text}</blockquote>
      </>}
      {changed && <p role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 font-medium text-amber-900">
        来源与原确认／编译时不同，请核对当前原文与候选判断后再签字。
      </p>}
      {pending && <p className="rounded-lg bg-slate-50 px-3 py-2 text-ink-2">
        补充依据：待挂接 {pending.capability_id}；原贡献人 {L.name(pending.contributor)}
      </p>}
    </div>;
  }).filter(Boolean);
  const conclusions = items.length ? <div className="space-y-3">{items}</div> : undefined;
  return <div className="row !block text-[13px] leading-5">
    {docs.length > 1 && <div className="mb-2 flex flex-wrap gap-2" role="group" aria-label="审阅来源">{docs.map((id) => <button key={id} type="button"
      className={`btn ${doc === id ? "btn-plain" : "btn-quiet"}`} aria-pressed={doc === id} onClick={() => setChosenDoc(id)}>{id}</button>)}</div>}
    {doc ? <SourceTrial key={`${me}:${doc}`} docId={doc} autoLoad preferredSpans={preferredSpans}
      rawEvidence={<GroupedFragments fragments={current} />}>{conclusions}</SourceTrial>
      : <>{conclusions}<GroupedFragments fragments={current} /></>}
  </div>;
}

function QiEvidenceReview({ q, dismiss, evidence }: { q: Question; dismiss: React.ReactNode; evidence: React.ReactNode }) {
  const { me } = useApp();
  const [review, setReview] = useState<Awaited<ReturnType<typeof api.reviewClaims>> | null>(null);
  return <>{evidence}<div className="row">
    <Act label="读取本次复核原文" run={() => api.reviewClaims([q.refs.ku_id], me).then(setReview)} />
  </div>{review && <EvidenceReviewPanel key={JSON.stringify(review.reviewed_evidence)} review={review} />}<div className="row gap-2">
    <Act label="复核后保留" disabled={!review}
      run={() => api.resolve(q.id, "sign", me, "", review!.reviewed_evidence)} />
    <Act kind="plain" label="撤回结论" run={() => api.withdrawClaim(q.refs.ku_id, me)} />{dismiss}
  </div></>;
}

function CandidateClaims({ reqId, empty = null }: { reqId: string | null; empty?: React.ReactNode }) {
  const { me } = useApp();
  const L = useLabels();
  const claims = useData(() => api.claims(reqId, me), [reqId, me]) ?? [];
  const [selected, setSelected] = useState<string[]>([]);
  const [review, setReview] = useState<Awaited<ReturnType<typeof api.reviewClaims>> | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [text, setText] = useState("");
  if (!claims.length) return <>{empty}</>;
  return <Group title={reqId ? "本单候选结论 · 待研发确认" : "本人资料候选 · 待研发确认"}
    foot="归属人是待确认负责人；点击签字才记录专业确认。用途授予与适用范围批准另行办理。">
    {claims.map((c) => <div key={c.id} className="row flex-wrap !items-start text-[13px] leading-5"><label className="flex min-w-0 flex-1 basis-64 items-start gap-2">
      <input type="checkbox" checked={selected.includes(c.id)} onChange={(e) => {
        setReview(null);
        setSelected(e.target.checked ? [...selected, c.id] : selected.filter((id) => id !== c.id));
      }} />
      <span className="min-w-0"><strong>{c.title}</strong><br /><span className="text-ink-3">待确认 · 归属 {L.name(c.owner)}</span>
        <span className="mt-1.5 block whitespace-pre-wrap leading-6">{c.text}</span></span>
    </label>{c.owner === me && <div className="flex shrink-0 gap-2">
      <button type="button" className="btn btn-plain" onClick={() => {
        setReview(null); setSelected([]); setEditing(c.id); setText(c.text);
      }}>修订正文</button>
      <Act kind="quiet" label="撤回候选" run={() => api.withdrawClaim(c.id, me).then(() => {
        setSelected([]); setReview(null); setEditing(null);
      })} />
    </div>}<div className="basis-full pl-6"><EvidenceSummary refs={c.evidence} /></div></div>)}
    {editing && <div className="row !block">
      <Field value={text} onChange={setText} rows={5} label="修订后的候选正文" />
      <p className="my-2 text-[12px] text-ink-2">保存后原稿撤回，新稿仍待确认。原依据保持不变，请重新审阅；原稿的用途能力按原有撤回规则处理。</p>
      <div className="flex gap-2">
        <Act label="保存为新的待审候选" disabled={!text.trim()} run={() => api.reviseClaim(editing, text, me).then(() => {
          setEditing(null); setText(""); setSelected([]); setReview(null);
        })} />
        <button type="button" className="btn btn-plain" onClick={() => setEditing(null)}>放弃修订</button>
      </div>
    </div>}
    <div className="row"><Act label="读取所选结论的审阅依据" disabled={!selected.length || editing !== null}
      run={() => api.reviewClaims(selected, me).then(setReview)} /></div>
    {review && <EvidenceReviewPanel key={JSON.stringify(review.reviewed_evidence)} review={review} compactSingle />}
    <div className="row"><Act label="签字确认已审阅结论" disabled={!selected.length || !review || editing !== null}
      run={() => api.confirmClaims(reqId, selected, me, review!.reviewed_evidence).then(() => {
        setSelected([]); setReview(null);
      })} /></div>
  </Group>;
}
