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
def login():
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

    # 验证用户名和密码
    user = db_service.get_user_by_username(username)
    if not user:
        return jsonify({"error": "用户名或密码错误"}), 401

    auth_service = get_auth_service()
    if not auth_service.verify_password(password, user["password_hash"]):
        return jsonify({"error": "用户名或密码错误"}), 401

    # 检查用户是否激活
    if not user.get("is_active", True):
        return jsonify({"error": "用户已被禁用"}), 403

    # 使用用户数据库中的角色（如果前端指定了角色且用户有权限则使用前端指定的）
    user_role = user["role"]
    # 这里简化处理：使用用户数据库中的角色
    # 实际场景可能需要更复杂的权限判断

    # 生成 JWT token
    token = auth_service.generate_token(
        user_id=user["user_id"],
        username=user["username"],
        role=user_role,
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "user_id": user["user_id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user_role,
                "token": token,
            },
        }
    )


@auth_bp.route("/auth/verify", methods=["GET"])
@require_auth
def verify_token():
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
def get_current_user():
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
def logout():
    """
    用户登出接口（客户端自行删除 Token 即可，服务器端为无状态）

    Response:
        {
            "success": True,
            "message": "登出成功"
        }
    """
    return jsonify({"success": True, "message": "登出成功"})


@auth_bp.route("/auth/users", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():
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
def create_user():
    """
    创建用户（仅管理员）

    Request Body:
        {
            "username": "new-user",
            "password": "password123",
            "display_name": "新用户",
            "role": "member"
        }

    Response:
        {
            "success": True,
            "data": {
                "user_id": "user-xxx",
                "username": "new-user",
                "display_name": "新用户",
                "role": "member"
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

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400

    if not display_name:
        return jsonify({"error": "显示名称不能为空"}), 400

    if role not in ("admin", "member", "viewer"):
        return jsonify({"error": "无效的角色"}), 400

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
    )

    # 不返回密码哈希
    return jsonify({"success": True, "data": user})


@auth_bp.route("/auth/users/<user_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_user(user_id: str):
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


@auth_bp.route("/auth/register", methods=["POST"])
def register():
    """
    用户注册接口（开放注册，无需认证）

    Request Body:
        {
            "username": "new-user",
            "password": "password123",
            "display_name": "新用户",
            "role": "member"  # 可选，默认为 member
        }

    Response:
        {
            "success": True,
            "data": {
                "user_id": "user-xxx",
                "username": "new-user",
                "display_name": "新用户",
                "role": "member"
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
    role = data.get("role", "member")

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
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return jsonify({"error": "用户名只能包含字母、数字、下划线和中划线"}), 400

    # 验证角色
    if role not in ("admin", "member", "viewer"):
        return jsonify({"error": "无效的角色"}), 400

    # 注册用户默认角色为 member，不允许自注册为 admin
    if role == "admin":
        return jsonify({"error": "不允许自注册为管理员"}), 400

    # 检查用户名是否已存在
    existing_user = db_service.get_user_by_username(username)
    if existing_user:
        return jsonify({"error": "用户名已存在"}), 400

    # 哈希密码
    auth_service = get_auth_service()
    password_hash = auth_service.hash_password(password)

    # 生成用户 ID
    user_id = auth_service.generate_user_id()

    # 创建用户（默认角色为 member）
    user = db_service.create_user(
        user_id=user_id,
        username=username,
        password_hash=password_hash,
        display_name=display_name,
        role="member",  # 强制使用 member 角色
        is_active=True,
    )

    # 不返回密码哈希
    return jsonify({"success": True, "data": user})
