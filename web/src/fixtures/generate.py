"""WP-C 第 0 步：用冻结契约生成界面开发样例，不调用业务门面或模型。"""
from datetime import datetime, timedelta
import json
from pathlib import Path

from huayan.clock import SimClock
from huayan.contracts import (
    AskHint, CardSection, CitedKnowledge, ContributionDraft, Evidence,
    JueTimeline, LeakHit, PointsDraft, Question, RecommendationCard,
    ReqItem, Requirement, RequirementView, ReuseProposal, ReuseView,
    SessionView, SheetDraft, SlotFill, TimelineNode, TimelinePoint, Turn,
)


def build():
    clock = SimClock(datetime.fromisoformat("2026-10-11T09:00:00+08:00"))
    times = [clock.now()]
    for _ in range(8):
        clock.advance_to(clock.now() + timedelta(minutes=1))
        times.append(clock.now())

    sid, rid = "sess:fixture-reuse", "req:fixture-reuse"
    sales, rd = "sales:S01", "rd:R02"
    product = "HY-FX301"
    name = "无醛固色剂 HY-FX301（模拟）"
    usage = "（模拟）1–3 % o.w.f.，皂洗后 40–50 ℃ 固色 20 分钟。"
    customer_note = "（模拟）可试用此产品改善水洗掉色，先按推荐用量做小样确认。"
    case_id = "ku:case:fixture-reuse"
    case_text = "（模拟案例原文）莱赛尔布水洗掉色，曾用 HY-FX301 做小样后改善。"
    basis = ["产品经理 P01 · 历史案例 · L2"]
    turns = [
        Turn(id=f"turn:{sid}:1", session_id=sid, n=1, speaker="customer",
             text="（模拟）这批布洗了掉色。", ts=times[0]),
        Turn(id=f"turn:{sid}:2", session_id=sid, n=2, speaker="sales",
             text="请问是什么面料？", ts=times[1]),
        Turn(id=f"turn:{sid}:3", session_id=sid, n=3, speaker="customer",
             text="（模拟）莱赛尔布，希望水洗后不掉色。", ts=times[2]),
    ]
    slot = SlotFill(slot="fiber", value="莱赛尔", status="filled", confidence=1,
                    quote="莱赛尔布", turn_id=turns[2].id)
    escalate_note = "（模拟）客户反馈莱赛尔布水洗掉色，当前无直接推荐，请查历史案例。"

    def question(family, object_id, title, owner, signer, minute, prepared=None):
        return Question(
            id=f"q:fixture:{family}:{object_id}", family=family, title=title,
            object_id=object_id, owner_role=owner.split(":")[0], owner_id=owner,
            signer_role=signer.split(":")[0] if signer else None, signer_id=signer,
            template_id=family, prepared_at=times[prepared] if prepared is not None else None,
            p_need=1, scored_by="rule", discoverer="jue_proto",
            dedup_key=f"{family}:{object_id}", created_at=times[minute],
        )

    escalation = question("escalate_need", f"session:{sid}", "是否转产品经理 Agent", sales, sales, 2, 3)
    escalation.refs = {"session_id": sid, "sales_id": sales}
    escalation.evidence = [Evidence(summary="（模拟）当前没有适用的直接推荐。")]
    reuse = question("reuse_product", f"requirement:{rid}", "是否采用现成产品", "pm:agent", rd, 4, 5)
    reuse.refs = {"session_id": sid, "requirement_id": rid, "assigned_rd": rd}
    reuse.evidence = [Evidence(summary="（模拟）产品经理 Agent 已查到案例，等待研发审定。")]

    common = dict(session_id=sid, viewer=sales, viewer_level=1, turns=turns,
                  slots=[slot], hints=[], replies=[], card=None,
                  status="escalated", escalation_question_id=escalation.id,
                  escalate_note=escalate_note)
    asking = SessionView(**{**common, "turns": turns[:1], "slots": [], "status": "open",
        "escalation_question_id": None, "escalate_note": "",
        "reply_draft": "请问是什么面料？",
        "hints": [AskHint(session_id=sid, slot="fiber", label="面料成分",
                          ask_text="请问是什么面料？", p_need=0.82, scored_by="jue_k")]})
    ready = SessionView(**{**common, "status": "open", "escalation_question_id": None,
                           "reply_draft": "我会进一步核对适用方案。"})
    pending = SessionView(**common, reuse=ReuseView(
        requirement_id=rid, product_id=product, product_name=name, status="pending"))
    card = RecommendationCard(
        session_id=sid, viewer=sales, product_id=product, version="product_usage",
        sections=[
            CardSection(title="产品说明", text="（模拟）改善水洗牢度。",
                        ku_id=f"ku:sheet:{product}", level=1),
            CardSection(title="用法", text=usage, ku_id=f"ku:usage:{product}", level=1),
        ], note=f"（模拟）研发 R02 审定：{customer_note}",
    )
    adopted = SessionView(**{**common, "status": "recommended", "card": card,
                            "reply_draft": customer_note}, reuse=ReuseView(
        requirement_id=rid, product_id=product, product_name=name, status="adopted",
        usage=usage, customer_note=customer_note, basis=basis))

    def sales_sample(label, session, questions):
        return dict(label=label, session=session.model_dump(mode="json"),
                    questions=[q.model_dump(mode="json") for q in questions])

    sales_samples = {
        "asking": sales_sample("追问提示与回复草稿", asking, []),
        "escalation_ready": sales_sample("升级说明已准备，业务员待签", ready, [escalation]),
        "pending": sales_sample("现成产品等待研发审定", pending, []),
        "adopted": sales_sample("研发审定后转给业务员", adopted, []),
    }

    req = Requirement(
        id=rid, question_id=escalation.id, session_ids=[sid], phenomenon="poor_fastness",
        known_slots={"fiber": "莱赛尔"}, assigned_rd=rd, escalate_note=escalate_note,
        status="draft", created_at=times[4], reuse=ReuseProposal(
            product_id=product, ku_refs=[case_id], customer_note=customer_note,
            note=basis[0]),
    )
    reuse_view = RequirementView(
        viewer=rd, viewer_level=3, requirement=req,
        quotes={t.id: t.text for t in turns if t.speaker == "customer"},
        cited=[CitedKnowledge(ku_id=case_id, owner="pm:P01", level=2,
                              title="（模拟）莱赛尔固色历史案例", text=case_text, n_cited=0)],
    )

    # 第二条线程只展示研发工作面，不与现成产品复用支线混为一次立项。
    main_sid, main_rid = "sess:fixture-main", "req:fixture-main"
    quote_id = f"turn:{main_sid}:1"
    main_quote = "（模拟）锦氨布在气流缸里染，深一块浅一块，不能影响色光。"
    l2_id, l3_id = "ku:translation:fixture-l2", "ku:translation:fixture-l3"
    main_req = Requirement(
        id=main_rid, question_id="q:fixture:escalate_need:main", session_ids=[main_sid],
        phenomenon="color_unlevel", known_slots={"fiber": "锦纶氨纶", "equipment": "气流染色机"},
        assigned_rd=rd, status="draft", created_at=times[4],
        reuse=ReuseProposal(product_id=None, note="（模拟）已查，无现成产品。"),
    )
    accept = question("accept_requirement", f"requirement:{main_rid}", "研发是否接单", "pm:agent", rd, 5)
    seal_req = Requirement(**{**main_req.model_dump(), "status": "rd_confirmed",
        "direction": "（模拟）开发低浴比气流染色适用的匀染产品。",
        "product_lang": [ReqItem(text="（模拟）低浴比下改善匀染，且不能影响色光。",
                                  quote_refs=[quote_id], ku_refs=[l2_id])],
        "chem_lang": [ReqItem(text="（模拟）控制升温过程中的染浴酸度变化。",
            quote_refs=[quote_id], ku_refs=[l3_id], edited_by=rd)],
        "hypotheses": ["（模拟假设）缓释酸组分可控制升温过程中的酸度变化。"],
        "chem_drafted_by": rd, "rd_accepted_by": rd, "rd_confirmed_by": rd,
        "contribution_drafts": [ContributionDraft(item_index=0,
            scene_phrase="（模拟）低浴比匀染", chem_term="（模拟）控制升温过程中的酸度变化",
            note="（模拟）已去掉客户特定条件，待研发审定是否沉淀。")],
        "points_draft": PointsDraft(public="（模拟）低浴比下改善匀染。缓释酸组分控制酸度变化。",
            sealed=["（模拟）缓释酸组分控制酸度变化"],
            self_check=[LeakHit(index=1, source="sealed")]),
        "product_id": "HY-LV206",
    })
    seal = question("seal_points", f"requirement:{main_rid}", "审定封存与对外要点", rd, rd, 7, 8)
    seal.evidence = [Evidence(summary="（模拟）客户评价通过，两栏草稿待核对，第 2 句需改写。")]
    for q in (accept, seal):
        q.refs = {"session_id": main_sid, "requirement_id": main_rid, "assigned_rd": rd}

    def rd_sample(label, view, questions, leak):
        return dict(label=label, requirement=view.model_dump(mode="json"),
                    questions=[q.model_dump(mode="json") for q in questions],
                    leak=[hit.model_dump(mode="json") for hit in leak])

    rd_samples = {
        "reuse_pending": rd_sample("现成产品待研发审定", reuse_view, [reuse], []),
        "preparing": rd_sample("产品经理 Agent 正在准备 L2", RequirementView(
            viewer=rd, viewer_level=3, requirement=main_req,
            quotes={quote_id: main_quote}, cited=[]), [accept], []),
        "points_ready": rd_sample("两栏草稿待签，需先改写自查命中句", RequirementView(
            viewer=rd, viewer_level=3, requirement=seal_req, quotes={quote_id: main_quote},
            cited=[
                CitedKnowledge(ku_id=l2_id, owner="pm:P01", level=2, title="（模拟）低浴比匀染需求",
                               text="（模拟）低浴比下保持匀染且不影响色光。", n_cited=1),
                CitedKnowledge(ku_id=l3_id, owner=rd, level=3, title="（模拟）酸度控制转化对照",
                               text="（模拟）控制升温过程中的染浴酸度变化。", n_cited=1),
            ]), [seal], []),
    }
    # leak 接口检查说明书；两栏草稿自查单独留在 points_draft.self_check。
    release_req = Requirement(**{**seal_req.model_dump(), "points_draft": None,
        "public_points": "（模拟）低浴比下改善匀染。",
        "sealed": ["（模拟）缓释酸组分控制酸度变化"],
        "sheet": SheetDraft(sheet="（模拟）低浴比下改善匀染。缓释酸组分控制酸度变化。",
                            usage="（模拟）先做小样确认用量。")})
    release_view = RequirementView(**{**rd_samples["points_ready"]["requirement"],
                                      "requirement": release_req})
    leak_question = question("seal_leak", f"requirement:{main_rid}",
                             "说明书含封存内容，需改写", rd, rd, 8)
    leak_question.refs = seal.refs.copy()
    release_question = question("release", f"requirement:{main_rid}",
                                "审定发布说明书", "pm:agent", rd, 8, 8)
    release_question.refs = seal.refs.copy()
    release_question.evidence = [Evidence(
        summary="（模拟）说明书已准备，待研发审定；泄密检查命中，改写通过后才能发布。")]
    rd_samples["sheet_leak"] = rd_sample("说明书泄密批注，研发 Agent 准备改写",
        release_view, [release_question, leak_question], [LeakHit(index=1, source="sealed")])

    points = []
    for minute, score in ((0, 0.82), (1, 0.91), (2, None)):
        points.append(TimelinePoint(at=times[minute], family="ask_slot",
            object_id=f"slot:{sid}/fiber", p_need=score, threshold=0.5,
            scored_by="jue_k", raised=False))  # 追问只出提示，不进问题总线。
    for family, object_id, values in (
        ("escalate_need", f"session:{sid}", ((0, None, False), (2, 1.0, True), (4, None, False))),
        ("reuse_product", f"requirement:{rid}", ((4, 1.0, True), (5, None, False), (6, None, False))),
    ):
        for minute, score, raised in values:
            points.append(TimelinePoint(at=times[minute], family=family, object_id=object_id,
                p_need=score, threshold=0.5, scored_by="rule", raised=raised))
    nodes = [
        TimelineNode(question_id=q.id, family=q.family, owner_id=q.owner_id, signer_id=q.signer_id,
            created_at=q.created_at, prepared_at=q.prepared_at, resolved_at=times[minute],
            action="sign", by=signer)
        for q, minute, signer in ((escalation, 4, sales), (reuse, 6, rd))
    ]
    timeline = JueTimeline(target_id=rid, viewer=rd,
        points=sorted(points, key=lambda p: p.at), nodes=nodes,
        n_judgments=7, n_llm_calls=0, n_questions=len(nodes), n_signatures=len(nodes))
    # 7 次模拟 propose：0/1/2 分钟各 1 次，4 分钟会话、需求单各 1 次，5/6 各 1 次。
    return {
        "sales_workbench.json": {"simulated": True, "scenarios": sales_samples},
        "rd_workbench.json": {"simulated": True, "scenarios": rd_samples},
        "jue_timeline.json": timeline.model_dump(mode="json"),
    }


if __name__ == "__main__":
    for name, payload in build().items():
        path = Path(__file__).parent / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(name)
