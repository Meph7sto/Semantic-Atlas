"""StructureValidator - Validates topology structure integrity.

This class validates the integrity and correctness of a topology
structure without actual execution.

Note: This is for manual modeling and structure building only.
No actual graph traversal or execution is performed.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Set

from .graph_structure_builder import TopologyStructure

from .edge_processor import EdgeType, EdgeProcessor
from .condition_evaluator import ConditionEvaluator


@dataclass
class ValidationResult:
    """Validation result for a topology structure.

    Attributes:
        is_valid: Whether the structure is valid
        errors: List of validation errors
        warnings: List of validation warnings
    """

    is_valid: bool
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class StructureValidator:
    """Validates topology structure integrity.

    This class provides comprehensive validation of topology
    structures including node connectivity, edge validity,
    condition syntax, and cycle detection.

    Note: No actual graph traversal or execution is performed.
    Only validation.
    """

    def __init__(self):
        """Initialize the structure validator."""
        self.edge_processor = EdgeProcessor()
        self.condition_evaluator = ConditionEvaluator()

    def validate(self, structure: TopologyStructure) -> ValidationResult:
        """Perform comprehensive validation of topology structure.

        Args:
            structure: The TopologyStructure to validate

        Returns:
            ValidationResult with validation status
        """
        errors = []
        warnings = []

        # Validate nodes
        errors.extend(self._validate_nodes(structure))

        # Validate edges
        errors.extend(self._validate_edges(structure))

        # Validate connectivity
        errors.extend(self._validate_connectivity(structure))

        # Validate condition expressions
        errors.extend(self._validate_conditions(structure))

        # Detect cycles
        warnings.extend(self._detect_cycles(structure))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_nodes(self, structure: TopologyStructure) -> List[str]:
        """Validate container and node definitions."""
        errors = []

        # Check for duplicate container keys
        container_keys = [c.container_key for c in structure.containers]
        seen_keys: Set[str] = set()
        for key in container_keys:
            if key in seen_keys:
                errors.append(f"Duplicate container key: {key}")
            seen_keys.add(key)

        # Validate each container and contained nodes
        _VALID_TOPOLOGY_NODE_TYPES = {"llm", "invoke", "handoff"}
        for container in structure.containers:
            if container.role_type.value not in {"human", "agent", "system"}:
                errors.append(
                    f"Invalid role_type '{container.role_type}' in container '{container.container_key}'"
                )
            for node in container.nodes:
                if node.node_type.value not in _VALID_TOPOLOGY_NODE_TYPES:
                    errors.append(
                        f"Invalid topology node type '{node.node_type.value}' in node '{node.node_key}'. "
                        f"Allowed: {', '.join(sorted(_VALID_TOPOLOGY_NODE_TYPES))}"
                    )

        return errors

    def _validate_edges(self, structure: TopologyStructure) -> List[str]:
        """Validate edge definitions."""
        errors = []

        # Validate each edge structure
        for edge in structure.edges:
            edge_errors = self.edge_processor.validate_edge_structure(
                edge, structure.containers
            )
            errors.extend(edge_errors)

        # Check for duplicate edges
        edge_key = lambda e: (
            e.source_container_id,
            e.target_container_id,
            e.edge_type,
        )
        seen_edge_keys: Set[Any] = set()

        for edge in structure.edges:
            key = edge_key(edge)
            if key in seen_edge_keys:
                errors.append(
                    f"Duplicate edge: {edge.source_container_id} -> {edge.target_container_id} ({edge.edge_type.value})"
                )
            seen_edge_keys.add(key)

        return errors

    def _validate_connectivity(
        self, structure: TopologyStructure
    ) -> List[str]:
        """Validate graph connectivity."""
        errors = []

        # Check for isolated nodes (not connected to any edge)
        connected_ids = set()
        for edge in structure.edges:
            connected_ids.add(edge.source_container_id)
            connected_ids.add(edge.target_container_id)

        if structure.edges and len(structure.containers) > 1:
            for container in structure.containers:
                if container.container_id not in connected_ids:
                    errors.append(
                        f"Isolated container: '{container.node_key}' is not connected to any cross-container edge"
                    )

        return errors

    def _find_reachable(
        self, start_id: str, edges: List[Any], visited: Set[str] = None
    ) -> Set[str]:
        """Find all containers reachable from start_id using BFS."""
        if visited is None:
            visited = set()

        reachable = set()
        queue = deque([start_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue

            visited.add(current)
            reachable.add(current)

            # Find outgoing edges from current
            for edge in edges:
                if edge.source_container_id == current:
                    queue.append(edge.target_container_id)

        return reachable

    def _validate_conditions(
        self, structure: TopologyStructure
    ) -> List[str]:
        """Validate condition expressions in edges."""
        errors = []

        # Collect available variables from container schemas
        available_vars = set()
        for container in structure.containers:
            for field in container.input_schema:
                available_vars.add(field.get("name", ""))
            for field in container.output_schema:
                available_vars.add(field.get("name", ""))

        # Validate each condition expression
        for edge in structure.edges:
            if edge.condition_expr:
                condition_errors = self.condition_evaluator.validate(
                    edge.condition_expr, available_vars
                )
                errors.extend(
                    [f"Edge '{edge.edge_id}': {e}" for e in condition_errors]
                )

        return errors

    def _detect_cycles(self, structure: TopologyStructure) -> List[str]:
        """Detect cycles in the graph using DFS."""
        warnings = []

        # Build adjacency map
        adj = {
            c.container_id: [
                e.target_container_id
                for e in structure.edges
                if e.source_container_id == c.container_id
            ]
            for c in structure.containers
        }

        # Detect cycles for each node
        def dfs(
            current_id: str,
            visited: Set[str],
            rec_stack: Set[str],
        ) -> bool:
            visited.add(current_id)
            rec_stack.add(current_id)

            for neighbor_id in adj.get(current_id, []):
                if neighbor_id not in visited:
                    if dfs(neighbor_id, visited, rec_stack):
                        return True
                elif neighbor_id in rec_stack:
                    return True

            rec_stack.remove(current_id)
            return False

        has_cycle = False
        visited = set()
        for container in structure.containers:
            if container.container_id not in visited:
                rec_stack = set()
                if dfs(container.container_id, visited, rec_stack):
                    has_cycle = True
                    warnings.append(
                        f"Cycle detected involving container: '{container.node_key}'"
                    )
                    break

        return warnings
