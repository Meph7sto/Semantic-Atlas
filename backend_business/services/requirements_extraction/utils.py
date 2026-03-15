"""
Utility functions for requirements extraction service
"""

import re
from typing import Any, Dict, List, Optional, Sequence


def safe_int(value: Any, default: int) -> int:
    """Safe integer conversion with default fallback"""
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_keywords(value: Optional[Sequence[str]]) -> Optional[List[str]]:
    """Normalize keyword list from various input formats"""
    if not value:
        return None
    if isinstance(value, str):
        parts = re.split(r"[,，;\n|]+", value)
        normalized = [p.strip() for p in parts if p.strip()]
        return normalized or None
    normalized = [str(v).strip() for v in value if str(v).strip()]
    return normalized or None


def normalize_max_r(r_value: Any) -> int:
    """Normalize radius value to 1 or 2"""
    try:
        value = int(r_value)
    except (TypeError, ValueError):
        value = 2
    return 1 if value <= 1 else 2


def build_attempt_r_values(max_r: int) -> List[int]:
    """Build list of radius values to attempt"""
    return [1, 2] if max_r >= 2 else [1]


def is_insufficient_output(exec_result: Optional[Dict[str, Any]]) -> bool:
    """Check if execution result warrants a retry with larger radius"""
    if not exec_result:
        return True
    status = exec_result.get("status")
    if status in {"empty", "invalid_format", "validation_failed"}:
        return True
    parsed_count = exec_result.get("parsed_count")
    if parsed_count is None:
        parsed_count = exec_result.get("parsed_create_count", 0) + exec_result.get(
            "parsed_update_count", 0
        )
    inserted = exec_result.get("inserted", 0)
    duplicates = exec_result.get("duplicates", 0)
    updated = exec_result.get("updated", 0)
    if parsed_count == 0 and updated == 0:
        return True
    if inserted == 0 and duplicates == 0 and updated == 0:
        return True
    return False
