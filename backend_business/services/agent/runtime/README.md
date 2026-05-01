# Agent Runtime Contracts

The graph-first runtime boundary is:

```text
GraphExecutor owns the flow.
ToolLoopRunner owns the loop.
```

New agents should start from an `AgentDefinition` and use shared runtime
helpers before adding a dedicated service. Dedicated service entry points must
enter through `GraphExecutor`; alpha single-agent test APIs may call dedicated
services, but their execution still enters graph/runtime instead of a separate
historical path.

Session and graph CRUD belongs in `AgentSessionGraphStore`. Business services
should delegate session hydration, active/suspended graph target resolution,
graph chain listing, and graph deletion to the store instead of copying those
helpers.
