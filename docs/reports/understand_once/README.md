# 理解只在一处：抽取离线核对（2026-10-22，待人审标注）

- 原话：45 句客户发言连同前 4 轮，取自 `data/enterprise/runs/` 下 Q9.4 业务月与冒烟的事件日志（模拟客户，模拟数据）。
- 期望的 `intent` 与 `product_refs` 由 Claude 人工标注，**待人审**；「推荐」列是该会话当时已推荐的产品。
- 「新抽取」为 `LLMExtractor`（试用接口 deepseek-v4.1-flash，temperature 0）按新提示词的第二轮结果；「规则降级」为 `RuleExtractor`；「旧线上」为当时运行里大模型抽取记下的意图（旧取值只有 need / product_question / mechanism_request / smalltalk）。
- 「对」列两个符号依次为 intent、product_refs。
- 第一轮（提示词初版）：intent 41/45、product_refs 34/45。之后改了两处：把已推荐产品单独作为 `recommended_product_id` 传入并写明指代规则；加了「回答追问是 need」「要过人之后的应答是 smalltalk」两条边界。这两处改动是看着这 45 句改的，第二轮不是独立样本；要拿诚实的数字须另取一批没看过的原话。
- 存疑的标注：#4（前一句已经要过业务员，模型判 smalltalk 也说得通）、#34（前文在谈防黄变剂，模型给 HY-AY901 也说得通）、#22 #23（「跟这个有关系吗」问的是产品对不对路还是毛病原因）。

| # | 原话 | 推荐 | 期望 intent | 期望 refs | 新抽取 | 对 | 规则降级 | 对 | 旧线上 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 那先给我寄点样试试吧，顺便报个价。 | HY-FX301 | commercial | HY-FX301 | commercial HY-FX301 | ✓✓ | need — | ✗✗ | need |
| 2 | 这个思路对得上，硬水里的金属离子跟活性料结合就容易出色点。我先要个报价，顺便能不能送点样来试试？ | HY-CH310 | commercial | HY-CH310 | commercial HY-CH310 | ✓✓ | commercial — | ✓✗ | need |
| 3 | 行，那就按0.5附近先试。寄样和报价的事麻烦让业务员直接联系我，我们细谈下经轴缸这边的加法。 | HY-CH310 | commercial | HY-CH310 | commercial HY-CH310 | ✓✓ | commercial — | ✓✗ | need |
| 4 | 行，那让业务员联系我吧，我把水质和工艺情况跟他讲一下。 | HY-CH310 | commercial | — | smalltalk — | ✗✓ | commercial — | ✓✓ | smalltalk |
| 5 | 行，那这样，你帮我安排一下寄个小样过来，另外让业务员联系我一下，APEO这块我得跟他确认清楚，我们出口卡得严。 | TF-231A | commercial | TF-231A | commercial TF-231A | ✓✓ | commercial — | ✓✗ | smalltalk |
| 6 | 这些参数、成分、配法光靠页面问答也问不清楚了，你直接安排个技术的人联系我吧，我们细聊。 | HY-FX301 | commercial | HY-FX301 | commercial HY-FX301 | ✓✓ | mechanism_request HY-FX301 | ✗✓ | mechanism_request |
| 7 | 行，原理说不清我这边不好调工艺。麻烦安排个业务员或者技术联系我，我想细聊一下。 | TF-288B | commercial | TF-288B | commercial TF-288B | ✓✓ | mechanism_request TF-288B | ✗✓ | mechanism_request |
| 8 | 我们用的是市政供水，普通自来水。这个螯合分散剂听着对路，先说说价格，能安排点样吗？ | HY-CH310 | commercial | HY-CH310 | commercial HY-CH310 | ✓✓ | commercial — | ✓✗ | need |
| 9 | 行，那你先按1到2克每升给我报个价，再寄点小样过来。我们这批是出口单，不能含APEO，环保这块你们能出证明吧？ | HY-AC601 | commercial | HY-AC601 | commercial HY-AC601 | ✓✓ | need — | ✗✗ | need |
| 10 | 我不是要你们配方，我是问这个产品对我这种分散料的掉色到底有没有用。你直接说能管还是不能管就行。 | HY-FX301 | product_question | HY-FX301 | product_question HY-FX301 | ✓✓ | mechanism_request HY-FX301 | ✗✓ | mechanism_request |
| 11 | 这个固色剂不含甲醛，那是含不含APEO？我们出口的，环保这块卡得严。 | HY-FX301 | product_question | HY-FX301 | product_question HY-FX301 | ✓✓ | need — | ✗✗ | product_question |
| 12 | 我说的是你刚推的那个 HY-SF520，别老让我报型号，你就告诉我纯涤的布能不能用。 | — | product_question | HY-SF520 | product_question HY-SF520 | ✓✓ | need HY-SF520 | ✗✓ | product_question |
| 13 | 那行，机理我也说不明白。不过我们这缸子泡沫特别敏感，起泡就不能用。你推荐的那个润滑剂泡沫多不多？ | HY-AC601 | product_question | HY-AC601 | product_question HY-AC601 | ✓✓ | mechanism_request HY-AC601 | ✗✓ | product_question |
| 14 | 这产品是前处理用的吧？我这布是还原染料在缸里染的，用它管用吗？ | HY-PT801 | product_question | HY-PT801 | product_question HY-PT801 | ✓✓ | need — | ✗✗ | product_question |
| 15 | 这支听着对路。不过我这边温度不能太高，想省蒸汽、低温染，这产品低温下效果还行吗？ | HY-LV101 | product_question | HY-LV101 | product_question HY-LV101 | ✓✓ | need — | ✗✗ | product_question |
| 16 | 你这个是给酸性染料用的吧？我们用的是分散染料，印花工艺，能对得上吗？ | HY-LV205 | product_question | HY-LV205 | product_question HY-LV205 | ✓✓ | need — | ✗✗ | product_question |
| 17 | 行，那这个APEO的事你让懂的人跟我确认下吧，报告能给我最好。另外你说的这个用法，我们是连续轧染的，不是一缸一缸浸的，这 | HY-FX301 | product_question | HY-FX301 | product_question HY-FX301 | ✓✓ | product_question HY-FX301 | ✓✓ | product_question |
| 18 | 这个能管用吗？我这布是缸里染的，用的活性料，主要是摸起来太糙了。 | HY-SF501 | product_question | HY-SF501 | product_question HY-SF501 | ✓✓ | need — | ✗✗ | need |
| 19 | 黄纸板倒是没特意用，就普通包装。你说的那个防黄变的，大概怎么用、加多少，你尽快给我个准信儿。 | HY-AY901 | product_question | HY-AY901 | product_question HY-AY901 | ✓✓ | product_question HY-AY901 | ✓✓ | mechanism_request |
| 20 | 这个保护剂是碱性和双氧水一起用的吧？我这是气流缸，不是前处理，是染色环节的事，能管用吗？ | HY-PT801 | product_question | HY-PT801 | product_question HY-PT801 | ✓✓ | need — | ✗✗ | mechanism_request |
| 21 | 这个思路对得上，我要的就是针对金属离子和分散稳定这块的东西。不过我这用的是市政供水，硬度应该不算高，先按0.5走还是直接 | HY-CH310 | product_question | HY-CH310 | product_question HY-CH310 | ✓✓ | need — | ✗✗ | need |
| 22 | 你这个是柔软剂？我不是要手感，我是问布放久了发黄的事，跟这个有关系吗？ | HY-SF501 | product_question | HY-SF501 | cause_question — | ✗✗ | need — | ✗✗ | product_question |
| 23 | 那我这布是分散染料印花的，经轴缸染的，跟这个有关系吗？ | HY-AY901 | product_question | HY-AY901 | cause_question — | ✗✗ | need — | ✗✗ | mechanism_request |
| 24 | 行，那我先拿点试试。不过我想问下，是不是我染的时候哪个环节出问题了？ | HY-DS410 | cause_question | — | cause_question — | ✓✓ | need — | ✗✓ | mechanism_request |
| 25 | 哦这个可以先试试。不过我想问下，我们这掉色是不是还有别的原因？我怕光加固色剂治标不治本。 | HY-FX301 | cause_question | — | cause_question — | ✓✓ | need — | ✗✓ | mechanism_request |
| 26 | 这个主要是防染料凝聚的吧？我这个斑点到底是染料的事还是水的事，能确定吗？ | HY-DS410 | cause_question | HY-DS410 | cause_question HY-DS410 | ✓✓ | need — | ✗✗ | mechanism_request |
| 27 | 你先等等，我们这水是市政自来水，不算硬水吧？这色点是不是因为水里的金属离子引起的我还真说不准。你还有没有别的方向可以排查 | HY-CH310 | cause_question | — | need — | ✗✓ | need — | ✗✓ | need |
| 28 | 哎对了，染的时候是不是跟pH有关系？我这缸里加了纯碱，碱放得比较多的。 | HY-SF501 | cause_question | — | cause_question — | ✓✓ | need — | ✗✓ | mechanism_request |
| 29 | 这个看着对路。你直接讲讲它的作用原理吧，我们好自己调升温工艺。 | HY-LV101 | mechanism_request | HY-LV101 | mechanism_request HY-LV101 | ✓✓ | mechanism_request HY-LV101 | ✓✓ | mechanism_request |
| 30 | 作用机理大致讲讲总可以吧，我又不是要你们的配方。就说说螯合和分散两步是怎么配合的，我们好判断加多少、什么时候加。 | HY-CH310 | mechanism_request | HY-CH310 | mechanism_request HY-CH310 | ✓✓ | mechanism_request HY-CH310 | ✓✓ | mechanism_request |
| 31 | 那它这个润滑的东西，是蜡类的还是硅类的？我就是想搞清楚它大概是哪一类起作用的。 | HY-AC601 | mechanism_request | HY-AC601 | mechanism_request HY-AC601 | ✓✓ | need — | ✗✗ | mechanism_request |
| 32 | 这个301听上去方向对，它是靠什么和染料结合的？阳离子型的吗，靠电荷吸附把染料封在纤维上？ | HY-FX301 | mechanism_request | HY-FX301 | mechanism_request HY-FX301 | ✓✓ | need — | ✗✗ | mechanism_request |
| 33 | 这个看着对路。你直接讲讲HY-LV205的匀染原理，是缓染为主还是靠什么？我们想自己调工艺。 | HY-LV205 | mechanism_request | HY-LV205 | mechanism_request HY-LV205 | ✓✓ | mechanism_request HY-LV205 | ✓✓ | mechanism_request |
| 34 | 对，浅色的。原理你先给我讲清楚，寄样我这边可以安排。 | HY-SF501 | mechanism_request | HY-SF501 | mechanism_request HY-AY901 | ✓✗ | mechanism_request HY-SF501 | ✓✓ | mechanism_request |
| 35 | 这个看着对路。不过我们是在卷染上做，你直接讲讲它是什么机理固色的，我们好自己调工艺。 | HY-FX350 | mechanism_request | HY-FX350 | mechanism_request HY-FX350 | ✓✓ | mechanism_request HY-FX350 | ✓✓ | mechanism_request |
| 36 | 你好，我这边染出来的布手感不对，摸起来硬邦邦的，有点板硬，想问问怎么回事。 | — | need | — | need — | ✓✓ | need — | ✓✓ | need |
| 37 | 我这批锦纶氨纶的布，染好放了一阵子就发黄了，白的变黄，怎么回事啊？ | — | need | — | need — | ✓✓ | need — | ✓✓ | need |
| 38 | 我那批锦纶氨纶的印花布，放了一阵子白的就发黄了，怎么回事啊？ | — | need | — | need — | ✓✓ | need — | ✓✓ | mechanism_request |
| 39 | 用的就是普通自来水，市政供水那种，硬不硬我不太清楚。 | — | need | — | need — | ✓✓ | need — | ✓✓ | mechanism_request |
| 40 | 加了纯碱，碱放得挺多的，pH十以上了。 | — | need | — | need — | ✓✓ | need — | ✓✓ | mechanism_request |
| 41 | 这缸是纯涤的，锦氨是另外的单子。匀染剂啥离子型的我还真没细看过，回头上机我瞅一眼告诉你。对了，助剂不能含APEO啊，我们 | HY-AC601 | need | — | need HY-AC601 | ✓✗ | need — | ✓✓ | need |
| 42 | 是这样，我们染出来的白布白度不行，看着发灰不够白，我估计是漂白时双氧水分解太快或者无效分解了，想找你们要荧光增白剂这类东 | — | need | — | need — | ✓✓ | need — | ✓✓ | need |
| 43 | 行，那就等你消息。对了，我们温度不能太高，想省蒸汽低温染的，配方别弄得太狠。 | HY-CH310 | need | — | need — | ✓✓ | mechanism_request HY-CH310 | ✗✗ | need |
| 44 | 好嘞，那就麻烦你了，等你电话。 | HY-SF501 | smalltalk | — | smalltalk — | ✓✓ | need — | ✗✓ | smalltalk |
| 45 | 好的，等他电话。 | HY-PT801 | smalltalk | — | smalltalk — | ✓✓ | need — | ✗✓ | smalltalk |

llm: intent 41/45，product_refs 41/45

rule: intent 19/45，product_refs 26/45
