"""
Data models for requirements deduplication service
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DuplicateGroup:
    """一组疑似重复的需求"""

    group_id: str
    level: str
    requirements: List[Dict[str, Any]]  # req_id, text, fingerprint, created_at
    similarity: float  # 组内平均相似度
    representative_text: str  # 最长/最完整的文本，用于参考


@dataclass
class MergeDecision:
    """LLM的合并决策结果"""

    should_merge: bool
    merged_text: str = ""
    merged_level: str = ""
    primary_req_id: str = ""
    reason: str = ""
    error: Optional[str] = None


@dataclass
class MergeResult:
    """执行合并后的结果"""

    success: bool
    primary_req_id: str
    deleted_count: int = 0
    old_text: str = ""
    new_text: str = ""
    reason: str = ""
    error: Optional[str] = None


@dataclass
class DeduplicationResult:
    """去重检测的完整结果"""

    duplicate_groups: List[Dict[str, Any]] = field(default_factory=list)
    total_duplicates: int = 0
    total_requirements_scanned: int = 0
    total_merged: int = 0
    errors: List[str] = field(default_factory=list)
