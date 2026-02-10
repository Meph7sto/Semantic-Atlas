"""Agent runner - generic execution loop for any registered agent."""

import json
import uuid
from typing import Any, Dict, Generator, List, Optional

import requests

from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.ai_chat_service import ai_chat_service
from backend_business.services.agent.context import AgentContext, BaseContext, ExecutionContext
from backend_business.services.agent.registry import agent_registry
from backend_business.services.agent.tools.base import tool_registry


def _inference_base_url() -> str:
    return (settings.INFERENCE_BASE_URL or "http://localhost:8000").rstrip("/")


class AgentRunner:
    """Runs any registered agent with its declared tools."""

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

        # 2) Build conversation history + system prompt
        history = ai_chat_service.list_messages(session_id, user_id=user_id, limit=20)
        messages = self._build_messages(history, agent_def.system_prompt, project_id)

        # 3) Resolve tool schemas for this agent
        try:
            tools_schema = tool_registry.get_schemas(agent_def.tool_names)
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': f'Invalid agent tool config: {e}'}, ensure_ascii=False)}\n\n"
            return

        tasks_created: List[Dict[str, Any]] = []
        assistant_content = ""
        thinking_content = ""

        try:
            model_name = "deepseek-reasoner" if use_thinking_mode else "deepseek-chat"
            for _round in range(agent_def.max_tool_rounds):
                tool_call_buffers: Dict[int, Dict[str, Any]] = {}
                need_another_round = False
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
                                messages.append(
                                    {
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


agent_runner = AgentRunner() if db_service else None
