"""确定性规则桩（impl="mock"），按契约 4.1 的 caller 规则给概率；不是 OneJev 的替代证据。"""

from huayan.contracts import S1Answer, S1Choice, S1Noul, S1Result


def _peak(options, peak, mass=0.7):
    rest = (1 - mass) / (len(options) - 1)
    return {key: mass if key == peak else rest for key in options}


def _choice(state, options, caller):
    if caller == "jev:match":
        unknown = {c["id"]: len(c["unknown_slots"]) for c in state["candidates"]}
        weights = {key: 0.2 if key == "none" else 1 / (1 + unknown[key]) for key in options}
        total = sum(weights.values())
        return {key: w / total for key, w in weights.items()}
    if caller == "jev:disclose":
        profile = state["need"]["profile"]
        savvy = profile["chem_savvy"] and "full_mechanism" in options
        return _peak(options, "full_mechanism" if savvy else "product_usage")
    if caller == "jev:grounding":
        return _peak(options, "grounded" if state["hits"] else "none")
    return {key: 1 / len(options) for key in options}


class MockSystem1Client:
    def __init__(self, meter=None):
        self.meter = meter

    def ask(self, state, media, questions, caller) -> S1Result:
        answers = {}
        for key, question in questions.items():
            if isinstance(question, S1Noul):
                answers[key] = S1Answer(probabilities={"yes": 0.5, "no": 0.5})
            elif isinstance(question, S1Choice):
                answers[key] = S1Answer(probabilities=_choice(state, list(question.options), caller))
            else:
                levels = question.levels
                answers[key] = S1Answer(probabilities={level: 1 / len(levels) for level in levels}, expected=0.5)
        if self.meter is not None:
            self.meter.record(caller=caller, kind="s1", impl="mock", degraded=True,
                              n_questions=len(questions), latency_ms=0, cost=None, ok=True)
        return S1Result(answers=answers, latency_ms=0, impl="mock", degraded=True)
