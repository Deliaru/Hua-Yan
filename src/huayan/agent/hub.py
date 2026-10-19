"""契约 ⑭：AgentHub。管理每个人的助手对话、确认卡（PendingAction）、派单与执行轨迹；HuayanApp.agents。"""
from huayan.clock import get_clock
from huayan.contracts import AgentMessage, AgentStep, Conversation, PendingAction, ToolResult
from huayan.knowledge import PermissionDenied

from .loop import OUT_OF_STEPS, run_turn
from .tools import TOOLS, ToolContext

OFFLINE = "助手需要大模型（当前离线）。"


class AgentHub:
    def __init__(self, app):
        self.app = app
        self._conversations: dict[str, Conversation] = {}
        self._pending: dict[str, PendingAction] = {}
        self._steps: list[AgentStep] = []
        self._dispatched: set[tuple[str, int]] = set()

    # ---- 对话 ----

    def context(self, actor_id: str, session_id: str | None = None) -> ToolContext:
        actor = self.app.actors.get(actor_id)
        if actor is None or actor.role not in ("sales", "pm", "rd"):
            raise PermissionDenied("只有业务员、产品经理、研发配有角色助手")
        if actor.role == "sales":
            if session_id is None:
                raise ValueError("业务员助手必须绑定客户会话")
            self.app.view_session(session_id, actor_id)      # 由门面校验会话归属：只能绑定自己参与的会话
        return ToolContext(self.app, actor, f"conv:{actor_id}:{session_id or 'inbox'}", session_id)

    def chat(self, actor_id: str, text: str, session_id: str | None = None,
             focus: str | None = None) -> Conversation:
        ctx = self.context(actor_id, session_id)
        ctx.focus = focus
        return self._respond(ctx, AgentMessage(role="principal", text=text, at=get_clock().now(), target=focus))

    def notify(self, actor_id: str, text: str, session_id: str | None = None) -> Conversation:
        ctx = self.context(actor_id, session_id)
        return self._respond(ctx, AgentMessage(role="system", text=text, at=get_clock().now()))

    def _respond(self, ctx: ToolContext, message: AgentMessage) -> Conversation:
        conv = self._conversation(ctx)
        conv.messages.append(message)
        if self.app.config["gateway_mock"]:
            conv.messages.append(AgentMessage(role="system", text=OFFLINE, at=get_clock().now(), target=ctx.focus))
        else:
            self.app.emit("agent_start", actor=ctx.principal.id, conversation_id=conv.id)
            conv.messages += run_turn(conv, ctx, self, self.app.gateway)
            self.app.emit("agent_end", actor=ctx.principal.id, conversation_id=conv.id, index=len(conv.messages) - 1)
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
            self.app._agent_drafting = spec.kind == "draft"
            try:
                return _run(fn, ctx, spec.params, args)
            finally:
                self.app._agent_drafting = False
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

    # ---- 派单 ----

    def dispatch(self) -> list[Conversation]:
        """只派觉已提出的问题；准备被撤回后，同一问题可再次起草。"""
        out = []
        exhausted = set()
        while True:
            rounds = {}
            for event in self.app.events.query(["question_prepared"]):
                qid = event.payload["question_id"]
                rounds[qid] = rounds.get(qid, 0) + 1
            pending = [q for q in self.app.bus.list() if q.prepared_at is None
                       and q.id not in exhausted
                       and q.owner_role in ("sales", "pm", "rd", "supervisor")
                       and (q.id, rounds.get(q.id, 0)) not in self._dispatched]
            if not pending:
                break
            for q in pending:
                if q.status != "open" or q.prepared_at is not None:
                    continue
                template = self.app.templates.get(q.template_id) if q.template_id else None
                if q.signer_role is None and template and template.auto_action:
                    self.app.auto_execute(q.id)      # v6 契约 6.1：低风险推进由觉自动执行
                    self._dispatched.add((q.id, rounds.get(q.id, 0)))
                    continue
                if q.owner_id is None or (q.owner_role == "pm" and q.owner_id != "pm:agent"):
                    # v6：自助会话没有业务员（回问由客户在对话里直接回答）；真人产品经理的问题留在待办，不派 Agent
                    self._dispatched.add((q.id, rounds.get(q.id, 0)))
                    continue
                session_id = q.refs.get("session_id") if q.owner_role == "sales" else None
                text = (f"{q.id}（{q.family}）：{q.title}。引用：{q.refs}。"
                        f"证据：{'；'.join(e.summary for e in q.evidence) or '无'}。请为此问题准备草稿，不签字。")
                if q.family == "qi_grant" and "capability_id" in q.refs:
                    self.app.mark_prepared(q.id, q.owner_id)
                    self._dispatched.add((q.id, rounds.get(q.id, 0)))
                    continue
                if self.app.config["gateway_mock"]:
                    text += "\n" + self._prepare_offline(q)
                    ctx = ToolContext(self.app, self.app.actors[q.owner_id],
                                      f"conv:{q.owner_id}:{session_id or 'inbox'}", session_id)
                    conv = self._conversation(ctx)
                    conv.messages.append(AgentMessage(role="system", text=text, at=get_clock().now(), target=q.object_id))
                    self._save(conv)
                    out.append(conv.model_copy(deep=True))
                elif q.owner_role != "supervisor":   # 主管没有 Agent：拼凑风险无需准备，直接待签（REPLAN 4.3 主人为「—」）
                    self.app.emit("dispatch", actor=q.owner_id, family=q.family)
                    out.append(self.notify(q.owner_id, text, session_id))
                    if out[-1].messages[-1].text == OUT_OF_STEPS:
                        exhausted.add(q.id)
                        continue  # 本轮不重试它，继续派其他问题；下次 dispatch 再试。
                if q.status == "open" and q.signer_role is not None:
                    self.app.mark_prepared(q.id, q.owner_id)
                self._dispatched.add((q.id, rounds.get(q.id, 0)))
        return out

    def _prepare_offline(self, q) -> str:
        """WP-C 指定的离线骨架；只起草，签字仍由人调用门面。"""
        if q.family == "accept_requirement":
            self.app.draft_requirement(q.refs["requirement_id"], q.owner_id)
        elif q.family == "confirm_translation":
            self.app.translate_requirement(q.refs["requirement_id"], q.owner_id)
        elif q.family == "release":
            self.app.package_sheet(q.refs["requirement_id"], q.owner_id)
        elif q.family == "reuse_product":
            self.app.save_reuse_proposal(q.refs["requirement_id"], None, [], "",
                                         "离线模式：未检索现成产品", q.owner_id)
        elif q.family == "scope_update":
            return "离线模式：研发已判定适用，待产品经理决定是否扩展适用范围。"
        elif q.family == "opportunity":
            reqs = [self.app.requirement_view(rid, q.owner_id).requirement
                    for rid in q.refs["requirement_ids"].split(",")]
            reqs.sort(key=lambda req: req.created_at)
            self.app.save_merge_proposal(q.id, reqs[0].id, [req.id for req in reqs[1:]],
                                         "离线模式：按主题规则合并，未经产品经理 Agent 判断", q.owner_id)
        else:
            return "离线，无草稿。" if q.signer_role is not None else "离线，仅提示，不标记准备完成。"
        return "离线模式：已由规则骨架起草，未经角色 Agent 判断。"

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
        self.app.emit("step", actor=step.principal, step=step.step, tool=step.tool, blocked=bool(step.blocked),
                      pending=bool(step.pending_action_id), ok=not step.result_summary.startswith('{"ok":false'))
        _append(self.app.run_dir / "agent_trace.jsonl", step.model_dump_json())

    def _log_pending(self, action: PendingAction) -> None:
        _append(self.app.run_dir / "pending.jsonl", action.model_dump_json())

    def _save(self, conv: Conversation) -> None:
        path = self.app.run_dir / "conversations"
        path.mkdir(exist_ok=True)
        (path / f"{conv.id.replace(':', '_')}.json").write_text(conv.model_dump_json(), encoding="utf-8")


def _run(fn, ctx: ToolContext, params, args: dict) -> ToolResult:
    """门面 / 知识库的拒绝与校验失败（含不存在的 id）原样回给模型；其他异常照常抛出。"""
    try:
        return fn(ctx, params.model_validate(args))
    except (PermissionDenied, ValueError) as exc:
        return ToolResult(ok=False, error=str(exc))


def _append(path, line: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
