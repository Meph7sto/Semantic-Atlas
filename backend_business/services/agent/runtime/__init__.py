"""Generic runtime infrastructure for agent execution."""

from .context import ContextEntry, ExecutionContext
from .graph_recorder import ContainerConfig, RuntimeGraphRecorder, StageNode
from .scratchpad import Scratchpad, ScratchpadEntry

__all__ = [
    "ContainerConfig",
    "ContextEntry",
    "ExecutionContext",
    "RuntimeGraphRecorder",
    "Scratchpad",
    "ScratchpadEntry",
    "StageNode",
]

