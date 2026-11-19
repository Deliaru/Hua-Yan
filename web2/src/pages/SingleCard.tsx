// 单卡对照（评测页内，REPLAN 3.6、WP-E2）：同一张需求卡、同一个模拟客户，左边一次性翻译，右边化言；
// 按轮播放，右边同步显示觉的逐轮追问概率；底部是研发会不会退回。多卡统计在评测页「失真对照」。
// 数据取自 report?name=single_card（门面按查看者裁剪：业务员只看到三组统计，评测页固定按研发视角取数）。
import { useState } from "react";
import { api } from "../api";
import { isModel, pct, useData, useLabels } from "../ctx";
import { Group } from "../components/ui";

interface Line { text: string; quote: string | null; owner?: string }
interface Side { chem_lang: Line[]; missing: string[]; wrong: string[]; returned: boolean; return_reason?: string }
interface Round {
  turn: { speaker: "customer" | "sales"; text: string };
  p_need: Record<string, number | null>; scored_by: Record<string, string>; threshold: number; asked: string | null;
  ask_text: string | null;
}
interface BackAsk { slot: string; p_need: number; scored_by: string; threshold: number; ask_text: string; answer: string; changed: boolean }
type Group3 = Record<string, number | null>;
interface Selection { rule: string; n_cards: number; n_same_phenomenon: number; n_eligible: number }
type Stats = Record<string, Group3 | number | Selection>;
interface Card {
  card_id: string; simulated: boolean; phenomenon: string; truth: Record<string, string>;
  one_shot: Side & { turns: { speaker: string; text: string }[] };
  huayan: Side & { rounds: Round[]; back_asks: BackAsk[] };
  stats: Stats;
}
// L1 身份只拿到模拟标注与三组统计
type Report = Card | { simulated: boolean; stats: Stats };

// 评测页是展示页，固定按研发视角取数（人已同意）；裁剪仍由门面按 viewer 执行
export function SingleCard({ viewer }: { viewer: string }) {
  const r = useData(() => api.singleCard<Report>(viewer), [viewer]);
  if (!r || !("huayan" in r)) return null;
  return <Player card={r} />;
}

function Player({ card }: { card: Card }) {
  const L = useLabels();
  const rounds = card.huayan.rounds;
  const [n, setN] = useState(1);
  const done = n >= rounds.length;
  return (
    <section className="flex flex-col gap-4">
      <div className="group-title flex items-baseline justify-between">
        <span>单卡对照 · {L.phen(card.phenomenon)} <span className="tag ml-1.5">模拟数据</span></span>
        <span className="flex items-center gap-1.5 font-normal">
          <button type="button" className="btn btn-quiet" disabled={n <= 1} onClick={() => setN(n - 1)}>上一轮</button>
          <span className="num text-[12px] text-ink-2">第 {n} / {rounds.length} 轮</span>
          <button type="button" className="btn btn-plain" disabled={done} onClick={() => setN(n + 1)}>下一轮</button>
          <button type="button" className="btn btn-quiet" onClick={() => setN(rounds.length)}>到结尾</button>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Group title="一次性翻译：客户开场白 → 化学语言">
          {card.one_shot.turns.map((t, i) => <div key={i} className="row text-[13px] leading-5">客户：{t.text}</div>)}
          <Outcome side={card.one_shot} />
        </Group>
        <Group title="化言：觉提示追问 → L2 → L3 → 回问">
          {rounds.slice(0, n).map((r, i) => (
            <div key={i} className="row !items-start !py-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] leading-5">{r.turn.speaker === "customer" ? "客户" : "业务员"}：{r.turn.text}</p>
                <p className="mt-1 flex flex-wrap items-center gap-1">
                  {Object.entries(r.p_need).filter(([, p]) => p != null).map(([slot, p]) => (
                    <span key={slot} className={`tag ${r.asked === slot ? "tag-attn" : ""}`}>
                      {L.slot(slot)} {isModel(r.scored_by[slot]) ? pct(p!) : p! >= r.threshold ? "规则 · 到点" : "规则 · 未到点"}
                    </span>
                  ))}
                  {Object.values(r.p_need).every((p) => p == null) && <span className="text-[12px] text-ink-3">觉：此刻不需要追问</span>}
                </p>
                {r.ask_text && <p className="mt-1 text-[13px] leading-5">业务员：{r.ask_text}</p>}
              </div>
            </div>
          ))}
          {done && card.huayan.back_asks.map((b, i) => (
            <div key={`b${i}`} className="row !items-start text-[13px] leading-5">
              <span className="tag tag-attn shrink-0">回问 · {L.slot(b.slot)}</span>
              <div className="min-w-0 flex-1">
                <p>业务员：{b.ask_text}</p>
                <p>客户：{b.answer}{b.changed && <span className="text-ink-2">（改变了转译）</span>}</p>
              </div>
            </div>
          ))}
          {done && <Outcome side={card.huayan} />}
        </Group>
      </div>
    </section>
  );
}

// 转译结果：规则骨架把条件与未转译的话也写成条目（「条件：…」「未转译：…」），这里分开显示；要点写成「『场景词』→ 表述」
function Outcome({ side }: { side: Side }) {
  const L = useLabels();
  const conds = side.chem_lang.filter((c) => c.text.startsWith("条件："));
  const gaps = side.chem_lang.filter((c) => c.text.startsWith("未转译："));
  const points = side.chem_lang.filter((c) => !conds.includes(c) && !gaps.includes(c));
  return (
    <>
      {points.map((c, i) => {
        const m = c.text.match(/^『([^』]+)』\s*→\s*([\s\S]+)$/);
        return (
          <div key={i} className="row !items-start text-[13px] leading-5">
            <div>
              {m ? m[2] : c.text}
              <p className="mt-0.5 text-[12px] text-ink-3">
                {m && <>针对「{m[1]}」</>}{c.quote ? ` ← 原话「${c.quote}」` : " · 无原话依据"}
              </p>
            </div>
          </div>
        );
      })}
      {!side.chem_lang.length && <div className="row text-[13px] text-ink-3">没有产出化学要点</div>}
      {!!conds.length && (
        <div className="row flex-wrap !gap-1.5 text-[13px]">
          <span className="text-ink-2">已知条件</span>
          {conds.map((c, i) => <span key={i} className="tag" title={c.quote ? `原话「${c.quote}」` : undefined}>{c.text.slice(3)}</span>)}
        </div>
      )}
      {gaps.map((c, i) => <div key={i} className="row text-[12.5px] text-ink-2">没能转译：「{c.text.slice(4)}」</div>)}
      <div className="row text-[13px]">
        {side.returned ? <span className="text-danger">研发退回{side.return_reason ? `：${side.return_reason.replace(/^缺：/, "缺")}` : ""}</span>
          : <span>研发不退回</span>}
        {!side.return_reason && (
          <span className="ml-auto text-ink-2">
            {!!side.missing.length && `缺 ${side.missing.map(L.slot).join("、")}`} {!!side.wrong.length && `错 ${side.wrong.map(L.slot).join("、")}`}
          </span>
        )}
      </div>
    </>
  );
}
