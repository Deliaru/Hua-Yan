// 单卡对照（评测页内，REPLAN 3.6、WP-E2）：同一张需求卡、同一个模拟客户，左边一次性翻译，右边化言；
// 按轮播放，右边同步显示觉的逐轮追问概率；底部是研发会不会退回，再接 60 张卡三组统计。
// 开发期读 B 交付的 web/src/fixtures/single_card.json（文件不存在时显示待交付），接口就位后换成 report?name=single_card。
import { useEffect, useState } from "react";
import { isModel, pct, useLabels } from "../ctx";
import { Group } from "../components/ui";

interface Line { text: string; quote: string | null; owner?: string }
interface Side { chem_lang: Line[]; missing: string[]; wrong: string[]; returned: boolean; return_reason?: string }
interface Round {
  turn: { speaker: "customer" | "sales"; text: string };
  p_need: Record<string, number | null>; scored_by: Record<string, string>; threshold: number; asked: string | null;
}
interface BackAsk { slot: string; p_need: number; scored_by: string; threshold: number; answer: string; changed: boolean }
interface Card {
  card_id: string; simulated: boolean; phenomenon: string; truth: Record<string, string>;
  one_shot: Side & { turns: { speaker: string; text: string }[] };
  huayan: Side & { rounds: Round[]; back_asks: BackAsk[] };
  stats: Record<string, Record<string, number | null> | number>;
}

const files = import.meta.glob("../fixtures/single_card.json", { import: "default" });

export function SingleCard() {
  const [card, setCard] = useState<Card | null | undefined>(undefined);
  useEffect(() => {
    const load = Object.values(files)[0];
    if (load) load().then((c) => setCard(c as Card));
    else setCard(null);
  }, []);
  if (card === undefined) return null;
  if (card === null) {
    return <Group title="单卡对照"><div className="row text-[13px] text-ink-2">单卡对照数据待交付（WP-E2 第 1 步）</div></Group>;
  }
  return <Player card={card} />;
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
                <p className="mt-1 flex flex-wrap gap-1">
                  {Object.entries(r.p_need).map(([slot, p]) => (
                    <span key={slot} className={`tag ${r.asked === slot ? "tag-attn" : ""}`}>
                      {L.slot(slot)} {p == null ? "—" : isModel(r.scored_by[slot]) ? pct(p) : p >= r.threshold ? "规则 · 到点" : "规则"}
                    </span>
                  ))}
                </p>
              </div>
            </div>
          ))}
          {done && card.huayan.back_asks.map((b, i) => (
            <div key={`b${i}`} className="row !items-start text-[13px] leading-5">
              <span className="tag tag-attn">回问 {L.slot(b.slot)}</span>
              <span className="flex-1">{b.answer}{b.changed && <span className="text-ink-2">（改变了转译）</span>}</span>
            </div>
          ))}
          {done && <Outcome side={card.huayan} />}
        </Group>
      </div>
      <Stats stats={card.stats} />
    </section>
  );
}

function Outcome({ side }: { side: Side }) {
  const L = useLabels();
  return (
    <>
      {side.chem_lang.map((c, i) => (
        <div key={i} className="row !items-start text-[13px] leading-5">
          <div>{c.text}{c.quote ? <p className="text-[12px] text-ink-3">原话「{c.quote}」</p> : <p className="text-[12px] text-ink-3">无原话依据</p>}</div>
        </div>
      ))}
      <div className="row text-[13px]">
        {side.returned ? <span className="text-danger">研发退回{side.return_reason ? `：${side.return_reason}` : ""}</span>
          : <span>研发不退回</span>}
        <span className="ml-auto text-ink-2">
          {!!side.missing.length && `缺 ${side.missing.map(L.slot).join("、")}`} {!!side.wrong.length && `错 ${side.wrong.map(L.slot).join("、")}`}
        </span>
      </div>
    </>
  );
}

function Stats({ stats }: { stats: Card["stats"] }) {
  const groups = Object.entries(stats).filter(([, v]) => typeof v === "object") as [string, Record<string, number | null>][];
  const keys = [...new Set(groups.flatMap(([, v]) => Object.keys(v)))];
  return (
    <Group title={`${stats.n_cards ?? 60} 张卡三组统计`} foot="取自失真对照报告，不另算。">
      <div className="overflow-x-auto px-4 py-2">
        <table className="w-full text-[13px]">
          <thead><tr><th />{keys.map((k) => <th key={k} className="py-1.5 text-right font-semibold text-ink-2">{k}</th>)}</tr></thead>
          <tbody>
            {groups.map(([g, v]) => (
              <tr key={g} className="border-t border-sep">
                <td className="py-1.5">{g}</td>
                {keys.map((k) => <td key={k} className="num py-1.5 text-right">{v[k] == null ? "—" : v[k]! <= 1 ? pct(v[k]!) : v[k]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Group>
  );
}
