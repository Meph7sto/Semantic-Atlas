"""
FastAPI 错误处理工具
提供 FastAPI 原生语义的错误响应格式
"""

from typing import Any, Dict

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_response(message: str, status_code: int) -> Dict[str, Any]:
    """返回与 FastAPI 原生语义一致的错误响应字典。"""
    return {"detail": message}


class ErrorResponse(Exception):
    """
    业务错误异常。

    Args:
        message: 错误消息
        status_code: HTTP 状态码，默认 400
    """

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """保留显式校验异常处理器，语义与 FastAPI 默认 422 保持一致。"""
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


async def error_response_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    统一异常处理：
    - ErrorResponse -> detail 字段
    - HTTPException -> 保留 status_code + detail
    - 其他异常 -> 500 Internal Server Error
    """
    if isinstance(exc, ErrorResponse):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "detail" in detail:
            content = detail
        else:
            content = {"detail": detail}
        return JSONResponse(status_code=exc.status_code, content=content)

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


def create_error_response(message: str, status_code: int) -> JSONResponse:
    """直接创建 FastAPI 风格错误响应。"""
    return JSONResponse(
        status_code=status_code,
        content={"detail": message},
    )


def create_success_response(data: Any) -> Any:
    """返回原始业务数据，不再包装 success/data 信封。"""
    return data
