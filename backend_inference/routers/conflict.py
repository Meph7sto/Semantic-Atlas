from fastapi import APIRouter, HTTPException
from core.model_container import model_engine
from schemas.conflict_report import ConflictCheckRequest, ConflictCheckResponse

# 创建 API Router，设置前缀为 /conflict，标签为 Conflict Detection
router = APIRouter(prefix="/conflict", tags=["Conflict Detection"])

# 定义系统提示词，用于指导模型进行冲突检测
SYSTEM_PROMPT_CONFLICT = """你是一个严格的系统需求分析专家。
你的任务是判断“需求A”和“需求B”是否存在实质性的逻辑冲突。

判断规则：
1. 冲突：指两个需求无法同时被满足（例如 A要求“响应时间<1s”，B要求“响应时间>2s”；或者 A要求“黑色背景”，B要求“白色背景”）。
2. 不冲突：指两个需求兼容、一致、或者属于不同维度（例如 A要求“快”，B要求“快”；或者 A要求“界面美观”，B要求“功能稳定”）。
3. 需求内容相同或相似，视为“不冲突”。

输出格式：
- 如果冲突，请直接以“冲突”开头，后跟简短原因。
- 如果不冲突，请直接以“不冲突”开头。
"""

@router.post("/check", response_model=ConflictCheckResponse)
async def check_conflict(request: ConflictCheckRequest):
    """
    专门分析两个需求是否存在潜在冲突。
    """
    # 构造用户提示词
    prompt = f"需求A：{request.requirement_a}\n需求B：{request.requirement_b}\n这两个需求冲突吗？"
    
    try:
        # 使用共享的模型引擎生成回答
        answer = model_engine.generate(
            prompt=prompt, 
            system_prompt=SYSTEM_PROMPT_CONFLICT,
            max_new_tokens=256
        )
        
        # 简单的解析逻辑 (可以根据模型输出的稳定性进行优化)
        # 鲁棒的解析逻辑
        clean_answer = answer.strip()
        if clean_answer.startswith("不冲突"):
             is_conflict = False
        elif clean_answer.startswith("冲突"):
             is_conflict = True
        else:
             # 回退方案: 查找关键词
             if "不冲突" in clean_answer:
                 is_conflict = False
             elif "冲突" in clean_answer:
                 is_conflict = True
             else:
                 is_conflict = False # 默认的安全假设
        
        return ConflictCheckResponse(
            is_conflict=is_conflict,
            raw_response=answer
        )
            
    except RuntimeError as e:
        # 如果模型服务未初始化或不可用，抛出 503 错误
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        # 捕获其他异常，抛出 500 错误
        raise HTTPException(status_code=500, detail=str(e))
