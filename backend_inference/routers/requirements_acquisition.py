from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.engine.remote.deepseek import DEFAULT_DEEPSEEK_MODEL
from services.requirements_acquisition_service import acquisition_service, RequirementGroup

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
    clean_model: Optional[str] = DEFAULT_DEEPSEEK_MODEL
    extract_model: Optional[str] = DEFAULT_DEEPSEEK_MODEL
    use_thinking_mode: bool = True

class RequirementItemModel(BaseModel):
    statement: str
    rationale: str
    evidence: str
    confidence: float

class ExtractionResponse(BaseModel):
    business_requirements: List[RequirementItemModel]
    stakeholder_requirements: List[RequirementItemModel]
    system_requirements: List[RequirementItemModel]

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
            extract_model=request.extract_model,
            use_thinking_mode=request.use_thinking_mode,
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
