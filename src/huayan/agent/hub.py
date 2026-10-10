"""契约 ⑭：AgentHub。管理每个人的助手对话、确认卡（PendingAction）、派单与执行轨迹；HuayanApp.agents。"""
from collections import Counter

from huayan.clock import get_clock
from huayan.contracts import AgentMessage, AgentStep, Conversation, PendingAction, ToolResult
from huayan.knowledge import PermissionDenied

from .loop import run_turn
from .tools import TOOLS, ToolContext

OFFLINE = "助手需要大模型（当前离线）。"


class AgentHub:
    def __init__(self, app):
        self.app = app
        self._conversations: dict[str, Conversation] = {}
        self._pending: dict[str, PendingAction] = {}
        self._steps: list[AgentStep] = []
        self._dispatched: set[str] = set()

    # ---- 对话 ----

    def context(self, actor_id: str, session_id: str | None = None) -> ToolContext:
        actor = self.app.actors.get(actor_id)
        if actor is None or actor.role not in ("sales", "pm", "rd"):
            raise PermissionDenied("只有业务员、产品经理、研发配有角色助手")
        if actor.role == "sales" and session_id is None:
            raise ValueError("业务员助手必须绑定客户会话")
        return ToolContext(self.app, actor, f"conv:{actor_id}:{session_id or 'inbox'}", session_id)

    def chat(self, actor_id: str, text: str, session_id: str | None = None) -> Conversation:
        ctx = self.context(actor_id, session_id)
        return self._respond(ctx, AgentMessage(role="principal", text=text, at=get_clock().now()))

    def notify(self, actor_id: str, text: str, session_id: str | None = None) -> Conversation:
        ctx = self.context(actor_id, session_id)
        return self._respond(ctx, AgentMessage(role="system", text=text, at=get_clock().now()))

    def _respond(self, ctx: ToolContext, message: AgentMessage) -> Conversation:
        conv = self._conversation(ctx)
        conv.messages.append(message)
        if self.app.config["gateway_mock"]:
            conv.messages.append(AgentMessage(role="system", text=OFFLINE, at=get_clock().now()))
        else:
            conv.messages += run_turn(conv, ctx, self, self.app.gateway)
        self._save(conv)
        return conv.model_copy(deep=True)

    def _conversation(self, ctx: ToolContext) -> Conversation:
        return self._conversations.setdefault(ctx.conversation_id, Conversation(
            id=ctx.conversation_id, principal=ctx.principal.id, role=ctx.principal.role, session_id=ctx.session_id))

    # ---- 工具执行入口：read / draft 直接执行，effect 挂起为确认卡 ----

    def call_tool(self, ctx: ToolContext, name: str, args: dict) -> ToolResult:
        if name not in TOOLS or ctx.principal.role not in TOOLS[name][0].roles:
            return ToolResult(ok=False, error=f"你的委托人没有工具 {name}")
        spec, fn = TOOLS[name]
        if spec.kind != "effect":
            return _run(fn, ctx, spec.params, args)
        try:
            params = spec.params.model_validate(args).model_dump()
        except ValueError as exc:
            return ToolResult(ok=False, error=str(exc))
        self._conversation(ctx)                                    # 确认结果写回这段对话
        action = PendingAction(id=f"act:{len(self._pending) + 1}", conversation_id=ctx.conversation_id,
                               principal=ctx.principal.id, tool=name, args=params,
                               summary=spec.confirm_text.format(**params), created_at=get_clock().now())
        self._pending[action.id] = action
        self._log_pending(action)
        self.app.events.append("agent_action_proposed", ctx.principal.id, {"action_id": action.id, "tool": name,
                               "principal": ctx.principal.id, "conversation_id": ctx.conversation_id},
                               session_id=ctx.session_id)
        return ToolResult(data={"summary": action.summary, "status": "等待委托人在确认卡上确认"},
                          pending_action_id=action.id)

    # ---- 确认卡 ----

    def approve(self, action_id: str, by: str) -> PendingAction:
        action, conv = self._decide(action_id, by, "approved")
        spec, fn = TOOLS[action.tool]
        action.result = _run(fn, ToolContext(self.app, self.app.actors[by], conv.id, conv.session_id), spec.params, action.args)
        outcome = "已执行" if action.result.ok else f"执行失败：{action.result.error}"
        self._close(action, conv, f"{by} 已确认：{action.summary}。{outcome}")
        if action.result.ok:
            self._hand_over(action, action.result.data)
        return action.model_copy(deep=True)

    def reject(self, action_id: str, by: str, note: str = "") -> PendingAction:
        action, conv = self._decide(action_id, by, "rejected")
        self._close(action, conv, f"{by} 已拒绝：{action.summary}。{note}")
        return action.model_copy(deep=True)

    def _decide(self, action_id: str, by: str, status: str) -> tuple[PendingAction, Conversation]:
        action = self._pending[action_id]
        if by != action.principal:
            raise PermissionDenied("只有委托人本人可以确认或拒绝")
        if action.status != "pending":
            raise ValueError(f"该动作已{action.status}")
        action.status, action.decided_at = status, get_clock().now()
        return action, self._conversations[action.conversation_id]

    def _close(self, action: PendingAction, conv: Conversation, text: str) -> None:
        conv.messages.append(AgentMessage(role="system", text=text, at=get_clock().now(), pending_action_ids=[action.id]))
        self._save(conv)
        self._log_pending(action)
        self.app.events.append("agent_action_decided", action.principal, {"action_id": action.id, "tool": action.tool,
                               "principal": action.principal, "status": action.status}, session_id=conv.session_id)

    def _hand_over(self, action: PendingAction, data: dict) -> None:
        """确认后派单（契约 ⑭，写死）。"""
        name = self.app.actors[action.principal].name
        if action.tool == "confirm_requirement":
            self.notify(self._translator(data["phenomenon"]),
                        f"{name} 已确认需求单 {data['req_id']} 的产品需求（现象 {data['phenomenon']}），请起草化学语言需求单。")
        elif action.tool == "set_public_points":
            req = self.app.requirement_view(data["req_id"], action.principal).requirement
            self.notify(req.pm_confirmed_by, f"{name} 已确认需求单 {req.id} 的对外要点，请生成 L1 说明书并发布。")
        elif action.tool == "request_decrypt":
            self._dispatched.add(data["question_id"])
            self.notify(data["owner_id"], f"{name} 为客户申请了解密（问题 {data['question_id']}），请审批。")

    def _translator(self, phenomenon: str) -> str:
        """该现象 L3 转化对照条数最多的研发，并列取 id 最小。"""
        reader = next(a for a in self.app.actors.values() if a.role == "rd")
        counts = Counter(u.owner for u in self.app.kb.list(reader, kinds=["translation"], phenomenon=phenomenon)
                         if u.level == 3)
        return min(counts, key=lambda owner: (-counts[owner], owner))

    # ---- 派单 ----

    def dispatch(self) -> list[Conversation]:
        out = []
        for q in self.app.bus.list(status="open"):
            if q.id in self._dispatched or q.owner_role not in ("sales", "pm", "rd"):
                continue
            self._dispatched.add(q.id)
            owner = q.owner_id or min(a.id for a in self.app.actors.values() if a.role == q.owner_role)
            evidence = "；".join(e.summary for e in q.evidence) or "无"
            out.append(self.notify(owner, f"新问题 {q.id}（{q.family}）：{q.title}。证据：{evidence}",
                                   q.refs.get("session_id") if q.owner_role == "sales" else None))
        return out

    # ---- 查询 ----

    def pending(self, actor_id: str) -> list[PendingAction]:
        return [a.model_copy(deep=True) for a in self._pending.values() if a.principal == actor_id and a.status == "pending"]

    def conversations(self, actor_id: str) -> list[Conversation]:
        return [c.model_copy(deep=True) for c in self._conversations.values() if c.principal == actor_id]

    def trace(self, conversation_id: str) -> list[AgentStep]:
        return [s.model_copy(deep=True) for s in self._steps if s.conversation_id == conversation_id]

    # ---- 落盘：runs/<run_id>/conversations/、pending.jsonl、agent_trace.jsonl ----

    def record_step(self, step: AgentStep) -> None:
        self._steps.append(step)
        _append(self.app.run_dir / "agent_trace.jsonl", step.model_dump_json())

    def _log_pending(self, action: PendingAction) -> None:
        _append(self.app.run_dir / "pending.jsonl", action.model_dump_json())

    def _save(self, conv: Conversation) -> None:
        path = self.app.run_dir / "conversations"
        path.mkdir(exist_ok=True)
        (path / f"{conv.id.replace(':', '_')}.json").write_text(conv.model_dump_json(), encoding="utf-8")


def _run(fn, ctx: ToolContext, params, args: dict) -> ToolResult:
    """门面 / 知识库的拒绝与校验失败（含模型给错的 id）原样回给模型；其他异常照常抛出。"""
    try:
        return fn(ctx, params.model_validate(args))
    except KeyError as exc:
        return ToolResult(ok=False, error=f"找不到 {exc.args[0]}")
    except (PermissionDenied, ValueError) as exc:
        return ToolResult(ok=False, error=str(exc))


def _append(path, line: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
