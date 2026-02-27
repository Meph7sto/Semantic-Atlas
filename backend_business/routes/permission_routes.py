"""
权限管理路由：处理项目成员、角色、评审、基线、变更请求等权限相关接口
"""

from flask import Blueprint, jsonify, request

from backend_business.routes.auth_routes import require_auth, require_role
from backend_business.services.db_service import db_service

permission_bp = Blueprint("permission", __name__)


# ========================
# 辅助函数
# ========================


def error_response(message: str, status: int = 400) -> tuple:
    """返回错误响应"""
    return jsonify({"success": False, "error": message}), status


def success_response(data: any) -> tuple:
    """返回成功响应"""
    return jsonify({"success": True, "data": data}), 200


def check_project_access(project_id: str, user_id: str) -> bool:
    """检查用户是否有访问项目的权限"""
    return db_service.is_project_member(project_id, user_id)


# ========================
# 项目成员管理
# ========================


@permission_bp.route("/projects/<project_id>/members", methods=["POST"])
@require_auth
def add_project_member(
    project_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    添加项目成员

    Request Body:
        {
            "user_id": "user-xxx",
            "member_roles": ["PO", "BA"]  # 可选：同时分配角色
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    # 检查是否有权限添加成员
    if not db_service.check_permission(project_id, user_id, "proj:add_member"):
        return error_response("无添加成员权限", 403)

    data = request.get_json()
    if not data:
        return error_response("请提供成员信息")

    target_user_id = data.get("user_id")
    if not target_user_id:
        return error_response("用户 ID 不能为空")

    # 检查目标用户是否存在
    target_user = db_service.get_user_by_id(target_user_id)
    if not target_user:
        return error_response("目标用户不存在", 404)

    # 添加成员
    member = db_service.add_project_member(project_id, target_user_id, user_id)
    if not member:
        return error_response("添加成员失败（可能已是成员）", 400)

    # 如果指定了角色，批量分配
    roles = data.get("member_roles", [])
    if roles:
        for role_id in roles:
            db_service.assign_role(project_id, target_user_id, role_id, user_id)

    # 返回包含角色的成员信息
    result = db_service.list_project_members(project_id, include_roles=True)
    member_info = next(
        (m for m in result["members"] if m["user_id"] == target_user_id), member
    )

    return success_response(member_info)


@permission_bp.route("/projects/<project_id>/members", methods=["GET"])
@require_auth
def list_project_members(
    project_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    列出项目成员

    Query Params:
        include_roles: 是否包含角色信息 (true/false)

    Response:
        {
            "success": true,
            "data": {
                "members": [...],
                "total": 10
            }
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    # 检查是否有访问项目的权限
    if not check_project_access(project_id, user_id):
        return error_response("无访问项目权限", 403)

    include_roles = request.args.get("include_roles", "false").lower() == "true"

    result = db_service.list_project_members(project_id, include_roles=include_roles)

    return success_response(result)


@permission_bp.route("/projects/<project_id>/members/<user_id>", methods=["DELETE"])
@require_auth
def remove_project_member(
    project_id: str, user_id: str
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    移除项目成员

    Response:
        {
            "success": true,
            "data": {"removed": true}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    operator_id = request.current_user["user_id"]

    # 不能移除自己
    if operator_id == user_id:
        return error_response("不能移除自己", 400)

    # 检查是否有权限移除成员
    if not db_service.check_permission(project_id, operator_id, "proj:remove_member"):
        return error_response("无移除成员权限", 403)

    # 移除成员
    success = db_service.remove_project_member(project_id, user_id)
    if not success:
        return error_response("移除成员失败", 400)

    return success_response({"removed": True})


@permission_bp.route("/projects/<project_id>/members/<user_id>/roles", methods=["PUT"])
@require_auth
def set_user_roles(
    project_id: str, user_id: str
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    设置用户角色（全量替换）

    Request Body:
        {
            "roles": ["PO", "BA"]
        }

    Response:
        {
            "success": true,
            "data": {
                "added": [...],
                "removed": [...],
                "kept": [...]
            }
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    operator_id = request.current_user["user_id"]

    # 检查是否有权限管理成员
    if not db_service.check_permission(project_id, operator_id, "proj:add_member"):
        return error_response("无管理成员权限", 403)

    data = request.get_json()
    if not data:
        return error_response("请提供角色信息")

    roles = data.get("roles", [])
    if not isinstance(roles, list):
        return error_response("roles 必须是数组")

    result = db_service.set_user_roles(project_id, user_id, roles, operator_id)

    if "error" in result:
        return error_response(result["error"], 400)

    return success_response(result)


# ========================
# 评审指派管理
# ========================


@permission_bp.route("/requirements/<requirement_id>/reviews", methods=["POST"])
@require_auth
def create_review_assignment(
    requirement_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    创建评审指派

    Request Body:
        {
            "reviewer_id": "user-xxx",
            "seq": 1,
            "comment": "请评审此需求"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    # 获取需求信息以获取项目 ID
    # 这里简化处理，假设前端会提供项目 ID
    data = request.get_json()
    if not data:
        return error_response("请提供评审信息")

    reviewer_id = data.get("reviewer_id")
    if not reviewer_id:
        return error_response("评审人 ID 不能为空")

    seq = data.get("seq", 1)
    comment = data.get("comment")

    # 检查评审人是否存在
    reviewer = db_service.get_user_by_id(reviewer_id)
    if not reviewer:
        return error_response("评审人不存在", 404)

    # 创建评审指派
    assignment = db_service.create_review_assignment(
        requirement_id=requirement_id,
        reviewer_id=reviewer_id,
        initiated_by=user_id,
        seq=seq,
        comment=comment,
    )

    if not assignment:
        return error_response("创建评审指派失败", 400)

    return success_response(assignment)


@permission_bp.route("/requirements/<requirement_id>/reviews", methods=["GET"])
@require_auth
def list_requirement_reviews(
    requirement_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    列出需求的所有评审

    Query Params:
        status: 筛选状态 (PENDING, APPROVED, REJECTED, WITHDRAWN)

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    status = request.args.get("status")

    reviews = db_service.list_requirement_reviews(requirement_id, status=status)

    return success_response(reviews)


@permission_bp.route("/reviews/<assignment_id>/approve", methods=["POST"])
@require_auth
def approve_review(
    assignment_id: int,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    通过评审

    Request Body:
        {
            "comment": "评审通过"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]
    data = request.get_json() or {}
    comment = data.get("comment")

    assignment = db_service.approve_review(assignment_id, user_id, comment)

    if not assignment:
        return error_response("审批失败（无权限或评审不存在）", 400)

    return success_response(assignment)


@permission_bp.route("/reviews/<assignment_id>/reject", methods=["POST"])
@require_auth
def reject_review(
    assignment_id: int,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    驳回评审

    Request Body:
        {
            "comment": "评审驳回原因"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]
    data = request.get_json() or {}
    comment = data.get("comment")

    assignment = db_service.reject_review(assignment_id, user_id, comment)

    if not assignment:
        return error_response("驳回失败（无权限或评审不存在）", 400)

    return success_response(assignment)


@permission_bp.route("/reviews/<assignment_id>/withdraw", methods=["POST"])
@require_auth
def withdraw_review(
    assignment_id: int,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    撤回评审

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    assignment = db_service.withdraw_review(assignment_id, user_id)

    if not assignment:
        return error_response("撤回失败（无权限或评审不存在）", 400)

    return success_response(assignment)


@permission_bp.route("/user/pending-reviews", methods=["GET"])
@require_auth
def get_user_pending_reviews():  # 已迁移到 backend_business/api/routers/permission.py
    """
    获取当前用户的待处理评审列表

    Query Params:
        project_id: 项目 ID（可选）

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]
    project_id = request.args.get("project_id")

    reviews = db_service.get_user_pending_reviews(user_id, project_id)

    return success_response(reviews)


# ========================
# 基线管理
# ========================


@permission_bp.route("/projects/<project_id>/baselines", methods=["POST"])
@require_auth
def create_baseline(
    project_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    创建基线

    Request Body:
        {
            "version": "1.0.0",
            "locked": false
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    # 检查是否有权限管理基线
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        return error_response("无管理基线权限", 403)

    data = request.get_json()
    if not data:
        return error_response("请提供基线信息")

    version = data.get("version")
    if not version:
        return error_response("版本号不能为空")

    locked = data.get("locked", False)

    # 检查版本号是否已存在
    existing = db_service.get_baseline_by_version(project_id, version)
    if existing:
        return error_response("版本号已存在", 400)

    baseline = db_service.create_baseline(project_id, version, user_id, locked)

    if not baseline:
        return error_response("创建基线失败", 400)

    return success_response(baseline)


@permission_bp.route("/projects/<project_id>/baselines", methods=["GET"])
@require_auth
def list_project_baselines(
    project_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    列出项目的所有基线

    Query Params:
        include_locked: 是否包含已锁定的基线 (true/false，默认 true)

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    # 检查是否有访问项目的权限
    if not check_project_access(project_id, user_id):
        return error_response("无访问项目权限", 403)

    include_locked = request.args.get("include_locked", "true").lower() == "true"

    baselines = db_service.list_project_baselines(
        project_id, include_locked=include_locked
    )

    return success_response(baselines)


@permission_bp.route("/baselines/<baseline_id>/lock", methods=["POST"])
@require_auth
def lock_baseline(
    baseline_id: int,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    锁定基线

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    # 获取基线信息以获取项目 ID
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        return error_response("基线不存在", 404)

    project_id = baseline["project_id"]

    # 检查是否有权限管理基线
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        return error_response("无管理基线权限", 403)

    # 锁定基线
    updated_baseline = db_service.lock_baseline(baseline_id, user_id)

    if not updated_baseline:
        return error_response("锁定基线失败", 400)

    return success_response(updated_baseline)


@permission_bp.route("/baselines/<baseline_id>/unlock", methods=["POST"])
@require_auth
def unlock_baseline(
    baseline_id: int,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    解锁基线

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    # 获取基线信息以获取项目 ID
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        return error_response("基线不存在", 404)

    project_id = baseline["project_id"]

    # 检查是否有权限管理基线
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        return error_response("无管理基线权限", 403)

    # 解锁基线
    updated_baseline = db_service.unlock_baseline(baseline_id, user_id)

    if not updated_baseline:
        return error_response("解锁基线失败", 400)

    return success_response(updated_baseline)


# ========================
# 变更请求管理
# ========================


@permission_bp.route("/requirements/<requirement_id>/change-requests", methods=["POST"])
@require_auth
def create_change_request(
    requirement_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    创建变更请求

    Request Body:
        {
            "baseline_id": 123,
            "reason": "需要修改需求优先级",
            "change_summary": "将优先级从 3 改为 5"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]

    data = request.get_json()
    if not data:
        return error_response("请提供变更请求信息")

    baseline_id = data.get("baseline_id")
    reason = data.get("reason")
    change_summary = data.get("change_summary")

    if not baseline_id:
        return error_response("基线 ID 不能为空")
    if not reason:
        return error_response("变更原因不能为空")
    if not change_summary:
        return error_response("变更摘要不能为空")

    # 检查基线是否存在
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        return error_response("基线不存在", 404)

    project_id = baseline["project_id"]

    # 检查是否有权限创建变更请求
    if not db_service.check_permission(project_id, user_id, "req:change_request"):
        return error_response("无创建变更请求权限", 403)

    # 创建变更请求
    change_request = db_service.create_change_request(
        requirement_id=requirement_id,
        baseline_id=baseline_id,
        requested_by=user_id,
        reason=reason,
        change_summary=change_summary,
    )

    if not change_request:
        return error_response("创建变更请求失败", 400)

    return success_response(change_request)


@permission_bp.route("/requirements/<requirement_id>/change-requests", methods=["GET"])
@require_auth
def list_requirement_change_requests(
    requirement_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    列出需求的所有变更请求

    Query Params:
        status: 筛选状态 (PENDING, APPROVED, REJECTED)

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    status = request.args.get("status")

    change_requests = db_service.list_requirement_change_requests(
        requirement_id, status=status
    )

    return success_response(change_requests)


@permission_bp.route("/change-requests/<request_id>/approve", methods=["POST"])
@require_auth
def approve_change_request(
    request_id: int,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    批准变更请求

    Request Body:
        {
            "review_comment": "同意变更"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]
    data = request.get_json() or {}
    review_comment = data.get("review_comment")

    # 获取变更请求信息以获取项目 ID
    change_request = db_service.get_change_request(request_id)
    if not change_request:
        return error_response("变更请求不存在", 404)

    project_id = change_request["project_id"]

    # 检查是否有权限批准变更
    if not db_service.check_permission(project_id, user_id, "req:change_approve"):
        return error_response("无批准变更权限", 403)

    # 批准变更请求
    updated_request = db_service.approve_change_request(
        request_id, user_id, review_comment
    )

    if not updated_request:
        return error_response("批准变更请求失败", 400)

    return success_response(updated_request)


@permission_bp.route("/change-requests/<request_id>/reject", methods=["POST"])
@require_auth
def reject_change_request(
    request_id: int,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    驳回变更请求

    Request Body:
        {
            "review_comment": "驳回原因"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]
    data = request.get_json() or {}
    review_comment = data.get("review_comment")

    # 获取变更请求信息以获取项目 ID
    change_request = db_service.get_change_request(request_id)
    if not change_request:
        return error_response("变更请求不存在", 404)

    project_id = change_request["project_id"]

    # 检查是否有权限驳回变更
    if not db_service.check_permission(project_id, user_id, "req:change_reject"):
        return error_response("无驳回变更权限", 403)

    # 驳回变更请求
    updated_request = db_service.reject_change_request(
        request_id, user_id, review_comment
    )

    if not updated_request:
        return error_response("驳回变更请求失败", 400)

    return success_response(updated_request)


@permission_bp.route("/change-requests/pending", methods=["GET"])
@require_auth
def get_pending_change_requests():  # 已迁移到 backend_business/api/routers/permission.py
    """
    获取待审批的变更请求列表

    Query Params:
        project_id: 项目 ID（可选）

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]
    project_id = request.args.get("project_id")

    # 获取用户的所有项目（如果未指定项目 ID）
    if not project_id:
        projects = db_service.get_accessible_projects(user_id)
        # 过滤有权限的项目
        accessible_projects = []
        for p_id in projects:
            if db_service.check_permission(p_id, user_id, "req:change_approve"):
                accessible_projects.append(p_id)

        # 收集所有可访问项目的待审批变更请求
        all_requests = []
        for p_id in accessible_projects:
            requests = db_service.get_pending_change_requests(project_id=p_id)
            all_requests.extend(requests)
    else:
        # 检查是否有权限批准变更
        if not db_service.check_permission(project_id, user_id, "req:change_approve"):
            return error_response("无查看待审批变更权限", 403)

        all_requests = db_service.get_pending_change_requests(project_id=project_id)

    return success_response(all_requests)


# ========================
# 权限上下文
# ========================


@permission_bp.route("/projects/<project_id>/context", methods=["GET"])
@require_auth
def get_user_context(
    project_id: str,
):  # 已迁移到 backend_business/api/routers/permission.py
    """
    获取用户在项目中的权限上下文

    Response:
        {
            "success": true,
            "data": {
                "user_id": "user-xxx",
                "system_identity": "SYS_USER",
                "roles": ["PO", "BA"],
                "permissions": [...]
            }
        }
    """
    if db_service is None:
        return error_response("数据库服务未初始化", 500)

    user_id = request.current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        return error_response("用户不存在", 404)

    context = db_service.get_user_context(project_id, user_id, user)

    return success_response(context)
