"""
Classification API Pydantic 请求模型
对应 Flask blueprint: classification_bp
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PredictTextsRequest(BaseModel):
    """文本分类请求"""

    requirements: list[str] = Field(min_length=1)
    save_to_db: bool = False
    session_id: Optional[str] = None
    batch_size: Optional[int] = Field(default=None, ge=1)
    max_length: Optional[int] = Field(default=None, ge=1)

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None
