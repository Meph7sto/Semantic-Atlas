# Beta Traceability Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a low-intrusion Beta traceability workbench that aggregates existing requirement-management models into traceability, coverage, impact, and risk views.

**Architecture:** Extend the existing manage backend with new aggregation endpoints and add one dedicated Beta traceability page that consumes them. Preserve current routes and page behavior by layering new code beside existing flows instead of refactoring them in place.

**Tech Stack:** Vue 3, existing Beta component patterns, FastAPI routers, `RequirementsManageService`, PostgreSQL-backed manage tables, pytest

---

### Task 1: Map existing route and navigation entry points

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/components/beta/Sidebar.vue`
- Check: `frontend/src/composables/useBetaNavigation.js`

- [x] **Step 1: Inspect the current Beta route and sidebar keys**

Run: `rg -n "beta-|activePage|navItemsConfig|Sidebar" frontend/src/router/index.js frontend/src/components/beta frontend/src/composables --glob '*.*'`
Expected: existing route names and sidebar navigation keys are visible

- [x] **Step 2: Write the failing expectation**

Document the intended new route and sidebar key:
- route name for Beta traceability page
- sidebar label for the new workbench

- [x] **Step 3: Add the new route and sidebar entry**

Implement a new Beta route that points to `TraceabilityView.vue` and add one sidebar navigation item without changing unrelated menu behavior.

- [x] **Step 4: Verify route wiring**

Run: `rg -n "traceability" frontend/src/router/index.js frontend/src/components/beta/Sidebar.vue`
Expected: the new Beta route and sidebar entry are both present

- [x] **Step 5: Commit**

```bash
git add frontend/src/router/index.js frontend/src/components/beta/Sidebar.vue
superspec commit --summary "Add beta traceability navigation entry" --next $'Build the dedicated traceability page shell and shared page state.\nKeep the change isolated to routing and sidebar navigation.' --details $'Register a new Beta workbench route for traceability.\nExpose the entry through the existing sidebar without restructuring navigation.'
```

### Task 2: Create the dedicated Beta traceability page shell

**Files:**
- Create: `frontend/src/views/beta/TraceabilityView.vue`
- Create: `frontend/src/composables/useTraceabilityWorkbench.js`
- Check: `frontend/src/views/beta/ProductManageView.vue`
- Check: `frontend/src/views/beta/RequirementsView.vue`

- [x] **Step 1: Write the failing UI target**

Define the page shell requirements:
- Beta layout
- project selector
- branch selector
- tab state
- loading and empty states

- [x] **Step 2: Add the composable skeleton**

Create a composable to manage:
- selected project
- selected branch
- active tab
- loading and error state

- [x] **Step 3: Add the new view**

Create `TraceabilityView.vue` using current Beta layout classes and wire it to the composable.

- [x] **Step 4: Verify the page compiles**

Run: `npm run build`
Expected: frontend build passes with the new page shell

- [x] **Step 5: Commit**

```bash
git add frontend/src/views/beta/TraceabilityView.vue frontend/src/composables/useTraceabilityWorkbench.js
superspec commit --summary "Create the beta traceability page shell" --next $'Add page-level API clients and load project and branch context.\nKeep the view isolated from existing manage pages.' --details $'Introduce a dedicated Beta traceability workbench view.\nUse a new composable for local page state instead of modifying existing large views.'
```

### Task 3: Add backend traceability schema contracts

**Files:**
- Modify: `backend_business/api/routers/schemas/manage_schemas.py`
- Modify: `backend_business/api/routers/manage.py`
- Test: `backend_business/tests/` relevant manage router tests

- [x] **Step 1: Write failing API contract expectations**

Define request and response needs for:
- matrix
- coverage
- impact
- risk

- [x] **Step 2: Add request schemas for traceability impact parameters**

Add minimal new Pydantic models for traceability impact comparison inputs and optional branch selection query parameters if needed.

- [x] **Step 3: Add router declarations**

Add route signatures and permission checks in `manage.py` without implementing the full service logic yet.

- [x] **Step 4: Verify imports and router load**

Run: `pytest backend_business/tests -q`
Expected: schema and router import errors are resolved

- [x] **Step 5: Commit**

```bash
git add backend_business/api/routers/schemas/manage_schemas.py backend_business/api/routers/manage.py backend_business/tests
superspec commit --summary "Add traceability API contracts" --next $'Implement service aggregation for overview, matrix, coverage, impact, and risk.\nKeep existing manage endpoints backward compatible.' --details $'Introduce dedicated manage-router contracts for the Beta traceability workbench.\nConstrain the change to additive router behavior.'
```

### Task 4: Implement traceability overview and matrix aggregation

**Files:**
- Modify: `backend_business/services/requirements_manage_service.py`
- Modify: `backend_business/api/routers/manage.py`
- Test: `backend_business/tests/` relevant service and API tests

- [x] **Step 1: Write failing tests for overview and matrix**

Add tests covering:
- branch list and selected branch context
- branch head milestone loading
- requirement tree reconstruction
- test-link hydration
- change-set and audit aggregation

- [x] **Step 2: Add focused helper methods**

Implement small internal helpers for:
- resolving branch head milestone
- loading branch snapshot nodes
- indexing requirement-to-test relationships
- collecting related change sets and audits

- [x] **Step 3: Implement `get_traceability_overview` and `get_traceability_matrix`**

Return page-ready payloads without changing existing list and detail methods.

- [x] **Step 4: Run targeted tests**

Run: `pytest backend_business/tests -k "traceability and (overview or matrix)" -q`
Expected: tests pass for the new aggregation behavior

- [x] **Step 5: Commit**

```bash
git add backend_business/services/requirements_manage_service.py backend_business/api/routers/manage.py backend_business/tests
superspec commit --summary "Add traceability overview and matrix aggregation" --next $'Implement coverage analysis and orphan-change detection.\nPreserve existing requirement-management service behavior outside the new endpoints.' --details $'Aggregate branch-head requirement snapshots, test links, change sets, and audit evidence for the Beta traceability matrix.\nKeep the implementation additive inside RequirementsManageService.'
```

### Task 5: Implement coverage aggregation

**Files:**
- Modify: `backend_business/services/requirements_manage_service.py`
- Modify: `backend_business/api/routers/manage.py`
- Test: `backend_business/tests/` relevant service and API tests

- [ ] **Step 1: Write failing tests for orphan requirement and unlinked change detection**

Cover:
- `in_progress` requirement with no test link
- linked requirement with tests
- change set with missing requirement reference
- change set with null requirement reference

- [ ] **Step 2: Implement `get_traceability_coverage`**

Return:
- coverage summary
- orphan requirements
- unlinked changes

- [ ] **Step 3: Wire the coverage endpoint**

Expose the service result through the additive router endpoint.

- [ ] **Step 4: Run targeted tests**

Run: `pytest backend_business/tests -k "traceability and coverage" -q`
Expected: coverage-specific tests pass

- [ ] **Step 5: Commit**

```bash
git add backend_business/services/requirements_manage_service.py backend_business/api/routers/manage.py backend_business/tests
superspec commit --summary "Add traceability coverage analysis" --next $'Implement impact calculation on top of milestone diffs and branch context.\nKeep coverage rules explicit and limited to current business models.' --details $'Detect uncovered in-progress requirements and unlinked branch changes for the Beta traceability workbench.\nAvoid inventing new task or defect entities.'
```

### Task 6: Replace placeholder impact reporting with real traceability impact logic

**Files:**
- Modify: `backend_business/services/requirements_manage_service.py`
- Modify: `backend_business/api/routers/manage.py`
- Modify: `backend_business/api/routers/schemas/manage_schemas.py`
- Test: `backend_business/tests/` relevant service and API tests

- [ ] **Step 1: Write failing impact tests**

Cover:
- compare to branch base milestone
- compare to project baseline
- changed requirements from milestone diff
- descendant propagation
- affected test case detection

- [ ] **Step 2: Implement impact comparison target resolution**

Resolve comparison target in this order when requested:
- explicit milestone
- baseline
- branch base milestone

- [ ] **Step 3: Implement `create_traceability_impact_report`**

Use existing milestone comparison and relationship traversal to compute:
- diff summary
- changed requirements
- affected descendants
- affected test cases
- related changes
- related audits
- risk flags

- [ ] **Step 4: Persist the report into the existing impact-report table**

Store the computed summary and detail JSON instead of the current placeholder payload.

- [ ] **Step 5: Run targeted tests**

Run: `pytest backend_business/tests -k "traceability and impact" -q`
Expected: impact calculation and persistence tests pass

- [ ] **Step 6: Commit**

```bash
git add backend_business/services/requirements_manage_service.py backend_business/api/routers/manage.py backend_business/api/routers/schemas/manage_schemas.py backend_business/tests
superspec commit --summary "Implement real traceability impact reports" --next $'Add risk summary aggregation and expose the remaining traceability read model.\nKeep the legacy impact endpoint shape stable where practical.' --details $'Replace the placeholder impact report with milestone-diff-based requirement and test impact calculation.\nPersist the computed result in the existing manage impact-report storage.'
```

### Task 7: Implement risk summary aggregation

**Files:**
- Modify: `backend_business/services/requirements_manage_service.py`
- Modify: `backend_business/api/routers/manage.py`
- Test: `backend_business/tests/` relevant service and API tests

- [ ] **Step 1: Write failing tests for risk summaries**

Cover:
- requirement status distribution
- uncovered in-progress requirements
- frequently changed requirements
- recently active audit targets

- [ ] **Step 2: Implement `get_traceability_risk`**

Aggregate risk-oriented summaries using already-computed traceability data where possible.

- [ ] **Step 3: Wire the risk endpoint**

Return a page-ready management summary payload.

- [ ] **Step 4: Run targeted tests**

Run: `pytest backend_business/tests -k "traceability and risk" -q`
Expected: risk tests pass

- [ ] **Step 5: Commit**

```bash
git add backend_business/services/requirements_manage_service.py backend_business/api/routers/manage.py backend_business/tests
superspec commit --summary "Add traceability risk summaries" --next $'Connect the frontend workbench to the new APIs and implement each tab.\nReuse Beta design patterns instead of introducing a separate UI system.' --details $'Aggregate management-facing risk signals from statuses, coverage gaps, change activity, and audit activity.\nKeep the read model additive and page-oriented.'
```

### Task 8: Add frontend API bindings for the traceability workbench

**Files:**
- Modify: `frontend/src/api/project.js` or create `frontend/src/api/traceability.js`
- Modify: `frontend/src/composables/useTraceabilityWorkbench.js`
- Test: frontend tests if present

- [ ] **Step 1: Write the failing client expectations**

Define client methods for:
- overview
- matrix
- coverage
- impact
- risk

- [ ] **Step 2: Add API calls**

Implement additive client methods that follow current `manageApi` error-handling style.

- [ ] **Step 3: Wire composable fetch flows**

Load shared context and tab-specific payloads without coupling to other pages.

- [ ] **Step 4: Verify frontend build**

Run: `npm run build`
Expected: the API additions compile cleanly

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/project.js frontend/src/composables/useTraceabilityWorkbench.js
superspec commit --summary "Add frontend traceability API bindings" --next $'Implement the matrix and coverage tabs in the new Beta page.\nKeep the page state localized to the dedicated composable.' --details $'Add additive client bindings for the traceability overview, matrix, coverage, impact, and risk endpoints.\nPreserve existing manage API behavior.'
```

### Task 9: Implement the matrix and coverage tabs

**Files:**
- Modify: `frontend/src/views/beta/TraceabilityView.vue`
- Create: `frontend/src/components/beta/traceability/TraceabilityMatrixPanel.vue`
- Create: `frontend/src/components/beta/traceability/TraceabilityCoveragePanel.vue`
- Optional Create: shared traceability panel components

- [ ] **Step 1: Write the failing UI expectations**

Cover:
- tab rendering
- matrix empty state
- matrix populated state
- coverage cards
- orphan and unlinked-change lists

- [ ] **Step 2: Build the matrix panel**

Render:
- hierarchical requirement rows
- status
- coverage indicators
- change and audit counts
- selection detail panel

- [ ] **Step 3: Build the coverage panel**

Render:
- summary cards
- orphan requirements list
- unlinked changes list

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: matrix and coverage UI compiles cleanly

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/beta/TraceabilityView.vue frontend/src/components/beta/traceability
superspec commit --summary "Build the traceability matrix and coverage tabs" --next $'Implement the impact and risk tabs using the new backend aggregations.\nKeep component responsibilities narrow and additive.' --details $'Add the first two Beta traceability workbench tabs with branch-scoped requirement, test, change, and audit context.\nFollow the existing Beta page layout and styling patterns.'
```

### Task 10: Implement the impact and risk tabs

**Files:**
- Modify: `frontend/src/views/beta/TraceabilityView.vue`
- Create: `frontend/src/components/beta/traceability/TraceabilityImpactPanel.vue`
- Create: `frontend/src/components/beta/traceability/TraceabilityRiskPanel.vue`

- [ ] **Step 1: Write the failing UI expectations**

Cover:
- impact trigger
- comparison target selection
- impact result rendering
- risk summary rendering

- [ ] **Step 2: Build the impact panel**

Render:
- diff summary cards
- changed and affected requirement lists
- affected test lists
- related change and audit evidence

- [ ] **Step 3: Build the risk panel**

Render:
- status distribution
- risk cards
- high-risk chains
- active audit targets

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: impact and risk tabs compile cleanly

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/beta/TraceabilityView.vue frontend/src/components/beta/traceability
superspec commit --summary "Build the traceability impact and risk tabs" --next $'Run backend and frontend verification for the full traceability increment.\nFix any contract mismatches without broad refactors.' --details $'Complete the Beta traceability workbench with impact and risk views.\nKeep the interaction model aligned to the approved four-tab design.'
```

### Task 11: Verify the increment end to end

**Files:**
- Modify: relevant backend and frontend files as needed for fixes
- Check: `.context/increments/add-beta-traceability-page/2026-03-24-design.md`
- Check: `.context/increments/add-beta-traceability-page/plan.md`

- [ ] **Step 1: Run backend tests**

Run: `pytest backend_business/tests -q`
Expected: backend tests pass for manage and traceability changes

- [ ] **Step 2: Run frontend build**

Run: `npm run build`
Expected: frontend compiles successfully

- [ ] **Step 3: Perform manual spot checks**

Verify:
- route opens
- project and branch selection works
- all four tabs render
- empty states are reasonable
- impact analysis returns persisted results

- [ ] **Step 4: Fix any regressions**

Make only focused corrective edits; do not restructure unrelated code during verification.

- [ ] **Step 5: Commit**

```bash
git add .context/increments/add-beta-traceability-page/2026-03-24-design.md .context/increments/add-beta-traceability-page/plan.md frontend backend_business
superspec commit --summary "Ship the beta traceability workbench" --next $'Run a final user-facing walkthrough on representative project and branch data.\nDecide whether the next increment should deepen traceability visualization or broaden linked entity coverage.' --details $'Deliver the Beta traceability workbench with matrix, coverage, impact, and risk tabs.\nKeep the implementation low-intrusion by layering additive APIs and a dedicated page onto the existing repository structure.'
```
