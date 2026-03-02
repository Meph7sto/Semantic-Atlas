"""Topology structure engine package.

This package provides runtime structure building for execution topologies without
actual LLM execution. It creates AgentContainer instances and processes
edge relationships to build a structure that can be understood and
taken over by intelligent agents.
"""

from .agent_container import AgentContainer, ContainerNode, NodeType, RoleType
from .edge_processor import CrossContainerEdge, EdgeType, EdgeProcessor
from .condition_evaluator import ConditionEvaluator, ParsedCondition
from .graph_structure_builder import GraphStructureBuilder, TopologyStructure
from .structure_validator import StructureValidator, ValidationResult
from .structure_serializer import (
    SerializedTopology,
    TopologyStructureSerializer,
)

__all__ = [
    "AgentContainer",
    "ContainerNode",
    "NodeType",
    "RoleType",
    "CrossContainerEdge",
    "EdgeType",
    "EdgeProcessor",
    "ConditionEvaluator",
    "ParsedCondition",
    "GraphStructureBuilder",
    "TopologyStructure",
    "StructureValidator",
    "ValidationResult",
    "TopologyStructureSerializer",
    "SerializedTopology",
]
