"""Generic runtime infrastructure for agent execution."""

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
from .state_contract import (
    RUN_STATE_SOURCE_OF_TRUTH,
    RUN_STATE_VERSION,
    SCRATCHPAD_STATE_BACKEND,
    SCRATCHPAD_STATE_VERSION,
    with_runtime_state_contract,
)
from .tool_capability import ToolCapabilityError, ToolCapabilityExecutor

__all__ = [
    "AgentRunResult",
    "AgentRuntime",
    "AgentRuntimeRegistry",
    "ContainerConfig",
    "ContextEntry",
    "ExecutionContext",
    "LocalAgentRuntime",
    "RuntimeGraphRecorder",
    "RunRequest",
    "RuntimeBinding",
    "Scratchpad",
    "ScratchpadEntry",
    "ScratchpadService",
    "SCRATCHPAD_STATE_BACKEND",
    "SCRATCHPAD_STATE_VERSION",
    "StageNode",
    "ToolCapabilityError",
    "ToolCapabilityExecutor",
    "RUN_STATE_SOURCE_OF_TRUTH",
    "RUN_STATE_VERSION",
    "with_runtime_state_contract",
]
