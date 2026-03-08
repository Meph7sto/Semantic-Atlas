from pydantic import BaseModel
from typing import Optional

class InferenceRequest(BaseModel):
    """
    通用推理请求模型
    """
    prompt: str # 用户输入的提示词
    system_prompt: str = "你是一个有用的中文助手。" # 系统提示词，默认为中文助手
    max_new_tokens: int = 128 # 生成的最大新 token 数

class InferenceResponse(BaseModel):
    """
    通用推理响应模型
    """
    answer: str # 模型的回答
