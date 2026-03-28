# Requirement Classification Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an additive `requirement_classification_agent` that fully mirrors the repository's existing agent shape, provides standalone classification chat/runtime-graph flows, and can be delegated by `session_controller` without introducing destructive refactors.

**Architecture:** Add a fourth agent package that follows the same `service + prompt_builder + tool_loop_runner + runtime_graph_recorder` pattern as the existing three agents. Reuse current `ToolLoopRunner`, `RequirementsManageService`, `ai_proxy`, and frontend execution-graph components; prefer new files and narrow registrations over modifying existing behavior, and keep the new agent read-only in its first version.

**Tech Stack:** Python, FastAPI, existing agent runtime graph services, `ai_proxy`, Vue 3, Vite, Pytest

---

## Implementation Rules

- Prefer additive changes over modifying old logic.
- Only touch existing files at stable extension points such as router registration, exports, route tables, and session-controller delegation hooks.
- Do not change existing `Classification.vue` offline behavior.
- Do not introduce a new runtime model, graph mode, or write path.
- Keep tests targeted and deterministic; use fakes patterned after the current agent tests.

## File Map

### New backend files

- `backend_business/services/agent/tools/requirement_classification_tools.py`
  Responsibility: define and execute `list_requirements`, `search_requirements`, `get_requirement_detail`, and `classify_requirement`.
- `backend_business/services/agent/agents/requirement_classification_agent/__init__.py`
  Responsibility: export service singleton and public package symbols.
- `backend_business/services/agent/agents/requirement_classification_agent/prompt_builder.py`
  Responsibility: build system prompt, user payload, and round summaries for the new agent.
- `backend_business/services/agent/agents/requirement_classification_agent/tool_loop_runner.py`
  Responsibility: adapt the generic `ToolLoopRunner` to the classification agent context.
- `backend_business/services/agent/agents/requirement_classification_agent/runtime_graph_recorder.py`
  Responsibility: define runtime graph container layout and graph metadata defaults.
- `backend_business/services/agent/agents/requirement_classification_agent/service.py`
  Responsibility: session lifecycle, SSE orchestration, graph lifecycle, and inline tool-loop execution.
- `backend_business/api/routers/requirement_classification_agent_chat.py`
  Responsibility: expose standalone session/message/graph endpoints for the new agent.

### New frontend files

- `frontend/src/api/requirementClassificationAgentChat.js`
  Responsibility: frontend client wrapper for the new agent router.
- `frontend/src/views/alpha/RequirementClassificationAgentChat.vue`
  Responsibility: standalone Alpha debugging page reusing the existing message + execution-graph UX.

### New test files

- `tests/agent_chat/test_requirement_classification_tools.py`
  Responsibility: unit coverage for tool schema, validation, and classification result normalization.
- `tests/agent_chat/test_requirement_classification_agent_chat_service.py`
  Responsibility: unit coverage for service orchestration and runtime graph behavior.
- `tests/agent_chat/test_fastapi_requirement_classification_agent_chat_contract.py`
  Responsibility: FastAPI contract coverage for the new router.

### Existing backend files to modify

- `backend_business/services/agent/tools/__init__.py`
  Responsibility: export the new tools class.
- `backend_business/services/agent/agents/session_controller/tools.py`
  Responsibility: add `invoke_requirement_classification_agent` with inline parent-graph recording.
- `backend_business/services/agent/agents/session_controller/prompt_builder.py`
  Responsibility: mention the new delegation tool in system instructions.
- `backend_business/services/agent/agents/session_controller/runtime_graph_recorder.py`
  Responsibility: add a `requirement_classification_agent` container to the parent graph.
- `backend_business/main.py`
  Responsibility: import and register the new FastAPI router.
- `backend_business/api/routers/__init__.py`
  Responsibility: keep router package exports aligned with the new router module.

### Existing frontend files to modify

- `frontend/src/router/index.js`
  Responsibility: add a route for the new Alpha page.
- `frontend/src/components/alpha/AlphaSidebar.vue`
  Responsibility: add a visible navigation entry for the new page.
- `frontend/src/api/index.js`
  Responsibility: re-export the new frontend API client.

### Existing tests to modify

- `tests/agent_chat/test_session_controller_tools.py`
  Responsibility: add delegation assertions for the new child agent path.

## Suggested Commit Boundaries

1. Tools only
2. Agent package service only
3. Router wiring only
4. Session-controller delegation only
5. Frontend only
6. Final verification fixes only

### Task 1: Requirement Classification Tools

**Files:**
- Create: `backend_business/services/agent/tools/requirement_classification_tools.py`
- Modify: `backend_business/services/agent/tools/__init__.py`
- Test: `tests/agent_chat/test_requirement_classification_tools.py`

- [x] **Step 1: Write the failing tool tests**

```python
def test_get_tools_list_contains_expected_schemas():
    tools = RequirementClassificationTools.get_tools_list()
    names = [item["function"]["name"] for item in tools]
    assert names == [
        "list_requirements",
        "search_requirements",
        "get_requirement_detail",
        "classify_requirement",
    ]


def test_execute_classify_requirement_combines_structural_and_model_results():
    tools, _, classifier_calls, llm_calls = _make_tools()
    result = tools.execute("classify_requirement", {"requirement_id": "r-1"}, {"project_id": "p-1"})
    assert result["requirement_id"] == "r-1"
    assert result["level"] == "L2"
    assert result["requirement_nature"] == "functional"
    assert result["priority_suggestion"] == "P2"
    assert result["raw_classifier_label"] == "功能性需求"
    assert classifier_calls == ["系统应支持批量导入需求数据"]
    assert len(llm_calls) == 1
```

- [x] **Step 2: Run the tool tests to verify they fail**

Run: `pytest tests/agent_chat/test_requirement_classification_tools.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `RequirementClassificationTools`

- [x] **Step 3: Write the minimal tool implementation**

```python
class RequirementClassificationTools:
    @staticmethod
    def get_tools_list() -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": "list_requirements", ...}},
            {"type": "function", "function": {"name": "search_requirements", ...}},
            {"type": "function", "function": {"name": "get_requirement_detail", ...}},
            {"type": "function", "function": {"name": "classify_requirement", ...}},
        ]

    def _execute_classify_requirement(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        requirement = self._resolve_project_requirement(...)
        base_level = self._infer_level_from_fields(requirement)
        raw_classifier_label = self._classify_requirement_nature(requirement)
        llm_result = self._complete_dimensions_with_llm(requirement, base_level, raw_classifier_label)
        return self._normalize_classification_result(requirement, llm_result, raw_classifier_label)
```

Implementation notes:
- Read from `RequirementsManageService` only.
- Keep the tool read-only.
- Prefer `source_level` and `requirement_type` before LLM inference.
- Use the existing classification model as a base nature signal, not as the sole output.

- [x] **Step 4: Run the tool tests to verify they pass**

Run: `pytest tests/agent_chat/test_requirement_classification_tools.py -v`
Expected: PASS for schema, validation, and normalization cases

- [x] **Step 5: Commit**

```bash
git add tests/agent_chat/test_requirement_classification_tools.py \
  backend_business/services/agent/tools/requirement_classification_tools.py \
  backend_business/services/agent/tools/__init__.py
superspec commit --summary "Add requirement classification agent tools." --next $'Build the standalone classification agent service package.\nKeep changes additive and read-only.' --details $'Added tool schemas and execution helpers for requirement classification.\nCovered structural level inference, base classifier reuse, and result normalization with unit tests.'
```

### Task 2: Standalone Classification Agent Service Package

**Files:**
- Create: `backend_business/services/agent/agents/requirement_classification_agent/__init__.py`
- Create: `backend_business/services/agent/agents/requirement_classification_agent/prompt_builder.py`
- Create: `backend_business/services/agent/agents/requirement_classification_agent/tool_loop_runner.py`
- Create: `backend_business/services/agent/agents/requirement_classification_agent/runtime_graph_recorder.py`
- Create: `backend_business/services/agent/agents/requirement_classification_agent/service.py`
- Test: `tests/agent_chat/test_requirement_classification_agent_chat_service.py`

- [x] **Step 1: Write the failing service tests**

```python
def test_stream_classification_agent_reply_emits_graph_and_result_events():
    service = _make_service()
    events = list(
        service.stream_requirement_classification_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="请分类 REQ-1",
            requirement_id="REQ-1",
        )
    )
    event_names = [event["event"] for event in events]
    assert "graph" in event_names
    assert event_names[-1] == "result"
    assert events[-1]["data"]["classification_result"]["requirement_id"] == "REQ-1"


def test_run_inline_tool_loop_returns_classification_summary():
    service = _make_service()
    result = service.run_inline_tool_loop(
        recorder=_FakeRecorder(),
        user_id="u-1",
        user_message="分类 REQ-1",
        project_id="p-1",
        requirement_id="REQ-1",
    )
    assert result["status"] == "success"
    assert result["resolved_requirement_id"] == "REQ-1"
    assert result["classification_result"]["level"] == "L2"
```

- [x] **Step 2: Run the service tests to verify they fail**

Run: `pytest tests/agent_chat/test_requirement_classification_agent_chat_service.py -v`
Expected: FAIL because the package and service do not exist yet

- [x] **Step 3: Write the minimal service package**

```python
class RequirementClassificationAgentService:
    AGENT_TYPE = "requirement_classification_agent"
    MAX_TOOL_CALL_ROUNDS = 6

    def stream_requirement_classification_agent_reply(...):
        recorder = RequirementClassificationGraphRecorder(...)
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}
        result = yield from self._stream_tool_loop(...)
        yield {"event": "result", "data": result}

    def run_inline_tool_loop(...):
        gen = self.stream_inline_tool_loop(...)
        ...
        return {
            "status": "success",
            "tool_loop_reply": result.get("tool_loop_reply", ""),
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "classification_result": context.get("classification_result"),
        }
```

Implementation notes:
- Copy session, graph-chain, and message lifecycle from `ConflictDetectionAgentService` and `RequirementAgentChatService`.
- Keep graph containers minimal: `human_input`, `conductor`, `requirement_classification_agent`.
- Persist `classification_result` into graph meta for graph-chain replay.

- [x] **Step 4: Run the service tests to verify they pass**

Run: `pytest tests/agent_chat/test_requirement_classification_agent_chat_service.py -v`
Expected: PASS for graph lifecycle, SSE, and inline execution cases

- [x] **Step 5: Commit**

```bash
git add tests/agent_chat/test_requirement_classification_agent_chat_service.py \
  backend_business/services/agent/agents/requirement_classification_agent/__init__.py \
  backend_business/services/agent/agents/requirement_classification_agent/prompt_builder.py \
  backend_business/services/agent/agents/requirement_classification_agent/tool_loop_runner.py \
  backend_business/services/agent/agents/requirement_classification_agent/runtime_graph_recorder.py \
  backend_business/services/agent/agents/requirement_classification_agent/service.py
superspec commit --summary "Add the standalone requirement classification agent service." --next $'Expose the classification agent through a FastAPI router.\nKeep API shape parallel to the existing agent chat routers.' --details $'Added the classification agent package, runtime graph recorder, prompt builder, tool loop runner, and service tests.\nMirrored the current agent lifecycle without changing existing agent behavior.'
```

### Task 3: FastAPI Router and Backend Registration

**Files:**
- Create: `backend_business/api/routers/requirement_classification_agent_chat.py`
- Modify: `backend_business/main.py`
- Modify: `backend_business/api/routers/__init__.py`
- Test: `tests/agent_chat/test_fastapi_requirement_classification_agent_chat_contract.py`

- [x] **Step 1: Write the failing FastAPI contract tests**

```python
async def test_stream_message_passes_requirement_id(monkeypatch):
    stub = _StubClassificationAgentService()
    monkeypatch.setattr(requirement_classification_agent_chat, "requirement_classification_agent_service", stub)
    monkeypatch.setattr(requirement_classification_agent_chat, "_require_project_access", lambda project_id, current_user: None)
    async with async_client(_build_app()) as client:
        response = await client.post(
            "/api/v2/requirement-classification-agent/sessions/sess-1/messages/stream",
            json={"project_id": "p-1", "message": "请分类", "requirement_id": "REQ-1"},
        )
    assert response.status_code == 200
    assert stub.last_stream_args["requirement_id"] == "REQ-1"
```

- [x] **Step 2: Run the contract tests to verify they fail**

Run: `pytest tests/agent_chat/test_fastapi_requirement_classification_agent_chat_contract.py -v`
Expected: FAIL with missing router module or missing route registration

- [x] **Step 3: Implement the router and app registration**

```python
router = APIRouter(
    prefix="/api/v2/requirement-classification-agent",
    tags=["requirement-classification-agent"],
)

@router.post("/sessions/{session_id}/messages/stream")
def stream_message(...):
    for event in requirement_classification_agent_service.stream_requirement_classification_agent_reply(...):
        yield _sse_event(event["event"], event.get("data", {}))
```

Implementation notes:
- Mirror `agent_chat.py` request flow.
- Keep auth and project-access checks identical to current agent routers.
- Add `app.include_router(requirement_classification_agent_chat.router)` in `backend_business/main.py`.

- [x] **Step 4: Run the contract tests to verify they pass**

Run: `pytest tests/agent_chat/test_fastapi_requirement_classification_agent_chat_contract.py -v`
Expected: PASS for session/message/graph route shapes

- [x] **Step 5: Commit**

```bash
git add tests/agent_chat/test_fastapi_requirement_classification_agent_chat_contract.py \
  backend_business/api/routers/requirement_classification_agent_chat.py \
  backend_business/api/routers/__init__.py \
  backend_business/main.py
superspec commit --summary "Expose the requirement classification agent router." --next $'Integrate the new agent into the session controller delegation path.\nOnly touch existing files at stable extension points.' --details $'Added the standalone FastAPI router for requirement classification agent sessions, messages, and graphs.\nRegistered the router without altering existing route behavior.'
```

### Task 4: Session Controller Delegation

**Files:**
- Modify: `backend_business/services/agent/agents/session_controller/tools.py`
- Modify: `backend_business/services/agent/agents/session_controller/prompt_builder.py`
- Modify: `backend_business/services/agent/agents/session_controller/runtime_graph_recorder.py`
- Modify: `tests/agent_chat/test_session_controller_tools.py`

- [x] **Step 1: Write the failing session-controller tests**

```python
def test_invoke_requirement_classification_agent_records_expanded_nodes():
    tools = _make_tools_with_classification_agent()
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }
    result = tools.execute(
        "invoke_requirement_classification_agent",
        {"task_description": "分类 REQ-1", "requirement_id": "REQ-1"},
        context,
    )
    assert result["status"] == "success"
    assert context["dispatched_agents"] == ["requirement_classification_agent"]
    assert any("classification_agent_1_start" in item["node_key"] for item in recorder.started)
```

- [x] **Step 2: Run the session-controller tests to verify they fail**

Run: `pytest tests/agent_chat/test_session_controller_tools.py -v`
Expected: FAIL because the new tool and container do not exist

- [x] **Step 3: Implement minimal delegation support**

```python
{
    "type": "function",
    "function": {
        "name": "invoke_requirement_classification_agent",
        "description": "将需求分类任务委托给需求分类 Agent 执行。",
        ...
    },
}

class SessionControllerGraphRecorder(RuntimeGraphRecorder):
    _CONTAINERS = (
        ("human_input", "Human Input", "human"),
        ("conductor", "Session Controller", "agent"),
        ("requirement_agent", "Requirement Agent", "agent"),
        ("conflict_detection", "Conflict Detection Agent", "agent"),
        ("requirement_classification_agent", "Requirement Classification Agent", "agent"),
    )
```

Implementation notes:
- Follow the same start node -> inline tool loop -> end node -> return edge flow as the existing two invoke paths.
- Keep names explicit and additive.
- Update the prompt builder so the controller knows classification must go through the new invoke tool.

- [x] **Step 4: Run the session-controller tests to verify they pass**

Run: `pytest tests/agent_chat/test_session_controller_tools.py -v`
Expected: PASS for all existing tests plus the new classification delegation path

- [x] **Step 5: Commit**

```bash
git add tests/agent_chat/test_session_controller_tools.py \
  backend_business/services/agent/agents/session_controller/tools.py \
  backend_business/services/agent/agents/session_controller/prompt_builder.py \
  backend_business/services/agent/agents/session_controller/runtime_graph_recorder.py
superspec commit --summary "Add session controller delegation for requirement classification." --next $'Build the frontend page and API wrapper for the new agent.\nAvoid changing the old offline classification page.' --details $'Added a new session-controller delegation tool and parent-graph container for the requirement classification agent.\nKept the inline call/start/end/return pattern consistent with current code.'
```

### Task 5: Frontend Route, API, and Alpha Page

**Files:**
- Create: `frontend/src/api/requirementClassificationAgentChat.js`
- Create: `frontend/src/views/alpha/RequirementClassificationAgentChat.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/components/alpha/AlphaSidebar.vue`
- Modify: `frontend/src/api/index.js`

- [x] **Step 1: Add the route and imports first, then verify the frontend build fails**

Planned change:

```javascript
import RequirementClassificationAgentChat from '../views/alpha/RequirementClassificationAgentChat.vue'

{
  path: 'requirement-classification-agent',
  name: 'requirement-classification-agent',
  component: RequirementClassificationAgentChat
}
```

Run: `npm run build`
Workdir: `frontend`
Expected: FAIL with missing module errors for the new page or API file

- [x] **Step 2: Implement the minimal frontend API client**

```javascript
export const requirementClassificationAgentChatApi = {
  async listSessions(projectId, limit = 100) { ... },
  async createOrGetSession(projectId) { ... },
  async createSession(projectId, title) { ... },
  async deleteSession(sessionId) { ... },
  async listMessages(sessionId, limit = 100) { ... },
  async getSessionGraphChain(sessionId) { ... },
  async getGraphDetail(graphId) { ... },
  async streamMessage({ sessionId, projectId, message, requirementId }) { ... },
}
```

- [x] **Step 3: Implement the minimal Alpha page by copying the existing agent-page pattern**

```vue
<script setup>
import { requirementClassificationAgentChatApi } from '@/api/requirementClassificationAgentChat'
import ExecutionGraphCanvas from '@/components/alpha/ExecutionGraphCanvas.vue'
import NodeDetailPanel from '@/components/alpha/NodeDetailPanel.vue'

const latestClassificationResult = computed(() => {
  return [...flattenedToolResults.value]
    .reverse()
    .find((entry) => entry.tool_name === 'classify_requirement' && !entry.result?.is_error)?.result || null
})
</script>
```

Implementation notes:
- Start from `RequirementAgentChat.vue` or `ConflictAgentChat.vue`, not `Classification.vue`.
- Keep the new page independent from the old offline classification page.
- Surface a concise classification summary card instead of inventing a brand-new layout system.

- [x] **Step 4: Run the frontend build to verify it passes**

Run: `npm run build`
Workdir: `frontend`
Expected: PASS with the new route and page included

- [x] **Step 5: Commit**

```bash
git add frontend/src/api/requirementClassificationAgentChat.js \
  frontend/src/views/alpha/RequirementClassificationAgentChat.vue \
  frontend/src/router/index.js \
  frontend/src/components/alpha/AlphaSidebar.vue \
  frontend/src/api/index.js
superspec commit --summary "Add the requirement classification agent frontend page." --next $'Run focused backend and frontend verification for the full feature.\nFix only additive integration issues if found.' --details $'Added a standalone Alpha page, frontend API wrapper, route, and sidebar entry for the requirement classification agent.\nReused the existing agent debugging UI pattern instead of changing the offline classification page.'
```

### Task 6: Focused Verification and Additive Fixes

**Files:**
- Modify: `backend_business/services/agent/tools/requirement_classification_tools.py` (only if verification exposes gaps)
- Modify: `backend_business/services/agent/agents/requirement_classification_agent/service.py` (only if verification exposes gaps)
- Modify: `backend_business/api/routers/requirement_classification_agent_chat.py` (only if verification exposes gaps)
- Modify: `frontend/src/views/alpha/RequirementClassificationAgentChat.vue` (only if verification exposes gaps)
- Test: `tests/agent_chat/test_requirement_classification_tools.py`
- Test: `tests/agent_chat/test_requirement_classification_agent_chat_service.py`
- Test: `tests/agent_chat/test_fastapi_requirement_classification_agent_chat_contract.py`
- Test: `tests/agent_chat/test_session_controller_tools.py`

- [ ] **Step 1: Run the focused backend test suite**

Run:

```bash
pytest \
  tests/agent_chat/test_requirement_classification_tools.py \
  tests/agent_chat/test_requirement_classification_agent_chat_service.py \
  tests/agent_chat/test_fastapi_requirement_classification_agent_chat_contract.py \
  tests/agent_chat/test_session_controller_tools.py -v
```

Expected: PASS

- [ ] **Step 2: Run the frontend production build**

Run: `npm run build`
Workdir: `frontend`
Expected: PASS

- [ ] **Step 3: Perform a manual smoke test**

Manual checklist:
- Open `/alpha/requirement-classification-agent`
- Create a session
- Send a request with an explicit requirement ID
- Confirm SSE messages stream in
- Confirm the execution graph renders
- Confirm the summary card shows `level`, `requirement_nature`, `domain_tags`, and `priority_suggestion`
- Confirm `/alpha/session-controller` can delegate a classification request and show nested nodes

- [ ] **Step 4: Apply only narrow additive fixes if any check fails**

Example fixes:

```python
# good: small normalization fix inside the new tool
if not result.get("domain_tags"):
    result["domain_tags"] = ["通用"]

# avoid: rewriting existing agent infrastructure or changing old offline classification behavior
```

- [ ] **Step 5: Commit**

```bash
git add backend_business/services/agent/tools/requirement_classification_tools.py \
  backend_business/services/agent/agents/requirement_classification_agent/service.py \
  backend_business/api/routers/requirement_classification_agent_chat.py \
  frontend/src/views/alpha/RequirementClassificationAgentChat.vue
superspec commit --summary "Verify and stabilize the requirement classification agent." --next $'Review the completed feature against the spec.\nDecide whether a follow-up increment should persist classification suggestions.' --details $'Ran focused backend tests, frontend build, and manual smoke checks for the requirement classification agent.\nApplied only narrow additive fixes needed to stabilize the new agent.'
```

## Done Criteria

- The repository has a new standalone `requirement_classification_agent` with its own router, frontend page, sessions, messages, and runtime graphs.
- The agent is read-only and does not introduce a new requirement write path.
- `session_controller` can delegate to the new agent using the same inline child-node pattern already used for `requirement_agent` and `conflict_detection_agent`.
- Existing offline classification behavior remains intact.
- Focused backend tests pass and `frontend` builds successfully.
