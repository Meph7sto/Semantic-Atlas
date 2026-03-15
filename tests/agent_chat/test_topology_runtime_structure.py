"""
Tests for topology runtime structures consuming execution graph node types.
"""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.topology.agent_container import ContainerNode
from backend_business.services.agent.topology.graph_structure_builder import GraphStructureBuilder


def test_container_node_accepts_runtime_llm_node_type():
    node = ContainerNode.from_db_node(
        {
            "node_id": "node-1",
            "node_key": "requirements_agent_tool_loop_round_1",
            "label": "Tool Loop Round 1",
            "node_type": "llm",
            "role_type": "agent",
            "config_json": {"runtime": True},
        }
    )

    assert node.node_type.value == "llm"
    assert node.to_dict()["node_type"] == "llm"


def test_graph_structure_builder_preserves_runtime_invoke_node_type():
    builder = GraphStructureBuilder()
    structure = builder.load_topology(
        graph_id="graph-1",
        graph_db={"name": "Runtime Graph"},
        containers_db=[
            {
                "container_id": "container-1",
                "container_key": "requirements_tools",
                "label": "Requirement Tools",
                "role_type": "system",
                "config_json": {"runtime": True},
                "order_index": 0,
            }
        ],
        nodes_db=[
            {
                "node_id": "node-2",
                "container_id": "container-1",
                "node_key": "invoke_search_requirements",
                "label": "Invoke Search Requirements",
                "node_type": "invoke",
                "role_type": "system",
                "config_json": {"runtime": True},
                "input_schema_json": [],
                "output_schema_json": [],
                "order_index": 0,
            }
        ],
        edges_db=[],
    )

    assert structure.containers[0].nodes[0].node_type.value == "invoke"
    assert structure.to_dict()["containers"][0]["nodes"][0]["node_type"] == "invoke"
