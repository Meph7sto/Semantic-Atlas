"""GraphStructureBuilder - Builds runtime topology structure.

This class loads topology definitions from the database and builds
runtime AgentContainer and CrossContainerEdge objects without actual
execution.

Note: This is for manual modeling and structure building only.
No actual graph traversal or execution is performed at this stage.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .agent_container import AgentContainer, ContainerNode, NodeType, RoleType
from .edge_processor import CrossContainerEdge, EdgeType, EdgeProcessor


@dataclass
class TopologyStructure:
    """Runtime structure for an execution topology.

    This dataclass contains the complete compiled structure
    of a topology graph that can be understood and
    taken over by intelligent agents.

    Attributes:
        graph_id: Original graph ID from database
        graph_name: Display name of the graph
        containers: List of AgentContainer objects
        edges: List of CrossContainerEdge objects
        start_containers: List of start node containers
        end_containers: List of end node containers
        validation_status: Validation status of the structure
        validation_errors: List of validation errors
    """

    graph_id: str
    graph_name: str
    containers: List[AgentContainer]
    edges: List[CrossContainerEdge]
    start_containers: List[AgentContainer]
    end_containers: List[AgentContainer]
    validation_status: str = "pending"
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert structure to dictionary for serialization."""
        return {
            "graph_id": self.graph_id,
            "graph_name": self.graph_name,
            "containers": [c.to_dict() for c in self.containers],
            "edges": [e.to_dict() for e in self.edges],
            "start_containers": [c.container_id for c in self.start_containers],
            "end_containers": [c.container_id for c in self.end_containers],
            "validation_status": self.validation_status,
            "validation_errors": self.validation_errors,
        }


class GraphStructureBuilder:
    """Builds runtime topology structure from database definitions.

    This class loads graph, nodes, and edges from the database
    and builds the runtime structure without actual execution.

    Note: No actual graph traversal or execution is performed.
    Only structure building and validation.
    """

    def __init__(self, db_service=None):
        """Initialize the graph structure builder.

        Args:
            db_service: Database service for loading topology data
        """
        self.db_service = db_service
        self.edge_processor = EdgeProcessor()

    def load_topology(
        self,
        graph_id: str,
        graph_db: Dict[str, Any],
        nodes_db: List[Dict[str, Any]],
        edges_db: List[Dict[str, Any]],
        containers_db: Optional[List[Dict[str, Any]]] = None,
    ) -> TopologyStructure:
        """Load topology from database and build runtime structure.

        Args:
            graph_id: The graph ID to load
            graph_db: Graph database record
            nodes_db: List of node database records
            edges_db: List of edge database records
            containers_db: List of container database records

        Returns:
            TopologyStructure with containers and edges

        Note: This method only builds structure. It does NOT
        execute or traverse the graph.
        """
        containers = self._build_containers(
            graph_id=graph_id,
            containers_db=containers_db or [],
            nodes_db=nodes_db,
        )

        # Build edges from database edges
        edges = self.edge_processor.build_edges(containers, edges_db)

        # Find start and end containers
        start_containers = [
            c for c in containers if any(n.node_type == NodeType.START for n in c.nodes)
        ]
        end_containers = [
            c for c in containers if any(n.node_type == NodeType.END for n in c.nodes)
        ]

        return TopologyStructure(
            graph_id=graph_id,
            graph_name=graph_db.get("name", ""),
            containers=containers,
            edges=edges,
            start_containers=start_containers,
            end_containers=end_containers,
        )

    def _build_containers(
        self,
        graph_id: str,
        containers_db: List[Dict[str, Any]],
        nodes_db: List[Dict[str, Any]],
    ) -> List[AgentContainer]:
        container_map: Dict[str, AgentContainer] = {}

        for container_db in containers_db:
            container = AgentContainer.from_db_container(container_db)
            container_map[container.container_id] = container

        # Put nodes into existing containers by container_id.
        unassigned_nodes: List[ContainerNode] = []
        for node_db in nodes_db:
            node = ContainerNode.from_db_node(node_db)
            container_id = node_db.get("container_id")
            if container_id and container_id in container_map:
                container_map[container_id].add_node(node)
            else:
                unassigned_nodes.append(node)

        # Backward-compatible fallback for historical graphs without containers.
        if unassigned_nodes:
            fallback_container_id = f"{graph_id}::default-container"
            fallback = AgentContainer(
                container_id=fallback_container_id,
                container_key="default_container",
                label="Default Container",
                role_type=RoleType.SYSTEM,
                config={"auto_generated": True, "reason": "nodes_without_container"},
                order_index=10**9,
            )
            for node in unassigned_nodes:
                fallback.add_node(node)
            container_map[fallback_container_id] = fallback

        containers = list(container_map.values())
        containers.sort(key=lambda c: (c.order_index, c.container_key))
        return containers

    def validate_topology(self, structure: TopologyStructure) -> List[str]:
        """Validate topology structure.

        Args:
            structure: The TopologyStructure to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check for start containers
        if not structure.start_containers:
            errors.append("Topology must have at least one start node")

        # Check for end containers
        if not structure.end_containers:
            errors.append("Topology must have at least one end node")

        # Check that all containers are connected
        connected_container_ids = set()
        for edge in structure.edges:
            connected_container_ids.add(edge.source_container_id)
            connected_container_ids.add(edge.target_container_id)

        if structure.edges and len(structure.containers) > 1:
            for container in structure.containers:
                if container.container_id not in connected_container_ids:
                    errors.append(
                        f"Container '{container.node_key}' is not connected to any cross-container edge"
                    )

        # Validate each edge
        container_map = {
            c.container_id: c for c in structure.containers
        }
        for edge in structure.edges:
            edge_errors = self.edge_processor.validate_edge_structure(
                edge, structure.containers
            )
            errors.extend(edge_errors)

        return errors

    def build_container_graph(
        self,
        containers: List[AgentContainer],
        edges: List[CrossContainerEdge],
    ) -> Dict[str, Dict[str, List[CrossContainerEdge]]]:
        """Build adjacency graph for containers.

        Args:
            containers: List of all containers
            edges: List of all edges

        Returns:
            Dictionary mapping container IDs to their outgoing edges
        """
        graph = {}

        for container in containers:
            container_id = container.container_id
            outgoing = self.edge_processor.get_outgoing_edges(
                container_id, edges
            )
            graph[container_id] = outgoing

        return graph
