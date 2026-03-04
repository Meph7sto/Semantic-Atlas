"""Memory context - short-term and working memory for an agent."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MemoryContext:
    """Optional memory carried across rounds or conversations."""

    short_term: List[Dict[str, Any]] = field(default_factory=list)   # recent conversation summaries
    working_memory: Dict[str, Any] = field(default_factory=dict)     # scratch-pad for current task
    facts: List[str] = field(default_factory=list)                   # known facts / constraints
