"""Generic runtime infrastructure for agent execution."""

from .agent_definition import AgentDefinition, AgentService
from .agent_registry import (
    BUILTIN_AGENT_REGISTRY,
    SESSION_CONTROLLER_DEFINITION,
    AgentRegistry,
    create_builtin_agent_registry,
)
from .agent_runtime import (
    AgentRunResult,
    AgentRuntime,
    AgentRuntimeRegistry,
    LocalAgentRuntime,
    RunRequest,
    RuntimeBinding,
)
from .context import ContextEntry, ExecutionContext
from .graph_recorder import ContainerConfig, RuntimeGraphRecorder, StageNode
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

__all__ = [
    "RUN_STATE_SOURCE_OF_TRUTH",
    "RUN_STATE_VERSION",
    "SCRATCHPAD_STATE_BACKEND",
    "SCRATCHPAD_STATE_VERSION",
    "AgentDefinition",
    "AgentRegistry",
    "AgentRunResult",
    "AgentRuntime",
    "AgentRuntimeRegistry",
    "AgentService",
    "AgentSessionGraphStore",
    "BUILTIN_AGENT_REGISTRY",
    "ContainerConfig",
    "ContextEntry",
    "ExecutionContext",
    "LocalAgentRuntime",
    "RunRequest",
    "RuntimeBinding",
    "RuntimeGraphRecorder",
    "SESSION_CONTROLLER_DEFINITION",
    "Scratchpad",
    "ScratchpadEntry",
    "ScratchpadService",
    "StageNode",
    "ToolCapabilityError",
    "ToolCapabilityExecutor",
    "create_builtin_agent_registry",
    "normalize_context_mode",
    "with_runtime_state_contract",
]
