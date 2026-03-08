# 追溯结果模型 (nodes/links/relations 结构) 占位符
# 此文件用于定义需求追溯图谱（节点、链接、关系）的数据结构
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TraceNode(BaseModel):
    id: str
    name: str
    text: str
    level: int = Field(..., description="建议范围：战略/业务目标 5-4，功能/特性 3-2，用户故事/任务 2-1")
    type: Literal["high_level", "low_level"] = "high_level"


class TraceLink(BaseModel):
    source: str
    target: str
    type: str = Field(..., description="关系类型，如 implementation/support/dependency/decomposition/general/unknown")
    label: str = Field(..., description="关系中文标签，如 实现关系/支持关系/依赖关系/分解关系/追溯关系")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class TraceNetwork(BaseModel):
    nodes: List[TraceNode] = Field(default_factory=list)
    links: List[TraceLink] = Field(default_factory=list)


class TraceRelationRequest(BaseModel):
    high_level_requirement: str = Field(..., min_length=1)
    low_level_requirement: str = Field(..., min_length=1)
    max_new_tokens: int = Field(default=800, ge=1, le=4096)


class TraceRelationResponse(BaseModel):
    high_level_requirement: str
    low_level_requirement: str
    has_relation: bool
    relation_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    summary: str
    analysis_details: str
    keywords: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    trace_network: TraceNetwork
    raw_response: Optional[str] = Field(default=None, description="模型原始输出，便于调试")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="模型返回但未建模的额外字段")


class BatchTraceRelationRequest(BaseModel):
    high_level_requirements: List[str] = Field(..., min_length=1)
    low_level_requirements: List[str] = Field(..., min_length=1)
    max_new_tokens: int = Field(default=1200, ge=1, le=8192)


class BatchRelationRecord(BaseModel):
    high_level_index: int
    low_level_index: int
    high_level_requirement: str
    low_level_requirement: str
    has_relation: bool
    relation_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    analysis_details: str = ""
    summary: str = ""
    keywords: List[str] = Field(default_factory=list)


class BatchStatistics(BaseModel):
    total_combinations: int = 0
    relations_found: int = 0
    relation_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class BatchTraceRelationResponse(BaseModel):
    summary: str
    statistics: BatchStatistics
    high_level_requirements: List[str] = Field(default_factory=list, description="原始输入的顶层需求列表")
    low_level_requirements: List[str] = Field(default_factory=list, description="原始输入的底层需求列表")
    relations: List[BatchRelationRecord] = Field(default_factory=list)
    trace_network: TraceNetwork
    relation_types_count: Optional[Dict[str, int]] = Field(default=None, description="关系类型统计")
    raw_response: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

# 追溯结果模型 (nodes/links/relations 结构) 占位符
# 此文件用于定义需求追溯图谱（节点、链接、关系）的数据结构
