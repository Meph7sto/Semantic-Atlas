from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.conflict_detection_agent.prompt_builder import (
    ConflictDetectionPromptBuilder,
)
from backend_business.services.agent.agents.conflict_detection_agent.tool_loop_runner import (
    ConflictDetectionToolLoopRunner,
)
from backend_business.services.agent.experience import SkillLoader, SkillRetriever


_SEED_TOOL_LOOP_SKILL = """---
skill_id: exp_conflict_detection_tool_loop_seed_20260418_001
experience_target: conflict_detection_tool_loop
container_key: conflict_detection
prompt_builder_kind: ""
node_type: llm
task_pattern_summary: 检测两个需求之间是否冲突
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 当用户要求检查需求冲突时使用

## 推荐步骤

1. 先定位目标需求
2. 再读取需求详情
3. 最后基于工具结果输出结论

## 常见陷阱

- 不要跳过详情读取

## 结果呈现建议

- 先给出结论，再说明原因
"""


class _FakeExecutionGraphService:
    def __init__(self) -> None:
        self.meta_patches: list[dict] = []

    def patch_graph_meta(self, graph_id, meta_patch, updated_by=""):
        self.meta_patches.append(
            {
                "graph_id": graph_id,
                "meta_patch": dict(meta_patch or {}),
                "updated_by": updated_by,
            }
        )
        return {"graph_id": graph_id, "meta_json": dict(meta_patch or {})}


class _FakeRecorder:
    def __init__(self) -> None:
        self.graph_id = "graph-1"
        self.turn_index = 1

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_1__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn 1)"

    def start_stage(self, *, node_key, label, node_type, role_type, container_key, created_by, input_summary, **_kw):
        _ = node_key, label, node_type, role_type, container_key, created_by, input_summary

    def record_tool_call_result(self, node_key, *, created_by, tool_name, request_payload, result_payload):
        _ = node_key, created_by, tool_name, request_payload, result_payload

    def complete_stage(self, node_key, *, created_by, output_summary, **_kw):
        _ = node_key, created_by, output_summary


class _FakeTools:
    def get_tools_list(self, context=None):
        _ = context
        return []

    def execute(self, tool_name: str, arguments: dict, context: dict):
        _ = tool_name, arguments, context
        return {"ok": True}


class _FakeAIProxy:
    def __init__(self) -> None:
        self.system_prompts: list[str] = []

    def chat_completion_with_tools(self, *, messages, tools, **_kw):
        _ = tools
        self.system_prompts.append(str(messages[0].get("content") or ""))
        return {
            "content": "冲突检测完成",
            "finish_reason": "stop",
            "tool_calls": [],
        }


def _drain_with_result(gen):
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        return events, stop.value


def _seed_root(root: Path) -> None:
    target_dir = root / "conflict_detection_tool_loop"
    (target_dir / "archive").mkdir(parents=True, exist_ok=True)
    (target_dir / "current.md").write_text(_SEED_TOOL_LOOP_SKILL, encoding="utf-8")
    (root / "_registry.yaml").write_text(
        "version: 1\n"
        "targets:\n"
        "  conflict_detection_tool_loop:\n"
        "    skill_id: exp_conflict_detection_tool_loop_seed_20260418_001\n"
        "    current_skill_path: conflict_detection_tool_loop/current.md\n"
        "    iteration: 1\n"
        "    invocation_count: 0\n"
        "    injection_miss_count: 0\n",
        encoding="utf-8",
    )


def test_conflict_detection_tool_loop_injects_tool_loop_skill(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    ai_proxy = _FakeAIProxy()
    graph_service = _FakeExecutionGraphService()
    runner = ConflictDetectionToolLoopRunner(
        ai_proxy_client=ai_proxy,
        tools=_FakeTools(),
        execution_graph_service=graph_service,
        prompt_builder=ConflictDetectionPromptBuilder(),
        max_tool_call_rounds=2,
        stage_container_key="conflict_detection",
        experience_retriever=SkillRetriever(root),
        skill_loader=SkillLoader(),
    )

    _events, result = _drain_with_result(
        runner.run(
            recorder=_FakeRecorder(),
            user_id="u-1",
            user_message="请检查支付需求和退款需求是否冲突",
            project_id="proj-1",
            session_id="s-1",
        )
    )

    assert result["tool_loop_reply"] == "冲突检测完成"
    assert ai_proxy.system_prompts
    assert "## 已命中的经验技能" in ai_proxy.system_prompts[0]
    assert any(
        item["meta_patch"].get("injected_skill_id")
        == "exp_conflict_detection_tool_loop_seed_20260418_001"
        for item in graph_service.meta_patches
    )
