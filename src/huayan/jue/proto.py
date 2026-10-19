"""契约 5.4：觉原型。模板 × 对象枚举全部组合；原有三类定时决策在 OneJev 可用时批量打分，其余用规则分。不调用网关。"""
import time
from pathlib import Path
from types import SimpleNamespace

import yaml

from huayan.contracts import ROLE_LEVEL, JueObject, JueOutput, JueState, JueTemplate, Meter, S1Noul, ScoredDecision, System1Client
from huayan.jev.system1 import OneJevClient
from huayan.jue.expr import evaluate

SCHEDULED_TYPES = {"theme", "knowledge", "actor"}
ONEJEV_FAMILIES = {"opportunity", "knowledge_conflict", "leak_risk"}   # 其余决策的概率未校准，不交给 OneJev（REPLAN 4.7）


def load_templates(templates_dir: str | Path) -> dict[str, JueTemplate]:
    """模板目录即决策目录：每个 family 只能有一个模板；object_type、kind 由契约模型校验。"""
    paths = sorted(Path(templates_dir).glob("*.yaml"))
    templates = [JueTemplate.model_validate(yaml.safe_load(p.read_text(encoding="utf-8"))) for p in paths]
    families = [t.family for t in templates]
    if len(set(families)) != len(families):
        raise ValueError(f"{templates_dir} 中有重复的 family：{sorted(f for f in set(families) if families.count(f) > 1)}")
    return {t.id: t for t in templates}


def mode_templates(templates_dir: str | Path, mode: str) -> dict[str, JueTemplate]:
    return {k: t for k, t in load_templates(templates_dir).items()
            if (t.object_type in SCHEDULED_TYPES) == (mode == "scheduled")}


def render(text: str, obj: JueObject) -> str:
    return text.format(object=obj.object_id, attrs=SimpleNamespace(**obj.attrs))


def urgency(t: JueTemplate, o: JueObject) -> float:
    """模板的紧急度表达式（规则，不学习），截断到 [0,1]；为空时 1.0。原型与 Jue-K 共用。"""
    return 1.0 if t.urgency is None else min(1.0, max(0.0, float(evaluate(t.urgency, o.attrs))))


def rule_score(t: JueTemplate, o: JueObject) -> float:
    if t.rule_score is None:
        return 1.0
    score = evaluate(t.rule_score, o.attrs)
    if score is None:
        raise ValueError(f"模板 {t.id} 的 rule_score 无法在 {o.object_id} 上求值")
    return min(1.0, max(0.0, float(score)))


def judge_level(t: JueTemplate, o: JueObject) -> int:
    """这个决策代哪一层判断：对象带 judge_level 的用它（槽位对象），其余取模板签字人（提示类取主人）所在层。"""
    return int(o.attrs.get("judge_level", ROLE_LEVEL[t.signer_role or t.owner_role]))


def decisions(pairs, scores: dict, sources: dict) -> list[ScoredDecision]:
    """pairs 为全部「模板 × 对象」；scores / sources 只含前置条件通过的组合。原型与 Jue-K 共用。"""
    out = []
    for t, o in pairs:
        key = (t.id, o.object_id)
        ok = key in scores
        out.append(ScoredDecision(family=t.family, object_id=o.object_id, template_id=t.id, p_need=scores.get(key),
                                  urgency=urgency(t, o) if ok else None, precondition_passed=ok,
                                  scored_by=sources.get(key)))
    return out


class JueProto:
    name = "jue_proto"

    def __init__(self, templates_dir: str | Path, system1: System1Client | None = None,
                 mode: str = "realtime", meter: Meter | None = None):
        self.templates = mode_templates(templates_dir, mode)
        self.system1, self.mode, self.meter = system1, mode, meter

    def propose(self, state: JueState) -> JueOutput:
        start = time.perf_counter()
        pairs = [(t, o) for t in self.templates.values() for o in state.objects.values() if o.object_type == t.object_type]
        passed = [(t, o) for t, o in pairs if evaluate(t.precondition, o.attrs, boolean=True)]
        onejev = isinstance(self.system1, OneJevClient)
        by_onejev = [(t, o) for t, o in passed if onejev and t.family in ONEJEV_FAMILIES]
        scores = {(t.id, o.object_id): rule_score(t, o) for t, o in passed}
        sources = {key: "rule" for key in scores}
        if by_onejev:
            questions = {f"q{i}": S1Noul(text=render(t.worth_prompt, o)) for i, (t, o) in enumerate(by_onejev)}
            ids = list(dict.fromkeys(o.object_id for _, o in by_onejev))
            result = self.system1.ask(state.to_s1_state(ids), [], questions, caller="jue:proto")
            for i, (t, o) in enumerate(by_onejev):
                scores[(t.id, o.object_id)] = result.answers[f"q{i}"].probabilities["yes"]
                sources[(t.id, o.object_id)] = "onejev"
        if self.meter is not None:
            self.meter.record(caller="jue:proto", kind="jue", impl="onejev" if by_onejev else "rule",
                              n_objects=len(state.objects), latency_ms=(time.perf_counter() - start) * 1000)
        return JueOutput(at=state.at, mode=state.mode, model="jue_proto",
                         scored_by="onejev" if by_onejev else "rule", decisions=decisions(pairs, scores, sources))
