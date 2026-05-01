from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.execution.topology_instantiator import (
    RuntimeContainer,
    RuntimeSubgraph,
)
from backend_business.services.agent.experience.targets import (
    ExperienceTarget,
    resolve_experience_target,
    resolve_experience_target_from_subgraph,
)


def test_resolve_experience_target_from_subgraph_uses_prompt_builder():
    container = RuntimeContainer(
        container_id="container-1",
        container_key="conflict_detection",
        label="Conflict Detection",
        role_type="agent",
        order_index=2,
        source_container_id="source-container-1",
    )
    subgraph = RuntimeSubgraph(
        subgraph_id="subgraph-1",
        container_id="container-1",
        subgraph_key="conflict_detection_runtime",
        label="Conflict Runtime",
        task_description="执行冲突检测委托任务",
        status="pending",
        order_index=1,
        node_type="llm",
        config_json={"prompt_builder": "session_controller_conflict_delegate"},
        source_node_id="node-1",
    )

    target = resolve_experience_target_from_subgraph(
        container=container,
        subgraph=subgraph,
    )

    assert target == ExperienceTarget(
        target_id="session_controller_conflict_delegate",
        container_key="conflict_detection",
        prompt_builder_kind="session_controller_conflict_delegate",
        node_type="llm",
    )


def test_resolve_experience_target_uses_tool_loop_agent_mapping():
    target = resolve_experience_target(
        container_key="requirement_agent",
        agent_type="requirement_agent",
        node_type="llm",
    )

    assert target == ExperienceTarget(
        target_id="requirement_agent_tool_loop",
        container_key="requirement_agent",
        prompt_builder_kind="",
        node_type="llm",
    )


def test_resolve_experience_target_returns_none_without_identifiers():
    assert resolve_experience_target() is None
