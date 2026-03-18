"""
Execution Graph API Pydantic 请求模型
执行拓扑图的请求和响应模式
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

_ALLOWED_NODE_TYPES = {"start", "node", "decision", "handoff", "end", "llm", "invoke"}
_ALLOWED_EDGE_TYPES = {"call", "return", "retry"}
_ALLOWED_ROLE_TYPES = {"human", "agent", "system"}
_ALLOWED_GRAPH_STATUSES = {"draft", "active", "running", "succeeded", "failed", "suspended"}


def normalize_node_type(node_type: Any) -> str:
    """规范化节点类型"""
    if not isinstance(node_type, str):
        raise ValueError(f"node_type 必须是字符串: {', '.join(_ALLOWED_NODE_TYPES)}")
    normalized = node_type.lower()
    if normalized not in _ALLOWED_NODE_TYPES:
        raise ValueError(f"node_type 必须是: {', '.join(_ALLOWED_NODE_TYPES)}")
    return normalized


def normalize_edge_type(edge_type: Any) -> str:
    """规范化边类型"""
    if not isinstance(edge_type, str):
        raise ValueError(f"edge_type 必须是字符串: {', '.join(_ALLOWED_EDGE_TYPES)}")
    normalized = edge_type.lower()
    if normalized not in _ALLOWED_EDGE_TYPES:
        raise ValueError(f"edge_type 必须是: {', '.join(_ALLOWED_EDGE_TYPES)}")
    return normalized


def normalize_role_type(role_type: Any) -> str:
    """规范化角色类型"""
    if not isinstance(role_type, str):
        raise ValueError(f"role_type 必须是字符串: {', '.join(_ALLOWED_ROLE_TYPES)}")
    normalized = role_type.lower()
    if normalized not in _ALLOWED_ROLE_TYPES:
        raise ValueError(f"role_type 必须是: {', '.join(_ALLOWED_ROLE_TYPES)}")
    return normalized


def normalize_graph_status(status: Any) -> str:
    """规范化图状态"""
    if not isinstance(status, str):
        raise ValueError(f"status 必须是字符串: {', '.join(_ALLOWED_GRAPH_STATUSES)}")
    normalized = status.lower()
    if normalized not in _ALLOWED_GRAPH_STATUSES:
        raise ValueError(f"status 必须是: {', '.join(_ALLOWED_GRAPH_STATUSES)}")
    return normalized


# ========================
# Graph Schemas
# ========================


class CreateGraphRequest(BaseModel):
    """创建执行拓扑图请求"""
    name: str = Field(..., min_length=1, description="图名称")
    description: str = Field(default="", description="图描述")


class UpdateGraphRequest(BaseModel):
    """更新执行拓扑图请求"""
    name: Optional[str] = Field(None, min_length=1, description="图名称")
    description: Optional[str] = Field(None, description="图描述")
    status: Optional[str] = Field(None, description="图状态: draft|active|running|succeeded|failed|suspended")
    layout_json: Optional[Dict[str, Any]] = Field(None, description="画布布局JSON（缩放、平移等）")
    meta_json: Optional[Dict[str, Any]] = Field(None, description="元数据JSON")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None:
            return normalize_graph_status(v)
        return v


# ========================
# Container Schemas
# ========================


class CreateContainerRequest(BaseModel):
    """创建容器请求"""
    container_key: str = Field(..., min_length=1, description="容器唯一标识（图内唯一）")
    label: str = Field(..., min_length=1, description="容器显示标签")
    role_type: str = Field(..., description="角色类型: human|agent|system")
    config_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="配置JSON")
    order_index: int = Field(default=0, description="排序索引")

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v):
        return normalize_role_type(v)


class UpdateContainerRequest(BaseModel):
    """更新容器请求（支持部分字段）"""
    label: Optional[str] = Field(None, min_length=1, description="容器显示标签")
    role_type: Optional[str] = Field(None, description="角色类型: human|agent|system")
    config_json: Optional[Dict[str, Any]] = Field(None, description="配置JSON")
    order_index: Optional[int] = Field(None, description="排序索引")

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v):
        if v is not None:
            return normalize_role_type(v)
        return v


# ========================
# Subgraph Schemas
# ========================


class CreateSubgraphRequest(BaseModel):
    """创建子图请求"""
    container_id: str = Field(..., min_length=1, description="所属容器ID")
    subgraph_key: str = Field(..., min_length=1, description="子图唯一标识（图内唯一）")
    label: str = Field(..., min_length=1, description="子图显示标签")
    task_description: str = Field(..., min_length=1, description="任务描述（注入 start 节点上下文）")
    order_index: int = Field(default=0, description="排序索引")
    config_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="配置JSON")


class UpdateSubgraphRequest(BaseModel):
    """更新子图请求（支持部分字段）"""
    label: Optional[str] = Field(None, min_length=1, description="子图显示标签")
    task_description: Optional[str] = Field(None, min_length=1, description="任务描述")
    order_index: Optional[int] = Field(None, description="排序索引")
    config_json: Optional[Dict[str, Any]] = Field(None, description="配置JSON")


# ========================
# Node Schemas
# ========================


class CreateNodeRequest(BaseModel):
    """创建节点请求"""
    container_id: Optional[str] = Field(default=None, description="所属容器ID（可选）")
    subgraph_id: Optional[str] = Field(default=None, description="所属子图ID（可选）")
    node_key: str = Field(..., min_length=1, description="节点唯一标识（图内唯一）")
    label: str = Field(..., min_length=1, description="节点显示标签")
    node_type: str = Field(..., description="节点类型: start|node|decision|handoff|end|llm|invoke")
    role_type: str = Field(..., description="角色类型: human|agent|system")
    config_json: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="配置JSON"
    )
    input_schema_json: Optional[List[str]] = Field(
        default_factory=list, description="输入模式JSON"
    )
    output_schema_json: Optional[List[str]] = Field(
        default_factory=list, description="输出模式JSON"
    )
    order_index: int = Field(default=0, description="排序索引")

    @field_validator("node_type")
    @classmethod
    def validate_node_type(cls, v):
        return normalize_node_type(v)

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v):
        return normalize_role_type(v)


class UpdateNodeRequest(BaseModel):
    """更新节点请求（支持部分字段）"""
    container_id: Optional[str] = Field(None, description="所属容器ID（可选）")
    subgraph_id: Optional[str] = Field(None, description="所属子图ID（可选）")
    label: Optional[str] = Field(None, min_length=1, description="节点显示标签")
    node_type: Optional[str] = Field(None, description="节点类型: start|node|decision|handoff|end|llm|invoke")
    role_type: Optional[str] = Field(None, description="角色类型: human|agent|system")
    config_json: Optional[Dict[str, Any]] = Field(None, description="配置JSON")
    stage_prompt: Optional[str] = Field(None, description="阶段提示词（将自动合并至 config_json.stage_prompt）")
    input_schema_json: Optional[List[str]] = Field(None, description="输入节点 ID 列表（节点内容 Tab 中选择的输入节点）")
    output_schema_json: Optional[List[str]] = Field(None, description="输出模式JSON")
    order_index: Optional[int] = Field(None, description="排序索引")

    @field_validator("node_type")
    @classmethod
    def validate_node_type(cls, v):
        if v is not None:
            return normalize_node_type(v)
        return v

    @field_validator("role_type")
    @classmethod
    def validate_role_type(cls, v):
        if v is not None:
            return normalize_role_type(v)
        return v


# ========================
# Edge Schemas
# ========================


class CreateEdgeRequest(BaseModel):
    """创建边请求"""
    source_node_id: str = Field(..., description="源节点ID")
    target_node_id: str = Field(..., description="目标节点ID")
    edge_type: str = Field(..., description="边类型: call|return|retry")
    label: Optional[str] = Field(None, description="边显示标签")
    condition_expr: Optional[str] = Field(None, description="条件表达式")
    config_json: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="配置JSON"
    )
    order_index: int = Field(default=0, description="排序索引")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v):
        return normalize_edge_type(v)


class UpdateEdgeRequest(BaseModel):
    """更新边请求（支持部分字段）"""
    label: Optional[str] = Field(None, description="边显示标签")
    edge_type: Optional[str] = Field(None, description="边类型: call|return|retry")
    condition_expr: Optional[str] = Field(None, description="条件表达式")
    config_json: Optional[Dict[str, Any]] = Field(None, description="配置JSON")
    order_index: Optional[int] = Field(None, description="排序索引")

    @field_validator("edge_type")
    @classmethod
    def validate_edge_type(cls, v):
        if v is not None:
            return normalize_edge_type(v)
        return v


# ========================
# Execution Runtime Schema
# ========================


class ExecuteTopologyRequest(BaseModel):
    """Execute a topology template into a runtime graph."""
    input_payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="输入 payload")
    max_steps: int = Field(default=100, ge=1, le=1000, description="最大执行步数")
    runtime_graph_name: Optional[str] = Field(None, min_length=1, description="运行时图名称")
    runtime_graph_description: Optional[str] = Field(None, description="运行时图描述")
