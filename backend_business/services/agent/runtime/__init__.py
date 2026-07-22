"""Generic runtime infrastructure for agent execution."""

from __future__ import annotations

from typing import Any

from .agent_definition import AgentDefinition, AgentDelegation, AgentService
from .agent_execution_service import AgentExecutionService, AgentExecutionTurn
from .agent_runtime import (
    AgentRunResult,
    AgentRuntime,
    AgentRuntimeRegistry,
    LocalAgentRuntime,
    RunRequest,
    RunSupervisor,
    RuntimeBinding,
)
from .context import ContextEntry, ExecutionContext
from .graph_recorder import ContainerConfig, RuntimeGraphRecorder, StageNode
from .memory_compiler import (
    MemoryCompilation,
    PromptMemoryPolicy,
    ScratchpadMemoryCompiler,
    estimate_prompt_tokens,
)
from .scratchpad import Scratchpad, ScratchpadEntry
from .scratchpad_service import ScratchpadService
from .session_graph_store import AgentSessionGraphStore, normalize_context_mode
from .state_contract import (
    RUN_STATE_SOURCE_OF_TRUTH,
    RUN_STATE_VERSION,
    SCRATCHPAD_STATE_BACKEND,
    SCRATCHPAD_STATE_VERSION,
    with_runtime_state_contract,
)
from .tool_capability import ToolCapabilityError, ToolCapabilityExecutor
from .tool_scheduling import ToolExecutionMetadata

__all__ = [
    "RUN_STATE_SOURCE_OF_TRUTH",
    "RUN_STATE_VERSION",
    "SCRATCHPAD_STATE_BACKEND",
    "SCRATCHPAD_STATE_VERSION",
    "AgentDefinition",
    "AgentDelegation",
    "AgentExecutionService",
    "AgentExecutionTurn",
    "AgentCatalog",
    "AgentRegistry",
    "AgentRunResult",
    "AgentRuntime",
    "AgentRuntimeRegistry",
    "AgentService",
    "AgentSessionGraphStore",
    "BUILTIN_AGENT_CATALOG",
    "BUILTIN_AGENT_REGISTRY",
    "ContainerConfig",
    "ContextEntry",
    "ExecutionContext",
    "LocalAgentRuntime",
    "MemoryCompilation",
    "PromptMemoryPolicy",
    "RunRequest",
    "RunSupervisor",
    "RuntimeBinding",
    "RuntimeGraphRecorder",
    "SESSION_CONTROLLER_DEFINITION",
    "Scratchpad",
    "ScratchpadEntry",
    "ScratchpadMemoryCompiler",
    "ScratchpadService",
    "StageNode",
    "ToolCapabilityError",
    "ToolCapabilityExecutor",
    "ToolExecutionMetadata",
    "create_builtin_agent_catalog",
    "create_builtin_agent_registry",
    "estimate_prompt_tokens",
    "normalize_context_mode",
    "with_runtime_state_contract",
]


_CATALOG_EXPORTS = {
    "AgentCatalog",
    "AgentRegistry",
    "BUILTIN_AGENT_CATALOG",
    "BUILTIN_AGENT_REGISTRY",
    "SESSION_CONTROLLER_DEFINITION",
    "create_builtin_agent_catalog",
    "create_builtin_agent_registry",
}


def __getattr__(name: str) -> Any:
    if name in _CATALOG_EXPORTS:
        from . import agent_registry

        return getattr(agent_registry, name)
    raise AttributeError(name)
