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
    "StageNode",
]
