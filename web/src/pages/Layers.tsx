// 三层对照页（WP-E）：同一张需求单在 L1 / L2 / L3 三列并排，各列按该层身份从门面读取（裁剪在门面里完成）。
// 点一句客户原话，三列里引用它的条目一起高亮：看得出一句原话如何逐层变成化学语言。下方为贡献看板与失真对照关键数字。
import { useState } from "react";
import { api } from "../api";
import { REQ_STATUS, Side, pct, useData, useLabels } from "../ctx";
import type { ContributionStat, RecommendationCard, ReqItem, RequirementView, SessionView } from "../types";
import { EmptyState, Group, PageHead, SideHead } from "../components/ui";

const L2_VIEWER = "pm:agent";                    // L2 列按产品经理 Agent 的权限读取（契约 ① Q8）

type Focus = { focus: string | null; setFocus: (t: string | null) => void };

function Column({ level, who, children }: { level: number; who: string; children: React.ReactNode }) {
  const label = ["", "场景需求卡", "产品需求", "化学语言"][level];
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      <div className="flex items-baseline gap-2 px-1">
        <span className="tag tag-accent">L{level}</span>
        <span className="text-[15px] font-semibold">{label}</span>
        <span className="ml-auto text-[12px] text-ink-2">{who} 视图</span>
      </div>
      {children}
    </div>
  );
}

function Quote({ id, text, f }: { id: string; text: string; f: Focus }) {
  return (
    <button onClick={() => f.setFocus(f.focus === id ? null : id)}
            className={`block w-full rounded-[6px] px-1.5 py-0.5 text-left text-[12px] leading-[18px] ${
              f.focus === id ? "bg-[rgba(255,149,0,.18)] text-ink" : "text-ink-2 hover:bg-fill"}`}>
      「{text}」
    </button>
  );
}

// L1：每段会话的客户原话（可点）与绑定在原话上的槽位
function L1Session({ v, title, f }: { v: SessionView; title: string; f: Focus }) {
  const L = useLabels();
  return (
    <Group title={title}>
      {v.turns.filter((t) => t.speaker === "customer").map((t) => {
        const slots = v.slots.filter((s) => s.turn_id === t.id);
        return (
          <div key={t.id} className={`row !items-start !py-2.5 ${f.focus === t.id ? "bg-[rgba(255,149,0,.12)]" : ""}`}>
            <div className="min-w-0 flex-1">
              <Quote id={t.id} text={t.text} f={f} />
              {!!slots.length && (
                <p className="mt-1 flex flex-wrap gap-1 pl-1.5">
                  {slots.map((s) => <span key={s.slot} className="tag">{L.slot(s.slot)} {s.value ?? "不清楚"}</span>)}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </Group>
  );
}

function Card({ title, card }: { title: string; card: RecommendationCard }) {
  const L = useLabels();
  return (
    <Group title={title} aside={`披露：${L.version(card.version)}`}>
      <div className="row text-[14px] font-semibold">{L.product(card.product_id)}</div>
      {card.sections.filter((s) => !s.ku_id.startsWith("ku:trial:")).map((s) => (   // 试样记录原文是结构化数据，不在卡片里展开
        <div key={s.ku_id} className="row !items-start !py-2.5">
          <div className="min-w-0">
            <p className="text-[12px] text-ink-2">L{s.level} · {s.title.replace(`${L.product(card.product_id)} · `, "")}</p>
            <p className="mt-0.5 line-clamp-4 text-[13px] leading-5">{s.text}</p>
          </div>
        </div>
      ))}
    </Group>
  );
}

// L2 / L3 条目：文本、依据（归属人 · 标题；无权时只显示归属）、客户原话；引用了焦点原话的条目高亮
function Items({ view, field, f, showText }: { view: RequirementView; field: "product_lang" | "chem_lang"; f: Focus; showText: boolean }) {
  const L = useLabels();
  const req = view.requirement;
  const cited = Object.fromEntries(view.cited.map((c) => [c.ku_id, c]));
  const [drafted, confirmed] = field === "product_lang"
    ? [req.drafted_by, req.rd_accepted_by] : [req.chem_drafted_by, req.rd_confirmed_by];
  return (
    <Group foot={`起草 ${L.name(drafted)} · ${field === "product_lang" ? "接单" : "确认"} ${L.name(confirmed)}`}>
      {req[field].map((item: ReqItem, i) => (
        <div key={i} className={`row !items-start !py-2.5 ${f.focus && item.quote_refs.includes(f.focus) ? "bg-[rgba(255,149,0,.12)]" : ""}`}>
          <span className="num w-4 shrink-0 pt-px text-[12px] text-ink-3">{i + 1}</span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] leading-5">{item.text}</p>
            {item.ku_refs.map((ref) => {
              const c = cited[ref];
              return (
                <p key={ref} className="mt-1 text-[12px] leading-[17px] text-ink-2" title={c.text ?? "无权查看原文，只显示归属"}>
                  <span className="text-ink">{L.name(c.owner)}</span>{" · "}
                  {c.text == null ? <span className="text-ink-3">L{c.level} 转化知识 · 原文不可见</span> : L.scrub(c.title)}
                  <span className="text-ink-3">　被引用 {c.n_cited} 次</span>
                  {showText && c.text && <span className="mt-0.5 block line-clamp-2 text-ink-3">{c.text}</span>}
                </p>
              );
            })}
            {item.quote_refs.map((ref) => <Quote key={ref} id={ref} text={view.quotes[ref]} f={f} />)}
          </div>
        </div>
      ))}
    </Group>
  );
}

function Contributions({ stats }: { stats: ContributionStat[] }) {
  const L = useLabels();
  const owners = [...new Set(stats.map((s) => s.owner))].map((owner) => {
    const mine = stats.filter((s) => s.owner === owner);
    return { owner, n: mine.length, cited: mine.reduce((a, s) => a + s.n_cited, 0), points: mine.reduce((a, s) => a + s.points, 0),
             used: [...new Set(mine.flatMap((s) => s.used_by))] };
  }).sort((a, b) => b.points - a.points);
  return (
    <Group title="贡献看板" foot="知识被引用即给归属人记分；沉淀、试样通过、发布另计（规则见 config/app.yaml 的 points）。">
      {owners.map((o) => (
        <div key={o.owner} className="row">
          <span className="w-28 shrink-0 text-[14px] font-semibold">{L.name(o.owner)}</span>
          <span className="num w-24 shrink-0 text-[13px] text-ink-2">{o.n} 条知识</span>
          <span className="num w-24 shrink-0 text-[13px] text-ink-2">被引用 {o.cited} 次</span>
          <span className="min-w-0 flex-1 truncate text-[12px] text-ink-3">用于 {o.used.length} 张需求单</span>
          <span className="num text-[15px] font-semibold">{o.points}</span><span className="text-[12px] text-ink-2">分</span>
        </div>
      ))}
    </Group>
  );
}

interface Distortion { n_cards: number; metrics: Record<string, Record<string, number | null>> }

function DistortionLine() {
  const d = useData(() => api.report<Distortion>("distortion"), []);
  if (!d) return null;
  const g = Object.entries(d.metrics);
  return (
    <Group title="失真对照（关键数字）" foot={<>{d.n_cards} 张模拟需求卡；G1 的转述噪声为假设参数。<a href="#eval" className="link">详见评测页</a></>}>
      {g.map(([name, m]) => (
        <div key={name} className="row">
          <span className="min-w-0 flex-1 text-[14px]">{name}</span>
          <span className="num w-40 text-right text-[13px] text-ink-2">关键信息完整率 <b className="text-ink">{pct(m.completeness ?? 0)}</b></span>
          <span className="num w-40 text-right text-[13px] text-ink-2">研发需退回 <b className="text-ink">{pct(m.returned ?? 0)}</b></span>
        </div>
      ))}
    </Group>
  );
}

function Compare({ id }: { id: string }) {
  const pm = L2_VIEWER;
  const L = useLabels();
  const [focus, setFocus] = useState<string | null>(null);
  const f = { focus, setFocus };
  const l2 = useData(() => api.requirement(id, pm), [id, pm]);
  const rd = l2?.requirement.assigned_rd ?? null;
  const l3 = useData(() => (rd ? api.requirement(id, rd) : Promise.resolve(null)), [id, rd]);
  const summaries = useData(() => api.sessions(), []);
  const req = l2?.requirement;
  const sales = (sid: string) => summaries?.find((s) => s.id === sid)?.sales_id ?? "";
  const own = useData(() => (req && summaries ? Promise.all(req.session_ids.map((sid) => api.session(sid, sales(sid))))
    : Promise.resolve(null)), [req?.id, summaries?.length]);
  // 发布后：L1 命中新品的会话（业务员版卡片）与同一会话的研发内部版卡片
  const hit = useData(async () => {
    if (!req?.product_id || !summaries || !rd) return null;
    for (const s of summaries.filter((x) => x.status === "recommended").reverse()) {
      const d = await api.session(s.id, s.sales_id);
      if (d.card?.product_id === req.product_id) return { l1: d.card, l3: (await api.session(s.id, rd)).card! };
    }
    return null;
  }, [req?.id, req?.product_id, summaries?.length, rd]);
  const stats = useData(() => api.contributions(pm), [pm]);
  if (!l2 || !l3 || !req || !rd) return null;
  return (
    <>
      <PageHead title={`三层对照 · ${L.phen(req.phenomenon)}`}
                subtitle={`${REQ_STATUS[req.status]}${req.product_id ? ` · 关联产品 ${L.product(req.product_id)}` : ""} · 演示对照：三列各按该层身份读取，与当前身份无关 · 点一句客户原话，三列中引用它的条目一起高亮`} />
      <div className="flex items-start gap-5">
        <Column level={1} who={[...new Set(req.session_ids.map(sales))].map(L.name).join("、")}>
          {own?.map((v, i) => <L1Session key={v.session_id} v={v} f={f}
                                         title={`客户 ${i + 1} · ${L.phen(req.phenomenon)}`} />)}
          {hit && <Card title="发布后 L1 拿到的产品卡" card={hit.l1} />}
        </Column>
        <Column level={2} who={L.name(pm)}>
          <Items view={l2} field="product_lang" f={f} showText={false} />
          <p className="px-1 text-[12px] leading-[18px] text-ink-2">所引 L3 知识只显示归属人，原文不可见；化学假设与封存项不对产品经理 Agent 开放。</p>
        </Column>
        <Column level={3} who={L.name(rd)}>
          <Items view={l3} field="chem_lang" f={f} showText />
          {!!l3.requirement.hypotheses.length && (
            <Group title="研发方向假设">
              {l3.requirement.hypotheses.map((h) => <div key={h} className="row text-[13px] leading-5">{h}</div>)}
            </Group>
          )}
          {hit && <Card title="同一产品 · 研发内部版" card={hit.l3} />}
        </Column>
      </div>
      {stats && <Contributions stats={stats} />}
      <DistortionLine />
    </>
  );
}

export function Layers() {
  const L = useLabels();
  const [chosen, choose] = useState<string | null>(null);
  const reqs = useData(() => api.requirements(L2_VIEWER), []);
  const list = (reqs ?? []).filter((r) => r.status === "rd_confirmed" || r.status === "released").reverse();
  const current = list.find((r) => r.id === chosen)?.id ?? list[0]?.id ?? null;
  return (
    <>
      <Side>
      <SideHead>研发已确认的需求单</SideHead>
      {list.length ? list.map((r) => (
        <button key={r.id} onClick={() => choose(r.id)} className={`side-row ${r.id === current ? "on" : ""}`}>
          <p className="text-[13px] font-semibold">{L.phen(r.phenomenon)}</p>
          <p className="text-[12px] text-ink-2">{REQ_STATUS[r.status]}</p>
        </button>
      )) : <p className="px-[18px] py-1 text-[13px] text-ink-3">暂无</p>}
      </Side>
      <div className="mx-auto flex max-w-[1280px] flex-col gap-7 px-8 pb-24 pt-7">
        {current ? <Compare key={current} id={current} />
          : <EmptyState title="还没有研发确认的需求单" text="需求单经研发确认转译（L3）后，可以在这里三层并排对照。" />}
      </div>
    </>
  );
}
