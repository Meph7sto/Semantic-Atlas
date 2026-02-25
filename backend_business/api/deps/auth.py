"""
FastAPI 认证依赖
提供 JWT Token 验证和 RBAC 权限控制
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from backend_business.services.auth_service import get_auth_service


async def get_current_user(request: Request) -> dict:
    """
    JWT Token 验证依赖
    从 Authorization header 提取并验证 Bearer Token

    Args:
        request: FastAPI Request 对象

    Returns:
        用户信息字典：{"user_id": str, "username": str, "role": str, "external_type": Optional[str]}

    Raises:
        HTTPException: 401 当 Token 缺失或无效时
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证 Token",
        )

    token = auth_header.split(" ")[1]

    # 验证 token
    auth_service = get_auth_service()
    payload = auth_service.verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )

    # 返回用户信息（与 Flask 格式一致）
    user_info = {
        "user_id": payload.get("user_id"),
        "username": payload.get("username"),
        "role": payload.get("role"),
        "external_type": payload.get("external_type"),
    }

    # 将用户信息附加到 request 对象（用于后续依赖使用）
    request.state.current_user = user_info

    return user_info


def require_roles(*allowed_roles: str):
    """
    角色权限验证依赖工厂
    验证当前用户的角色是否在允许的角色列表中

    Args:
        *allowed_roles: 允许的角色列表，如 "admin", "member", "viewer"

    Returns:
        依赖函数，返回用户信息

    Raises:
        HTTPException: 403 当用户角色不在允许列表中时

    Usage:
        @router.get("/admin-only")
        async def admin_only(user: dict = Depends(require_roles("admin"))):
            return {"message": "admin access"}
    """

    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role")

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )

        return user

    return role_checker


# 便捷的角色依赖函数
async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求管理员角色的便捷依赖"""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )
    return user


async def require_member_or_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求成员或管理员角色的便捷依赖"""
    if user.get("role") not in ("admin", "member"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )
    return user
