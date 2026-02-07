"""产品管理路由"""

from flask import Blueprint, jsonify, request

from backend_business.config import settings
from backend_business.services.product_service import ProductService

product_bp = Blueprint("product", __name__)
service = ProductService(dsn=settings.POSTGRES_DSN)


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _get_actor() -> str:
    return (
        request.headers.get("X-Actor", "") or request.args.get("actor", "") or "system"
    )


def _get_global_role() -> str:
    return request.headers.get("X-Role", "") or request.args.get("role", "") or ""


def _require_product_write(product_id: str):
    actor = _get_actor()
    global_role = _get_global_role()
    member_role = service.get_member_role(product_id, actor)
    if not service.can_write_product(global_role, member_role):
        return _json_error("Permission denied", 403)
    return None


# ----------------------
# Products CRUD
# ----------------------
@product_bp.post("/products")
def create_product():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _json_error("Missing product name")
    actor = _get_actor()
    global_role = _get_global_role()
    if (global_role or "").lower() != "admin":
        return _json_error("Permission denied", 403)
    product = service.create_product(
        name=name,
        description=data.get("description", ""),
        roadmap=data.get("roadmap", ""),
        version=data.get("version", ""),
        tags=data.get("tags"),
        created_by=actor,
    )
    service.add_audit_log(
        product_id=product["product_id"],
        actor=actor,
        action="create",
        target_type="product",
        target_id=product["product_id"],
        detail=product,
    )
    return jsonify(product)


@product_bp.get("/products")
def list_products():
    include_archived = request.args.get("include_archived") in ("1", "true", "True")
    return jsonify(
        {"products": service.list_products(include_archived=include_archived)}
    )


@product_bp.get("/products/<product_id>")
def get_product(product_id: str):
    product = service.get_product(product_id)
    if not product:
        return _json_error("Product not found", 404)
    return jsonify(product)


@product_bp.patch("/products/<product_id>")
def update_product(product_id: str):
    denied = _require_product_write(product_id)
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    actor = _get_actor()
    try:
        product = service.update_product(product_id, data, updated_by=actor)
    except Exception as e:
        return _json_error(str(e))
    service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="update",
        target_type="product",
        target_id=product_id,
        detail=data,
    )
    return jsonify(product)


@product_bp.delete("/products/<product_id>")
def delete_product(product_id: str):
    denied = _require_product_write(product_id)
    if denied:
        return denied
    actor = _get_actor()
    try:
        affected = service.delete_product(product_id)
    except Exception as e:
        return _json_error(str(e))
    if affected == 0:
        return _json_error("Product not found or already archived", 404)
    service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="archive",
        target_type="product",
        target_id=product_id,
        detail={"status": "archived"},
    )
    return jsonify({"success": True, "archived": affected})


# ----------------------
# Product Members
# ----------------------
@product_bp.post("/products/<product_id>/members")
def add_member(product_id: str):
    denied = _require_product_write(product_id)
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user_id") or "").strip()
    if not user_id:
        return _json_error("Missing user_id")
    role = data.get("role", "member")
    actor = _get_actor()
    try:
        member = service.add_member(product_id, user_id, role)
    except Exception as e:
        return _json_error(str(e))
    service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="add_member",
        target_type="product_member",
        target_id=user_id,
        detail=member,
    )
    return jsonify(member)


@product_bp.delete("/products/<product_id>/members/<user_id>")
def remove_member(product_id: str, user_id: str):
    denied = _require_product_write(product_id)
    if denied:
        return denied
    actor = _get_actor()
    try:
        affected = service.remove_member(product_id, user_id)
    except Exception as e:
        return _json_error(str(e))
    if affected == 0:
        return _json_error("Member not found", 404)
    service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="remove_member",
        target_type="product_member",
        target_id=user_id,
        detail={},
    )
    return jsonify({"success": True, "removed": affected})


@product_bp.get("/products/<product_id>/members")
def list_members(product_id: str):
    return jsonify({"members": service.list_members(product_id)})


# ----------------------
# Product-Project Relations
# ----------------------
@product_bp.get("/products/<product_id>/projects")
def list_projects_by_product(product_id: str):
    return jsonify({"projects": service.list_projects_by_product(product_id)})


@product_bp.post("/products/<product_id>/projects")
def create_project_under_product(product_id: str):
    denied = _require_product_write(product_id)
    if denied:
        return denied
    # 在产品下新建项目
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _json_error("Missing project name")
    actor = _get_actor()
    try:
        project = service.create_project_under_product(
            product_id=product_id,
            name=name,
            description=data.get("description", ""),
            created_by=actor,
        )
    except Exception as e:
        return _json_error(str(e))
    service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="create_project",
        target_type="project",
        target_id=project["project_id"],
        detail=project,
    )
    return jsonify(project)


@product_bp.post("/projects/<project_id>/bind")
def bind_project_to_product(project_id: str):
    """将项目绑定/解绑到产品"""
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")  # None 表示解绑

    # 绑定到某产品时，校验对该产品有写权限；解绑不需要产品权限
    if product_id:
        denied = _require_product_write(product_id)
        if denied:
            return denied
    actor = _get_actor()
    try:
        project = service.bind_project_to_product(project_id, product_id)
    except Exception as e:
        return _json_error(str(e))
    service.add_audit_log(
        product_id=product_id,
        actor=actor,
        action="bind_project" if product_id else "unbind_project",
        target_type="project",
        target_id=project_id,
        detail={"product_id": product_id},
    )
    return jsonify(project)


# ----------------------
# Product Overview (聚合查看)
# ----------------------
@product_bp.get("/products/<product_id>/overview")
def get_product_overview(product_id: str):
    try:
        overview = service.get_product_overview(product_id)
    except Exception as e:
        return _json_error(str(e))
    return jsonify(overview)


@product_bp.get("/products/<product_id>/requirements")
def list_requirements_by_product(product_id: str):
    include_deleted = request.args.get("include_deleted") in ("1", "true", "True")
    return jsonify(
        {
            "requirements": service.list_requirements_by_product(
                product_id, include_deleted
            )
        }
    )


@product_bp.get("/products/<product_id>/milestones")
def list_milestones_by_product(product_id: str):
    return jsonify({"milestones": service.list_milestones_by_product(product_id)})


@product_bp.get("/products/<product_id>/baselines")
def list_baselines_by_product(product_id: str):
    return jsonify({"baselines": service.list_baselines_by_product(product_id)})
