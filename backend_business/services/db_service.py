import os

from backend_business.config import settings
from backend_business.services.db_service_parts.auth import AuthMixin
from backend_business.services.db_service_parts.base import DBServiceBase
from backend_business.services.db_service_parts.classification import (
    ClassificationAnalysisMixin,
)
from backend_business.services.db_service_parts.conflict import ConflictAnalysisMixin
from backend_business.services.db_service_parts.requirements import L4RequirementsMixin
from backend_business.services.db_service_parts.spans import SpansMixin
from backend_business.services.db_service_parts.trace import TraceAnalysisMixin
from backend_business.services.db_service_parts.utils import _utc_now_iso
# 权限系统 Mixins
from backend_business.services.db_service_parts.project_members import ProjectMembersMixin
from backend_business.services.db_service_parts.member_roles import MemberRolesMixin
from backend_business.services.db_service_parts.review_assignments import ReviewAssignmentsMixin
from backend_business.services.db_service_parts.baselines import BaselinesMixin
from backend_business.services.db_service_parts.change_requests import ChangeRequestsMixin
from backend_business.services.db_service_parts.permissions import PermissionsMixin


class DBService(
    TraceAnalysisMixin,
    ConflictAnalysisMixin,
    ClassificationAnalysisMixin,
    L4RequirementsMixin,
    SpansMixin,
    AuthMixin,
    ProjectMembersMixin,
    MemberRolesMixin,
    ReviewAssignmentsMixin,
    BaselinesMixin,
    ChangeRequestsMixin,
    PermissionsMixin,
    DBServiceBase,
):
    """
    轻量级 PostgreSQL 存储：
    - 保存追溯分析（单对、批量）的输入与输出 JSON
    - 保存解析后的 transcript spans
    - 提供列表/详情/统计
    """


__all__ = ["DBService", "db_service", "_utc_now_iso"]


if os.environ.get("SKIP_DB_INIT") == "1":
    db_service = None
else:
    db_service = DBService(dsn=settings.POSTGRES_DSN)
