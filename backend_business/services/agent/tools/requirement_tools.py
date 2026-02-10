"""Requirement management tools (search, get, update).

Read tools execute immediately.
Write tools create a pending task via the task queue.
"""

from typing import Any, Dict

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service import db_service
from backend_business.services.agent.context import AgentContext
from backend_business.services.agent.tools.base import ToolDefinition, tool_registry
from backend_business.services.agent.tasks.queue import agent_task_queue
from backend_business.services.requirements_manage_service import normalize_priority

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

# ========================
# OpenAI Schemas
# ========================

_SEARCH_SCHEMA = {
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
}

_GET_SCHEMA = {
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
}

_LIST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "requirement_list",
        "description": (
            "按层级浏览项目需求列表。不提供 parent_id 时列出根级需求，"
            "提供 parent_id 时列出该需求的子需求。"
            "支持按 requirement_type 和 source_level 过滤。"
            "这是一个读操作，可直接执行。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID，必须提供"},
                "parent_id": {
                    "type": "string",
                    "description": "父需求ID。不提供时列出根级需求，提供时列出该父需求的子需求",
                },
                "requirement_type": {
                    "type": "string",
                    "enum": ["top_level", "low_level", "task"],
                    "description": "按需求类型过滤",
                },
                "source_level": {
                    "type": "string",
                    "enum": ["L1", "L2", "L3", "L4"],
                    "description": "按原始提取级别过滤",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量限制，默认20，最大50",
                    "default": 20,
                },
                "offset": {
                    "type": "integer",
                    "description": "分页偏移量，默认0",
                    "default": 0,
                },
            },
            "required": ["project_id"],
        },
    },
}

_UPDATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "requirement_update",
        "description": (
            "更新需求的内容。这是一个写操作，会创建待审批任务而非直接执行。"
            "用户批准后才会实际更新。"
            "可更新的字段仅限：title、description、status、priority、assignee、"
            "tags、due_date、custom_fields、order_index。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "req_id": {"type": "string", "description": "要更新的需求ID"},
                "fields": {
                    "type": "object",
                    "description": "要更新的字段",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
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
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "assignee": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "due_date": {"type": "string"},
                        "custom_fields": {"type": "object"},
                        "order_index": {"type": "integer"},
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
}


# ========================
# Handlers
# ========================


def _search_handler(args: dict, ctx: AgentContext) -> dict:
    project_id = args.get("project_id", "")
    query = args.get("query", "")
    limit = args.get("limit", 10)

    if not project_id:
        return {"error": "project_id is required", "results": []}

    limit = max(1, min(50, int(limit)))
    pattern = f"%{query}%"

    try:
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, project_id, requirement_type, status, title,
                           description, priority, assignee, parent_id
                    FROM manage_requirements
                    WHERE project_id = %s
                      AND deleted = FALSE
                      AND (title ILIKE %s OR description ILIKE %s)
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (project_id, pattern, pattern, limit),
                )
                rows = cur.fetchall()
        return {"success": True, "count": len(rows), "results": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e), "results": []}


def _get_handler(args: dict, ctx: AgentContext) -> dict:
    project_id = args.get("project_id", "")
    req_id = args.get("req_id", "")

    if not req_id:
        return {"error": "req_id is required"}

    try:
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, project_id, requirement_type, status, title,
                           description, priority, assignee, tags, due_date,
                           parent_id, order_index,
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

        if project_id and row["project_id"] != project_id:
            return {"error": f"Requirement {req_id} does not belong to project {project_id}"}

        return {"success": True, "requirement": dict(row)}
    except Exception as e:
        return {"error": str(e)}


def _list_handler(args: dict, ctx: AgentContext) -> dict:
    project_id = args.get("project_id", "")
    parent_id = args.get("parent_id")
    requirement_type = args.get("requirement_type")
    source_level = args.get("source_level")
    limit = max(1, min(50, int(args.get("limit", 20))))
    offset = max(0, int(args.get("offset", 0)))

    if not project_id:
        return {"error": "project_id is required", "results": []}

    conditions = ["project_id = %s", "deleted = FALSE"]
    params: list = [project_id]

    if parent_id:
        conditions.append("parent_id = %s")
        params.append(parent_id)
    else:
        conditions.append("parent_id IS NULL")

    if requirement_type:
        conditions.append("requirement_type = %s")
        params.append(requirement_type)

    if source_level:
        conditions.append("source_level = %s")
        params.append(source_level)

    where = " AND ".join(conditions)

    try:
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM manage_requirements WHERE {where}", params)
                total_count = cur.fetchone()["cnt"]

                cur.execute(
                    f"""
                    SELECT req_id, project_id, requirement_type, source_level,
                           status, title, description, priority, assignee,
                           parent_id, order_index
                    FROM manage_requirements
                    WHERE {where}
                    ORDER BY order_index ASC, created_at ASC
                    LIMIT %s OFFSET %s
                    """,
                    params + [limit, offset],
                )
                rows = cur.fetchall()

        remaining = max(0, total_count - offset - len(rows))
        result: Dict[str, Any] = {
            "success": True,
            "total_count": total_count,
            "returned": len(rows),
            "offset": offset,
            "limit": limit,
            "results": [dict(r) for r in rows],
        }
        if remaining > 0:
            result["hint"] = f"还有 {remaining} 条未显示，使用 offset={offset + limit} 翻页查看"
        return result
    except Exception as e:
        return {"error": str(e), "results": []}


def _update_handler(args: dict, ctx: AgentContext) -> dict:
    """Create a pending task for requirement_update (write op, requires approval)."""
    req_project_id = args.get("project_id", "")
    req_id = args.get("req_id", "")
    fields = args.get("fields", {})
    rationale = args.get("rationale", "")

    if not req_id:
        raise ValueError("req_id is required")
    if not fields:
        raise ValueError("fields is required")

    filtered_fields = {k: v for k, v in fields.items() if k in ALLOWED_UPDATE_FIELDS}
    if not filtered_fields:
        raise ValueError(f"No valid fields. Allowed: {sorted(ALLOWED_UPDATE_FIELDS)}")
    if "priority" in filtered_fields:
        filtered_fields["priority"] = normalize_priority(
            filtered_fields.get("priority"), allow_none=True
        )

    # Fetch before-snapshot
    before = _get_handler(
        {"project_id": req_project_id or ctx.project_id or "", "req_id": req_id}, ctx
    )
    if before.get("error"):
        raise ValueError(before["error"])

    current_req = before.get("requirement", {})

    # Build diff preview
    diff_preview = {}
    for key, new_val in filtered_fields.items():
        old_val = current_req.get(key)
        if old_val != new_val:
            diff_preview[key] = {"before": old_val, "after": new_val}

    field_names = (
        ", ".join(diff_preview.keys()) if diff_preview else ", ".join(filtered_fields.keys())
    )
    title = f"更新需求: {current_req.get('title', req_id)[:30]}"
    description = f"修改字段: {field_names}\n原因: {rationale}"

    payload = {
        "project_id": req_project_id or ctx.project_id,
        "req_id": req_id,
        "fields": filtered_fields,
        "rationale": rationale,
        "before": current_req,
        "diff_preview": diff_preview,
        "source": {
            "agent_id": ctx.agent_id,
            "session_id": ctx.session_id,
            "user_message_id": ctx.user_message_id,
            "tool_call_id": ctx.tool_call_id,
        },
    }

    return agent_task_queue.create_task(
        user_id=ctx.user_id,
        task_type="requirement_update",
        title=title,
        description=description,
        payload=payload,
        session_id=ctx.session_id,
        project_id=req_project_id or ctx.project_id,
    )


# ========================
# Registration
# ========================

tool_registry.register(
    ToolDefinition(
        name="requirement_list",
        openai_schema=_LIST_SCHEMA,
        handler=_list_handler,
        is_write=False,
    )
)
tool_registry.register(
    ToolDefinition(
        name="requirement_search",
        openai_schema=_SEARCH_SCHEMA,
        handler=_search_handler,
        is_write=False,
    )
)
tool_registry.register(
    ToolDefinition(
        name="requirement_get",
        openai_schema=_GET_SCHEMA,
        handler=_get_handler,
        is_write=False,
    )
)
tool_registry.register(
    ToolDefinition(
        name="requirement_update",
        openai_schema=_UPDATE_SCHEMA,
        handler=_update_handler,
        is_write=True,
    )
)
