import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from core.model_container import model_engine
from core.engine.remote.deepseek import DEFAULT_DEEPSEEK_MODEL
from schemas.chat import ChatRequest
from services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["General Chat"])

chat_service = ChatService(model_engine)

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: system, user, or assistant")
    content: Optional[str] = Field(default=None, description="Message content")
    reasoning_content: Optional[str] = Field(
        default=None, description="Reasoning content for assistant tool-call messages"
    )
    tool_call_id: Optional[str] = Field(
        default=None, description="Tool call ID for tool role"
    )
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Tool calls from assistant"
    )


class ToolFunction(BaseModel):
    name: str = Field(..., description="Function name")
    description: Optional[str] = Field(default=None, description="Function description")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Function parameters schema"
    )


class Tool(BaseModel):
    type: str = Field(default="function", description="Tool type, always 'function'")
    function: ToolFunction = Field(..., description="Function definition")


class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="List of messages")
    model: str = Field(default=DEFAULT_DEEPSEEK_MODEL, description="Model name")
    thinking_enabled: bool = Field(default=True, description="Enable thinking mode")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=8000)


class ChatCompletionWithToolsRequest(BaseModel):
    """带工具定义的 chat completions 请求"""

    messages: List[ChatMessage] = Field(..., description="List of messages")
    tools: List[Dict[str, Any]] = Field(..., description="List of tool definitions")
    model: str = Field(default=DEFAULT_DEEPSEEK_MODEL, description="Model name")
    thinking_enabled: bool = Field(default=True, description="Enable thinking mode")
    temperature: Optional[float] = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=8000)
    tool_choice: Optional[str] = Field(
        default=None, description="Tool choice: none, auto, required"
    )
    use_async_client: bool = Field(
        default=False, description="Use async client for streaming"
    )


class ToolCallFunction(BaseModel):
    name: str
    arguments: str


class ToolCallItem(BaseModel):
    id: str
    type: str = "function"
    function: ToolCallFunction


class ChatCompletionResponse(BaseModel):
    content: str = Field(..., description="Generated content")
    usage: Optional[Dict[str, Any]] = Field(
        default=None, description="Token usage stats"
    )


class ContextCompletionRequest(BaseModel):
    prompt: str = Field(..., description="Prompt content")
    system_prompt: str = Field(default="", description="System prompt")
    model: Optional[str] = Field(default=None, description="Model override")
    thinking_enabled: bool = Field(default=True, description="Enable thinking mode")
    max_tokens: int = Field(default=8000, ge=1, le=12000)


class ContextCompletionResponse(BaseModel):
    content: str = Field(..., description="Generated content")


class ChatCompletionWithToolsResponse(BaseModel):
    """带工具调用的 chat completions 响应"""

    content: Optional[str] = Field(
        default=None, description="Generated content (if any)"
    )
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Tool calls from model"
    )
    reasoning_content: Optional[str] = Field(
        default=None, description="Reasoning content (for thinking mode)"
    )
    finish_reason: Optional[str] = Field(
        default=None, description="Finish reason: stop, tool_calls, length"
    )


def _convert_messages(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    """将 Pydantic ChatMessage 列表转为 dict 列表"""
    result = []
    for msg in messages:
        msg_dict = {"role": msg.role}
        if msg.content is not None:
            msg_dict["content"] = msg.content
        if msg.reasoning_content is not None:
            msg_dict["reasoning_content"] = msg.reasoning_content
        if msg.tool_call_id is not None:
            msg_dict["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls is not None:
            msg_dict["tool_calls"] = msg.tool_calls
        result.append(msg_dict)
    return result


def _ndjson_line(obj: Dict[str, Any]) -> str:
    """Serialize one NDJSON line (ASCII-safe by default)."""
    return json.dumps(obj, ensure_ascii=False) + "\n"


@router.post("/stream")
async def stream_chat(request: ChatRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required.")

    try:
        return StreamingResponse(
            chat_service.ask_stream(
                prompt=request.prompt,
                system_prompt=request.system_prompt,
                max_new_tokens=request.max_new_tokens,
                model=request.model,
                use_thinking_mode=request.use_thinking_mode,
                use_async_client=request.use_async_client,
            ),
            media_type="application/x-ndjson",
        )
    except RuntimeError:
        logger.exception("Chat stream failed with RuntimeError.")
        raise HTTPException(
            status_code=503, detail="Model service not initialized or unavailable."
        )
    except Exception as e:
        logger.exception("Chat stream failed with unexpected exception.")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    """
    标准 chat completions 接口
    用于需求抽取等任务
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list is required.")

    try:
        # 构建 system prompt 和 user prompt
        system_prompt = ""
        user_prompt = ""

        for msg in request.messages:
            if msg.role == "system":
                system_prompt += (msg.content or "") + "\n"
            elif msg.role == "user":
                user_prompt += (msg.content or "") + "\n"
            elif msg.role == "assistant":
                # 可以支持多轮对话，这里简化处理
                pass

        system_prompt = system_prompt.strip()
        user_prompt = user_prompt.strip()

        if not user_prompt:
            raise HTTPException(status_code=400, detail="User message is required.")

        # 调用模型生成
        result = await model_engine.generate_async(
            prompt=user_prompt,
            system_prompt=system_prompt or "",
            max_new_tokens=request.max_tokens,
            model=request.model,
            thinking_enabled=request.thinking_enabled,
        )

        if isinstance(result, dict):
            content = str(result.get("output") or result.get("content") or "").strip()
            usage = result.get("usage")
        else:
            content = str(result or "").strip()
            usage = None

        return ChatCompletionResponse(
            content=content,
            usage=usage,
        )

    except RuntimeError:
        logger.exception("Chat completion failed with RuntimeError.")
        raise HTTPException(
            status_code=503, detail="Model service not initialized or unavailable."
        )
    except Exception as e:
        logger.exception("Chat completion failed with unexpected exception.")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context-completion", response_model=ContextCompletionResponse)
async def context_completion(request: ContextCompletionRequest):
    """
    Context builder 专用补全接口。
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required.")

    try:
        content = await model_engine.generate_async(
            prompt=request.prompt,
            system_prompt=request.system_prompt or "",
            max_new_tokens=request.max_tokens,
            model=request.model,
            thinking_enabled=request.thinking_enabled,
        )
        return ContextCompletionResponse(content=content or "")
    except RuntimeError:
        logger.exception("Context completion failed with RuntimeError.")
        raise HTTPException(
            status_code=503, detail="Model service not initialized or unavailable."
        )
    except Exception as e:
        logger.exception("Context completion failed with unexpected exception.")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context-completion/stream")
async def context_completion_stream(request: ContextCompletionRequest):
    """
    Context builder 专用流式补全接口。
    返回 NDJSON，每行一个 JSON 对象。
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required.")

    async def generate():
        full_response = ""

        def _handle_chunk(chunk):
            nonlocal full_response
            if isinstance(chunk, dict):
                msg_type = chunk.get("type", "content")
                content = chunk.get("delta", "")
                if msg_type == "thinking":
                    return "thinking", content
                if msg_type == "content":
                    full_response += content
                    return "token", content
                return None

            token = str(chunk)
            full_response += token
            return "token", token

        try:
            stream = model_engine.generate_stream_async(
                prompt=request.prompt,
                system_prompt=request.system_prompt or "",
                max_new_tokens=request.max_tokens,
                model=request.model,
                thinking_enabled=request.thinking_enabled,
            )

            async for chunk in stream:
                parsed = _handle_chunk(chunk)
                if not parsed:
                    continue
                msg_type, content = parsed
                if msg_type == "thinking":
                    yield _ndjson_line({"type": "thinking", "content": content})
                else:
                    yield _ndjson_line({"type": "token", "content": content})

            yield _ndjson_line({"type": "result", "data": {"answer": full_response}})
        except RuntimeError:
            logger.exception("Context completion stream failed with RuntimeError.")
            yield _ndjson_line(
                {
                    "type": "error",
                    "error": "Model service not initialized or unavailable.",
                }
            )
        except Exception as e:
            logger.exception("Context completion stream failed with unexpected exception.")
            yield _ndjson_line({"type": "error", "error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
    )


@router.post("/completions/tools", response_model=ChatCompletionWithToolsResponse)
async def chat_completions_with_tools(request: ChatCompletionWithToolsRequest):
    """
    带工具定义的 chat completions 接口
    支持 DeepSeek API tool call 格式
    参考: https://api-docs.deepseek.com/zh-cn/guides/tool_calls
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list is required.")

    if not request.tools:
        raise HTTPException(status_code=400, detail="Tools list is required.")

    try:
        messages = _convert_messages(request.messages)

        # 调用带工具的模型生成
        result = model_engine.generate_with_tools(
            messages=messages,
            tools=request.tools,
            max_new_tokens=request.max_tokens,
            tool_choice=request.tool_choice,
            model=request.model,
            temperature=request.temperature,
            thinking_enabled=request.thinking_enabled,
        )

        # 返回结果
        return ChatCompletionWithToolsResponse(
            content=result.content,
            tool_calls=result.tool_calls,
            reasoning_content=result.reasoning_content,
            finish_reason=result.finish_reason,
        )

    except NotImplementedError as e:
        logger.exception("Tool calls not supported for current provider.")
        raise HTTPException(status_code=501, detail=str(e))
    except RuntimeError:
        logger.exception("Chat completion with tools failed with RuntimeError.")
        raise HTTPException(
            status_code=503, detail="Model service not initialized or unavailable."
        )
    except Exception as e:
        logger.exception("Chat completion with tools failed with unexpected exception.")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/completions/tools/stream")
async def chat_completions_with_tools_stream(
    request: ChatCompletionWithToolsRequest,
):
    """
    带工具定义的流式 chat completions 接口
    返回 NDJSON 流，每行一个 JSON 对象
    chunk 类型: thinking / content / tool_call / finish
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages list is required.")

    if not request.tools:
        raise HTTPException(status_code=400, detail="Tools list is required.")

    messages = _convert_messages(request.messages)

    def _tools_stream_sync():
        try:
            for chunk in model_engine.generate_with_tools_stream(
                messages=messages,
                tools=request.tools,
                max_new_tokens=request.max_tokens,
                tool_choice=request.tool_choice,
                model=request.model,
                temperature=request.temperature,
                thinking_enabled=request.thinking_enabled,
            ):
                # Normalize engine chunk shape to business backend expectations.
                # Engine uses {type, delta/...}; business expects {type, content/...} and tool_call wrapper.
                t = chunk.get("type")
                if t in ("thinking", "content"):
                    yield _ndjson_line(
                        {
                            "type": t,
                            "content": chunk.get("content") or chunk.get("delta") or "",
                        }
                    )
                elif t == "tool_call":
                    tool_call = {
                        "index": chunk.get("index"),
                        "id": chunk.get("id"),
                        "function": chunk.get("function"),
                    }
                    yield _ndjson_line({"type": "tool_call", "tool_call": tool_call})
                elif t == "finish":
                    yield _ndjson_line(
                        {"type": "finish", "finish_reason": chunk.get("finish_reason")}
                    )
                else:
                    yield _ndjson_line(chunk)
        except Exception as e:
            logger.exception("Tool stream (sync) error.")
            yield _ndjson_line({"type": "error", "message": str(e)})

    async def _tools_stream_async():
        try:
            async for chunk in model_engine.generate_with_tools_stream_async(
                messages=messages,
                tools=request.tools,
                max_new_tokens=request.max_tokens,
                tool_choice=request.tool_choice,
                model=request.model,
                temperature=request.temperature,
                thinking_enabled=request.thinking_enabled,
            ):
                t = chunk.get("type")
                if t in ("thinking", "content"):
                    yield _ndjson_line(
                        {
                            "type": t,
                            "content": chunk.get("content") or chunk.get("delta") or "",
                        }
                    )
                elif t == "tool_call":
                    tool_call = {
                        "index": chunk.get("index"),
                        "id": chunk.get("id"),
                        "function": chunk.get("function"),
                    }
                    yield _ndjson_line({"type": "tool_call", "tool_call": tool_call})
                elif t == "finish":
                    yield _ndjson_line(
                        {"type": "finish", "finish_reason": chunk.get("finish_reason")}
                    )
                else:
                    yield _ndjson_line(chunk)
        except Exception as e:
            logger.exception("Tool stream (async) error.")
            yield _ndjson_line({"type": "error", "message": str(e)})

    generator = (
        _tools_stream_async() if request.use_async_client else _tools_stream_sync()
    )

    return StreamingResponse(generator, media_type="application/x-ndjson")
