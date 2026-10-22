"""契约 ⑭：AgentHub。管理每个人的助手对话、确认卡（PendingAction）、派单与执行轨迹；HuayanApp.agents。"""
import json
import re
from typing import Literal

import httpx
import openai

from huayan.clock import get_clock
from huayan.contracts import AgentMessage, AgentStep, Conversation, LLMRequest, Message, PendingAction, Tier, ToolResult
from huayan.contracts._base import BaseModel
from huayan.gateway.client import StructuredOutputError
from huayan.knowledge import PermissionDenied

from .loop import OUT_OF_STEPS, PROMPTS, run_turn
from .tools import TOOLS, ToolContext, agent_id

OFFLINE = "助手需要大模型（当前离线）。"
PUSHBACKS = 1          # v8：准备没落在对象上时，把缺什么退回给 Agent 再做的次数
ATTEMPTS = 2           # 同一问题最多派几次；仍没准备好就留在「准备中」，记一条 Agent 错误
# V9.2：模型接口出的错（断网、超时、限流、结构化输出不合格）。这类失败不占派单次数，整项留着重跑
MODEL_ERRORS = (openai.APIError, httpx.HTTPError, StructuredOutputError, TimeoutError)


class MemoryOp(BaseModel):
    op: Literal["add", "delete"]
    id: str = ""                                    # delete：要删的记忆编号
    kind: Literal["habit", "fact", "lesson"] = "lesson"
    text: str = ""
    why: str = ""
    refs: list[str] = []


class MemoryOps(BaseModel):
    ops: list[MemoryOp]


class AgentHub:
    def __init__(self, app):
        self.app = app
        self._conversations: dict[str, Conversation] = {}
        self._pending: dict[str, PendingAction] = {}
        self._steps: list[AgentStep] = []
        self._dispatched: set[tuple[str, int]] = set()
        self._attempts: dict[str, int] = {}
        self.failures: dict[str, dict] = {}     # V9.2：问题 → 最近一次因模型接口失败没准备成的原因；准备成了就清掉

    # ---- 对话 ----

    def _conv_id(self, actor_id: str, session_id: str | None, thread: str | None) -> str:
        # v8：agent_threads=object 时，收件箱按工作对象分开（req:4、knowledge:… 各一段），不让旧回复被照抄
        if thread and not session_id and self.app.config["agent_threads"] == "object":
            return f"conv:{actor_id}:{thread.split('/')[0]}"
        return f"conv:{actor_id}:{session_id or 'inbox'}"

    def conversation(self, actor_id: str, session_id: str | None = None, thread: str | None = None) -> Conversation | None:
        conv = self._conversations.get(self._conv_id(actor_id, session_id, thread))
        return conv and conv.model_copy(deep=True)

    def context(self, actor_id: str, session_id: str | None = None, thread: str | None = None) -> ToolContext:
        actor = self.app.actors.get(actor_id)
        if actor is None or actor.role not in ("sales", "pm", "rd"):
            raise PermissionDenied("只有业务员、产品经理、研发配有角色助手")
        if actor.role == "sales":
            if session_id is None:
                raise ValueError("业务员助手必须绑定客户会话")
            self.app.view_session(session_id, actor_id)      # 由门面校验会话归属：只能绑定自己参与的会话
        return ToolContext(self.app, actor, self._conv_id(actor_id, session_id, thread), session_id)

    def chat(self, actor_id: str, text: str, session_id: str | None = None,
             focus: str | None = None) -> Conversation:
        ctx = self.context(actor_id, session_id, focus)
        ctx.focus = focus
        return self._respond(ctx, AgentMessage(role="principal", text=text, at=get_clock().now(), target=focus))

    def notify(self, actor_id: str, text: str, session_id: str | None = None, thread: str | None = None) -> Conversation:
        ctx = self.context(actor_id, session_id, thread)
        return self._respond(ctx, AgentMessage(role="system", text=text, at=get_clock().now()))

    def _respond(self, ctx: ToolContext, message: AgentMessage) -> Conversation:
        conv = self._conversation(ctx)
        conv.messages.append(message)
        if self.app.config["gateway_mock"]:
            conv.messages.append(AgentMessage(role="system", text=OFFLINE, at=get_clock().now(), target=ctx.focus))
        else:
            self.app.emit("agent_start", actor=ctx.principal.id, conversation_id=conv.id)
            ctx.instructed = message.role == "principal"      # v8 收口：委托人亲口交代的这一轮，起草记在委托人名下
            try:
                with self.app.drafting():                       # 这一轮起草完再由觉评估
                    conv.messages += run_turn(conv, ctx, self, self.app.gateway)
            except MODEL_ERRORS:
                # V9.2：模型失败时这一轮整个撤回，委托人重发同一句就是重跑；已经落在对象上的草稿以对象为准
                conv.messages.remove(message)
                self.app.emit("agent_end", actor=ctx.principal.id, conversation_id=conv.id, index=len(conv.messages) - 1)
                raise
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
            # 委托人亲口交代、且改的是他这一轮打开的那张单，才记在委托人名下；顺手改别的单仍是 Agent 起草
            own = ctx.instructed and args.get("req_id") == (ctx.focus or "").split("/")[0]
            self.app._agent_drafting = spec.kind == "draft" and not own
            try:
                result = _run(fn, ctx, spec.params, args)
            finally:
                self.app._agent_drafting = False
            if not result.ok:
                self.error(ctx.principal.id, "tool_rejected", tool=name, detail=result.error)
            return result
        try:
            params = spec.params.model_validate(args).model_dump()
        except ValueError as exc:
            self.error(ctx.principal.id, "tool_rejected", tool=name, detail=str(exc))
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

    def _rounds(self) -> dict[str, int]:
        rounds = {}
        for event in self.app.events.query(["question_prepared"]):
            qid = event.payload["question_id"]
            rounds[qid] = rounds.get(qid, 0) + 1
        return rounds

    def pending_dispatch(self) -> list:
        """觉已提出、还没准备、这一轮还没派过的问题（派的次数用完的算派过）。"""
        rounds = self._rounds()
        return [q for q in self.app.bus.list() if q.prepared_at is None
                and q.owner_role in ("sales", "pm", "rd", "supervisor")
                and (q.id, rounds.get(q.id, 0)) not in self._dispatched]

    def conversation_of(self, q) -> str:
        """问题派到哪段对话：业务员按客户会话，其余按工作对象（agent_threads=object）或收件箱。"""
        session_id = q.refs.get("session_id") if q.owner_role == "sales" else None
        return self._conv_id(q.owner_id, session_id, q.refs.get("requirement_id") or q.object_id)

    def dispatch(self, only: set[str] | None = None) -> list[Conversation]:
        """只派觉已提出的问题；准备被撤回后，同一问题可再次起草。only：只派这几个（v8 模拟器按对话分组并发）。"""
        out = []
        exhausted = set()
        while True:
            rounds = self._rounds()
            pending = [q for q in self.pending_dispatch() if q.id not in exhausted and (only is None or q.id in only)]
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
                try:
                    session_id = q.refs.get("session_id") if q.owner_role == "sales" else None
                    target = q.refs.get("requirement_id") or q.refs.get("session_id") or q.object_id
                    text = (f"{target}：{q.title}（觉的问题 {q.id}，{q.family}；调用工具时用 {target}，不要用问题编号）。引用：{q.refs}。"
                            f"证据：{'；'.join(e.summary for e in q.evidence) or '无'}。")
                    # 授予现有能力：形式与目标层已由觉算出，Agent 只告知委托人，不起草
                    text += ("请告知委托人待签的授予，不起草，不签字。" if q.family == "qi_grant" and "capability_id" in q.refs
                             else "请告知委托人：同事申请查看这条知识，附上申请人碰到过它的需求单，不起草，不签字。"
                             if q.family == "qi_grant" and "requester" in q.refs
                             else f"请起草一句可以写给 L{q.refs['audience']} 的话，不含结论原文与机理，交委托人在签字区改定，不签字。"
                             if q.family == "qi_grant" and q.refs.get("form") == "statement"
                             else "请为此问题准备草稿，不签字。")
                    with self.app.drafting():          # v8 收口：准备（含退回再做）结束后觉才评估，中间稿不触发问题
                        if self.app.config["gateway_mock"]:
                            text += "\n" + self._prepare_offline(q)
                            ctx = ToolContext(self.app, self.app.actors[q.owner_id], self.conversation_of(q), session_id)
                            conv = self._conversation(ctx)
                            conv.messages.append(AgentMessage(role="system", text=text, at=get_clock().now(), target=q.object_id))
                            self._save(conv)
                            out.append(conv.model_copy(deep=True))
                        elif q.owner_role != "supervisor":   # 主管没有 Agent：拼凑风险无需准备，直接待签（REPLAN 4.3 主人为「—」）
                            self.app.emit("dispatch", actor=q.owner_id, family=q.family)
                            thread = q.refs.get("requirement_id") or q.object_id
                            out.append(self.notify(q.owner_id, text, session_id, thread))
                            # 步数用完也以对象为准：草稿齐了照常标记已准备
                            if out[-1].messages[-1].text == OUT_OF_STEPS and not (q.signer_role and not self.app.preparation_gap(q.id)):
                                self._give_up(q, rounds, exhausted, "out_of_steps", OUT_OF_STEPS)
                                continue  # 本轮不重试它，继续派其他问题；下次 dispatch 再试。
                            # v8：准备好没有以对象为准；缺什么就退回给 Agent 再做，Agent 说「已就绪」不算
                            for _ in range(PUSHBACKS):
                                gap = q.signer_role and self.app.preparation_gap(q.id)
                                if not gap:
                                    break
                                self.error(q.owner_id, "prepare_missing", question_id=q.id, detail=gap)
                                out.append(self.notify(q.owner_id, f"{q.id} 还没有准备好：{gap}。是否准备好以对象上的草稿为准，"
                                                                   "不以你的回复为准。", session_id, thread))
                            gap = q.signer_role and self.app.preparation_gap(q.id)
                            if gap:
                                self._give_up(q, rounds, exhausted, "prepare_failed", gap)
                                continue
                    if q.status == "open" and q.signer_role is not None:
                        self.app.mark_prepared(q.id, q.owner_id)
                    self._dispatched.add((q.id, rounds.get(q.id, 0)))
                except MODEL_ERRORS as exc:
                    # V9.2：模型接口失败，这一项整个留到下一次 dispatch 重跑（或委托人点重跑），不影响别的问题
                    self.failures[q.id] = {"at": get_clock().now().isoformat(), "error": f"{type(exc).__name__}: {exc}"}
                    self.error(q.owner_id, "model_failed", question_id=q.id, detail=self.failures[q.id]["error"])
                    exhausted.add(q.id)
                    continue
                self.failures.pop(q.id, None)
        return out

    def retry(self, question_id: str, by: str) -> dict:
        """V9.2：把一项准备整个重跑（模型失败或派单次数用完之后）。能看到这个问题的人都可以点；下一次 dispatch 重新派。"""
        if question_id not in {q.id for q in self.app.questions(by)}:
            raise PermissionDenied("只能重跑自己能看到的问题")
        q = self.app.bus.get(question_id)
        if q.status != "open" or q.prepared_at is not None:
            raise ValueError("这一项已经准备好或已处理，不需要重跑")
        self._dispatched = {d for d in self._dispatched if d[0] != question_id}
        self._attempts.pop(question_id, None)
        self.failures.pop(question_id, None)
        return {"question_id": question_id}

    def failures_for(self, viewer: str) -> dict[str, dict]:
        visible = {q.id for q in self.app.questions(viewer)}
        return {qid: f for qid, f in self.failures.items() if qid in visible}

    def _give_up(self, q, rounds, exhausted, kind, detail) -> None:
        """这次没准备好：记一条 Agent 错误；派的次数没用完就下次 dispatch 再派，用完就留在「准备中」由人看见。"""
        self._attempts[q.id] = self._attempts.get(q.id, 0) + 1
        self.error(q.owner_id, kind, question_id=q.id, detail=detail, attempt=self._attempts[q.id])
        exhausted.add(q.id)
        if self._attempts[q.id] >= ATTEMPTS:
            self._dispatched.add((q.id, rounds.get(q.id, 0)))

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
        elif q.family == "qi_grant" and "capability_id" in q.refs:
            layer = "客户层" if q.refs["audience"] == "0" else "业务员层"
            return f"离线模式：觉提出了「是否把这项能力授予{layer}」，形式与依据见问题卡，请在签字区决定。"
        elif q.family == "qi_grant" and "requester" in q.refs:
            reqs = q.refs.get("requirement_ids") or "无"
            return f"离线模式：{q.refs['requester']} 申请查看这条知识（碰到过它的需求单：{reqs}），请在签字区决定是否授予。"
        elif q.family == "opportunity":
            reqs = [self.app.requirement_view(rid, q.owner_id).requirement
                    for rid in q.refs["requirement_ids"].split(",")]
            reqs.sort(key=lambda req: req.created_at)
            self.app.save_merge_proposal(q.id, reqs[0].id, [req.id for req in reqs[1:]],
                                         "离线模式：按主题规则合并，未经产品经理 Agent 判断", q.owner_id)
        else:
            return "离线，无草稿。" if q.signer_role is not None else "离线，仅提示，不标记准备完成。"
        return "离线模式：已由规则骨架起草，未经角色 Agent 判断。"

    # ---- v8：Agent 的错误记在 Agent 名下（agent:<委托人>），不算委托人的；写 runs/<run_id>/agent_errors.jsonl ----

    def error(self, principal: str, kind: str, **detail) -> None:
        _append(self.app.run_dir / "agent_errors.jsonl", json.dumps(
            {"at": get_clock().now().isoformat(), "agent": agent_id(principal), "principal": principal, "kind": kind,
             **detail}, ensure_ascii=False))

    def errors(self, principal: str | None = None) -> list[dict]:
        path = self.app.run_dir / "agent_errors.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
        return [r for r in rows if principal in (None, r["principal"])]

    # ---- v8：收工归纳记忆 ----

    def consolidate(self, principal: str, since) -> list[str]:
        """把当天的决策记录（程序生成）与已有记忆交给该助手自己的模型：合并、删旧、写新；写入仍经门面校验。"""
        records = self.app.decision_records(principal, since) + [
            f"你的错误：{r['kind']} {r.get('question_id', r.get('tool', ''))} {r.get('detail', '')}"
            for r in self.errors(principal) if r["at"] >= since.isoformat()]
        if not records:
            return []
        actor = self.app.actors[principal]
        memories = [m.model_dump(mode="json", include={"id", "kind", "text", "why", "refs"})
                    for m in self.app.memories(principal)]
        prompt = (PROMPTS / "memory_consolidate.md").read_text(encoding="utf-8").format(name=actor.name, id=principal)
        out, _ = self.app.gateway.structured(LLMRequest(tier=Tier.FAST, caller=f"agent:{actor.role}", temperature=0,
            messages=[Message(role="system", content=prompt), Message(role="user", content=json.dumps(
                {"records": records, "memories": memories}, ensure_ascii=False))]), MemoryOps)
        done = []
        for op in out.ops:
            try:
                if op.op == "delete":
                    self.app.forget(op.id, principal)
                    done.append(f"删 {op.id}")
                else:
                    done.append(f"记 {self.app.remember(op.kind, op.text, op.why, op.refs, principal).id}")
            except (PermissionDenied, ValueError) as exc:
                self.error(principal, "memory_rejected", detail=str(exc))
        return done

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
        (path / f"{re.sub(r'[^\w.-]', '_', conv.id)}.json").write_text(conv.model_dump_json(), encoding="utf-8")


def _run(fn, ctx: ToolContext, params, args: dict) -> ToolResult:
    """门面 / 知识库的拒绝与校验失败（含不存在的 id）原样回给模型；其他异常照常抛出。"""
    try:
        return fn(ctx, params.model_validate(args))
    except (PermissionDenied, ValueError) as exc:
        return ToolResult(ok=False, error=str(exc))


def _append(path, line: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
