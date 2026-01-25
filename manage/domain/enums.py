"""枚举类型定义"""
from enum import Enum


class RequirementType(Enum):
    """需求类型枚举"""
    TOP_LEVEL = "top_level"  # 顶层需求
    LOW_LEVEL = "low_level"  # 底层需求
    TASK = "task"  # 任务


class RequirementStatus(Enum):
    """需求状态枚举"""
    DRAFT = "draft"  # 草稿
    UNDER_REVIEW = "under_review"  # 评审中
    CONFIRMED = "confirmed"  # 已确认
    IN_PROGRESS = "in_progress"  # 实现中
    COMPLETED = "completed"  # 已完成
    ARCHIVED = "archived"  # 已归档


class ChangeType(Enum):
    """变更类型枚举"""
    ADDED = "added"  # 新增
    MODIFIED = "modified"  # 修改
    DELETED = "deleted"  # 删除
    MOVED = "moved"  # 移动


class BranchStatus(Enum):
    """分支状态枚举"""
    ACTIVE = "active"  # 活跃
    UNDER_REVIEW = "under_review"  # 评审中
    MERGED = "merged"  # 已合并
    CLOSED = "closed"  # 已关闭


class ReviewStatus(Enum):
    """评审状态枚举"""
    PENDING = "pending"  # 待评审
    APPROVED = "approved"  # 已通过
    REJECTED = "rejected"  # 已驳回
    CHANGES_REQUESTED = "changes_requested"  # 需要修改


class ConflictResolutionStrategy(Enum):
    """冲突解决策略枚举"""
    USE_BRANCH = "use_branch"  # 使用分支版本
    USE_MAIN = "use_main"  # 使用主线版本
    MANUAL = "manual"  # 手工解决


class ProjectStatus(Enum):
    """项目状态枚举"""
    ACTIVE = "active"  # 活跃
    ARCHIVED = "archived"  # 归档


class TestCaseStatus(Enum):
    """测试用例/验收标准状态枚举"""
    DRAFT = "draft"  # 草稿
    ACTIVE = "active"  # 生效
    DEPRECATED = "deprecated"  # 过期/废弃


class ImpactLevel(Enum):
    """影响级别枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditAction(Enum):
    """审计动作枚举"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    IMPORT = "import"
    SNAPSHOT = "snapshot"
    BASELINE = "baseline"
    BRANCH_CREATE = "branch_create"
    REVIEW_REQUEST = "review_request"
    REVIEW_DECISION = "review_decision"
    MERGE = "merge"
    EXPORT = "export"


class MergeStatus(Enum):
    """合并状态枚举"""
    PENDING = "pending"
    CONFLICTS = "conflicts"
    MERGED = "merged"
    FAILED = "failed"
