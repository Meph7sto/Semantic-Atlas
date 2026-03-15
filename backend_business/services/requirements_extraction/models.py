"""
Data models for requirements extraction service
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AnchorResult:
    """单个锚点的处理结果"""

    anchor_idx: int
    anchor_span_id: str
    bundle_r: int
    exec_result: Dict[str, Any]
    error: Optional[str] = None
