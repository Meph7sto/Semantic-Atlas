"""
KB Schemas - 知识库相关的 Pydantic 数据模型

定义 Evidence、Search 请求/响应等结构
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ========================
# Evidence 条目
# ========================


class EvidenceItem(BaseModel):
    """知识库检索返回的证据条目"""

    evidence_id: str = Field(
        ..., description="稳定ID，格式: pattern-xxxx / spec-xxxx / nfr-xxxx"
    )
    kb_type: Literal["pattern", "spec", "nfr"] = Field(..., description="知识库类型")
    text: str = Field(..., description="证据文本内容")
    score: float = Field(..., description="相似度得分 (0~1)")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="元数据: domain, capability_type, nfr_type, language, source 等",
    )


class PatternEvidence(EvidenceItem):
    """Pattern KB 特有结构：高层→低层分解范式"""

    high_text: str = Field(..., description="高层需求表述")
    low_text: str = Field(..., description="低层需求表述")


# ========================
# Search 请求/响应
# ========================


class KBSearchRequest(BaseModel):
    """KB 检索请求"""

    query: str = Field(..., description="检索查询文本")
    kb_type: Literal["pattern", "spec", "nfr", "all"] = Field(
        default="all", description="知识库类型，'all' 表示检索全部"
    )
    top_k: int = Field(default=5, ge=1, le=50, description="返回条目数量")
    filters: Optional[Dict[str, str]] = Field(
        default=None,
        description="过滤条件: domain, capability_type, nfr_type, language",
    )


class KBSearchResponse(BaseModel):
    """KB 检索响应"""

    items: List[EvidenceItem] = Field(..., description="检索到的证据条目列表")
    kb_version: str = Field(..., description="知识库版本标识")
    total_searched: int = Field(default=0, description="被检索的知识库总条目数")


# ========================
# KB 状态
# ========================


class KBStatus(BaseModel):
    """知识库状态"""

    is_loaded: bool = Field(default=False, description="索引是否已加载")
    kb_version: str = Field(default="", description="知识库版本")
    pattern_count: int = Field(default=0, description="Pattern KB 条目数")
    spec_count: int = Field(default=0, description="Spec KB 条目数")
    nfr_count: int = Field(default=0, description="NFR KB 条目数")
    hard_negative_count: int = Field(
        default=0, description="Pattern hard negatives 条目数"
    )
    index_path: str = Field(default="", description="索引持久化路径")
