"""
RequirementActor 状态机

定义需求的状态转换规则和前置条件校验
"""

import logging
from enum import Enum
from typing import Dict, Set, Optional, Callable

logger = logging.getLogger(__name__)


class RequirementStatus(str, Enum):
    """需求状态枚举"""
    DRAFT = "Draft"
    PENDING_REVIEW = "PendingReview"
    UNDER_REVIEW = "UnderReview"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    BASELINED = "Baselined"
    CHANGE_REQUESTED = "ChangeRequested"


class StateTransition:
    """状态转换定义"""
    def __init__(self, from_status: RequirementStatus, to_status: RequirementStatus,
                 condition: str = "", validator: Optional[Callable] = None):
        self.from_status = from_status
        self.to_status = to_status
        self.condition = condition
        self.validator = validator


class RequirementStateMachine:
    """需求状态机"""

    def __init__(self):
        self._transitions: Dict[RequirementStatus, Dict[RequirementStatus, StateTransition]] = {}
        self._forbidden_transitions: Set[tuple] = set()
        self._initialize_transitions()

    def _initialize_transitions(self):
        """初始化状态转换规则"""

        # ========================
        # Draft 状态转换
        # ========================
        self._add_transition(
            RequirementStatus.DRAFT,
            RequirementStatus.PENDING_REVIEW,
            "质量门禁通过"
        )
        self._add_forbidden(RequirementStatus.DRAFT, [
            RequirementStatus.UNDER_REVIEW,
            RequirementStatus.APPROVED,
            RequirementStatus.BASELINED,
            RequirementStatus.CHANGE_REQUESTED
        ])

        # ========================
        # PendingReview 状态转换
        # ========================
        self._add_transition(
            RequirementStatus.PENDING_REVIEW,
            RequirementStatus.UNDER_REVIEW,
            "提交评审"
        )
        self._add_forbidden(RequirementStatus.PENDING_REVIEW, [
            RequirementStatus.DRAFT,
            RequirementStatus.APPROVED,
            RequirementStatus.BASELINED,
            RequirementStatus.REJECTED
        ])

        # ========================
        # UnderReview 状态转换
        # ========================
        self._add_transition(
            RequirementStatus.UNDER_REVIEW,
            RequirementStatus.APPROVED,
            "通过"
        )
        self._add_transition(
            RequirementStatus.UNDER_REVIEW,
            RequirementStatus.REJECTED,
            "驳回"
        )
        self._add_transition(
            RequirementStatus.UNDER_REVIEW,
            RequirementStatus.PENDING_REVIEW,
            "要求修改"
        )
        self._add_forbidden(RequirementStatus.UNDER_REVIEW, [
            RequirementStatus.DRAFT,
            RequirementStatus.BASELINED
        ])

        # ========================
        # Approved 状态转换
        # ========================
        self._add_transition(
            RequirementStatus.APPROVED,
            RequirementStatus.BASELINED,
            "纳入基线"
        )
        self._add_transition(
            RequirementStatus.APPROVED,
            RequirementStatus.CHANGE_REQUESTED,
            "请求变更"
        )
        self._add_forbidden(RequirementStatus.APPROVED, [
            RequirementStatus.DRAFT,
            RequirementStatus.PENDING_REVIEW,
            RequirementStatus.UNDER_REVIEW,
            RequirementStatus.REJECTED
        ])

        # ========================
        # Rejected 状态转换
        # ========================
        self._add_transition(
            RequirementStatus.REJECTED,
            RequirementStatus.PENDING_REVIEW,
            "修订后提交"
        )
        self._add_forbidden(RequirementStatus.REJECTED, [
            RequirementStatus.APPROVED,
            RequirementStatus.BASELINED,
            RequirementStatus.UNDER_REVIEW
        ])

        # ========================
        # Baselined 状态转换
        # ========================
        self._add_transition(
            RequirementStatus.BASELINED,
            RequirementStatus.CHANGE_REQUESTED,
            "发起变更"
        )
        self._add_forbidden(RequirementStatus.BASELINED, [
            RequirementStatus.DRAFT,
            RequirementStatus.PENDING_REVIEW,
            RequirementStatus.UNDER_REVIEW,
            RequirementStatus.APPROVED,
            RequirementStatus.REJECTED
        ])

        # ========================
        # ChangeRequested 状态转换
        # ========================
        self._add_transition(
            RequirementStatus.CHANGE_REQUESTED,
            RequirementStatus.BASELINED,
            "批准变更"
        )
        self._add_transition(
            RequirementStatus.CHANGE_REQUESTED,
            RequirementStatus.BASELINED,
            "拒绝变更"
        )
        self._add_forbidden(RequirementStatus.CHANGE_REQUESTED, [
            RequirementStatus.DRAFT,
            RequirementStatus.PENDING_REVIEW,
            RequirementStatus.UNDER_REVIEW,
            RequirementStatus.APPROVED,
            RequirementStatus.REJECTED
        ])

    def _add_transition(self, from_status: RequirementStatus, to_status: RequirementStatus, condition: str):
        """添加合法转换"""
        if from_status not in self._transitions:
            self._transitions[from_status] = {}
        self._transitions[from_status][to_status] = StateTransition(from_status, to_status, condition)

    def _add_forbidden(self, from_status: RequirementStatus, to_statuses: list):
        """添加禁止转换"""
        for to_status in to_statuses:
            self._forbidden_transitions.add((from_status, to_status))

    def can_transition(self, current_status: RequirementStatus, target_status: RequirementStatus) -> bool:
        """
        检查状态转换是否允许

        Args:
            current_status: 当前状态
            target_status: 目标状态

        Returns:
            True 如果转换允许，False 否则
        """
        if (current_status, target_status) in self._forbidden_transitions:
            return False
        return target_status in self._transitions.get(current_status, {})

    def get_allowed_transitions(self, current_status: RequirementStatus) -> list[RequirementStatus]:
        """
        获取当前状态允许的所有转换目标

        Args:
            current_status: 当前状态

        Returns:
            允许转换到的状态列表
        """
        return list(self._transitions.get(current_status, {}).keys())

    def get_transition_condition(self, current_status: RequirementStatus,
                               target_status: RequirementStatus) -> str:
        """
        获取转换条件描述

        Args:
            current_status: 当前状态
            target_status: 目标状态

        Returns:
            转换条件描述
        """
        transition = self._transitions.get(current_status, {}).get(target_status)
        return transition.condition if transition else ""

    def transition(self, current_status: RequirementStatus, target_status: RequirementStatus,
                  validator: Optional[Callable] = None) -> RequirementStatus:
        """
        执行状态转换

        Args:
            current_status: 当前状态
            target_status: 目标状态
            validator: 自定义验证器（可选）

        Returns:
            新状态

        Raises:
            ValueError: 转换不合法时
        """
        if not self.can_transition(current_status, target_status):
            allowed = [s.value for s in self.get_allowed_transitions(current_status)]
            raise ValueError(
                f"非法状态转换: {current_status.value} -> {target_status.value}. "
                f"允许的转换: {allowed}"
            )

        # 执行自定义验证器
        if validator:
            validator(current_status, target_status)

        logger.info(f"State transition: {current_status.value} -> {target_status.value}")
        return target_status


# 全局状态机实例（单例）
state_machine = RequirementStateMachine()
