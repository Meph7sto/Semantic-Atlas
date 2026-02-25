"""ThinkingToolCallEngine — DeepSeek thinking-mode + tool-call protocol.

Implements the correct message sequence per the DeepSeek API docs:
- ONE assistant message per round containing ALL tool_calls + reasoning_content
- Tool result messages follow immediately after the assistant message
- Historical reasoning_content is cleared when a new user turn begins

Works for both ``deepseek-reasoner`` (thinking mode) and ``deepseek-chat``
(standard mode) — the only difference is whether ``reasoning_content`` is
populated and whether ``temperature`` is sent.
"""

import json
import logging
import uuid
from typing import Any, Dict, Generator, List, Optional

import requests

from backend_business.config import settings
from backend_business.services.agent.engines.base import (
    BaseEngine,
    EngineRunResult,
    ToolCallRequest,
    ToolExecutor,
    ToolResult,
)

logger = logging.getLogger(__name__)


def _inference_base_url() -> str:
    return (settings.INFERENCE_BASE_URL or "http://localhost:8000").rstrip("/")


class ThinkingToolCallEngine(BaseEngine):
    """Engine that follows the DeepSeek thinking + tool-call protocol."""

    def __init__(self, model: str = "deepseek-chat") -> None:
        self.model = model

    @property
    def _is_thinking_mode(self) -> bool:
        return self.model == "deepseek-reasoner"

    # ------------------------------------------------------------------
    # Message construction helpers
    # ------------------------------------------------------------------

    def _build_assistant_message(
        self,
        content: Optional[str],
        reasoning_content: Optional[str],
        tool_calls: List[ToolCallRequest],
    ) -> Dict[str, Any]:
        """Build ONE assistant message with all tool_calls (DeepSeek protocol)."""
        msg: Dict[str, Any] = {
            "role": "assistant",
            "content": content or None,
        }
        if self._is_thinking_mode:
            msg["reasoning_content"] = reasoning_content or ""
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments or {}, ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ]
        return msg

    @staticmethod
    def _build_tool_message(tool_call_id: str, content: Any) -> Dict[str, Any]:
        """Build a tool result message."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(content, ensure_ascii=False) if not isinstance(content, str) else content,
        }

    @staticmethod
    def prepare_messages_for_new_turn(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clear historical reasoning_content to save bandwidth on new user turns.

        Per DeepSeek docs, reasoning_content from previous rounds should be
        stripped when a new user message arrives.
        """
        cleaned = []
        for msg in messages:
            if msg.get("role") == "assistant" and "reasoning_content" in msg:
                msg = {k: v for k, v in msg.items() if k != "reasoning_content"}
            cleaned.append(msg)
        return cleaned

    # ------------------------------------------------------------------
    # LLM call helpers
    # ------------------------------------------------------------------

    def _build_request_payload(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[dict],
        max_tokens: int,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "messages": messages,
            "tools": tools_schema,
            "model": self.model,
            "max_tokens": max_tokens,
            "tool_choice": "auto",
        }
        if not self._is_thinking_mode:
            payload["temperature"] = 0.3
        return payload

    def _call_llm_sync(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[dict],
        max_tokens: int,
    ) -> Dict[str, Any]:
        payload = self._build_request_payload(messages, tools_schema, max_tokens)
        response = requests.post(
            f"{_inference_base_url()}/chat/completions/tools",
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        return response.json()

    def _call_llm_stream(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[dict],
        max_tokens: int,
    ) -> requests.Response:
        payload = self._build_request_payload(messages, tools_schema, max_tokens)
        response = requests.post(
            f"{_inference_base_url()}/chat/completions/tools/stream",
            json=payload,
            stream=True,
            timeout=180,
        )
        response.raise_for_status()
        return response

    # ------------------------------------------------------------------
    # Parse helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tool_calls(raw_tool_calls: List[dict]) -> List[ToolCallRequest]:
        result = []
        for tc in raw_tool_calls:
            tc_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
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
            result.append(ToolCallRequest(id=tc_id, name=name, arguments=arguments))
        return result

    # ------------------------------------------------------------------
    # Core protocol: synchronous
    # ------------------------------------------------------------------

    def run(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[dict],
        tool_executor: ToolExecutor,
        max_rounds: int = 6,
        max_tokens: int = 4096,
    ) -> EngineRunResult:
        tasks_created: List[Dict[str, Any]] = []
        assistant_content = ""
        thinking_content = ""
        errors: List[Dict[str, Any]] = []
        rounds_used = 0

        for rounds_used in range(1, max_rounds + 1):
            result = self._call_llm_sync(messages, tools_schema, max_tokens)

            content = result.get("content") or ""
            if content:
                assistant_content += content

            reasoning = result.get("reasoning_content") or ""
            if reasoning:
                thinking_content += reasoning

            raw_tool_calls = result.get("tool_calls") or []
            finish_reason = result.get("finish_reason") or ""

            if finish_reason != "tool_calls" or not raw_tool_calls:
                break

            # Parse tool calls
            tool_calls = self._parse_tool_calls(raw_tool_calls)

            # Build ONE assistant message with all tool_calls (protocol fix)
            assistant_msg = self._build_assistant_message(
                content=content or None,
                reasoning_content=reasoning,
                tool_calls=tool_calls,
            )
            messages.append(assistant_msg)

            # Execute tools and collect results
            has_read_results = False
            for tc in tool_calls:
                if tc.arguments is None:
                    errors.append({
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "error": "Invalid tool arguments",
                    })
                    # Still need a tool result message to keep protocol valid
                    messages.append(self._build_tool_message(
                        tc.id, {"error": "Invalid tool arguments"},
                    ))
                    continue

                tr = tool_executor(tc)

                if tr.is_write:
                    if tr.task:
                        tasks_created.append(tr.task)
                    elif tr.content and isinstance(tr.content, dict) and "error" in tr.content:
                        errors.append({
                            "tool_call_id": tc.id,
                            "name": tc.name,
                            "error": tr.content["error"],
                        })
                    # Write tools still need a tool result message
                    messages.append(self._build_tool_message(
                        tc.id, tr.task or {"status": "task_created"} if tr.task else tr.content,
                    ))
                else:
                    has_read_results = True
                    messages.append(self._build_tool_message(tc.id, tr.content))

            # If only write tools were called, stop
            if not has_read_results:
                break
        else:
            errors.append({
                "error": "Tool loop exceeded max rounds",
                "max_rounds": max_rounds,
            })

        return EngineRunResult(
            content=assistant_content,
            thinking_content=thinking_content,
            tasks_created=tasks_created,
            errors=errors,
            rounds_used=rounds_used,
        )

    # ------------------------------------------------------------------
    # Core protocol: streaming
    # ------------------------------------------------------------------

    def stream(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[dict],
        tool_executor: ToolExecutor,
        max_rounds: int = 6,
        max_tokens: int = 4096,
    ) -> Generator[Dict[str, Any], None, EngineRunResult]:
        """Streaming multi-round execution.

        Yields event dicts: {"type": "thinking"|"token"|"tool_call"|
        "tool_result"|"task_created"|"finish"|"error", ...}
        """
        tasks_created: List[Dict[str, Any]] = []
        assistant_content = ""
        thinking_content = ""
        errors: List[Dict[str, Any]] = []
        rounds_used = 0

        for rounds_used in range(1, max_rounds + 1):
            # Stream one LLM round
            response = self._call_llm_stream(messages, tools_schema, max_tokens)

            tool_call_buffers: Dict[int, Dict[str, Any]] = {}
            round_thinking = ""
            round_content = ""
            need_another_round = False

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
                    delta = chunk.get("content") or chunk.get("delta") or ""
                    thinking_content += delta
                    round_thinking += delta
                    yield {"type": "thinking", "content": delta}

                elif chunk_type == "content":
                    delta = chunk.get("content") or chunk.get("delta") or ""
                    assistant_content += delta
                    round_content += delta
                    yield {"type": "token", "content": delta}

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
                    yield {"type": "finish", "finish_reason": finish_reason}

                    if finish_reason != "tool_calls":
                        break

                    # Finalize buffered tool calls
                    tool_calls: List[ToolCallRequest] = []
                    for _idx, buf in sorted(tool_call_buffers.items()):
                        raw_args = buf.get("arguments_buffer") or ""
                        try:
                            parsed = json.loads(raw_args) if raw_args else {}
                        except Exception:
                            parsed = None
                        tc_req = ToolCallRequest(
                            id=buf["id"], name=buf["name"], arguments=parsed,
                        )
                        tool_calls.append(tc_req)
                        yield {
                            "type": "tool_call",
                            "id": tc_req.id,
                            "name": tc_req.name,
                            "arguments": parsed,
                        }

                    # Build ONE assistant message (protocol fix)
                    assistant_msg = self._build_assistant_message(
                        content=round_content or None,
                        reasoning_content=round_thinking,
                        tool_calls=tool_calls,
                    )
                    messages.append(assistant_msg)

                    # Execute tools
                    has_read_results = False
                    for tc_req in tool_calls:
                        if tc_req.arguments is None:
                            yield {
                                "type": "error",
                                "error": "Invalid tool arguments",
                                "tool_call_id": tc_req.id,
                                "name": tc_req.name,
                            }
                            messages.append(self._build_tool_message(
                                tc_req.id, {"error": "Invalid tool arguments"},
                            ))
                            continue

                        tr = tool_executor(tc_req)

                        if tr.is_write:
                            if tr.task:
                                tasks_created.append(tr.task)
                                yield {"type": "task_created", "task": tr.task}
                            elif tr.content and isinstance(tr.content, dict) and "error" in tr.content:
                                yield {
                                    "type": "error",
                                    "error": tr.content["error"],
                                    "tool_call_id": tc_req.id,
                                    "name": tc_req.name,
                                }
                            messages.append(self._build_tool_message(
                                tc_req.id,
                                tr.task or {"status": "task_created"} if tr.task else tr.content,
                            ))
                        else:
                            has_read_results = True
                            messages.append(self._build_tool_message(tc_req.id, tr.content))
                            yield {
                                "type": "tool_result",
                                "tool_call_id": tc_req.id,
                                "name": tc_req.name,
                                "result": tr.content,
                            }

                    if has_read_results:
                        need_another_round = True
                    break

                elif chunk_type == "error":
                    error_msg = chunk.get("message", "Unknown error")
                    errors.append({"error": error_msg})
                    yield {"type": "error", "error": error_msg}
                    break

            if need_another_round:
                continue
            break
        else:
            errors.append({"error": "Tool loop exceeded max rounds", "max_rounds": max_rounds})
            yield {"type": "error", "error": "Tool loop exceeded max rounds"}

        return EngineRunResult(
            content=assistant_content,
            thinking_content=thinking_content,
            tasks_created=tasks_created,
            errors=errors,
            rounds_used=rounds_used,
        )
