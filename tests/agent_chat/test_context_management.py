"""Unit tests for context management: Scratchpad + ExecutionContext + ToolLoopRunner integration."""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from typing import Any

import pytest

from backend_business.services.agent.runtime.scratchpad import Scratchpad, ScratchpadEntry
from backend_business.services.agent.runtime.context import ContextEntry, ExecutionContext


# ============================================================
# Scratchpad tests
# ============================================================


class TestScratchpadBasicReadWrite:
    def test_write_and_read_returns_entries(self):
        pad = Scratchpad()
        pad.write("note", "用户想修改登录页面", source_subgraph="analysis")
        pad.write("tool_excerpt", {"req_id": "R-1"}, source_subgraph="fetch")

        entries = pad.read()
        assert len(entries) == 2
        assert entries[0].entry_type == "note"
        assert entries[0].content == "用户想修改登录页面"
        assert entries[0].source_subgraph == "analysis"
        assert entries[1].entry_type == "tool_excerpt"
        assert entries[1].readonly is True  # tool_excerpt auto readonly

    def test_write_note_not_readonly_by_default(self):
        pad = Scratchpad()
        pad.write("note", "test")
        assert pad.read()[0].readonly is False

    def test_tool_excerpt_always_readonly(self):
        pad = Scratchpad()
        pad.write("tool_excerpt", "data", readonly=False)  # explicit False ignored
        assert pad.read()[0].readonly is True


class TestScratchpadFiltering:
    def test_filter_by_type(self):
        pad = Scratchpad()
        pad.write("note", "n1")
        pad.write("tool_excerpt", "t1")
        pad.write("note", "n2")

        notes = pad.read(filter_type="note")
        assert len(notes) == 2
        assert all(e.entry_type == "note" for e in notes)

        excerpts = pad.read(filter_type="tool_excerpt")
        assert len(excerpts) == 1

    def test_filter_after_subgraph(self):
        pad = Scratchpad()
        pad.write("note", "before", source_subgraph="sg1")
        pad.write("note", "also_sg1", source_subgraph="sg1")
        pad.write("note", "after_sg1", source_subgraph="sg2")
        pad.write("tool_excerpt", "later")

        entries = pad.read(after_subgraph="sg1")
        assert len(entries) == 2
        assert entries[0].content == "after_sg1"
        assert entries[1].content == "later"


class TestScratchpadStageOutput:
    def test_append_stage_output(self):
        pad = Scratchpad()
        pad.append_stage_output("analysis", {"conclusion": "需求明确"})

        entries = pad.read(filter_type="stage_output")
        assert len(entries) == 1
        assert entries[0].content == {"conclusion": "需求明确"}
        assert entries[0].source_subgraph == "analysis"
        assert entries[0].readonly is True


class TestScratchpadSerialization:
    def test_snapshot_and_restore(self):
        pad = Scratchpad()
        pad.write("note", "hello", source_subgraph="sg1")
        pad.write("tool_excerpt", {"k": "v"})
        pad.append_stage_output("sg1", "done")

        snapshot = pad.snapshot()
        assert len(snapshot) == 3
        assert all(isinstance(item, dict) for item in snapshot)

        restored = Scratchpad.from_snapshot(snapshot)
        assert len(restored) == 3
        assert restored.read()[0].content == "hello"
        assert restored.read()[1].readonly is True

    def test_from_snapshot_empty(self):
        pad = Scratchpad.from_snapshot([])
        assert len(pad) == 0

    def test_from_snapshot_none(self):
        pad = Scratchpad.from_snapshot(None)
        assert len(pad) == 0


class TestScratchpadPromptFormat:
    def test_empty_returns_empty_string(self):
        pad = Scratchpad()
        assert pad.format_for_prompt() == ""

    def test_non_empty_returns_formatted_text(self):
        pad = Scratchpad()
        pad.write("note", "important finding", source_subgraph="analysis")
        text = pad.format_for_prompt()
        assert "[Scratchpad" in text
        assert "NOTE" in text
        assert "important finding" in text
        assert "analysis" in text


# ============================================================
# ExecutionContext tests
# ============================================================


class TestExecutionContextBackwardCompat:
    def test_basic_add_and_snapshot(self):
        ctx = ExecutionContext()
        ctx.add(ContextEntry(kind="test", value="v1"))
        ctx.add(ContextEntry(kind="test", value="v2"))
        assert len(ctx.snapshot()) == 2
        assert ctx.snapshot()[0].value == "v1"

    def test_extend(self):
        ctx = ExecutionContext()
        ctx.extend([
            ContextEntry(kind="a", value=1),
            ContextEntry(kind="b", value=2),
        ])
        assert len(ctx.snapshot()) == 2

    def test_scratchpad_exists_by_default(self):
        ctx = ExecutionContext()
        assert isinstance(ctx.scratchpad, Scratchpad)

    def test_no_subgraph_by_default(self):
        ctx = ExecutionContext()
        assert ctx.current_subgraph is None


class TestExecutionContextSubgraph:
    def test_begin_and_end_subgraph(self):
        pad = Scratchpad()
        ctx = ExecutionContext(scratchpad=pad)

        ctx.begin_subgraph("sg1")
        assert ctx.current_subgraph == "sg1"

        ctx.add(ContextEntry(kind="work", value="data"))
        assert ctx.subgraph_entries("sg1")[0].subgraph_key == "sg1"

        ctx.end_subgraph("sg1", output={"result": "ok"})
        assert ctx.current_subgraph is None

        # Output was auto-appended to Scratchpad
        pad_entries = pad.read(filter_type="stage_output")
        assert len(pad_entries) == 1
        assert pad_entries[0].content == {"result": "ok"}

    def test_subgraph_entries_isolation(self):
        ctx = ExecutionContext()
        ctx.begin_subgraph("sg1")
        ctx.add(ContextEntry(kind="a", value="in_sg1"))
        ctx.end_subgraph("sg1")

        ctx.begin_subgraph("sg2")
        ctx.add(ContextEntry(kind="b", value="in_sg2"))

        sg1_entries = ctx.subgraph_entries("sg1")
        sg2_entries = ctx.subgraph_entries("sg2")
        assert len(sg1_entries) == 1
        assert sg1_entries[0].value == "in_sg1"
        assert len(sg2_entries) == 1
        assert sg2_entries[0].value == "in_sg2"

    def test_begin_subgraph_injects_scratchpad(self):
        pad = Scratchpad()
        pad.write("note", "prior knowledge")
        ctx = ExecutionContext(scratchpad=pad)

        ctx.begin_subgraph("sg1")
        # Internal global entries should have scratchpad snapshot
        assert len(ctx._global_entries) == 1
        assert "prior knowledge" in ctx._global_entries[0].value


# ============================================================
# ToolLoopRunner scratchpad integration
# ============================================================


class _FakeToolExecutor:
    def __init__(self, handlers=None):
        self._handlers = list(handlers or [])
        self.calls = []

    def get_tools_list(self):
        return [
            {
                "type": "function",
                "function": {"name": "dummy", "parameters": {"type": "object"}},
            }
        ]

    def execute(self, tool_name, arguments, context):
        self.calls.append((tool_name, arguments))
        if not self._handlers:
            return {"ok": True}
        return self._handlers.pop(0)(tool_name, arguments, context)


class _FakePromptBuilder:
    def build_system_prompt(self, *, context):
        return "system"

    def build_user_message(self, *, user_message, context):
        return f"user:{user_message}"

    def build_round_input_summary(self, *, round_index, messages, context):
        return {"round": round_index}


class _ContextAwarePromptBuilder:
    def build_system_prompt(self, *, context):
        execution_context = context.get("_execution_context")
        if execution_context is None:
            return "system"
        return execution_context.format_local_for_prompt(
            context.get("_current_subgraph"),
        )

    def build_user_message(self, *, user_message, context):
        return f"user:{user_message}"

    def build_round_input_summary(self, *, round_index, messages, context):
        return {"round": round_index}


class _FakeGraphService:
    def __init__(self):
        self.graph_counter = 0
        self.container_counter = 0
        self.node_counter = 0
        self.edge_counter = 0
        self.graphs = {}
        self.containers = {}
        self.nodes = {}
        self.edges = {}

    def create_runtime_graph(self, project_id, name, description="", created_by="", meta_json=None, layout_json=None, status="running"):
        self.graph_counter += 1
        gid = f"graph-{self.graph_counter}"
        g = {"graph_id": gid, "project_id": project_id, "name": name, "status": status, "meta_json": meta_json or {}, "created_by": created_by}
        self.graphs[gid] = g
        return dict(g)

    def patch_graph_meta(self, graph_id, meta_patch, status=None, updated_by=""):
        g = self.graphs[graph_id]
        merged = dict(g.get("meta_json") or {})
        merged.update(meta_patch or {})
        g["meta_json"] = merged
        if status:
            g["status"] = status
        return dict(g)

    def get_execution_graph(self, graph_id):
        g = self.graphs.get(graph_id)
        return dict(g) if g else None

    def get_graph_detail(self, graph_id):
        return {
            "graph": self.get_execution_graph(graph_id),
            "containers": [v for v in self.containers.values() if v["graph_id"] == graph_id],
            "nodes": [v for v in self.nodes.values() if v["graph_id"] == graph_id],
            "edges": [v for v in self.edges.values() if v["graph_id"] == graph_id],
        }

    def create_container(self, graph_id, container_key, label, role_type, config_json=None, order_index=0, created_by=""):
        self.container_counter += 1
        cid = f"container-{self.container_counter}"
        c = {"container_id": cid, "graph_id": graph_id, "container_key": container_key, "label": label, "role_type": role_type, "config_json": config_json or {}, "order_index": order_index}
        self.containers[cid] = c
        return dict(c)

    def create_node(self, graph_id, node_key, label, node_type, role_type, container_id=None, subgraph_id=None, config_json=None, input_schema_json=None, output_schema_json=None, order_index=0, created_by=""):
        self.node_counter += 1
        nid = f"node-{self.node_counter}"
        n = {"node_id": nid, "graph_id": graph_id, "container_id": container_id, "subgraph_id": subgraph_id, "node_key": node_key, "label": label, "node_type": node_type, "role_type": role_type, "config_json": config_json or {}, "order_index": order_index}
        self.nodes[nid] = n
        return dict(n)

    def get_node(self, node_id):
        return dict(self.nodes[node_id])

    def update_node(self, node_id, config_json=None, updated_by="", **kwargs):
        n = self.nodes[node_id]
        if config_json is not None:
            n["config_json"] = config_json
        return dict(n)

    def create_edge(self, graph_id, source_node_id, target_node_id, edge_type, label=None, condition_expr=None, config_json=None, order_index=0, created_by=""):
        self.edge_counter += 1
        eid = f"edge-{self.edge_counter}"
        e = {"edge_id": eid, "graph_id": graph_id, "source_node_id": source_node_id, "target_node_id": target_node_id, "edge_type": edge_type, "order_index": order_index}
        self.edges[eid] = e
        return dict(e)


class _FakeAiProxy:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def chat_completion_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected call")
        return self._responses.pop(0)


def _run_to_completion(gen):
    events = []
    while True:
        try:
            events.append(next(gen))
        except StopIteration as stop:
            return events, stop.value


class TestToolLoopRunnerScratchpadIntegration:
    def test_scratchpad_write_tool_injected_when_scratchpad_provided(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        pad = Scratchpad()
        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        runner = ToolLoopRunner(
            ai_proxy_client=_FakeAiProxy([
                {
                    "content": "",
                    "tool_calls": [{
                        "id": "tc-1",
                        "type": "function",
                        "function": {"name": "scratchpad_write", "arguments": '{"entry_type":"note","content":"user wants login change"}'},
                    }],
                    "finish_reason": "tool_calls",
                },
                {"content": "done", "tool_calls": [], "finish_reason": "stop"},
            ]),
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            scratchpad=pad,
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        # scratchpad_write was handled internally, not forwarded to tool_executor
        assert result.tool_loop_reply == "done"
        assert len(pad) == 1
        assert pad.read()[0].content == "user wants login change"
        assert pad.read()[0].entry_type == "note"

    def test_no_scratchpad_backward_compatible(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        tool_executor = _FakeToolExecutor([lambda *_: {"ok": True}])
        ai_proxy = _FakeAiProxy([
            {
                "content": "",
                "tool_calls": [{
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "dummy", "arguments": "{}"},
                }],
                "finish_reason": "tool_calls",
            },
            {"content": "done", "tool_calls": [], "finish_reason": "stop"},
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=tool_executor,
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            # No scratchpad parameter
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        assert result.tool_loop_reply == "done"
        # scratchpad_write should NOT be in tools list
        tools_sent = ai_proxy.calls[0]["tools"]
        tool_names = [t.get("function", {}).get("name") for t in tools_sent]
        assert "scratchpad_write" not in tool_names

    def test_scratchpad_write_tool_in_tools_list(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        pad = Scratchpad()
        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {"content": "just text", "tool_calls": [], "finish_reason": "stop"},
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            scratchpad=pad,
        )

        _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        # Verify scratchpad_write was included in tools list sent to AI
        tools_sent = ai_proxy.calls[0]["tools"]
        tool_names = [t.get("function", {}).get("name") for t in tools_sent]
        assert "scratchpad_write" in tool_names
        assert "dummy" in tool_names

    def test_execution_context_local_history_visible_next_round(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        pad = Scratchpad()
        execution_context = ExecutionContext(scratchpad=pad)
        execution_context.begin_subgraph("sg_fetch")
        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {
                "content": "",
                "tool_calls": [{
                    "id": "tc-1",
                    "type": "function",
                    "function": {"name": "dummy", "arguments": '{"target":"r-1"}'},
                }],
                "finish_reason": "tool_calls",
            },
            {"content": "done", "tool_calls": [], "finish_reason": "stop"},
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor([lambda *_: {"ok": True, "req_id": "r-1"}]),
            prompt_builder=_ContextAwarePromptBuilder(),
            stage_container_key="agent_main",
            scratchpad=pad,
        )

        _, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={
                "project_id": "p-1",
                "tool_results": [],
                "_current_subgraph": "sg_fetch",
                "_execution_context": execution_context,
            },
        ))

        assert result.tool_loop_reply == "done"
        assert len(ai_proxy.calls) == 2
        second_system_prompt = ai_proxy.calls[1]["messages"][0]["content"]
        assert "Subgraph Context" in second_system_prompt
        assert "tool_result" in second_system_prompt
        assert "req_id" in second_system_prompt


# ============================================================
# ToolLoopRunner complete_phase integration
# ============================================================


class TestToolLoopRunnerCompletePhaseIntegration:
    def test_complete_phase_tool_injected_when_enabled(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {"content": "just text", "tool_calls": [], "finish_reason": "stop"},
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            enable_complete_phase=True,
        )

        _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        tools_sent = ai_proxy.calls[0]["tools"]
        tool_names = [t.get("function", {}).get("name") for t in tools_sent]
        assert "complete_phase" in tool_names
        assert "dummy" in tool_names
        complete_phase_tool = next(
            t for t in tools_sent
            if t.get("function", {}).get("name") == "complete_phase"
        )
        complete_phase_props = (
            complete_phase_tool.get("function", {})
            .get("parameters", {})
            .get("properties", {})
        )
        assert "expand_topology" in complete_phase_props
        assert "target_template_graph_id" in complete_phase_props

    def test_complete_phase_tool_not_injected_when_disabled(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {"content": "just text", "tool_calls": [], "finish_reason": "stop"},
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            # enable_complete_phase defaults to False
        )

        _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        tools_sent = ai_proxy.calls[0]["tools"]
        tool_names = [t.get("function", {}).get("name") for t in tools_sent]
        assert "complete_phase" not in tool_names

    def test_complete_phase_triggers_loop_exit_with_phase_completed(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {
                "content": "",
                "tool_calls": [{
                    "id": "tc-cp-1",
                    "type": "function",
                    "function": {
                        "name": "complete_phase",
                        "arguments": '{"conclusion":"分析完成，需求明确"}',
                    },
                }],
                "finish_reason": "tool_calls",
            },
            # This second response should never be reached
            {"content": "should not reach here", "tool_calls": [], "finish_reason": "stop"},
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            enable_complete_phase=True,
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        assert result.phase_completed is True
        assert result.conclusion == "分析完成，需求明确"
        assert result.rounds == 1
        # AI proxy should only have been called once (loop exits after complete_phase)
        assert len(ai_proxy.calls) == 1

    def test_complete_phase_passes_route_key(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {
                "content": "",
                "tool_calls": [{
                    "id": "tc-cp-2",
                    "type": "function",
                    "function": {
                        "name": "complete_phase",
                        "arguments": '{"conclusion":"needs review","route_key":"review_required"}',
                    },
                }],
                "finish_reason": "tool_calls",
            },
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            enable_complete_phase=True,
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        assert result.phase_completed is True
        assert result.route_key == "review_required"
        assert result.conclusion == "needs review"

    def test_complete_phase_passes_judge_decision_fields(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {
                "content": "",
                "tool_calls": [{
                    "id": "tc-cp-judge",
                    "type": "function",
                    "function": {
                        "name": "complete_phase",
                        "arguments": (
                            '{"conclusion":"需要进入冲突检测流程",'
                            '"expand_topology":true,'
                            '"target_template_graph_id":"tpl-conflict"}'
                        ),
                    },
                }],
                "finish_reason": "tool_calls",
            },
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            enable_complete_phase=True,
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        assert result.phase_completed is True
        assert result.expand_topology is True
        assert result.target_template_graph_id == "tpl-conflict"
        assert result.conclusion == "需要进入冲突检测流程"

    def test_complete_phase_auto_appends_scratchpad_stage_output(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        pad = Scratchpad()
        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {
                "content": "",
                "tool_calls": [{
                    "id": "tc-cp-3",
                    "type": "function",
                    "function": {
                        "name": "complete_phase",
                        "arguments": '{"conclusion":"all requirements gathered"}',
                    },
                }],
                "finish_reason": "tool_calls",
            },
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            scratchpad=pad,
            enable_complete_phase=True,
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        assert result.phase_completed is True
        # Scratchpad should have a stage_output entry
        stage_outputs = pad.read(filter_type="stage_output")
        assert len(stage_outputs) == 1
        assert stage_outputs[0].content == "all requirements gathered"

    def test_complete_phase_without_scratchpad_still_works(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {
                "content": "",
                "tool_calls": [{
                    "id": "tc-cp-4",
                    "type": "function",
                    "function": {
                        "name": "complete_phase",
                        "arguments": '{"conclusion":"done without scratchpad"}',
                    },
                }],
                "finish_reason": "tool_calls",
            },
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            # No scratchpad, but complete_phase enabled
            enable_complete_phase=True,
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        assert result.phase_completed is True
        assert result.conclusion == "done without scratchpad"

    def test_backward_compat_text_completion_still_works(self):
        from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
        from backend_business.services.agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig

        graph_service = _FakeGraphService()
        recorder = RuntimeGraphRecorder(
            execution_graph_service=graph_service,
            container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
            project_id="p-1", user_id="u-1", session_id="s-1", user_message="hello",
        )

        ai_proxy = _FakeAiProxy([
            {"content": "task done naturally", "tool_calls": [], "finish_reason": "stop"},
        ])

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=_FakeToolExecutor(),
            prompt_builder=_FakePromptBuilder(),
            stage_container_key="agent_main",
            enable_complete_phase=True,  # enabled but model doesn't call it
        )

        events, result = _run_to_completion(runner.run(
            recorder=recorder, user_id="u-1", user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ))

        # Natural text completion should still work
        assert result.tool_loop_reply == "task done naturally"
        assert result.phase_completed is False
        assert result.route_key is None
        assert result.conclusion is None
