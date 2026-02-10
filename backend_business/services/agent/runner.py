"""Agent runner - generic execution loop for any registered agent.

The runner now integrates with the MessageBus:
- When an agent starts, it subscribes to the bus for incoming messages.
- When an agent finishes, it unsubscribes.
- ``run_once`` (used by orchestration / tool delegation) can be triggered
  via the bus – the messaging_tools layer sends a REQUEST through the bus
  and the runner executes the target agent in the same thread.
"""

import json
import logging
import uuid
from typing import Any, Dict, Generator, List, Optional

import requests

from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.ai_chat_service import ai_chat_service
from backend_business.services.agent.context import AgentContext, BaseContext, ExecutionContext, MessagingContext
from backend_business.services.agent.registry import agent_registry
from backend_business.services.agent.tools.base import tool_registry
from backend_business.services.agent.messaging import message_bus, AgentMessage, MessageType
from backend_business.services.agent.messaging.channel import channel_manager

logger = logging.getLogger(__name__)


def _inference_base_url() -> str:
    return (settings.INFERENCE_BASE_URL or "http://localhost:8000").rstrip("/")


class AgentRunner:
    """Runs any registered agent with its declared tools.

    Integration with MessageBus
    ---------------------------
    1. ``run_once`` subscribes the agent to the bus **for the duration of
       execution**, then unsubscribes.  If another agent sends a REQUEST
       during that window, the callback queues it for the next tool round.
    2. ``stream`` works the same way for user-facing SSE streams.
    3. A top-level helper ``handle_bus_request`` is provided so that the
       messaging tools can trigger an agent synchronously through the bus.
    """

    # ------------------------------------------------------------------
    # Bus-integrated execution helper
    # ------------------------------------------------------------------

    def handle_bus_request(
        self,
        target_agent_id: str,
        request_message: AgentMessage,
        parent_context: Optional[AgentContext] = None,
        tool_names_override: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute *target_agent_id* in response to a bus REQUEST message.

        This method is called by the messaging tools (delegate_task / query_agent).
        It runs the agent synchronously via ``run_once`` and then publishes the
        RESPONSE back through the bus, completing the request-response cycle.
        """
        content = request_message.content or {}

        user_id = content.get("user_id") or (parent_context.user_id if parent_context else "system")
        session_id = content.get("session_id") or (parent_context.session_id if parent_context else "")
        project_id = content.get("project_id") or (parent_context.project_id if parent_context else None)

        # Build a natural-language prompt from the bus message
        action = content.get("action", "task")
        task_text = content.get("task_description") or content.get("query") or json.dumps(content, ensure_ascii=False)
        prompt_lines = [
            f"你收到来自上级调度 Agent（{request_message.sender_id}）的{action}请求。",
            task_text.strip(),
        ]
        task_context = content.get("task_context") or content.get("query_context")
        if task_context:
            prompt_lines.extend(["", "补充上下文（JSON）:", json.dumps(task_context, ensure_ascii=False)])
        prompt = "\n".join(prompt_lines)

        # Build MessagingContext so the child agent knows its channel
        messaging_ctx = MessagingContext(
            channel_id=request_message.channel_id,
            channel_type="direct",
            peer_agents=[request_message.sender_id],
            reply_to_message_id=request_message.message_id,
        )

        # Execute the agent
        result = self.run_once(
            agent_id=target_agent_id,
            user_id=user_id,
            session_id=session_id,
            user_content=prompt,
            project_id=project_id,
            parent_context=parent_context,
            tool_names_override=tool_names_override,
            messaging_context=messaging_ctx,
        )

        # Publish RESPONSE back through the bus
        response_message_id = message_bus.send_response(
            sender_id=target_agent_id,
            channel_id=request_message.channel_id,
            reply_to=request_message.message_id,
            content={
                "status": "completed" if not result.get("errors") else "completed_with_errors",
                "result": result,
                "project_id": project_id,
                "session_id": session_id,
            },
        )
        result["response_message_id"] = response_message_id
        return result

    # ------------------------------------------------------------------
    # Synchronous execution (for orchestration / delegation)
    # ------------------------------------------------------------------

    def run_once(
        self,
        agent_id: str,
        user_id: str,
        session_id: str,
        user_content: str,
        project_id: Optional[str] = None,
        use_thinking_mode: bool = False,
        parent_context: Optional[AgentContext] = None,
        tool_names_override: Optional[List[str]] = None,
        messaging_context: Optional[MessagingContext] = None,
    ) -> Dict[str, Any]:
        """
        Run an agent synchronously for orchestration use-cases.

        This execution does NOT persist chat messages; callers decide how to surface
        the result (for example, as a conductor tool result).
        """
        agent_def = agent_registry.get(agent_id)
        if not agent_def:
            raise ValueError(f"Unknown agent: {agent_id}")

        parent_depth = parent_context.execution.depth if parent_context and parent_context.execution else -1
        parent_agent_id = parent_context.execution.agent_id if parent_context and parent_context.execution else None

        ctx = AgentContext(
            base=BaseContext(
                user_id=user_id,
                session_id=session_id,
                project_id=project_id,
            ),
            execution=ExecutionContext(
                agent_id=agent_id,
                max_rounds=agent_def.max_tool_rounds,
                depth=max(0, parent_depth + 1),
                parent_agent_id=parent_agent_id,
                user_message_id=parent_context.user_message_id if parent_context else None,
            ),
            messaging=messaging_context,
        )

        # Subscribe to bus for the duration of execution
        _inbox: List[AgentMessage] = []

        def _on_message(msg: AgentMessage) -> None:
            _inbox.append(msg)

        message_bus.subscribe(agent_id, _on_message)

        try:
            prompt = agent_def.system_prompt
            if project_id:
                prompt += f"\n\n当前项目ID: {project_id}"
            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ]

            effective_tool_names = (
                tool_names_override if tool_names_override is not None else agent_def.tool_names
            )
            tools_schema = tool_registry.get_schemas(effective_tool_names)

            model_name = "deepseek-reasoner" if use_thinking_mode else "deepseek-chat"
            tasks_created: List[Dict[str, Any]] = []
            assistant_content = ""
            errors: List[Dict[str, Any]] = []
            rounds_used = 0

            for rounds_used in range(1, agent_def.max_tool_rounds + 1):
                self._drain_bus_inbox(agent_id=agent_id, inbox=_inbox, llm_messages=messages)
                request_payload: Dict[str, Any] = {
                    "messages": messages,
                    "tools": tools_schema,
                    "model": model_name,
                    "max_tokens": 4096,
                    "tool_choice": "auto",
                }
                if not use_thinking_mode:
                    request_payload["temperature"] = 0.3

                response = requests.post(
                    f"{_inference_base_url()}/chat/completions/tools",
                    json=request_payload,
                    timeout=180,
                )
                response.raise_for_status()
                result = response.json()

                content = result.get("content") or ""
                if content:
                    assistant_content += content
                round_reasoning_content = result.get("reasoning_content")

                tool_calls = result.get("tool_calls") or []
                finish_reason = result.get("finish_reason") or ""

                if finish_reason != "tool_calls" or not tool_calls:
                    break

                read_results: List[Dict[str, Any]] = []
                for tc in tool_calls:
                    tool_call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    fn = tc.get("function") or {}
                    tool_name = fn.get("name") or ""
                    raw_args = fn.get("arguments")

                    if isinstance(raw_args, str):
                        try:
                            arguments = json.loads(raw_args) if raw_args else {}
                        except Exception:
                            arguments = None
                    elif isinstance(raw_args, dict):
                        arguments = raw_args
                    else:
                        arguments = None

                    if arguments is None:
                        errors.append(
                            {
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                                "error": "Invalid tool arguments",
                            }
                        )
                        continue

                    tool_def = tool_registry.get(tool_name)
                    if not tool_def:
                        errors.append(
                            {
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                                "error": f"Unknown tool: {tool_name}",
                            }
                        )
                        continue

                    ctx.tool_call_id = tool_call_id

                    if tool_def.is_write:
                        try:
                            task = tool_def.handler(arguments, ctx)
                            tasks_created.append(task)
                        except Exception as e:
                            errors.append(
                                {
                                    "tool_call_id": tool_call_id,
                                    "name": tool_name,
                                    "error": str(e),
                                }
                            )
                        continue

                    try:
                        tool_result = tool_def.handler(arguments, ctx)
                        read_results.append(
                            {
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                                "arguments": arguments,
                                "result": tool_result,
                            }
                        )
                    except Exception as e:
                        errors.append(
                            {
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                                "error": str(e),
                            }
                        )

                if not read_results:
                    break

                for rr in read_results:
                    assistant_tool_msg: Dict[str, Any] = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": rr["tool_call_id"],
                                "type": "function",
                                "function": {
                                    "name": rr["name"],
                                    "arguments": json.dumps(
                                        rr["arguments"], ensure_ascii=False
                                    ),
                                },
                            }
                        ],
                    }
                    if use_thinking_mode:
                        assistant_tool_msg["reasoning_content"] = (
                            round_reasoning_content
                            if round_reasoning_content is not None
                            else ""
                        )
                    messages.append(
                        assistant_tool_msg
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": rr["tool_call_id"],
                            "content": json.dumps(rr["result"], ensure_ascii=False),
                        }
                    )
            else:
                errors.append(
                    {
                        "error": "Tool loop exceeded max rounds",
                        "max_rounds": agent_def.max_tool_rounds,
                    }
                )

            if tasks_created:
                summary = f"已创建 {len(tasks_created)} 个待审批任务，请在「待审」标签页查看并批准。"
                assistant_content = f"{assistant_content}\n\n{summary}" if assistant_content else summary

            if not assistant_content:
                assistant_content = "处理完成。"

            return {
                "agent_id": agent_id,
                "content": assistant_content,
                "tasks_created": tasks_created,
                "errors": errors,
                "rounds_used": rounds_used,
            }
        finally:
            # Always unsubscribe when done
            message_bus.unsubscribe(agent_id, _on_message)

    # ------------------------------------------------------------------
    # SSE streaming (user-facing)
    # ------------------------------------------------------------------

    def stream(
        self,
        agent_id: str,
        session_id: str,
        user_id: str,
        user_content: str,
        project_id: Optional[str] = None,
        use_thinking_mode: bool = False,
    ) -> Generator[str, None, None]:
        """Stream agent reply with tool-calling support. Yields SSE-formatted events."""
        agent_def = agent_registry.get(agent_id)
        if not agent_def:
            yield f"event: error\ndata: {json.dumps({'error': f'Unknown agent: {agent_id}'}, ensure_ascii=False)}\n\n"
            return

        # 1) Persist user message
        user_msg = ai_chat_service.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_content,
            is_read=True,
        )
        user_message_id = user_msg["message_id"]
        yield f"event: user_message\ndata: {json.dumps(user_msg, ensure_ascii=False)}\n\n"

        ctx = AgentContext(
            base=BaseContext(
                user_id=user_id,
                session_id=session_id,
                project_id=project_id,
            ),
            execution=ExecutionContext(
                agent_id=agent_id,
                user_message_id=user_message_id,
                max_rounds=agent_def.max_tool_rounds,
            ),
        )

        # Subscribe to bus for the duration of the stream
        _inbox: List[AgentMessage] = []

        def _on_message(msg: AgentMessage) -> None:
            _inbox.append(msg)

        message_bus.subscribe(agent_id, _on_message)

        # 2) Build conversation history + system prompt
        history = ai_chat_service.list_messages(session_id, user_id=user_id, limit=20)
        messages = self._build_messages(history, agent_def.system_prompt, project_id)

        # 3) Resolve tool schemas for this agent
        try:
            tools_schema = tool_registry.get_schemas(agent_def.tool_names)
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': f'Invalid agent tool config: {e}'}, ensure_ascii=False)}\n\n"
            message_bus.unsubscribe(agent_id, _on_message)
            return

        tasks_created: List[Dict[str, Any]] = []
        assistant_content = ""
        thinking_content = ""

        try:
            model_name = "deepseek-reasoner" if use_thinking_mode else "deepseek-chat"
            for _round in range(agent_def.max_tool_rounds):
                self._drain_bus_inbox(agent_id=agent_id, inbox=_inbox, llm_messages=messages)
                tool_call_buffers: Dict[int, Dict[str, Any]] = {}
                need_another_round = False
                round_thinking_content = ""
                request_payload: Dict[str, Any] = {
                    "messages": messages,
                    "tools": tools_schema,
                    "model": model_name,
                    "max_tokens": 4096,
                    "tool_choice": "auto",
                }
                if not use_thinking_mode:
                    request_payload["temperature"] = 0.3

                response = requests.post(
                    f"{_inference_base_url()}/chat/completions/tools/stream",
                    json=request_payload,
                    stream=True,
                    timeout=180,
                )
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        if isinstance(line, (bytes, bytearray)):
                            line = line.decode("utf-8")
                        chunk = json.loads(line)
                    except Exception:
                        continue

                    chunk_type = chunk.get("type")

                    if chunk_type == "thinking":
                        content = chunk.get("content") or chunk.get("delta") or ""
                        thinking_content += content
                        round_thinking_content += content
                        yield f"event: thinking\ndata: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

                    elif chunk_type == "content":
                        content = chunk.get("content") or chunk.get("delta") or ""
                        assistant_content += content
                        yield f"event: token\ndata: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

                    elif chunk_type == "tool_call":
                        tc = chunk.get("tool_call") or chunk
                        idx = int(tc.get("index", 0) or 0)
                        buf = tool_call_buffers.get(idx)
                        if not buf:
                            buf = {
                                "id": tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                                "name": "",
                                "arguments_buffer": "",
                            }
                            tool_call_buffers[idx] = buf
                        if tc.get("id"):
                            buf["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            buf["name"] = fn["name"]
                        if fn.get("arguments"):
                            buf["arguments_buffer"] += fn["arguments"]

                    elif chunk_type == "finish":
                        finish_reason = chunk.get("finish_reason", "")
                        yield f"event: finish\ndata: {json.dumps({'finish_reason': finish_reason}, ensure_ascii=False)}\n\n"

                        if finish_reason != "tool_calls":
                            break

                        # Finalize buffered tool calls
                        tool_calls: List[Dict[str, Any]] = []
                        for _idx, buf in sorted(tool_call_buffers.items()):
                            raw_args = buf.get("arguments_buffer") or ""
                            try:
                                parsed_args = json.loads(raw_args) if raw_args else {}
                            except Exception:
                                parsed_args = None
                            tc_final = {
                                "id": buf["id"],
                                "name": buf["name"],
                                "arguments": parsed_args,
                            }
                            tool_calls.append(tc_final)
                            yield f"event: tool_call\ndata: {json.dumps(tc_final, ensure_ascii=False)}\n\n"

                        read_results: List[Dict[str, Any]] = []
                        for tc in tool_calls:
                            tool_name = tc.get("name") or ""
                            tool_call_id = tc.get("id") or ""
                            arguments = tc.get("arguments")

                            if arguments is None:
                                yield f"event: error\ndata: {json.dumps({'error': 'Invalid tool arguments', 'tool_call_id': tool_call_id, 'name': tool_name}, ensure_ascii=False)}\n\n"
                                continue

                            tool_def = tool_registry.get(tool_name)
                            if not tool_def:
                                yield f"event: error\ndata: {json.dumps({'error': f'Unknown tool: {tool_name}', 'tool_call_id': tool_call_id}, ensure_ascii=False)}\n\n"
                                continue

                            # Provide per-invocation context
                            ctx.tool_call_id = tool_call_id

                            if tool_def.is_write:
                                try:
                                    task = tool_def.handler(arguments, ctx)
                                    tasks_created.append(task)
                                    yield f"event: task_created\ndata: {json.dumps(task, ensure_ascii=False)}\n\n"
                                except Exception as e:
                                    yield f"event: error\ndata: {json.dumps({'error': f'Failed to create task: {e}', 'tool_call_id': tool_call_id, 'name': tool_name}, ensure_ascii=False)}\n\n"
                            else:
                                try:
                                    result = tool_def.handler(arguments, ctx)
                                    read_results.append(
                                        {
                                            "tool_call_id": tool_call_id,
                                            "name": tool_name,
                                            "arguments": arguments,
                                            "result": result,
                                        }
                                    )
                                    yield f"event: tool_result\ndata: {json.dumps({'tool_call_id': tool_call_id, 'name': tool_name, 'result': result}, ensure_ascii=False)}\n\n"
                                except Exception as e:
                                    yield f"event: error\ndata: {json.dumps({'error': f'Tool failed: {e}', 'tool_call_id': tool_call_id, 'name': tool_name}, ensure_ascii=False)}\n\n"

                        if read_results:
                            # Feed tool outputs back into the conversation
                            for rr in read_results:
                                assistant_tool_msg: Dict[str, Any] = {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": rr["tool_call_id"],
                                            "type": "function",
                                            "function": {
                                                "name": rr["name"],
                                                "arguments": json.dumps(
                                                    rr["arguments"], ensure_ascii=False
                                                ),
                                            },
                                        }
                                    ],
                                }
                                if use_thinking_mode:
                                    assistant_tool_msg["reasoning_content"] = (
                                        round_thinking_content or ""
                                    )
                                messages.append(
                                    assistant_tool_msg
                                )
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": rr["tool_call_id"],
                                        "content": json.dumps(rr["result"], ensure_ascii=False),
                                    }
                                )
                            need_another_round = True
                        break

                    elif chunk_type == "error":
                        yield f"event: error\ndata: {json.dumps({'error': chunk.get('message', 'Unknown error')}, ensure_ascii=False)}\n\n"
                        break

                if need_another_round:
                    continue
                break

            else:
                yield f"event: error\ndata: {json.dumps({'error': 'Tool loop exceeded max rounds'}, ensure_ascii=False)}\n\n"

            # 4) Persist assistant message
            if tasks_created:
                summary = f"已创建 {len(tasks_created)} 个待审批任务，请在「待审」标签页查看并批准。"
                assistant_content = f"{assistant_content}\n\n{summary}" if assistant_content else summary

            if not assistant_content:
                assistant_content = "处理完成。"

            metadata: Dict[str, Any] = {}
            if thinking_content:
                metadata["thinking_content"] = thinking_content
            if tasks_created:
                metadata["tasks_created"] = [t["task_id"] for t in tasks_created]

            assistant_msg = ai_chat_service.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=assistant_content,
                metadata=metadata if metadata else None,
                is_read=False,
            )
            yield f"event: assistant_message\ndata: {json.dumps(assistant_msg, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'completed', 'tasks_count': len(tasks_created)}, ensure_ascii=False)}\n\n"

        except requests.RequestException as e:
            err_msg = ai_chat_service.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=f"抱歉，发生了错误：{e}",
                metadata={"error": True},
                is_read=False,
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'message': err_msg}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'error'}, ensure_ascii=False)}\n\n"
        finally:
            # Always unsubscribe when done
            message_bus.unsubscribe(agent_id, _on_message)

    @staticmethod
    def _build_messages(
        history: List[Dict[str, Any]],
        system_prompt: str,
        project_id: Optional[str],
    ) -> List[dict]:
        prompt = system_prompt
        if project_id:
            prompt += f"\n\n当前项目ID: {project_id}"
        messages = [{"role": "system", "content": prompt}]
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        return messages

    @staticmethod
    def _drain_bus_inbox(
        agent_id: str,
        inbox: List[AgentMessage],
        llm_messages: List[Dict[str, Any]],
    ) -> None:
        """Consume inbound bus messages gathered during execution."""
        while inbox:
            msg = inbox.pop(0)

            if msg.message_type in (MessageType.NOTIFY, MessageType.HEARTBEAT):
                llm_messages.append(
                    {
                        "role": "system",
                        "content": (
                            f"[bus:{msg.message_type.value}] from={msg.sender_id} "
                            f"content={json.dumps(msg.content or {}, ensure_ascii=False)}"
                        ),
                    }
                )
                continue

            if msg.message_type == MessageType.REQUEST:
                message_bus.send_response(
                    sender_id=agent_id,
                    channel_id=msg.channel_id,
                    reply_to=msg.message_id,
                    content={
                        "status": "rejected",
                        "error": "agent_busy",
                        "reason": "Agent is executing another task and cannot handle nested request",
                    },
                )


agent_runner = AgentRunner() if db_service else None
