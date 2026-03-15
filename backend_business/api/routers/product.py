"""
产品管理路由 - FastAPI 版本
对应历史蓝图: product_bp (url_prefix="/api/v2/product")
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from backend_business.config import settings
from backend_business.services.product_service import ProductService
from backend_business.services.db_service import db_service
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.product_schemas import (
    CreateProductRequest,
    UpdateProductRequest,
    AddMemberRequest,
    CreateProjectUnderProductRequest,
    BindProjectRequest,
)
from backend_business.api.deps.auth import get_current_user

router = APIRouter(prefix="/api/v2/product", tags=["product"])
_service = ProductService(dsn=settings.POSTGRES_DSN)


# ========================
# 辅助函数
# ========================

def _get_actor(request: Request, current_user: Optional[dict] = None) -> str:
    """获取操作者标识，优先使用认证用户ID"""
    if current_user:
        return current_user.get("user_id", "system")

    actor = request.headers.get("X-Actor", "")
    if actor:
        return actor

    actor = request.query_params.get("actor", "")
    if actor:
        return actor

    return "system"


def _require_product_access(
    product_id: str,
    current_user: dict,
):
    """检查产品可见权限，无权限时抛出 ErrorResponse"""
    if db_service is None:
        return
    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)
    if not user:
        raise ErrorResponse("用户不存在", 404)
    if not db_service.can_access_product(product_id, user_id, user):
        raise ErrorResponse("Permission denied", 403)


def _require_product_write(
    product_id: str,
    current_user: dict,
):
    """检查产品写权限，无权限时抛出 ErrorResponse"""
    if db_service is None:
        user_id = current_user["user_id"]
        global_role = current_user.get("role", "")
        member_role = _service.get_member_role(product_id, user_id)
        if not _service.can_write_product(global_role, member_role):
            raise ErrorResponse("Permission denied", 403)
        return
    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)
    if not user:
        raise ErrorResponse("用户不存在", 404)
    if not db_service.can_edit_product(product_id, user_id, user):
        raise ErrorResponse("Permission denied", 403)


# ========================
# Products CRUD
# ========================

@router.post("/products")
def create_product(
    req: CreateProductRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    创建产品（需要 admin 权限）

    Request body:
    {
        "name": "产品名称",
        "description": "产品描述",
        "roadmap": "路线图",
        "version": "版本",
        "tags": ["tag1", "tag2"]
    }

    Response:
    {
        "product_id": "xxx",
        "name": "...",
        "description": "...",
        ...
    }
    """
    actor = _get_actor(request, current_user)
    global_role = (current_user or {}).get("role", "")

    if global_role not in ("super_admin", "admin"):
        raise ErrorResponse("Permission denied", 403)

    try:
        product = _service.create_product(
            name=req.name,
            description=req.description,
            roadmap=req.roadmap,
            version=req.version,
            tags=req.tags,
            created_by=actor,
        )
    except ValueError as e:
        raise ErrorResponse(str(e), 400)
    if db_service is not None and global_role != "super_admin":
        db_service.upsert_user_product_scope(
            user_id=actor,
            product_id=product["product_id"],
            can_edit=True,
            granted_by=actor,
        )

    _service.add_audit_log(
        product_id=product["product_id"],
        actor=actor,
        action="create",
        target_type="product",
        target_id=product["product_id"],
        detail=product,
    )
    return product


@router.get("/products")
def list_products(
    include_archived: bool = Query(False, description="是否包含已归档的产品"),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出产品

    Query Params:
        include_archived: 是否包含已归档的产品 (false/true)

    Response:
    {
        "products": [...]
    }
    """
    if db_service is None:
        return {"products": _service.list_products(include_archived=include_archived)}
    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)
    if not user:
        raise ErrorResponse("用户不存在", 404)

    products = _service.list_products(include_archived=include_archived)
    if user.get("role") == "super_admin":
        return {"products": products}

    allowed_product_ids = set(db_service.get_accessible_product_ids(user_id, user=user))
    filtered = [p for p in products if p.get("product_id") in allowed_product_ids]
    return {"products": filtered}


@router.get("/products/{product_id}")
def get_product(
    product_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取产品详情

    Response:
    {
        "product_id": "xxx",
        "name": "...",
        ...
    }
    """
    _require_product_access(product_id, current_user)
    product = _service.get_product(product_id)
    if not product:
        raise ErrorResponse("Product not found", 404)
    return product


@router.patch("/products/{product_id}")
def update_product(
    product_id: str,
    req: UpdateProductRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    更新产品（需要产品写权限）

    Request body (仅提供需要更新的字段):
    {
        "name": "新名称",
        "description": "新描述",
        "status": "active",
        "roadmap": "新路线图",
        "version": "新版本",
        "tags": ["tag1"]
    }

    Response:
    {
        "product_id": "xxx",
        ...
    }
    """
    actor = _get_actor(request, current_user)

    # 权限检查
    _require_product_write(product_id, current_user)

    # 转换为字典，过滤 None 值
    update_data = req.model_dump(exclude_unset=True)

    if not update_data:
        raise ErrorResponse("没有可更新字段")

    try:
        product = _service.update_product(product_id, update_data, updated_by=actor)
    except ValueError as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="update",
        target_type="product",
        target_id=product_id,
        detail=update_data,
    )
    return product


@router.delete("/products/{product_id}")
def delete_product(
    product_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    归档产品（软删除，需要产品写权限）

    Response:
    {
        "success": true,
        "archived": 1
    }
    """
    actor = _get_actor(request, current_user)

    # 权限检查
    _require_product_write(product_id, current_user)

    try:
        affected = _service.delete_product(product_id)
    except ValueError as e:
        raise ErrorResponse(str(e))

    if affected == 0:
        raise ErrorResponse("Product not found or already archived", 404)

    _service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="archive",
        target_type="product",
        target_id=product_id,
        detail={"status": "archived"},
    )
    return {"success": True, "archived": affected}


# ========================
# Product Members
# ========================

@router.post("/products/{product_id}/members")
def add_member(
    product_id: str,
    req: AddMemberRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    添加成员（需要产品写权限）

    Request body:
    {
        "user_id": "user-xxx",
        "role": "member"
    }

    Response:
    {
        "id": 1,
        "product_id": "xxx",
        "user_id": "xxx",
        "role": "member",
        ...
    }
    """
    actor = _get_actor(request, current_user)

    # 权限检查
    _require_product_write(product_id, current_user)

    try:
        member = _service.add_member(product_id, req.user_id, req.role)
    except ValueError as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="add_member",
        target_type="product_member",
        target_id=req.user_id,
        detail=member,
    )
    return member


@router.delete("/products/{product_id}/members/{user_id}")
def remove_member(
    product_id: str,
    user_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    移除成员（需要产品写权限）

    Response:
    {
        "success": true,
        "removed": 1
    }
    """
    actor = _get_actor(request, current_user)

    # 权限检查
    _require_product_write(product_id, current_user)

    try:
        affected = _service.remove_member(product_id, user_id)
    except ValueError as e:
        raise ErrorResponse(str(e))

    if affected == 0:
        raise ErrorResponse("Member not found", 404)

    _service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="remove_member",
        target_type="product_member",
        target_id=user_id,
        detail={},
    )
    return {"success": True, "removed": affected}


@router.get("/products/{product_id}/members")
def list_members(
    product_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出成员

    Response:
    {
        "members": [...]
    }
    """
    _require_product_access(product_id, current_user)
    return {"members": _service.list_members(product_id)}


# ========================
# Product-Project Relations
# ========================

@router.get("/products/{product_id}/projects")
def list_projects_by_product(
    product_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出产品下的项目

    Response:
    {
        "projects": [...]
    }
    """
    _require_product_access(product_id, current_user)
    return {"projects": _service.list_projects_by_product(product_id)}


@router.post("/products/{product_id}/projects")
def create_project_under_product(
    product_id: str,
    req: CreateProjectUnderProductRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    在产品下创建项目（需要产品写权限）

    Request body:
    {
        "name": "项目名称",
        "description": "项目描述"
    }

    Response:
    {
        "project_id": "xxx",
        "name": "...",
        ...
    }
    """
    actor = _get_actor(request, current_user)

    # 权限检查
    _require_product_write(product_id, current_user)

    try:
        project = _service.create_project_under_product(
            product_id=product_id,
            name=req.name,
            description=req.description,
            created_by=actor,
        )
    except ValueError as e:
        raise ErrorResponse(str(e))
    if db_service is not None and (current_user or {}).get("role") != "super_admin":
        db_service.upsert_user_project_scope(
            user_id=actor,
            project_id=project["project_id"],
            can_edit=True,
            granted_by=actor,
        )

    _service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="create_project",
        target_type="project",
        target_id=project["project_id"],
        detail=project,
    )
    return project


@router.post("/projects/{project_id}/bind")
def bind_project_to_product(
    project_id: str,
    req: BindProjectRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    将项目绑定/解绑到产品

    绑定到某产品时，需要对该产品有写权限；解绑不需要产品权限

    Request body:
    {
        "product_id": "product-xxx"  // null 表示解绑
    }

    Response:
    {
        "project_id": "xxx",
        "name": "...",
        "product_id": "xxx",  // 绑定后
        ...
    }
    """
    actor = _get_actor(request, current_user)
    product_id = req.product_id

    if db_service is not None:
        operator_id = current_user["user_id"]
        operator_user = db_service.get_user_by_id(operator_id)
        if not operator_user:
            raise ErrorResponse("用户不存在", 404)

        # 操作项目绑定需要项目编辑权限
        if not db_service.can_edit_project(project_id, operator_id, operator_user):
            raise ErrorResponse("Permission denied", 403)

    # 绑定到某产品时，校验对该产品有写权限
    if product_id:
        _require_product_write(product_id, current_user)

    try:
        project = _service.bind_project_to_product(project_id, product_id)
    except ValueError as e:
        raise ErrorResponse(str(e))

    _service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="bind_project" if product_id else "unbind_project",
        target_type="project",
        target_id=project_id,
        detail={"product_id": product_id},
    )
    return project


# ========================
# Product Overview (聚合查看)
# ========================

@router.get("/products/{product_id}/overview")
def get_product_overview(
    product_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取产品概览统计

    Response:
    {
        "product": {...},
        "stats": {
            "projects": {...},
            "requirements": {...},
            "milestones": {...}
        }
    }
    """
    _require_product_access(product_id, current_user)
    try:
        overview = _service.get_product_overview(product_id)
    except ValueError as e:
        raise ErrorResponse(str(e))
    return overview


@router.get("/products/{product_id}/requirements")
def list_requirements_by_product(
    product_id: str,
    include_deleted: bool = Query(False, description="是否包含已删除的需求"),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取产品下的需求列表

    Query Params:
        include_deleted: 是否包含已删除的需求 (false/true)

    Response:
    {
        "requirements": [...]
    }
    """
    _require_product_access(product_id, current_user)
    return {
        "requirements": _service.list_requirements_by_product(
            product_id, include_deleted=include_deleted
        )
    }


@router.get("/products/{product_id}/milestones")
def list_milestones_by_product(
    product_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取产品下的里程碑列表

    Response:
    {
        "milestones": [...]
    }
    """
    _require_product_access(product_id, current_user)
    return {"milestones": _service.list_milestones_by_product(product_id)}


@router.get("/products/{product_id}/baselines")
def list_baselines_by_product(
    product_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    获取产品下的基线列表

    Response:
    {
        "baselines": [...]
    }
    """
    _require_product_access(product_id, current_user)
    return {"baselines": _service.list_baselines_by_product(product_id)}
