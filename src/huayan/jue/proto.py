"""契约 5.4：觉原型。模板 × 对象枚举全部组合；OneJev 可用时批量打分，否则用规则分。不调用网关。"""
import time
from pathlib import Path
from types import SimpleNamespace

import yaml

from huayan.contracts import JueObject, JueOutput, JueState, JueTemplate, Meter, S1Noul, ScoredDecision, System1Client
from huayan.jev.system1 import OneJevClient
from huayan.jue.expr import evaluate


def load_templates(templates_dir: str | Path) -> dict[str, JueTemplate]:
    paths = sorted(Path(templates_dir).glob("*.yaml"))
    templates = [JueTemplate.model_validate(yaml.safe_load(p.read_text(encoding="utf-8"))) for p in paths]
    return {t.id: t for t in templates}


def render(text: str, obj: JueObject) -> str:
    return text.format(object=obj.object_id, attrs=SimpleNamespace(**obj.attrs))


def urgency(t: JueTemplate, o: JueObject) -> float:
    """模板的紧急度表达式（规则，不学习），截断到 [0,1]；为空时 1.0。原型与 Jue-K 共用。"""
    return 1.0 if t.urgency is None else min(1.0, max(0.0, float(evaluate(t.urgency, o.attrs))))


class JueProto:
    name = "jue_proto"

    def __init__(self, templates_dir: str | Path, system1: System1Client | None = None,
                 mode: str = "realtime", meter: Meter | None = None):
        self.templates = {k: t for k, t in load_templates(templates_dir).items()
                          if (t.object_type == "slot") == (mode == "realtime")}
        self.system1, self.mode, self.meter = system1, mode, meter

    def propose(self, state: JueState) -> JueOutput:
        start = time.perf_counter()
        pairs = [(t, o) for t in self.templates.values() for o in state.objects.values() if o.object_type == t.object_type]
        passed = [(t, o) for t, o in pairs if evaluate(t.precondition, o.attrs, boolean=True)]
        onejev = isinstance(self.system1, OneJevClient)
        if onejev and passed:
            questions = {f"q{i}": S1Noul(text=render(t.worth_prompt, o)) for i, (t, o) in enumerate(passed)}
            ids = list(dict.fromkeys(o.object_id for _, o in passed))
            result = self.system1.ask(state.to_s1_state(ids), [], questions, caller="jue:proto")
            scores = [result.answers[f"q{i}"].probabilities["yes"] for i in range(len(passed))]
        else:
            scores = [self._rule(t, o) for t, o in passed]
        p = {(t.id, o.object_id): s for (t, o), s in zip(passed, scores)}
        decisions = []
        for t, o in pairs:
            ok = (t.id, o.object_id) in p
            decisions.append(ScoredDecision(family=t.family, object_id=o.object_id, template_id=t.id,
                                            p_need=p.get((t.id, o.object_id)), urgency=urgency(t, o) if ok else None,
                                            precondition_passed=ok))
        if self.meter is not None:
            self.meter.record(caller="jue:proto", kind="jue", impl="onejev" if onejev else "rule",
                              n_objects=len(state.objects), latency_ms=(time.perf_counter() - start) * 1000)
        return JueOutput(at=state.at, mode=state.mode, model="jue_proto",
                         scored_by="onejev" if onejev else "rule", decisions=decisions)

    @staticmethod
    def _rule(t: JueTemplate, o: JueObject) -> float:
        if t.rule_score is None:
            return 1.0
        score = evaluate(t.rule_score, o.attrs)
        if score is None:
            raise ValueError(f"模板 {t.id} 的 rule_score 无法在 {o.object_id} 上求值")
        return min(1.0, max(0.0, float(score)))
