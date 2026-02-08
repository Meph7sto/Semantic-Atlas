"""
Agent Tools Service.

Defines tools for AI agent and handles tool execution.
Write operations create pending tasks instead of executing directly.
"""

import json
import uuid
from typing import Any, Dict, Generator, List, Optional

import requests
from psycopg2.extras import RealDictCursor
from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.agent_task_service import agent_task_service
from backend_business.services.ai_chat_service import ai_chat_service


def _inference_base_url() -> str:
    return (settings.INFERENCE_BASE_URL or "http://localhost:8000").rstrip("/")


# ========================
# Tool Definitions (OpenAI format)
# ========================
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "requirement_search",
            "description": "搜索项目中的需求。用于定位匹配查询条件的需求列表。这是一个读操作，可直接执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "项目ID，必须提供"},
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，会匹配需求标题和描述",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制，默认10",
                        "default": 10,
                    },
                },
                "required": ["project_id", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "requirement_get",
            "description": "获取单个需求的详细信息。用于查看需求的完整内容。这是一个读操作，可直接执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "项目ID"},
                    "req_id": {"type": "string", "description": "需求ID"},
                },
                "required": ["project_id", "req_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "requirement_update",
            "description": "更新需求的内容。这是一个写操作，会创建待审批任务而非直接执行。用户批准后才会实际更新。可更新的字段仅限：title、description、status、priority、assignee、tags、due_date、custom_fields、order_index。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "项目ID"},
                    "req_id": {"type": "string", "description": "要更新的需求ID"},
                    "fields": {
                        "type": "object",
                        "description": "要更新的字段，可包含：title、description、status、priority、assignee、tags、due_date、custom_fields、order_index",
                        "properties": {
                            "title": {"type": "string", "description": "需求标题"},
                            "description": {
                                "type": "string",
                                "description": "需求描述",
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "draft",
                                    "under_review",
                                    "confirmed",
                                    "in_progress",
                                    "completed",
                                    "archived",
                                ],
                                "description": "需求状态",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                                "description": "优先级",
                            },
                            "assignee": {"type": "string", "description": "负责人"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "标签列表",
                            },
                            "due_date": {
                                "type": "string",
                                "description": "截止日期 (ISO格式)",
                            },
                            "custom_fields": {
                                "type": "object",
                                "description": "自定义字段 (JSON 对象)",
                            },
                            "order_index": {
                                "type": "integer",
                                "description": "排序索引",
                            },
                        },
                    },
                    "rationale": {
                        "type": "string",
                        "description": "修改原因说明，用于审批时参考",
                    },
                },
                "required": ["project_id", "req_id", "fields", "rationale"],
            },
        },
    },
]

# Allowed fields for requirement_update (matching RequirementsManageService.update_requirement)
ALLOWED_UPDATE_FIELDS = {
    "title",
    "description",
    "status",
    "priority",
    "assignee",
    "tags",
    "due_date",
    "custom_fields",
    "order_index",
}

# Write tool names (require pending task approval)
WRITE_TOOLS = {"requirement_update"}


# ========================
# System Prompt
# ========================
AGENT_SYSTEM_PROMPT = """你是一个专业的需求管理助手，帮助用户分析、查询和修改项目需求。

## 工具使用规则

1. **读操作**（requirement_search、requirement_get）可以直接执行，用于：
   - 搜索定位需求
   - 获取需求详情以了解当前状态

2. **写操作**（requirement_update）会创建待审批任务：
   - 你不能直接修改需求，只能提交修改请求
   - 用户批准后才会实际执行
   - 必须提供清晰的 rationale（修改原因）

## 工作流程

当用户请求修改需求时：
1. 先用 requirement_search 定位目标需求（如果用户没有明确指定req_id）
2. 如果有多个匹配结果，询问用户确认是哪一个
3. 用 requirement_get 获取需求当前详情
4. 调用 requirement_update 提交修改请求
5. 告知用户已创建待审批任务，等待批准后生效

## 重要约束

- 可更新的字段仅限于：title、description、status、priority、assignee、tags、due_date、custom_fields、order_index
- status 的可选值：draft、under_review、confirmed、in_progress、completed、archived
- priority 的可选值：low、medium、high、critical
- 不要声称已经完成修改，要说明"已创建待审批任务"
- 如果用户的请求涉及不支持的字段，说明限制并建议替代方案
"""


class AgentToolsService:
    """Handles tool execution for AI agent."""

    def execute_read_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        """Execute a read-only tool and return result."""
        if tool_name == "requirement_search":
            return self._search_requirements(
                project_id=arguments.get("project_id", ""),
                query=arguments.get("query", ""),
                limit=arguments.get("limit", 10),
            )
        elif tool_name == "requirement_get":
            return self._get_requirement(
                project_id=arguments.get("project_id", ""),
                req_id=arguments.get("req_id", ""),
            )
        else:
            return {"error": f"Unknown read tool: {tool_name}"}

    def create_pending_task_for_write_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: str,
        session_id: str,
        user_message_id: str,
        tool_call_id: str,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a pending task for a write operation."""
        if tool_name == "requirement_update":
            return self._create_update_task(
                arguments=arguments,
                user_id=user_id,
                session_id=session_id,
                user_message_id=user_message_id,
                tool_call_id=tool_call_id,
                project_id=project_id,
            )
        else:
            raise ValueError(f"Unknown write tool: {tool_name}")

    def _search_requirements(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search requirements by query string."""
        if not project_id:
            return {"error": "project_id is required", "results": []}

        limit = max(1, min(50, int(limit)))
        search_pattern = f"%{query}%"

        try:
            with db_service._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT req_id, project_id, requirement_type, status, title, description,
                               priority, assignee, parent_id
                        FROM manage_requirements
                        WHERE project_id = %s
                          AND deleted = FALSE
                          AND (title ILIKE %s OR description ILIKE %s)
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        (project_id, search_pattern, search_pattern, limit),
                    )
                    rows = cur.fetchall()

            results = [dict(row) for row in rows]
            return {
                "success": True,
                "count": len(results),
                "results": results,
            }
        except Exception as e:
            return {"error": str(e), "results": []}

    def _get_requirement(
        self,
        project_id: str,
        req_id: str,
    ) -> Dict[str, Any]:
        """Get a single requirement by ID."""
        if not req_id:
            return {"error": "req_id is required"}

        try:
            with db_service._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT req_id, project_id, requirement_type, status, title, description,
                               priority, assignee, tags, due_date, parent_id, order_index,
                               created_by, created_at::text AS created_at,
                               updated_by, updated_at::text AS updated_at
                        FROM manage_requirements
                        WHERE req_id = %s AND deleted = FALSE
                        """,
                        (req_id,),
                    )
                    row = cur.fetchone()

            if not row:
                return {"error": f"Requirement {req_id} not found"}

            # Optionally verify project_id matches
            if project_id and row["project_id"] != project_id:
                return {
                    "error": f"Requirement {req_id} does not belong to project {project_id}"
                }

            return {"success": True, "requirement": dict(row)}
        except Exception as e:
            return {"error": str(e)}

    def _create_update_task(
        self,
        arguments: Dict[str, Any],
        user_id: str,
        session_id: str,
        user_message_id: str,
        tool_call_id: str,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a pending task for requirement_update."""
        req_project_id = arguments.get("project_id", "")
        req_id = arguments.get("req_id", "")
        fields = arguments.get("fields", {})
        rationale = arguments.get("rationale", "")

        if not req_id:
            raise ValueError("req_id is required")
        if not fields:
            raise ValueError("fields is required")

        # Filter to allowed fields only
        filtered_fields = {
            k: v for k, v in fields.items() if k in ALLOWED_UPDATE_FIELDS
        }
        if not filtered_fields:
            raise ValueError(
                f"No valid fields to update. Allowed: {ALLOWED_UPDATE_FIELDS}"
            )

        # Get current requirement for before snapshot
        before = self._get_requirement(req_project_id or project_id or "", req_id)
        if before.get("error"):
            raise ValueError(before["error"])

        current_req = before.get("requirement", {})

        # Build diff preview
        diff_preview = {}
        for key, new_value in filtered_fields.items():
            old_value = current_req.get(key)
            if old_value != new_value:
                diff_preview[key] = {"before": old_value, "after": new_value}

        # Build task title and description
        field_names = (
            ", ".join(diff_preview.keys())
            if diff_preview
            else ", ".join(filtered_fields.keys())
        )
        title = f"更新需求: {current_req.get('title', req_id)[:30]}"
        description = f"修改字段: {field_names}\n原因: {rationale}"

        # Create pending task
        payload = {
            "project_id": req_project_id or project_id,
            "req_id": req_id,
            "fields": filtered_fields,
            "rationale": rationale,
            "before": current_req,
            "diff_preview": diff_preview,
            "source": {
                "session_id": session_id,
                "user_message_id": user_message_id,
                "tool_call_id": tool_call_id,
            },
        }

        task = agent_task_service.create_task(
            user_id=user_id,
            task_type="requirement_update",
            title=title,
            description=description,
            payload=payload,
            session_id=session_id,
            project_id=req_project_id or project_id,
        )

        return task


class AgentStreamService:
    """Handles agent chat with tool calling and streaming."""

    def __init__(self):
        self.tools_service = AgentToolsService()

    def stream_agent_reply(
        self,
        session_id: str,
        user_id: str,
        user_content: str,
        project_id: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Stream agent reply with tool calling support.
        Yields SSE-formatted events.
        """
        # 1) Save user message
        user_msg = ai_chat_service.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_content,
            is_read=True,
        )
        user_message_id = user_msg["message_id"]
        yield f"event: user_message\ndata: {json.dumps(user_msg, ensure_ascii=False)}\n\n"

        # 2) Build inference messages
        history = ai_chat_service.list_messages(session_id, user_id=user_id, limit=20)
        messages = self._build_messages(history, project_id)

        tasks_created: List[Dict[str, Any]] = []
        assistant_content = ""
        thinking_content = ""

        max_tool_rounds = 6

        try:
            for _round in range(max_tool_rounds):
                tool_call_buffers: Dict[int, Dict[str, Any]] = {}
                need_another_round = False

                response = requests.post(
                    f"{_inference_base_url()}/chat/completions/tools/stream",
                    json={
                        "messages": messages,
                        "tools": AGENT_TOOLS,
                        "model": "deepseek-chat",
                        "max_tokens": 4096,
                        "temperature": 0.3,
                        "tool_choice": "auto",
                    },
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
                        # Support both shapes:
                        # - {type:'tool_call', tool_call:{index,id,function:{name,arguments}}}
                        # - {type:'tool_call', index,id,function:{name,arguments}} (engine passthrough)
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
                            # Model finished normally.
                            break

                        # finish_reason == tool_calls: finalize and execute tools.
                        tool_calls: List[Dict[str, Any]] = []
                        for _idx, buf in sorted(tool_call_buffers.items()):
                            raw_args = buf.get("arguments_buffer") or ""
                            try:
                                parsed_args = json.loads(raw_args) if raw_args else {}
                            except Exception:
                                parsed_args = None

                            tool_call = {
                                "id": buf.get("id"),
                                "name": buf.get("name"),
                                "arguments": parsed_args,
                            }
                            tool_calls.append(tool_call)
                            # Send completed tool call (frontend should not stitch arguments).
                            yield f"event: tool_call\ndata: {json.dumps(tool_call, ensure_ascii=False)}\n\n"

                        read_results: List[Dict[str, Any]] = []
                        for tc in tool_calls:
                            tool_name = tc.get("name") or ""
                            tool_call_id = tc.get("id") or ""
                            arguments = tc.get("arguments")

                            if arguments is None:
                                yield f"event: error\ndata: {json.dumps({'error': 'Invalid tool_call arguments', 'tool_call_id': tool_call_id, 'name': tool_name}, ensure_ascii=False)}\n\n"
                                continue

                            if tool_name in WRITE_TOOLS:
                                try:
                                    task = self.tools_service.create_pending_task_for_write_tool(
                                        tool_name=tool_name,
                                        arguments=arguments,
                                        user_id=user_id,
                                        session_id=session_id,
                                        user_message_id=user_message_id,
                                        tool_call_id=tool_call_id,
                                        project_id=project_id,
                                    )
                                    tasks_created.append(task)
                                    yield f"event: task_created\ndata: {json.dumps(task, ensure_ascii=False)}\n\n"
                                except Exception as e:
                                    yield f"event: error\ndata: {json.dumps({'error': f'Failed to create task: {str(e)}', 'tool_call_id': tool_call_id, 'name': tool_name}, ensure_ascii=False)}\n\n"
                            else:
                                try:
                                    result = self.tools_service.execute_read_tool(
                                        tool_name=tool_name,
                                        arguments=arguments,
                                        user_id=user_id,
                                    )
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
                                    yield f"event: error\ndata: {json.dumps({'error': f'Tool execution failed: {str(e)}', 'tool_call_id': tool_call_id, 'name': tool_name}, ensure_ascii=False)}\n\n"

                        if read_results:
                            # Feed tool calls + tool outputs back to model in next round.
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
                                                        rr["arguments"],
                                                        ensure_ascii=False,
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
                                        "content": json.dumps(
                                            rr["result"], ensure_ascii=False
                                        ),
                                    }
                                )
                            need_another_round = True
                        # Either way, tool_calls round ends.
                        break

                    elif chunk_type == "error":
                        yield f"event: error\ndata: {json.dumps({'error': chunk.get('message', 'Unknown error')}, ensure_ascii=False)}\n\n"
                        break

                if need_another_round:
                    continue
                break

            else:
                yield f"event: error\ndata: {json.dumps({'error': 'tool loop exceeded max rounds'}, ensure_ascii=False)}\n\n"

            # 3) Save assistant message and finalize.
            if tasks_created:
                task_summary = f"已创建 {len(tasks_created)} 个待审批任务，请在「待审」标签页查看并批准。"
                if assistant_content:
                    assistant_content = f"{assistant_content}\n\n{task_summary}"
                else:
                    assistant_content = task_summary

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
            error_msg = ai_chat_service.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=f"抱歉，发生了错误：{str(e)}",
                metadata={"error": True},
                is_read=False,
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'message': error_msg}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'error'}, ensure_ascii=False)}\n\n"

    # NOTE: legacy helper removed; stream_agent_reply implements full tool loop.

    def _build_messages(
        self,
        history: List[Dict[str, Any]],
        project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build messages list for inference API."""
        messages = []

        # Add system prompt with project context
        system_prompt = AGENT_SYSTEM_PROMPT
        if project_id:
            system_prompt += f"\n\n当前项目ID: {project_id}"

        messages.append({"role": "system", "content": system_prompt})

        # Add conversation history
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        return messages


# Singleton instance
agent_stream_service = AgentStreamService() if db_service else None
