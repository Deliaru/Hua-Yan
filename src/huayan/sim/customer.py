"""契约 ⑨：模拟客户。模板模式只用种子中的口语说法（零成本）；大模型模式 caller 为 sim:customer。"""
import random
import re
from pathlib import Path

from huayan.contracts import LLMRequest, Message, NeedCard, Seeds, Tier
from huayan.domain import detect_asked_slots

PROMPT = Path(__file__).parents[3] / "prompts" / "sim_customer.md"
_OPENERS = ["你好，我们这边{p}", "最近{p}", "客户投诉说{p}", "这批货{p}"]
# 懂化学的客户开口就带着判断、直接要某一类助剂；想了解原理的，收到推荐后像同行一样请对方讲明白，不是考问
_SAVVY_OPENERS = ["{p}，我判断是{d}，想找一款{c}，有合适的吗？", "{p}，应该是{d}，你们有没有{c}？"]
_PLAIN_ASK = ["行，那你直接跟我说它是怎么起作用的，我们自己也懂一点，好对着调工艺。",
              "可以，作用原理直接讲明白就行，不用包装，我们自己会判断用量。"]


class SimCustomer:
    def __init__(self, card: NeedCard, seeds: Seeds, rng: random.Random, gateway=None, persona: str = "",
                 channel: str = ""):
        # persona、channel：v8 业务月的客户人设与沟通渠道；只在给出时追加到系统提示词末尾，原有录制缓存的请求不变
        self.card, self.seeds, self.rng, self.gateway, self.persona = card, seeds, rng, gateway, persona
        self.channel = channel
        self.slots = {s.id: s for s in seeds.slots}
        self.phen = next(p for p in seeds.phenomena if p.id == card.phenomenon)
        self.history: list[Message] = []
        self.asked_mechanism = False
        # 懂化学的客户自己的判断（种子中该现象原因说明的第一句）与据此想要的助剂品类（该现象下第一个产品的品类）
        self.diagnosis = re.split("[，；。]", self.phen.causes.removeprefix("（模拟）"))[0]
        self.category = min((p for p in seeds.products if card.phenomenon in p.solves), key=lambda p: p.id).category

    def _phrase(self, slot: str) -> str:
        return self.rng.choice(self.slots[slot].customer_phrases[self.card.slots[slot]])

    def opening(self, cue: str = "（你刚和业务员接通，请用一两句话说出你遇到的问题。）") -> str:
        if self.gateway is not None:
            return self._llm(cue)
        parts = [self.rng.choice(_OPENERS).format(p=self.rng.choice(self.phen.customer_phrases))]
        parts += [self._phrase(s) for s in self.card.opening_slots]
        if self.card.chem_savvy:
            return self.rng.choice(_SAVVY_OPENERS).format(p="，".join(parts), d=self.diagnosis, c=self.category)
        return "，".join(parts) + "，有什么办法吗？"

    def reply(self, sales_text: str) -> str:
        if self.gateway is not None:
            return self._llm(sales_text)
        # 先认推荐：说明书里常带「染料」「染色机」等字样，不能当成追问
        if "推荐" in sales_text or any(p.id in sales_text for p in self.seeds.products):
            if self.card.wants_mechanism and not self.asked_mechanism:
                self.asked_mechanism = True
                return self.rng.choice(_PLAIN_ASK)
            return "好的，明白了。"
        asked = detect_asked_slots(sales_text, self.seeds.slots)
        if asked:
            return "，".join("这个不太清楚" if s in self.card.unknown_slots else self._phrase(s) for s in asked) + "。"
        return "嗯，你说。"

    def _savvy_text(self) -> str:
        if not self.card.chem_savvy:
            return "不懂化学：只描述看到的现象，要的是解决办法，不说化学术语。"
        text = (f"懂化学：开场就用化学语言说出你对原因的判断（{self.diagnosis}），并直接要一类助剂（{self.category}）。"
                "你不是来考问或刁难业务员的，只是说话直接。")
        if self.card.wants_mechanism:
            text += "收到推荐后，像同行一样请对方直接讲清楚作用原理，方便你们自己调工艺。"
        return text

    def _llm(self, sales_text: str) -> str:
        if not self.history:
            facts = "\n".join(f"- {self.slots[s].label}：" + ("你也说不清" if s in self.card.unknown_slots else
                              f"{v}（你会这样说：{'、'.join(self.slots[s].customer_phrases[v])}）")
                              for s, v in self.card.slots.items())
            system = PROMPT.read_text(encoding="utf-8").format(
                phenomenon="、".join(self.phen.customer_phrases), facts=facts,
                opening="、".join(self.slots[s].label for s in self.card.opening_slots) or "无",
                savvy=self._savvy_text())
            if self.persona:
                system += "\n你的性格：" + self.persona
            if self.channel:
                system += "\n" + self.channel
            self.history.append(Message(role="system", content=system))
        self.history.append(Message(role="user", content=sales_text))
        resp = self.gateway.complete(LLMRequest(tier=Tier.FAST, caller="sim:customer", messages=self.history,
                                                temperature=0.7, max_tokens=200))
        self.history.append(Message(role="assistant", content=resp.content or ""))
        return resp.content or ""
