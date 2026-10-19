"""层级权限；客户解密例外只在披露网关中处理。"""
from huayan.contracts import ROLE_LEVEL, Actor, KnowledgeUnit, Level


class PermissionDenied(Exception):
    pass


def level_of(actor: Actor) -> Level:
    return ROLE_LEVEL[actor.role]


def holder(ku: KnowledgeUnit) -> str:
    return ku.confirmed_by if ku.kind == "claim" else ku.owner


def colleague_l3(actor: Actor, ku: KnowledgeUnit) -> bool:
    """同层研发的知识：L3、归属真人研发、读者是另一位研发（系统内部身份不受此限）。"""
    return (ku.level == 3 and holder(ku).startswith("rd:") and actor.role == "rd"
            and actor.id != holder(ku) and not actor.id.startswith("system:"))


def can_read(actor: Actor, ku: KnowledgeUnit, shared: frozenset[str] = frozenset()) -> bool:
    """shared：授予读者本人的 active share 能力所指的知识 id。"""
    return ku.level <= level_of(actor) and (not colleague_l3(actor, ku) or ku.id in shared)
