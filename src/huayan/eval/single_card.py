"""WP-E2 单卡对照：从同一次失真对照（60 张卡）的逐轮轨迹里按固定规则选一张卡，组装演示第一幕与评测页的展示数据。
只读需求卡与这次运行的轨迹，不重新生成对话、不另跑该卡；单卡是讲故事的例子，底部三组统计才是证据。"""
import pandas as pd

from huayan.contracts import NeedCard
from huayan.eval.distortion import GROUPS

DEMO_PHENOMENON = "color_unlevel"           # 与演示主线相同
STATS_GROUPS = [GROUPS[0], GROUPS[1], GROUPS[3]]
RULE = f"现象为 {DEMO_PHENOMENON}、G2 一次性翻译被研发退回、G3 化言不被退回的卡中 id 最小的一张；没有则取第一张同现象卡"


def pick(cards: list[NeedCard], df: pd.DataFrame) -> tuple[NeedCard, dict]:
    """选卡规则写死，不挑；返回选中的卡与选卡说明（满足条件的张数）。"""
    returned = df.set_index(["card_id", "group"]).returned
    number = lambda c: int(c.id.rsplit(":", 1)[1])
    same = sorted((c for c in cards if c.phenomenon == DEMO_PHENOMENON), key=number)
    eligible = [c for c in same if returned[(c.id, GROUPS[1])] and not returned[(c.id, GROUPS[3])]]
    return (eligible or same)[0], {"rule": RULE, "n_cards": len(cards), "n_same_phenomenon": len(same),
                                   "n_eligible": len(eligible)}


def single_card(card: NeedCard, trace: dict, stats: dict) -> dict:
    """trace = run_distortion(trace=True) 中该卡的轨迹；stats = 这次运行 metrics.json 的 metrics 与选卡说明。
    truth 只列必问槽位中模拟客户知道的取值（必问槽位即追问轮次里的那几列）。"""
    required = trace["huayan"]["rounds"][0]["p_need"]
    return {"card_id": card.id, "simulated": True, "phenomenon": card.phenomenon,
            "truth": {s: card.slots[s] for s in required if s not in card.unknown_slots},
            "one_shot": trace["one_shot"], "huayan": trace["huayan"], "stats": stats}
