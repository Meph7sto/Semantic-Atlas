"""
认证路由 - FastAPI 版本
对应 Flask blueprint: auth_bp (url_prefix="/api")
"""

from typing import Optional

from fastapi import APIRouter, Depends

from backend_business.services.db_service import db_service
from backend_business.services.auth_service import get_auth_service
from backend_business.api.deps.auth import get_current_user, require_admin
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.auth_schemas import (
    LoginRequest,
    RegisterRequest,
    ChangePasswordRequest,
    UpdateProfileRequest,
    CreateUserRequest,
    UpdateUserRequest,
)

router = APIRouter(prefix="/api", tags=["auth"])


# ========================
# 公开端点（无需认证）
# ========================

@router.post("/auth/login")
def login(req: LoginRequest):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    username = req.username.strip()
    password = req.password
    selected_role = req.role

    if not username or not password:
        raise ErrorResponse("用户名和密码不能为空", 400)

    # 验证用户名和密码
    user = db_service.get_user_by_username(username)
    if not user:
        raise ErrorResponse("用户名或密码错误", 401)

    auth_service = get_auth_service()
    if not auth_service.verify_password(password, user["password_hash"]):
        raise ErrorResponse("用户名或密码错误", 401)

    # 检查用户是否激活
    if not user.get("is_active", True):
        raise ErrorResponse("用户已被禁用", 403)

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

    return {
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


@router.post("/auth/logout")
def logout():
    """
    用户登出接口（客户端自行删除 Token 即可，服务器端为无状态）

    Response:
        {
            "success": True,
            "message": "登出成功"
        }
    """
    return {"success": True, "message": "登出成功"}


@router.post("/auth/register")
def register(req: RegisterRequest):
    """
    用户注册接口（开放注册，无需认证）

    Request Body:
        {
            "username": "new-user",
            "password": "password123",
            "display_name": "新用户",
            "role": "viewer",  # 可选，默认为 viewer
            "external_type": "CLIENT"  # 可选
        }

    Response:
        {
            "success": True,
            "data": {
                "user_id": "user-xxx",
                "username": "new-user",
                "display_name": "新用户",
                "role": "viewer",
                "external_type": "CLIENT"
            }
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    username = req.username
    password = req.password
    display_name = req.display_name
    role = req.role
    external_type = req.external_type

    # 验证角色（前端传入的角色会被忽略，统一强制为 viewer）
    if role not in ("admin", "member", "viewer"):
        raise ErrorResponse("无效的角色", 400)

    # 不允许自注册为 admin 或 member，注册后默认为 viewer（只读）
    if role in ("admin", "member"):
        raise ErrorResponse("注册后默认为只读访客（viewer），如需更高权限请联系管理员", 400)

    # 验证 external_type
    if external_type and external_type not in ("CLIENT", "CONTRACTOR"):
        raise ErrorResponse("无效的外部身份类型", 400)

    # 检查用户名是否已存在
    existing_user = db_service.get_user_by_username(username)
    if existing_user:
        raise ErrorResponse("用户名已存在", 400)

    # 哈希密码
    auth_service = get_auth_service()
    password_hash = auth_service.hash_password(password)

    # 生成用户 ID
    user_id = auth_service.generate_user_id()

    # 创建用户（默认角色为 viewer，只读权限）
    user = db_service.create_user(
        user_id=user_id,
        username=username,
        password_hash=password_hash,
        display_name=display_name,
        role="viewer",  # 注册默认为 viewer（只读），后续由管理员修改
        is_active=True,
        external_type=external_type,
    )

    return {"success": True, "data": user}


# ========================
# 需要认证的端点
# ========================

@router.get("/auth/verify")
def verify_token(current_user: dict = Depends(get_current_user)):
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
    return {"success": True, "data": current_user}


@router.get("/auth/me")
def get_current_user_info(current_user: dict = Depends(get_current_user)):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        raise ErrorResponse("用户不存在", 404)

    # 不返回密码哈希
    user.pop("password_hash", None)

    return {"success": True, "data": user}


@router.get("/auth/profile")
def get_profile(current_user: dict = Depends(get_current_user)):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        raise ErrorResponse("用户不存在", 404)

    user.pop("password_hash", None)
    return {"success": True, "data": user}


@router.patch("/auth/profile")
def update_profile(req: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    user = db_service.update_profile(
        user_id=user_id,
        display_name=req.display_name,
        avatar_url=req.avatar_url,
    )

    if not user:
        raise ErrorResponse("用户不存在", 404)

    user.pop("password_hash", None)
    return {"success": True, "data": user}


@router.post("/auth/profile/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    old_password = req.old_password
    new_password = req.new_password

    if old_password == new_password:
        raise ErrorResponse("新密码不能与当前密码相同", 400)

    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        raise ErrorResponse("用户不存在", 404)

    auth_service = get_auth_service()
    if not auth_service.verify_password(old_password, user["password_hash"]):
        raise ErrorResponse("当前密码不正确", 400)

    new_hash = auth_service.hash_password(new_password)
    success = db_service.change_password(user_id=user_id, new_password_hash=new_hash)

    if not success:
        raise ErrorResponse("密码修改失败，请稍后重试", 500)

    return {"success": True, "message": "密码修改成功"}


# ========================
# 管理员端点
# ========================

@router.get("/auth/users")
def list_users(
    role: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(require_admin),
):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    result = db_service.list_users(role=role, limit=limit, offset=offset)

    return {"success": True, "data": result}


@router.post("/auth/users")
def create_user(
    req: CreateUserRequest,
    current_user: dict = Depends(require_admin),
):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    username = req.username.strip()
    password = req.password
    display_name = req.display_name.strip()
    role = req.role
    external_type = req.external_type

    if not username or not password:
        raise ErrorResponse("用户名和密码不能为空", 400)

    if not display_name:
        raise ErrorResponse("显示名称不能为空", 400)

    if role not in ("admin", "member", "viewer"):
        raise ErrorResponse("无效的角色", 400)

    # 验证 external_type
    if external_type and external_type not in ("CLIENT", "CONTRACTOR"):
        raise ErrorResponse("无效的外部身份类型", 400)

    # 检查用户名是否已存在
    existing_user = db_service.get_user_by_username(username)
    if existing_user:
        raise ErrorResponse("用户名已存在", 400)

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

    return {"success": True, "data": user}


@router.patch("/auth/users/{user_id}")
def update_user(
    user_id: str,
    req: UpdateUserRequest,
    current_user: dict = Depends(require_admin),
):
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
        raise ErrorResponse("数据库服务未初始化", 500)

    display_name = req.display_name
    role = req.role
    is_active = req.is_active

    if role and role not in ("admin", "member", "viewer"):
        raise ErrorResponse("无效的角色", 400)

    user = db_service.update_user(
        user_id=user_id,
        display_name=display_name,
        role=role,
        is_active=is_active,
    )

    if not user:
        raise ErrorResponse("用户不存在", 404)

    return {"success": True, "data": user}
