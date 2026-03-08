from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class RequirementClassificationRequest(BaseModel):
    requirements: List[str] = Field(..., description="待分类的需求文本列表", min_length=1)
    batch_size: Optional[int] = Field(
        default=None, description="覆盖默认批大小", ge=1, le=1024
    )
    max_length: Optional[int] = Field(
        default=None, description="覆盖 tokenizer 截断长度", ge=16, le=4096
    )

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, value: List[str]) -> List[str]:
        if not any((str(item).strip() for item in value)):
            raise ValueError("requirements 至少包含一个有效文本")
        return value


class ClassificationPrediction(BaseModel):
    index: int = Field(description="原始输入索引")
    requirement: str = Field(description="需求文本")
    predicted_label: str = Field(description="预测类别标签")


class RequirementClassificationResponse(BaseModel):
    total: int = Field(description="预测的需求条目数量")
    predictions: List[ClassificationPrediction] = Field(description="逐条分类结果")
    label_distribution: Dict[str, int] = Field(
        description="按标签统计的频次，协助绘图"
    )
