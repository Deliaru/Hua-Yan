"""契约 ⑦：升级、分层转译与回流。"""
from __future__ import annotations

from typing import Literal

from ._base import BaseModel, datetime
from .seeds import Level


class ReqItem(BaseModel):
    text: str
    slot: str | None = None
    quote_refs: list[str] = []                # turn id，可回查客户原话
    ku_refs: list[str] = []                   # 依据的知识单元（转化对照、案例、机理）；其归属人记 cited
    edited_by: str | None = None              # 最后一次由人修改的 actor id；None = 骨架或 Agent 起草
                                              # v8 收口：委托人在对话里交代、助手当轮改的，记委托人；派单准备时仍为 None


class PMDraft(BaseModel):                     # L2：场景语言 → 产品需求语言（规则骨架，产品经理 Agent 编辑）
    direction: str
    product_lang: list[ReqItem]


class RDDraft(BaseModel):                     # L3：产品需求 → 化学语言（规则骨架，研发 Agent 编辑）
    chem_lang: list[ReqItem]
    hypotheses: list[str] = []                # 研发方向假设


class SheetDraft(BaseModel):                  # 反向包装：产品需求＋对外要点 → L1 说明书（规则模板，产品经理 Agent 编辑）
    sheet: str
    usage: str


class ReuseProposal(BaseModel):               # 产品经理 Agent 查 L2 知识后的现成产品建议（v5.1）
    product_id: str | None                    # None = 已查，无现成产品
    ku_refs: list[str] = []                   # 依据的 L2 知识（案例、L2 转化对照）；采用时给归属人记 cited
    customer_note: str = ""                   # 面向客户的一句说明（v5.3：研发审定后才对 L1 可见；保存与审定时过 leak_hits）
    note: str = ""                            # 给业务员的依据说明，只写归属，不写案例原文
    declined_reason: str = ""                 # 研发不采用的理由（v5.3：审定人由业务员改为研发）


class LeakHit(BaseModel):                     # 泄密匹配结果，只给句序号与类别，不含命中内容
    index: int                                # 按「。；！？\n」切句后的序号，从 0 开始
    source: Literal["sealed", "l3_term", "hypothesis", "claim"]


class PointsDraft(BaseModel):                 # 封存 / 放出两栏草稿（只对 L3 可见）
    public: str                               # 拟放出的对外要点
    sealed: list[str]                         # 拟封存的窗户纸
    self_check: list[LeakHit] = []            # 对 public 的泄露自查结果


class ContributionDraft(BaseModel):           # Agent 提炼的可沉淀转化知识（只对 L3 可见）
    item_index: int
    scene_phrase: str
    chem_term: str
    note: str = ""                            # 泛化说明、与已有知识相近或冲突之处


class Requirement(BaseModel):
    id: str                                   # "req:<n>"
    question_id: str                          # 产生它的 escalate_need 或 opportunity 问题
    session_ids: list[str]
    phenomenon: str
    known_slots: dict[str, str]
    assigned_rd: str                          # 接单与签字的研发：建单时取该现象 L3 转化对照条数最多的研发（并列取 id 最小）
    escalate_note: str = ""                   # 业务员签字时的升级说明（L2/L3 可见）
    reuse: ReuseProposal | None = None        # v5.1：现成产品建议；None = 还没查
    merged_into: str | None = None            # v5.2：被并入的单指向主单
    merge_from: list[str] = []                # v5.2：产品经理 Agent 起草的合并建议，拟并入本单的需求单 id（研发签字前是草稿）
    merge_note: str = ""                      # v5.2：判断依据——几位客户说的是不是同一件事（L2/L3 可见）
    direction: str = ""                       # 空单时为空
    product_lang: list[ReqItem] = []          # L2/L3 可见；空单时为空
    engine_refs: list[str] = []
    chem_lang: list[ReqItem] = []             # L2/L3 可见；所引 L3 知识的原文只有 L3 可见
    hypotheses: list[str] = []                # 研发方向假设（只对 L3 可见）；泄密匹配的来源之一
    status: Literal["draft", "reused", "merged", "rd_accepted", "rd_confirmed", "released", "rejected"]
    # reused：研发审定采用现成产品（v5.3）；merged（v5.2）：已并入另一张单
    drafted_by: str = "pm:agent"              # L2 草稿的起草者
    chem_drafted_by: str | None = None        # L3 草稿的委托人（研发 actor id）
    rd_accepted_by: str | None = None         # 研发接单（= 立项）
    rd_confirmed_by: str | None = None
    return_notes: list[str] = []              # 研发退回理由（提交前经 L3 术语自查，L2 可见）
    contribution_drafts: list[ContributionDraft] = []   # 只对 L3 可见
    points_draft: PointsDraft | None = None   # 只对 L3 可见
    public_points: str = ""                   # 研发签字放出的对外要点：L3 内容流向 L2/L1 的唯一出口
    sealed: list[str] = []                    # 研发签字封存的窗户纸，只对 L3 可见
    sheet: SheetDraft | None = None           # 反向包装草稿
    product_id: str | None = None             # 目标产品：L3 确认时关联研发中项目（种子 status=project，或接单时立的 proj:<req_id>，v8 Q9.3）；发布后即新产品
    created_at: datetime


class Trial(BaseModel):
    id: str
    product_id: str
    requirement_id: str | None = None
    rd: str
    conditions: dict[str, str]
    result: Literal["pass", "fail"]
    cause: Literal["none", "product", "equipment", "operation", "requirement"]
    note: str = ""
    at: datetime
    market_eval: Literal["pass", "fail"] | None = None   # 客户评价，业务员录入
    market_eval_by: str | None = None
    market_eval_note: str = ""
    missing_slots: list[str] = []
    market_eval_missing: list[str] = []


class CitedKnowledge(BaseModel):              # 需求单中被引用的知识，按查看者裁剪
    ku_id: str
    owner: str
    level: Level
    title: str
    text: str | None                          # 查看者无权阅读时为 None，只显示归属与层级
    n_cited: int                              # 全系统累计被引用次数


class RequirementView(BaseModel):
    viewer: str
    viewer_level: Level
    requirement: Requirement
    quotes: dict[str, str]                    # turn id → 客户原话
    cited: list[CitedKnowledge]


class ContributionStat(BaseModel):            # 贡献看板的一行
    owner: str
    ku_id: str
    level: Level
    title: str
    n_cited: int
    points: int
    used_by: list[str]                        # 需求单 / 会话 id
