"""契约 5.4：Jue-K。一个梯度提升模型覆盖五类决策，按 family 分别做 isotonic 校准；与原型共用模板枚举、前置条件和紧急度。
只做本地推理，不调用网关与任何模型服务。"""
import json
import pickle
import time
from pathlib import Path

from huayan.contracts import JueOutput, JueState, Meter, ScoredDecision
from huayan.jue.expr import evaluate
from huayan.jue.features import build, vectorize
from huayan.jue.proto import load_templates, urgency


class JueK:
    name = "jue_k"

    def __init__(self, model_dir: str | Path, templates_dir: str | Path, mode: str = "realtime",
                 meter: Meter | None = None):
        model_dir = Path(model_dir)
        with (model_dir / "model.pkl").open("rb") as stream:
            artifact = pickle.load(stream)
        self.classifier, self.calibrators = artifact["classifier"], artifact["calibrators"]
        self.columns = json.loads((model_dir / "features.json").read_text(encoding="utf-8"))["columns"]
        self.templates = {k: t for k, t in load_templates(templates_dir).items()
                          if (t.object_type == "slot") == (mode == "realtime")}
        self.mode, self.meter = mode, meter

    def propose(self, state: JueState) -> JueOutput:
        start = time.perf_counter()
        pairs = [(t, o) for t in self.templates.values() for o in state.objects.values() if o.object_type == t.object_type]
        passed = [(t, o) for t, o in pairs if evaluate(t.precondition, o.attrs, boolean=True)]
        p = {}
        if passed:
            raw = self.classifier.predict_proba(vectorize([build(o, t.family) for t, o in passed], self.columns))[:, 1]
            for (t, o), r in zip(passed, raw):
                p[(t.id, o.object_id)] = float(self.calibrators[t.family].predict([r])[0])
        decisions = []
        for t, o in pairs:
            ok = (t.id, o.object_id) in p
            decisions.append(ScoredDecision(family=t.family, object_id=o.object_id, template_id=t.id,
                                            p_need=p.get((t.id, o.object_id)), urgency=urgency(t, o) if ok else None,
                                            precondition_passed=ok))
        if self.meter is not None:
            self.meter.record(caller="jue:jue_k", kind="jue", impl="jue_k", n_objects=len(state.objects),
                              latency_ms=(time.perf_counter() - start) * 1000)
        return JueOutput(at=state.at, mode=state.mode, model="jue_k", scored_by="jue_k", decisions=decisions)
