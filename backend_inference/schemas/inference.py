from pydantic import BaseModel
from typing import Optional

class InferenceRequest(BaseModel):
    prompt: str
    system_prompt: str = "你是一个有用的中文助手。"
    max_new_tokens: int = 128

class InferenceResponse(BaseModel):
    answer: str
