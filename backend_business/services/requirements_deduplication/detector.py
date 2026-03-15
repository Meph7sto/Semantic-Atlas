"""
Duplicate detector for requirements deduplication service.

Uses difflib SequenceMatcher for text similarity comparison.
Groups requirements by level (L1/L2/L3) and performs pairwise comparison.
"""

import difflib
import re
from typing import Any, Dict, List, Set, Tuple

from .models import DuplicateGroup


class DuplicateDetector:
    """
    重复需求检测器

    使用 difflib 进行文本相似度比较，支持按层级分组检测。
    """

    # 默认相似度阈值
    DEFAULT_SIMILARITY_THRESHOLD = 0.85

    def __init__(self, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        """
        初始化检测器

        Args:
            similarity_threshold: 相似度阈值，>=该值视为重复 (默认0.85)
        """
        self.similarity_threshold = similarity_threshold

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        归一化文本用于相似度比较

        - 转小写
        - 移除多余空白
        - 移除标点符号
        """
        normalized = text.strip().lower()
        # 移除所有空白
        normalized = re.sub(r"\s+", "", normalized)
        # 移除中英文标点
        normalized = re.sub(
            r"[，,。.!！？?；;:：\-—（）()\[\]【】\"'`、/\\]", "", normalized
        )
        return normalized

    def _compute_similarity(self, text_a: str, text_b: str) -> float:
        """
        计算两个需求文本的相似度

        Args:
            text_a: 第一个需求文本
            text_b: 第二个需求文本

        Returns:
            相似度 (0.0 ~ 1.0)
        """
        norm_a = self._normalize_text(text_a)
        norm_b = self._normalize_text(text_b)

        # 空文本处理
        if not norm_a or not norm_b:
            return 0.0

        return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

    def detect_duplicates(
        self,
        requirements: List[Dict[str, Any]],
        by_level: bool = True,
    ) -> List[DuplicateGroup]:
        """
        检测重复需求

        Args:
            requirements: 需求列表，每项必须包含 req_id, level, text
            by_level: 是否按层级分组检测（推荐True，避免跨层级误报）

        Returns:
            重复组列表
        """
        if not requirements:
            return []

        if by_level:
            # 按层级分组
            level_groups: Dict[str, List[Dict[str, Any]]] = {
                "L1": [],
                "L2": [],
                "L3": [],
            }
            for req in requirements:
                level = req.get("level", "")
                if level in level_groups:
                    level_groups[level].append(req)

            # 分别检测每个层级
            all_groups: List[DuplicateGroup] = []
            for level, reqs in level_groups.items():
                if len(reqs) > 1:
                    groups = self._detect_in_group(reqs, level)
                    all_groups.extend(groups)

            return all_groups
        else:
            return self._detect_in_group(requirements, "ALL")

    def _detect_in_group(
        self,
        requirements: List[Dict[str, Any]],
        level: str,
    ) -> List[DuplicateGroup]:
        """
        在同一组内检测重复

        使用 Union-Find 合并重叠的重复对

        Args:
            requirements: 需求列表
            level: 层级标识

        Returns:
            重复组列表
        """
        if len(requirements) < 2:
            return []

        n = len(requirements)

        # 建立索引映射
        req_id_to_idx: Dict[str, int] = {
            req["req_id"]: i for i, req in enumerate(requirements)
        }

        # Union-Find 数据结构
        parent = list(range(n))

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # 相似度矩阵（只存储超过阈值的）
        similarity_pairs: List[Tuple[int, int, float]] = []

        # O(n²) 两两比较
        for i in range(n):
            for j in range(i + 1, n):
                text_a = requirements[i].get("text", "")
                text_b = requirements[j].get("text", "")

                similarity = self._compute_similarity(text_a, text_b)

                if similarity >= self.similarity_threshold:
                    union(i, j)
                    similarity_pairs.append((i, j, similarity))

        # 收集分组
        groups_map: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in groups_map:
                groups_map[root] = []
            groups_map[root].append(i)

        # 构建结果（只返回多于1个成员的组）
        groups: List[DuplicateGroup] = []
        group_counter = 0

        for root, member_indices in groups_map.items():
            if len(member_indices) < 2:
                continue

            # 获取组内需求
            group_reqs = [requirements[i] for i in member_indices]

            # 计算组内平均相似度
            avg_similarity = self._calculate_group_similarity(
                member_indices, similarity_pairs
            )

            # 选择最长的文本作为代表
            representative = max(group_reqs, key=lambda r: len(r.get("text", "")))

            groups.append(
                DuplicateGroup(
                    group_id=f"dup_{level}_{group_counter}",
                    level=level,
                    requirements=group_reqs,
                    similarity=avg_similarity,
                    representative_text=representative.get("text", ""),
                )
            )
            group_counter += 1

        return groups

    def _calculate_group_similarity(
        self,
        member_indices: List[int],
        similarity_pairs: List[Tuple[int, int, float]],
    ) -> float:
        """
        计算组内平均相似度

        Args:
            member_indices: 组内成员的索引列表
            similarity_pairs: 所有相似度超过阈值的配对

        Returns:
            平均相似度
        """
        member_set: Set[int] = set(member_indices)
        relevant_similarities: List[float] = []

        for i, j, sim in similarity_pairs:
            if i in member_set and j in member_set:
                relevant_similarities.append(sim)

        if not relevant_similarities:
            return self.similarity_threshold  # 默认返回阈值

        return sum(relevant_similarities) / len(relevant_similarities)

    def find_similar_pairs(
        self,
        requirements: List[Dict[str, Any]],
        by_level: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        查找所有相似的需求对（不分组，直接返回配对）

        用于调试或详细展示

        Args:
            requirements: 需求列表
            by_level: 是否按层级分组检测

        Returns:
            相似配对列表 [{"req_1": {...}, "req_2": {...}, "similarity": 0.9}]
        """
        pairs: List[Dict[str, Any]] = []

        if by_level:
            level_groups: Dict[str, List[Dict[str, Any]]] = {
                "L1": [],
                "L2": [],
                "L3": [],
            }
            for req in requirements:
                level = req.get("level", "")
                if level in level_groups:
                    level_groups[level].append(req)

            for level, reqs in level_groups.items():
                pairs.extend(self._find_pairs_in_group(reqs))
        else:
            pairs = self._find_pairs_in_group(requirements)

        # 按相似度降序排序
        pairs.sort(key=lambda p: p["similarity"], reverse=True)
        return pairs

    def _find_pairs_in_group(
        self,
        requirements: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """在组内查找所有相似配对"""
        pairs: List[Dict[str, Any]] = []
        n = len(requirements)

        for i in range(n):
            for j in range(i + 1, n):
                text_a = requirements[i].get("text", "")
                text_b = requirements[j].get("text", "")

                similarity = self._compute_similarity(text_a, text_b)

                if similarity >= self.similarity_threshold:
                    pairs.append(
                        {
                            "req_1": requirements[i],
                            "req_2": requirements[j],
                            "similarity": round(similarity, 4),
                        }
                    )

        return pairs
