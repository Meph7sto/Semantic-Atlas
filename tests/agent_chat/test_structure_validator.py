"""Tests for topology structure validation compatibility."""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.topology import GraphStructureBuilder, StructureValidator


def _build_structure(*, conditional_edges):
    builder = GraphStructureBuilder()
    return builder.load_topology(
        graph_id="graph-1",
        graph_db={"name": "Runtime Graph"},
        containers_db=[
            {
                "container_id": "container-1",
                "container_key": "main",
                "label": "Main",
                "role_type": "agent",
                "config_json": {},
                "order_index": 0,
            }
        ],
        nodes_db=[
            {
                "node_id": "node-1",
                "container_id": "container-1",
                "node_key": "decision",
                "label": "Decision",
                "node_type": "llm",
                "role_type": "agent",
                "phase_label": "判断",
                "task_prompt": "判断",
                "conditional_edges": conditional_edges,
                "config_json": {},
                "input_schema_json": [],
                "output_schema_json": [],
                "order_index": 0,
            },
            {
                "node_id": "node-2",
                "container_id": "container-1",
                "node_key": "approved",
                "label": "Approved",
                "node_type": "llm",
                "role_type": "agent",
                "phase_label": "通过",
                "task_prompt": "继续",
                "conditional_edges": [],
                "config_json": {},
                "input_schema_json": [],
                "output_schema_json": [],
                "order_index": 1,
            },
        ],
        edges_db=[],
    )


def test_structure_validator_accepts_node_conditional_edges_route_keys():
    structure = _build_structure(
        conditional_edges=[{"condition": "approved", "target_node_id": "node-2"}]
    )

    result = StructureValidator().validate(structure)

    assert result.is_valid is True
    assert result.errors == []


def test_structure_validator_rejects_missing_conditional_edge_target_node():
    structure = _build_structure(
        conditional_edges=[{"condition": "approved", "target_node_id": "node-404"}]
    )

    result = StructureValidator().validate(structure)

    assert result.is_valid is False
    assert any("node-404" in error for error in result.errors)
