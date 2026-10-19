"""契约 5.4：Jue-K。按「家族 × 判断层」每格一个梯度提升模型加 isotonic 校准（huayan.jue.train）；
没有模型的格（没有样本，或评估输给规则而没有保存）由模板 rule_score 打分，逐条标 scored_by。
与原型共用模板枚举、前置条件和紧急度。只做本地推理，不调用网关与任何模型服务。"""
import json
import pickle
import time
from pathlib import Path

from huayan.contracts import JueOutput, JueState, Meter
from huayan.jue.expr import evaluate
from huayan.jue.features import build, vectorize
from huayan.jue.proto import decisions, judge_level, mode_templates, rule_score


class JueK:
    name = "jue_k"

    def __init__(self, model_dir: str | Path, templates_dir: str | Path, mode: str = "realtime",
                 meter: Meter | None = None):
        model_dir = Path(model_dir)
        with (model_dir / "model.pkl").open("rb") as stream:
            artifact = pickle.load(stream)
        self.models = artifact["models"]
        self.columns = json.loads((model_dir / "features.json").read_text(encoding="utf-8"))["columns"]
        self.templates = mode_templates(templates_dir, mode)
        self.mode, self.meter = mode, meter

    def propose(self, state: JueState) -> JueOutput:
        start = time.perf_counter()
        pairs = [(t, o) for t in self.templates.values() for o in state.objects.values() if o.object_type == t.object_type]
        passed = [(t, o) for t, o in pairs if evaluate(t.precondition, o.attrs, boolean=True)]
        scores = {(t.id, o.object_id): rule_score(t, o) for t, o in passed}
        sources = {key: "rule" for key in scores}
        for t, o in passed:
            cell = f"{t.family}|L{judge_level(t, o)}"
            if cell in self.models:
                classifier, calibrator = self.models[cell]
                raw = classifier.predict_proba(vectorize([build(o, t.family)], self.columns[cell]))[:, 1]
                scores[(t.id, o.object_id)] = float(calibrator.predict(raw)[0])
                sources[(t.id, o.object_id)] = "jue_k"
        if self.meter is not None:
            self.meter.record(caller="jue:jue_k", kind="jue", impl="jue_k", n_objects=len(state.objects),
                              latency_ms=(time.perf_counter() - start) * 1000)
        return JueOutput(at=state.at, mode=state.mode, model="jue_k", scored_by="jue_k",
                         decisions=decisions(pairs, scores, sources))
