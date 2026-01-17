
from dataclasses import asdict
import json
import queue
import threading
import time
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from services.requirements_acquisition_service import acquisition_service, RequirementGroup, RequirementItem

router = APIRouter(
    prefix="/acquisition",
    tags=["acquisition"],
    responses={404: {"description": "Not found"}},
)

# --- Pydantic Models for API ---

class ExtractionRequest(BaseModel):
    text: str
    chunk_size: Optional[int] = 3600
    overlap: Optional[int] = 500
    clean_model: Optional[str] = "deepseek-chat"
    extract_model: Optional[str] = "deepseek-reasoner"

class RequirementItemModel(BaseModel):
    statement: str
    rationale: str
    evidence: str
    confidence: float

class ExtractionResponse(BaseModel):
    business_requirements: List[RequirementItemModel]
    stakeholder_requirements: List[RequirementItemModel]
    system_requirements: List[RequirementItemModel]

def _serialize_result(result: RequirementGroup) -> dict:
    return {
        "business_requirements": [asdict(item) for item in result.business],
        "stakeholder_requirements": [asdict(item) for item in result.stakeholder],
        "system_requirements": [asdict(item) for item in result.system],
    }

def _format_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

# --- Endpoints ---

@router.post("/extract", response_model=ExtractionResponse)
async def extract_requirements(request: ExtractionRequest):
    try:
        # Update service config based on request if needed (not thread-safe in this simple impl, but okay for demo)
        acquisition_service.chunk_size = request.chunk_size
        acquisition_service.overlap = request.overlap
        
        result: RequirementGroup = acquisition_service.process(
            request.text, 
            clean_model=request.clean_model,
            extract_model=request.extract_model
        )
        
        return ExtractionResponse(
            business_requirements=[
                RequirementItemModel(**asdict(item)) for item in result.business
            ],
            stakeholder_requirements=[
                RequirementItemModel(**asdict(item)) for item in result.stakeholder
            ],
            system_requirements=[
                RequirementItemModel(**asdict(item)) for item in result.system
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/extract/stream")
async def extract_requirements_stream(request: ExtractionRequest):
    q = queue.Queue()

    def on_progress(payload: dict) -> None:
        q.put(("progress", payload))

    def worker() -> None:
        try:
            acquisition_service.chunk_size = request.chunk_size
            acquisition_service.overlap = request.overlap
            result: RequirementGroup = acquisition_service.process(
                request.text,
                clean_model=request.clean_model,
                extract_model=request.extract_model,
                on_progress=on_progress,
            )
            q.put(("result", _serialize_result(result)))
        except Exception as exc:
            q.put(("error", {"error": str(exc)}))
        finally:
            q.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        while True:
            try:
                event, payload = q.get(timeout=10)
            except queue.Empty:
                yield _format_sse("ping", {"ts": time.time()})
                continue
            if event == "done":
                break
            yield _format_sse(event, payload or {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
