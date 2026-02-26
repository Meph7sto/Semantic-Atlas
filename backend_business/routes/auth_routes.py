"""
认证路由：处理登录、登出等认证相关接口
"""

import os
from functools import wraps

from flask import Blueprint, jsonify, request

from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.auth_service import get_auth_service

auth_bp = Blueprint("auth", __name__)


def require_auth(f):
    """
    JWT 认证装饰器：保护需要认证的路由

    使用方式：
        @auth_bp.route("/protected")
        @require_auth
        def protected():
            # request.current_user 包含当前用户信息
            return jsonify({"message": "success"})
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 从 Authorization header 获取 token
        auth_header = request.headers.get("Authorization", "")

        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "未提供认证 Token"}), 401

        token = auth_header.split(" ")[1]

        # 验证 token
        auth_service = get_auth_service()
        payload = auth_service.verify_token(token)

        if not payload:
            return jsonify({"error": "Token 无效或已过期"}), 401

        # 将用户信息附加到 request 对象
        request.current_user = {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "role": payload.get("role"),
            "external_type": payload.get("external_type"),
        }

        return f(*args, **kwargs)

    return decorated_function


def require_role(*allowed_roles):
    """
    角色权限验证装饰器

    使用方式：
        @auth_bp.route("/admin-only")
        @require_auth
        @require_role("admin")
        def admin_only():
            return jsonify({"message": "admin access"})
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, "current_user"):
                return jsonify({"error": "未认证"}), 401

            user_role = request.current_user.get("role")
            if user_role not in allowed_roles:
                return jsonify({"error": "权限不足"}), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


@auth_bp.route("/auth/login", methods=["POST"])
def login():  # 已迁移
    """
    用户登录接口

    Request Body:
        {
            "username": "test-test",
            "password": "test-test",
            "role": "member"  # 可选：指定登录的角色
        }

    Response:
        {
            "success": true,
            "data": {
                "user_id": "user-xxx",
                "username": "test-test",
                "display_name": "测试用户",
                "role": "member",
                "token": "eyJhbGc..."
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供登录信息"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    selected_role = data.get("role", "member")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    # 使用 get_user_by_username_for_auth 获取用户（不过滤 is_active，用于检查审批状态）
    user = db_service.get_user_by_username_for_auth(username)
    if not user:
        return jsonify({"error": "用户名或密码错误"}), 401

    auth_service = get_auth_service()
    if not auth_service.verify_password(password, user["password_hash"]):
        return jsonify({"error": "用户名或密码错误"}), 401

    # 检查注册状态
    registration_status = user.get("registration_status", "approved")

    if registration_status == "pending":
        return jsonify({"error": "注册审核中，请等待管理员审批"}), 403

    if registration_status == "rejected":
        rejection_reason = user.get("rejection_reason", "未提供原因")
        return jsonify({"error": f"注册申请已被拒绝：{rejection_reason}"}), 403

    # 检查用户是否激活
    if not user.get("is_active", True):
        return jsonify({"error": "用户已被禁用"}), 403

    # 使用用户数据库中的角色（如果前端指定了角色且用户有权限则使用前端指定的）
    user_role = user["role"]
    user_external_type = user.get("external_type")

    # 特殊处理：test 用户可以模拟任何角色和外部身份
    if username == "test":
        if selected_role in ("admin", "member", "viewer"):
            user_role = selected_role
        # 如果前端选择了外部身份
        if selected_role == "client":
            user_role = "member"  # 外部客户的基础角色
            user_external_type = "CLIENT"
        elif selected_role == "contractor":
            user_role = "member"  # 外包成员的基础角色
            user_external_type = "CONTRACTOR"

    # 生成 JWT token
    token = auth_service.generate_token(
        user_id=user["user_id"],
        username=user["username"],
        role=user_role,
        external_type=user_external_type,
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "user_id": user["user_id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user_role,
                "external_type": user_external_type,
                "token": token,
            },
        }
    )


@auth_bp.route("/auth/verify", methods=["GET"])
@require_auth
def verify_token():  # 已迁移
    """
    验证 Token 有效性

    Response:
        {
            "success": true,
            "data": {
                "user_id": "user-xxx",
                "username": "test-test",
                "role": "member"
            }
        }
    """
    return jsonify(
        {
            "success": True,
            "data": request.current_user,
        }
    )


@auth_bp.route("/auth/me", methods=["GET"])
@require_auth
def get_current_user():  # 已迁移
    """
    获取当前用户信息

    Response:
        {
            "success": True,
            "data": {
                "user_id": "user-xxx",
                "username": "test-test",
                "display_name": "测试用户",
                "role": "member",
                "is_active": true,
                "created_at": "2024-01-01T00:00:00"
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    user_id = request.current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "用户不存在"}), 404

    # 不返回密码哈希
    user.pop("password_hash", None)

    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():  # 已迁移
    """
    用户登出接口（客户端自行删除 Token 即可，服务器端为无状态）

    Response:
        {
            "success": True,
            "message": "登出成功"
        }
    """
    return jsonify({"success": True, "message": "登出成功"})


@auth_bp.route("/auth/user-directory", methods=["GET"])
@require_auth
def list_user_directory():  # 已迁移
    """
    列出可用于用户选择的目录（所有用户，含未激活）

    Query Params:
        role: 可选角色筛选
        limit: 返回数量（默认 500，最大 1000）
        offset: 偏移量（默认 0）
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    role = request.args.get("role")
    limit = max(1, min(request.args.get("limit", 500, type=int) or 500, 1000))
    offset = max(request.args.get("offset", 0, type=int) or 0, 0)

    result = db_service.list_users(
        role=role,
        limit=limit,
        offset=offset,
        include_inactive=True,
    )
    users = [
        {
            "user_id": user.get("user_id"),
            "username": user.get("username"),
            "display_name": user.get("display_name"),
            "role": user.get("role"),
        }
        for user in (result.get("users") or [])
        if user.get("user_id")
    ]

    return jsonify(
        {
            "success": True,
            "data": {
                "users": users,
                "total": result.get("total", len(users)),
                "limit": limit,
                "offset": offset,
            },
        }
    )


@auth_bp.route("/auth/users", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():  # 已迁移
    """
    列出所有用户（仅管理员）

    Query Params:
        role: 筛选角色 (admin, member, viewer)
        limit: 返回数量（默认 100）
        offset: 偏移量（默认 0）

    Response:
        {
            "success": True,
            "data": {
                "users": [...],
                "total": 10
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    role = request.args.get("role")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    result = db_service.list_users(role=role, limit=limit, offset=offset)

    return jsonify({"success": True, "data": result})


@auth_bp.route("/auth/users", methods=["POST"])
@require_auth
@require_role("admin")
def create_user():  # 已迁移
    """
    创建用户（仅管理员）

    Request Body:
        {
            "username": "new-user",
            "password": "password123",
            "display_name": "新用户",
            "role": "member",
            "external_type": "CLIENT"  # 可选
        }

    Response:
        {
            "success": True,
            "data": {
                "user_id": "user-xxx",
                "username": "new-user",
                "display_name": "新用户",
                "role": "member",
                "external_type": "CLIENT"
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供用户信息"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    display_name = data.get("display_name", "").strip()
    role = data.get("role", "member")
    external_type = data.get("external_type")

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    if not display_name:
        return jsonify({"error": "显示名称不能为空"}), 400

    if role not in ("admin", "member", "viewer"):
        return jsonify({"error": "无效的角色"}), 400

    # 验证 external_type
    if external_type and external_type not in ("CLIENT", "CONTRACTOR"):
        return jsonify({"error": "无效的外部身份类型"}), 400

    # 检查用户名是否已存在
    existing_user = db_service.get_user_by_username(username)
    if existing_user:
        return jsonify({"error": "用户名已存在"}), 400

    # 哈希密码
    auth_service = get_auth_service()
    password_hash = auth_service.hash_password(password)

    # 生成用户 ID
    user_id = auth_service.generate_user_id()

    # 创建用户
    user = db_service.create_user(
        user_id=user_id,
        username=username,
        password_hash=password_hash,
        display_name=display_name,
        role=role,
        external_type=external_type,
    )

    # 不返回密码哈希
    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/users/<user_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_user(user_id: str):  # 已迁移
    """
    更新用户信息（仅管理员）

    Request Body:
        {
            "display_name": "新名称",
            "role": "admin",
            "is_active": false
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供更新信息"}), 400

    display_name = data.get("display_name")
    role = data.get("role")
    is_active = data.get("is_active")

    if role and role not in ("admin", "member", "viewer"):
        return jsonify({"error": "无效的角色"}), 400

    user = db_service.update_user(
        user_id=user_id,
        display_name=display_name,
        role=role,
        is_active=is_active,
    )

    if not user:
        return jsonify({"error": "用户不存在"}), 404

    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/profile", methods=["GET"])
@require_auth
def get_profile():  # 已迁移
    """
    获取当前用户的个人资料

    Response:
        {
            "success": True,
            "data": {
                "user_id": "user-xxx",
                "username": "test",
                "display_name": "测试用户",
                "role": "admin",
                "external_type": null,
                "avatar_url": null,
                "created_at": "2024-01-01T00:00:00"
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    user_id = request.current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "用户不存在"}), 404

    user.pop("password_hash", None)
    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/profile", methods=["PATCH"])
@require_auth
def update_profile():  # 已迁移
    """
    更新当前用户的个人资料（仅允许修改 display_name 和 avatar_url）

    Request Body:
        {
            "display_name": "新名称",      # 可选
            "avatar_url": "https://..."    # 可选，传空字符串清除头像
        }

    Response:
        {
            "success": True,
            "data": { ...updated user... }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供更新信息"}), 400

    display_name = data.get("display_name")
    avatar_url = data.get("avatar_url")

    # 验证 display_name
    if display_name is not None:
        display_name = display_name.strip()
        if not display_name:
            return jsonify({"error": "显示名称不能为空"}), 400
        if len(display_name) > 50:
            return jsonify({"error": "显示名称不能超过 50 个字符"}), 400

    # 验证 avatar_url（允许空字符串表示清除头像）
    if avatar_url is not None and avatar_url.strip():
        if not avatar_url.startswith(("http://", "https://")):
            return jsonify({"error": "头像 URL 必须以 http:// 或 https:// 开头"}), 400
        if len(avatar_url) > 500:
            return jsonify({"error": "头像 URL 过长"}), 400

    user_id = request.current_user["user_id"]
    user = db_service.update_profile(
        user_id=user_id,
        display_name=display_name,
        avatar_url=avatar_url,
    )

    if not user:
        return jsonify({"error": "用户不存在"}), 404

    user.pop("password_hash", None)
    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/profile/change-password", methods=["POST"])
@require_auth
def change_password():  # 已迁移
    """
    修改当前用户的密码（需要验证旧密码）

    Request Body:
        {
            "old_password": "旧密码",
            "new_password": "新密码"
        }

    Response:
        {
            "success": True,
            "message": "密码修改成功"
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供密码信息"}), 400

    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password:
        return jsonify({"error": "请提供当前密码"}), 400
    if not new_password:
        return jsonify({"error": "请提供新密码"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "新密码长度不能少于 6 位"}), 400
    if old_password == new_password:
        return jsonify({"error": "新密码不能与当前密码相同"}), 400

    user_id = request.current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        return jsonify({"error": "用户不存在"}), 404

    auth_service = get_auth_service()
    if not auth_service.verify_password(old_password, user["password_hash"]):
        return jsonify({"error": "当前密码不正确"}), 400

    new_hash = auth_service.hash_password(new_password)
    success = db_service.change_password(user_id=user_id, new_password_hash=new_hash)

    if not success:
        return jsonify({"error": "密码修改失败，请稍后重试"}), 500

    return jsonify({"success": True, "message": "密码修改成功"})


@auth_bp.route("/auth/register", methods=["POST"])
def register():  # 已迁移
    """
    用户注册接口（开放注册，无需认证，注册后待管理员审批）

    Request Body:
        {
            "username": "new-user",
            "password": "password123",
            "display_name": "新用户"
        }

    Response:
        {
            "success": True,
            "data": {
                "user_id": "user-xxx",
                "username": "new-user",
                "display_name": "新用户",
                "registration_status": "pending",
                "message": "注册成功，请等待管理员审核"
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供注册信息"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")
    display_name = data.get("display_name", "").strip()

    # 验证必填字段
    if not username:
        return jsonify({"error": "用户名不能为空"}), 400
    if not password:
        return jsonify({"error": "密码不能为空"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码长度不能少于 6 位"}), 400
    if not display_name:
        return jsonify({"error": "显示名称不能为空"}), 400

    # 验证用户名格式（只允许字母、数字、下划线、中划线）
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        return jsonify({"error": "用户名只能包含字母、数字、下划线和中划线"}), 400

    # 检查用户名是否已存在（只检查 pending 或 approved 状态，允许被拒绝的用户重新注册）
    existing_user = db_service.get_user_by_username(username)
    if existing_user:
        return jsonify({"error": "用户名已存在"}), 400

    # 哈希密码
    auth_service = get_auth_service()
    password_hash = auth_service.hash_password(password)

    # 生成用户 ID
    user_id = auth_service.generate_user_id()

    # 创建用户（待审批状态，未激活）
    user = db_service.create_user(
        user_id=user_id,
        username=username,
        password_hash=password_hash,
        display_name=display_name,
        role=None,  # 不分配角色，待审批时由管理员指定
        is_active=False,  # 未激活，待审批后才能登录
        external_type=None,  # 外部类型待审批时由管理员指定
        registration_status="pending",  # 待审批状态
    )

    # 不返回密码哈希
    return jsonify(
        {
            "success": True,
            "data": {
                **user,
                "message": "注册成功，请等待管理员审核",
            },
        }
    )


# ========================
# 注册管理接口（管理员专用）
# ========================


@auth_bp.route("/auth/registrations", methods=["GET"])
@require_auth
@require_role("admin")
def list_registrations():  # 已迁移
    """
    列出注册请求（仅管理员）

    Query Params:
        status: 状态筛选（pending, approved, rejected）
        limit: 返回数量限制（默认 100）
        offset: 分页偏移（默认 0）

    Response:
        {
            "registrations": [...],
            "total": 10,
            "limit": 100,
            "offset": 0
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    status = request.args.get("status", "pending")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    # 验证状态值
    valid_statuses = ("pending", "approved", "rejected")
    if status not in valid_statuses:
        return jsonify(
            {"error": f"无效的状态，必须是: {', '.join(valid_statuses)}"}
        ), 400

    result = db_service.get_pending_registrations(
        status=status, limit=limit, offset=offset
    )

    return jsonify({"success": True, "data": result})


@auth_bp.route("/auth/registrations/<user_id>", methods=["GET"])
@require_auth
@require_role("admin")
def get_registration(user_id: str):  # 已迁移
    """
    获取注册详情（仅管理员）

    Response:
        {
            "user_id": "user-xxx",
            "username": "new-user",
            "display_name": "新用户",
            "registration_status": "pending",
            ...
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    user = db_service.get_registration_details(user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/registrations/<user_id>/approve", methods=["POST"])
@require_auth
@require_role("admin")
def approve_registration(user_id: str):  # 已迁移
    """
    批准注册（仅管理员）

    Request Body:
        {
            "role": "member",
            "external_type": "CLIENT"
        }

    Response:
        {
            "success": true,
            "data": {
                "user_id": "user-xxx",
                "username": "new-user",
                "role": "member",
                "registration_status": "approved",
                "approved_by": "admin-user-id"
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供审批信息"}), 400

    role = data.get("role", "member")
    external_type = data.get("external_type")

    # 验证角色
    if role not in ("admin", "member", "viewer"):
        return jsonify({"error": "无效的角色"}), 400

    # 验证 external_type
    if external_type and external_type not in ("CLIENT", "CONTRACTOR"):
        return jsonify({"error": "无效的外部身份类型"}), 400

    admin_user_id = request.current_user["user_id"]

    # 批准注册
    user = db_service.approve_registration(
        user_id=user_id,
        approved_by_user_id=admin_user_id,
        role=role,
        external_type=external_type,
    )

    if not user:
        return jsonify({"error": "用户不存在或已被处理"}), 404

    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/registrations/<user_id>/reject", methods=["POST"])
@require_auth
@require_role("admin")
def reject_registration(user_id: str):  # 已迁移
    """
    拒绝注册（仅管理员）

    Request Body:
        {
            "reason": "用户信息不完整"
        }

    Response:
        {
            "success": true,
            "data": {
                "user_id": "user-xxx",
                "username": "new-user",
                "registration_status": "rejected",
                "rejection_reason": "用户信息不完整",
                "rejected_by": "admin-user-id"
            }
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供拒绝原因"}), 400

    reason = data.get("reason", "").strip()

    # 验证拒绝原因
    if not reason:
        return jsonify({"error": "拒绝原因不能为空"}), 400
    if len(reason) > 500:
        return jsonify({"error": "拒绝原因不能超过 500 个字符"}), 400

    admin_user_id = request.current_user["user_id"]

    # 拒绝注册
    user = db_service.reject_registration(
        user_id=user_id,
        rejected_by_user_id=admin_user_id,
        rejection_reason=reason,
    )

    if not user:
        return jsonify({"error": "用户不存在或已被处理"}), 404

    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/registrations/pending/count", methods=["GET"])
@require_auth
@require_role("admin")
def get_pending_count():  # 已迁移
    """
    获取待审批数量（仅管理员）

    Response:
        {
            "count": 5
        }
    """
    if db_service is None:
        return jsonify({"error": "数据库服务未初始化"}), 500

    result = db_service.get_pending_registrations(status="pending", limit=1, offset=0)

    return jsonify({"success": True, "data": {"count": result["total"]}})
