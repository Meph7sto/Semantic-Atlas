"""
项目管理路由 - FastAPI 版本
统一 v2 前缀：/api/v2/manage/*
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.requirements_manage_service import (
    RequirementsManageService,
)
from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.manage_schemas import (
    # Project schemas
    CreateProjectRequest,
    UpdateProjectRequest,
    # Requirement schemas
    CreateRequirementRequest,
    UpdateRequirementRequest,
    BulkUpdateStatusRequest,
    MoveRequirementRequest,
    ImportRequirementsRequest,
    # Test Case schemas
    CreateTestCaseRequest,
    BindTestCaseRequest,
    # Milestone schemas
    CreateMilestoneRequest,
    CompareMilestonesRequest,
    AddMilestoneEdgeRequest,
    # Branch schemas
    CreateBranchRequest,
    AddChangeSetRequest,
    CreateMergeRequest,
    MergeBranchesRequest,
)

router = APIRouter(prefix="/api/v2/manage", tags=["manage"])

# 初始化管理服务
_service = RequirementsManageService(dsn=settings.POSTGRES_DSN)


# ========================
# 辅助函数
# ========================

def _get_actor(request: Request, current_user: Optional[dict] = None) -> str:
    """
    获取操作者标识
    优先使用认证用户ID，其次使用 X-Actor header，最后使用 "system"
    """
    if current_user:
        return current_user.get("user_id", "system")

    # 从 header 获取 actor
    actor = request.headers.get("X-Actor", "")
    if actor:
        return actor

    # 从 query 参数获取 actor（兼容性）
    actor = request.query_params.get("actor", "")
    if actor:
        return actor

    return "system"


def _require_project_access(project_id: str, current_user: dict) -> dict:
    if db_service is None:
        return {
            "user_id": current_user.get("user_id"),
            "role": current_user.get("role"),
        }
    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)
    if not user:
        raise ErrorResponse("用户不存在", 404)
    if not db_service.can_access_project(project_id, user_id, user):
        raise ErrorResponse("Permission denied", 403)
    return user


def _require_project_edit(project_id: str, current_user: dict) -> dict:
    user = _require_project_access(project_id, current_user)
    user_id = current_user["user_id"]
    if not db_service.can_edit_project(project_id, user_id, user):
        raise ErrorResponse("Permission denied", 403)
    return user


def _get_project_id_by_branch(branch_id: str) -> Optional[str]:
    if db_service is None:
        return "__unknown_project__"
    with db_service.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT project_id
                FROM manage_branch_refs
                WHERE ref_id = %s
                """,
                (branch_id,),
            )
            row = cur.fetchone()
    return row[0] if row else None


# ========================
# Projects
# ========================

@router.post("/projects")
def create_project(
    req: CreateProjectRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建项目

    Request body:
    {
        "name": "项目名称",
        "description": "项目描述"
    }

    Response:
    {
        "project_id": "xxx",
        "name": "项目名称",
        "description": "项目描述",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    if (current_user or {}).get("role") not in ("super_admin", "admin"):
        raise ErrorResponse("Permission denied", 403)
    try:
        project = _service.create_project(
            name=req.name,
            description=req.description,
            created_by=actor,
        )
    except ValueError as e:
        raise ErrorResponse(str(e), 400)
    if db_service is not None and (current_user or {}).get("role") != "super_admin":
        db_service.upsert_user_project_scope(
            user_id=actor,
            project_id=project["project_id"],
            can_edit=True,
            granted_by=actor,
        )

    _service.add_audit_log(
        project_id=project["project_id"],
        actor=actor,
        action="create",
        target_type="project",
        target_id=project["project_id"],
        detail=project,
    )
    return project


@router.get("/projects")
def list_projects(current_user: Optional[dict] = Depends(get_current_user)):
    """
    列出所有项目

    Response:
    {
        "projects": [...]
    }
    """
    if db_service is None:
        return {"projects": _service.list_projects()}
    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)
    if not user:
        raise ErrorResponse("用户不存在", 404)

    projects = _service.list_projects()
    if user.get("role") == "super_admin":
        return {"projects": projects}
    accessible = set(db_service.get_accessible_projects(user_id, user=user))
    return {"projects": [p for p in projects if p.get("project_id") in accessible]}


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取项目详情

    Response:
    {
        "project_id": "xxx",
        "name": "项目名称",
        ...
    }
    """
    _require_project_access(project_id, current_user)
    project = _service.get_project(project_id)
    if not project:
        raise ErrorResponse("Project not found", 404)
    return project


@router.patch("/projects/{project_id}")
def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    更新项目

    Request body (仅提供需要更新的字段):
    {
        "name": "新名称",
        "description": "新描述"
    }

    或设置当前会话:
    {
        "current_session_id": "session-xxx"
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)

    # Handle current_session_id update
    if "current_session_id" in req.model_fields_set:
        try:
            project = _service.set_project_session(
                project_id=project_id,
                session_id=req.current_session_id,
                updated_by=actor,
            )
        except ValueError as e:
            raise ErrorResponse(str(e))
        _service.add_audit_log(
            project_id=project_id,
            actor=actor,
            action="update",
            target_type="project",
            target_id=project_id,
            detail={"current_session_id": req.current_session_id},
        )
        return project

    # Handle general field updates (name, description)
    if req.name is None and req.description is None:
        raise ErrorResponse("No updatable fields provided")

    try:
        project = _service.update_project_info(
            project_id=project_id,
            name=req.name.strip() if req.name else None,
            description=req.description,
            updated_by=actor,
        )
    except ValueError as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="update",
        target_type="project",
        target_id=project_id,
        detail={"name": req.name, "description": req.description},
    )
    return project


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    归档项目（软删除）

    Response:
    {
        "success": true,
        "archived": 1
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    try:
        affected = _service.archive_project(project_id, updated_by=actor)
    except Exception as e:
        raise ErrorResponse(str(e))

    if affected == 0:
        raise ErrorResponse("Project not found or already archived", 404)

    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="archive",
        target_type="project",
        target_id=project_id,
        detail={"status": "archived"},
    )
    return {"success": True, "archived": affected}


# ========================
# Requirements
# ========================

@router.post("/projects/{project_id}/requirements")
def create_requirement(
    project_id: str,
    req: CreateRequirementRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建需求

    Request body:
    {
        "requirement_type": "top_level",
        "title": "需求标题",
        "description": "需求描述",
        "status": "draft",
        "parent_id": "parent-xxx",
        "order_index": 0,
        "priority": "medium",
        "assignee": "user-xxx",
        "tags": ["tag1", "tag2"],
        "due_date": "2024-12-31",
        "source_req_id": "source-xxx",
        "source_level": "L1",
        "custom_fields": {...}
    }

    Response:
    {
        "req_id": "xxx",
        "project_id": "xxx",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    try:
        req_result = _service.create_requirement(
            project_id=project_id,
            requirement_type=req.requirement_type,
            title=req.title,
            description=req.description,
            status=req.status,
            parent_id=req.parent_id,
            order_index=req.order_index,
            priority=req.priority,
            assignee=req.assignee,
            tags=req.tags,
            due_date=req.due_date,
            created_by=actor,
            source_req_id=req.source_req_id,
            source_level=req.source_level,
            custom_fields=req.custom_fields,
        )
    except (ValueError, TypeError) as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="create",
        target_type="requirement",
        target_id=req_result["req_id"],
        detail=req_result,
    )
    return req_result


@router.get("/projects/{project_id}/requirements")
def list_requirements(
    project_id: str,
    include_deleted: bool = Query(False),
    tree: bool = Query(False),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出项目需求

    Query Params:
        include_deleted: 是否包含已删除的需求
        tree: 是否返回树形结构

    Response (flat mode):
    {
        "requirements": [...]
    }

    Response (tree mode):
    {
        "tree": [...],
        "orphans": [...]
    }
    """
    _require_project_access(project_id, current_user)
    if tree:
        tree_result, orphans = _service.get_requirement_tree(
            project_id, include_deleted=include_deleted
        )
        return {"tree": tree_result, "orphans": orphans}

    return {
        "requirements": _service.list_requirements(
            project_id, include_deleted=include_deleted
        )
    }


@router.post("/projects/{project_id}/requirements/import")
def import_requirements(
    project_id: str,
    req: ImportRequirementsRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    从 session 导入需求

    Request body:
    {
        "session_id": "session-xxx",
        "mapping_mode": "tree"
    }

    Response:
    {
        "inserted": 10,
        "inserted_l123": 5,
        "inserted_l4": 5,
        "total": 12,
        "mapping_mode": "tree",
        "stats": {...}
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    result = _service.import_from_session(
        session_id=req.session_id,
        project_id=project_id,
        created_by=actor,
        mapping_mode=req.mapping_mode,
    )
    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="import",
        target_type="requirements",
        target_id=project_id,
        detail=result,
    )
    return result


@router.patch("/requirements/{req_id}")
def update_requirement(
    req_id: str,
    req: UpdateRequirementRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    更新需求

    Request body (仅提供需要更新的字段):
    {
        "title": "新标题",
        "description": "新描述",
        "status": "confirmed",
        "priority": "high",
        "assignee": "user-xxx",
        "tags": ["tag1"],
        "due_date": "2024-12-31",
        "custom_fields": {...},
        "order_index": 1
    }

    Response:
    {
        "req_id": "xxx",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    req_before = _service.get_requirement(req_id)
    if not req_before:
        raise ErrorResponse("需求不存在", 404)
    _require_project_edit(req_before["project_id"], current_user)

    # 转换为字典，过滤 None 值
    update_data = req.model_dump(exclude_unset=True)

    try:
        req_result = _service.update_requirement(req_id, update_data, updated_by=actor)
    except ValueError as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        project_id=req_result["project_id"],
        actor=actor,
        action="update",
        target_type="requirement",
        target_id=req_id,
        detail=update_data,
    )
    return req_result


@router.post("/requirements/bulk-status")
def bulk_update_requirement_status(
    req: BulkUpdateStatusRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    批量更新需求状态

    Request body:
    {
        "req_ids": ["req1", "req2"],
        "status": "confirmed"
    }

    Response:
    {
        "updated": 2,
        "skipped": 0
    }
    """
    actor = _get_actor(request, current_user)
    for req_id in req.req_ids:
        req_item = _service.get_requirement(req_id)
        if not req_item:
            raise ErrorResponse(f"需求不存在: {req_id}", 404)
        _require_project_edit(req_item["project_id"], current_user)
    try:
        result = _service.bulk_update_requirement_status(
            req.req_ids, req.status, updated_by=actor
        )
    except ValueError as e:
        raise ErrorResponse(str(e))

    return result


@router.post("/requirements/{req_id}/move")
def move_requirement(
    req_id: str,
    req: MoveRequirementRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    移动需求

    Request body:
    {
        "parent_id": "new-parent-xxx",
        "order_index": 0
    }

    Response:
    {
        "success": true
    }
    """
    actor = _get_actor(request, current_user)
    req_before = _service.get_requirement(req_id)
    if not req_before:
        raise ErrorResponse("需求不存在", 404)
    _require_project_edit(req_before["project_id"], current_user)
    try:
        _service.move_requirement(
            req_id, req.parent_id, req.order_index, updated_by=actor
        )
        req_result = _service.get_requirement(req_id)
        if req_result:
            _service.add_audit_log(
                project_id=req_result["project_id"],
                actor=actor,
                action="update",
                target_type="requirement",
                target_id=req_id,
                detail={
                    "parent_id": req.parent_id,
                    "order_index": req.order_index,
                },
            )
        return {"success": True}
    except ValueError as e:
        raise ErrorResponse(str(e))


@router.delete("/requirements/{req_id}")
def delete_requirement(
    req_id: str,
    cascade: bool = Query(False),
    request: Request = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    删除需求（软删除）

    Query Params:
        cascade: 是否级联删除子需求

    Response:
    {
        "deleted": 3
    }
    """
    actor = _get_actor(request, current_user)
    req_before = _service.get_requirement(req_id)
    if not req_before:
        raise ErrorResponse("需求不存在", 404)
    _require_project_edit(req_before["project_id"], current_user)
    try:
        affected = _service.delete_requirement(req_id, cascade=cascade, updated_by=actor)
    except ValueError as e:
        raise ErrorResponse(str(e))

    req_result = _service.get_requirement(req_id)
    project_id = req_result["project_id"] if req_result else None
    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="delete",
        target_type="requirement",
        target_id=req_id,
        detail={"cascade": cascade, "affected": affected},
    )
    return {"deleted": affected}


# ========================
# Test Cases
# ========================

@router.post("/projects/{project_id}/test-cases")
def create_test_case(
    project_id: str,
    req: CreateTestCaseRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建测试用例

    Request body:
    {
        "title": "测试用例标题",
        "description": "测试用例描述",
        "status": "draft",
        "source": "来源"
    }

    Response:
    {
        "test_case_id": "xxx",
        "project_id": "xxx",
        "title": "...",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    tc = _service.create_test_case(
        project_id=project_id,
        title=req.title,
        description=req.description,
        status=req.status,
        source=req.source,
        created_by=actor,
    )
    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="create",
        target_type="test_case",
        target_id=tc["test_case_id"],
        detail=tc,
    )
    return tc


@router.get("/projects/{project_id}/test-cases")
def list_test_cases(
    project_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出项目测试用例

    Response:
    {
        "test_cases": [...]
    }
    """
    _require_project_access(project_id, current_user)
    return {"test_cases": _service.list_test_cases(project_id)}


@router.post("/requirements/{req_id}/bind-testcase")
def bind_test_case(
    req_id: str,
    req: BindTestCaseRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    绑定测试用例到需求

    Request body:
    {
        "test_case_id": "tc-xxx",
        "link_type": "verification"
    }

    Response:
    {
        "success": true
    }
    """
    actor = _get_actor(request, current_user)
    req_before = _service.get_requirement(req_id)
    if not req_before:
        raise ErrorResponse("需求不存在", 404)
    _require_project_edit(req_before["project_id"], current_user)
    try:
        _service.bind_test_case(req_id, req.test_case_id, req.link_type)
    except ValueError as e:
        raise ErrorResponse(str(e))

    req_result = _service.get_requirement(req_id)
    if req_result:
        _service.add_audit_log(
            project_id=req_result["project_id"],
            actor=actor,
            action="update",
            target_type="requirement",
            target_id=req_id,
            detail={"test_case_id": req.test_case_id, "link_type": req.link_type},
        )
    return {"success": True}


# ========================
# Milestones
# ========================

@router.post("/projects/{project_id}/milestones")
def create_milestone(
    project_id: str,
    req: CreateMilestoneRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建里程碑

    Request body:
    {
        "name": "里程碑名称",
        "message": "里程碑消息",
        "milestone_type": "regular",
        "is_baseline": false,
        "sprint": "sprint1",
        "version": "1.0.0",
        "tags": ["tag1"],
        "metadata": {...},
        "branch_name": "feature1",
        "parent_milestone_id": "parent-xxx"
    }

    Response:
    {
        "milestone_id": "xxx",
        "project_id": "xxx",
        "name": "...",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    try:
        milestone = _service.create_milestone(
            project_id=project_id,
            name=req.name,
            message=req.message,
            created_by=actor,
            milestone_type=req.milestone_type,
            is_baseline=req.is_baseline,
            sprint=req.sprint,
            version=req.version,
            tags=req.tags,
            metadata=req.metadata,
            branch_name=req.branch_name,
            parent_milestone_id=req.parent_milestone_id,
        )
    except ValueError as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="snapshot",
        target_type="milestone",
        target_id=milestone["milestone_id"],
        detail=milestone,
    )
    return milestone


@router.get("/projects/{project_id}/milestones")
def list_milestones(
    project_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出项目里程碑

    Response:
    {
        "milestones": [...]
    }
    """
    _require_project_access(project_id, current_user)
    return {"milestones": _service.list_milestones(project_id)}


@router.get("/milestones/{milestone_id}")
def get_milestone(
    milestone_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取里程碑详情

    Response:
    {
        "milestone_id": "xxx",
        "project_id": "xxx",
        "name": "...",
        "nodes": [...],
        "relations": [...],
        ...
    }
    """
    milestone = _service.get_milestone(milestone_id, include_nodes=True)
    if not milestone:
        raise ErrorResponse("Milestone not found", 404)
    _require_project_access(milestone["project_id"], current_user)
    return milestone


@router.post("/milestones/{milestone_id}/baseline")
def set_baseline(
    milestone_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    设置里程碑为基线

    Response:
    {
        "success": true
    }
    """
    actor = _get_actor(request, current_user)
    milestone = _service.get_milestone(milestone_id, include_nodes=False)
    if not milestone:
        raise ErrorResponse("Milestone not found", 404)
    _require_project_edit(milestone["project_id"], current_user)
    try:
        _service.set_baseline(milestone_id)
        milestone = _service.get_milestone(milestone_id, include_nodes=False)
        if milestone:
            _service.add_audit_log(
                project_id=milestone["project_id"],
                actor=actor,
                action="baseline",
                target_type="milestone",
                target_id=milestone_id,
                detail=milestone,
            )
        return {"success": True}
    except ValueError as e:
        raise ErrorResponse(str(e))


@router.post("/milestones/compare")
def compare_milestones(
    req: CompareMilestonesRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    比较两个里程碑

    Request body:
    {
        "from_milestone_id": "from-xxx",
        "to_milestone_id": "to-xxx"
    }

    Response:
    {
        "from_milestone_id": "from-xxx",
        "to_milestone_id": "to-xxx",
        "summary": {...},
        "added": [...],
        "deleted": [...],
        "modified": [...],
        "moved": [...],
        "changes": [...],
        "change_map": {...},
        "from_tree": [...],
        "to_tree": [...]
    }
    """
    from_milestone = _service.get_milestone(req.from_milestone_id, include_nodes=False)
    to_milestone = _service.get_milestone(req.to_milestone_id, include_nodes=False)
    if not from_milestone or not to_milestone:
        raise ErrorResponse("里程碑不存在", 404)
    _require_project_access(from_milestone["project_id"], current_user)
    _require_project_access(to_milestone["project_id"], current_user)
    try:
        diff = _service.compare_milestones(req.from_milestone_id, req.to_milestone_id)
        return diff
    except Exception as e:
        raise ErrorResponse(str(e))


@router.post("/projects/{project_id}/milestones/link")
def add_milestone_edge(
    project_id: str,
    req: AddMilestoneEdgeRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    添加里程碑边

    Request body:
    {
        "from_milestone_id": "from-xxx",
        "to_milestone_id": "to-xxx",
        "relation_type": "activity",
        "message": "消息"
    }

    Response:
    {
        "id": 1,
        "project_id": "xxx",
        "from_milestone_id": "...",
        "to_milestone_id": "...",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    try:
        edge = _service.add_milestone_edge(
            project_id=project_id,
            from_milestone_id=req.from_milestone_id,
            to_milestone_id=req.to_milestone_id,
            relation_type=req.relation_type,
            message=req.message,
            created_by=actor,
        )
    except Exception as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="update",
        target_type="milestone_edge",
        target_id=str(edge.get("id")),
        detail=edge,
    )
    return edge


@router.get("/projects/{project_id}/milestone-graph")
def list_milestone_graph(
    project_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取项目里程碑图

    Response:
    {
        "nodes": [...],
        "edges": [...]
    }
    """
    _require_project_access(project_id, current_user)
    return _service.list_milestone_graph(project_id)


# ========================
# Branches
# ========================

@router.post("/projects/{project_id}/branches")
def create_branch(
    project_id: str,
    req: CreateBranchRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建分支

    Request body:
    {
        "name": "feature1",
        "base_milestone_id": "milestone-xxx"
    }

    Response:
    {
        "ref_id": "xxx",
        "project_id": "xxx",
        "ref_name": "feature1",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    branch = _service.create_branch(project_id, req.base_milestone_id, req.name, actor)
    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="branch_create",
        target_type="branch_ref",
        target_id=branch["ref_id"],
        detail=branch,
    )
    return branch


@router.get("/projects/{project_id}/branches")
def list_branches(
    project_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出项目分支

    Response:
    {
        "branches": [...]
    }
    """
    _require_project_access(project_id, current_user)
    return {"branches": _service.list_branches(project_id)}


@router.post("/branches/{branch_id}/changes")
def add_change_set(
    branch_id: str,
    req: AddChangeSetRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    添加变更集

    Request body:
    {
        "change_type": "update",
        "requirement_id": "req-xxx",
        "before_data": {...},
        "after_data": {...}
    }

    Response:
    {
        "change_id": "xxx",
        "branch_id": "xxx",
        "change_type": "...",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    project_id = _get_project_id_by_branch(branch_id)
    if not project_id:
        raise ErrorResponse("分支不存在", 404)
    _require_project_edit(project_id, current_user)
    change = _service.add_change_set(
        branch_id=branch_id,
        change_type=req.change_type,
        requirement_id=req.requirement_id,
        before_data=req.before_data,
        after_data=req.after_data,
        created_by=actor,
    )
    return change


@router.get("/branches/{branch_id}/changes")
def list_change_sets(
    branch_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出分支变更集

    Response:
    {
        "changes": [...]
    }
    """
    project_id = _get_project_id_by_branch(branch_id)
    if not project_id:
        raise ErrorResponse("分支不存在", 404)
    _require_project_access(project_id, current_user)
    return {"changes": _service.list_change_sets(branch_id)}


@router.post("/branches/{branch_id}/impact")
def create_impact_report(
    branch_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建影响报告

    Response:
    {
        "report_id": "xxx",
        "branch_id": "xxx",
        "summary": "...",
        "detail_json": {...},
        "status": "pending",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    project_id = _get_project_id_by_branch(branch_id)
    if not project_id:
        raise ErrorResponse("分支不存在", 404)
    _require_project_edit(project_id, current_user)
    report = _service.create_impact_report(branch_id, actor)
    return report


@router.post("/branches/{branch_id}/merge")
def create_merge_request(
    branch_id: str,
    req: CreateMergeRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建合并请求

    Request body:
    {
        "target_milestone_id": "milestone-xxx"
    }

    Response:
    {
        "merge_id": "xxx",
        "branch_id": "xxx",
        "target_milestone_id": "...",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    project_id = _get_project_id_by_branch(branch_id)
    if not project_id:
        raise ErrorResponse("分支不存在", 404)
    _require_project_edit(project_id, current_user)
    merge = _service.create_merge_request(branch_id, req.target_milestone_id, actor)
    return merge


@router.post("/projects/{project_id}/branches/merge")
def merge_branches(
    project_id: str,
    req: MergeBranchesRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    合并分支

    Request body:
    {
        "source_branch": "feature1",
        "target_branch": "main",
        "message": "合并消息"
    }

    Response:
    {
        "milestone": {...},
        "conflicts": [...],
        "conflict_count": 0,
        "source_branch": "feature1",
        "target_branch": "main"
    }
    """
    actor = _get_actor(request, current_user)
    _require_project_edit(project_id, current_user)
    try:
        result = _service.merge_branches(
            project_id=project_id,
            source_branch=req.source_branch,
            target_branch=req.target_branch,
            created_by=actor,
            message=req.message,
        )
    except ValueError as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        project_id=project_id,
        actor=actor,
        action="branch_merge",
        target_type="branch_ref",
        target_id=req.target_branch,
        detail=result,
    )
    return result


# ========================
# Audit Logs
# ========================

@router.get("/projects/{project_id}/audits")
def list_audits(
    project_id: str,
    limit: int = Query(100, ge=1, le=1000),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出项目审计日志

    Query Params:
        limit: 返回数量限制（1-1000，默认 100）

    Response:
    {
        "logs": [...]
    }
    """
    _require_project_access(project_id, current_user)
    return {"logs": _service.list_audit_logs(project_id, limit=limit)}
