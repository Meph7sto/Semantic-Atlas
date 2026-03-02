"""API routes for topology structure operations.

This router provides endpoints for getting topology structures,
validation, and export without actual execution.

Note: This is for manual modeling and structure building only.
No actual graph traversal or execution is performed at this stage.
"""

import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from backend_business.services.db_service import db_service
from backend_business.services.agent.topology import (
    AgentContainer,
    EdgeType,
    GraphStructureBuilder,
    StructureValidator,
    TopologyStructureSerializer,
)

logger = logging.getLogger(__name__)

execution_topology_structure_bp = Blueprint(
    "execution_topology_structure_bp", __name__
)


# Helper functions


def get_current_user() -> Dict[str, Any]:
    """Get current user from request headers.

    TODO: Implement proper authentication when available.
    For now, return a placeholder user ID.
    """
    # Try to get user from X-Actor header
    user_id = request.headers.get("X-Actor", "system")
    return {"user_id": user_id, "session_id": "default"}


def error_response(message: str, status_code: int = 500) -> tuple:
    """Create error response."""
    response = jsonify({"success": False, "error": message})
    return response, status_code


# Routes


@execution_topology_structure_bp.route(
    "/<graph_id>/structure", methods=["GET"]
)
def get_topology_structure(graph_id: str):
    """Get the compiled topology structure for a graph.

    This endpoint loads the topology from the database and returns
    the compiled runtime structure with containers and edges.

    Args:
        graph_id: The graph ID to load

    Returns:
        JSON response with the topology structure
    """
    try:
        # Load graph from database
        graph = db_service.get_execution_graph(graph_id)
        if not graph:
            return error_response("Graph not found", 404)

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

        return jsonify(
            {
                "success": True,
                "structure": {
                    "graph_id": structure.graph_id,
                    "graph_name": structure.graph_name,
                    "containers": [c.to_dict() for c in structure.containers],
                    "edges": [e.to_dict() for e in structure.edges],
                    "start_containers": [c.container_id for c in structure.start_containers],
                    "end_containers": [c.container_id for c in structure.end_containers],
                    "validation_status": structure.validation_status,
                    "validation_errors": structure.validation_errors,
                },
            }
        )

    except Exception as e:
        logger.error(f"Error getting topology structure: {e}")
        return error_response(str(e))


@execution_topology_structure_bp.route(
    "/<graph_id>/validate", methods=["POST"]
)
def validate_topology_structure(graph_id: str):
    """Validate the topology structure.

    This endpoint loads and validates the topology structure.

    Args:
        graph_id: The graph ID to validate

    Returns:
        JSON response with validation result
    """
    try:
        request_body = request.get_json() or {}

        # Load topology structure
        graph = db_service.get_execution_graph(graph_id)
        if not graph:
            return error_response("Graph not found", 404)

        nodes = db_service.list_execution_nodes(graph_id)
        edges = db_service.list_execution_edges(graph_id)

        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(graph_id, graph, nodes, edges)

        # Validate structure
        validator = StructureValidator()
        validation = validator.validate(structure)

        return jsonify(
            {
                "success": True,
                "result": {
                    "is_valid": validation.is_valid,
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                },
            }
        )

    except Exception as e:
        logger.error(f"Error validating topology structure: {e}")
        return error_response(str(e))


@execution_topology_structure_bp.route(
    "/<graph_id>/containers", methods=["GET"]
)
def get_containers(graph_id: str):
    """Get all container definitions for a graph.

    This endpoint returns the list of AgentContainer objects
    for the specified graph, optionally filtered by type or role.

    Query Parameters:
        node_type: Filter by node type (optional)
        role_type: Filter by role type (optional)

    Returns:
        JSON response with the list of containers
    """
    try:
        # Load nodes from database
        nodes = db_service.list_execution_nodes(graph_id)

        # Build containers
        containers = [AgentContainer.from_db_node(node) for node in nodes]

        # Apply filters from query parameters
        node_type = request.args.get("node_type")
        role_type = request.args.get("role_type")

        if node_type:
            containers = [c for c in containers if c.node_type.value == node_type]
        if role_type:
            containers = [c for c in containers if c.role_type.value == role_type]

        return jsonify(
            {
                "success": True,
                "containers": [c.to_dict() for c in containers],
            }
        )

    except Exception as e:
        logger.error(f"Error getting containers: {e}")
        return error_response(str(e))


@execution_topology_structure_bp.route(
    "/<graph_id>/edges", methods=["GET"]
)
def get_edges(graph_id: str):
    """Get all edge definitions for a graph.

    This endpoint returns the list of CrossContainerEdge objects
    for the specified graph, optionally filtered by type.

    Query Parameters:
        edge_type: Filter by edge type (optional)

    Returns:
        JSON response with the list of edges
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

        # Apply filter from query parameters
        edge_type = request.args.get("edge_type")
        if edge_type:
            edges = [e for e in edges if e.edge_type.value == edge_type]

        return jsonify(
            {
                "success": True,
                "edges": [e.to_dict() for e in edges],
            }
        )

    except Exception as e:
        logger.error(f"Error getting edges: {e}")
        return error_response(str(e))


@execution_topology_structure_bp.route(
    "/<graph_id>/export", methods=["GET"]
)
def export_topology(graph_id: str):
    """Export topology structure for agent consumption.

    This endpoint exports the topology structure in a format
    that can be understood and taken over by intelligent agents.

    Query Parameters:
        format: Export format (only 'json' supported)

    Returns:
        JSON response with the exported structure
    """
    try:
        format_param = request.args.get("format", "json")

        if format_param != "json":
            return error_response("Only 'json' format is supported", 400)

        # Load topology structure
        graph = db_service.get_execution_graph(graph_id)
        if not graph:
            return error_response("Graph not found", 404)

        nodes = db_service.list_execution_nodes(graph_id)
        edges = db_service.list_execution_edges(graph_id)

        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(graph_id, graph, nodes, edges)

        # Serialize for agent consumption
        serializer = TopologyStructureSerializer()
        exported_data = serializer.export_for_agent(structure)

        return jsonify(
            {
                "success": True,
                "exported": exported_data,
            }
        )

    except Exception as e:
        logger.error(f"Error exporting topology: {e}")
        return error_response(str(e))
