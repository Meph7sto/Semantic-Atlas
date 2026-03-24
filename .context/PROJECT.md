# Semantic-Atlas

## What This Repository Is

Semantic-Atlas is a requirement-engineering analysis and management platform. It combines a Vue workbench, a FastAPI business backend, and a FastAPI inference backend to support transcript ingestion, context construction, multi-level requirement extraction, traceability analysis, conflict detection, requirement classification, project/product management, and agent-assisted workflows. The repository also serves as the implementation base for evolving these domain workflows into reusable actor and multi-agent execution infrastructure.

## Long-Term Direction

- Build an end-to-end requirement-engineering platform that turns raw meeting or document inputs into structured, reviewable, and traceable requirements.
- Keep business orchestration, persistence, and inference concerns separated so product workflows can evolve without collapsing service boundaries.
- Evolve agent-facing runtime capabilities, including requirement actors, execution topology, and multi-agent messaging, into reusable platform infrastructure rather than one-off demos.
- Consolidate the user-facing experience around durable workbench flows while preserving experimental surfaces for validating new analysis and agent capabilities.

## Current Focus Area

- Stabilize the main requirement collection, analysis, management, and product/project workbench flows exposed through the `beta` frontend routes.
- Continue converging the business backend on FastAPI-native contracts and behavior instead of maintaining long-lived compatibility shims.
- Advance the actor and execution-topology foundations that support richer agent orchestration on top of the requirement domain.

## Constraints

- Frontend, business backend, and inference backend are separate layers and should remain decoupled by explicit API boundaries -- this repository intentionally does not collapse them into a single service.
- The business backend owns orchestration, persistence, auth, and domain APIs, while the inference backend owns model-facing inference capabilities -- changes should preserve that responsibility split.
- PostgreSQL is the durable system of record for managed business data and extracted requirement artifacts -- implementation choices should not introduce a competing source of truth.
- The repository uses `superspec` workflow conventions, including `superspec commit` instead of plain `git commit` for normal repository work -- future sessions should preserve that workflow.
- Existing user changes in the worktree must be treated as authoritative unless explicitly asked to revert them -- repository work may happen in a dirty tree.

## Stable Decisions

- The canonical MVP context layer lives under `.context/`.
- `beta` routes represent the primary user-facing workbench, while `alpha` routes are retained for experiments, validation tools, and transitional feature surfaces.
- FastAPI-native request validation and error semantics are the target contract for the business backend; long-lived Flask-style compatibility behavior is not the goal.
- Requirement-domain workflows are not only CRUD screens; the repository intentionally includes runtime foundations such as actors, agent communication, and execution topology because they are part of the product direction.

## Open Questions

- How much of the execution-topology and multi-agent infrastructure should become first-class product surface versus remaining an internal or experimental capability?
- What is the intended long-term boundary between requirement-analysis workflows and broader general-purpose agent orchestration in this repository?
- Which repository area should be treated as the primary externally demonstrated value in the near term: the requirement-engineering workbench, the requirement actor runtime, or the execution-topology/multi-agent platform layer?

## Important Context

- The repository already contains substantial implementation across frontend, business backend, inference backend, tests, and architecture documents; it should be treated as an active existing-code codebase rather than a greenfield scaffold.
- Documentation mixes landed behavior, refactor plans, and forward-looking architecture. Future sessions should verify whether a claim is implemented in code before treating it as current system behavior.
- The `beta` workbench centers on project, product, requirement collection, and requirement analysis flows, while `alpha` retains lower-level tools for transcript/context pipelines, chat, topology experimentation, and actor inspection.
- Repository context automation currently has some broken increment-state metadata in `superspec start inspect`; this affects session recovery tooling but does not change the application architecture itself.

## How To Work In This Repository

- Read `README.md` first for the system overview, then inspect the relevant frontend route, business router, and inference router before changing behavior.
- Prefer understanding whether a capability is implemented in `beta`, `alpha`, backend routers, or design docs before making repository-level claims about current behavior.
- Preserve the layered architecture: user workflow and presentation in `frontend/`, business orchestration in `backend_business/`, and model/inference logic in `backend_inference/`.
- When working on backend API behavior, follow FastAPI-native contracts and update the corresponding frontend caller instead of adding compatibility branches by default.
- Use `superspec` repository workflow conventions, and do not treat `.context/PROJECT.md` as a task log or session scratchpad.

---
*Last updated: 2026-03-24*
