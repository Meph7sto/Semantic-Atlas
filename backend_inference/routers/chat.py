import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from core.model_container import model_engine
from schemas.chat import ChatRequest
from services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["General Chat"])

chat_service = ChatService(model_engine)

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="List of messages")
    model: str = Field(default="deepseek-chat", description="Model name")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=8000)


class ChatCompletionResponse(BaseModel):
    content: str = Field(..., description="Generated content")
    usage: Optional[Dict[str, Any]] = Field(default=None, description="Token usage stats")


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
                use_thinking_mode=request.use_thinking_mode,
            ),
            media_type="application/x-ndjson",
        )
    except RuntimeError:
        logger.exception("Chat stream failed with RuntimeError.")
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
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
                system_prompt += msg.content + "\n"
            elif msg.role == "user":
                user_prompt += msg.content + "\n"
            elif msg.role == "assistant":
                # 可以支持多轮对话，这里简化处理
                pass

        system_prompt = system_prompt.strip()
        user_prompt = user_prompt.strip()

        if not user_prompt:
            raise HTTPException(status_code=400, detail="User message is required.")

        # 调用模型生成
        result = model_engine.generate(
            prompt=user_prompt,
            system_prompt=system_prompt if system_prompt else None,
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        # 返回结果
        return ChatCompletionResponse(
            content=result.get("output", ""),
            usage=result.get("usage"),
        )

    except RuntimeError:
        logger.exception("Chat completion failed with RuntimeError.")
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        logger.exception("Chat completion failed with unexpected exception.")
        raise HTTPException(status_code=500, detail=str(e))
