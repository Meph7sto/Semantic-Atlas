"""
Requirements deduplication API routes.

Provides endpoints for detecting, merging, and managing duplicate requirements.
"""

from flask import Blueprint, jsonify, request

from backend_business.config import settings
from backend_business.services.requirements_deduplication import (
    RequirementsDeduplicationService,
)

dedup_bp = Blueprint("deduplication", __name__)

# Initialize deduplication service
dedup_service = RequirementsDeduplicationService(dsn=settings.POSTGRES_DSN)


def _service_with_threshold(threshold):
    if threshold is None:
        return dedup_service
    return RequirementsDeduplicationService(
        dsn=settings.POSTGRES_DSN,
        similarity_threshold=float(threshold),
    )


def _parse_bool(value, default: bool = False) -> bool:
    """Parse common bool-like inputs from JSON payloads."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _parse_int(value, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_optional_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return "__invalid__"


@dedup_bp.post("/detect")
def detect_duplicates():  # 已迁移
    """
    Detect duplicate requirements in a session.

    Request body:
    {
        "session_id": "xxx",              # Required
        "level": "L1" | "L2" | "L3",      # Optional, filter by level
        "with_llm_decision": true,         # Optional, default true
        "auto_merge": false,               # Optional, default false
        "model": "deepseek-chat",          # Optional
        "threshold": 0.85,                 # Optional, similarity threshold
        "max_concurrent": 5                # Optional, max concurrent LLM calls
    }

    Returns:
    {
        "duplicate_groups": [...],
        "total_duplicates": int,
        "total_requirements_scanned": int,
        "total_merged": int | null
    }
    """
    data = request.get_json() or {}

    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing 'session_id' field"}), 400

    level = data.get("level")
    with_llm_decision = _parse_bool(data.get("with_llm_decision"), default=True)
    auto_merge = _parse_bool(data.get("auto_merge"), default=False)
    model_name = data.get("model")
    threshold = _parse_optional_float(data.get("threshold"))
    if threshold == "__invalid__":
        return jsonify({"error": "Invalid 'threshold' field"}), 400
    max_concurrent = _parse_int(data.get("max_concurrent"), default=5)
    max_concurrent = max(1, min(10, max_concurrent))

    try:
        service = _service_with_threshold(threshold)
        result = service.detect_duplicates(
            session_id=session_id,
            level=level,
            with_llm_decision=with_llm_decision,
            auto_merge=auto_merge,
            model_name=model_name,
            max_concurrent=max_concurrent,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@dedup_bp.post("/merge")
def execute_merge():  # 已迁移
    """
    Execute a merge operation (after user confirmation).

    Request body:
    {
        "session_id": "xxx",                  # Required
        "primary_req_id": "xxx",              # Required, the requirement to keep
        "to_delete_req_ids": ["id1", "id2"],  # Required, requirements to delete
        "merged_text": "...",                 # Required, the merged requirement text
        "merged_level": "L2",                 # Required
        "reason": "..."                       # Optional
    }

    Returns:
    {
        "success": true,
        "primary_req_id": "xxx",
        "deleted_count": 2,
        "old_text": "...",
        "new_text": "...",
        "reason": "..."
    }
    """
    data = request.get_json() or {}

    session_id = data.get("session_id")
    primary_req_id = data.get("primary_req_id")
    to_delete_req_ids = data.get("to_delete_req_ids", [])
    merged_text = data.get("merged_text")
    merged_level = data.get("merged_level")
    reason = data.get("reason", "")

    # Validation
    if not session_id:
        return jsonify({"error": "Missing 'session_id' field"}), 400
    if not primary_req_id:
        return jsonify({"error": "Missing 'primary_req_id' field"}), 400
    if not to_delete_req_ids:
        return jsonify({"error": "Missing 'to_delete_req_ids' field"}), 400
    if not merged_text:
        return jsonify({"error": "Missing 'merged_text' field"}), 400
    if not merged_level:
        return jsonify({"error": "Missing 'merged_level' field"}), 400

    try:
        result = dedup_service.execute_merge(
            session_id=session_id,
            primary_req_id=primary_req_id,
            to_delete_req_ids=to_delete_req_ids,
            merged_text=merged_text,
            merged_level=merged_level,
            reason=reason,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@dedup_bp.post("/delete")
def delete_requirements():  # 已迁移
    """
    Batch delete requirements.

    Request body:
    {
        "session_id": "xxx",          # Required
        "req_ids": ["id1", "id2"],    # Required
        "reason": "..."               # Optional
    }

    Returns:
    {
        "success": true,
        "deleted_count": 2
    }
    """
    data = request.get_json() or {}

    session_id = data.get("session_id")
    req_ids = data.get("req_ids", [])
    reason = data.get("reason", "")

    if not session_id:
        return jsonify({"error": "Missing 'session_id' field"}), 400
    if not req_ids:
        return jsonify({"error": "Missing 'req_ids' field"}), 400

    try:
        result = dedup_service.delete_requirements(
            session_id=session_id,
            req_ids=req_ids,
            reason=reason,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@dedup_bp.post("/update")
def update_requirement():  # 已迁移
    """
    Update a single requirement's text and/or level.

    Request body:
    {
        "session_id": "xxx",      # Required
        "req_id": "xxx",          # Required
        "new_text": "...",        # Required
        "new_level": "L2",        # Optional
        "reason": "..."           # Optional
    }

    Returns:
    {
        "success": true,
        "req_id": "xxx",
        "old_text": "...",
        "new_text": "..."
    }
    """
    data = request.get_json() or {}

    session_id = data.get("session_id")
    req_id = data.get("req_id")
    new_text = data.get("new_text")
    new_level = data.get("new_level")
    reason = data.get("reason", "")

    if not session_id:
        return jsonify({"error": "Missing 'session_id' field"}), 400
    if not req_id:
        return jsonify({"error": "Missing 'req_id' field"}), 400
    if not new_text:
        return jsonify({"error": "Missing 'new_text' field"}), 400

    try:
        result = dedup_service.update_requirement(
            session_id=session_id,
            req_id=req_id,
            new_text=new_text,
            new_level=new_level,
            reason=reason,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@dedup_bp.post("/pairs")
def get_similar_pairs():  # 已迁移
    """
    Get all similar requirement pairs (without grouping).

    Request body:
    {
        "session_id": "xxx",          # Required
        "level": "L1" | "L2" | "L3",  # Optional
        "threshold": 0.85             # Optional
    }

    Returns:
    {
        "pairs": [{"req_1": {...}, "req_2": {...}, "similarity": 0.92}, ...],
        "total_pairs": int,
        "total_requirements_scanned": int
    }
    """
    data = request.get_json() or {}

    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing 'session_id' field"}), 400

    level = data.get("level")
    threshold = _parse_optional_float(data.get("threshold"))
    if threshold == "__invalid__":
        return jsonify({"error": "Invalid 'threshold' field"}), 400

    try:
        service = _service_with_threshold(threshold)
        result = service.get_similar_pairs(
            session_id=session_id,
            level=level,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@dedup_bp.post("/regenerate")
def regenerate_llm_decision():  # 已迁移
    """
    Regenerate LLM merge decision for specific requirements.

    Request body:
    {
        "session_id": "xxx",          # Required
        "req_ids": ["id1", "id2"],    # Required, at least 2
        "model": "deepseek-chat"      # Optional
    }

    Returns:
    {
        "requirements": [...],
        "similarity": float,
        "llm_decision": {
            "should_merge": bool,
            "merged_text": "...",
            "merged_level": "L2",
            "primary_req_id": "...",
            "reason": "...",
            "error": null
        }
    }
    """
    data = request.get_json() or {}

    session_id = data.get("session_id")
    req_ids = data.get("req_ids", [])
    model_name = data.get("model")

    if not session_id:
        return jsonify({"error": "Missing 'session_id' field"}), 400
    if not req_ids or len(req_ids) < 2:
        return jsonify(
            {"error": "'req_ids' must contain at least 2 requirement IDs"}
        ), 400

    try:
        result = dedup_service.regenerate_llm_decision(
            session_id=session_id,
            req_ids=req_ids,
            model_name=model_name,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
