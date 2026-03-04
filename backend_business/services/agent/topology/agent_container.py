"""AgentContainer model for runtime topology structure."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeType(str, Enum):
    """Node type definitions."""
    START = "start"
    NODE = "node"
    DECISION = "decision"
    HANDOFF = "handoff"
    END = "end"


class RoleType(str, Enum):
    """Role type definitions."""
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass
class ContainerNode:
    """A topology node contained by an AgentContainer."""

    node_id: str
    node_key: str
    label: str
    node_type: NodeType
    role_type: RoleType
    config: Dict[str, Any] = field(default_factory=dict)
    input_schema: List[Dict[str, Any]] = field(default_factory=list)
    output_schema: List[Dict[str, Any]] = field(default_factory=list)
    order_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_key": self.node_key,
            "label": self.label,
            "node_type": self.node_type.value,
            "role_type": self.role_type.value,
            "config": self.config,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "order_index": self.order_index,
        }

    @classmethod
    def from_db_node(cls, node_db: Dict[str, Any]) -> "ContainerNode":
        return cls(
            node_id=node_db.get("node_id", ""),
            node_key=node_db.get("node_key", ""),
            label=node_db.get("label", ""),
            node_type=NodeType(node_db.get("node_type", "node")),
            role_type=RoleType(node_db.get("role_type", "system")),
            config=node_db.get("config_json", {}) or {},
            input_schema=node_db.get("input_schema_json", []) or [],
            output_schema=node_db.get("output_schema_json", []) or [],
            order_index=node_db.get("order_index", 0) or 0,
        )


@dataclass
class AgentContainer:
    """Runtime container which owns one or more topology nodes."""

    container_id: str
    container_key: str
    label: str
    role_type: RoleType
    agent_id: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    order_index: int = 0
    nodes: List[ContainerNode] = field(default_factory=list)

    # Runtime state (for future execution)
    execution_count: int = 0
    last_executed_at: Optional[datetime] = None
    accumulated_inputs: Dict[str, Any] = field(default_factory=dict)
    accumulated_outputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        node_types = sorted({n.node_type.value for n in self.nodes})
        start_node_ids = [n.node_id for n in self.nodes if n.node_type == NodeType.START]
        end_node_ids = [n.node_id for n in self.nodes if n.node_type == NodeType.END]
        return {
            "container_id": self.container_id,
            "container_key": self.container_key,
            "label": self.label,
            "node_count": len(self.nodes),
            "node_types": node_types,
            "start_node_ids": start_node_ids,
            "end_node_ids": end_node_ids,
            "role_type": self.role_type.value,
            "agent_id": self.agent_id,
            "config": self.config,
            "order_index": self.order_index,
            "nodes": [n.to_dict() for n in self.nodes],
            "execution_count": self.execution_count,
            "accumulated_inputs": self.accumulated_inputs,
            "accumulated_outputs": self.accumulated_outputs,
        }

    @property
    def node_key(self) -> str:
        # Backward compatible alias used in validators/serializers.
        return self.container_key

    @property
    def input_schema(self) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for node in self.nodes:
            merged.extend(node.input_schema)
        return merged

    @property
    def output_schema(self) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for node in self.nodes:
            merged.extend(node.output_schema)
        return merged

    def add_node(self, node: ContainerNode) -> None:
        self.nodes.append(node)

    @classmethod
    def from_db_container(cls, container_db: Dict[str, Any]) -> "AgentContainer":
        """Create AgentContainer from database container record."""
        config = container_db.get("config_json", {}) or {}
        return cls(
            container_id=container_db.get("container_id", ""),
            container_key=container_db.get("container_key", ""),
            label=container_db.get("label", ""),
            role_type=RoleType(container_db.get("role_type", "system")),
            agent_id=config.get("agent_id"),
            config=config,
            order_index=container_db.get("order_index", 0) or 0,
        )

    @classmethod
    def from_db_node(cls, node_db: Dict[str, Any]) -> "AgentContainer":
        """Backward-compatible builder for legacy callers."""
        node = ContainerNode.from_db_node(node_db)
        container = cls(
            container_id=f"legacy-container::{node.node_id}",
            container_key=f"legacy_{node.node_key}",
            label=node.label,
            role_type=node.role_type,
            agent_id=node.config.get("agent_id"),
            config={"auto_generated": True, "reason": "legacy_from_db_node"},
            order_index=node.order_index,
        )
        container.add_node(node)
        return container
