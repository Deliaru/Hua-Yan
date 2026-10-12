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

// V6-5 岗位对照（scripts/demo_routes.py）：同一批需求按传统定义、v5、v6 三种走法
interface Cell { traditional: string | number; v5: string | number; v6: string | number }
interface Routes {
  batch: { route: string; customer: string; title: string }[]; jue_model: string; rd_tickets: Cell;
  roles: (Cell & { role: string; duty: string; note?: string })[];
  metrics: (Cell & { label: string; note: string })[];
  definitions: Record<"traditional" | "v5" | "v6", string>;
}

// 单卡对照的结论数字（门面按研发视角返回整张卡）
interface Single { one_shot: { missing: string[] }; huayan: { missing: string[]; rounds: { asked: string | null }[]; back_asks: unknown[] } }

// 每块的结论：标题是一句结论，右侧一个关键数字；页首「四个结论」与各块标题用同一份
interface Finding { id: string; topic: string; headline: string; hero: string; heroLabel: string }

function findings(c: Single, d: Distortion, j: JueK, w: Week, v: Routes): Finding[] {
  const e = d.by_route.escalate.metrics;
  const cut = Math.round((1 - e[G3].returned! / e[G1].returned!) * 10) * 10;
  const asks = c.huayan.rounds.filter((r) => r.asked).length;
  const test = Object.entries(j.calibration).filter(([k]) => k.endsWith("/test"));
  const wins = test.filter(([, x]) => x.jue_k.auc > x.jue_proto_rule.auc).length;
  const ask = j.calibration["ask_slot/test"];
  const k = w.detection.jue_k, rule = w.detection.rule_alert;
  const relay = v.metrics[0];
  return [
    { id: "sec-card", topic: "同一个客户，两种做法",
      headline: `一次性翻译缺 ${c.one_shot.missing.length} 项必问信息被退回；化言追问 ${asks} 次、回问 ${c.huayan.back_asks.length} 次，研发拿到的信息是齐的`,
      hero: `${c.one_shot.missing.length} → ${c.huayan.missing.length}`, heroLabel: "研发必问信息缺项" },
    { id: "sec-distortion", topic: "需求到研发手里还剩多少",
      headline: `真正到研发的需求，被退回的比例减少约 ${cut}%`,
      hero: `${pct1(e[G1].returned!)} → ${pct1(e[G3].returned!)}`, heroLabel: `研发退回比例 · 应升级的 ${d.by_route.escalate.n_cards} 张卡` },
    { id: "sec-juek", topic: "觉的判断可信吗",
      headline: `${test.length} 类决策中 ${wins} 类觉比规则分得更准；追问的概率校准得好，阈值可以按代价来定`,
      hero: ask.jue_k.ece.toFixed(3), heroLabel: `追问概率校准误差 · 规则 ${ask.jue_proto_rule.ece.toFixed(3)}` },
    { id: "sec-week", topic: "一周业务里能不能及时发现",
      headline: `命中 ${k.hits}/${k.positives} 个真情况，困难负样本误报 ${k.false_alarms} 次，发现环节调用大模型 ${k.jue_llm_calls} 次`,
      hero: `${k.false_alarms} / ${k.hard_negatives}`, heroLabel: `困难负样本误报 · 规则告警 ${rule.false_alarms} / ${rule.hard_negatives}` },
    { id: "sec-roles", topic: "每个岗位还要不要做过去每单都做的事",
      headline: `同一批 ${v.batch.length} 个需求：研发收到的需求单 ${v.rd_tickets.v5} → ${v.rd_tickets.v6} 张，业务员不再陪聊和签升级，产品经理开始管适用范围和机会`,
      hero: `${relay.v5} → ${relay.v6}`, heroLabel: "人工中转节点 · v5 → v6" },
  ];
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
          <span className={`num text-right ${mine ? "font-semibold text-ink" : "text-ink-2"}`}>{pct1(v)}</span>
        </div>
      ))}
    </div>
  );
}

// 一块：小字主题 → 一句结论（大字）+ 一个关键数字 → 图 → 补充一句 → 收起的「怎么测、完整数据」
function Section({ f, n, children, note, how, more, bare }: {
  f: Finding; n: number; children: React.ReactNode; note?: React.ReactNode; how: React.ReactNode; more?: React.ReactNode; bare?: boolean;
}) {
  return (
    <section id={f.id} className="flex scroll-mt-6 flex-col gap-3">
      <p className="text-[13px] text-ink-3"><span className="num mr-2">0{n}</span>{f.topic}</p>
      <div className="flex items-end justify-between gap-8">
        <h2 className="max-w-[560px] text-[22px] font-semibold leading-[32px] tracking-[-0.01em]">{f.headline}</h2>
        <Hero f={f} />
      </div>
      {bare ? <div className="mt-1">{children}</div> : <div className="group mt-1 flex flex-col gap-4 px-5 py-4">{children}</div>}
      {note && <p className="px-1 text-[13px] leading-[21px] text-ink-2">{note}</p>}
      <div className="px-1">
        <Disclosure label="怎么测的、完整数据与原图">
          <p className="text-[12.5px] leading-[20px] text-ink-2">{how}</p>
          {more}
        </Disclosure>
      </div>
    </section>
  );
}

function Hero({ f, small }: { f: Finding; small?: boolean }) {
  return (
    <div className="shrink-0 text-right">
      <p className={`num whitespace-nowrap font-semibold tracking-[-0.02em] ${small ? "text-[22px] leading-7" : "text-[32px] leading-10"}`}>{f.hero}</p>
      <p className="text-[12px] text-ink-2">{f.heroLabel}</p>
    </div>
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

// 页首：四个结论一览，点一行跳到对应一块
function Summary({ fs }: { fs: Finding[] }) {
  const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  return (
    <div className="group">
      {fs.map((f, i) => (
        <button key={f.id} onClick={() => go(f.id)}
                className={`flex w-full items-center gap-5 px-5 py-3.5 text-left hover:bg-fill ${i ? "border-t border-sep" : ""}`}>
          <span className="num w-5 text-[13px] text-ink-3">0{i + 1}</span>
          <span className="min-w-0 flex-1">
            <span className="block text-[12px] text-ink-3">{f.topic}</span>
            <span className="block text-[15px] font-semibold leading-[22px]">{f.headline}</span>
          </span>
          <Hero f={f} small />
        </button>
      ))}
    </div>
  );
}

function DistortionSection({ f, d, d60 }: { f: Finding; d: Distortion; d60: Distortion }) {
  const e = d.by_route.escalate, l1 = d.by_route.l1;
  const groups = [G1, G2, G3];
  const a = d.relay_assumption;
  return (
    <Section f={f} n={2}
             how={<>同一批需求卡、同一位模拟客户，三种做法各自交给研发的需求，研发要退回多少。程序生成 {d.n_cards} 张需求卡（{d.placeholder_seeds ? "种子为占位数据，" : ""}客户只说现象、被问到才透露），模拟客户、抽取、觉、转译都是规则实现，大模型调用 {d.calls.llm} 次。
               业务员转述的噪声是假设参数（只问 {a.habit_slots.length} 个习惯槽位；现象说笼统 {a.vague_prob}、漏槽位 {a.drop_prob}、记错 {a.swap_prob}）。
               只有 L1 解决不了的需求才会到研发，所以按「应升级」拆开看。来源 docs/reports/distortion_300/。</>}
             note={<>一次性翻译输在不追问：客户开场白里没说的面料、设备、工艺，翻译得再准也翻不出来。错译（引用了别的现象的知识）一次性翻译 {pct1(d.metrics[G2].mistranslation!)}、化言 {pct1(d.metrics[G3].mistranslation!)}；化言每条转译都能回查到客户原话。
               如实说明：L1 可解的卡上觉问得更少，这些卡「退回」的多（{pct1(l1.metrics[G3].returned!)}），但它们现实中不会到研发。</>}
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
    </Section>
  );
}

function JueKSection({ f, j }: { f: Finding; j: JueK }) {
  const test = Object.entries(j.calibration).filter(([k]) => k.endsWith("/test"));
  const wins = test.filter(([, c]) => c.jue_k.auc > c.jue_proto_rule.auc).length;
  const s = j.scheduled_detection;
  return (
    <Section f={f} n={3}
             how={<>觉说「此刻该追问 / 该回问 / 该合并」时，概率靠不靠谱、比同样条件下的规则强不强。追问、回问来自程序生成的对话轨迹，定时类来自生成的业务周在真实链路上跑出的事件；只看测试集。AUC 越高越能分开「该决定」与「不必」，ECE 越低概率越准。
               另有未见现象（heldout）的结果见报告。来源 docs/reports/jue_k/。</>}
             note={<>{test.length > wins && `${test.filter(([, c]) => c.jue_k.auc <= c.jue_proto_rule.auc).map(([k]) => FAMILY[k.split("/")[0]]).join("、")}一类规则已经足够，保留规则。`}{s.weeks.length} 个测试周里，困难负样本误报觉 {s.jue_k.hard_false_alarms} / {s.jue_k.hard_negatives}，原型规则 {s.jue_proto_rule.hard_false_alarms} / {s.jue_proto_rule.hard_negatives}。</>}
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
          <span>决策（测试集）</span><span>觉 · Jue-K 区分度 AUC</span><span>规则 AUC</span>
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
                  <span className={`num w-10 text-right ${i === 0 && mine ? "font-semibold text-ink" : "text-ink-2"}`}>{v.toFixed(2)}</span>
                </span>
              ))}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function RolesSection({ f, v }: { f: Finding; v: Routes }) {
  const cols = ["传统（按定义）", "v5 化言", "v6 化言"];
  const cell = (x: string | number, strong?: boolean) => <td className={`py-2 pl-3 align-top ${strong ? "font-semibold" : "text-ink-2"}`}>{x}</td>;
  return (
    <Section f={f} n={5} bare
             note={<>「传统」一列是按黑线流程定义出来的，不是测量；v5、v6 两列是同一套代码、同一批台词真实运行后由事件日志计出的。
               岗位之间必要的协作都保留，拿掉的是因信息缺失、转述、重复才被迫发生的工作。研发因此多出多少中长期研发时间，需要企业试点验证。</>}
             how={<>同一批 {v.batch.length} 个需求：{v.batch.map((b) => `${b.route}（${b.title}）`).join("；")}。
               v6：{v.definitions.v6}。v5：{v.definitions.v5}。觉用 {v.jue_model}，离线运行（Jev 用桩、抽取用规则）。
               来源 docs/reports/v6_routes/metrics.json，由 scripts/demo_routes.py 生成，脚本对每条路径的关键结果做了断言。全部为模拟数据。</>}
             more={<div className="mt-3 flex flex-col gap-1.5">{v.metrics.map((m) => (
               <p key={m.label} className="text-[12.5px] leading-[20px] text-ink-2"><b className="font-semibold text-ink">{m.label}</b>：{m.note}</p>))}
               {v.roles.filter((x) => x.note).map((x) => (
               <p key={x.duty} className="text-[12.5px] leading-[20px] text-ink-2"><b className="font-semibold text-ink">{x.duty}</b>：{x.note}</p>))}</div>}>
      <div className="group overflow-x-auto px-5 py-3">
        <p className="eyebrow pb-1">岗位判别：过去每张单都要做的事，现在还要不要做</p>
        <table className="w-full text-[13px] leading-5">
          <thead><tr className="text-left text-[12px] text-ink-2">
            <th className="py-1.5 font-semibold">岗位 · 事</th>{cols.map((h) => <th key={h} className="py-1.5 pl-3 font-semibold">{h}</th>)}
          </tr></thead>
          <tbody>
            {v.roles.map((x) => (
              <tr key={x.duty} className="border-t border-sep">
                <td className="py-2 align-top"><span className="mr-1.5 text-ink-3">{x.role}</span>{x.duty}</td>
                {cell(x.traditional)}{cell(x.v5)}{cell(x.v6, true)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 grid grid-cols-4 gap-3">
        {v.metrics.map((m) => (
          <div key={m.label} className="group px-4 py-3">
            <p className="text-[12px] text-ink-2">{m.label}</p>
            <p className="num mt-1 text-[22px] font-semibold leading-7">{m.v6}</p>
            <p className="num text-[12px] text-ink-3">v5 {m.v5} · 传统 {m.traditional}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function WeekSection({ f, w }: { f: Finding; w: Week }) {
  const names = Object.keys(w.detection);
  const k = w.detection.jue_k;
  return (
    <Section f={f} n={4}
             how={<>把觉放进一个完整的模拟业务周（真实链路），看它能否在机会和风险出现后及时提出，同时不把正常行为当成问题。1 个程序生成的模拟业务周（{w.week}），剧本逐条驱动应用门面；埋入 {k.positives} 个真情况和 {k.hard_negatives} 个「看起来像、其实不是」的困难负样本。抽取规则、Jev 桩、转译规则模式；处置由运行器按固定延迟代替人执行。来源 docs/reports/week/。</>}
             note={<>数量很小，只看方向。觉全天开着几乎不花钱：发现环节是本地小模型，不调用大模型。</>}
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
            <div key={d} className={`rounded-[10px] px-4 py-3 ${mine ? "bg-white shadow-[inset_0_0_0_1.5px_var(--color-ink)]" : "bg-[#f7f7f9]"}`}>
              <p className={`text-[13px] font-semibold ${mine ? "text-ink" : "text-ink-2"}`}>{DISCOVERER[d] ?? d}</p>
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
  const c = useData(() => api.singleCard<Single>("rd:R02"), []);
  const d = useData(() => api.report<Distortion>("distortion_300"), []);
  const d60 = useData(() => api.report<Distortion>("distortion"), []);
  const j = useData(() => api.report<JueK>("jue_k"), []);
  const w = useData(() => api.report<Week>("week"), []);
  const v = useData(() => api.report<Routes>("v6_routes"), []);
  if (!c || !d || !d60 || !j || !w || !v) return null;
  const fs = findings(c, d, j, w, v);
  return (
    <>
      <Side>
        <SideHead>评测</SideHead>
        <nav className="flex flex-col">
          {fs.map((f, i) => (
            <a key={f.id} href={`#${f.id}`} onClick={(e) => { e.preventDefault(); document.getElementById(f.id)?.scrollIntoView({ behavior: "smooth" }); }}
               className="side-row text-[13px]"><span className="num mr-2 text-ink-3">0{i + 1}</span>{f.topic}</a>
          ))}
        </nav>
        <p className="mt-4 px-[18px] text-[12px] leading-[18px] text-ink-3">
          数字取自各报告的 metrics.json，同一种子重跑逐字节一致；结论与限制以各报告 README.md 为准。
        </p>
      </Side>
      <div className="mx-auto flex max-w-[960px] flex-col gap-14 px-8 pb-24 pt-7">
        <div className="flex flex-col gap-4">
          <PageHead title="研发开工前，需求被说清楚了吗" subtitle="全部基于模拟数据，是相对比较，不是真实业务验证。完整率与需退回比例是返工的前置指标，不是返工次数或工时。五个结论，点一行看怎么测出来的。" />
          <Summary fs={fs} />
        </div>
        <Section f={fs[0]} n={1} bare
                 how="同一张需求卡、同一位模拟客户：左边把客户开场白一次性翻译成化学语言；右边是化言，觉逐轮提示该追问什么，转译后还缺的再回问。来源 docs/reports/single_card/。">
          <SingleCard viewer="rd:R02" />
        </Section>
        <DistortionSection f={fs[1]} d={d} d60={d60} />
        <JueKSection f={fs[2]} j={j} />
        <WeekSection f={fs[3]} w={w} />
        <RolesSection f={fs[4]} v={v} />
      </div>
    </>
  );
}
