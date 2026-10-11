"""契约代码，与 docs/CONTRACTS.md 一致；只能由人修改。"""
from ._base import SHANGHAI, BaseModel
from .agent import AgentMessage, AgentStep, Conversation, PendingAction, ToolKind, ToolResult, ToolSpec
from .app import JueTimeline, ReuseView, RunStatus, SessionView, TimelineNode, TimelinePoint
from .bus import Evidence, QFamily, Question, Resolution
from .escalation import (CitedKnowledge, ContributionDraft, ContributionStat, LeakHit, PMDraft, PointsDraft, RDDraft,
                         ReqItem, Requirement, RequirementView, ReuseProposal, SheetDraft, Trial)
from .events import Event, EventKind
from .gateway import LLMRequest, LLMResponse, LLMToolCall, Message, ModelGateway, Tier, Usage
from .jev import JevDecision, S1Answer, S1Choice, S1Noul, S1Question, S1Result, S1Score, System1Client
from .jue import (Discoverer, Family, JueObject, JueOutput, JueRecord, JueState, JueTemplate, ObjectType,
                  QuestionModel, ScoredDecision)
from .knowledge import (CUSTOMER_VERSIONS, KIND_LEVEL, AuditRecord, BlockedHint, CardSection, DecryptGrant, KnowledgeHit,
                        KnowledgeUnit, KUKind, LedgerEntry, RecommendationCard, Version)
from .meter import Meter, MeterRecord
from .seeds import (ROLE_LEVEL, Actor, Candidate, Case, Level, Phenomenon, Product, Role, Seeds, SlotDef,
                    Translation)
from .session import (AskHint, AssistantReply, CustomerProfile, ExtractedSlot, ExtractionResult, Intent, NeedState,
                      Recommendation, Session, SlotFill, Turn)
from .sim import Injection, NeedCard, WeekItem

__all__ = [
    "SHANGHAI", "BaseModel",
    "Role", "Level", "ROLE_LEVEL", "Actor", "SlotDef", "Phenomenon", "Product", "Case", "Translation", "Seeds",
    "Candidate",
    "KUKind", "KIND_LEVEL", "KnowledgeUnit", "KnowledgeHit", "BlockedHint", "Version", "CUSTOMER_VERSIONS", "DecryptGrant",
    "CardSection", "RecommendationCard", "AuditRecord", "LedgerEntry",
    "Intent", "Turn", "SlotFill", "CustomerProfile", "NeedState", "ExtractedSlot", "ExtractionResult", "AskHint",
    "Recommendation", "AssistantReply", "Session",
    "S1Noul", "S1Choice", "S1Score", "S1Question", "S1Answer", "S1Result", "System1Client", "JevDecision",
    "ObjectType", "Family", "JueObject", "JueState", "JueTemplate", "ScoredDecision", "JueOutput", "JueRecord", "QuestionModel",
    "Discoverer",
    "QFamily", "Evidence", "Resolution", "Question",
    "ReqItem", "PMDraft", "RDDraft", "SheetDraft", "LeakHit", "PointsDraft", "ContributionDraft", "ReuseProposal", "Requirement", "Trial",
    "CitedKnowledge", "RequirementView", "ContributionStat",
    "EventKind", "Event",
    "NeedCard", "Injection", "WeekItem",
    "Tier", "Message", "LLMRequest", "LLMToolCall", "Usage", "LLMResponse", "ModelGateway",
    "MeterRecord", "Meter",
    "SessionView", "ReuseView", "RunStatus", "TimelinePoint", "TimelineNode", "JueTimeline",
    "ToolKind", "ToolSpec", "ToolResult", "PendingAction", "AgentStep", "AgentMessage", "Conversation",
]
