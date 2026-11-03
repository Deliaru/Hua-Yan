"""契约 ⑭：角色助手的原子工具。一个工具 = 一个动作 = 调用一个门面 / 知识库 / 转译函数；
业务规则、权限与校验都在门面和知识库里，工具只组装参数、精简返回。委托人由 ToolContext 绑定，模型看不到也改不了。
注册表写法参照 JUE src/jue/tools/__init__.py（Registry.register / openai_schemas），按契约 ⑭ 重写。"""
from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import Field

from huayan.clock import get_clock
from huayan.contracts import Actor, ContributionDraft, KUKind, ReqItem, Role, SheetDraft, ToolKind, ToolResult, ToolSpec, Trial
from huayan.contracts._base import BaseModel
from huayan.domain import match_candidates
from huayan.knowledge.permission import level_of
from huayan.escalation import translate


@dataclass
class ToolContext:
    app: Any                                  # HuayanApp
    principal: Actor
    conversation_id: str
    session_id: str | None = None
    focus: str | None = None                  # 本轮工作面打开的对象，不改变委托人权限
    instructed: bool = False                  # v8 收口：本轮是委托人亲口交代的，起草记在委托人名下


TOOLS: dict[str, tuple[ToolSpec, Callable[[ToolContext, BaseModel], ToolResult]]] = {}
MEMORY_TOOLS = {"remember", "recall_memory"}          # v8：agent_memory 打开时才给模型


def agent_id(principal: str) -> str:
    """v8：助手借委托人的权限，但以自己的名义记事件与错误；产品经理 Agent 本身就是 pm:agent。"""
    return principal if principal == "pm:agent" else f"agent:{principal}"


def tool(name: str, kind: ToolKind, roles: list[Role], description: str, params: type[BaseModel], confirm_text: str = ""):
    def register(fn):
        TOOLS[name] = (ToolSpec(name=name, kind=kind, roles=roles, description=description, params=params,
                                confirm_text=confirm_text), fn)
        return fn
    return register


def openai_schemas(role: Role, memory: bool = False) -> list[dict]:
    return [{"type": "function", "function": {"name": spec.name, "description": spec.description,
                                              "parameters": spec.params.model_json_schema()}}
            for spec, _ in TOOLS.values() if role in spec.roles and (memory or spec.name not in MEMORY_TOOLS)]


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
    req_id: str = Field(description="需求单编号req:…，从requirement_id/req_id取；不是question_id或knowledge/theme对象编号；问题引用里没有需求单就不要调用，不要拼编号")


class QuestionId(BaseModel):
    question_id: str


# ---- 通用 ----

class SearchArgs(BaseModel):
    query: str
    kind: KUKind | None = None
    purpose: Literal["usage", "cause", "internal", ""] = ""   # ⑰′ 只记进检索事件作参考，不进泄露判断


@tool("search_knowledge", "read", ["sales", "pm", "rd"],
      "在你委托人这一层检索：可读的结论、授予这一层的话（写给下层时只写 [[编号]]）、相关提示；"
      "越权命中只告诉你归属人与层级（谁知道），不给内容；purpose 写你为什么查：usage 用法与适用、cause 毛病原因、internal 产品内部", SearchArgs)
def search_knowledge(ctx: ToolContext, args: SearchArgs) -> ToolResult:
    found = ctx.app.kb.explore(args.query, ctx.principal, k=5, session_id=ctx.session_id,
                               asked_by=agent_id(ctx.principal.id), intent=args.purpose)
    return ToolResult(data={"hits": [{"ku_id": u.id, "product_id": u.product_id, "kind": u.kind, "level": u.level, "title": u.title,
                                      "text": u.text[:160], "owner": u.owner} for u in found.units if args.kind in (None, u.kind)],
                            "statements": [{"ref": c.id, "text": c.payload["text"]} for c in found.capabilities if c.form == "statement"],
                            "hints": found.hints, "candidates": [{"ku_id": u.id, "title": u.title} for u in found.candidates],
                            "blocked": [f"{b.owner} · L{b.level}" + (f" · 可申请 {b.ku_id}" if b.ku_id else "") for b in found.stubs]})


class KuId(BaseModel):
    ku_id: str


DOC_ID = "已登记的资料来源编号（如报告编号P2CQL2024012304），从问题引用、search_sources命中或search_knowledge、get_knowledge结果的出处里取；不是业务试样wk:trial:…或需求单编号，不要猜"


class SourceSearchArgs(BaseModel):
    query: str = Field(description="用需求里的现象、产品、设备、纤维、工艺条件写一句话；可换几种说法多查几次")


@tool("search_sources", "read", ["sales", "pm", "rd"],
      "在委托人有权读的原始资料（试样报告、实验报告、说明书、MSDS、培训课件）里找相关的页；不知道来源编号时先用它。"
      "返回来源编号、标题、页、摘录、相关度和所用方法（semantic 语义 / keyword 关键词）以及依据指针 pointer；"
      "命中只是线索，要用 read_source 读原文核对，pointer 可直接存进 save_source_preparation。", SourceSearchArgs)
def search_sources(ctx: ToolContext, args: SourceSearchArgs) -> ToolResult:
    return ToolResult(data=ctx.app.search_sources(args.query, ctx.principal.id))


class SourceArgs(BaseModel):
    doc_id: str = Field(description=DOC_ID)
    span: str | None = None


@tool("read_source", "read", ["sales", "pm", "rd"],
      "按已知来源编号读取原文；span 可指定块。返回原文、密级与指纹，不返回文件路径。"
      "使用委托人权限，内部资料需归属或整份来源分享；查证不代表结论已确认或已授权。", SourceArgs)
def read_source(ctx: ToolContext, args: SourceArgs) -> ToolResult:
    fragments = ctx.app.read_source(args.doc_id, ctx.principal.id, args.span)
    return ToolResult(data=[f.model_dump() for f in fragments])


class SourceImageArgs(BaseModel):
    doc_id: str = Field(description=DOC_ID)
    page: int
    span: str | None = None


@tool("read_source_image", "read", ["sales", "pm", "rd"],
      "按来源编号、页码和可选块span回取原页或已登记区域，图像随本轮输入提供。"
      "没有区域坐标时返回整页；不接受文件路径或自由坐标，使用委托人权限，读取不确认或授予。", SourceImageArgs)
def read_source_image(ctx: ToolContext, args: SourceImageArgs) -> ToolResult:
    return ToolResult(data=ctx.app.read_source_image(args.doc_id, args.page, ctx.principal.id, args.span))


class SourceTrialArgs(BaseModel):
    doc_id: str = Field(description=DOC_ID)


@tool("read_trial_record", "read", ["sales", "pm", "rd"],
      "按来源编号回取已整理试样记录的A/B条件、配方、曲线标签、观察、出处及待补项。"
      "使用委托人权限；单次观察不代表通用适用范围，读取不确认或授予。", SourceTrialArgs)
def read_trial_record(ctx: ToolContext, args: SourceTrialArgs) -> ToolResult:
    record = ctx.app.read_trial_record(args.doc_id, ctx.principal.id)
    return ToolResult(data=record.model_dump(mode="json", exclude={"file_sha256", "changes", "professional_confirmation"}))


class SourcePreparationArgs(BaseModel):
    req_id: str
    evidence: list[str] = Field(description="仅填doc_id#span@fingerprint指针数组；可逐字复制read_trial_record中evidence[].fragment或search_sources命中的pointer（读过原文核对后）。不能填原文、摘要或Python列表字符串。")
    claim_ids: list[str] = []
    pending: str = ""


@tool("save_source_preparation", "draft", ["rd"],
      "将依据指针 doc_id#span@fingerprint、已有待审候选编号及待补说明保存到原需求。"
      "不复制原文，不导入候选，不确认或授予，也不标记事项已准备完成。", SourcePreparationArgs)
def save_source_preparation(ctx: ToolContext, args: SourcePreparationArgs) -> ToolResult:
    return ToolResult(data=ctx.app.save_source_preparation(
        args.req_id, args.evidence, args.claim_ids, args.pending, ctx.principal.id))


@tool("get_source_preparation", "read", ["rd"], "读取原需求已保存的资料准备草稿及当时条件，供继续补充与审阅。", ReqId)
def get_source_preparation(ctx: ToolContext, args: ReqId) -> ToolResult:
    return ToolResult(data=ctx.app.source_preparation(args.req_id, ctx.principal.id))


class CompileSourceArgs(BaseModel):
    req_id: str
    doc_id: str = Field(description=DOC_ID)


@tool("compile_source_preparation", "draft", ["rd"],
      "将该来源编译成本单待审候选：有登记的操作或负例观察 IR 就按 IR 导入，没有就用本单已保存的这份来源的依据页现编单次观察。"
      "须先保存依据；只产生候选，不确认、授予或标记事项准备完成。", CompileSourceArgs)
def compile_source_preparation(ctx: ToolContext, args: CompileSourceArgs) -> ToolResult:
    return ToolResult(data=ctx.app.compile_source_preparation(args.req_id, args.doc_id, ctx.principal.id))


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

@tool("get_authorized_replies", "read", ["sales"],
      "查看当前会话对应需求已有的生效授权说明；只返回授予业务员层及以下的文字和能力编号，不返回报告或待审判断。", NoArgs)
def get_authorized_replies(ctx: ToolContext, args: NoArgs) -> ToolResult:
    return ToolResult(data=ctx.app.authorized_source_replies(ctx.session_id, ctx.principal.id))


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
    return ToolResult(data=ctx.app.agent_need_card(ctx.session_id, ctx.principal.id))


@tool("request_decrypt", "effect", ["sales"], "客户确有正当需要了解机理时，为当前会话的推荐产品申请解密（产品归属研发审批）",
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
                            "temperature": v.temperature.model_dump() if v.temperature is not None else None,
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
    phenomenon: str = Field(description="复制get_need_card或get_requirement返回的phenomenon现象ID；不填客户原话或机理描述")
    slots: dict[str, str] = {}
    temperature_c: tuple[float, float] | None = None


@tool("find_products", "read", ["sales", "pm", "rd"], "按现象与已知条件查已发布产品中的候选；temperature_c 为摄氏闭区间，未知则省略", ProductArgs)
def find_products(ctx: ToolContext, args: ProductArgs) -> ToolResult:
    phenomena = {p.id: p.label for p in ctx.app.seeds.phenomena}
    if args.phenomenon not in phenomena:      # 填了说法而不是 id 时如实报错，不当作「没有候选」
        raise ValueError(f"phenomenon 要填现象 id（需求单的 phenomenon 字段），{args.phenomenon} 不是；可选："
                         + "；".join(f"{k}={v}" for k, v in phenomena.items()))
    limited = ctx.app.kb.limits()
    found = match_candidates(args.phenomenon, args.slots, ctx.app.kb.view(ctx.principal).products, limited,
                             temperature_c=args.temperature_c)
    # V9.5：带研发限制的适用标「可能」；产品经理、研发看得到限制原文，其他人只知道要研发处理
    shown = lambda c: (limited[c.capability_id] if level_of(ctx.principal) >= 2 else "带研发限制，需研发处理")
    return ToolResult(data=[{**c.model_dump(), **({"limits": shown(c)} if c.capability_id in limited else {})}
                            for c in found])


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
    question_id: str = Field(description="当前opportunity问题的question_id（q:…）；不是theme对象编号或需求单编号")
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


@tool("draft_chem_need", "draft", ["rd"], "为研发已接单的需求单起草 L3 化学语言条目与研发方向假设（规则骨架）", ReqId)
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


# ---- v8：记忆（按委托人存；只记委托人这一层看得到的内容，门面校验）----

class RememberArgs(BaseModel):
    kind: Literal["habit", "fact", "lesson"]
    text: str
    why: str = ""
    refs: list[str] = []


@tool("remember", "draft", ["sales", "pm", "rd"],
      "记下一条以后用得上的记忆：委托人的习惯（habit）、业务事实（fact）或教训（lesson）。一句话，why 写来由与怎么用，"
      "refs 写依据的需求单、会话或问题编号；只记已经发生、对象上查得到的事，不记你的打算。", RememberArgs)
def remember(ctx: ToolContext, args: RememberArgs) -> ToolResult:
    return ToolResult(data={"id": ctx.app.remember(args.kind, args.text, args.why, args.refs, ctx.principal.id).id})


@tool("recall_memory", "read", ["sales", "pm", "rd"],
      "按关键词查委托人的记忆细节（来由与依据编号）。记忆是记下时为真，用之前以对象现状核实。", SearchArgs)
def recall_memory(ctx: ToolContext, args: SearchArgs) -> ToolResult:
    return ToolResult(data=[m.model_dump(mode="json", include={"id", "kind", "text", "why", "refs"})
                            for m in ctx.app.recall_memory(args.query, ctx.principal.id)])
