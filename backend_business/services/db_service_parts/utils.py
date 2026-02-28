from datetime import datetime


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
