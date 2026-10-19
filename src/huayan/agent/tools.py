"""契约 ⑭：角色助手的原子工具。一个工具 = 一个动作 = 调用一个门面 / 知识库 / 转译函数；
业务规则、权限与校验都在门面和知识库里，工具只组装参数、精简返回。委托人由 ToolContext 绑定，模型看不到也改不了。
注册表写法参照 JUE src/jue/tools/__init__.py（Registry.register / openai_schemas），按契约 ⑭ 重写。"""
from dataclasses import dataclass
from typing import Any, Callable, Literal

from huayan.clock import get_clock
from huayan.contracts import Actor, ContributionDraft, KUKind, ReqItem, Role, SheetDraft, ToolKind, ToolResult, ToolSpec, Trial
from huayan.contracts._base import BaseModel
from huayan.domain import match_candidates
from huayan.escalation import translate


@dataclass
class ToolContext:
    app: Any                                  # HuayanApp
    principal: Actor
    conversation_id: str
    session_id: str | None = None
    focus: str | None = None                  # 本轮工作面打开的对象，不改变委托人权限


TOOLS: dict[str, tuple[ToolSpec, Callable[[ToolContext, BaseModel], ToolResult]]] = {}


def tool(name: str, kind: ToolKind, roles: list[Role], description: str, params: type[BaseModel], confirm_text: str = ""):
    def register(fn):
        TOOLS[name] = (ToolSpec(name=name, kind=kind, roles=roles, description=description, params=params,
                                confirm_text=confirm_text), fn)
        return fn
    return register


def openai_schemas(role: Role) -> list[dict]:
    return [{"type": "function", "function": {"name": spec.name, "description": spec.description,
                                              "parameters": spec.params.model_json_schema()}}
            for spec, _ in TOOLS.values() if role in spec.roles]


def _items(items: list[ReqItem]) -> list[dict]:
    return [{"index": i, "text": it.text, "quote_refs": it.quote_refs, "ku_refs": it.ku_refs,
             "edited_by": it.edited_by} for i, it in enumerate(items)]


def _req(req) -> dict:
    return {"req_id": req.id, "status": req.status, "phenomenon": req.phenomenon, "known_slots": req.known_slots,
            "direction": req.direction, "product_lang": _items(req.product_lang), "chem_lang": _items(req.chem_lang),
            "hypotheses": req.hypotheses, "public_points": req.public_points, "product_id": req.product_id,
            "sheet": req.sheet and req.sheet.model_dump(), "return_notes": req.return_notes,
            "reuse": req.reuse and req.reuse.model_dump(),
            "session_ids": req.session_ids, "merge_from": req.merge_from, "merge_note": req.merge_note,
            "sealed": req.sealed, "points_draft": req.points_draft and req.points_draft.model_dump(),
            "contribution_drafts": [d.model_dump() for d in req.contribution_drafts]}


class NoArgs(BaseModel):
    pass


class Text(BaseModel):
    text: str


class ReqId(BaseModel):
    req_id: str


class QuestionId(BaseModel):
    question_id: str


# ---- 通用 ----

class SearchArgs(BaseModel):
    query: str
    kind: KUKind | None = None


@tool("search_knowledge", "read", ["sales", "pm", "rd"],
      "在你委托人这一层检索：可读的结论、授予这一层的话（写给下层时只写 [[编号]]）、相关提示；"
      "越权命中只告诉你归属人与层级（谁知道），不给内容", SearchArgs)
def search_knowledge(ctx: ToolContext, args: SearchArgs) -> ToolResult:
    found = ctx.app.kb.explore(args.query, ctx.principal, k=5, session_id=ctx.session_id)
    return ToolResult(data={"hits": [{"ku_id": u.id, "kind": u.kind, "level": u.level, "title": u.title,
                                      "text": u.text[:160], "owner": u.owner} for u in found.units if args.kind in (None, u.kind)],
                            "statements": [{"ref": c.id, "text": c.payload["text"]} for c in found.capabilities if c.form == "statement"],
                            "hints": found.hints, "candidates": [{"ku_id": u.id, "title": u.title} for u in found.candidates],
                            "blocked": [f"{b.owner} · L{b.level}" + (f" · 可申请 {b.ku_id}" if b.ku_id else "") for b in found.stubs]})


class KuId(BaseModel):
    ku_id: str


@tool("get_knowledge", "read", ["sales", "pm", "rd"], "读取一条知识的全文（越权会被拒绝）", KuId)
def get_knowledge(ctx: ToolContext, args: KuId) -> ToolResult:
    u = ctx.app.kb.get(args.ku_id, ctx.principal)
    return ToolResult(data={"ku_id": u.id, "kind": u.kind, "level": u.level, "title": u.title, "text": u.text,
                            "owner": u.owner})


@tool("list_my_questions", "read", ["sales", "pm", "rd"], "列出派给你委托人（或其角色、尚未指派到人）的待处理问题", NoArgs)
def list_my_questions(ctx: ToolContext, args: NoArgs) -> ToolResult:
    me = ctx.principal
    return ToolResult(data=[{"question_id": q.id, "family": q.family, "title": q.title, "object_id": q.object_id,
                             "p_need": q.p_need, "refs": q.refs, "evidence": [e.summary for e in q.evidence]}
                            for q in ctx.app.bus.list(owner_role=me.role) if q.owner_id in (None, me.id)])


# ---- 业务员（绑定当前客户会话） ----

@tool("save_reply_draft", "draft", ["sales"], "将回复草稿写入当前会话，供业务员查看、修改后发送", Text)
def save_reply_draft(ctx: ToolContext, args: Text) -> ToolResult:
    session = ctx.app.save_reply_draft(ctx.session_id, args.text, ctx.principal.id)
    return ToolResult(data={"session_id": session.id, "reply_draft": session.reply_draft})


@tool("save_escalate_note", "draft", ["sales"], "将升级说明草稿写入当前会话，供业务员审查签字", Text)
def save_escalate_note(ctx: ToolContext, args: Text) -> ToolResult:
    session = ctx.app.save_escalate_note(ctx.session_id, args.text, ctx.principal.id)
    return ToolResult(data={"session_id": session.id, "escalate_note": session.escalate_note})


@tool("get_need_card", "read", ["sales"], "查看当前会话的场景需求卡：槽位与客户原话、追问提示、推荐卡", NoArgs)
def get_need_card(ctx: ToolContext, args: NoArgs) -> ToolResult:
    v = ctx.app.view_session(ctx.session_id, ctx.principal.id)
    return ToolResult(data={"status": v.status, "slots": [{"slot": f.slot, "value": f.value, "quote": f.quote} for f in v.slots],
                            "turns": [{"turn_id": t.id, "speaker": t.speaker, "text": t.text} for t in v.turns],
                            "ask_hints": [h.ask_text for h in v.hints], "escalation_question_id": v.escalation_question_id,
                            "reply_draft": v.reply_draft, "escalate_note": v.escalate_note,
                            "reuse": v.reuse and v.reuse.model_dump(),
                            "card": v.card and {"product_id": v.card.product_id, "version": v.card.version,
                                                "note": v.card.note,
                                                "sections": [f"{s.title}：{s.text}" for s in v.card.sections]}})


@tool("request_decrypt", "effect", ["sales"], "客户懂化学且要求了解机理时，为当前会话的推荐产品申请解密（产品归属研发审批）",
      NoArgs, "为当前会话的推荐产品申请解密，交产品归属研发审批")
def request_decrypt(ctx: ToolContext, args: NoArgs) -> ToolResult:
    q = ctx.app.request_decrypt(ctx.session_id, ctx.principal.id)
    return ToolResult(data={"question_id": q.id, "owner_id": q.owner_id})


# ---- 产品经理 / 研发：读 ----

class SessionId(BaseModel):
    session_id: str


@tool("get_session", "read", ["pm", "rd"], "查看一段客户会话：逐轮原话（带 turn id）、槽位、状态", SessionId)
def get_session(ctx: ToolContext, args: SessionId) -> ToolResult:
    v = ctx.app.view_session(args.session_id, ctx.principal.id)
    return ToolResult(data={"turns": [{"turn_id": t.id, "speaker": t.speaker, "text": t.text} for t in v.turns],
                            "slots": {f.slot: f.value for f in v.slots}, "status": v.status,
                            "requirement_id": v.requirement.id if v.requirement else None})


class MatchArgs(BaseModel):
    text: str
    phenomenon: str | None = None


@tool("match_translations", "read", ["pm", "rd"], "用一段场景描述匹配你可读的转化对照（场景说法 → 本层术语）", MatchArgs)
def match_translations(ctx: ToolContext, args: MatchArgs) -> ToolResult:
    hits = translate.match_translations(args.text, ctx.app.kb, ctx.principal, args.phenomenon)
    return ToolResult(data=[{"ku_id": h.ku.id, "level": h.ku.level, "translation": h.ku.text, "owner": h.ku.owner,
                             "score": round(h.score, 2)} for h in hits])


class ProductArgs(BaseModel):
    phenomenon: str
    slots: dict[str, str] = {}


@tool("find_products", "read", ["pm", "rd"], "按现象与已知条件查已发布产品中的候选（含还不知道的限定条件）", ProductArgs)
def find_products(ctx: ToolContext, args: ProductArgs) -> ToolResult:
    found = match_candidates(args.phenomenon, args.slots, ctx.app.kb.view(ctx.principal).products)
    return ToolResult(data=[c.model_dump() for c in found])


@tool("get_requirement", "read", ["pm", "rd"], "查看需求单：各层条目、客户原话、所引知识（越权知识只显示归属）", ReqId)
def get_requirement(ctx: ToolContext, args: ReqId) -> ToolResult:
    v = ctx.app.requirement_view(args.req_id, ctx.principal.id)
    return ToolResult(data={**_req(v.requirement), "quotes": v.quotes,
                            "cited": [{"ku_id": c.ku_id, "owner": c.owner, "level": c.level, "title": c.title,
                                       "text": c.text} for c in v.cited]})


@tool("my_contributions", "read", ["pm", "rd"], "查看你委托人的知识被引用的次数与积分", NoArgs)
def my_contributions(ctx: ToolContext, args: NoArgs) -> ToolResult:
    rows = ctx.app.contributions(ctx.principal.id)
    return ToolResult(data=[{"ku_id": r.ku_id, "title": r.title, "n_cited": r.n_cited, "points": r.points}
                            for r in rows if r.owner == ctx.principal.id])


# ---- 需求单草稿（产品经理改 L2，研发改 L3；层的规则在门面） ----

class ReuseArgs(BaseModel):
    req_id: str
    product_id: str | None
    ku_refs: list[str]
    customer_note: str
    note: str


@tool("propose_reuse", "draft", ["pm"], "保存复用建议；ku_refs 仅限 L2 案例/转化知识。查无产品时 product_id=null、ku_refs=[]、customer_note为空，note 写检索结果", ReuseArgs)
def propose_reuse(ctx: ToolContext, args: ReuseArgs) -> ToolResult:
    req = ctx.app.save_reuse_proposal(args.req_id, args.product_id, args.ku_refs,
                                     args.customer_note, args.note, ctx.principal.id)
    return ToolResult(data=_req(req))


@tool("draft_product_need", "draft", ["pm"], "为已有需求单起草 L2 产品需求（规则骨架，之后可逐条修改）", ReqId)
def draft_product_need(ctx: ToolContext, args: ReqId) -> ToolResult:
    return ToolResult(data=_req(ctx.app.draft_requirement(args.req_id, ctx.principal.id)))


class MergeArgs(BaseModel):
    question_id: str
    target_req_id: str
    member_ids: list[str]
    note: str


@tool("propose_merge", "draft", ["pm"], "保存同类需求合并建议；不是同一需求时 member_ids 留空并写理由", MergeArgs)
def propose_merge(ctx: ToolContext, args: MergeArgs) -> ToolResult:
    req = ctx.app.save_merge_proposal(args.question_id, args.target_req_id, args.member_ids, args.note, ctx.principal.id)
    return ToolResult(data=_req(req))


LANG = {"pm": "product_lang", "rd": "chem_lang"}         # 编辑哪一层由门面按角色决定，这里只用来读原条目


class EditArgs(BaseModel):
    req_id: str
    index: int                                # -1 = 追加
    text: str
    quote_refs: list[str] = []
    ku_refs: list[str] = []


@tool("edit_item", "draft", ["pm", "rd"],
      "改写需求单的一条（产品经理改产品需求，研发改化学语言）；index=-1 追加；quote_refs 填客户原话的 turn id，ku_refs 填依据的知识",
      EditArgs)
def edit_item(ctx: ToolContext, args: EditArgs) -> ToolResult:
    old = getattr(ctx.app.requirement_view(args.req_id, ctx.principal.id).requirement, LANG[ctx.principal.role])
    slot = old[args.index].slot if -1 < args.index < len(old) else None      # 改写条件条目时保留其槽位标记
    item = ReqItem(text=args.text, slot=slot, quote_refs=args.quote_refs, ku_refs=args.ku_refs)
    return ToolResult(data=_req(ctx.app.edit_req_item(args.req_id, args.index, item, ctx.principal.id)))


class IndexArgs(BaseModel):
    req_id: str
    index: int


@tool("remove_item", "draft", ["pm", "rd"], "删除需求单的一条（产品经理删产品需求，研发删化学语言）", IndexArgs)
def remove_item(ctx: ToolContext, args: IndexArgs) -> ToolResult:
    return ToolResult(data=_req(ctx.app.remove_req_item(args.req_id, args.index, ctx.principal.id)))


class DirectionArgs(BaseModel):
    req_id: str
    text: str


@tool("set_direction", "draft", ["pm"], "修改需求单的产品方向（一句话）", DirectionArgs)
def set_direction(ctx: ToolContext, args: DirectionArgs) -> ToolResult:
    return ToolResult(data=_req(ctx.app.set_direction(args.req_id, args.text, ctx.principal.id)))


@tool("edit_reuse_note", "draft", ["pm", "rd"], "改写现成产品建议中给客户的说明；草稿经泄密检查，研发审定后才可对外", DirectionArgs)
def edit_reuse_note(ctx: ToolContext, args: DirectionArgs) -> ToolResult:
    return ToolResult(data=_req(ctx.app.update_reuse_note(args.req_id, args.text, ctx.principal.id)))


@tool("draft_chem_need", "draft", ["rd"], "为产品经理已确认的需求单起草 L3 化学语言条目与研发方向假设（规则骨架）", ReqId)
def draft_chem_need(ctx: ToolContext, args: ReqId) -> ToolResult:
    return ToolResult(data=_req(ctx.app.translate_requirement(args.req_id, ctx.principal.id)))


@tool("package_sheet", "draft", ["pm"], "用产品需求与研发的对外要点生成 L1 说明书草稿（反向包装）", ReqId)
def package_sheet(ctx: ToolContext, args: ReqId) -> ToolResult:
    return ToolResult(data=ctx.app.package_sheet(args.req_id, ctx.principal.id).model_dump())


class SheetArgs(BaseModel):
    req_id: str
    sheet: str
    usage: str


@tool("edit_sheet", "draft", ["pm", "rd"], "修改 L1 说明书草稿（说明与用法）；研发可改写泄密句", SheetArgs)
def edit_sheet(ctx: ToolContext, args: SheetArgs) -> ToolResult:
    req = ctx.app.save_sheet(args.req_id, SheetDraft(sheet=args.sheet, usage=args.usage), ctx.principal.id)
    return ToolResult(data={"req_id": req.id, "sheet": req.sheet.model_dump()})


@tool("leak_check", "read", ["pm", "rd"], "检查说明书与用法，仅返回命中句序号与类别", ReqId)
def leak_check(ctx: ToolContext, args: ReqId) -> ToolResult:
    return ToolResult(data=[h.model_dump() for h in ctx.app.leak_check(args.req_id, ctx.principal.id)])


# ---- 生效动作（只挂起为确认卡，委托人确认后才执行） ----


@tool("confirm_translation", "effect", ["rd"], "提议确认 L3 化学语言需求单（关联研发中产品，给所引知识的归属人记分）", ReqId,
      "确认需求单 {req_id} 的化学语言转译，并给所引知识的归属人记分")
def confirm_translation(ctx: ToolContext, args: ReqId) -> ToolResult:
    return ToolResult(data=_req(ctx.app.confirm_translation(args.req_id, ctx.principal.id)))


class ContributeArgs(BaseModel):
    req_id: str
    index: int
    scene_phrase: str
    chem_term: str


class ContributionDraftArgs(ContributeArgs):
    note: str = ""


@tool("save_contribution_draft", "draft", ["rd"], "保存一条提炼后的沉淀草稿，含泛化说明与相近或冲突之处；不入库、不记分",
      ContributionDraftArgs)
def save_contribution_draft(ctx: ToolContext, args: ContributionDraftArgs) -> ToolResult:
    draft = ContributionDraft(item_index=args.index, scene_phrase=args.scene_phrase, chem_term=args.chem_term, note=args.note)
    return ToolResult(data=_req(ctx.app.save_contribution_draft(args.req_id, draft, ctx.principal.id)))


@tool("contribute_translation", "effect", ["rd"], "提议把化学语言的一条沉淀为委托人自己的转化知识（场景说法 → 化学术语）",
      ContributeArgs, "把「{scene_phrase} → {chem_term}」沉淀为你的转化知识（需求单 {req_id} 第 {index} 条）")
def contribute_translation(ctx: ToolContext, args: ContributeArgs) -> ToolResult:
    u = ctx.app.contribute_translation(args.req_id, args.index, args.scene_phrase, args.chem_term, ctx.principal.id)
    return ToolResult(data={"ku_id": u.id, "title": u.title})


class PointsArgs(BaseModel):
    req_id: str
    text: str
    sealed: list[str]


class PointsDraftArgs(BaseModel):
    req_id: str
    public: str
    sealed: list[str]


@tool("save_points_draft", "draft", ["rd"], "起草封存／放出两栏，返回泄密自查结果；草稿不生效", PointsDraftArgs)
def save_points_draft(ctx: ToolContext, args: PointsDraftArgs) -> ToolResult:
    return ToolResult(data=_req(ctx.app.save_points_draft(args.req_id, args.public, args.sealed, ctx.principal.id)))


@tool("set_public_points", "effect", ["rd"], "提议确认可以对外的要点（L3 内容流向下层的唯一出口，不写机理与配方）", PointsArgs,
      "签字封存／放出需求单 {req_id} 的两栏内容")
def set_public_points(ctx: ToolContext, args: PointsArgs) -> ToolResult:
    return ToolResult(data=_req(ctx.app.set_public_points(args.req_id, args.text, args.sealed, ctx.principal.id)))


class TrialArgs(BaseModel):
    req_id: str
    result: Literal["pass", "fail"]
    cause: Literal["none", "product", "equipment", "operation"] = "none"
    note: str = ""


@tool("record_trial", "effect", ["rd"], "提议录入需求单关联产品的试样结果（条件取自需求单）", TrialArgs,
      "录入需求单 {req_id} 的试样结果：{result}（原因 {cause}）{note}")
def record_trial(ctx: ToolContext, args: TrialArgs) -> ToolResult:
    req, at = ctx.app.requirement_view(args.req_id, ctx.principal.id).requirement, get_clock().now()
    trial = ctx.app.record_trial(Trial(id=f"trial:{req.id}@{at:%Y%m%d%H%M%S}", product_id=req.product_id,
                                       requirement_id=req.id, rd=ctx.principal.id, conditions=req.known_slots,
                                       result=args.result, cause=args.cause, note=args.note, at=at))
    return ToolResult(data={"trial_id": trial.id, "product_id": trial.product_id, "result": trial.result})


class DecryptArgs(BaseModel):
    question_id: str
    approve: bool


@tool("decide_decrypt", "effect", ["rd"], "提议批准或拒绝客户的解密申请（只有产品归属研发本人可审批）", DecryptArgs,
      "解密申请 {question_id}：{approve}（True = 批准，客户可看机理、看不到配方）")
def decide_decrypt(ctx: ToolContext, args: DecryptArgs) -> ToolResult:
    q = ctx.app.decide_decrypt(args.question_id, ctx.principal.id, args.approve)
    return ToolResult(data={"question_id": q.id, "status": q.status, "action": q.resolution.action})
