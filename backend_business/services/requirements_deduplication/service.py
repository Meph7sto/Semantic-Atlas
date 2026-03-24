"""
Main orchestration service for requirements deduplication.

Coordinates detection, LLM merge decisions, and execution.
"""

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from backend_business.services.requirements_extraction.data_access import (
    RequirementsDataAccess,
)

from .detector import DuplicateDetector
from .executor import DeduplicationExecutor
from .merger import RequirementMerger
from .models import DeduplicationResult, DuplicateGroup, MergeDecision

logger = logging.getLogger(__name__)


class RequirementsDeduplicationService:
    """
    需求去重服务

    提供完整的去重流程：检测 → LLM决策 → 执行合并
    """

    def __init__(
        self,
        dsn: str,
        similarity_threshold: float = 0.85,
        default_model: str = "deepseek-reasoner",
    ):
        """
        初始化去重服务

        Args:
            dsn: PostgreSQL 连接字符串
            similarity_threshold: 相似度阈值
            default_model: 默认使用的LLM模型
        """
        self.dsn = dsn
        self.detector = DuplicateDetector(similarity_threshold=similarity_threshold)
        self.merger = RequirementMerger(model_name=default_model)
        self.executor = DeduplicationExecutor(dsn)
        self.data_access = RequirementsDataAccess(dsn)
        self.default_model = default_model

    def detect_duplicates(
        self,
        session_id: str,
        level: Optional[str] = None,
        with_llm_decision: bool = True,
        auto_merge: bool = False,
        model_name: Optional[str] = None,
        max_concurrent: int = 5,
    ) -> Dict[str, Any]:
        """
        检测重复需求

        Args:
            session_id: 会话ID
            level: 限定层级（可选，None表示检测所有层级）
            with_llm_decision: 是否调用LLM获取合并建议
            auto_merge: 是否自动执行LLM建议的合并
            model_name: 使用的模型名称
            max_concurrent: LLM 并行调用的最大并发数（默认 5）

        Returns:
            检测结果，包含 duplicate_groups, total_duplicates 等
        """
        model = model_name or self.default_model

        # 1. 获取需求列表
        all_reqs = self.data_access.get_all_requirements_for_session(session_id)

        # 按层级过滤
        if level and level in ("L1", "L2", "L3"):
            all_reqs = [r for r in all_reqs if r.get("level") == level]

        total_scanned = len(all_reqs)

        if total_scanned < 2:
            return {
                "duplicate_groups": [],
                "total_duplicates": 0,
                "total_requirements_scanned": total_scanned,
                "total_merged": 0,
                "message": "需求数量不足，无需去重",
            }

        # 2. 检测重复
        duplicate_groups: List[DuplicateGroup] = self.detector.detect_duplicates(
            all_reqs, by_level=True
        )

        if not duplicate_groups:
            return {
                "duplicate_groups": [],
                "total_duplicates": 0,
                "total_requirements_scanned": total_scanned,
                "total_merged": 0,
                "message": "未检测到重复需求",
            }

        # 3. 调用 LLM 获取合并建议（并行）
        decisions: List[Optional[MergeDecision]] = [None] * len(duplicate_groups)
        if with_llm_decision:
            # 构建 LLM 请求的输入
            llm_inputs = [
                {
                    "level": group.level,
                    "requirements": group.requirements,
                    "similarity": group.similarity,
                }
                for group in duplicate_groups
            ]
            # 并行调用 LLM
            decisions = self.merger.batch_decide_merge(
                llm_inputs,
                model_name=model,
                max_concurrent=max_concurrent,
            )

        # 4. 构建结果
        result_groups: List[Dict[str, Any]] = []
        total_merged = 0

        for i, group in enumerate(duplicate_groups):
            group_dict = {
                "group_id": group.group_id,
                "level": group.level,
                "requirements": group.requirements,
                "similarity": round(group.similarity, 4),
                "representative_text": group.representative_text,
            }

            # 添加 LLM 决策结果
            if with_llm_decision and decisions[i] is not None:
                decision = decisions[i]
                group_dict["llm_decision"] = {
                    "should_merge": decision.should_merge,
                    "merged_text": decision.merged_text,
                    "merged_level": decision.merged_level,
                    "primary_req_id": decision.primary_req_id,
                    "reason": decision.reason,
                    "error": decision.error,
                }

                # 5. 自动执行合并
                if auto_merge and decision.should_merge and not decision.error:
                    merge_result = self._execute_merge_for_group(
                        session_id=session_id,
                        group=group,
                        decision=decision,
                    )
                    group_dict["merge_result"] = asdict(merge_result)

                    if merge_result.success:
                        total_merged += 1

            result_groups.append(group_dict)

        return {
            "duplicate_groups": result_groups,
            "total_duplicates": len(duplicate_groups),
            "total_requirements_scanned": total_scanned,
            "total_merged": total_merged if auto_merge else None,
        }

    def _execute_merge_for_group(
        self,
        session_id: str,
        group: DuplicateGroup,
        decision: MergeDecision,
    ):
        """执行单个组的合并操作"""
        # 确定要删除的需求ID
        all_req_ids = [r["req_id"] for r in group.requirements]
        primary_id = decision.primary_req_id

        # 如果LLM没有指定主需求，使用第一个
        if not primary_id or primary_id not in all_req_ids:
            primary_id = all_req_ids[0]

        to_delete_ids = [rid for rid in all_req_ids if rid != primary_id]

        return self.executor.merge_requirements(
            session_id=session_id,
            primary_req_id=primary_id,
            to_delete_req_ids=to_delete_ids,
            merged_text=decision.merged_text,
            merged_level=decision.merged_level or group.level,
            reason=decision.reason,
        )

    def execute_merge(
        self,
        session_id: str,
        primary_req_id: str,
        to_delete_req_ids: List[str],
        merged_text: str,
        merged_level: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        执行合并操作（用户确认后手动调用）

        Args:
            session_id: 会话ID
            primary_req_id: 保留的主需求ID
            to_delete_req_ids: 要删除的需求ID列表
            merged_text: 合并后的需求文本
            merged_level: 合并后的需求层级
            reason: 合并原因

        Returns:
            合并结果
        """
        result = self.executor.merge_requirements(
            session_id=session_id,
            primary_req_id=primary_req_id,
            to_delete_req_ids=to_delete_req_ids,
            merged_text=merged_text,
            merged_level=merged_level,
            reason=reason,
        )
        return asdict(result)

    def delete_requirements(
        self,
        session_id: str,
        req_ids: List[str],
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        批量删除需求

        Args:
            session_id: 会话ID
            req_ids: 要删除的需求ID列表
            reason: 删除原因

        Returns:
            删除结果
        """
        return self.executor.delete_requirements(
            session_id=session_id,
            req_ids=req_ids,
            reason=reason,
        )

    def update_requirement(
        self,
        session_id: str,
        req_id: str,
        new_text: str,
        new_level: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        更新单个需求

        Args:
            session_id: 会话ID
            req_id: 需求ID
            new_text: 新的需求文本
            new_level: 新的需求层级（可选）
            reason: 更新原因

        Returns:
            更新结果
        """
        return self.executor.update_requirement_text(
            session_id=session_id,
            req_id=req_id,
            new_text=new_text,
            new_level=new_level,
            reason=reason,
        )

    def get_similar_pairs(
        self,
        session_id: str,
        level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取所有相似的需求对（不分组）

        用于详细展示每一对相似需求

        Args:
            session_id: 会话ID
            level: 限定层级（可选）

        Returns:
            相似配对列表
        """
        all_reqs = self.data_access.get_all_requirements_for_session(session_id)

        if level and level in ("L1", "L2", "L3"):
            all_reqs = [r for r in all_reqs if r.get("level") == level]

        pairs = self.detector.find_similar_pairs(all_reqs, by_level=True)

        return {
            "pairs": pairs,
            "total_pairs": len(pairs),
            "total_requirements_scanned": len(all_reqs),
        }

    def regenerate_llm_decision(
        self,
        session_id: str,
        req_ids: List[str],
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        为指定的需求重新生成LLM合并建议

        Args:
            session_id: 会话ID
            req_ids: 需求ID列表
            model_name: 使用的模型

        Returns:
            LLM决策结果
        """
        model = model_name or self.default_model

        # 获取需求详情
        requirements = self.executor.get_requirements_by_ids(session_id, req_ids)

        if len(requirements) < 2:
            return {
                "error": "需要至少2个需求才能生成合并建议",
                "requirements_found": len(requirements),
            }

        # 确定层级（取第一个需求的层级）
        level = requirements[0].get("level", "L2")

        # 计算相似度
        if len(requirements) == 2:
            similarity = self.detector._compute_similarity(
                requirements[0].get("text", ""),
                requirements[1].get("text", ""),
            )
        else:
            # 多个需求时计算平均相似度
            total_sim = 0
            count = 0
            for i in range(len(requirements)):
                for j in range(i + 1, len(requirements)):
                    sim = self.detector._compute_similarity(
                        requirements[i].get("text", ""),
                        requirements[j].get("text", ""),
                    )
                    total_sim += sim
                    count += 1
            similarity = total_sim / count if count > 0 else 0

        # 调用LLM
        decision = self.merger.decide_merge(
            {
                "level": level,
                "requirements": requirements,
                "similarity": similarity,
            },
            model_name=model,
        )

        return {
            "requirements": requirements,
            "similarity": round(similarity, 4),
            "llm_decision": {
                "should_merge": decision.should_merge,
                "merged_text": decision.merged_text,
                "merged_level": decision.merged_level,
                "primary_req_id": decision.primary_req_id,
                "reason": decision.reason,
                "error": decision.error,
            },
        }
