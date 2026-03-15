"""
FastAPI SSE (Server-Sent Events) 工具
提供 SSE 事件格式化和响应生成功能
"""

import json
from collections.abc import AsyncGenerator as AsyncGeneratorABC
from collections.abc import Generator as GeneratorABC
from typing import AsyncGenerator, Generator, Union

from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool


# SSE 响应头
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def format_sse_event(event: str, data: dict) -> str:
    """
    格式化 SSE 事件

    Args:
        event: 事件名称（如 "message", "error", "done"）
        data: 事件数据字典

    Returns:
        格式化的 SSE 事件字符串：`event: {event}\ndata: {json}\n\n`

    Example:
        >>> format_sse_event("message", {"text": "测试"})
        'event: message\\ndata: {"text": "测试"}\\n\\n'
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_response(
    generator: Union[Generator, AsyncGenerator],
    event_type: str = "message",
) -> StreamingResponse:
    """
    创建 SSE 响应

    Args:
        generator: 数据生成器（同步或异步）
        event_type: 默认事件类型，如果生成器返回的是数据字典则使用此事件名

    Returns:
        StreamingResponse 对象，media_type 为 "text/event-stream"

    Usage:
        def event_generator():
            for i in range(5):
                yield {"text": f"消息 {i}"}

        return sse_response(event_generator())
    """
    async def async_sse_generator():
        # 处理同步生成器（在线程池中迭代，避免阻塞/嵌套事件循环）
        if isinstance(generator, GeneratorABC):
            async for item in iterate_in_threadpool(generator):
                # 如果 item 是 (event, data) 元组，使用指定事件名
                if isinstance(item, tuple) and len(item) == 2:
                    event, data = item
                    yield format_sse_event(event, data)
                # 否则使用默认事件名
                elif isinstance(item, dict):
                    yield format_sse_event(event_type, item)
                else:
                    yield format_sse_event(event_type, {"data": item})
        # 处理异步生成器
        elif isinstance(generator, AsyncGeneratorABC):
            async for item in generator:
                if isinstance(item, tuple) and len(item) == 2:
                    event, data = item
                    yield format_sse_event(event, data)
                elif isinstance(item, dict):
                    yield format_sse_event(event_type, item)
                else:
                    yield format_sse_event(event_type, {"data": item})
        else:
            for item in generator:
                if isinstance(item, tuple) and len(item) == 2:
                    event, data = item
                    yield format_sse_event(event, data)
                elif isinstance(item, dict):
                    yield format_sse_event(event_type, item)
                else:
                    yield format_sse_event(event_type, {"data": item})

    return StreamingResponse(
        async_sse_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def sse_response_raw(generator: Union[Generator, AsyncGenerator]) -> StreamingResponse:
    """
    创建 SSE 响应（原始格式）
    适用于生成器已经返回格式化好的 SSE 字符串

    Args:
        generator: SSE 格式字符串生成器

    Returns:
        StreamingResponse 对象
    """
    async def async_sse_generator():
        if isinstance(generator, GeneratorABC):
            async for chunk in iterate_in_threadpool(generator):
                yield chunk
        elif isinstance(generator, AsyncGeneratorABC):
            async for chunk in generator:
                yield chunk
        else:
            for chunk in generator:
                yield chunk

    return StreamingResponse(
        async_sse_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
