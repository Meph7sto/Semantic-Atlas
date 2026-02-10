"""Base context - identity and environment info shared by all scenarios.
基础上下文 - 所有场景共享的身份和环境信息。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BaseContext:
    """Minimum context every agent activity needs: who, where, when.
    每个 Agent 活动所需的最小上下文：谁，哪里，何时。
    """

    user_id: str  # 当前操作的用户 ID
    session_id: str  # 当前会话 ID
    project_id: Optional[str] = None  # 当前项目 ID（可选）
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # 追踪 ID，用于日志和调试
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # 创建时间
