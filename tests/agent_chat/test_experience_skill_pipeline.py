from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience import (
    ExperienceOrchestrator,
    SkillRegistry,
    SkillStore,
)
from backend_business.services.agent.experience.collector import ExperienceCollector
from backend_business.services.agent.experience.skill_sanitizer import (
    SkillSanitizeResult,
)
from backend_business.services.agent.experience.targets import ExperienceTarget


_SEED_SKILL = """---
skill_id: exp_session_controller_conflict_delegate_seed_20260418_001
experience_target: session_controller_conflict_delegate
container_key: conflict_detection
prompt_builder_kind: session_controller_conflict_delegate
node_type: llm
task_pattern_summary: seed
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- seed scene

## 推荐步骤

1. seed one
2. seed two
3. seed three

## 常见陷阱

- seed pitfall

## 结果呈现建议

- seed result

## 成功案例模式摘要

- seed summary
"""


class _FakeGraphService:
    def __init__(self) -> None:
        self._detail = {
            "containers": [
                {
                    "container_id": "container-1",
                    "container_key": "conflict_detection",
                }
            ],
            "subgraphs": [
                {
                    "subgraph_id": "subgraph-1",
                    "subgraph_key": "conflict_delegate",
                    "task_description": "检测两个需求之间是否冲突",
                }
            ],
            "nodes": [
                {
                    "node_id": "node-1",
                    "container_id": "container-1",
                    "node_key": "turn_1__sg_conflict_delegate_r1",
                    "order_index": 1,
                    "config_json": {
                        "output_summary": {"conclusion": "先读取详情，再检测冲突"},
                        "tool_call_results": [
                            {
                                "tool_name": "list_requirements",
                                "request": {"keyword": "payment"},
                                "result": {"items": [{"id": "R-12"}]},
                            },
                            {
                                "tool_name": "detect_conflict",
                                "request": {"left": "R-12", "right": "R-13"},
                                "result": {"conflict": True},
                            },
                        ],
                    },
                }
            ],
        }

    def get_graph_detail(self, graph_id: str) -> dict:
        _ = graph_id
        return self._detail


class _FakeRecorder:
    def __init__(self) -> None:
        self._task_context = {
            "user_message": "请检查支付需求和退款需求是否冲突",
        }


class _AlwaysFailSanitizer:
    def sanitize(self, *, content: str, material=None):
        _ = content, material
        return SkillSanitizeResult(
            passed=False,
            sanitized_content="",
            failure_reason="forced sanitizer failure",
        )


def _seed_root(root: Path) -> None:
    store = SkillStore(root)
    registry = SkillRegistry(root)
    registry.initialize()
    store.write_current(
        "session_controller_conflict_delegate",
        _SEED_SKILL,
        archive_existing=False,
    )
    registry.upsert_target(
        "session_controller_conflict_delegate",
        skill_id="exp_session_controller_conflict_delegate_seed_20260418_001",
        current_skill_path="session_controller_conflict_delegate/current.md",
        iteration=1,
        updated_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


def test_experience_orchestrator_writes_updated_skill_and_registry(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    orchestrator = ExperienceOrchestrator(root_path=root)

    result = orchestrator.process_outcome(
        target=ExperienceTarget(
            target_id="session_controller_conflict_delegate",
            container_key="conflict_detection",
            prompt_builder_kind="session_controller_conflict_delegate",
            node_type="llm",
        ),
        graph_id="graph-1",
        graph_service=_FakeGraphService(),
        recorder=_FakeRecorder(),
        scratchpad_snapshot=[
            {
                "container_key": "conflict_detection",
                "source_subgraph": "conflict_delegate",
                "content": "已读取两条需求详情",
            }
        ],
        container_key="conflict_detection",
        subgraph_key="conflict_delegate",
        user_message="请检查支付需求和退款需求是否冲突",
        task_description="检测两个需求之间是否冲突",
        final_conclusion="存在冲突，需要重点说明互斥点",
        runtime_status="succeeded",
    )

    current_skill = SkillStore(root).read_current("session_controller_conflict_delegate")
    entry = SkillRegistry(root).get_target("session_controller_conflict_delegate")

    assert result.status == "written"
    assert current_skill is not None
    assert "detect_conflict" in current_skill
    assert "R-12" not in current_skill
    assert "R-13" not in current_skill
    assert entry is not None
    assert entry["iteration"] == 2


def test_experience_orchestrator_does_not_write_when_sanitizer_fails(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    store = SkillStore(root)
    before = store.read_current("session_controller_conflict_delegate")
    orchestrator = ExperienceOrchestrator(
        root_path=root,
        sanitizer=_AlwaysFailSanitizer(),
    )

    result = orchestrator.process_outcome(
        target=ExperienceTarget(
            target_id="session_controller_conflict_delegate",
            container_key="conflict_detection",
            prompt_builder_kind="session_controller_conflict_delegate",
            node_type="llm",
        ),
        graph_id="graph-1",
        graph_service=_FakeGraphService(),
        recorder=_FakeRecorder(),
        scratchpad_snapshot=[],
        container_key="conflict_detection",
        subgraph_key="conflict_delegate",
        user_message="请检查支付需求和退款需求是否冲突",
        task_description="检测两个需求之间是否冲突",
        final_conclusion="存在冲突",
        runtime_status="succeeded",
    )

    after = store.read_current("session_controller_conflict_delegate")

    assert result.status == "skipped"
    assert result.reason == "forced sanitizer failure"
    assert before == after


def test_experience_orchestrator_failure_mode_only_updates_pitfalls(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    orchestrator = ExperienceOrchestrator(root_path=root)

    result = orchestrator.process_outcome(
        target=ExperienceTarget(
            target_id="session_controller_conflict_delegate",
            container_key="conflict_detection",
            prompt_builder_kind="session_controller_conflict_delegate",
            node_type="llm",
        ),
        graph_id="graph-2",
        graph_service=_FakeGraphService(),
        recorder=_FakeRecorder(),
        scratchpad_snapshot=[],
        container_key="conflict_detection",
        subgraph_key="conflict_delegate",
        user_message="请检查支付需求和退款需求是否冲突",
        task_description="检测两个需求之间是否冲突",
        final_conclusion=None,
        runtime_status="failed",
        final_error="tool timeout",
    )

    current_skill = SkillStore(root).read_current("session_controller_conflict_delegate")

    assert result.status == "written"
    assert current_skill is not None
    assert "tool timeout" in current_skill
    assert "seed one" in current_skill
