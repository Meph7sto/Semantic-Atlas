"""
Conflict API Pydantic 请求模型
对应历史蓝图: conflict_bp
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ConflictCheckRequest(BaseModel):
    """单条冲突检测请求"""

    requirement_a: NonEmptyStr
    requirement_b: NonEmptyStr
    model: str = "deepseek-v4-pro"
    use_thinking_mode: bool = True
    save_to_db: bool = False
    session_id: str | None = None


class ConflictPair(BaseModel):
    """批量检测中的需求对"""

    requirement_a: NonEmptyStr
    requirement_b: NonEmptyStr


class ConflictCheckBatchRequest(BaseModel):
    """批量冲突检测请求"""

    pairs: list[ConflictPair] = Field(min_length=1)
    model: str = "deepseek-v4-pro"
    use_thinking_mode: bool = True
    save_to_db: bool = False
    session_id: str | None = None


class ConflictRequirementSnapshot(BaseModel):
    """冲突分析使用的需求快照"""

    requirement_id: NonEmptyStr
    text: NonEmptyStr
    level: str = "L1"
    parent_id: str | None = None
    source_top_id: str | None = None
    title: str | None = None
    component: str | None = None
    module: str | None = None
    status: str | None = None
    priority: str | None = None


class ConflictAnalyzeRequest(BaseModel):
    """批量冲突分析请求"""

    requirements: list[ConflictRequirementSnapshot] = Field(min_length=2)
    model: str = "deepseek-v4-pro"
    use_thinking_mode: bool = True
    save_to_db: bool = False
    session_id: str | None = None
    conflict_concurrency: int = Field(default=3, ge=1, le=8)
    max_candidates_per_bucket: int = Field(default=20, ge=1, le=50)
