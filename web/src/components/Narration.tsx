// V11.4 旁白与个人时间账。旁白沿用讲解栏的五段（发生了什么 · 过去怎么做 · 解放了谁的什么 · ↑ 降本增效 · ★ 体验与影响力），
// 内容按这件事的实际路径（前情 case_story）与旧流程推算（old-flow）生成；时间构成色条读 time-bar。每个数带来源标签：
// 这次的经过标「模拟」，旧流程标「推算」，传化没给的参数标「假设」。真实试用只给「过去怎么做」，不讲这次省了什么。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData } from "../ctx";
import type { StoryLine } from "../types";
import { Group } from "./ui";

const GAIN = "#248a3d";
const FAME = "#5856d6";
const CROSS = ["#e08a2b", "#c7a25a"];
const ROLE: Record<string, string> = { sales: "业务员", pm: "产品经理", rd: "研发" };
const OWN_GOAL: Record<string, string> = { sales: "销售额、回款率、新客户数", pm: "产品线利润、新品上市数量", rd: "新品转化率、专利数、配方稳定性" };
const SEGMENT: Record<string, string> = { "sales.pm": "做产品经理的事", "pm.sales": "被业务员交叉占用", "pm.rd": "被研发交叉占用", "rd.pm": "做产品经理的事" };
const ANSWER = new Set(["turn", "recommend", "escalate", "sales_assigned"]);   // 客户收到的第一个回应：化言或业务员开口、推荐、转交

const Src = ({ s }: { s: string }) => (
  <span className={`tag !h-[18px] !px-1.5 !text-[11px] !font-normal ${s === "假设" ? "tag-warn" : s === "推算" ? "" : "tag-accent"}`}>{s}</span>
);
const span = (a: string, b: string) => {
  const m = (Date.parse(b) - Date.parse(a)) / 60000;
  return m < 1 ? "1 分钟内" : m < 60 ? `${Math.round(m)} 分钟` : m < 48 * 60 ? `${Math.round(m / 60)} 小时` : `${Math.round(m / 1440)} 天`;
};
const hours = (h: number) => (h < 1 ? `${Math.round(h * 60)} 分钟` : h < 48 ? `${+h.toFixed(1)} 小时` : `${+(h / 24).toFixed(1)} 天`);
const job = (station: string) => (station === "补问一轮" ? "回头补问" : station.replace(/^(业务员|产品经理|研发)/, ""));

export function Narration({ id }: { id: string }) {
  const { me, meta, notes } = useApp();
  const est = useData(() => api.oldFlow(id, me), [id, me]);
  const data = useData(() => api.caseStory(id, me), [id, me]);
  if (!notes || !est || !data?.story.length) return null;
  const trial = !!meta.trial && !meta.play;   // 真实试用；游戏模式照常讲
  const { old } = est;
  const story = data.story;
  const first = story[0].ts, last = story[story.length - 1].ts;
  const assumed = est.assumed.length > 0;
  const freed = old.stations.filter((x) => x.now_times !== undefined && x.now_times < x.times);
  const saved = (x: (typeof freed)[number]) => Math.round(x.minutes - (x.now_minutes ?? 0));
  const savedMin = freed.reduce((n, x) => n + saved(x), 0);
  const bypassed = old.roles.filter((r) => !est.now.roles.includes(r));
  const reworks = old.stations.find((x) => x.station === "试样返工一轮")?.now_times ?? 0;   // 这次实际录了几次未通过的试样
  const reply = story.find((x: StoryLine) => ANSWER.has(x.kind) && !(x.kind === "turn" && x.role === "customer"));
  return (
    <Group title="旁白" foot={assumed ? `旧流程按参数推算；其中 ${est.assumed.length} 项参数传化还没给，用的是假设值。` : "旧流程按传化给的参数推算。"}>
      <div className="flex flex-col gap-3 px-4 py-3.5">
        {!trial && (
          <Part label="发生了什么" src={<Src s="模拟" />}>
            {est.now.roles.length ? `这次经过${est.now.roles.join("、")}，人亲手做了 ${est.now.human_steps} 步${reworks ? `，试样返工 ${reworks} 轮` : ""}` : "这次没有经过任何岗位的人"}
            ，前后 {span(first, last)}{reply && reply.ts > first ? `；客户说完 ${span(first, reply.ts)}就有了回应` : ""}。
          </Part>
        )}
        <Part label="过去怎么做" src={<><Src s="推算" />{assumed && <Src s="假设" />}</>} muted>
          要经过{old.roles.join(" → ")}：{old.stations.map((x) => x.station).join("、")}。约 {Math.round(old.handoffs)} 次交接
          {old.backs > 0 && `，补问约 ${+old.backs.toFixed(2)} 轮`}{old.reworks > 0 && `，试样返工约 ${+old.reworks.toFixed(2)} 轮`}
          {`；人工约 ${+old.work_hours.toFixed(1)} 工时，前后等约 ${hours(old.wait_hours)}。`}
          {old.lost?.length ? `转述时会丢掉：${old.lost.join("、")}。` : ""}
        </Part>
        {!trial && <>
          {(freed.length > 0 || bypassed.length > 0) && (
            <Part label="解放了谁的什么" src={<Src s="推算" />} strong>
              {bypassed.length > 0 && `${bypassed.join("、")}这次没被打断。`}
              {freed.map((x) => `${ROLE[x.role]}不用${job(x.station)}（约 ${saved(x)} 分钟${x.times < 1 ? "，按旧流程的比例" : ""}）`).join("；")}{freed.length > 0 && "。"}
            </Part>
          )}
          {savedMin > 0 && (
            <Value mark="↑" label="降本增效" color={GAIN}>
              这件事少了约 {savedMin} 分钟被交叉占用的工作；各岗位的本职判断照常保留。
            </Value>
          )}
          <Value mark="★" label="体验与影响力" color={FAME}>
            过去客户前后要等约 {hours(old.wait_hours)}，这次前后 {span(first, last)}{data.waiting.length ? "，还在进行中" : ""}。
          </Value>
        </>}
      </div>
    </Group>
  );
}

function Part({ label, src, muted, strong, children }: { label: string; src?: React.ReactNode; muted?: boolean; strong?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <p className="eyebrow flex items-center gap-1.5">{label}{src}</p>
      <p className={`mt-0.5 text-[13px] leading-[21px] ${muted ? "text-ink-2" : ""} ${strong ? "font-semibold" : ""}`}>{children}</p>
    </div>
  );
}

function Value({ mark, label, color, children }: { mark: string; label: string; color: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="eyebrow" style={{ color }}>{mark} {label}</p>
      <p className="mt-0.5 text-[13px] leading-[21px]">{children}</p>
    </div>
  );
}

// 个人时间构成：现状（传化研发估计，标假设）→ 这一局（推算）。点开看每一段的算式
export function TimeBar() {
  const { me, meta, notes } = useApp();
  const trial = !!meta.trial && !meta.play;   // 真实试用；游戏模式照常讲
  const role = me.split(":")[0];
  const bar = useData(() => (ROLE[role] ? api.timeBar(me) : Promise.resolve(null)), [me]);
  const [open, setOpen] = useState(false);
  if (!notes || !bar) return null;
  const strip = (own: number, segs: number[]) => (
    <div className="flex h-[18px] overflow-hidden rounded-[5px] bg-fill text-[10.5px] font-semibold leading-[18px] text-white">
      <div style={{ width: `${own}%`, background: GAIN }} className="truncate px-1.5">本职 {Math.round(own)}%</div>
      {segs.map((pct, i) => pct > 0 && (
        <div key={i} style={{ width: `${pct}%`, background: CROSS[i] }} className="truncate px-1">{Math.round(pct)}%</div>
      ))}
    </div>
  );
  return (
    <Group title="你的时间构成" aside={bar.cases > 0 && <button className="text-[12px] text-accent" onClick={() => setOpen(!open)}>{open ? "收起算式" : "看算式"}</button>}
           foot={`现状比例从研发提供的岗位对比图上量出，待确认。${trial ? "到现在" : "这一局"}按 ${bar.cases} 件事推算：如果你被交叉占用的工作都像这几件事。`}>
      <div className="flex flex-col gap-2.5 px-4 py-3.5 text-[12.5px]">
        <div className="flex flex-col gap-1">
          <p className="flex items-center gap-1.5 text-ink-2">现状<Src s={bar.split_source} /></p>
          {strip(bar.own_before, bar.segments.map((x) => x.before))}
        </div>
        <div className="flex flex-col gap-1">
          <p className="flex items-center gap-1.5 text-ink-2">{trial ? "到现在" : "这一局"}<Src s={bar.source} /></p>
          {strip(bar.own_after, bar.segments.map((x) => x.after))}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] text-ink-2">
          {bar.segments.map((x, i) => (
            <span key={x.whose} className="flex items-center gap-1">
              <i className="inline-block h-2 w-2 rounded-[2px]" style={{ background: CROSS[i] }} />{SEGMENT[`${role}.${x.whose}`]}
              {x.worse && <span className="text-attn-ink">（这批事里比旧流程预期还多，未缩短）</span>}
            </span>
          ))}
        </div>
        <p className="text-ink-2">本职对应：{OWN_GOAL[role]}</p>
        {open && bar.segments.map((x) => (
          <div key={x.whose} className="border-t border-sep pt-2">
            <p className="font-semibold">{SEGMENT[`${role}.${x.whose}`]}：省下约 {Math.round(x.saved_minutes)} / {Math.round(x.old_minutes)} 分钟</p>
            {x.steps.map((s) => (
              <p key={s.station} className="num text-ink-2">{s.station}：旧流程约 {s.times} 次 × {s.minutes_each} 分钟，这次 {s.now_times} 次</p>
            ))}
          </div>
        ))}
      </div>
    </Group>
  );
}
