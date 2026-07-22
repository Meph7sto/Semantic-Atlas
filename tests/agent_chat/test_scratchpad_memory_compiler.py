"""Regression tests for bounded, selective Scratchpad prompt memory."""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.runtime.memory_compiler import (  # noqa: E402
    PromptMemoryPolicy,
    estimate_prompt_tokens,
)
from backend_business.services.agent.runtime.scratchpad import Scratchpad  # noqa: E402
from backend_business.services.agent.runtime.scratchpad_service import (  # noqa: E402
    ScratchpadService,
)


def test_prompt_compilation_enforces_entry_and_token_budgets_without_mutating_raw_history():
    pad = Scratchpad().for_container("requirement_agent")
    for index in range(30):
        pad.write(
            "note",
            f"payment checkout decision {index}: " + ("detail " * 30),
            source_subgraph=f"analysis_{index}",
            task_refs=["payment-checkout"],
        )
    raw_before = pad.snapshot_all()
    policy = PromptMemoryPolicy(
        max_tokens=180,
        max_entries=3,
        max_entry_tokens=45,
        summary_tokens=45,
    )

    compilation = pad.compile_for_prompt(
        task="payment checkout",
        policy=policy,
    )

    assert compilation.selected_entry_count <= 3
    assert compilation.omitted_entry_count > 0
    assert compilation.was_distilled is True
    assert compilation.estimated_tokens <= policy.max_tokens
    assert estimate_prompt_tokens(compilation.text) <= policy.max_tokens
    assert f"estimated_tokens={compilation.estimated_tokens}/{policy.max_tokens}" in (
        compilation.text
    )
    assert "Distilled history" in compilation.text
    assert pad.snapshot_all() == raw_before
    assert len(pad.snapshot_all()) == 30


def test_prompt_compilation_is_container_scoped_and_task_selective():
    root = Scratchpad()
    requirement_pad = root.for_container("requirement_agent")
    conflict_pad = root.for_container("conflict_detection")
    requirement_pad.write(
        "note",
        "login authentication uses passkeys",
        source_subgraph="login_analysis",
    )
    requirement_pad.write(
        "note",
        "payment checkout uses card authorization",
        source_subgraph="payment_analysis",
    )
    conflict_pad.write(
        "note",
        "login authentication secret from another container",
        source_subgraph="conflict_analysis",
    )

    compilation = requirement_pad.compile_for_prompt(task="login authentication")

    assert "login authentication uses passkeys" in compilation.text
    assert "payment checkout uses card authorization" not in compilation.text
    assert "secret from another container" not in compilation.text
    assert compilation.raw_entry_count == 2
    assert compilation.eligible_entry_count == 1
    assert compilation.task_filtered_entry_count == 1


def test_prompt_compilation_excludes_unrelated_recent_and_important_entries_but_keeps_global_invariants():
    pad = Scratchpad().for_container("conductor")
    pad.write("note", "payment checkout authorization", importance=0.7)
    pad.append_stage_output(
        "unrelated_recent_stage",
        "weather forecast humidity",
        importance=1.0,
    )
    pad.write(
        "note",
        "baseball standings inning",
        importance=1.0,
        task_refs=["sports"],
    )
    pad.write(
        "note",
        "all actions require explicit approval",
        importance=1.0,
        task_refs=["global-invariant"],
    )

    compilation = pad.compile_for_prompt(task="payment checkout")

    assert "payment checkout authorization" in compilation.text
    assert "all actions require explicit approval" in compilation.text
    assert "weather forecast humidity" not in compilation.text
    assert "baseball standings inning" not in compilation.text
    assert compilation.task_filtered_entry_count == 2


def test_prompt_compilation_ranking_combines_importance_and_recency():
    pad = Scratchpad().for_container("conductor")
    pad.write(
        "note",
        "release decision critical baseline",
        importance=1.0,
    )
    for index in range(5):
        pad.write(
            "note",
            f"release decision routine update {index}",
            importance=0.65,
        )
    policy = PromptMemoryPolicy(
        max_tokens=300,
        max_entries=1,
        max_entry_tokens=80,
        summary_tokens=50,
        task_weight=0.3,
        importance_weight=0.5,
        recency_weight=0.2,
    )

    compilation = pad.compile_for_prompt(task="release decision", policy=policy)

    assert "critical baseline" in compilation.text
    assert compilation.selected_entry_ids == (pad.read()[0].entry_id,)


def test_cross_round_restore_compiles_a_bounded_view_and_preserves_entry_ids():
    previous = Scratchpad().for_container("conductor")
    for index in range(20):
        previous.write("note", f"payment history {index}")
    previous.write(
        "note",
        "login focus REQ-LOGIN",
        importance=0.95,
        task_refs=["REQ-LOGIN"],
    )
    raw_snapshot = previous.snapshot_all()
    inherited = Scratchpad.from_store_snapshot(raw_snapshot).for_container("conductor")

    compilation = inherited.compile_for_prompt(
        task="continue REQ-LOGIN",
        policy=PromptMemoryPolicy(max_tokens=160, max_entries=2),
    )

    assert "login focus REQ-LOGIN" in compilation.text
    assert "payment history" not in compilation.text
    assert compilation.selected_entry_count <= 2
    assert len(inherited.snapshot_all()) == 21
    assert [item["entry_id"] for item in inherited.snapshot_all()] == [
        item["entry_id"] for item in raw_snapshot
    ]


def test_legacy_snapshot_gains_stable_audit_fields_and_keeps_raw_content():
    snapshot = [
        {
            "entry_type": "note",
            "content": "legacy audit history",
            "source_subgraph": "legacy",
            "container_key": "conductor",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]

    first = Scratchpad.from_store_snapshot(snapshot).for_container("conductor")
    second = Scratchpad.from_store_snapshot(snapshot).for_container("conductor")

    assert first.read()[0].entry_id.startswith("legacy-")
    assert first.read()[0].entry_id == second.read()[0].entry_id
    assert first.snapshot()[0]["content"] == "legacy audit history"
    assert first.snapshot()[0]["importance"] == 0.65


class _FakeExecutionGraphService:
    def __init__(self) -> None:
        self.graph = {"graph_id": "g-1", "meta_json": {}}
        self.graphs = {"g-1": self.graph}
        self.container_states: dict[tuple[str, str], dict] = {}

    def get_execution_graph(self, graph_id: str):
        graph = self.graphs.get(graph_id)
        return dict(graph) if graph else None

    def list_container_states(self, graph_id: str):
        return [
            dict(row)
            for (stored_graph_id, _), row in self.container_states.items()
            if stored_graph_id == graph_id
        ]

    def upsert_container_state(
        self,
        *,
        graph_id: str,
        container_key: str,
        state_json: dict,
        updated_by: str,
    ):
        row = {
            "graph_id": graph_id,
            "container_key": container_key,
            "state_json": state_json,
            "updated_by": updated_by,
        }
        self.container_states[(graph_id, container_key)] = row
        return dict(row)

    def patch_graph_meta(
        self,
        graph_id: str,
        meta_patch: dict,
        *,
        updated_by: str,
    ):
        graph = self.graphs[graph_id]
        graph["meta_json"] = {
            **graph.get("meta_json", {}),
            **meta_patch,
        }
        graph["updated_by"] = updated_by
        return dict(graph)


def test_scratchpad_service_persists_raw_history_and_compilation_observability():
    graph_service = _FakeExecutionGraphService()
    scratchpad_service = ScratchpadService(execution_graph_service=graph_service)
    pad = Scratchpad().for_container("conductor")
    for index in range(10):
        pad.write("note", f"login decision {index}")
    compilation = pad.compile_for_prompt(
        task="login decision",
        policy=PromptMemoryPolicy(max_tokens=140, max_entries=2),
    )

    scratchpad_service.save("g-1", pad, updated_by="tester")

    raw_state = graph_service.container_states[("g-1", "conductor")]["state_json"][
        "scratchpad_snapshot"
    ]
    meta = graph_service.graph["meta_json"]
    assert len(raw_state) == 10
    assert len(meta["scratchpad_snapshot"]) == 10
    assert meta["scratchpad_memory_compilation"]["estimated_tokens"] <= 140
    assert meta["scratchpad_memory_compilation"]["raw_entry_count"] == 10
    assert meta["scratchpad_memory_compilation"]["by_container"]["conductor"]["max_tokens"] == 140
    assert meta["scratchpad_memory_compilation"]["raw_history_digest"] == (
        compilation.raw_history_digest
    )


def test_scratchpad_service_restores_bounded_per_observation_compilation_history():
    graph_service = _FakeExecutionGraphService()
    scratchpad_service = ScratchpadService(execution_graph_service=graph_service)
    pad = Scratchpad().for_container("conductor")
    pad.write("note", "login authentication decision")
    pad.compile_for_prompt(
        task="login authentication",
        observation_key="subgraph:conductor:intake",
    )
    pad.compile_for_prompt(
        task="login authentication",
        observation_key="subgraph:conductor:reply",
    )

    scratchpad_service.save("g-1", pad, updated_by="tester")
    restored = scratchpad_service.load("g-1")

    history = restored.compilation_history()
    assert [item["observation_key"] for item in history] == [
        "subgraph:conductor:intake",
        "subgraph:conductor:reply",
    ]
    assert graph_service.graph["meta_json"]["scratchpad_memory_compilation_history"] == history


def test_cross_round_inheritance_is_bounded_relevant_and_points_to_raw_prior_trace():
    graph_service = _FakeExecutionGraphService()
    graph_service.graphs["g-prev"] = {"graph_id": "g-prev", "meta_json": {}}
    graph_service.graphs["g-next"] = {"graph_id": "g-next", "meta_json": {}}
    scratchpad_service = ScratchpadService(execution_graph_service=graph_service)
    previous = Scratchpad().for_container("conductor")
    for index in range(20):
        previous.append_stage_output(
            f"weather_{index}",
            f"unrelated weather history {index}",
            importance=1.0,
            task_refs=["flow-context"],
        )
    previous.write(
        "note",
        "payment checkout decision " + ("critical detail " * 80),
        importance=0.9,
        task_refs=["payment-checkout"],
    )
    previous.write(
        "note",
        "all writes require approval",
        importance=1.0,
        task_refs=["global-invariant"],
    )
    scratchpad_service.save("g-prev", previous, updated_by="tester")
    raw_prior = scratchpad_service.load("g-prev").snapshot_all()
    policy = PromptMemoryPolicy(
        max_tokens=300,
        max_entries=2,
        max_entry_tokens=80,
        summary_tokens=50,
    )

    lineage = scratchpad_service.inherit_relevant_snapshot(
        "g-next",
        previous_graph_id="g-prev",
        task="payment checkout",
        updated_by="tester",
        policy=policy,
    )

    inherited = scratchpad_service.load("g-next").snapshot_all()
    inherited_text = str(inherited)
    assert len(inherited) <= policy.max_entries
    assert "payment checkout decision" in inherited_text
    assert "all writes require approval" in inherited_text
    assert "unrelated weather history" not in inherited_text
    assert all(item["readonly"] is True for item in inherited)
    assert all(
        estimate_prompt_tokens(item["content"]["excerpt"]) <= policy.max_entry_tokens - 48
        for item in inherited
    )
    assert scratchpad_service.load("g-prev").snapshot_all() == raw_prior
    assert lineage["previous_graph_id"] == "g-prev"
    assert lineage["raw_entry_count"] == len(raw_prior)
    assert lineage["inherited_entry_count"] == len(inherited)
    assert graph_service.graphs["g-next"]["meta_json"]["scratchpad_memory_lineage"] == lineage
    assert (
        scratchpad_service.load("g-next").compilation_history()[0]["observation_key"]
        == "cross_round_inheritance:g-prev"
    )


def test_cross_round_inheritance_recovers_topic_omitted_by_intervening_turn():
    graph_service = _FakeExecutionGraphService()
    for graph_id in ("g-topic-a", "g-topic-b", "g-topic-a-return"):
        graph_service.graphs[graph_id] = {"graph_id": graph_id, "meta_json": {}}
    scratchpad_service = ScratchpadService(execution_graph_service=graph_service)
    policy = PromptMemoryPolicy(
        max_tokens=240,
        max_entries=3,
        max_entry_tokens=72,
        summary_tokens=40,
    )

    first_turn = Scratchpad().for_container("conductor")
    first_turn.write(
        "note",
        "payment checkout uses authorization hold PAYMENT-42",
        importance=0.9,
        task_refs=["payment-checkout"],
    )
    first_turn.write(
        "note",
        "all writes require explicit approval",
        importance=1.0,
        task_refs=["global-invariant"],
    )
    scratchpad_service.save("g-topic-a", first_turn, updated_by="tester")
    first_turn_raw = scratchpad_service.load("g-topic-a").snapshot_all()

    scratchpad_service.inherit_relevant_snapshot(
        "g-topic-b",
        previous_graph_id="g-topic-a",
        task="weather forecast",
        updated_by="tester",
        policy=policy,
    )
    second_turn = scratchpad_service.load("g-topic-b")
    assert "PAYMENT-42" not in str(second_turn.snapshot_all())
    second_turn.write(
        "note",
        "weather forecast expects rain WEATHER-7",
        task_refs=["weather-forecast"],
    )
    scratchpad_service.save("g-topic-b", second_turn, updated_by="tester")

    lineage = scratchpad_service.inherit_relevant_snapshot(
        "g-topic-a-return",
        previous_graph_id="g-topic-b",
        task="resume payment checkout",
        updated_by="tester",
        policy=policy,
    )

    returned_snapshot = scratchpad_service.load("g-topic-a-return").snapshot_all()
    returned_text = str(returned_snapshot)
    assert "PAYMENT-42" in returned_text
    assert "WEATHER-7" not in returned_text
    assert returned_text.count("explicit approval") == 1
    assert len(returned_snapshot) <= policy.max_entries
    assert lineage["inherited_estimated_tokens"] <= policy.max_tokens
    assert lineage["lineage_graph_ids"] == ["g-topic-b", "g-topic-a"]
    assert lineage["scanned_entry_count"] > lineage["deduplicated_entry_count"]
    assert {item["source_graph_id"] for item in lineage["selected_entry_origins"]} == {"g-topic-a"}
    assert scratchpad_service.load("g-topic-a").snapshot_all() == first_turn_raw


def test_cross_round_lineage_traversal_stops_on_cycles():
    graph_service = _FakeExecutionGraphService()
    for graph_id in ("g-cycle-a", "g-cycle-b", "g-cycle-next"):
        graph_service.graphs[graph_id] = {"graph_id": graph_id, "meta_json": {}}
    scratchpad_service = ScratchpadService(execution_graph_service=graph_service)

    first = Scratchpad().for_container("conductor")
    first.write("note", "cycle-safe payment decision", task_refs=["payment"])
    scratchpad_service.save("g-cycle-a", first, updated_by="tester")
    second = Scratchpad().for_container("conductor")
    second.write("note", "unrelated weather decision", task_refs=["weather"])
    scratchpad_service.save("g-cycle-b", second, updated_by="tester")
    graph_service.graphs["g-cycle-a"]["meta_json"][ScratchpadService.LINEAGE_KEY] = {
        "previous_graph_id": "g-cycle-b"
    }
    graph_service.graphs["g-cycle-b"]["meta_json"][ScratchpadService.LINEAGE_KEY] = {
        "previous_graph_id": "g-cycle-a"
    }

    lineage = scratchpad_service.inherit_relevant_snapshot(
        "g-cycle-next",
        previous_graph_id="g-cycle-b",
        task="payment",
        updated_by="tester",
    )

    assert lineage["lineage_cycle_detected"] is True
    assert lineage["lineage_graph_ids"] == ["g-cycle-b", "g-cycle-a"]
    assert len(lineage["lineage_graph_ids"]) <= ScratchpadService._MAX_LINEAGE_DEPTH
    assert "cycle-safe payment decision" in str(
        scratchpad_service.load("g-cycle-next").snapshot_all()
    )
