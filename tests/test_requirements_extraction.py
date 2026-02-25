"""Unit tests for requirements extraction building blocks.

This file used to be an interactive demo script and drifted from the current
implementation. It is now a small pytest-compatible suite that:

- asserts EgoBundleGenerator behavior
- validates RequirementsExecutor parsing/validation against the current API

It intentionally avoids real DB connections.
"""

from __future__ import annotations

import os
import sys

import pytest


# Keep compatibility with running pytest from arbitrary CWD.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sample_spans():
    return [
        {
            "span_id": "span_001",
            "session_id": "test_session",
            "start_ms": 0,
            "end_ms": 5000,
            "speaker": "PM",
            "text": "我们需要提升借用审批效率，降低人工核验成本",
        },
        {
            "span_id": "span_002",
            "session_id": "test_session",
            "start_ms": 5000,
            "end_ms": 10000,
            "speaker": "TechLead",
            "text": "可以考虑增加在线提交借用申请的功能",
        },
        {
            "span_id": "span_003",
            "session_id": "test_session",
            "start_ms": 10000,
            "end_ms": 15000,
            "speaker": "PM",
            "text": "对，系统应该支持用户自主填写申请表单",
        },
        {
            "span_id": "span_004",
            "session_id": "test_session",
            "start_ms": 15000,
            "end_ms": 20000,
            "speaker": "TechLead",
            "text": "系统必须在 2 秒内完成审批流程验证，保证用户体验",
        },
        {
            "span_id": "span_005",
            "session_id": "test_session",
            "start_ms": 20000,
            "end_ms": 25000,
            "speaker": "PM",
            "text": "还需要考虑权限控制，不同角色看到的内容应该不同",
        },
    ]


def test_ego_bundle_generator_select_anchors_all():
    from backend_business.services.ego_bundle_generator import EgoBundleGenerator

    spans = _sample_spans()
    generator = EgoBundleGenerator(max_spans_per_bundle=10)

    anchors = generator.select_anchors(spans, strategy="all")
    assert anchors == list(range(len(spans)))


def test_ego_bundle_generator_generate_sequence_bundle_shape():
    from backend_business.services.ego_bundle_generator import EgoBundleGenerator

    spans = _sample_spans()
    generator = EgoBundleGenerator(max_spans_per_bundle=10)

    bundle = generator.generate_sequence_bundle(spans, anchor_idx=2, r=2)

    assert bundle["anchor_span_id"] == "span_003"
    assert bundle["anchor_idx"] == 2
    assert bundle["strategy"] == "sequence"
    assert bundle["r"] == 2
    assert len(bundle["spans"]) == 5
    assert bundle["span_refs"] == ["S1", "S2", "S3", "S4", "S5"]
    assert bundle["ref_mapping"]["S3"] == "span_003"


def _import_executor_or_skip():
    try:
        from backend_business.services.requirements_executor import RequirementsExecutor

        return RequirementsExecutor
    except Exception as e:  # pragma: no cover
        pytest.skip(f"RequirementsExecutor import failed in this env: {e}")


def test_requirements_executor_parse_toolcalls_legacy_call_lines():
    RequirementsExecutor = _import_executor_or_skip()

    model_output = (
        'CALL create_req level="L1" text="提升借用审批效率并降低人工核验成本"\n'
        'CALL create_req level="L2" text="系统应支持在线提交借用申请"\n'
        'CALL create_req level="L3" text="系统必须在 2 秒内完成审批流程验证"\n'
    )

    executor = RequirementsExecutor(dsn="postgresql://test:test@localhost:5432/test")
    create_calls, update_calls = executor.parse_toolcalls(model_output)

    assert len(create_calls) == 3
    assert update_calls == []
    assert create_calls[0]["level"] == "L1"
    assert "提升借用审批效率" in create_calls[0]["text"]


def test_requirements_executor_validate_toolcall_and_quota():
    RequirementsExecutor = _import_executor_or_skip()

    executor = RequirementsExecutor(dsn="postgresql://test:test@localhost:5432/test")

    calls = [
        {"level": "L1", "text": "提升借用审批效率并降低人工核验成本"},
        {"level": "L2", "text": "系统应支持在线提交借用申请"},
        {"level": "L3", "text": "系统必须在2秒内完成审批流程验证"},
    ]

    for call in calls:
        ok, err = executor.validate_toolcall(call)
        assert ok is True
        assert err is None

    quota_ok, quota_err = executor.check_quota(calls)
    assert quota_ok is True
    assert quota_err is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
