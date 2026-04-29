"""Session controller agent chat orchestration service."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any

from backend_business.config import settings
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.agent.execution.graph_executor import GraphExecutor
from backend_business.services.agent.experience import ExperienceOrchestrator
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.runtime.scratchpad import Scratchpad
from backend_business.services.agent.runtime.scratchpad_service import ScratchpadService
from backend_business.services.agent.runtime.binding_bootstrap import (
    ensure_runtime_bindings,
    extract_tool_names,
)
from backend_business.services.requirements_manage_service import RequirementsManageService
from backend_business.services.agent.execution.topology_instantiator import (
    RuntimeContainer,
    RuntimeEdge,
    RuntimeGraphSkeleton,
    RuntimeNode,
    RuntimeSubgraph,
)

from .contracts import SessionControllerDecisionMode, SessionControllerLoopResult, SuspendReason
from .graph_template import ensure_session_controller_template
from .prompt_builder import SessionControllerPromptBuilder
from .prompt_factory import create_session_controller_prompt_builder
from .runtime_graph_recorder import SessionControllerGraphRecorder
from .session_graph_store import SessionControllerSessionGraphStore
from .tools import SessionControllerTools


logger = logging.getLogger(__name__)

_NORMAL_CONVERSATION_TOOL_TO_MODE = {
    "invoke_requirement_agent": SessionControllerDecisionMode.DELEGATE_REQUIREMENT,
    "invoke_conflict_detection": SessionControllerDecisionMode.DELEGATE_CONFLICT,
    "invoke_requirement_classification_agent": SessionControllerDecisionMode.DELEGATE_CLASSIFICATION,
    "list_requirements": SessionControllerDecisionMode.BROWSE,
    "search_requirements": SessionControllerDecisionMode.BROWSE,
}

_NORMAL_CONVERSATION_TOOL_TO_AGENT = {
    "invoke_requirement_agent": "requirement_agent",
    "invoke_conflict_detection": "conflict_detection",
    "invoke_requirement_classification_agent": "requirement_classification_agent",
}


class SessionControllerService:
    MAX_TOOL_CALL_ROUNDS = 8
    AGENT_TYPE = "session_controller"

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService | None = None,
        requirements_service: RequirementsManageService | None = None,
        tools: SessionControllerTools | None = None,
        ai_proxy_client: Any = None,
        prompt_builder: SessionControllerPromptBuilder | None = None,
    ) -> None:
        self.chat_storage = chat_storage
        self.execution_graph_service = execution_graph_service or ExecutionGraphService(
            settings.POSTGRES_DSN
        )
        self.requirements_service = requirements_service or RequirementsManageService(
            settings.POSTGRES_DSN
        )
        self.ai_proxy = ai_proxy_client or ai_proxy
        self.prompt_builder = prompt_builder or SessionControllerPromptBuilder()
        self.tools = tools
        self._session_graph_store = SessionControllerSessionGraphStore(
            chat_storage=chat_storage,
            execution_graph_service=self.execution_graph_service,
            agent_type=self.AGENT_TYPE,
        )

    def _resolve_execution_mode(self, execution_mode: str | None) -> str:
        if execution_mode is None:
            return "graph"
        normalized = str(execution_mode).strip().lower()
        if normalized != "graph":
            raise ValueError("execution_mode 仅支持 graph")
        return normalized

    def _ensure_execution_mode_enabled(self, execution_mode: str) -> None:
        if execution_mode != "graph":
            raise ValueError("execution_mode 仅支持 graph")

    def _graph_ai_proxy_client(self, *, model: str, use_thinking_mode: bool) -> Any:
        with_defaults = getattr(self.ai_proxy, "with_defaults", None)
        if callable(with_defaults):
            return with_defaults(model=model, thinking_enabled=use_thinking_mode)
        return self.ai_proxy

    @staticmethod
    def _compact_write_result(write_result: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(write_result, dict):
            return None
        compact = {
            "requirement_id": write_result.get("requirement_id"),
            "version": write_result.get("version"),
            "priority": write_result.get("priority"),
            "title": write_result.get("title"),
            "applied_updates": write_result.get("applied_updates"),
        }
        return {key: value for key, value in compact.items() if value is not None}

    def _ensure_graph_runtime_bindings(self) -> None:
        conductor_tool_names = extract_tool_names(self.tools)
        requirement_tool_names = extract_tool_names(
            self.tools.resolve_runtime_tool_executor(container_key="requirement_agent")
            if self.tools is not None
            else None
        )
        conflict_tool_names = extract_tool_names(
            self.tools.resolve_runtime_tool_executor(container_key="conflict_detection")
            if self.tools is not None
            else None
        )
        classification_tool_names = extract_tool_names(
            self.tools.resolve_runtime_tool_executor(
                container_key="requirement_classification_agent"
            )
            if self.tools is not None
            else None
        )
        binding_specs = [
            {
                "container_key": "conductor",
                "agent_type": "session_controller",
                "runtime_profile": "default",
                "implementation_type": "local",
                "capability_policy_json": {
                    "policy_id": "session_controller::conductor",
                    "scope": "conductor",
                    "tool_names": conductor_tool_names,
                },
                "quota_policy_json": {
                    "policy_id": "session_controller::conductor::quota",
                    "max_rounds": self.MAX_TOOL_CALL_ROUNDS,
                    "timeout_seconds": 180,
                    "max_concurrent_runs": 1,
                    "max_parallel_runs_per_scope": 1,
                },
                "memory_policy_json": {
                    "scope": "container",
                    "strict_memory_contract": True,
                },
            },
            {
                "container_key": "requirement_agent",
                "agent_type": "requirement_agent",
                "runtime_profile": "default",
                "implementation_type": "local",
                "capability_policy_json": {
                    "policy_id": "session_controller::requirement_agent",
                    "scope": "delegated_requirement",
                    "tool_names": requirement_tool_names,
                },
                "quota_policy_json": {
                    "policy_id": "session_controller::requirement_agent::quota",
                    "timeout_seconds": 180,
                    "max_concurrent_runs": 4,
                    "max_parallel_runs_per_scope": 1,
                },
                "memory_policy_json": {
                    "scope": "container",
                    "strict_memory_contract": True,
                },
            },
            {
                "container_key": "conflict_detection",
                "agent_type": "conflict_detection",
                "runtime_profile": "default",
                "implementation_type": "local",
                "capability_policy_json": {
                    "policy_id": "session_controller::conflict_detection",
                    "scope": "delegated_conflict",
                    "tool_names": conflict_tool_names,
                },
                "quota_policy_json": {
                    "policy_id": "session_controller::conflict_detection::quota",
                    "timeout_seconds": 180,
                    "max_concurrent_runs": 4,
                    "max_parallel_runs_per_scope": 1,
                },
                "memory_policy_json": {
                    "scope": "container",
                    "strict_memory_contract": True,
                },
            },
            {
                "container_key": "requirement_classification_agent",
                "agent_type": "requirement_classification_agent",
                "runtime_profile": "default",
                "implementation_type": "local",
                "capability_policy_json": {
                    "policy_id": "session_controller::requirement_classification_agent",
                    "scope": "delegated_classification",
                    "tool_names": classification_tool_names,
                },
                "quota_policy_json": {
                    "policy_id": "session_controller::requirement_classification_agent::quota",
                    "timeout_seconds": 180,
                    "max_concurrent_runs": 4,
                    "max_parallel_runs_per_scope": 1,
                },
                "memory_policy_json": {
                    "scope": "container",
                    "strict_memory_contract": True,
                },
            },
        ]
        ensure_runtime_bindings(self.execution_graph_service, binding_specs)

    def _inherit_session_scratchpad(
        self,
        *,
        graph_id: str,
        prev_graph_id: str | None,
        updated_by: str,
    ) -> None:
        if not prev_graph_id:
            return
        scratchpad_service = ScratchpadService(
            execution_graph_service=self.execution_graph_service,
        )
        existing_snapshot = scratchpad_service.load(graph_id).snapshot_all()
        if existing_snapshot:
            return

        previous_graph = self.execution_graph_service.get_execution_graph(prev_graph_id)
        previous_meta = (previous_graph.get("meta_json") or {}) if previous_graph else {}
        inherited_snapshot = scratchpad_service.load(prev_graph_id).snapshot_all()
        inherited_requirement_id = previous_meta.get("resolved_requirement_id")
        if not inherited_snapshot and not inherited_requirement_id:
            return

        meta_patch: dict[str, Any] = {}
        if inherited_snapshot:
            scratchpad_service.save_snapshot(
                graph_id,
                inherited_snapshot,
                updated_by=updated_by,
            )
        if inherited_requirement_id:
            meta_patch["resolved_requirement_id"] = inherited_requirement_id
        if meta_patch:
            self.execution_graph_service.patch_graph_meta(
                graph_id,
                meta_patch,
                updated_by=updated_by,
            )

    def _generate_turn_summary(
        self,
        *,
        user_message: str,
        tool_loop_reply: str,
        assistant_reply: str,
        context: dict[str, Any],
    ) -> str:
        write_result = self._compact_write_result(context.get("last_write_result"))
        payload = {
            "user_message": user_message,
            "tool_loop_reply": tool_loop_reply,
            "assistant_reply": assistant_reply,
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "dispatched_agents": context.get("dispatched_agents") or [],
            "write_result": write_result,
        }
        fallback_parts = []
        resolved_requirement_id = payload.get("resolved_requirement_id")
        if resolved_requirement_id:
            fallback_parts.append(f"当前焦点需求是 {resolved_requirement_id}。")
        if write_result and write_result.get("applied_updates"):
            fallback_parts.append(
                f"本轮已执行更新：{json.dumps(write_result['applied_updates'], ensure_ascii=False)}。"
            )
        elif payload["dispatched_agents"]:
            fallback_parts.append(
                f"本轮调用了 {', '.join(payload['dispatched_agents'])}。"
            )
        if assistant_reply.strip():
            fallback_parts.append(f"结果：{assistant_reply.strip()}")
        elif tool_loop_reply.strip():
            fallback_parts.append(f"结果：{tool_loop_reply.strip()}")
        fallback_summary = " ".join(fallback_parts) or f"用户本轮请求：{user_message}"

        try:
            response = self.ai_proxy.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你负责维护需求工程会话的跨轮记事本。"
                            "请根据给定信息写一段 1 到 3 句的中文摘要，记录本轮做了什么、"
                            "当前聚焦对象是什么、结果或待澄清点是什么。"
                            "如果目标需求可确定，优先明确写出 requirement_id。"
                            "只输出摘要正文，不要 JSON，不要客套话。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                temperature=0.2,
                max_tokens=220,
            )
            summary = str(response.get("content") or "").strip()
            return summary or fallback_summary
        except Exception:
            logger.warning("生成会话记事本摘要失败，改用回退摘要", exc_info=True)
            return fallback_summary

    def _persist_turn_summary_to_scratchpad(
        self,
        *,
        graph_id: str,
        turn_index: int,
        user_id: str,
        user_message: str,
        tool_loop_reply: str,
        assistant_reply: str,
        context: dict[str, Any],
    ) -> None:
        scratchpad = context.get("_scratchpad")
        if not isinstance(scratchpad, Scratchpad):
            scratchpad = ScratchpadService(
                execution_graph_service=self.execution_graph_service,
            ).load(graph_id, container_key="conductor")

        summary = self._generate_turn_summary(
            user_message=user_message,
            tool_loop_reply=tool_loop_reply,
            assistant_reply=assistant_reply,
            context=context,
        )
        scratchpad.write(
            "note",
            {
                "turn": turn_index,
                "summary": summary,
                "resolved_requirement_id": context.get("resolved_requirement_id"),
                "dispatched_agents": context.get("dispatched_agents") or [],
                "write_result": self._compact_write_result(context.get("last_write_result")),
            },
            source_subgraph=f"session_turn_{turn_index}",
            readonly=True,
        )
        context["_scratchpad"] = scratchpad
        context["_scratchpad_prompt_text"] = scratchpad.format_for_prompt()
        scratchpad_service = ScratchpadService(
            execution_graph_service=self.execution_graph_service,
        )
        scratchpad_service.save(
            graph_id,
            scratchpad,
            updated_by=user_id,
        )
        self.execution_graph_service.patch_graph_meta(
            graph_id,
            {
                "resolved_requirement_id": context.get("resolved_requirement_id"),
            },
            updated_by=user_id,
        )

    # ---- session helpers ----

    def _hydrate_session_graph(self, session: dict[str, Any]) -> dict[str, Any]:
        return self._session_graph_store.hydrate_session_graph(session)

    def _resolve_session_graph_target(
        self,
        *,
        session: dict[str, Any],
        project_id: str | None,
    ) -> dict[str, str | None]:
        return self._session_graph_store.resolve_session_graph_target(
            session=session,
            project_id=project_id,
        )

    def create_or_get_session(
        self,
        user_id: str,
        project_id: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._session_graph_store.create_or_get_session(
            user_id=user_id,
            project_id=project_id,
        )

    def create_session(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._session_graph_store.create_session(
            user_id=user_id,
            project_id=project_id,
            title=title,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
        )

    def update_session(
        self,
        *,
        session_id: str,
        user_id: str,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._session_graph_store.update_session(
            session_id=session_id,
            user_id=user_id,
            title=title,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
        )

    def list_sessions(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._session_graph_store.list_sessions(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
        )

    def list_session_graph_chain(
        self,
        *,
        session_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        return self._session_graph_store.list_session_graph_chain(
            session_id=session_id,
            user_id=user_id,
        )

    def delete_session(self, *, session_id: str, user_id: str) -> bool:
        return self._session_graph_store.delete_session(
            session_id=session_id,
            user_id=user_id,
        )

    def list_messages(self, *, session_id: str, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._session_graph_store.list_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )

    def get_graph_detail(self, graph_id: str) -> dict[str, Any]:
        return self._session_graph_store.get_graph_detail(graph_id)

    def get_graph(self, graph_id: str) -> dict[str, Any] | None:
        return self._session_graph_store.get_graph(graph_id)

    @staticmethod
    def _resolve_structured_assistant_reply(
        loop_result: SessionControllerLoopResult,
    ) -> str:
        if loop_result.mode == SessionControllerDecisionMode.CLARIFY:
            return (
                str(loop_result.clarification_question or "").strip()
                or str(loop_result.assistant_reply_seed or "").strip()
                or str(loop_result.tool_loop_reply or "").strip()
                or "请补充最小必要信息后我再继续。"
            )
        if loop_result.mode == SessionControllerDecisionMode.APPROVAL_PENDING:
            return (
                str(loop_result.assistant_reply_seed or "").strip()
                or str(loop_result.tool_loop_reply or "").strip()
                or (
                    "需求管理 Agent 已把变更通知发到你的移动端待审界面。"
                    "请先去手机端查看并同意该变更通知；在你同意之前，系统不会修改需求。"
                )
            )
        if loop_result.mode == SessionControllerDecisionMode.ERROR:
            return (
                str(loop_result.assistant_reply_seed or "").strip()
                or str(loop_result.tool_loop_reply or "").strip()
                or "当前请求未能完成。"
            )
        return ""

    @staticmethod
    def _normalize_graph_mode_loop_result(
        payload: dict[str, Any] | None,
    ) -> SessionControllerLoopResult:
        normalized = dict(payload or {})
        raw_mode = str(normalized.get("mode") or "").strip().lower()
        if raw_mode == "clarification":
            raw_mode = SessionControllerDecisionMode.CLARIFY.value
        mode = next(
            (item for item in SessionControllerDecisionMode if item.value == raw_mode),
            SessionControllerDecisionMode.ERROR,
        )
        raw_suspend_reason = str(normalized.get("suspend_reason") or "").strip().lower()
        suspend_reason = next(
            (item for item in SuspendReason if item.value == raw_suspend_reason),
            None,
        )
        if mode == SessionControllerDecisionMode.CLARIFY:
            suspend_reason = SuspendReason.CLARIFICATION
        elif mode == SessionControllerDecisionMode.APPROVAL_PENDING:
            suspend_reason = SuspendReason.APPROVAL_PENDING
        context = normalized.get("context") if isinstance(normalized.get("context"), dict) else {}
        return SessionControllerLoopResult(
            mode=mode,
            tool_loop_reply=str(normalized.get("tool_loop_reply") or "").strip(),
            assistant_reply_seed=str(normalized.get("assistant_reply_seed") or "").strip() or None,
            clarification_question=str(normalized.get("clarification_question") or "").strip() or None,
            delegated_agent=str(normalized.get("delegated_agent") or "").strip() or None,
            resolved_requirement_id=str(normalized.get("resolved_requirement_id") or "").strip() or None,
            dispatched_agents=[
                str(item).strip()
                for item in (normalized.get("dispatched_agents") or [])
                if str(item).strip()
            ],
            approval_pending=bool(normalized.get("approval_pending")),
            approval_result=normalized.get("approval_result") if isinstance(normalized.get("approval_result"), dict) else None,
            should_suspend=bool(normalized.get("should_suspend")),
            suspend_reason=suspend_reason,
            context=context,
        )

    @staticmethod
    def _find_stage_output(
        snapshot: list[dict[str, Any]],
        *,
        source_subgraph: str,
    ) -> Any:
        for entry in reversed(snapshot or []):
            if (
                entry.get("entry_type") == "stage_output"
                and entry.get("source_subgraph") == source_subgraph
            ):
                return entry.get("content")
        return None

    @staticmethod
    def _find_latest_stage_output_for_sources(
        snapshot: list[dict[str, Any]],
        *,
        source_subgraphs: set[str],
    ) -> Any:
        for entry in reversed(snapshot or []):
            if (
                entry.get("entry_type") == "stage_output"
                and entry.get("source_subgraph") in source_subgraphs
            ):
                return entry.get("content")
        return None

    def _load_graph_mode_state(
        self,
        *,
        graph_id: str,
    ) -> tuple[SessionControllerLoopResult, dict[str, Any], str]:
        graph = self.execution_graph_service.get_execution_graph(graph_id) or {}
        meta = graph.get("meta_json") or {}
        snapshot = ScratchpadService(
            execution_graph_service=self.execution_graph_service,
        ).load(graph_id).snapshot_all()
        decision_content = self._find_latest_stage_output_for_sources(
            snapshot,
            source_subgraphs={
                "sg_controller_intake",
                "sg_controller_resume_intake",
                "sg_invoke_requirement_agent",
                "sg_invoke_conflict_detection",
                "sg_invoke_requirement_classification_agent",
            },
        )
        try:
            decision_payload = (
                json.loads(decision_content)
                if isinstance(decision_content, str) and decision_content.strip()
                else {}
            )
        except json.JSONDecodeError:
            decision_payload = {}
        if not isinstance(decision_payload, dict):
            decision_payload = {}
        loop_result = self._normalize_graph_mode_loop_result(decision_payload)
        if loop_result.resolved_requirement_id and not meta.get("resolved_requirement_id"):
            meta["resolved_requirement_id"] = loop_result.resolved_requirement_id
        assistant_reply = str(
            self._find_stage_output(snapshot, source_subgraph="sg_final_reply")
            or self._find_stage_output(snapshot, source_subgraph="sg_suspend_reply")
            or meta.get("final_reply")
            or ""
        ).strip()
        context = dict(loop_result.context or {})
        if loop_result.resolved_requirement_id:
            context.setdefault("resolved_requirement_id", loop_result.resolved_requirement_id)
        if loop_result.dispatched_agents:
            context.setdefault("dispatched_agents", loop_result.dispatched_agents)
        if loop_result.approval_result:
            context.setdefault("last_approval_result", loop_result.approval_result)
        return loop_result, context, assistant_reply

    @staticmethod
    def _load_normal_conversation_graph_mode_state(
        *,
        result: Any,
    ) -> tuple[SessionControllerLoopResult, dict[str, Any], str]:
        metadata = result.metadata if isinstance(getattr(result, "metadata", None), dict) else {}
        tool_loop_payload = (
            metadata.get("tool_loop_result")
            if isinstance(metadata.get("tool_loop_result"), dict)
            else {}
        )
        context = (
            dict(tool_loop_payload.get("context") or {})
            if isinstance(tool_loop_payload.get("context"), dict)
            else {}
        )
        assistant_reply = str(
            result.final_output
            or tool_loop_payload.get("tool_loop_reply")
            or ""
        ).strip()

        tool_results = context.get("tool_results") or []
        last_tool_entry = tool_results[-1] if tool_results else {}
        last_tool_name = str(last_tool_entry.get("tool_name") or "").strip()
        last_tool_result = (
            last_tool_entry.get("result")
            if isinstance(last_tool_entry.get("result"), dict)
            else {}
        )
        mode = _NORMAL_CONVERSATION_TOOL_TO_MODE.get(
            last_tool_name,
            SessionControllerDecisionMode.DIRECT_REPLY,
        )
        delegated_agent = _NORMAL_CONVERSATION_TOOL_TO_AGENT.get(last_tool_name)
        approval_pending = bool(last_tool_result.get("approval_pending"))
        approval_result = (
            context.get("last_approval_result")
            if isinstance(context.get("last_approval_result"), dict)
            else None
        )
        status = str(last_tool_result.get("status") or "").strip().lower()
        clarification_required = bool(
            last_tool_result.get("clarification_required")
            or SessionControllerService._normalize_graph_mode_loop_result(
                {"mode": last_tool_result.get("mode")}
            ).mode
            == SessionControllerDecisionMode.CLARIFY
        )
        tool_loop_reply = str(
            tool_loop_payload.get("tool_loop_reply")
            or last_tool_result.get("tool_loop_reply")
            or last_tool_result.get("reply")
            or assistant_reply
        ).strip()
        clarification_question = tool_loop_reply if clarification_required else None
        should_suspend = False
        suspend_reason: SuspendReason | None = None

        if status == "error":
            mode = SessionControllerDecisionMode.ERROR
        elif approval_pending:
            mode = SessionControllerDecisionMode.APPROVAL_PENDING
            should_suspend = True
            suspend_reason = SuspendReason.APPROVAL_PENDING
        elif clarification_required:
            mode = SessionControllerDecisionMode.CLARIFY
            should_suspend = True
            suspend_reason = SuspendReason.CLARIFICATION

        dispatched_agents = [
            str(item).strip()
            for item in (context.get("dispatched_agents") or [])
            if str(item).strip()
        ]
        if not dispatched_agents and delegated_agent:
            dispatched_agents = [delegated_agent]

        return (
            SessionControllerLoopResult(
                mode=mode,
                tool_loop_reply=tool_loop_reply,
                assistant_reply_seed=assistant_reply or tool_loop_reply or None,
                clarification_question=clarification_question,
                delegated_agent=delegated_agent,
                resolved_requirement_id=(
                    str(context.get("resolved_requirement_id") or "").strip() or None
                ),
                dispatched_agents=dispatched_agents,
                approval_pending=approval_pending,
                approval_result=approval_result,
                should_suspend=should_suspend,
                suspend_reason=suspend_reason,
                context=context,
                rounds=int(tool_loop_payload.get("rounds") or 0),
            ),
            context,
            assistant_reply,
        )

    @staticmethod
    def _build_runtime_skeleton_from_detail(detail: dict[str, Any]) -> RuntimeGraphSkeleton:
        graph = detail.get("graph") or {}
        graph_id = str(graph.get("graph_id") or "")
        containers = tuple(
            RuntimeContainer(
                container_id=item["container_id"],
                container_key=item.get("container_key") or "",
                label=item.get("label") or item.get("container_key") or "",
                role_type=item.get("role_type") or "agent",
                order_index=int(item.get("order_index") or 0),
                source_container_id=str(
                    ((item.get("config_json") or {}).get("source_container_id"))
                    or ((item.get("config_json") or {}).get("template_container_id"))
                    or item["container_id"]
                ),
            )
            for item in sorted(
                detail.get("containers") or [],
                key=lambda entry: (int(entry.get("order_index") or 0), str(entry.get("container_id") or "")),
            )
        )
        subgraphs = tuple(
            RuntimeSubgraph(
                subgraph_id=item["subgraph_id"],
                container_id=item["container_id"],
                subgraph_key=item.get("subgraph_key") or "",
                label=item.get("label") or item.get("subgraph_key") or "",
                task_description=item.get("task_description") or "",
                status=item.get("status") or "pending",
                order_index=int(item.get("order_index") or 0),
                node_type=str((item.get("config_json") or {}).get("node_type") or "llm"),
                config_json=dict(item.get("config_json") or {}),
                source_node_id=str(
                    ((item.get("config_json") or {}).get("source_node_id"))
                    or item["subgraph_id"]
                ),
            )
            for item in sorted(
                detail.get("subgraphs") or [],
                key=lambda entry: (int(entry.get("order_index") or 0), str(entry.get("subgraph_id") or "")),
            )
        )
        nodes = tuple(
            RuntimeNode(
                node_id=item["node_id"],
                graph_id=graph_id,
                container_id=item.get("container_id"),
                subgraph_id=item.get("subgraph_id"),
                node_key=item.get("node_key") or "",
                label=item.get("label") or item.get("node_key") or "",
                node_type=item.get("node_type") or "llm",
                role_type=item.get("role_type") or "agent",
                order_index=int(item.get("order_index") or 0),
            )
            for item in sorted(
                detail.get("nodes") or [],
                key=lambda entry: (int(entry.get("order_index") or 0), str(entry.get("node_id") or "")),
            )
        )
        edges = tuple(
            RuntimeEdge(
                edge_id=item["edge_id"],
                source_node_id=item["source_node_id"],
                target_node_id=item["target_node_id"],
                edge_type=item.get("edge_type") or "seq",
                label=item.get("label"),
                condition_expr=item.get("condition_expr"),
                config_json=dict(item.get("config_json") or {}),
                order_index=int(item.get("order_index") or 0),
            )
            for item in sorted(
                detail.get("edges") or [],
                key=lambda entry: (int(entry.get("order_index") or 0), str(entry.get("edge_id") or "")),
            )
        )
        return RuntimeGraphSkeleton(
            graph_id=graph_id,
            containers=containers,
            subgraphs=subgraphs,
            nodes=nodes,
            edges=edges,
        )

    def stream_graph_executor_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
        delegated_max_tool_call_rounds: int = 15,
        skip_user_message_creation: bool = False,
    ) -> Generator[dict[str, Any], None, None]:
        self._ensure_execution_mode_enabled("graph")
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")

        session = self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        if not skip_user_message_creation:
            user_record = self.chat_storage.create_message(
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=user_message,
                metadata={},
                is_read=True,
            )
            self.chat_storage.update_session(session_id=session_id)
            yield {"event": "user_message", "data": user_record}

        graph_target = self._resolve_session_graph_target(session=session, project_id=project_id)
        recorder = SessionControllerGraphRecorder(
            execution_graph_service=self.execution_graph_service,
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            graph_id=graph_target["graph_id"],
            prev_graph_id=graph_target["prev_graph_id"],
            task_context={
                "delegated_max_tool_call_rounds": delegated_max_tool_call_rounds,
                "delegated_prompt_payload_format": "markdown",
                "delegated_context_mode": "full",
            },
            container_keys=("conductor",),
        )
        self._inherit_session_scratchpad(
            graph_id=recorder.graph_id,
            prev_graph_id=graph_target["prev_graph_id"],
            updated_by=user_id,
        )
        self.chat_storage.update_session(
            session_id=session_id,
            active_graph_id=recorder.graph_id,
        )
        self._ensure_graph_runtime_bindings()
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}

        executor = GraphExecutor(
            experience_orchestrator=ExperienceOrchestrator(),
            prompt_builder_factory=create_session_controller_prompt_builder,
        )
        assistant_content = ""
        loop_result = SessionControllerLoopResult(mode=SessionControllerDecisionMode.ERROR)
        context: dict[str, Any] = {}
        current_graph = self.execution_graph_service.get_execution_graph(recorder.graph_id) or {}
        current_meta = current_graph.get("meta_json") or {}
        is_resume = (
            current_graph.get("status") == "suspended"
            and bool(current_meta.get("source_template_id"))
            and bool(current_meta.get("suspended_subgraph_id"))
        )

        try:
            if is_resume:
                detail = self.execution_graph_service.get_graph_detail(recorder.graph_id)
                skeleton = self._build_runtime_skeleton_from_detail(detail)
                gen = executor.resume(
                    skeleton=skeleton,
                    suspended_subgraph_id=str(current_meta.get("suspended_subgraph_id")),
                    user_input=user_message,
                    tool_executor=self.tools,
                    ai_proxy_client=self._graph_ai_proxy_client(
                        model=model,
                        use_thinking_mode=use_thinking_mode,
                    ),
                    graph_service=self.execution_graph_service,
                    recorder=recorder,
                    actor=user_id,
                )
            else:
                template_graph_id = ensure_session_controller_template(
                    execution_graph_service=self.execution_graph_service,
                    project_id=project_id,
                    actor=user_id,
                )
                template_graph = (
                    self.execution_graph_service.get_execution_graph(template_graph_id) or {}
                )
                gen = executor.execute(
                    candidate_templates=[
                        {
                            "graph_id": template_graph_id,
                            "name": str(template_graph.get("name") or "Session Controller"),
                            "description": str(
                                template_graph.get("description")
                                or "Session Controller GraphExecutor builtin template"
                            ),
                            "selectable_containers": [
                                {
                                    "container_key": "requirement_agent",
                                    "label": "Requirement Agent",
                                    "description": "需求检索、需求分析、需求修改",
                                },
                                {
                                    "container_key": "conflict_detection",
                                    "label": "Conflict Detection Agent",
                                    "description": "需求冲突检测与冲突解释",
                                },
                                {
                                    "container_key": "requirement_classification_agent",
                                    "label": "Requirement Classification Agent",
                                    "description": "需求分类、标签归类、类别判断",
                                },
                            ],
                        }
                    ],
                    project_id=project_id,
                    user_message=user_message,
                    tool_executor=self.tools,
                    ai_proxy_client=self._graph_ai_proxy_client(
                        model=model,
                        use_thinking_mode=use_thinking_mode,
                    ),
                    graph_service=self.execution_graph_service,
                    recorder=recorder,
                    actor=user_id,
                    runtime_graph_id=recorder.graph_id,
                    runtime_container_key="conductor",
                    runtime_container_label="Session Controller",
                    runtime_container_role_type="agent",
                )

            while True:
                try:
                    event = next(gen)
                except StopIteration as stop:
                    result = stop.value
                    break
                yield event

            if (
                isinstance(getattr(result, "metadata", None), dict)
                and result.metadata.get("execution_path") == "normal_conversation"
            ):
                loop_result, context, assistant_content = (
                    self._load_normal_conversation_graph_mode_state(result=result)
                )
            else:
                loop_result, context, assistant_content = self._load_graph_mode_state(
                    graph_id=recorder.graph_id,
                )
            if result.status == "failed":
                loop_result = SessionControllerLoopResult(
                    mode=SessionControllerDecisionMode.ERROR,
                    tool_loop_reply=result.error or "执行失败",
                    assistant_reply_seed=result.error or "执行失败",
                    context=context,
                )
                assistant_content = result.error or assistant_content or "执行失败"
            else:
                assistant_content = str(result.final_output or assistant_content or "").strip()
                if not assistant_content:
                    assistant_content = self._resolve_structured_assistant_reply(loop_result)

            self._persist_turn_summary_to_scratchpad(
                graph_id=recorder.graph_id,
                turn_index=recorder.turn_index,
                user_id=user_id,
                user_message=user_message,
                tool_loop_reply=loop_result.tool_loop_reply,
                assistant_reply=assistant_content,
                context=context,
            )

            meta_patch = {
                "intent": "session_control",
                "session_controller_mode": loop_result.mode.value,
                "final_reply": assistant_content,
                "delegated_agent": loop_result.delegated_agent,
                "dispatched_agents": loop_result.dispatched_agents,
                "turn_count": recorder.turn_index,
                "active_turn_index": recorder.turn_index,
                "resolved_requirement_id": loop_result.resolved_requirement_id,
                "awaiting_user_input": (
                    loop_result.should_suspend
                    and loop_result.suspend_reason == SuspendReason.CLARIFICATION
                ),
                "suspended_subgraph_id": getattr(result, "suspended_subgraph_id", None),
            }
            if loop_result.approval_result:
                meta_patch.update(
                    {
                        "approval_request_id": loop_result.approval_result.get("approval_request_id"),
                        "approval_push_message_id": loop_result.approval_result.get("push_message_id"),
                        "approval_status": "pending",
                    }
                )
            self.execution_graph_service.patch_graph_meta(
                recorder.graph_id,
                {key: value for key, value in meta_patch.items() if value is not None},
                updated_by=user_id,
            )

            assistant_message = self.chat_storage.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=assistant_content,
                metadata={
                    "graph_id": recorder.graph_id,
                    "mode": loop_result.mode.value,
                    "delegated_agent": loop_result.delegated_agent,
                    "dispatched_agents": loop_result.dispatched_agents,
                    "approval_result": loop_result.approval_result,
                    "execution_mode": "graph",
                },
                is_read=False,
            )
            yield {"event": "assistant_message", "data": assistant_message}
            yield {
                "event": "result",
                "data": {
                    "graph_id": recorder.graph_id,
                    "reply_text": assistant_message["content"],
                    "mode": loop_result.mode.value,
                    "status": result.status,
                    "dispatched_agents": loop_result.dispatched_agents,
                    "approval_result": loop_result.approval_result,
                    "execution_mode": "graph",
                },
            }
        except Exception as exc:
            error_text = str(exc)
            self.execution_graph_service.patch_graph_meta(
                recorder.graph_id,
                {"final_reply": error_text},
                status="failed",
                updated_by=user_id,
            )
            error_message = self.chat_storage.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=error_text,
                metadata={"error": True, "graph_id": recorder.graph_id, "execution_mode": "graph"},
                is_read=False,
            )
            yield {
                "event": "error",
                "data": {
                    "error": error_text,
                    "message": error_message,
                    "graph_id": recorder.graph_id,
                },
            }

    def stream_session_controller_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        execution_mode: str | None = None,
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
        delegated_max_tool_call_rounds: int = 15,
        skip_user_message_creation: bool = False,
    ) -> Generator[dict[str, Any], None, None]:
        execution_mode = self._resolve_execution_mode(execution_mode)
        self._ensure_execution_mode_enabled(execution_mode)
        yield from self.stream_graph_executor_reply(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            user_message=user_message,
            model=model,
            use_thinking_mode=use_thinking_mode,
            delegated_max_tool_call_rounds=delegated_max_tool_call_rounds,
            skip_user_message_creation=skip_user_message_creation,
        )


def _make_session_controller_service() -> SessionControllerService:
    """Deferred factory to avoid circular imports at module load time."""
    from backend_business.services.agent.agents.requirement_agent import (
        requirement_agent_chat_service,
    )
    from backend_business.services.agent.agents.requirement_classification_agent import (
        requirement_classification_agent_service,
    )
    from backend_business.services.agent.agents.conflict_detection_agent import (
        conflict_detection_agent_service,
    )

    tools = SessionControllerTools(
        requirements_service=RequirementsManageService(settings.POSTGRES_DSN),
        requirement_agent_service=requirement_agent_chat_service,
        conflict_agent_service=conflict_detection_agent_service,
        requirement_classification_agent_service=requirement_classification_agent_service,
    )
    return SessionControllerService(
        chat_storage=ai_chat_service,
        tools=tools,
    )


session_controller_service: SessionControllerService = _make_session_controller_service()
