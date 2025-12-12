from fastapi import APIRouter, HTTPException
from core.model_container import model_engine
from schemas.conflict_report import ConflictCheckRequest, ConflictCheckResponse

router = APIRouter(prefix="/conflict", tags=["Conflict Detection"])

SYSTEM_PROMPT_CONFLICT = """你是一个专业的系统需求分析专家。
你的任务是准确判断给定的两个需求（需求A 和 需求B）是否存在逻辑上的冲突或无法同时满足的情况。
如果存在冲突，请回答“冲突”并简要说明原因。
如果不存在冲突，请回答“不冲突”。
请只关注客观的技术或逻辑冲突。
"""

@router.post("/check", response_model=ConflictCheckResponse)
async def check_conflict(request: ConflictCheckRequest):
    """
    Specifically analyzes two requirements for potential conflicts.
    """
    prompt = f"需求A：{request.requirement_a}\n需求B：{request.requirement_b}\n这两个需求冲突吗？"
    
    try:
        # Use the shared model engine
        answer = model_engine.generate(
            prompt=prompt, 
            system_prompt=SYSTEM_PROMPT_CONFLICT,
            max_new_tokens=256
        )
        
        # Simple parsing logic (can be refined based on model output stability)
        is_conflict = "冲突" in answer and "不冲突" not in answer # Basic heuristic
        # A better heuristic might be needed depending on strict output, 
        # but the prompt asks for specific words.
        # Let's trust the "Conflicts" vs "Not Conflicts" keyword for now.
        if answer.startswith("冲突") or "是冲突" in answer:
             is_conflict = True
        elif "不冲突" in answer:
             is_conflict = False
        
        return ConflictCheckResponse(
            is_conflict=is_conflict,
            raw_response=answer
        )
            
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
