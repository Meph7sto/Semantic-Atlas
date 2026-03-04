"""Base context - identity and environment info shared by all scenarios."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BaseContext:
    """Minimum context every agent activity needs: who, where, when."""

    user_id: str
    session_id: str
    project_id: Optional[str] = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
