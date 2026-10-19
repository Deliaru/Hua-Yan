"""契约 5.4：实时输出追问提示，定时输出发布到总线的问题。"""
from types import SimpleNamespace

from huayan.bus import QuestionBus
from huayan.clock import get_clock
from huayan.contracts import (AskHint, Evidence, JueObject, JueOutput, JueState, JueTemplate, NeedState, Product,
                              Question, ScoredDecision, Seeds)
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
    if family == "ask_back":
        return f"第 {a['layer']} 层转译中，该信息有 {a['trans_splits']} 种取值会改变引用的转化知识，客户尚未说明"
    if family == "leak_risk":
        return (f"检索 {a['n_queries']} 次，被拦截的高层级命中 {a['n_blocked']} 条，"
                f"最集中的产品占 {a['blocked_top_share']:.0%}，涉及 {a['n_distinct_products']} 个产品")
    if family == "qi_grant" and a["requested"]:
        return "同事申请查看这条知识的原文；授予后对方可读、你记「授予」分，可随时撤销。"
    if family == "qi_grant" and a["slot"] == "statement":
        return f"这条结论在该层被问到 {a['n_unanswerable']} 次却没有可说的话；是否授予一句话（看不到结论原文）？"
    if family == "qi_grant":
        return (f"研发已回问 {a['n_ask_back']} 次、该层命中却答不了 {a['n_unanswerable']} 次；"
                "是否将这项能力授予所需层级？")
    if family == "qi_review":
        return "结论的原文依据已变化，依赖它的能力已挂起；请复核或撤回。"
    if family == "scope_update":
        return f"研发 {a['n_applicable']} 次判定 {a['product_id']} 适用于该现象，产品适用范围尚未包含"
    if family == "contribution_pm":
        return f"产品经理修正过、尚未沉淀为知识的产品需求条目 {a['n_pm_edited_uncovered']} 条"
    if family == "handoff_sales":
        return "客户原话中提出了报价、采购或送样等商务诉求，会话尚无业务员"
    if family in ("escalate_need", "route_rd"):
        return f"最近一次匹配中「都不合适」概率 {a['p_none']:.2f}，高于最好的候选产品 {a['p_top']:.2f}；已了解 {a['n_filled']} 项信息"
    if family == "distortion":
        return f"本层有 {a['n_unmapped_constraints']} 项上层约束未承接，{a['n_unquoted_items']} 条条目缺少客户原话"
    if family == "seal_leak":
        return f"说明书与用法中有 {a['n_leak_hits']} 句命中封存项、L3 术语或研发方向假设"
    if family == "contribution":
        return f"研发修改过、未被已有转化知识覆盖的条目 {a['n_edited_uncovered']} 条"
    return "上一步已签字、本步未签（规则到点）"


def _label(obj: JueObject, seeds: Seeds | None) -> str:
    """给人看的对象名；没有种子时用 object_id。"""
    a = obj.attrs
    if obj.object_type == "requirement":
        return f"需求单 {obj.object_id.removeprefix('requirement:')}"
    if obj.object_type == "session":
        return f"会话 {obj.object_id.removeprefix('session:')}"
    if seeds is None:
        return obj.object_id
    if obj.object_type == "slot":
        return next(s.label for s in seeds.slots if s.id == a["slot"])
    if obj.object_type == "theme":
        phen = next(p for p in seeds.phenomena if p.id == a["phenomenon"])
        known = dict(kv.split("=") for kv in obj.object_id.split("|")[1].split(",") if kv)
        return " + ".join(known[s] for s in phen.required_slots if s in known) + f"的{phen.label}"
    if obj.object_type == "knowledge" and a["slot"] == "share":
        name = next((x.name for x in seeds.actors if x.id == a["value"]), a["value"])
        return f"{name}申请查看 {obj.object_id.removeprefix('knowledge:share:').split('|')[0]}"
    if obj.object_type == "knowledge" and a["slot"] == "statement":
        return f"{a['product_id'] or '结论'} · {a['value']} · {obj.object_id.rsplit('|', 1)[1]}"
    if obj.object_type == "knowledge":
        value = next((p.label for p in seeds.phenomena if p.id == a["value"]), a["value"]) if a["slot"] == "phenomenon" else a["value"]
        return f"{a['product_id']} × {value}"
    actor = obj.object_id.removeprefix("actor:")
    return next((f"{x.name}（{x.id}）" for x in seeds.actors if x.id == actor), actor)


def _resolve(role: str | None, obj: JueObject, ref: dict, seeds: Seeds | None, signer: bool = False) -> str | None:
    """契约 5.4 解析表：角色 × 对象 → 具体的人。v6：pm 作签字人为真人产品经理；
    需求单被研发退回过、尚未接单时，pm 作主人也解析为真人产品经理（例外纠偏不走 Agent 起草）。"""
    if role is None:
        return None
    if role == "pm":
        human = signer or (obj.object_type == "requirement" and obj.attrs.get("n_returns", 0) >= 1
                           and obj.attrs["status"] == "draft")
        return min(a.id for a in seeds.actors if a.role == "pm" and a.id != "pm:agent") if human else "pm:agent"
    if role == "sales":
        return ref["sales_id"]
    if role == "supervisor":
        return min(a.id for a in seeds.actors if a.role == "supervisor")
    if obj.object_type == "knowledge":
        if "signer" in ref:
            return ref["signer"]
        return next((p.owner for p in seeds.products if p.id == obj.attrs["product_id"]), None)
    return ref["assigned_rd"]      # requirement / slot（第 2、3 层）/ theme（机会汇聚，C14）


def _refs(d: ScoredDecision, ref: dict) -> dict[str, str]:
    """门面传入的引用（列表用逗号连接，event_ids 进证据）+ 由对象 id 得到的引用。"""
    q_refs = {k: ",".join(v) if isinstance(v, list) else v for k, v in ref.items()
              if k != "event_ids" and v not in (None, [])}
    kind, _, rest = d.object_id.partition(":")
    if kind == "requirement":
        q_refs["requirement_id"] = rest
    elif kind == "session":
        q_refs["session_id"] = rest
    elif kind == "slot" and d.family == "ask_back":
        q_refs["requirement_id"], q_refs["slot"] = rest.rsplit("/", 1)
    elif kind == "knowledge":
        q_refs.setdefault("product_id", rest.split("|", 1)[0])
    elif kind == "actor":
        q_refs["actor_id"] = rest
    return q_refs


def publish(out: JueOutput, state: JueState, templates: dict[str, JueTemplate], bus: QuestionBus, threshold: float,
            *, seeds: Seeds | None = None, refs: dict[str, dict] | None = None) -> list[Question]:
    """所有非 ask_slot 的组合 p_need ≥ threshold 即生成问题，不区分实时 / 定时。
    refs：每个对象由门面传入解析主人与签字人所需的 id（sales_id、assigned_rd）与要带进问题的引用
    （session_id、requirement_ids 等）；定时对象另有 collect_scheduled 的 event_ids、session_ids。
    seeds 用于给人看的标题、知识冲突的归属研发与主管。"""
    catalog = {t.family for t in templates.values()}
    unknown = {d.family for d in out.decisions} - catalog
    if unknown:
        raise ValueError(f"决策目录中没有这些 family：{sorted(unknown)}")
    existing = {q.id for q in bus.list(status=None)}
    published = []
    for d in out.decisions:
        if d.family == "ask_slot" or d.p_need is None or d.p_need < threshold:
            continue
        t, obj = templates[d.template_id], state.objects[d.object_id]
        ref = (refs or {}).get(d.object_id, {})
        owner_role = "rd" if d.family == "distortion" and obj.attrs["layer"] == 3 else t.owner_role
        q = bus.publish(Question(
            id="", family=d.family, title=t.title.format(object=_label(obj, seeds), attrs=SimpleNamespace(**obj.attrs)),
            object_id=d.object_id, owner_role=owner_role, owner_id=_resolve(owner_role, obj, ref, seeds),
            signer_role=t.signer_role, signer_id=_resolve(t.signer_role, obj, ref, seeds, signer=True), template_id=t.id,
            p_need=d.p_need, urgency=d.urgency, scored_by=d.scored_by or out.scored_by, discoverer=out.model,
            evidence=[Evidence(summary=_summary(d.family, obj.attrs), event_ids=ref.get("event_ids", []))],
            refs=_refs(d, ref), bounty_points=t.bounty_points, dedup_key=f"{d.family}:{d.object_id}",
            created_at=out.at))
        if q.id and q.id not in existing:   # 合并进已有问题或被抑制的不算新发布
            published.append(q)
    return published
