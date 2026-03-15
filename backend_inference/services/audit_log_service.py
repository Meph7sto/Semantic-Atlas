"""
Audit Log Service - 结构化审计日志
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


DEFAULT_AUDIT_LOG_DIR = "data/audit_logs"


def log_audit_event(
    event_type: str,
    payload: Dict[str, Any],
    status: str = "ok",
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    log_dir: str = DEFAULT_AUDIT_LOG_DIR,
) -> str:
    """写入 JSONL 审计日志"""
    req_id = request_id or uuid4().hex
    timestamp = datetime.utcnow().isoformat() + "Z"
    entry = {
        "timestamp": timestamp,
        "request_id": req_id,
        "event_type": event_type,
        "status": status,
        "payload": payload,
    }
    if error:
        entry["error"] = error
    if metadata:
        entry["metadata"] = metadata

    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        filename = log_path / f"{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
        with open(filename, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except Exception:
        return req_id

    return req_id
