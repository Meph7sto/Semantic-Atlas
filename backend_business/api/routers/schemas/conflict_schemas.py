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
    save_to_db: bool = False
    session_id: str | None = None
