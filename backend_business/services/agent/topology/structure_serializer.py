"""TopologyStructureSerializer - Serializes topology structure for agents.

This class serializes the compiled topology structure into a
standard JSON format that can be understood and taken over
by intelligent agents.

Note: This is for manual modeling and structure building only.
No actual execution or evaluation is performed.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .graph_structure_builder import TopologyStructure


@dataclass
class SerializedTopology:
    """Serialized topology structure for agent consumption.

    This class contains the topology structure serialized
    in a standard JSON format that can be understood
    by intelligent agents.

    Attributes:
        version: Serialization format version
        topology: The TopologyStructure data
        metadata: Additional metadata about the serialization
    """

    version: str = "1.0"
    topology: TopologyStructure = None
    metadata: Dict[str, Any] = None

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string representation
        """
        data = {
            "version": self.version,
            "topology": self.topology.to_dict() if self.topology else None,
            "metadata": self.metadata or {},
        }
        return json.dumps(data, ensure_ascii=False, indent=indent)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "topology": self.topology.to_dict() if self.topology else None,
            "metadata": self.metadata or {},
        }


class TopologyStructureSerializer:
    """Serializes topology structure for agent consumption.

    This class provides serialization of the compiled topology
    structure into a standard format.

    Note: No actual execution or evaluation is performed.
    Only serialization.
    """

    def serialize(
        self,
        structure: TopologyStructure,
        include_metadata: bool = True,
    ) -> SerializedTopology:
        """Serialize topology structure.

        Args:
            structure: The TopologyStructure to serialize
            include_metadata: Whether to include metadata

        Returns:
            SerializedTopology object
        """
        # Build metadata
        metadata = None
        if include_metadata:
            node_type_counts: Dict[str, int] = {}
            for container in structure.containers:
                for node in container.nodes:
                    node_type = node.node_type.value
                    node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1

            metadata = {
                "container_count": len(structure.containers),
                "edge_count": len(structure.edges),
                "start_count": len(structure.start_containers),
                "end_count": len(structure.end_containers),
                "node_types": node_type_counts,
                "edge_types": {
                    e.edge_type.value: sum(
                        1 for x in structure.edges
                        if x.edge_type == e.edge_type
                    )
                    for e in structure.edges
                },
            }

        return SerializedTopology(
            topology=structure,
            metadata=metadata,
        )

    def export_for_agent(self, structure: TopologyStructure) -> Dict[str, Any]:
        """Export topology in agent-consumable format.

        This method creates a simplified representation optimized
        for agent understanding and execution.

        Args:
            structure: The TopologyStructure to export

        Returns:
            Dictionary in agent-consumable format

        The exported format includes:
        - High-level topology description
        - Container definitions with input/output schemas
        - Edge definitions with data flow mappings
        - Execution hints for agents
        """
        return {
            "description": f"Execution topology: {structure.graph_name}",
            "version": "1.0",
            "structure": {
                "containers": [
                    {
                        "id": c.container_id,
                        "key": c.container_key,
                        "label": c.label,
                        "role": c.role_type.value,
                        "node_count": len(c.nodes),
                        "nodes": [
                            {
                                "id": n.node_id,
                                "key": n.node_key,
                                "label": n.label,
                                "type": n.node_type.value,
                                "role": n.role_type.value,
                            }
                            for n in c.nodes
                        ],
                        "input_schema": c.input_schema,
                        "output_schema": c.output_schema,
                    }
                    for c in structure.containers
                ],
                "edges": [
                    {
                        "id": e.edge_id,
                        "source": e.source_container_id,
                        "target": e.target_container_id,
                        "type": e.edge_type.value,
                        "condition": e.condition_expr,
                        "data_flow": {
                            "call": e.param_mapping if e.edge_type.value == "call" else None,
                            "return": e.result_mapping if e.edge_type.value == "return" else None,
                            "retry": e.retry_config if e.edge_type.value == "retry" else None,
                        },
                    }
                    for e in structure.edges
                ],
                "start_points": [c.container_id for c in structure.start_containers],
                "end_points": [c.container_id for c in structure.end_containers],
            },
            "execution_hints": {
                "max_depth": self._calculate_max_depth(structure),
                "parallel_branches": self._count_parallel_branches(structure),
                "critical_path": self._find_critical_path(structure),
            },
        }

    def _calculate_max_depth(self, structure: TopologyStructure) -> int:
        """Calculate maximum depth of the topology."""
        # Build adjacency map
        adj = {
            c.container_id: [
                e.target_container_id
                for e in structure.edges
                if e.source_container_id == c.container_id
            ]
            for c in structure.containers
        }

        # DFS to find max depth
        def dfs(container_id: str, depth: int = 0) -> int:
            max_depth = depth
            if container_id in adj:
                for next_id in adj[container_id]:
                    max_depth = max(max_depth, dfs(next_id, depth + 1))
            return max_depth

        max_depth = 0
        for start in structure.start_containers:
            max_depth = max(max_depth, dfs(start.container_id))

        return max_depth

    def _count_parallel_branches(self, structure: TopologyStructure) -> int:
        """Count parallel branches in the topology."""
        branch_count = 0

        # Count nodes with multiple outgoing edges
        for container in structure.containers:
            outgoing = [
                edge
                for edge in structure.edges
                if edge.source_container_id == container.container_id
            ]
            if len(outgoing) > 1:
                branch_count += 1

        return branch_count

    def _find_critical_path(self, structure: TopologyStructure) -> List[str]:
        """Find the longest path from start to end."""
        # Simplified critical path analysis
        if not structure.start_containers or not structure.end_containers:
            return []

        # Build adjacency map
        adj = {
            c.container_id: [
                e.target_container_id
                for e in structure.edges
                if e.source_container_id == c.container_id
            ]
            for c in structure.containers
        }

        # Find longest path from any start to any end
        longest_path = []

        def dfs_longest(
            current_id: str, visited: set, path: List[str] = []
        ) -> List[str]:
            path.append(current_id)
            visited.add(current_id)

            # Check if we reached an end node
            if current_id in [c.container_id for c in structure.end_containers]:
                return path.copy()

            # Explore neighbors
            neighbors = adj.get(current_id, [])
            for neighbor_id in neighbors:
                if neighbor_id not in visited:
                    result = dfs_longest(neighbor_id, visited.copy(), path.copy())
                    if len(result) > len(longest_path):
                        longest_path.clear()
                        longest_path.extend(result)

        for start in structure.start_containers:
            dfs_longest(start.container_id, set())

        return longest_path
