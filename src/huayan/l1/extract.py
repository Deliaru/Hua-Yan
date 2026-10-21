"""逐轮需求抽取：规则实现与单次结构化模型调用。"""
import json
import re
from pathlib import Path

from huayan.contracts import (ExtractedSlot, ExtractionResult, LLMRequest, Message,
                              NeedState, SlotFill, Tier)
from huayan.domain import detect_asked_slots, find_phenomenon, find_slot_values


class RuleExtractor:
    name = "rule"

    def __init__(self, seeds):
        self.seeds = seeds

    def extract(self, turns, prev):
        turn = turns[-1]
        profile = prev.profile.model_copy(deep=True)
        result = ExtractionResult(intent="need", phenomenon=prev.phenomenon,
            phenomenon_quote=prev.phenomenon_quote, profile=profile)
        if turn.speaker == "sales":
            result.asked_slots = detect_asked_slots(turn.text, self.seeds.slots)
            return result
        text = turn.text
        phenomenon = find_phenomenon(text, self.seeds.phenomena)
        if phenomenon:
            result.phenomenon, result.phenomenon_quote = phenomenon
        values = find_slot_values(text, self.seeds.slots)
        # 数值 pH / 加酸到目标值是本轮的新条件，不能沿用上一轮的「中性」。
        ph_slot = next((s for s in self.seeds.slots if s.id == "bath_ph"), None)
        for match in re.finditer(r"(?:pH\s*(?:[=:：为是]|调到|控制在)?|加酸(?:调)?到)\s*"
                                 r"(\d+(?:\.\d+)?)(?![\d.%％])", text, re.IGNORECASE):
            ph = float(match.group(1))
            value = "强酸性" if ph < 4 else "弱酸性" if ph < 7 else "中性" if ph == 7 else "碱性"
            if ph_slot and 0 <= ph <= 14 and value in ph_slot.values:
                values["bath_ph"] = (value, match.group())
        for slot, (value, quote) in values.items():
            result.slots.append(ExtractedSlot(slot=slot, value=value, status="filled",
                confidence=0.7, quote=quote, turn_n=turn.n))
        if any(word in text for word in ("不清楚", "不知道", "不确定")):
            previous = next((t for t in reversed(turns[:-1]) if t.speaker != "customer"), None)   # 业务员或化言的问话
            if previous:
                for slot in detect_asked_slots(previous.text, self.seeds.slots):
                    if slot not in {s.slot for s in result.slots}:
                        result.slots.append(ExtractedSlot(slot=slot, value=None, status="unknown",
                            confidence=0.7, quote=text, turn_n=turn.n))
        # 「成分」在说布料（面料用词或本轮抽到面料取值）时是需求，不算问机理
        about_fabric = "fiber" in {s.slot for s in result.slots} or any(
            word in text for word in ("面料", "布", "纱", "纤维", "料子", "材质"))
        if any(word in text for word in ("原理", "为什么", "配方", "机理")) or ("成分" in text and not about_fabric):
            result.intent = "mechanism_request"
            profile.asked_mechanism = True
        elif any(word in text for word in ("是什么产品", "怎么用", "用法")):
            result.intent = "product_question"
        elif not phenomenon and not result.slots and any(w in text for w in ("你好", "谢谢", "再见")):
            result.intent = "smalltalk"
        # 懂化学的客户直接点名要某一类助剂（种子产品品类）；不懂化学的只说现象。
        compact = text.replace(" ", "").casefold()
        if any(p.category.replace(" ", "").casefold() in compact for p in self.seeds.products):
            profile.chem_savvy, profile.evidence_quote = True, text
        return result


class LLMExtractor:
    name = "llm"

    def __init__(self, seeds, gateway):
        self.seeds, self.gateway = seeds, gateway
        self.prompt = (Path(__file__).resolve().parents[3] / "prompts/extract.md").read_text(encoding="utf-8")

    def extract(self, turns, prev):
        data = {"slots": [{"id": s.id, "label": s.label, "values": s.values} for s in self.seeds.slots],
                "categories": sorted({p.category for p in self.seeds.products}),
                "phenomena": [{"id": p.id, "label": p.label, "phrases": p.customer_phrases}
                              for p in self.seeds.phenomena],
                "previous": prev.model_dump(mode="json"),
                "turns": [{"n": t.n, "speaker": t.speaker, "text": t.text} for t in turns]}
        output, _ = self.gateway.structured(LLMRequest(tier=Tier.FAST, caller="agent:extract",
            temperature=0, messages=[Message(role="system", content=self.prompt),
                Message(role="user", content=json.dumps(data, ensure_ascii=False))]), ExtractionResult)
        return output


def validate_extraction(result, seeds, turns):
    """枚举校验位于掌握种子定义的输入边界，保持 apply_extraction 的冻结签名。"""
    slots = {s.id: s for s in seeds.slots}
    by_n = {t.n: t for t in turns}
    result = result.model_copy(deep=True)
    # 大模型偶尔回现象的中文名而不是编号（试用接口实测），按名换回编号
    result.phenomenon = {p.label: p.id for p in seeds.phenomena}.get(result.phenomenon, result.phenomenon)
    if result.phenomenon is not None and result.phenomenon not in {p.id for p in seeds.phenomena}:
        raise ValueError("抽取返回未知现象")
    result.slots = [s for s in result.slots if s.slot in slots
                    and ((s.status == "unknown" and s.value is None)
                         or (s.status == "filled" and s.value in slots[s.slot].values))]
    # 槽位必须引用真实客户发言；引不上原话的不填（试用接口实测：大模型偶尔改写引文），与取值不合法同样处理
    result.slots = [s for s in result.slots if (src := by_n.get(s.turn_n)) is not None and src.speaker == "customer"
                    and s.quote and s.quote in src.text]
    result.asked_slots = [s for s in result.asked_slots if s in slots]
    if turns[-1].speaker != "sales":
        result.asked_slots = []
    return result


def apply_extraction(prev: NeedState, result: ExtractionResult, turns) -> NeedState:
    need = prev.model_copy(deep=True)
    need.phenomenon, need.phenomenon_quote = result.phenomenon, result.phenomenon_quote
    by_n = {t.n: t for t in turns}
    for slot in result.slots:
        need.slots[slot.slot] = SlotFill(**slot.model_dump(exclude={"turn_n"}), turn_id=by_n[slot.turn_n].id)
    for slot in result.asked_slots:
        need.asked[slot] = need.asked.get(slot, 0) + 1
    need.profile, need.last_intent, need.turn_count = result.profile, result.intent, len(turns)
    return need
