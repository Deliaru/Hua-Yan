"""层级权限；客户解密例外只在披露网关中处理。"""
from huayan.contracts import ROLE_LEVEL, Actor, KnowledgeUnit, Level


class PermissionDenied(Exception):
    pass


def level_of(actor: Actor) -> Level:
    return ROLE_LEVEL[actor.role]


def can_read(actor: Actor, ku: KnowledgeUnit) -> bool:
    return ku.level <= level_of(actor)
