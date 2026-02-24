"""
FastAPI 错误处理工具
提供与 Flask 兼容的错误响应格式
"""

from typing import Any, Dict

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def error_response(message: str, status_code: int) -> Dict[str, Any]:
    """
    返回错误响应字典（Flask 兼容格式）

    Args:
        message: 错误消息
        status_code: HTTP 状态码

    Returns:
        错误响应字典：{"success": False, "error": message}

    Usage:
        raise HTTPException(
            status_code=400,
            detail=error_response("参数错误", 400)
        )
    """
    return {"success": False, "error": message}


class ErrorResponse(Exception):
    """
    自定义错误异常
    用于抛出 Flask 格式的错误响应

    Args:
        message: 错误消息
        status_code: HTTP 状态码，默认 400
    """

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def error_response_handler(request, exc):
    """
    全局异常处理器
    将异常转换为 Flask 兼容的 JSON 响应

    Args:
        request: FastAPI Request 对象
        exc: 异常对象

    Returns:
        JSONResponse with Flask-compatible format
    """
    if isinstance(exc, ErrorResponse):
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.message},
        )

    if isinstance(exc, HTTPException):
        # FastAPI HTTPException 转换为 Flask 格式
        detail = exc.detail
        if isinstance(detail, dict):
            # 如果 detail 已经是字典（包含 success 和 error），直接返回
            return JSONResponse(status_code=exc.status_code, content=detail)
        # 否则包装成 Flask 格式
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": str(detail)},
        )

    # 其他未捕获的异常
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "服务器内部错误"},
    )


def create_error_response(message: str, status_code: int) -> JSONResponse:
    """
    直接创建 Flask 格式的错误响应

    Args:
        message: 错误消息
        status_code: HTTP 状态码

    Returns:
        JSONResponse 对象
    """
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": message},
    )


def create_success_response(data: Any) -> Dict[str, Any]:
    """
    创建 Flask 格式的成功响应

    Args:
        data: 响应数据

    Returns:
        成功响应字典：{"success": True, "data": data}
    """
    return {"success": True, "data": data}
