from datetime import timedelta

from huayan.contracts import Injection, NeedCard, NeedState, Requirement, SlotFill
from huayan.events import EventLog
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.sim.trajectory import ask_label, back_label
from huayan.sim.week_events import window_label

THEME = "theme:color_unlevel|equipment=气流染色机,fiber=锦纶氨纶"


def test_hindsight_labels_on_hand_examples(mini_seeds, sim_clock):
    at = sim_clock.now()
    products = mini_seeds.products
    phen = next(p for p in mini_seeds.phenomena if p.id == "color_unlevel")
    card = lambda slots, unknown=(), product=None: NeedCard(id="card:1", phenomenon="color_unlevel", slots=slots,
                                                            unknown_slots=list(unknown), customer_id="customer:C01",
                                                            chem_savvy=False, wants_mechanism=False, truth_product=product)
    fill = lambda slot, value, status="filled": SlotFill(slot=slot, value=value, status=status, confidence=0.5,
                                                        quote="", turn_id="turn:s:1")
    need = lambda **slots: NeedState(session_id="s", customer_id="customer:C01", sales_id="sales:S01",
                                     phenomenon="color_unlevel", slots=slots)
    truth = {"fiber": "棉", "equipment": "溢流染色机", "constraint": "无"}

    # 追问 1：面料未填时推荐 T-205（候选 {T-101, T-205}，取适用条件多的），真值「棉」、应升级 → 补上后候选为空、判为升级，由错变对 → 1
    assert ask_label(need(), card(truth), "fiber", products, phen.required_slots) == 1
    # 追问 2：面料答过「不清楚」→ 0
    assert ask_label(need(fiber=fill("fiber", None, "unknown")), card(truth, ["fiber"]), "fiber", products,
                     phen.required_slots) == 0
    # 追问 3：真值「锦纶氨纶」、正确产品 T-205 → 补上后候选缩成 {T-205}，但推荐本来就是 T-205 → 0
    nylon = {**truth, "fiber": "锦纶氨纶"}
    assert ask_label(need(), card(nylon, product="T-205"), "fiber", products, phen.required_slots) == 0
    # 追问 4：面料被填错成「涤纶」（推荐 T-101），改正后推荐 T-205 → 1
    assert ask_label(need(fiber=fill("fiber", "涤纶")), card(nylon, product="T-205"), "fiber", products,
                     phen.required_slots) == 1
    # 追问 5：已知「棉」时已正确判为应升级（推荐不再变），但设备是研发必问信息、不问研发会退回 → 1
    assert ask_label(need(fiber=fill("fiber", "棉")), card(truth), "equipment", products, phen.required_slots) == 1

    # 回问：L3 起草中只知设备；文本「色花（匀染性差） 气流染色机」只命中 L3 的 tr:4（匀染），
    # 补上真值「锦纶氨纶」后多命中 R02 的 tr:5 → 1
    kb = KnowledgeBase.from_seeds(mini_seeds, EventLog(), AuditLog())
    req = Requirement(id="req:1", question_id="q:1", session_ids=["s"], phenomenon="color_unlevel",
                      known_slots={"equipment": "气流染色机"}, direction="", product_lang=[], status="rd_accepted",
                      assigned_rd="rd:R01", drafted_by="pm:agent", created_at=at)
    back_card = card({**truth, "fiber": "锦纶氨纶", "equipment": "气流染色机"})
    assert back_label(req, need(equipment=fill("equipment", "气流染色机")), back_card, "fiber", phen, kb, 3) == 1

    # 定时：注入窗口内的机会汇聚主题 → 1；同一客户反复升级的困难负样本（窗口内）→ 0
    inj = lambda oid, hard: Injection(id="inj", family="opportunity", object_id=oid, hard_negative=hard, onset=at,
                                      earliest=at, latest=at + timedelta(days=3))
    hard = "theme:poor_fastness|fiber=涤纶"
    injections = [inj(THEME, False), inj(hard, True)]
    assert window_label("opportunity", THEME, at + timedelta(days=1), injections) == 1
    assert window_label("opportunity", hard, at + timedelta(days=1), injections) == 0
