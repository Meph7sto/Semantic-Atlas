from pydantic import BaseModel, Field
from core.engine.remote.deepseek import DEFAULT_DEEPSEEK_MODEL

class ConflictCheckRequest(BaseModel):
    """
    冲突检查请求模型
    """
    requirement_a: str = Field(..., description="Description of the first requirement") # 需求 A 的描述
    requirement_b: str = Field(..., description="Description of the second requirement") # 需求 B 的描述
    model: str = Field(DEFAULT_DEEPSEEK_MODEL, description="DeepSeek model name")
    use_thinking_mode: bool = Field(True, description="Whether to use reasoning model")

class ConflictCheckResponse(BaseModel):
    """
    冲突检查响应模型
    """
    is_conflict: bool = Field(..., description="True if conflict is detected, False otherwise") # 如果检测到冲突则为 True，否则为 False
    raw_response: str = Field(..., description="The raw explanation or response from the model") # 模型返回的原始解释或响应
