from datetime import datetime


def _utc_now_iso(timespec: str = "seconds") -> str:
    """UTC ISO-8601 timestamp with trailing 'Z'.

    timespec: 'auto', 'hours', 'minutes', 'seconds', 'milliseconds', 'microseconds'
    """
    return datetime.utcnow().isoformat(timespec=timespec) + "Z"
