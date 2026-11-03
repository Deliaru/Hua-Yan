// V11.9 游戏结算：这一局各岗位的业务和关卡各步送来的事走了哪条路，三个岗位的时间构成怎么变，以及这一局的账本。
// 口径同 CEO 面（这一局的事放大到每月询问量）；游戏世界里的经过标「模拟」，旧流程标「推算」，参数标「假设」。
// 服务端只给各件的路径与推算，不给原话和经手人，所以谁都能看。
import { useState } from "react";
import { api } from "../api";
import { useData } from "../ctx";
import { Group, PageHead } from "../components/ui";
import { type Basis, Headline, hours, Src, TimeBars } from "./Ceo";

export function Settle() {
  const data = useData(() => api.playSettle(), []);
  const [set, setSet] = useState<Basis>("given");
  if (!data) return <p className="p-10 text-ink-2">正在结算……</p>;
  const byId = Object.fromEntries(data.cases.map((c) => [c.session_id, c]));
  const passed = data.levels.filter((x) => x.passed).length;
  const wait = (a: string, b: string | null) => (b ? hours((Date.parse(b) - Date.parse(a)) / 3.6e6) : "还没有");
  return (
    <div className="mx-auto flex max-w-[1180px] flex-col gap-6 px-8 pb-24 pt-7">
      <PageHead title="这一局的结算"
        subtitle={<>通过 {passed} / {data.levels.length} 件。这一局的经过是游戏世界里的 <Src s="模拟" />，同一件事按传化原来的流程走是 <Src s="推算" />。</>}
        aside={<button className={`chip ${set === "safe" ? "!bg-[#248a3d] !text-white" : ""}`} onClick={() => setSet(set === "safe" ? "given" : "safe")}
                       title="转述少丢条件、研发早发现、工位快、交接等待短、人工与试样便宜：差距往小里算">按最保守参数</button>} />
      <Group title="业务与关卡各走了哪条路">
        {data.levels.map((lv) => (
          <div key={lv.id} className="row flex-col !items-start gap-1 text-[13px]">
            <p className="flex items-center gap-2">
              <span className={`tag ${lv.passed ? "tag-ok" : ""}`}>{lv.id}{lv.passed ? " ✓" : ""}</span>
              <span className="font-semibold">{lv.title}</span><span className="text-ink-2">· {lv.point}</span>
            </p>
            {lv.cases.map((sid) => byId[sid]).filter(Boolean).map((c) => (
              <p key={c.session_id} className="num pl-1 text-[12.5px] text-ink-2">
                化言：{c.path}{c.reused ? "（研发签过的判断替他答了）" : ""}{c.rerouted ? "（先拿到推荐，后来推荐被撤下、改道交研发）" : ""}，经过 {c[set].now.roles.join("、") || "没有人"}，客户等第一个答复 {wait(c.arrived, c.answered)}；
                旧流程：经过 {c[set].old.roles.join("、")}，交接 {c[set].old.handoffs} 次，客户等约 {hours(c[set].first_reply_hours)}
              </p>
            ))}
            {!lv.cases.length && <p className="pl-1 text-[12.5px] text-ink-2">这一件不送新的事：影响的是前面用过同一份资料的事</p>}
          </div>
        ))}
      </Group>
      <TimeBars data={data} set={set} />
      <Headline data={data} set={set} p={data.params[set]} volume={1} tag="模拟" assumed={(k) => data.params.given.assumed.includes(k)} />
    </div>
  );
}
