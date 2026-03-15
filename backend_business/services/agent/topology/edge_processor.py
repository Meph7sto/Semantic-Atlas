"""EdgeProcessor - Handles cross-container edge relationships.

This class processes edge definitions from the database and creates
runtime CrossContainerEdge objects that define the data flow and
relationship between containers.

Note: This is for manual modeling and structure building only.
No actual data transfer or evaluation is performed at this stage.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .agent_container import AgentContainer


class EdgeType(str, Enum):
    """Edge type definitions."""
    CALL = "call"
    RETURN = "return"
    RETRY = "retry"


@dataclass
class CrossContainerEdge:
    """Runtime edge connecting two containers.

    This edge defines the relationship and data flow between
    source and target containers without actual execution.

    Attributes:
        edge_id: Unique identifier for this edge
        source_container_id: Source container ID
        target_container_id: Target container ID
        edge_type: Type of edge (call/return/retry)
        label: Display label for the edge
        condition_expr: Conditional expression for routing (structure only, not evaluated)
        config: Edge configuration dictionary
        param_mapping: Parameter mapping from source output to target input (for call edges)
        result_mapping: Result mapping from target output to source input (for return edges)
        retry_config: Retry configuration (for retry edges)
    """

    edge_id: str
    source_container_id: str
    target_container_id: str
    edge_type: EdgeType
    label: Optional[str] = None
    condition_expr: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)

    # Data flow mappings (structure definitions, not actual transfer)
    param_mapping: Dict[str, str] = field(default_factory=dict)
    result_mapping: Dict[str, str] = field(default_factory=dict)
    retry_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert edge to dictionary for serialization."""
        return {
            "edge_id": self.edge_id,
            "source_container_id": self.source_container_id,
            "target_container_id": self.target_container_id,
            "edge_type": self.edge_type.value,
            "label": self.label,
            "condition_expr": self.condition_expr,
            "config": self.config,
            "param_mapping": self.param_mapping,
            "result_mapping": self.result_mapping,
            "retry_config": self.retry_config,
        }

    @classmethod
    def from_db_edge(cls, edge_db: Dict[str, Any]) -> "CrossContainerEdge":
        """Create CrossContainerEdge from database edge record."""
        config = edge_db.get("config_json", {})

        # Extract mappings from config
        param_mapping = config.get("param_mapping", {})
        result_mapping = config.get("result_mapping", {})
        retry_config = {
            "max_retries": config.get("max_retries", 3),
            "retry_on_errors": config.get("retry_on_errors", []),
            "retry_delay_ms": config.get("retry_delay_ms", 1000),
        }

        return cls(
            edge_id=edge_db.get("edge_id", ""),
            source_container_id=edge_db.get("source_node_id", ""),
            target_container_id=edge_db.get("target_node_id", ""),
            edge_type=EdgeType(edge_db.get("edge_type", "call")),
            label=edge_db.get("label"),
            condition_expr=edge_db.get("condition_expr"),
            config=config,
            param_mapping=param_mapping,
            result_mapping=result_mapping,
            retry_config=retry_config,
        )


class EdgeProcessor:
    """Processes edge relationships between containers.

    This processor builds runtime edges from database records and
    provides utilities for managing edge relationships.

    Note: No actual data transfer or evaluation is performed.
    Only structure building and validation.
    """

    def build_edges(
        self,
        containers: List[AgentContainer],
        db_edges: List[Dict[str, Any]],
    ) -> List[CrossContainerEdge]:
        """Build cross-container edges from database edges.

        Args:
            containers: List of AgentContainer objects
            db_edges: List of database edge records

        Returns:
            List of CrossContainerEdge objects
        """
        # Map node IDs to container IDs
        container_id_map: Dict[str, str] = {}
        for container in containers:
            for node in container.nodes:
                container_id_map[node.node_id] = container.container_id

        edges = []
        for edge_db in db_edges:
            # Remap node IDs to container IDs
            edge_db_copy = edge_db.copy()
            source_node_id = edge_db.get("source_node_id", "")
            target_node_id = edge_db.get("target_node_id", "")

            source_container_id = container_id_map.get(source_node_id)
            target_container_id = container_id_map.get(target_node_id)
            if not source_container_id or not target_container_id:
                continue

            # Internal node edges stay inside container; only keep cross-container edges here.
            if source_container_id == target_container_id:
                continue

            edge_db_copy["source_node_id"] = source_container_id
            edge_db_copy["target_node_id"] = target_container_id

            edge = CrossContainerEdge.from_db_edge(edge_db_copy)
            edges.append(edge)

        return edges

    def get_outgoing_edges(
        self,
        container_id: str,
        edges: List[CrossContainerEdge],
    ) -> List[CrossContainerEdge]:
        """Get all outgoing edges from a container.

        Args:
            container_id: Container ID to find outgoing edges from
            edges: List of all edges

        Returns:
            List of edges where source_container_id == container_id
        """
        return [e for e in edges if e.source_container_id == container_id]

    def get_incoming_edges(
        self,
        container_id: str,
        edges: List[CrossContainerEdge],
    ) -> List[CrossContainerEdge]:
        """Get all incoming edges to a container.

        Args:
            container_id: Container ID to find incoming edges to
            edges: List of all edges

        Returns:
            List of edges where target_container_id == container_id
        """
        return [e for e in edges if e.target_container_id == container_id]

    def get_edges_by_type(
        self,
        edge_type: EdgeType,
        edges: List[CrossContainerEdge],
    ) -> List[CrossContainerEdge]:
        """Get all edges of a specific type.

        Args:
            edge_type: Edge type to filter by
            edges: List of all edges

        Returns:
            List of edges matching the specified type
        """
        return [e for e in edges if e.edge_type == edge_type]

    def validate_edge_structure(
        self,
        edge: CrossContainerEdge,
        containers: List[AgentContainer],
    ) -> List[str]:
        """Validate edge structure.

        Args:
            edge: Edge to validate
            containers: List of all containers for reference

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check source container exists
        source_exists = any(c.container_id == edge.source_container_id for c in containers)
        if not source_exists:
            errors.append(
                f"Source container '{edge.source_container_id}' does not exist"
            )

        # Check target container exists
        target_exists = any(c.container_id == edge.target_container_id for c in containers)
        if not target_exists:
            errors.append(
                f"Target container '{edge.target_container_id}' does not exist"
            )

        # Validate edge type-specific requirements
        if edge.edge_type == EdgeType.CALL:
            # Call edges should have param mapping
            if not edge.param_mapping:
                errors.append("Call edge should define param_mapping")

        elif edge.edge_type == EdgeType.RETURN:
            # Return edges should have result mapping
            if not edge.result_mapping:
                errors.append("Return edge should define result_mapping")

        elif edge.edge_type == EdgeType.RETRY:
            # Retry edges should have retry config
            if not edge.retry_config:
                errors.append("Retry edge should define retry_config")

        return errors
