"""API router for topology structure operations.

This router provides endpoints for getting topology structures,
validation, and export without actual execution.

Note: This is for manual modeling and structure building only.
No actual graph traversal or execution is performed at this stage.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from backend_business.services.db_service import db_service
from backend_business.services.agent.topology import (
    AgentContainer,
    EdgeType,
    GraphStructureBuilder,
    StructureValidator,
    TopologyStructureSerializer,
)
from .schemas.execution_topology_structure_schemas import (
    AgentContainerSchema,
    CrossContainerEdgeSchema,
    ExportTopologyResponse,
    ExportedTopologySchema,
    GetContainersResponse,
    GetEdgesResponse,
    GetTopologyStructureResponse,
    SerializedTopologySchema,
    TopologyStructureSchema,
    ValidateTopologyRequest,
    ValidateTopologyResponse,
    ValidationResultSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/execution-topology", tags=["execution-topology-structure"])


# Helper functions


def get_current_user(request) -> Dict[str, Any]:
    """Get current user from request headers."""
    # TODO: Implement proper authentication when available
    # For now, return a placeholder user ID
    return {"user_id": "system", "session_id": "default"}


# Endpoints


@router.get("/{graph_id}/structure", response_model=GetTopologyStructureResponse)
async def get_topology_structure(
    graph_id: str,
    request: Dict[str, Any] = Depends(get_current_user),
):
    """Get the compiled topology structure for a graph.

    This endpoint loads the topology from the database and returns
    the compiled runtime structure with containers and edges.

    Args:
        graph_id: The graph ID to load

    Returns:
        GetTopologyStructureResponse with the topology structure
    """
    try:
        # Load graph from database
        graph = db_service.get_execution_graph(graph_id)
        if not graph:
            raise HTTPException(status_code=404, detail="Graph not found")

        # Load nodes and edges from database
        nodes = db_service.list_execution_nodes(graph_id)
        edges = db_service.list_execution_edges(graph_id)

        # Build topology structure
        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(graph_id, graph, nodes, edges)

        # Validate structure
        validator = StructureValidator()
        validation = validator.validate(structure)
        structure.validation_status = "valid" if validation.is_valid else "invalid"
        structure.validation_errors = validation.errors

        return GetTopologyStructureResponse(
            success=True,
            structure=TopologyStructureSchema(
                graph_id=structure.graph_id,
                graph_name=structure.graph_name,
                containers=[AgentContainerSchema(**c.to_dict()) for c in structure.containers],
                edges=[CrossContainerEdgeSchema(**e.to_dict()) for e in structure.edges],
                start_containers=[c.container_id for c in structure.start_containers],
                end_containers=[c.container_id for c in structure.end_containers],
                validation_status=structure.validation_status,
                validation_errors=structure.validation_errors,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting topology structure: {e}")
        return GetTopologyStructureResponse(success=False, error=str(e))


@router.post("/{graph_id}/validate", response_model=ValidateTopologyResponse)
async def validate_topology_structure(
    graph_id: str,
    request_body: ValidateTopologyRequest,
    request: Dict[str, Any] = Depends(get_current_user),
):
    """Validate the topology structure.

    This endpoint loads and validates the topology structure
    without caching (unless dry_run is False).

    Args:
        graph_id: The graph ID to validate
        request_body: Validation request parameters

    Returns:
        ValidateTopologyResponse with validation result
    """
    try:
        # Load topology structure
        graph = db_service.get_execution_graph(graph_id)
        if not graph:
            raise HTTPException(status_code=404, detail="Graph not found")

        nodes = db_service.list_execution_nodes(graph_id)
        edges = db_service.list_execution_edges(graph_id)

        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(graph_id, graph, nodes, edges)

        # Validate structure
        validator = StructureValidator()
        validation = validator.validate(structure)

        return ValidateTopologyResponse(
            success=True,
            result=ValidationResultSchema(
                is_valid=validation.is_valid,
                errors=validation.errors,
                warnings=validation.warnings,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating topology structure: {e}")
        return ValidateTopologyResponse(success=False, error=str(e))


@router.get("/{graph_id}/containers", response_model=GetContainersResponse)
async def get_containers(
    graph_id: str,
    request: Dict[str, Any] = Depends(get_current_user),
    node_type: Optional[str] = Query(None, description="Filter by node type"),
    role_type: Optional[str] = Query(None, description="Filter by role type"),
):
    """Get all container definitions for a graph.

    This endpoint returns the list of AgentContainer objects
    for the specified graph, optionally filtered by type or role.

    Args:
        graph_id: The graph ID to load containers from
        node_type: Optional filter for node type
        role_type: Optional filter for role type

    Returns:
        GetContainersResponse with the list of containers
    """
    try:
        # Load nodes from database
        nodes = db_service.list_execution_nodes(graph_id)

        # Build containers
        containers = [AgentContainer.from_db_node(node) for node in nodes]

        # Apply filters
        if node_type:
            containers = [c for c in containers if c.node_type.value == node_type]
        if role_type:
            containers = [c for c in containers if c.role_type.value == role_type]

        return GetContainersResponse(
            success=True,
            containers=[AgentContainerSchema(**c.to_dict()) for c in containers],
        )

    except Exception as e:
        logger.error(f"Error getting containers: {e}")
        return GetContainersResponse(success=False, error=str(e))


@router.get("/{graph_id}/edges", response_model=GetEdgesResponse)
async def get_edges(
    graph_id: str,
    request: Dict[str, Any] = Depends(get_current_user),
    edge_type: Optional[str] = Query(None, description="Filter by edge type"),
):
    """Get all edge definitions for a graph.

    This endpoint returns the list of CrossContainerEdge objects
    for the specified graph, optionally filtered by type.

    Args:
        graph_id: The graph ID to load edges from
        edge_type: Optional filter for edge type

    Returns:
        GetEdgesResponse with the list of edges
    """
    try:
        # Load edges from database
        edges_db = db_service.list_execution_edges(graph_id)

        # Load nodes for container ID mapping
        nodes = db_service.list_execution_nodes(graph_id)
        containers = [AgentContainer.from_db_node(node) for node in nodes]

        # Build edges
        builder = GraphStructureBuilder(db_service)
        edges = builder.edge_processor.build_edges(containers, edges_db)

        # Apply filter
        if edge_type:
            edges = [e for e in edges if e.edge_type.value == edge_type]

        return GetEdgesResponse(
            success=True,
            edges=[CrossContainerEdgeSchema(**e.to_dict()) for e in edges],
        )

    except Exception as e:
        logger.error(f"Error getting edges: {e}")
        return GetEdgesResponse(success=False, error=str(e))


@router.get("/{graph_id}/export", response_model=ExportTopologyResponse)
async def export_topology(
    graph_id: str,
    request: Dict[str, Any] = Depends(get_current_user),
    format: str = Query("json", description="Export format (json)"),
):
    """Export topology structure for agent consumption.

    This endpoint exports the topology structure in a format
    that can be understood and taken over by intelligent agents.

    Args:
        graph_id: The graph ID to export
        format: Export format (only 'json' supported)

    Returns:
        ExportTopologyResponse with the exported structure
    """
    try:
        if format != "json":
            raise HTTPException(
                status_code=400, detail="Only 'json' format is supported"
            )

        # Load topology structure
        graph = db_service.get_execution_graph(graph_id)
        if not graph:
            raise HTTPException(status_code=404, detail="Graph not found")

        nodes = db_service.list_execution_nodes(graph_id)
        edges = db_service.list_execution_edges(graph_id)

        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(graph_id, graph, nodes, edges)

        # Serialize for agent consumption
        serializer = TopologyStructureSerializer()
        exported_data = serializer.export_for_agent(structure)

        return ExportTopologyResponse(
            success=True,
            exported=ExportedTopologySchema(**exported_data),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting topology: {e}")
        return ExportTopologyResponse(success=False, error=str(e))
