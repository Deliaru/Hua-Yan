"""逐轮需求抽取：规则实现与单次结构化模型调用。"""
import json
import re
from pathlib import Path

from huayan.contracts import (ExtractedSlot, ExtractedTemperature, ExtractionResult, LLMRequest, Message,
                              NeedState, SlotFill, TemperatureFill, Tier)
from huayan.domain import detect_asked_slots, find_phenomenon, find_slot_values


_MODEL = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)+")
_CELSIUS = re.compile(r"(?<![\d.])(?P<lower>-?\d+(?:\.\d+)?)\s*(?P<initial_unit>℃|°\s*[Cc]|摄氏度|度)?\s*"
                      r"(?:[~～—–至到-]\s*(?P<upper>-?\d+(?:\.\d+)?)\s*)?"
                      r"(?P<unit>℃|°\s*[Cc]|摄氏度|度)(?!\s*/)")


def _temperature(turns, asking):
    """离线规则降级；线上由 LLMExtractor 一次理解温度与否定/纠正。"""
    turn = turns[-1]
    previous = next((t for t in reversed(turns[:-1]) if t.speaker != "customer"), None)
    context = "温" in turn.text or (previous is not None and "温" in previous.text)
    matches = [m for m in _CELSIUS.finditer(turn.text)
               if m["unit"] != "度" or m["initial_unit"] not in (None, "度")
               or (context and not re.search(r"(?:硬度|牢度|白度|浓度|粘度|酸度|碱度)\s*$", turn.text[:m.start()]))]
    valid = []
    for i, match in enumerate(matches):
        start = matches[i - 1].end() if i else 0
        prefix = re.split(r"[，,。；;]", turn.text[start:match.start()])[-1]
        # 引用资料的数值不是客户自己的实际工艺条件。
        if any(w in prefix for w in ("说明书", "资料", "报告")):
            continue
        lower = float(match["lower"])
        upper = float(match["upper"]) if match["upper"] is not None else lower
        if lower <= upper and not any(w in prefix for w in ("不是", "不在", "不超过", "低于", "高于", "小于", "大于")) \
                and not re.match(r"\s*(?:以上|以下)", turn.text[match.end():]):
            valid.append((match, lower, upper))
    unknown = [c for c in re.finditer(r"[^，,。；;]+", turn.text)
               if any(w in c.group() for w in ("不清楚", "不知道", "不确定", "没测过"))
               and not any(w in c.group() for w in ("说明书", "资料", "报告"))
               and ("温" in c.group() or _CELSIUS.search(c.group())
                    or re.fullmatch(r"\s*(?:我|实际|其实|这个)?(?:不清楚|不知道|不确定|没测过)[？！!?\s]*", c.group()))]
    if unknown:
        # 未知只能由明确补充的实际读数解除，不能靠后出现的数字解除。
        valid = [item for item in valid if item[0].start() >= unknown[-1].end()
                 and re.search(r"问过|测过|实测|确认|更正|改成|改为",
                               re.split(r"[，,。；;]", turn.text[:item[0].start()])[-1])]
    if valid and (len(valid) == 1 or any(w in turn.text[valid[-2][0].end():valid[-1][0].start()]
                                       for w in ("不对", "说错", "改成", "改为", "其实", "更正"))):
        match, lower, upper = valid[-1]
        return ExtractedTemperature(celsius=(lower, upper), status="filled", quote=match.group(), turn_n=turn.n)
    if matches or (any(w in turn.text for w in ("不清楚", "不知道", "不确定", "没测过"))
                   and ("温度" in turn.text or (previous is not None and "温度" in previous.text)
                        or "temperature_c" in asking)):
        return ExtractedTemperature(celsius=None, status="unknown", quote=turn.text, turn_n=turn.n)
    return None


def _named(text, products):
    """按编号认型号：已知型号以本层视图为准，不假设连字符、字母或数字的排列方式。"""
    return [p["id"] for p in products if re.search(
        rf"(?<![A-Za-z0-9_-]){re.escape(p['id'])}(?![A-Za-z0-9_-])", text, re.IGNORECASE)]


class RuleExtractor:
    name = "rule"

    def __init__(self, seeds):
        self.seeds = seeds

    def extract(self, turns, prev, products=(), asking=()):
        turn = turns[-1]
        profile = prev.profile.model_copy(deep=True)
        result = ExtractionResult(intent="need", phenomenon=prev.phenomenon,
            phenomenon_quote=prev.phenomenon_quote, profile=profile)
        if turn.speaker == "sales":
            result.asked_slots = detect_asked_slots(turn.text, self.seeds.slots)
            return result
        text = turn.text
        result.temperature = _temperature(turns, asking)
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
            asked = detect_asked_slots(previous.text, self.seeds.slots) if previous else []
            for slot in asked or list(asking):          # 没有问话时，答的是客户页上正显示的回问
                if slot not in {s.slot for s in result.slots}:
                    result.slots.append(ExtractedSlot(slot=slot, value=None, status="unknown",
                        confidence=0.7, quote=text, turn_n=turn.n))
        # 「成分」在说布料（面料用词或本轮抽到面料取值）时是需求，不算问机理
        about_fabric = "fiber" in {s.slot for s in result.slots} or any(
            word in text for word in ("面料", "布", "纱", "纤维", "料子", "材质"))
        # 以下词表只是离线降级（测试、无模型）；线上意图由大模型抽取给出（契约 ⑰′）
        if any(word in text for word in ("原理", "配方", "配比", "机理", "染座")) or ("成分" in text and not about_fabric):
            result.intent = "mechanism_request"
            profile.asked_mechanism = True
        elif any(word in text for word in ("报价", "价格", "采购", "下单", "送样", "寄样", "业务员", "人工")):
            result.intent = "commercial"
        elif any(word in text for word in ("是什么产品", "怎么用", "用法", "用量", "说明书")):
            result.intent = "product_question"
        elif "为什么" in text:
            result.intent = "cause_question"
        elif not phenomenon and not result.slots and any(w in text for w in ("你好", "谢谢", "再见")):
            result.intent = "smalltalk"
        result.product_refs = _named(text, products)
        # 型号按编号认；没点名型号（也没有认不出的型号）的问题默认指已推荐的产品
        if not result.product_refs and not _MODEL.search(text) and result.intent in (
                "product_question", "cause_question", "mechanism_request"):
            result.product_refs = [p["id"] for p in products if p.get("recommended")]
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

    def extract(self, turns, prev, products=(), asking=()):
        slots = {s.id: s for s in self.seeds.slots}
        data = {"products": [{"id": p["id"], "name": p["name"]} for p in products],
                "recommended_product_id": next((p["id"] for p in products if p.get("recommended")), None),"slots": [{"id": s.id, "label": s.label, "values": s.values} for s in self.seeds.slots],
                "categories": sorted({p.category for p in self.seeds.products}),
                "phenomena": [{"id": p.id, "label": p.label, "phrases": p.customer_phrases}
                              for p in self.seeds.phenomena],
                "previous": prev.model_dump(mode="json"),
                "turns": [{"n": t.n, "speaker": t.speaker, "text": t.text} for t in turns],
                # V9.3：研发的回问显示在客户自助页上，不在对话里；客户这句可能就是在答它
                "asking": [{"slot": s, "label": slots[s].label, "ask_text": slots[s].ask_text} for s in asking]}
        output, _ = self.gateway.structured(LLMRequest(tier=Tier.FAST, caller="agent:extract",
            temperature=0, max_tokens=4096, timeout_s=180,
            messages=[Message(role="system", content=self.prompt),
                Message(role="user", content=json.dumps(data, ensure_ascii=False) +
                    "\n请现在分析以上真实输入，返回 ExtractionResult 的 JSON 数据实例，不是 JSON Schema。"
                    "temperature 只能是本轮新增或改口后的一个对象或 null，不是历轮列表。"
                    "quote 必须逐字存在于所引客户发言，不得增添标点。只输出 JSON，不输出分析。")]), ExtractionResult)
        return output


def validate_extraction(result, seeds, turns, product_ids):
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
    temperature = result.temperature
    if temperature is not None:
        src = by_n.get(temperature.turn_n)
        valid = src is not None and src.speaker == "customer" and temperature.quote and temperature.quote in src.text
        valid = valid and ((temperature.status == "unknown" and temperature.celsius is None)
            or (temperature.status == "filled" and temperature.celsius is not None
                and temperature.celsius[0] <= temperature.celsius[1]))
        if not valid:
            result.temperature = None
    result.product_refs = list(dict.fromkeys(p for p in result.product_refs if p in product_ids))   # 只认本层视图里的编号
    if turns[-1].speaker != "sales":
        result.asked_slots = []
    return result


def apply_extraction(prev: NeedState, result: ExtractionResult, turns) -> NeedState:
    need = prev.model_copy(deep=True)
    if result.phenomenon is not None:       # 大模型偶尔漏回已认出的现象（整月录制里客户答回问时遇到），沿用上一轮
        need.phenomenon, need.phenomenon_quote = result.phenomenon, result.phenomenon_quote
    by_n = {t.n: t for t in turns}
    for slot in result.slots:
        need.slots[slot.slot] = SlotFill(**slot.model_dump(exclude={"turn_n"}), turn_id=by_n[slot.turn_n].id)
    for slot in result.asked_slots:
        need.asked[slot] = need.asked.get(slot, 0) + 1
    if result.temperature is not None:
        need.temperature = TemperatureFill(**result.temperature.model_dump(exclude={"turn_n"}),
                                           turn_id=by_n[result.temperature.turn_n].id)
    need.profile, need.last_intent, need.turn_count = result.profile, result.intent, len(turns)
    return need
