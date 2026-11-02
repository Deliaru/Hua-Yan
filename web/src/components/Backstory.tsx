// V11.3 前情：一件事到你手上之前发生过什么（门面 case_story，按查看者层级裁剪）。
// 默认只显示客户原话和最近几步，点开看全部；觉提出、Agent 准备这类过程行淡色显示；末尾写现在在等谁。
import { useState } from "react";
import { api } from "../api";
import { useApp, useData, useLabels } from "../ctx";
import type { StoryLine } from "../types";
import { Group } from "./ui";

const ROLE: Record<string, string> = { customer: "客户", sales: "业务员", pm: "产品经理", rd: "研发", supervisor: "负责人" };
const SUBJECT: Record<string, string> = { jue: "觉", jev: "Jev", qi: "契", system: "系统" };
const PROCESS = new Set(["question_published", "question_prepared"]);   // 过程行：淡色
const RECENT = 4;

const when = (ts: string, first: string) => ts.slice(0, 10) === first.slice(0, 10) ? ts.slice(11, 16) : `${ts.slice(5, 10)} ${ts.slice(11, 16)}`;

export function Backstory({ id, title = "前情" }: { id: string; title?: string }) {
  const { me } = useApp();
  const L = useLabels();
  const data = useData(() => api.caseStory(id, me), [id, me]);
  const [open, setOpen] = useState(false);
  if (!data || !data.story.length) return null;
  const { story, waiting } = data;
  const first = story[0];
  // 收起时：第一句（通常是客户原话）+ 最近几步
  const shown = open || story.length <= RECENT + 1 ? story : [first, ...story.slice(-RECENT)];
  const hidden = story.length - shown.length;
  const agentName = (who: string) => (who === "pm:agent" ? "产品经理 Agent" : `${L.name(who)}的 Agent`);
  const label = (x: StoryLine) =>
    x.subject === "human" ? <><span className="tag shrink-0">{ROLE[x.role ?? ""] ?? "人"}</span><span className="shrink-0 font-semibold">{L.name(x.who)}</span></>
      : x.subject === "agent" ? <span className="tag tag-agent shrink-0">{agentName(x.who)}</span>
      : <span className="tag tag-accent shrink-0">{SUBJECT[x.subject]}</span>;
  return (
    <Group title={title} aside={story.length > RECENT + 1 && (
      <button className="text-[12px] text-accent" onClick={() => setOpen(!open)}>{open ? "收起" : `展开全部 ${story.length} 步`}</button>
    )}>
      {shown.map((x, i) => (
        <div key={`${x.ts}:${i}`}>
          {!open && hidden > 0 && i === 1 && <div className="row !min-h-0 !py-1 text-[12px] text-ink-3">…… 中间 {hidden} 步</div>}
          <div className={`row !min-h-0 !items-baseline !py-2 text-[13px] leading-5 ${PROCESS.has(x.kind) ? "text-ink-3" : ""}`}>
            <span className="num w-[78px] shrink-0 text-[11.5px] text-ink-3">{when(x.ts, first.ts)}</span>
            <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              {label(x)}<span className="min-w-0">{L.scrub(x.text)}</span>
            </span>
          </div>
        </div>
      ))}
      {waiting.map((w) => {
        const mine = w.signer_id === me || (!w.signer_id && w.owner_id === me);
        const text = !w.prepared && w.owner_id
          ? `${agentName(w.owner_id)}正在准备「${w.decision}」`
          : mine ? `轮到你：「${w.decision}」` : `等${L.name(w.signer_id ?? w.owner_id)}处理「${w.decision}」`;
        return (
          <div key={w.question_id} className={`row !min-h-0 !py-2 text-[13px] ${mine && w.prepared ? "bg-attn-bg font-semibold text-attn-ink" : "text-ink-2"}`}>
            <span className="w-[78px] shrink-0 text-[11.5px]">现在</span><span>{text}</span>
          </div>
        );
      })}
    </Group>
  );
}
