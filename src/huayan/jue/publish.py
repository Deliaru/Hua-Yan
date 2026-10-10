"""契约 5.4：实时输出追问提示，定时输出发布到总线的问题。"""
from types import SimpleNamespace

from huayan.bus import QuestionBus
from huayan.clock import get_clock
from huayan.contracts import (AskHint, Evidence, JueObject, JueOutput, JueState, JueTemplate, NeedState, Product,
                              Question, Seeds)
from huayan.jue.state import realtime_state


def select_asks(out: JueOutput, state: JueState, seeds: Seeds, threshold: float, max_asks: int = 2) -> list[AskHint]:
    slots = {s.id: s for s in seeds.slots}
    best = {}
    for d in out.decisions:
        if d.family == "ask_slot" and d.p_need is not None and d.p_need >= threshold:
            best[d.object_id] = max(best.get(d.object_id, 0.0), d.p_need)
    hints = []
    for oid, p in sorted(best.items(), key=lambda kv: -kv[1])[:max_asks]:
        session_id, slot = oid.removeprefix("slot:").rsplit("/", 1)
        hints.append(AskHint(session_id=session_id, slot=slot, label=slots[slot].label,
                             ask_text=slots[slot].ask_text, p_need=p, scored_by=out.scored_by))
    return hints


def ask_hints(need: NeedState, seeds: Seeds, products: list[Product], model, threshold: float,
              max_asks: int = 2) -> tuple[list[AskHint], JueOutput]:
    state = realtime_state(need, seeds, products, get_clock().now())
    out = model.propose(state)
    return select_asks(out, state, seeds, threshold, max_asks), out


def _summary(family: str, a: dict) -> str:
    if family == "opportunity":
        return (f"{a['days_active']} 天内 {a['n_escalations']} 次升级，涉及 {a['n_customers']} 个客户，"
                f"同主题成功推荐 {a['n_matched']} 次，平均「都不合适」概率 {a['mean_p_none']:.2f}")
    if family == "knowledge_conflict":
        claim = "声称适用" if a["claimed"] else "未限定"
        return (f"说明书对 {a['product_id']} 在 {a['slot']}={a['value']} 上{claim}；{a['n_trials']} 次试样失败 {a['n_fail']} 次，"
                f"其中 {a['n_fail_product']} 次原因为产品本身")
    return (f"检索 {a['n_queries']} 次，被拦截的高层级命中 {a['n_blocked']} 条，"
            f"最集中的产品占 {a['blocked_top_share']:.0%}，涉及 {a['n_distinct_products']} 个产品")


def _label(obj: JueObject, seeds: Seeds | None) -> str:
    """给人看的对象名；没有种子时用 object_id。"""
    if seeds is None:
        return obj.object_id
    a = obj.attrs
    if obj.object_type == "theme":
        phen = next(p for p in seeds.phenomena if p.id == a["phenomenon"])
        known = dict(kv.split("=") for kv in obj.object_id.split("|")[1].split(",") if kv)
        return " + ".join(known[s] for s in phen.required_slots if s in known) + f"的{phen.label}"
    if obj.object_type == "knowledge":
        return f"{a['product_id']} × {a['value']}"
    actor = obj.object_id.removeprefix("actor:")
    return next((f"{x.name}（{x.id}）" for x in seeds.actors if x.id == actor), actor)


def publish(out: JueOutput, state: JueState, templates: dict[str, JueTemplate], bus: QuestionBus, threshold: float,
            *, seeds: Seeds | None = None, refs: dict[str, dict[str, list[str]]] | None = None) -> list[Question]:
    """seeds 用于给人看的标题与知识冲突的 owner_id（产品归属研发）；refs 来自 collect_scheduled，用于证据与会话引用。"""
    owners = {p.id: p.owner for p in seeds.products} if seeds else {}
    existing = {q.id for q in bus.list(status=None)}
    published = []
    for d in out.decisions:
        if d.family == "ask_slot" or d.p_need is None or d.p_need < threshold:
            continue
        t, obj = templates[d.template_id], state.objects[d.object_id]
        ref = (refs or {}).get(d.object_id, {"event_ids": [], "session_ids": []})
        q_refs = {"session_ids": ",".join(ref["session_ids"])} if ref["session_ids"] else {}
        owner_id = None
        if d.family == "knowledge_conflict":
            q_refs["product_id"] = obj.attrs["product_id"]
            owner_id = owners.get(obj.attrs["product_id"])
        elif d.family == "leak_risk":
            q_refs["actor_id"] = d.object_id.removeprefix("actor:")
        q = bus.publish(Question(
            id="", family=d.family, title=t.title.format(object=_label(obj, seeds), attrs=SimpleNamespace(**obj.attrs)), object_id=d.object_id, owner_role=t.owner_role,
            owner_id=owner_id, p_need=d.p_need, scored_by=out.scored_by, discoverer="jue_proto",
            evidence=[Evidence(summary=_summary(d.family, obj.attrs), event_ids=ref["event_ids"])],
            refs=q_refs, bounty_points=t.bounty_points, dedup_key=f"{d.family}:{d.object_id}", created_at=out.at))
        if q.id and q.id not in existing:   # 合并进已有问题或被抑制的不算新发布
            published.append(q)
    return published
