// 评测页（WP-E）：先给三个结论数字，再按「要回答的问题 → 怎么测 → 结论 → 简图」讲四块；完整表格与原图收进「完整数据」。
// 数字只读各报告的 metrics.json（distortion_300 按「应升级」拆开），图为同目录的 png；结论与限制以各报告 README.md 为准。
import { api } from "../api";
import { FAMILY, Side, pct, useData } from "../ctx";
import { Disclosure, PageHead, SideHead } from "../components/ui";
import { SingleCard } from "./SingleCard";

type Num = number | null;
type Metrics = Record<string, Record<string, Num>>;
interface Distortion {
  n_cards: number; placeholder_seeds: boolean; calls: Record<string, number>;
  relay_assumption: { habit_slots: string[]; vague_prob: number; drop_prob: number; swap_prob: number };
  metrics: Metrics; labels: Record<string, string>;
  by_route: Record<"escalate" | "l1", { n_cards: number; metrics: Metrics }>;
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
  week: string; detection: Record<string, WeekSummary>;
  consequences: Record<string, { found_at: string | null; escalations_after: number; l1_hits_after: number; all_escalations: number }>;
}

const G1 = "G1 业务员转述", G2 = "G2 一次性翻译", G3 = "G3 化言";
const RATE = new Set(["completeness", "slot_error", "mistranslation", "traceable", "returned", "backs_useful"]);
const DISCOVERER: Record<string, string> = { jue_proto: "觉原型（规则打分）", jue_k: "觉（Jue-K）", rule_alert: "常见规则告警（升级 ≥ 3 次）" };
const pct1 = (x: number) => `${(Math.round(x * 1000) / 10).toString()}%`;
const fmt = (k: string, v: Num) => (v == null ? "—" : RATE.has(k) ? pct1(v) : v.toFixed(2));
const groupName = (g: string) => g.replace(/^G\d\s*/, "");

const SECTIONS = [
  ["sec-card", "同一个客户，两种做法"],
  ["sec-distortion", "需求到研发手里还剩多少"],
  ["sec-juek", "觉的判断可信吗"],
  ["sec-week", "一周业务里能不能及时发现"],
] as const;

function Stat({ label, from, to, fromLabel, toLabel, note }: {
  label: string; from: string; to: string; fromLabel: string; toLabel: string; note: string;
}) {
  return (
    <div className="group flex flex-col gap-1 px-5 py-4">
      <span className="eyebrow">{label}</span>
      <span className="mt-1 flex items-baseline gap-2">
        <span className="num text-[18px] text-ink-3 line-through decoration-1">{from}</span>
        <span className="text-ink-3">→</span>
        <span className="num text-[32px] font-semibold leading-9 tracking-[-0.02em] text-accent">{to}</span>
      </span>
      <span className="text-[12px] text-ink-2">{fromLabel} → <b className="font-semibold text-ink">{toLabel}</b></span>
      <span className="mt-1 text-[11.5px] leading-[17px] text-ink-3">{note}</span>
    </div>
  );
}

// 横向条：一行一组，化言一行用强调色
function Bars({ rows, worse }: { rows: [string, number, boolean][]; worse?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      {rows.map(([name, v, mine]) => (
        <div key={name} className="grid grid-cols-[150px_1fr_52px] items-center gap-3 text-[13px]">
          <span className={mine ? "font-semibold" : "text-ink-2"}>{name}</span>
          <span className="h-2.5 overflow-hidden rounded-full bg-fill">
            <span className={`block h-full rounded-full ${mine ? "bg-accent" : worse ? "bg-[#c7c7cc]" : "bg-[#aeb4bf]"}`}
                  style={{ width: `${Math.max(v * 100, 1)}%` }} />
          </span>
          <span className={`num text-right ${mine ? "font-semibold text-accent" : "text-ink-2"}`}>{pct1(v)}</span>
        </div>
      ))}
    </div>
  );
}

function Section({ id, n, title, question, how, conclusion, children, more }: {
  id: string; n: number; title: string; question: string; how: React.ReactNode; conclusion: React.ReactNode;
  children: React.ReactNode; more?: React.ReactNode;
}) {
  return (
    <section id={id} className="flex scroll-mt-6 flex-col gap-3">
      <div>
        <span className="eyebrow">0{n}</span>
        <h2 className="text-[17px] font-semibold leading-6">{title}</h2>
        <p className="mt-0.5 text-[13px] text-ink-2">{question}</p>
      </div>
      <div className="group">
        <div className="flex flex-col gap-4 px-5 py-4">{children}</div>
        <div className="attn-edge px-5 py-3 text-[13px] leading-5"><b className="font-semibold">结论　</b>{conclusion}</div>
      </div>
      <p className="group-foot leading-[18px]">怎么测：{how}</p>
      {more && <div className="px-1"><Disclosure label={<span>完整数据与原图</span>}>{more}</Disclosure></div>}
    </section>
  );
}

function Figure({ src, alt }: { src: string; alt: string }) {
  return <img src={src} alt={alt} className="w-full rounded-lg bg-white p-2" />;
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="group overflow-x-auto px-4 py-2">
      <table className="w-full text-[12.5px]">
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

function MetricTable({ m, labels }: { m: Metrics; labels: Record<string, string> }) {
  const groups = Object.keys(m);
  return <Table head={["指标", ...groups.map(groupName)]}
                rows={Object.entries(labels).map(([k, label]) => [label, ...groups.map((g) => fmt(k, m[g][k]))])} />;
}

function Headline({ d, w }: { d: Distortion; w: Week }) {
  const e = d.by_route.escalate.metrics;
  const juek = w.detection.jue_k, rule = w.detection.rule_alert;
  const of = `${d.n_cards} 张模拟需求卡中应升级的 ${d.by_route.escalate.n_cards} 张（真正会到研发的那部分）`;
  return (
    <div className="grid grid-cols-3 gap-4">
      <Stat label="研发需退回的比例" from={pct1(e[G1].returned!)} to={pct1(e[G3].returned!)} fromLabel="业务员转述" toLabel="化言" note={of} />
      <Stat label="关键信息完整率" from={pct1(e[G1].completeness!)} to={pct1(e[G3].completeness!)} fromLabel="业务员转述" toLabel="化言" note={of} />
      <Stat label="困难负样本上的误报" from={`${rule.false_alarms} / ${rule.hard_negatives}`} to={`${juek.false_alarms} / ${juek.hard_negatives}`}
            fromLabel="常见规则告警" toLabel="觉（Jue-K）"
            note={`模拟业务周 ${w.week}，真实链路；觉在发现环节调用大模型 ${juek.jue_llm_calls} 次`} />
    </div>
  );
}

function DistortionSection({ d, d60 }: { d: Distortion; d60: Distortion }) {
  const e = d.by_route.escalate, l1 = d.by_route.l1;
  const groups = [G1, G2, G3];
  const a = d.relay_assumption;
  return (
    <Section id="sec-distortion" n={2} title="需求到研发手里还剩多少、对不对"
             question="同一批需求卡、同一位模拟客户，三种做法各自交给研发的需求，研发要退回多少？"
             how={<>程序生成 {d.n_cards} 张需求卡（{d.placeholder_seeds ? "种子为占位数据，" : ""}客户只说现象、被问到才透露），模拟客户、抽取、觉、转译都是规则实现，大模型调用 {d.calls.llm} 次。
               业务员转述的噪声是假设参数（只问 {a.habit_slots.length} 个习惯槽位；现象说笼统 {a.vague_prob}、漏槽位 {a.drop_prob}、记错 {a.swap_prob}）。
               只有 L1 解决不了的需求才会到研发，所以按「应升级」拆开看。来源 docs/reports/distortion_300/。</>}
             conclusion={<>真正到研发的需求，退回比例从 {pct1(e.metrics[G1].returned!)} 降到 {pct1(e.metrics[G3].returned!)}。一次性翻译输在不追问：客户开场白里没说的面料、设备、工艺，翻译得再准也翻不出来。
               如实说明：L1 可解的卡上 Jue-K 问得更少，这些卡被「退回」的多（{pct1(l1.metrics[G3].returned!)}）；但它们现实中不会到研发。</>}
             more={<>
               <p className="text-[12px] text-ink-2">应升级的 {e.n_cards} 张卡</p>
               <MetricTable m={e.metrics} labels={d.labels} />
               <p className="mt-2 text-[12px] text-ink-2">L1 可解的 {l1.n_cards} 张卡</p>
               <MetricTable m={l1.metrics} labels={d.labels} />
               <p className="mt-2 text-[12px] text-ink-2">全部 {d.n_cards} 张卡</p>
               <MetricTable m={d.metrics} labels={d.labels} />
               <p className="mt-2 text-[12px] text-ink-2">单卡对照所在的 {d60.n_cards} 张卡（docs/reports/distortion/）</p>
               <MetricTable m={d60.metrics} labels={d60.labels} />
             </>}>
      <div className="grid grid-cols-2 gap-6">
        <div>
          <p className="mb-2.5 text-[12px] font-semibold text-ink-2">研发需退回的比例（越低越好）</p>
          <Bars worse rows={groups.map((g) => [groupName(g), e.metrics[g].returned!, g === G3])} />
        </div>
        <div>
          <p className="mb-2.5 text-[12px] font-semibold text-ink-2">关键信息完整率（越高越好）</p>
          <Bars rows={groups.map((g) => [groupName(g), e.metrics[g].completeness!, g === G3])} />
        </div>
      </div>
      <p className="text-[12.5px] text-ink-2">
        错译（引用了别的现象的知识）：一次性翻译 {pct1(d.metrics[G2].mistranslation!)}，化言 {pct1(d.metrics[G3].mistranslation!)}；
        化言每条转译都能回查到客户原话（{pct1(d.metrics[G3].traceable!)}），业务员转述 {pct1(d.metrics[G1].traceable!)}。
      </p>
    </Section>
  );
}

function JueKSection({ j }: { j: JueK }) {
  const test = Object.entries(j.calibration).filter(([k]) => k.endsWith("/test"));
  const wins = test.filter(([, c]) => c.jue_k.auc > c.jue_proto_rule.auc).length;
  const ask = j.calibration["ask_slot/test"];
  const s = j.scheduled_detection;
  return (
    <Section id="sec-juek" n={3} title="觉的判断可信吗"
             question="觉说「此刻该追问 / 该回问 / 该合并」时，概率靠不靠谱？比同样条件下的规则强吗？"
             how={<>追问、回问来自程序生成的对话轨迹，定时类来自生成的业务周在真实链路上跑出的事件；只看测试集。AUC 越高越能分开「该决定」与「不必」，ECE 越低概率越准。
               另有未见现象（heldout）的结果见报告。来源 docs/reports/jue_k/。</>}
             conclusion={<>{test.length} 类决策中 {wins} 类 Jue-K 的区分度高于规则{test.length > wins && `（其余 ${test.length - wins} 类规则已经足够，保留规则）`}；追问概率的校准误差 {ask.jue_k.ece.toFixed(3)}，规则分为 {ask.jue_proto_rule.ece.toFixed(3)}，所以阈值可以按「漏问与多问的代价」来定。
               {s.weeks.length} 个测试周里，困难负样本误报 Jue-K {s.jue_k.hard_false_alarms} / {s.jue_k.hard_negatives}，原型规则 {s.jue_proto_rule.hard_false_alarms} / {s.jue_proto_rule.hard_negatives}。</>}
             more={<>
               <Table head={["决策（测试集）", "样本（正例）", "Jue-K AUC", "Jue-K ECE", "规则 AUC", "规则 ECE"]}
                      rows={test.map(([k, c]) => [FAMILY[k.split("/")[0]], `${c.jue_k.n}（${c.positives}）`, c.jue_k.auc.toFixed(3), c.jue_k.ece.toFixed(3),
                        c.jue_proto_rule.auc.toFixed(3), c.jue_proto_rule.ece.toFixed(3)])} />
               <Table head={[`定时发现（${s.weeks.length} 个测试周）`, "注入命中", "困难负样本误报"]}
                      rows={([["Jue-K", s.jue_k], ["原型规则", s.jue_proto_rule]] as const).map(([n, d]) =>
                        [n, `${d.hits} / ${d.positives}`, `${d.hard_false_alarms} / ${d.hard_negatives}`])} />
               <p className="text-[12px] text-ink-2">可靠性图（横轴预测概率、纵轴实际比例，越贴对角线越准）与追问操作点（问得越多准确率越高，Jue-K 用更少的追问达到同样的准确率）：</p>
               <Figure src="reports/jue_k/reliability.png" alt="可靠性图" />
               <Figure src="reports/jue_k/ask_curve.png" alt="追问操作点" />
             </>}>
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-[150px_1fr_1fr] gap-3 text-[11.5px] font-semibold text-ink-3">
          <span>决策</span><span>Jue-K 区分度（AUC）</span><span>规则（AUC）</span>
        </div>
        {test.map(([k, c]) => {
          const mine = c.jue_k.auc > c.jue_proto_rule.auc;
          return (
            <div key={k} className="grid grid-cols-[150px_1fr_1fr] items-center gap-3 text-[13px]">
              <span className={mine ? "font-semibold" : "text-ink-2"}>{FAMILY[k.split("/")[0]]}</span>
              {[c.jue_k.auc, c.jue_proto_rule.auc].map((v, i) => (
                <span key={i} className="flex items-center gap-2">
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-fill">
                    <span className={`block h-full rounded-full ${i === 0 && mine ? "bg-accent" : "bg-[#aeb4bf]"}`} style={{ width: `${v * 100}%` }} />
                  </span>
                  <span className={`num w-10 text-right ${i === 0 && mine ? "font-semibold text-accent" : "text-ink-2"}`}>{v.toFixed(2)}</span>
                </span>
              ))}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function WeekSection({ w }: { w: Week }) {
  const names = Object.keys(w.detection);
  const k = w.detection.jue_k;
  return (
    <Section id="sec-week" n={4} title="一周业务里能不能及时发现、又不乱报"
             question="把觉放进一个完整的模拟业务周（真实链路），它能否在机会和风险出现后及时提出，同时不把正常行为当成问题？"
             how={<>1 个程序生成的模拟业务周（{w.week}），剧本逐条驱动应用门面；埋入 {k.positives} 个真情况和 {k.hard_negatives} 个「看起来像、其实不是」的困难负样本。抽取规则、Jev 桩、转译规则模式；处置由运行器按固定延迟代替人执行。数量很小，只看方向。来源 docs/reports/week/。</>}
             conclusion={<>Jue-K 命中 {k.hits} / {k.positives} 个真情况，困难负样本误报 {k.false_alarms} / {k.hard_negatives}；常见规则告警误报 {w.detection.rule_alert.false_alarms} / {w.detection.rule_alert.hard_negatives}。
               发现环节大模型调用 {k.jue_llm_calls} 次：觉全天开着几乎不花钱。</>}
             more={<>
               <Table head={["发现器 / 分支", "发现时刻", "发现后同主题升级", "发现后 L1 直接命中", "全周升级"]}
                      rows={Object.entries(w.consequences).map(([key, c]) => {
                        const [d, p] = key.split("/");
                        return [`${DISCOVERER[d] ?? d} · ${p === "handle" ? "处置" : "不处置"}`, c.found_at?.slice(5, 16).replace("T", " ") ?? "—",
                                c.escalations_after, c.l1_hits_after, c.all_escalations];
                      })} />
               <p className="text-[12px] text-ink-2">觉原型的泄露风险一行受检索噪声影响（每次检索都被拦截几十条），不成立；Jue-K 在留出周上区分开了两人，见报告 README。</p>
               <Figure src="reports/week/week_detection.png" alt="发现时间线" />
               <Figure src="reports/week/week_escalations.png" alt="按天升级次数" />
             </>}>
      <div className="grid grid-cols-3 gap-3">
        {names.map((d) => {
          const s = w.detection[d], mine = d === "jue_k";
          return (
            <div key={d} className={`rounded-[10px] px-4 py-3 ${mine ? "bg-[rgba(10,108,223,.06)] shadow-[inset_0_0_0_1px_rgba(10,108,223,.25)]" : "bg-[#f7f7f9]"}`}>
              <p className={`text-[12.5px] ${mine ? "font-semibold text-accent" : "font-semibold text-ink-2"}`}>{DISCOVERER[d] ?? d}</p>
              <dl className="mt-2 grid grid-cols-[1fr_auto] gap-y-1 text-[12.5px]">
                <dt className="text-ink-2">真情况命中</dt><dd className="num text-right">{s.hits} / {s.positives}</dd>
                <dt className="text-ink-2">困难负样本误报</dt><dd className={`num text-right ${s.false_alarms ? "text-danger" : ""}`}>{s.false_alarms} / {s.hard_negatives}</dd>
                <dt className="text-ink-2">平均提前（小时）</dt><dd className="num text-right">{s.mean_lead_hours ?? "—"}</dd>
                <dt className="text-ink-2">大模型调用</dt><dd className="num text-right">{s.jue_llm_calls}</dd>
              </dl>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

export function Eval() {
  const d = useData(() => api.report<Distortion>("distortion_300"), []);
  const d60 = useData(() => api.report<Distortion>("distortion"), []);
  const j = useData(() => api.report<JueK>("jue_k"), []);
  const w = useData(() => api.report<Week>("week"), []);
  return (
    <>
      <Side>
        <SideHead>评测</SideHead>
        <nav className="flex flex-col">
          {SECTIONS.map(([id, label], i) => (
            <a key={id} href={`#${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); }}
               className="side-row text-[13px]"><span className="num mr-2 text-ink-3">0{i + 1}</span>{label}</a>
          ))}
        </nav>
        <p className="mt-4 px-[18px] text-[12px] leading-[18px] text-ink-3">
          全部基于模拟数据，是相对比较，不是真实业务验证。数字取自各报告的 metrics.json，同一种子重跑逐字节一致；结论与限制以各报告 README.md 为准。
        </p>
      </Side>
      <div className="mx-auto flex max-w-[960px] flex-col gap-10 px-8 pb-24 pt-7">
        <div className="flex flex-col gap-4">
          <PageHead title="评测" subtitle="化言让研发拿到的需求更完整、更少退回吗？三个结论数字，下面四块逐一说明怎么测出来的。" />
          {d && w && <Headline d={d} w={w} />}
        </div>
        <section id="sec-card" className="flex scroll-mt-6 flex-col gap-3">
          <div>
            <span className="eyebrow">01</span>
            <h2 className="text-[17px] font-semibold leading-6">同一个客户，两种做法</h2>
            <p className="mt-0.5 text-[13px] text-ink-2">左边把客户开场白一次性翻译成化学语言；右边是化言：觉逐轮提示该追问什么，转译后还缺的再回问。点「下一轮」逐轮播放。</p>
          </div>
          <SingleCard viewer="rd:R02" />
        </section>
        {d && d60 && <DistortionSection d={d} d60={d60} />}
        {j && <JueKSection j={j} />}
        {w && <WeekSection w={w} />}
      </div>
    </>
  );
}
