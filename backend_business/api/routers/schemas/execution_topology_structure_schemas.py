"""Request/Response schemas for topology structure API.

This module defines Pydantic models for API requests and responses
for topology structure operations.

Note: This is for manual modeling and structure building only.
No actual execution or evaluation is performed at this stage.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Request Schemas


class ValidateTopologyRequest(BaseModel):
    """Request to validate a topology structure."""

    dry_run: bool = Field(
        default=False,
        description="Whether to perform a dry run validation without caching",
    )


# Response Schemas


class AgentContainerSchema(BaseModel):
    """Agent container schema."""

    class ContainerNodeSchema(BaseModel):
        node_id: str
        node_key: str
        label: str
        node_type: str
        role_type: str
        phase_label: Optional[str] = None
        task_prompt: Optional[str] = None
        conditional_edges: List[Dict[str, Any]] = Field(default_factory=list)
        config: Dict[str, Any] = Field(default_factory=dict)
        input_schema: List[Dict[str, Any]] = Field(default_factory=list)
        output_schema: List[Dict[str, Any]] = Field(default_factory=list)
        order_index: int = 0

    container_id: str
    container_key: str
    label: str
    node_count: int
    node_types: List[str] = Field(default_factory=list)
    entry_node_ids: List[str] = Field(default_factory=list)
    exit_node_ids: List[str] = Field(default_factory=list)
    role_type: str
    agent_id: Optional[str]
    config: Dict[str, Any]
    order_index: int = 0
    nodes: List[ContainerNodeSchema] = Field(default_factory=list)
    execution_count: int = 0
    accumulated_inputs: Dict[str, Any] = Field(default_factory=dict)
    accumulated_outputs: Dict[str, Any] = Field(default_factory=dict)


class CrossContainerEdgeSchema(BaseModel):
    """Cross-container edge schema."""

    edge_id: str
    source_container_id: str
    target_container_id: str
    edge_type: str
    label: Optional[str]
    condition_expr: Optional[str]
    config: Dict[str, Any] = Field(default_factory=dict)
    param_mapping: Dict[str, str] = Field(default_factory=dict)
    result_mapping: Dict[str, str] = Field(default_factory=dict)
    retry_config: Dict[str, Any] = Field(default_factory=dict)


class TopologyStructureSchema(BaseModel):
    """Topology structure schema."""

    graph_id: str
    graph_name: str
    containers: List[AgentContainerSchema]
    edges: List[CrossContainerEdgeSchema]
    start_containers: List[str]
    end_containers: List[str]
    validation_status: str
    validation_errors: List[str] = Field(default_factory=list)


class SerializedTopologySchema(BaseModel):
    """Serialized topology schema for agent consumption."""

    version: str
    topology: Optional[TopologyStructureSchema]
    metadata: Optional[Dict[str, Any]]


class ValidationResultSchema(BaseModel):
    """Validation result schema."""

    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ExportedTopologySchema(BaseModel):
    """Exported topology schema for agent consumption."""

    description: str
    version: str
    structure: Dict[str, Any]
    execution_hints: Dict[str, Any]


# API Response Schemas


class GetTopologyStructureResponse(BaseModel):
    """Response for getting topology structure."""

    success: bool
    structure: Optional[TopologyStructureSchema]
    error: Optional[str] = None


class ValidateTopologyResponse(BaseModel):
    """Response for validating topology structure."""

    success: bool
    result: Optional[ValidationResultSchema]
    error: Optional[str] = None


class GetContainersResponse(BaseModel):
    """Response for getting containers."""

    success: bool
    containers: List[AgentContainerSchema] = Field(default_factory=list)
    error: Optional[str] = None


class GetEdgesResponse(BaseModel):
    """Response for getting edges."""

    success: bool
    edges: List[CrossContainerEdgeSchema] = Field(default_factory=list)
    error: Optional[str] = None


class ExportTopologyResponse(BaseModel):
    """Response for exporting topology."""

    success: bool
    exported: Optional[ExportedTopologySchema]
    error: Optional[str] = None
