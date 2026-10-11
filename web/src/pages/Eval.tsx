// 评测页（WP-E）：展示 docs/reports/ 下失真对照、Jue-K、业务周三份报告的关键数字与图，每块写明数据来源。
// 数字只读各报告的 metrics.json，图为同目录的 png；结论与限制以各报告 README.md 为准。
import { api } from "../api";
import { FAMILY, Side, pct, useData, useLabels } from "../ctx";
import { Group, PageHead, SideHead } from "../components/ui";
import { SingleCard } from "./SingleCard";

type Num = number | null;
interface Distortion {
  n_cards: number; placeholder_seeds: boolean; calls: Record<string, number>;
  relay_assumption: { habit_slots: string[]; vague_prob: number; drop_prob: number; swap_prob: number };
  metrics: Record<string, Record<string, Num>>; labels: Record<string, string>;
}
interface Calib { auc: number; ece: number }
interface JueK {
  calibration: Record<string, { jue_k: Calib & { n: number }; jue_proto_rule: Calib; positives: number }>;
  scheduled_detection: { weeks: number[]; jue_k: Detect; jue_proto_rule: Detect };
}
interface Detect { hits: number; positives: number; hard_false_alarms: number; hard_negatives: number }
interface WeekSummary { hits: number; positives: number; false_alarms: number; hard_negatives: number; mean_lead_hours: Num;
  n_found_outside_injections: number; jue_llm_calls: number }
interface Week {
  week: string; opportunity_theme: string; detection: Record<string, WeekSummary>;
  consequences: Record<string, { found_at: string | null; escalations_after: number; l1_hits_after: number; all_escalations: number }>;
}

const RATE = new Set(["completeness", "slot_error", "mistranslation", "traceable", "returned", "backs_useful"]);
const DISCOVERER: Record<string, string> = { jue_proto: "觉原型", jue_k: "Jue-K", rule_alert: "规则告警（升级 ≥ 3 次）" };
const fmt = (k: string, v: Num) => (v == null ? "—" : RATE.has(k) ? pct(v) : v.toFixed(2));

function Figure({ src, alt }: { src: string; alt: string }) {
  return <div className="row !p-3"><img src={src} alt={alt} className="w-full" /></div>;
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="overflow-x-auto px-4 py-2">
      <table className="w-full text-[13px]">
        <thead><tr>{head.map((h, i) => <th key={i} className={`py-1.5 font-semibold text-ink-2 ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-sep">
              {r.map((c, j) => <td key={j} className={`num py-1.5 ${j ? "text-right" : "text-left"}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DistortionBlock() {
  const L = useLabels();
  const d = useData(() => api.report<Distortion>("distortion"), []);
  if (!d) return null;
  const groups = Object.keys(d.metrics);
  const a = d.relay_assumption;
  return (
    <Group title="失真对照：需求到研发手里还剩多少、对不对"
           foot={`来源：docs/reports/distortion/。${d.n_cards} 张程序生成的需求卡，${d.placeholder_seeds ? "种子为占位数据，" : ""}`
             + `模拟客户为模板模式，抽取、觉、转译均为规则实现；大模型调用 ${d.calls.llm} 次。G1 的转述噪声是假设参数`
             + `（只问 ${a.habit_slots.map(L.slot).join("、")}；现象说笼统 ${a.vague_prob}、漏槽位 ${a.drop_prob}、记错 ${a.swap_prob}），企业数据到位后替换。`}>
      <Table head={["指标", ...groups]}
             rows={Object.entries(d.labels).map(([k, label]) => [label, ...groups.map((g) => fmt(k, d.metrics[g][k]))])} />
      <Figure src="reports/distortion/distortion.png" alt="失真对照" />
    </Group>
  );
}

function JueKBlock() {
  const j = useData(() => api.report<JueK>("jue_k"), []);
  if (!j) return null;
  const s = j.scheduled_detection;
  return (
    <Group title="Jue-K：一个模型覆盖五类决策，输出校准概率"
           foot="来源：docs/reports/jue_k/。追问 / 回问来自程序生成的对话轨迹（另有未见现象 heldout 的结果见报告）；定时三类来自生成的业务周在真实链路上跑出的事件。留出周 w1 上的对照见下方业务周。">
      <Table head={["决策（测试集）", "样本（正例）", "Jue-K AUC", "Jue-K ECE", "原型规则 AUC", "原型规则 ECE"]}
             rows={Object.entries(j.calibration).filter(([k]) => k.endsWith("/test")).map(([k, c]) => [
               FAMILY[k.split("/")[0]], `${c.jue_k.n}（${c.positives}）`, c.jue_k.auc.toFixed(3), c.jue_k.ece.toFixed(3),
               c.jue_proto_rule.auc.toFixed(3), c.jue_proto_rule.ece.toFixed(3)])} />
      <Table head={[`定时发现（${s.weeks.length} 个测试周，真实链路事件）`, "注入命中", "困难负样本误报"]}
             rows={([["Jue-K", s.jue_k], ["原型规则", s.jue_proto_rule]] as const).map(([n, d]) =>
               [n, `${d.hits} / ${d.positives}`, `${d.hard_false_alarms} / ${d.hard_negatives}`])} />
      <Figure src="reports/jue_k/reliability.png" alt="可靠性图" />
      <Figure src="reports/jue_k/ask_curve.png" alt="追问操作点" />
    </Group>
  );
}

function WeekBlock() {
  const w = useData(() => api.report<Week>("week"), []);
  if (!w) return null;
  const names = Object.keys(w.detection);
  return (
    <Group title="业务周：真实链路上的定时发现，机会汇聚处置 vs 不处置"
           foot={`来源：docs/reports/week/。1 个程序生成的模拟业务周（${w.week}），剧本逐条驱动应用门面；抽取规则、Jev 桩、转译规则模式；`
             + "处置动作由运行器按固定延迟代替人执行。数量很小，只看方向。觉原型的泄露风险一行受检索噪声影响（每次检索都被拦截几十条），不成立；Jue-K 在留出周上区分开了两人，见报告 README。"}>
      <Table head={["发现器", "真注入命中", "困难负样本误报", "平均提前（小时）", "注入外发现", "发现环节大模型调用"]}
             rows={names.map((d) => {
               const s = w.detection[d];
               return [DISCOVERER[d] ?? d, `${s.hits} / ${s.positives}`, `${s.false_alarms} / ${s.hard_negatives}`,
                       s.mean_lead_hours ?? "—", s.n_found_outside_injections, s.jue_llm_calls];
             })} />
      <Table head={["发现器 / 分支", "发现时刻", "发现后同主题升级", "发现后 L1 直接命中", "全周升级"]}
             rows={Object.entries(w.consequences).map(([k, c]) => {
               const [d, p] = k.split("/");
               return [`${DISCOVERER[d] ?? d} · ${p === "handle" ? "处置" : "不处置"}`, c.found_at?.slice(5, 16).replace("T", " ") ?? "—",
                       c.escalations_after, c.l1_hits_after, c.all_escalations];
             })} />
      <Figure src="reports/week/week_detection.png" alt="发现时间线" />
      <Figure src="reports/week/week_escalations.png" alt="按天升级次数" />
    </Group>
  );
}

export function Eval() {
  return (
    <>
      <Side>
        <SideHead>评测</SideHead>
        <p className="px-[18px] text-[12px] leading-[18px] text-ink-2">
          全部基于模拟数据。数字取自各报告的 metrics.json，结论与限制以各报告 README.md 为准。
        </p>
      </Side>
      <div className="mx-auto flex max-w-[960px] flex-col gap-7 px-8 pb-24 pt-7">
        <PageHead title="评测" subtitle="单卡对照 · 失真可度量 · 觉的校准 · 真实链路上的发现与处置" />
        <SingleCard />
        <DistortionBlock />
        <JueKBlock />
        <WeekBlock />
      </div>
    </>
  );
}
