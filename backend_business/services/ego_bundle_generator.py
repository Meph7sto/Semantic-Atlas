"""
EgoBundle 生成器
支持基于序列窗口和图邻域两种策略生成以锚点为中心的上下文包
"""
import hashlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class EgoBundleGenerator:
    """
    生成 EgoBundle: 以锚点 span 为中心的上下文包
    支持两种策略:
    1. 序列窗口: 基于索引的滑动窗口 (anchor ± r)
    2. 图邻域: 基于关联图的 1-hop 或 2-hop 邻居
    """

    def __init__(
        self,
        max_spans_per_bundle: int = 12,
        token_limit: Optional[int] = 1500,
    ):
        """
        Args:
            max_spans_per_bundle: 单个 bundle 最多包含的 span 数量
            token_limit: 单个 bundle 的大概 token 上限（字数近似）
        """
        self.max_spans_per_bundle = max_spans_per_bundle
        self.token_limit = token_limit

    def select_anchors(
        self,
        spans: List[Dict[str, Any]],
        strategy: str = "all",
        keywords: Optional[List[str]] = None,
    ) -> List[int]:
        """
        选择锚点集合

        Args:
            spans: span 列表，已按 start_ms 或 span_index 排序
            strategy: 锚点选择策略
                - "all": 每个 span 都作为锚点
                - "keyword": 只选择包含特定关键词的 span
                - "informative": 选择信息量大的 span（长度较长或包含关键词）
            keywords: 关键词列表，用于 keyword/informative 策略

        Returns:
            锚点索引列表
        """
        if strategy == "all":
            return list(range(len(spans)))

        if keywords is None:
            keywords = ["要", "需要", "必须", "应该", "决定", "改成", "提升", "优化", "实现"]

        anchors = []
        for i, span in enumerate(spans):
            text = span.get("text", "")
            # keyword 策略：包含关键词
            if strategy == "keyword":
                if any(kw in text for kw in keywords):
                    anchors.append(i)
            # informative 策略：包含关键词或文本较长
            elif strategy == "informative":
                if any(kw in text for kw in keywords) or len(text) >= 150:
                    anchors.append(i)

        # 如果没有选中任何锚点，退化为 all 策略
        return anchors if anchors else list(range(len(spans)))

    def generate_sequence_bundle(
        self,
        spans: List[Dict[str, Any]],
        anchor_idx: int,
        r: int = 2,
    ) -> Dict[str, Any]:
        """
        基于序列窗口生成 EgoBundle

        Args:
            spans: span 列表
            anchor_idx: 锚点索引
            r: 窗口半径（取 anchor ± r 范围）

        Returns:
            EgoBundle 字典
        """
        n = len(spans)
        left = max(0, anchor_idx - r)
        right = min(n - 1, anchor_idx + r)

        bundle_spans = spans[left : right + 1]

        # 如果超出限制，优先保留离锚点近的
        bundle_spans = self._trim_bundle(bundle_spans, anchor_idx - left)

        # 生成短引用映射 S1..Sn
        span_refs = [f"S{i+1}" for i in range(len(bundle_spans))]

        return {
            "anchor_span_id": spans[anchor_idx]["span_id"],
            "anchor_idx": anchor_idx,
            "r": r,
            "strategy": "sequence",
            "spans": bundle_spans,
            "span_refs": span_refs,
            "ref_mapping": {
                span_refs[i]: bundle_spans[i]["span_id"] for i in range(len(bundle_spans))
            },
        }

    def generate_graph_bundle(
        self,
        spans: List[Dict[str, Any]],
        anchor_idx: int,
        adjacency: Dict[str, List[Tuple[str, str, float]]],
        hop: int = 1,
        top_m_2hop: int = 5,
    ) -> Dict[str, Any]:
        """
        基于图邻域生成 EgoBundle

        Args:
            spans: span 列表
            anchor_idx: 锚点索引
            adjacency: 邻接表 {span_id: [(target_span_id, relation_type, strength), ...]}
            hop: 跳数 (1 或 2)
            top_m_2hop: 2-hop 时最多保留的二跳邻居数量

        Returns:
            EgoBundle 字典
        """
        anchor_span = spans[anchor_idx]
        anchor_id = anchor_span["span_id"]

        # 构建 span_id -> span 映射
        span_map = {s["span_id"]: s for s in spans}

        # 1-hop 邻居
        neighbors_1hop = set()
        if anchor_id in adjacency:
            for target_id, _, _ in adjacency[anchor_id]:
                if target_id in span_map:
                    neighbors_1hop.add(target_id)

        # 反向边：谁指向锚点
        for src_id, edges in adjacency.items():
            for tgt_id, _, _ in edges:
                if tgt_id == anchor_id and src_id in span_map:
                    neighbors_1hop.add(src_id)

        # Ego(a, 1) = {a} ∪ N1(a)
        bundle_ids = {anchor_id} | neighbors_1hop

        # 2-hop 邻居
        if hop == 2:
            neighbors_2hop = []
            for n1_id in neighbors_1hop:
                if n1_id in adjacency:
                    for n2_id, _, strength in adjacency[n1_id]:
                        if n2_id not in bundle_ids and n2_id in span_map:
                            # 计算二跳强度（取最小或平均）
                            # 这里简化为直接用当前边的强度
                            neighbors_2hop.append((n2_id, strength))

            # 按强度排序，取 Top-M
            neighbors_2hop.sort(key=lambda x: x[1], reverse=True)
            for n2_id, _ in neighbors_2hop[:top_m_2hop]:
                bundle_ids.add(n2_id)

        # 按原始顺序排列
        bundle_spans = [s for s in spans if s["span_id"] in bundle_ids]

        # Trim
        anchor_local_idx = next(
            (i for i, s in enumerate(bundle_spans) if s["span_id"] == anchor_id), 0
        )
        bundle_spans = self._trim_bundle(bundle_spans, anchor_local_idx)

        # 生成短引用
        span_refs = [f"S{i+1}" for i in range(len(bundle_spans))]

        return {
            "anchor_span_id": anchor_id,
            "anchor_idx": anchor_idx,
            "r": hop,
            "strategy": "graph",
            "spans": bundle_spans,
            "span_refs": span_refs,
            "ref_mapping": {
                span_refs[i]: bundle_spans[i]["span_id"] for i in range(len(bundle_spans))
            },
        }

    def _trim_bundle(self, bundle_spans: List[Dict[str, Any]], anchor_local_idx: int) -> List[Dict[str, Any]]:
        """
        根据大小限制修剪 bundle，优先保留离锚点近的 span

        Args:
            bundle_spans: bundle 中的 span 列表
            anchor_local_idx: 锚点在 bundle 中的局部索引

        Returns:
            修剪后的 span 列表
        """
        # 按数量限制
        if len(bundle_spans) <= self.max_spans_per_bundle:
            trimmed = bundle_spans
        else:
            # 优先保留锚点附近的
            distances = [(abs(i - anchor_local_idx), i) for i in range(len(bundle_spans))]
            distances.sort()
            keep_indices = sorted([idx for _, idx in distances[: self.max_spans_per_bundle]])
            trimmed = [bundle_spans[i] for i in keep_indices]

        # 按 token 限制（简单字数估算）
        if self.token_limit:
            total_chars = sum(len(s.get("text", "")) for s in trimmed)
            if total_chars > self.token_limit:
                # 从远端开始丢弃
                anchor_in_trimmed = next(
                    (i for i, s in enumerate(trimmed) if s == bundle_spans[anchor_local_idx]),
                    0,
                )
                distances = [(abs(i - anchor_in_trimmed), i) for i in range(len(trimmed))]
                distances.sort()

                kept = []
                chars = 0
                for _, idx in distances:
                    span_text = trimmed[idx].get("text", "")
                    if chars + len(span_text) <= self.token_limit:
                        kept.append(idx)
                        chars += len(span_text)
                    else:
                        break

                kept.sort()
                trimmed = [trimmed[i] for i in kept]

        return trimmed

    def build_adjacency_from_edges(
        self, edges: List[Dict[str, Any]]
    ) -> Dict[str, List[Tuple[str, str, float]]]:
        """
        从边列表构建邻接表

        Args:
            edges: 边列表，每条边包含 source_span_id, target_span_id, relation_type, strength

        Returns:
            邻接表 {span_id: [(target_span_id, relation_type, strength), ...]}
        """
        adjacency: Dict[str, List[Tuple[str, str, float]]] = {}

        for edge in edges:
            src = edge["source_span_id"]
            tgt = edge["target_span_id"]
            rel = edge["relation_type"]
            strength = edge["strength"]

            if src not in adjacency:
                adjacency[src] = []
            adjacency[src].append((tgt, rel, strength))

        return adjacency
