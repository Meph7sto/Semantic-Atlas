"""
Deduplication API Pydantic 请求模型
对应历史蓝图: dedup_bp
"""

from typing import Optional

from pydantic import BaseModel, Field


class DetectDuplicatesRequest(BaseModel):
    """检测重复需求请求"""
    session_id: str = Field(min_length=1)
    level: Optional[str] = None  # "L1" | "L2" | "L3"
    with_llm_decision: bool = True
    auto_merge: bool = False
    pairwise_review: bool = False
    pairwise_auto_apply: bool = False
    pairwise_max_pairs: Optional[int] = Field(default=None, ge=1, le=5000)
    model: Optional[str] = None
    threshold: Optional[float] = None
    max_concurrent: int = Field(default=5, ge=1, le=10)


class MergeRequest(BaseModel):
    """执行合并操作请求"""
    session_id: str = Field(min_length=1)
    primary_req_id: str = Field(min_length=1)
    to_delete_req_ids: list[str] = Field(min_length=1)
    merged_text: str = Field(min_length=1)
    merged_level: str = Field(min_length=1)
    reason: Optional[str] = None


class DeleteRequirementsRequest(BaseModel):
    """批量删除需求请求"""
    session_id: str = Field(min_length=1)
    req_ids: list[str] = Field(min_length=1)
    reason: Optional[str] = None


class UpdateRequirementRequest(BaseModel):
    """更新单个需求请求"""
    session_id: str = Field(min_length=1)
    req_id: str = Field(min_length=1)
    new_text: str = Field(min_length=1)
    new_level: Optional[str] = None
    reason: Optional[str] = None


class GetSimilarPairsRequest(BaseModel):
    """获取相似需求对请求"""
    session_id: str = Field(min_length=1)
    level: Optional[str] = None
    threshold: Optional[float] = None


class RegenerateLLMDecisionRequest(BaseModel):
    """重新生成 LLM 合并决策请求"""
    session_id: str = Field(min_length=1)
    req_ids: list[str] = Field(min_length=2)
    model: Optional[str] = None
