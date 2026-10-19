"""Jev 的三个业务问题；输入只含 L1 可见信息。"""
from huayan.contracts import CUSTOMER_VERSIONS, JevDecision, S1Choice


class Jev:
    def __init__(self, system1, match_threshold=0.5):
        self.system1, self.match_threshold = system1, match_threshold

    def _ask(self, name, state, text, options):
        result = self.system1.ask(state, [], {name: S1Choice(text=text, options=options)}, f"jev:{name}")
        probabilities = result.answers[name].probabilities
        choice = max(probabilities, key=probabilities.get)
        return JevDecision(question=name, probabilities=probabilities, choice=choice,
            confident=probabilities[choice] >= self.match_threshold and choice != "none", scored_by=result.impl)

    def match(self, need, candidates, products):
        if not candidates:
            return JevDecision(question="match", probabilities={"none": 1.0}, choice="none",
                               confident=False, scored_by="rule")
        state = {"need": need.model_dump(mode="json"), "candidates": [
            {"id": c.product_id, "name": products[c.product_id].name,
             "category": products[c.product_id].category, "situations": [s.model_dump() for s in products[c.product_id].situations],
             "unknown_slots": c.unknown_slots} for c in candidates]}
        return self._ask("match", state, "根据客户现象与已知条件，哪个产品最可能解决？都不合适选 none。",
                         {**{c.product_id: products[c.product_id].name for c in candidates}, "none": "都不合适"})

    def disclose(self, need, product_id, cap):
        allowed = CUSTOMER_VERSIONS[:CUSTOMER_VERSIONS.index(cap) + 1] if cap != "internal" else CUSTOMER_VERSIONS
        if len(allowed) == 1:
            return JevDecision(question="disclose", probabilities={allowed[0]: 1.0}, choice=allowed[0],
                               confident=True, scored_by="rule")
        return self._ask("disclose", {"need": need.model_dump(mode="json"), "product_id": product_id},
            "在权限允许范围内，根据客户画像选择披露版本。", {v: v for v in allowed})

    def grounding(self, answer, hits):
        return self._ask("grounding", {"answer": answer,
            "hits": [{"title": h.ku.title, "text": h.ku.text} for h in hits]},
            "回答是否得到这些知识支持？", {"grounded": "有依据", "partial": "部分有依据", "none": "无依据"})
