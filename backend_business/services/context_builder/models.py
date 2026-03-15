from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Edge:
    source_span_id: str
    target_span_id: str
    relation_type: str
    strength: float
    note: str = ""
    source_order: int = 0
    target_order: int = 0


@dataclass
class Span:
    span_id: str
    session_id: str
    start_ms: Optional[int]
    end_ms: Optional[int]
    speaker: Optional[str]
    text: str
    order_index: int = 0


@dataclass
class SSEEvent:
    event: str
    data: Dict[str, Any]
