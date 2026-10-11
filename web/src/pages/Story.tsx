// 演示工作面：独立的讲解页。沿一条真实录制的需求（runs/demo_record/record_v5.json，模拟数据）逐步走完三层，
// 左边是这一步工作面上的画面（摘自录制运行的原文与概率），右边讲这一步的业务价值与创新；最后是未来展望。
// 只读、不调用接口，不改变共享的演示进度；想亲手操作去「沉浸工作面」。数字出处见各章「数据」，与 docs/PITCH.md 一致。
import { useEffect, useState } from "react";
import { PageHead } from "../components/ui";

type Layer = 0 | 1 | 2 | 3;
interface Chapter {
  title: string; layer: Layer; who: string; screen: React.ReactNode;
  happened: string; value: string[]; innovation: string[]; data: [string, string, string][];
}

// ── 画面上的小部件（只为讲解，样式沿用工作面） ─────────────────────
const LAYERS = [
  [1, "L1 · 场景语言", "客户 · 业务员", "只看得到说明书和用法"],
  [2, "L2 · 产品需求语言", "产品经理 Agent", "研发知识只见归属"],
  [3, "L3 · 化学语言", "研发", "全部可见，封存项只本层"],
] as const;

function LayerRail({ on }: { on: Layer }) {
  return (
    <div className="grid grid-cols-3 gap-1.5">
      {LAYERS.map(([l, name, who, see]) => (
        <div key={l} className={`rounded-[8px] px-2.5 py-1.5 transition-colors ${on === l ? "bg-accent text-white" : "bg-fill text-ink-3"}`}>
          <p className="text-[11.5px] font-semibold">{name}</p>
          <p className={`text-[10.5px] ${on === l ? "text-white/80" : ""}`}>{who} · {see}</p>
        </div>
      ))}
    </div>
  );
}

function Screen({ who, children }: { who: string; children: React.ReactNode }) {
  return (
    <div className="group">
      <div className="flex items-center gap-2 border-b border-sep bg-[#fafafb] px-4 py-2">
        <span className="flex gap-1">{[0, 1, 2].map((i) => <i key={i} className="h-2 w-2 rounded-full bg-[#d8d8dd]" />)}</span>
        <span className="text-[12px] font-semibold text-ink-2">{who}</span>
      </div>
      <div className="flex flex-col gap-3 px-4 py-4">{children}</div>
    </div>
  );
}

function Say({ from, children }: { from: "customer" | "sales"; children: React.ReactNode }) {
  const c = from === "customer";
  return (
    <div className={`flex ${c ? "" : "justify-end"}`}>
      <div className={`max-w-[85%] rounded-[12px] px-3 py-2 text-[13px] leading-5 ${c ? "bg-fill" : "bg-[rgba(10,108,223,.09)]"}`}>
        <p className="mb-0.5 text-[11px] font-semibold text-ink-3">{c ? "客户" : "业务员（Agent 起草，业务员发出）"}</p>{children}
      </div>
    </div>
  );
}

function Jue({ title, score, why, flow }: { title: string; score: string; why: string; flow: string }) {
  return (
    <div className="decision rounded-[10px] px-3.5 py-2.5">
      <p className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold tracking-[.04em] text-attn-ink">觉提出</span>
        <span className="num text-[11.5px] font-semibold text-attn-ink">{score}</span>
      </p>
      <p className="mt-0.5 text-[13.5px] font-semibold leading-5">{title}</p>
      <p className="mt-1 text-[12px] leading-[18px] text-ink-2">依据：{why}</p>
      <p className="mt-1 text-[12px] leading-[18px] text-ink-2">{flow}</p>
    </div>
  );
}

function Signed({ children }: { children: React.ReactNode }) {
  return <p className="flex items-center gap-2 text-[12.5px]"><span className="tag tag-accent">✓ 签字</span>{children}</p>;
}

function Draft({ label = "Agent 起草", children }: { label?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border border-dashed border-[rgba(60,60,67,.25)] px-3 py-2 text-[13px] leading-5">
      <span className="tag tag-agent mb-1">{label}</span><div>{children}</div>
    </div>
  );
}

function Item({ term, text, quote, owner, edited }: { term: string; text: string; quote: string; owner: string; edited?: string }) {
  return (
    <div className="border-t border-sep pt-2 text-[13px] leading-5 first:border-t-0 first:pt-0">
      <p><b className="font-semibold">「{term}」</b>→ {text}{edited && <span className="rounded bg-[rgba(10,108,223,.1)] px-1 text-accent">{edited}</span>}</p>
      <p className="mt-0.5 flex flex-wrap gap-1.5 text-[11.5px] text-ink-3">
        <span>原话「{quote}」</span><span>·</span><span>依据 {owner} 的转化知识</span>
      </p>
    </div>
  );
}

function Slots({ items }: { items: [string, string, string][] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map(([k, v, q]) => <span key={k} className="tag" title={`原话「${q}」`}>{k}：{v}<span className="ml-1 font-normal text-ink-3">「{q}」</span></span>)}
    </div>
  );
}

// ── 章节：画面原文摘自录制运行 run-1e92ea5b8d30（模拟数据） ─────────────
const CHAPTERS: Chapter[] = [
  {
    title: "传话游戏", layer: 0, who: "今天的样子：没有化言",
    screen: (
      <div className="flex flex-col gap-3">
        <Say from="customer">我们染完以后布面深一块浅一块，客户老投诉</Say>
        <div className="rounded-[10px] bg-fill px-3 py-2 text-[13px] leading-5">
          <p className="mb-0.5 text-[11px] font-semibold text-ink-3">业务员转述给研发</p>客户说染色有问题，要个匀染剂。
        </div>
        <div className="rounded-[10px] bg-[rgba(215,0,21,.06)] px-3 py-2 text-[13px] leading-5">
          <p className="mb-0.5 text-[11px] font-semibold text-danger">研发</p>什么布？什么设备？染浴 pH 多少？—— 退回，重新问。
        </div>
      </div>
    ),
    happened: "客户只会描述现象，业务员凭自己的理解转述一遍，研发拿到的是走样的需求，只能退回或按走样的需求做无用功。",
    value: ["翻译得再准、检索得再全，也补不回客户没说的信息、业务员丢掉的信息、研发不肯交出来的知识。", "化言要修的是这条会失真的需求传递链，而不是做一个更懂化学的问答机器人。"],
    innovation: ["先造尺子：用只说现象、被问到才透露的模拟客户，把「传话游戏」变成可度量的任务。"],
    data: [["95%", "业务员转述后，真正到研发的需求需退回的比例", "300 张模拟卡中应升级的 41 张"], ["95%", "一次性翻译（不追问）同样需退回", "同上"]],
  },
  {
    title: "追问", layer: 1, who: "业务员小王的工作面 · 某印染厂 A",
    screen: (
      <>
        <Say from="customer">我们染完以后布面深一块浅一块，客户老投诉</Say>
        <Jue title="趁客户还在，该问面料和染色设备" score="面料 80% · 设备 30%（Jue-K，阈值 15%）"
             why="现象是色花，面料和设备会改变候选产品，也是研发必问的信息" flow="提示给业务员；业务员对 Agent 说「帮我回一句，问问是什么布、用什么缸染的」" />
        <Say from="sales">请问具体是什么面料材质的布？染色用的是哪种染缸（比如溢流缸还是气流缸）呢？</Say>
        <Say from="customer">锦氨弹力布，气流缸，浴比很低。上次你们推荐的那个匀染剂用了，回修了三次</Say>
        <div>
          <p className="mb-1.5 text-[11.5px] font-semibold text-ink-3">场景需求卡：每一格都绑定客户原话</p>
          <Slots items={[["现象", "色花", "深一块浅一块"], ["面料", "锦纶氨纶", "锦氨弹力布"], ["设备", "气流染色机", "气流缸"]]} />
        </div>
      </>
    ),
    happened: "客户只说了现象。觉看着对话，提示业务员此刻该问面料和设备；业务员用一句话吩咐自己的 Agent，Agent 起草追问，业务员确认后发出。",
    value: ["业务员不用懂化学也能问到点上，研发要的信息在客户还在时就问到了。", "Agent 还能随时帮业务员查说明书和用法、理解需求、起草话术；够不着的知识会告诉他「研发陈工懂这个」。"],
    innovation: ["问什么是学出来的：觉的追问标签同时包含「问了推荐就对」和「这单多半要升级、这是研发必问的信息」。", "概率经过校准，阈值按「漏问与多问的代价」来定，不靠提示词里写「缺信息就追问」。"],
    data: [["49% → 91%", "应升级需求的关键信息完整率", "docs/reports/distortion_300/"], ["1.32 vs 0.80", "应升级会话里 Jue-K 与规则的平均追问次数", "同上"], ["0.043 vs 0.297", "追问概率校准误差 ECE（Jue-K vs 规则）", "docs/reports/jue_k/"]],
  },
  {
    title: "升级", layer: 1, who: "业务员小王的工作面 · 某印染厂 A",
    screen: (
      <>
        <div className="rounded-[10px] bg-fill px-3 py-2 text-[13px] leading-5">
          <p className="text-[11px] font-semibold text-ink-3">Jev 匹配（按业务员的 L1 权限检索）</p>
          锦纶氨纶 + 气流染色机 + 色花：现有产品都不合适，「都不合适」概率 100%
        </div>
        <Jue title="是否转产品经理 Agent？" score="规则 · 到点" why="最近一次匹配中「都不合适」概率 1.00，高于最好的候选产品 0.00；已了解 2 项信息"
             flow="主人：业务员的 Agent（起草升级说明）→ 签字人：业务员小王" />
        <Draft>客户需求：锦氨弹力布在气流缸（低浴比）染色时出现布面深浅不一（色花），上次使用的匀染剂经三次回修仍未改善。<br />尚缺信息：具体使用的染料类型/品牌、具体浴比数值及当前染色工艺温度曲线与 pH 等参数。</Draft>
        <Signed>业务员小王：升级。需求单带着客户原话进入产品经理 Agent 的队列</Signed>
      </>
    ),
    happened: "L1 推荐不了，觉提出「是否升级」，业务员的 Agent 起草升级说明，业务员签字。这张单从此带着客户原话往下走。",
    value: ["业务员不再说「我回去问问」，需求原话完整地到了下一层。", "人只做判断和签字，说明由 Agent 写好。"],
    innovation: ["系统里没有工作流引擎：「升级之后交给谁」不写在代码里，每一步都是觉提出、Agent 准备、人签字。", "Agent 只起草，生效永远是人；没有委托人的产品经理 Agent 没有任何生效工具。"],
    data: [["15", "个决策模板驱动全链路（推进类 + 异常类）", "config/templates/"], ["50 / 20", "模拟业务周里觉提出的问题 / 人签字次数", "docs/reports/catalog_stats.md"]],
  },
  {
    title: "先查现成、汇聚机会", layer: 2, who: "产品经理 Agent（由觉派单，只有 L2 权限）",
    screen: (
      <>
        <div className="rounded-[10px] bg-fill px-3 py-2 text-[13px] leading-5">
          <p className="text-[11px] font-semibold text-ink-3">检索「锦纶氨纶 气流染色机 匀染 色花」</p>
          命中说明书 3 份、历史案例 2 个；另有 23 条研发知识越权，<b className="font-semibold">只返回归属</b>（是哪位研发、哪一层的知识），不返回内容。结论：无现成产品。
        </div>
        <Say from="customer">锦氨布在气流机里染，颜色不匀，回修了好几次<span className="text-ink-3">　—— 第二位客户（某印染厂 B）</span></Say>
        <Jue title="同类需求反复出现且无产品可用，是否合并立项？" score="Jue-K 打分 · 超过阈值"
             why="1 天内 2 次升级，涉及 2 个客户，同主题成功推荐 0 次，平均「都不合适」概率 1.00" flow="主人：产品经理 Agent（判断是否同一件事）→ 签字人：研发刘工" />
        <Draft label="产品经理 Agent 起草">两单现象均为色花，材质均为锦纶氨纶，设备均为低浴比气流染色机，且均诉求减少回修、保护弹力面料，确认为同类场景需求。建议以最早的一单为主单合并，统一立项研发。</Draft>
        <Signed>研发刘工：合并（发现机会记 10 分）</Signed>
      </>
    ),
    happened: "产品经理 Agent 先查有没有现成产品；查不到时，觉发现第二位客户在说同一件事，提出「是否合并立项」。研发看到的是一个机会，而不是两张重复的单。",
    value: ["能复用就不立项；不能复用时，零散的抱怨被汇聚成一个值得立项的市场机会。", "产品经理不再在市场和研发之间来回转述，这部分由 Agent 承担。"],
    innovation: ["看不到内容，但知道谁懂：越权检索只返回归属，产品经理 Agent 知道该依据谁，却拿不到原文。", "「几位客户在说同一件事」这种流程图里没有的时刻，也由觉提出。"],
    data: [["0.953 vs 0.854", "机会汇聚的区分度 AUC（Jue-K vs 规则）", "docs/reports/jue_k/"], ["0 / 4", "模拟业务周困难负样本误报（常见规则告警 2 / 4）", "docs/reports/week/"]],
  },
  {
    title: "L2：产品需求 · 接单", layer: 2, who: "研发刘工的需求单 · 产品需求（L2）",
    screen: (
      <>
        <Item term="深一块浅一块" text="需要匀染类助剂，改善上染均匀性" quote="我们染完以后布面深一块浅一块" owner="产品经理老周" />
        <Item term="气流" text="需要在低浴比条件下仍能保持匀染效果的助剂" quote="锦氨弹力布，气流缸，浴比很低" owner="产品经理老周" />
        <Item term="弹力" text="弹力面料（含氨纶），需要兼顾锦纶匀染与氨纶保护" quote="锦氨弹力布" owner="产品经理老周" />
        <Item term="回修" text="需要一次成功率高、减少回修的匀染方案" quote="回修了三次 / 回修了好几次" owner="产品经理老周" />
        <Signed>研发刘工：接单 = 立项（被引用的知识给产品经理老周记分）</Signed>
      </>
    ),
    happened: "产品经理 Agent 把场景语言转成产品需求语言，每一句都标着客户原话和依据了谁的转化知识。研发接单就是立项，这是 L2 的生效点。",
    value: ["研发拿到的不是一句「要个匀染剂」，而是逐句可回查的产品需求。", "过去产品经理积累的转述经验仍记在本人名下，被引用照常记分。"],
    innovation: ["三层编译：场景语言 → 产品需求语言 → 化学语言，每层只用本层能看的知识；分级既是权限边界，也是转译边界。", "像编译器的 source map：每一行都能回到客户原话的那一句、知识的那一位主人。"],
    data: [["7 分", "这条需求里产品经理老周的知识被引用记分", "runs/demo_record/（录制运行的贡献账本）"]],
  },
  {
    title: "L3：化学要点 · 回问", layer: 3, who: "研发刘工的需求单 · 化学要点（L3）",
    screen: (
      <>
        <Item term="匀染" text="（模拟）对酸性染料有缓染作用、与染料竞争纤维染座的阴离子型组分" quote="布面深一块浅一块" owner="研发陈工" />
        <Item term="锦纶氨纶" text="（模拟）氨纶段对酸性染料亲和力低，需同时控制锦纶上染速率与氨纶沾色" quote="锦氨弹力布" owner="研发刘工" />
        <Jue title="转译需要确认客户的染浴 pH" score="91%（Jue-K，阈值 15%）" why="第 3 层转译中，该信息有 2 种取值会改变引用的转化知识，客户尚未说明"
             flow="主人：业务员的 Agent（起草话术）→ 业务员回头问客户" />
        <Say from="sales">方便问一下，您染色时的染浴 pH 大概控制在多少呢？研发同事评估工艺时需要参考这个参数。</Say>
        <Say from="customer">加点醋酸调的，pH五左右</Say>
        <Item term="弱酸性浴" text="（模拟）弱酸性浴中酸性染料对锦纶初染快，需配合随升温缓释酸的 pH 调节组分" quote="加点醋酸调的，pH五左右" owner="研发陈工" />
      </>
    ),
    happened: "研发 Agent 起草化学语言需求单，引用两位研发的转化知识。觉发现客户没说的染浴 pH 会改变转译，提出回问；业务员趁客户还在问到，答复回填需求单。",
    value: ["研发要的信息不用等退回，客户还在时就补上了。", "研发的 Agent 也能随时帮研发调取客户原话、检索案例与实验记录、一起分析需求。"],
    innovation: ["回问是跨层的：L3 的缺口由觉发现，交给 L1 的业务员去问，问法由业务员的 Agent 用场景语言起草。", "逐层编译不拼凑：两步各用本层的转化知识，不会把别的现象的知识错引进来。"],
    data: [["0.713 vs 0.500", "回问的区分度 AUC（Jue-K vs 规则）", "docs/reports/jue_k/"], ["11.1% → 0%", "错译率（一次性翻译 → 化言）", "docs/reports/distortion/"]],
  },
  {
    title: "研发修改 · 确认 · 沉淀", layer: 3, who: "研发刘工的需求单 · 待你签字",
    screen: (
      <>
        <Item term="低浴比" text="（模拟）低浴比下染液交换快、局部染料浓度高，需随升温缓释酸，使染浴 pH 由中性逐步降至弱酸性，控制酸性染料初染速率"
              edited="；气流缸里要随升温分段加酸，别一次加足" quote="浴比很低" owner="研发陈工" />
        <p className="text-[12px] text-ink-2">蓝色是研发刘工自己加的一句：Agent 起草，人只改、只签。</p>
        <Signed>研发刘工：化言已经为您辅助理解了客户的需求 —— 确认化学要点</Signed>
        <Jue title="是否沉淀研发修改的转化知识？" score="规则 · 到点" why="研发修改过、未被已有转化知识覆盖的条目 1 条" flow="主人：研发的 Agent（提炼）→ 签字人：研发刘工" />
        <Draft>「气流缸低浴比加酸」→ 在气流缸等超低浴比设备中需随升温分段阶梯加酸，避免一次加足导致局部初染过快。与研发陈工的「低浴比」相近，本条补充了实操要点。</Draft>
        <Signed>研发刘工：沉淀为自己名下的知识（+5 分）</Signed>
      </>
    ),
    happened: "研发在 Agent 起草的化学要点上补了一句经验，确认后，Agent 把这句修改提炼成一条新知识，研发审定后记在自己名下。",
    value: ["「窗户纸」第一次被写下来，而且写下来的人有回报。", "知识库不需要先治理：研发在真实需求里改过的转译，就是被校正过的标准知识。"],
    innovation: ["修改即沉淀、引用即版税：知识有主人，被引用、试样成功、产品发布都记在主人名下。", "这是对「权责不对等」这个组织问题的机制解：交出知识换来的是回报，不是被无偿取用。"],
    data: [["37 分", "这一条需求走完后研发刘工获得的积分（发现、引用、沉淀、试样、发布）", "runs/demo_record/（录制运行的贡献账本）"], ["5 分", "研发陈工的知识被引用记分", "同上"]],
  },
  {
    title: "试样 · 封存放出 · 发布", layer: 3, who: "研发刘工的需求单 · 发布审定",
    screen: (
      <>
        <p className="flex flex-wrap gap-1.5"><span className="tag tag-accent">试样通过 · HY-LV206</span><span className="tag tag-accent">客户评价：小样确认，深浅一致</span></p>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-[10px] bg-fill px-3 py-2 text-[12.5px] leading-[19px]">
            <p className="mb-1 text-[11px] font-semibold text-ink-3">放出（对外要点）</p>
            适用于锦纶氨纶弹力面料在气流染色机（低浴比 1:3–1:5）弱酸性浴条件下的酸性染料匀染，有效改善色花问题，一次成功率高，减少回修……
          </div>
          <div className="rounded-[10px] bg-[#1c1c1e] px-3 py-2 text-[12.5px] leading-[19px] text-white/85">
            <p className="mb-1 text-[11px] font-semibold text-white/50">封存（只有研发可见）· 4 项</p>
            缓染机理 · 可逆络合释放机理 · 组分配比与配方构成 · 阶梯加酸的控制诀窍
          </div>
        </div>
        <Draft label="产品经理 Agent 包装说明书">只用研发放出的对外要点写成；拿不到封存项，也看不到机理与配方。</Draft>
        <Signed>研发刘工：审定发布，新品 HY-LV206 上架到 L1</Signed>
      </>
    ),
    happened: "试样通过、业务员带回客户评价后，研发决定哪层窗户纸封存、哪些要点放出；产品经理 Agent 只用放出的要点包装成说明书，研发审定发布。",
    value: ["不懂化学的客户拿到的是产品和工艺，保护黏性和定价；懂化学、明确要求的客户可申请解密，由研发本人审批，配方永不对外。"],
    innovation: ["向下只有两个受控出口：研发审定的对外要点、研发本人审批的解密；其余 L3 内容没有任何路径流到下层。", "权限在数据层而不在提示词层：Agent 根本拿不到不该说的东西，挡得住提示注入。"],
    data: [["0", "L1 输出中的 L2 / L3 内容（由测试守住）", "tests/test_wp_a1.py、test_wp_t.py"], ["0.941 vs 0.500", "拼凑机密（换着角度套配方）的发现 AUC", "docs/reports/jue_k/"]],
  },
  {
    title: "回流：下一位客户", layer: 1, who: "业务员小李的工作面 · 某印染厂 C",
    screen: (
      <>
        <Say from="customer">锦氨布在气流缸里染，布面深一块浅一块</Say>
        <div className="rounded-[10px] bg-[rgba(10,108,223,.07)] px-3 py-2.5 text-[13px] leading-5">
          <p className="text-[11px] font-semibold text-accent">推荐 · Jev（OneJev）97%</p>
          <p className="mt-0.5 font-semibold">HY-LV206</p>
          <p className="text-ink-2">适用于锦纶氨纶弹力面料在气流染色机弱酸性浴条件下的匀染……（按客户画像披露「产品」版本）</p>
        </div>
        <p className="text-[12.5px] text-ink-2">没有升级、没有立项：业务员当场推荐。</p>
      </>
    ),
    happened: "新品说明书回到 L1 知识库。下一位客户说同样的问题，业务员在 L1 直接命中新品，不再升级。",
    value: ["一线解决率持续上升，研发专注真正的新问题。", "系统每走完一轮就多会一件事：这是飞轮。"],
    innovation: ["研发的结果经反向包装回流到 L1，整条链首尾相接。"],
    data: [["97%", "新品在 L1 的匹配概率（OneJev）", "runs/demo_record/"], ["端到端", "升级 → 沉淀 → 发布 → 同类需求在 L1 命中新品", "tests/test_wp_a3.py"]],
  },
  {
    title: "支线：说明书没写，案例里用过", layer: 2, who: "业务员小李 → 产品经理 Agent → 研发刘工",
    screen: (
      <>
        <Say from="customer">涤纶布整理完摸起来硬邦邦的</Say>
        <Jue title="该问加工工艺" score="74%（Jue-K）" why="工艺会改变候选产品" flow="业务员追问，客户答「浸染的」；现有产品都不合适，业务员签字升级" />
        <Draft label="产品经理 Agent 查到现成产品">历史案例里曾用 HY-SF520 改善涤纶浸染手感发硬（产品经理老周的案例）。说明书尚未列入涤纶，但小样已验证过，建议复用，待研发审定。</Draft>
        <Signed>研发刘工：采用（把「改善」改成「明显改善」）</Signed>
        <Say from="sales">您好，针对您涤纶布浸染整理后手感偏硬的问题，我们研发这边确认了现成产品「柔软剂 HY-SF520」……建议您先安排做个小样测试看下效果。</Say>
      </>
    ),
    happened: "另一个现象升级后，产品经理 Agent 在历史案例里找到「说明书没写、但小样用过」的现成产品，研发审定后，业务员的 Agent 起草回复转给客户。",
    value: ["能复用就不立项：从升级到回复客户只隔几分钟（业务时间），而不是一个研发周期。", "沉睡在案例里的用法被找回来，案例作者照常记分。"],
    innovation: ["先查后立项也是觉提出的决策（现成产品复用），不是写死的分支。"],
    data: [["1 次签字", "研发审定即可回复客户，无需立项", "runs/demo_record/"]],
  },
];

const FUTURE: [string, string, string][] = [
  ["企业 RAG", "站在 RAG 之上", "RAG 解决「找得到」，化言解决「找到之后」：谁能看、怎么转、依据了谁、该不该有人决定。全系统只有一个检索入口，接企业 RAG 只替换排序，权限、拦截记录、引用记分照常生效。企业 RAG 越强，化言越强。"],
  ["钉钉 / 飞书", "嵌进去，不换系统", "听记把对话转写进业务员工作面；觉的问题以互动卡片 / 待办推给负责人，签字就是卡片上的按钮；每个人的 Agent 以机器人身份在单聊里与本人协作。"],
  ["ELN · 私有化模型", "数据不出企业", "试样结果从 ELN 回流，触发客户评价、知识冲突等决策；大模型经 OpenAI 兼容网关，换私有化模型只改配置；觉在本地 CPU 推理。"],
  ["转化语料 · 流程图", "续上已有投入", "企业花钱做过的转化语料作为初始知识导入、记在原作者名下，之后在每次真实需求中被研发校正；企业自己的流程图直接写成决策目录。"],
  ["更多场景", "同一套发现层", "配方优化：这次试样失败该不该调整方向？换产清洗：下一批是否现在切换？缺料预警：是否启用替代原料并通知研发验证？加的是决策模板和训练数据，不是新系统。"],
  ["组织层面", "让知识在组织里流动", "研发之间按归属申请、本人审批的盲点互换；某类决定上 Agent 草稿长期被原样签字，就提请降为「Agent 处理、人事后抽查」；被忽略的问题与人自发的决定反哺决策目录；管理层看得到知识贡献账本。"],
];

const PATH = [["影子模式", "觉只提问不动作，零风险"], ["试点签字", "一个产品线启用签字与知识归属"], ["重训扩目录", "用真实处置数据重训 Jue-K"], ["扩场景", "同一发现层接入更多业务"]];

function Future() {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-[17px] font-semibold leading-6">未来展望</h2>
        <p className="mt-0.5 text-[13px] text-ink-2">当前 Demo 是架构与业务流程演示：网页工作面就是将来钉钉卡片和页面里的内容。下面是接入路径与代码接缝，不是已完成的功能。</p>
      </div>
      <div className="grid grid-cols-3 gap-4">
        {FUTURE.map(([k, title, text]) => (
          <div key={k} className="group flex flex-col gap-1 px-4 py-3.5">
            <span className="eyebrow">{k}</span>
            <p className="text-[14.5px] font-semibold">{title}</p>
            <p className="text-[12.5px] leading-[19px] text-ink-2">{text}</p>
          </div>
        ))}
      </div>
      <div className="group px-5 py-4">
        <p className="eyebrow mb-2.5">上线路径</p>
        <div className="grid grid-cols-4 gap-2">
          {PATH.map(([t, s], i) => (
            <div key={t} className="relative rounded-[10px] bg-fill px-3 py-2.5">
              <p className="text-[13px] font-semibold"><span className="num mr-1.5 text-accent">{i + 1}</span>{t}</p>
              <p className="mt-0.5 text-[12px] text-ink-2">{s}</p>
            </div>
          ))}
        </div>
      </div>
      <p className="text-center text-[15px] font-semibold leading-6">
        今天的 Agent 等着人给任务；化言让企业里「该处理什么」由一个可训练的发现层持续提出，<br />交给 Agent 起草、人来决定。它不替代人做决定，它让每一个该有人决定的时刻都不被错过。
      </p>
    </div>
  );
}

function Value({ c }: { c: Chapter }) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="eyebrow mb-1">这一步发生了什么</p>
        <p className="text-[14px] leading-[22px]">{c.happened}</p>
      </div>
      <div className="group px-4 py-3">
        <p className="eyebrow mb-1.5">业务价值</p>
        <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] leading-5">{c.value.map((v) => <li key={v}>{v}</li>)}</ul>
      </div>
      <div className="group px-4 py-3">
        <p className="eyebrow mb-1.5 !text-accent">创新点</p>
        <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] leading-5">{c.innovation.map((v) => <li key={v}>{v}</li>)}</ul>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {c.data.map(([num, label, src]) => (
          <div key={label} className="rounded-[10px] bg-[rgba(10,108,223,.06)] px-3 py-2.5">
            <p className="num text-[19px] font-semibold leading-6 text-accent">{num}</p>
            <p className="mt-0.5 text-[12px] leading-[17px]">{label}</p>
            <p className="mt-1 text-[10.5px] leading-[14px] text-ink-3">{src}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Story({ toDesk }: { toDesk: () => void }) {
  const total = CHAPTERS.length + 1;                       // 最后一章是未来展望
  const [i, setI] = useState(() => Number(new URLSearchParams(location.search).get("ch")) || 0);   // ?ch=N 直接打开第 N 章（讲解时用）
  const go = (n: number) => setI(Math.max(0, Math.min(total - 1, n)));
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") go(i + 1);
      if (e.key === "ArrowLeft") go(i - 1);
    };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  });
  const c = CHAPTERS[i];
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col gap-5 px-8 pb-16 pt-7">
      <PageHead title="演示工作面"
                subtitle="跟着一条真实录制的需求走一遍（大模型真实运行，数据为模拟）：左边是工作面上的画面，右边讲这一步的价值。键盘 ← → 翻页。"
                aside={<button className="btn btn-plain" onClick={toDesk}>去沉浸工作面亲手操作</button>} />
      <nav className="flex flex-wrap gap-1">
        {[...CHAPTERS.map((x) => x.title), "未来展望"].map((t, n) => (
          <button key={t} onClick={() => go(n)}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] transition-colors ${
                    n === i ? "bg-accent font-semibold text-white" : n < i ? "bg-[rgba(10,108,223,.09)] text-accent" : "bg-fill text-ink-2 hover:bg-[rgba(118,118,128,.18)]"}`}>
            <span className="num">{n}</span>{t}
          </button>
        ))}
      </nav>
      {c ? (
        <div key={i} className="anim-fade grid grid-cols-[minmax(0,7fr)_minmax(0,5fr)] items-start gap-6">
          <div className="flex flex-col gap-3">
            <LayerRail on={c.layer} />
            <Screen who={c.who}>{c.screen}</Screen>
          </div>
          <Value c={c} />
        </div>
      ) : <div key={i} className="anim-fade"><Future /></div>}
      <div className="flex items-center justify-between border-t border-sep pt-4">
        <button className="btn btn-plain" disabled={i === 0} onClick={() => go(i - 1)}>上一步</button>
        <span className="num text-[12px] text-ink-3">{i} / {total - 1}</span>
        {i < total - 1
          ? <button className="btn btn-primary" onClick={() => go(i + 1)}>下一步：{i + 1 < CHAPTERS.length ? CHAPTERS[i + 1].title : "未来展望"}</button>
          : <button className="btn btn-primary" onClick={toDesk}>去沉浸工作面亲手走一遍</button>}
      </div>
    </div>
  );
}
