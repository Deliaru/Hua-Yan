"""披露网关：在客户×产品的授权上限内输出卡片。"""
from huayan.contracts import Actor, CardSection, DecryptGrant, RecommendationCard, Version
from .permission import PermissionDenied, colleague_l3, level_of
from .store import KnowledgeBase

VERSIONS = ("product", "product_usage", "full_mechanism", "internal")


def cap(viewer: Actor, customer_id: str, product_id: str, grants: list[DecryptGrant]) -> Version:
    """L0 客户自己看固定 product_usage（解密走业务员，见 v6）。"""
    if level_of(viewer) == 3:
        return "internal"
    if level_of(viewer) == 1 and any(g.customer_id == customer_id and g.product_id == product_id for g in grants):
        return "full_mechanism"
    return "product_usage"


def render(product_id: str, version: Version, viewer: Actor, kb: KnowledgeBase, *,
           session_id: str, customer_id: str, grants: list[DecryptGrant]) -> RecommendationCard:
    product = kb.product(product_id)
    valid_grants = [g for g in grants if g.approved_by == product.owner]
    allowed = cap(viewer, customer_id, product_id, valid_grants)
    if viewer.role == "customer" and viewer.id != customer_id:
        raise PermissionDenied("不能查看其他客户的推荐卡片")
    if VERSIONS.index(version) > VERSIONS.index(allowed) or (
            kb.is_frozen(viewer.id) and version in ("full_mechanism", "internal")):
        kb._deny(viewer, [product_id], "披露版本超过权限上限", session_id)
        raise PermissionDenied("披露版本超过权限上限")
    kinds = ["sheet"]
    if version != "product":
        kinds.append("usage")
    if version in ("full_mechanism", "internal"):
        kinds.append("mechanism")
    if version == "internal":
        kinds.append("formula")
    # 读取位于知识层内部；只有通过上述授权校验的机理可以跨层披露。
    units = [kb._units[f"ku:{kind}:{product_id}"] for kind in kinds]
    if level_of(viewer) <= 1:      # v6：L0 公开案例（客户与业务员）、L1 内部评价（仅业务员）
        units += [u for u in kb.list(viewer, kinds=["public_case", "report"]) if u.product_id == product_id]
    if level_of(viewer) == 2:
        units += [u for u in kb.list(viewer, kinds=["case"])
                  if set(u.phenomenon_ids) & set(product.solves)]
    if version == "internal":
        units += [u for u in kb.list(viewer, kinds=["trial"]) if u.product_id == product_id]
        units = [u for u in units if not colleague_l3(viewer, u) or kb._readable(viewer, u)]   # 同事的机理、配方只经授予可读
    for unit in units:
        decrypted = unit.kind == "mechanism" and unit.decryptable and allowed == "full_mechanism"
        if unit.level > level_of(viewer) and not decrypted:
            raise PermissionDenied("卡片包含超出查看者权限的知识")
    grant = next((g for g in reversed(valid_grants) if g.customer_id == customer_id and g.product_id == product_id), None)
    return RecommendationCard(session_id=session_id, viewer=viewer.id, product_id=product_id,
        version=version, sections=[CardSection(title=u.title,
            text=grant.text if level_of(viewer) == 1 and u.kind == "mechanism" and grant and grant.text else u.text,
            ku_id=u.id, level=u.level) for u in units],
        note="机理已经研发审批解密" if level_of(viewer) == 1 and version == "full_mechanism" else "")
