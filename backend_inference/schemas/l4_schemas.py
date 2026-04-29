"""
L4 Schemas - L4 需求相关的 Pydantic 数据模型

定义 L4Requirement、生成请求/响应、校验结果等结构
"""

from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ========================
# L4 需求结构
# ========================


class ValidatorIssue(BaseModel):
    """校验问题"""

    rule: str = Field(..., description="违反的规则名称")
    severity: Literal["error", "warning", "info"] = Field(
        default="error", description="严重程度"
    )
    message: str = Field(..., description="问题描述")
    field: Optional[str] = Field(default=None, description="涉及的字段")


class ValidatorStatus(BaseModel):
    """校验状态"""

    passed: bool = Field(default=False, description="是否通过校验")
    issues: List[ValidatorIssue] = Field(
        default_factory=list, description="校验问题列表"
    )


class L4Requirement(BaseModel):
    """L4 软件需求"""

    # 来源追溯
    source_top_id: str = Field(..., description="来源顶层需求 ID")
    source_top_text: Optional[str] = Field(
        default=None, description="来源顶层需求文本（方便审阅）"
    )

    # L4 标识
    l4_id: str = Field(
        default_factory=lambda: f"L4-{uuid4().hex[:8]}",
        description="L4 需求 ID（临时 UUID）",
    )
    component: str = Field(default="TBD", description="模块/子系统（不确定填 TBD）")

    # 需求正文
    shall_statement: str = Field(..., description="L4 需求正文（工程化、可实现）")

    # 验收与测试
    acceptance_criteria: List[str] = Field(
        default_factory=list, description="验收口径（必须可测）"
    )
    test_method: Literal[
        "unit", "integration", "system", "analysis", "manual", "TBD"
    ] = Field(default="TBD", description="测试方法")

    # 工程要素
    interfaces: List[str] = Field(
        default_factory=list, description="涉及的接口/外部交互（可空）"
    )
    data_contracts: List[str] = Field(
        default_factory=list, description="字段/格式/范围/幂等等（可空）"
    )
    error_handling: List[str] = Field(
        default_factory=list, description="异常、边界、超时、重试、错误码（可空但建议）"
    )
    nfr: List[str] = Field(
        default_factory=list, description="性能/安全/审计/日志等（可空）"
    )

    # 不确定项
    open_questions: List[str] = Field(
        default_factory=list, description="信息不足时必须有（替代'瞎写'）"
    )

    # 可解释性与置信度
    evidence_ids: List[str] = Field(
        default_factory=list, description="本条 L4 引用的 KB 证据 ID"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="置信度（低于阈值可触发 open_questions）",
    )
    issues: List[str] = Field(
        default_factory=list, description="生成阶段的自检问题（可选）"
    )

    # 校验状态
    validator_status: ValidatorStatus = Field(
        default_factory=ValidatorStatus, description="校验状态"
    )


# ========================
# 生成请求/响应
# ========================


class TopRequirement(BaseModel):
    """顶层需求输入"""

    id: str = Field(..., description="需求 ID")
    text: str = Field(..., description="需求文本")


class GenerateConfig(BaseModel):
    """生成配置"""

    top_k_pattern: int = Field(
        default=5, ge=1, le=20, description="Pattern KB 检索数量"
    )
    top_k_spec: int = Field(default=3, ge=1, le=10, description="Spec KB 检索数量")
    top_k_nfr: int = Field(default=3, ge=1, le=10, description="NFR KB 检索数量")
    max_l4_per_top_req: int = Field(
        default=10, ge=1, le=50, description="每条顶层需求最多生成的 L4 数量"
    )
    min_l4_per_top_req: int = Field(
        default=1, ge=0, le=10, description="每条顶层需求最少生成的 L4 数量"
    )
    confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, description="置信度阈值"
    )


class GenerateL4Request(BaseModel):
    """L4 生成请求"""

    requirements: List[TopRequirement] = Field(..., description="顶层需求列表")
    config: Optional[GenerateConfig] = Field(
        default_factory=GenerateConfig, description="生成配置"
    )
    model: Optional[str] = Field(
        default=None, description="模型 ID 覆盖（如 deepseek-v4-pro）"
    )
    use_thinking_mode: bool = Field(default=True, description="是否启用思考模式")


class GenerateL4Result(BaseModel):
    """单条顶层需求的生成结果"""

    source_top_id: str = Field(..., description="来源顶层需求 ID")
    l4_requirements: List[L4Requirement] = Field(
        default_factory=list, description="生成的 L4 需求列表"
    )
    open_questions: List[str] = Field(
        default_factory=list, description="待澄清问题列表"
    )


class GenerateL4Response(BaseModel):
    """L4 生成响应"""

    results: List[GenerateL4Result] = Field(..., description="生成结果列表")
    kb_version: str = Field(..., description="知识库版本")
    prompt_version: str = Field(default="v1.0", description="Prompt 版本")
    model_id: str = Field(..., description="使用的模型 ID")


# ========================
# 校验请求/响应
# ========================


class ValidateL4Request(BaseModel):
    """L4 校验请求"""

    l4_requirements: List[L4Requirement] = Field(..., description="待校验的 L4 列表")
    expected_top_ids: Optional[List[str]] = Field(
        default=None, description="期望覆盖的顶层需求 ID 列表"
    )
    open_questions_by_top_id: Optional[Dict[str, List[str]]] = Field(
        default=None, description="按顶层需求分组的 open_questions"
    )
    allowed_evidence_ids: Optional[List[str]] = Field(
        default=None, description="允许引用的 evidence_ids 白名单"
    )
    confidence_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="置信度阈值"
    )


class CoverageSummary(BaseModel):
    """覆盖率统计"""

    total_count: int = Field(default=0, description="总数")
    pass_count: int = Field(default=0, description="通过数")
    fail_count: int = Field(default=0, description="失败数")
    open_question_count: int = Field(default=0, description="有待澄清问题的数量")
    top_requirement_total: int = Field(default=0, description="顶层需求总数")
    top_requirement_passed: int = Field(default=0, description="顶层需求通过数")
    top_requirement_open_question: int = Field(
        default=0, description="顶层需求待澄清数"
    )
    top_requirement_failed: int = Field(default=0, description="顶层需求未覆盖数")


class ValidateL4Response(BaseModel):
    """L4 校验响应"""

    per_item_issues: Dict[str, List[ValidatorIssue]] = Field(
        default_factory=dict, description="每条 L4 的校验问题 (key=l4_id)"
    )
    coverage_summary: CoverageSummary = Field(
        default_factory=CoverageSummary, description="覆盖率统计"
    )
    global_pass: bool = Field(default=False, description="整体是否通过")
