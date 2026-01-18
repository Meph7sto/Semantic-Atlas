import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from core.model_container import model_engine
from schemas.chat import ChatRequest
from services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["General Chat"])

chat_service = ChatService(model_engine)

logger = logging.getLogger(__name__)


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
            ),
            media_type="application/x-ndjson",
        )
    except RuntimeError:
        logger.exception("Chat stream failed with RuntimeError.")
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        logger.exception("Chat stream failed with unexpected exception.")
        raise HTTPException(status_code=500, detail=str(e))
