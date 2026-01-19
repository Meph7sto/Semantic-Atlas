"""
Phase 2: 基于关联图的语义分拣与动态打包 (Graph-based Context Building)

核心职责:
1. 从DB读取session下的spans
2. 滑动窗口 + 短引用 -> LLM产边
3. 物理约束剪枝
4. 连通分量计算
5. Orphan吸附
6. 动态打包 (Bin Packing)
7. 落库: context_runs, span_links, bundles, bundle_items
"""

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Set, Tuple
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

from backend_business.config import settings


# ========================
# 配置与常量
# ========================

RELATION_TYPES = frozenset(["continuation", "elaboration", "dependency", "same_topic", "conflict"])

# 关系类型优先级（裁剪时保留高优先级）
RELATION_PRIORITY = {
    "conflict": 5,
    "continuation": 4,
    "dependency": 4,
    "elaboration": 2,
    "same_topic": 1,
}

# 默认参数
DEFAULT_OPTIONS = {
    "window_size": 8,
    "step_size": 7,
    "tau": 0.60,
    "top_k": 3,
    "max_edges_per_window": 24,
    "token_limit_per_bundle": 4000,
    "mock_llm": False,
    "llm_model": None,
}


def _resolve_llm_model(options: Dict[str, Any]) -> Optional[str]:
    raw_model = options.get("llm_model")
    if isinstance(raw_model, str) and raw_model.strip():
        return raw_model.strip()
    if options.get("use_thinking_mode"):
        return "deepseek-reasoner"
    return None


@dataclass
class Edge:
    """图边数据结构"""
    source_span_id: str
    target_span_id: str
    relation_type: str
    strength: float
    note: str = ""
    source_order: int = 0  # 用于距离偏好
    target_order: int = 0


@dataclass
class Span:
    """Span数据结构"""
    span_id: str
    session_id: str
    start_ms: Optional[int]
    end_ms: Optional[int]
    speaker: Optional[str]
    text: str
    order_index: int = 0  # 在session内的顺序


@dataclass 
class SSEEvent:
    """SSE事件封装"""
    event: str
    data: Dict[str, Any]


# ========================
# LLM Prompt 模板
# ========================

SYSTEM_PROMPT_LINK = """你是一个语义关系分析专家。你需要分析给定的对话片段之间的语义关联关系。

## 关系类型（只能选择以下5种）:
- continuation: 延续 - 后续内容是对前文的自然延续
- elaboration: 补充/细化 - 对之前观点的详细展开或补充说明
- dependency: 依赖 - 后文依赖前文的信息才能理解（有向）
- same_topic: 同主题弱连接 - 讨论相同主题但无强逻辑关联
- conflict: 冲突 - 两个片段之间存在矛盾或冲突

## 输出格式要求:
你必须输出一个JSON对象，包含两个数组：
1. "links": 边列表，每条边包含:
   - "source": 源片段短引用（如"S1"）
   - "target": 目标片段短引用（如"S2"）
   - "type": 关系类型（只能是上述5种之一）
   - "strength": 关联强度（0.0-1.0之间的小数）
   - "note": 简短理由（可选）

2. "noise": 噪音片段列表（无意义的片段引用，如["S3"]），可为空数组

## 重要约束:
- source和target必须使用给定的短引用（S1, S2, ...），不能使用其他标识
- 不要输出自环（source等于target）
- strength必须在0.0到1.0之间
- 只输出JSON，不要有其他文字

## 示例输出:
```json
{
  "links": [
    {"source": "S1", "target": "S2", "type": "continuation", "strength": 0.85, "note": "自然延续讨论"},
    {"source": "S1", "target": "S3", "type": "elaboration", "strength": 0.70, "note": "S3补充说明S1"}
  ],
  "noise": ["S4"]
}
```
"""


def _build_window_prompt(spans: List[Span], ref_map: Dict[str, str]) -> str:
    """构建窗口内的用户提示"""
    lines = ["请分析以下对话片段之间的语义关联关系：\n"]
    for span in spans:
        ref = ref_map[span.span_id]
        time_info = f"{span.start_ms}-{span.end_ms}" if span.start_ms is not None else "?"
        speaker = span.speaker or "unknown"
        lines.append(f"[{ref}] [{time_info}] [{speaker}]: {span.text}")
    lines.append("\n请输出JSON格式的分析结果。")
    return "\n".join(lines)


# ========================
# LLM 客户端（复用DeepSeek引擎）
# ========================

class LLMClient:
    """LLM客户端，用于产边"""
    
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode or os.environ.get("MOCK_LLM_CONTEXT_BUILDING", "").lower() in ("1", "true")
        self._engine = None
    
    def _get_engine(self):
        """懒加载DeepSeek引擎"""
        if self._engine is None:
            # 动态导入避免循环依赖
            from backend_inference.core.model_container import model_engine
            self._engine = model_engine
        return self._engine

    def _collect_stream_text(self, stream) -> str:
        chunks = []
        for event in stream:
            if isinstance(event, dict):
                if event.get("type") == "thinking":
                    continue
                delta = event.get("delta") or event.get("content")
                if delta:
                    chunks.append(str(delta))
            elif isinstance(event, (bytes, bytearray)):
                chunks.append(event.decode("utf-8", errors="ignore"))
            elif isinstance(event, str):
                chunks.append(event)
        return "".join(chunks).strip()

    def _generate_text(self, engine, prompt: str, model_name: Optional[str]) -> str:
        if model_name:
            stream = engine.generate_stream(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_LINK,
                max_new_tokens=1500,
                model=model_name
            )
            text = self._collect_stream_text(stream)
            if text:
                return text
        return engine.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_LINK,
            max_new_tokens=1500
        )
    
    def generate_links(
        self,
        spans: List[Span],
        ref_map: Dict[str, str],
        model_name: Optional[str] = None
    ) -> Tuple[List[Dict], List[str]]:
        """
        调用LLM生成边列表
        
        Returns:
            (links, noise_refs): 边列表和噪音短引用列表
        """
        if self.mock_mode:
            return self._mock_generate(spans, ref_map)
        
        prompt = _build_window_prompt(spans, ref_map)
        engine = self._get_engine()
        
        try:
            response = self._generate_text(engine, prompt, model_name)
            return self._parse_llm_response(response)
        except Exception as e:
            print(f"[LLMClient] Error calling LLM: {e}")
            return [], []
    
    def _mock_generate(self, spans: List[Span], ref_map: Dict[str, str]) -> Tuple[List[Dict], List[str]]:
        """Mock模式：生成少量边用于测试流程"""
        links = []
        refs = list(ref_map.values())
        
        # 相邻span之间创建continuation边
        for i in range(len(refs) - 1):
            links.append({
                "source": refs[i],
                "target": refs[i + 1],
                "type": "continuation",
                "strength": 0.75,
                "note": "mock continuation"
            })
        
        return links, []
    
    def _parse_llm_response(self, response: str) -> Tuple[List[Dict], List[str]]:
        """解析LLM的JSON响应"""
        links = []
        noise = []
        
        # 尝试提取JSON
        response = response.strip()
        
        # 移除可能的markdown代码块标记
        if response.startswith("```"):
            lines = response.split("\n")
            # 找到第一行和最后一行的```
            start_idx = 0
            end_idx = len(lines)
            for i, line in enumerate(lines):
                if line.strip().startswith("```") and i == 0:
                    start_idx = 1
                elif line.strip() == "```":
                    end_idx = i
                    break
            response = "\n".join(lines[start_idx:end_idx])
        
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 尝试用正则提取JSON对象
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    print(f"[LLMClient] Failed to parse JSON: {response[:200]}")
                    return [], []
            else:
                print(f"[LLMClient] No JSON found in response: {response[:200]}")
                return [], []
        
        # 解析links
        raw_links = data.get("links", [])
        if isinstance(raw_links, list):
            for item in raw_links:
                if isinstance(item, dict):
                    link = {
                        "source": str(item.get("source", "")),
                        "target": str(item.get("target", "")),
                        "type": str(item.get("type", "")),
                        "strength": float(item.get("strength", 0)),
                        "note": str(item.get("note", ""))
                    }
                    # 验证关系类型
                    if link["type"] in RELATION_TYPES:
                        links.append(link)
        
        # 解析noise
        raw_noise = data.get("noise", [])
        if isinstance(raw_noise, list):
            noise = [str(n) for n in raw_noise if isinstance(n, str) or isinstance(n, int)]
        
        return links, noise


# ========================
# 图算法：连通分量
# ========================

class UnionFind:
    """并查集，用于计算连通分量"""
    
    def __init__(self):
        self.parent = {}
        self.rank = {}
    
    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
    
    def get_components(self) -> Dict[str, List[str]]:
        """返回 {root: [members]} 的映射"""
        components = defaultdict(list)
        for node in self.parent:
            root = self.find(node)
            components[root].append(node)
        return dict(components)


# ========================
# ContextBuilder 核心类
# ========================

class ContextBuilder:
    """
    Phase 2 核心构建器
    """
    
    def __init__(self, dsn: str = None):
        self.dsn = dsn or settings.POSTGRES_DSN
        self.llm_client = None
    
    def _connect(self):
        return psycopg2.connect(self.dsn)
    
    def _get_llm_client(self, mock_mode: bool) -> LLMClient:
        if self.llm_client is None or self.llm_client.mock_mode != mock_mode:
            self.llm_client = LLMClient(mock_mode=mock_mode)
        return self.llm_client
    
    # ========================
    # 数据加载
    # ========================
    
    def load_spans(self, session_id: str) -> List[Span]:
        """从DB加载session下的所有spans，按时间/顺序排序"""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT span_id, session_id, start_ms, end_ms, speaker, text
                    FROM spans
                    WHERE session_id = %s
                    ORDER BY COALESCE(start_ms, 0), created_at
                    """,
                    (session_id,)
                )
                rows = cur.fetchall()
        
        spans = []
        for idx, row in enumerate(rows):
            spans.append(Span(
                span_id=row["span_id"],
                session_id=row["session_id"],
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                speaker=row["speaker"],
                text=row["text"],
                order_index=idx
            ))
        return spans
    
    # ========================
    # 窗口滑动与短引用
    # ========================
    
    def generate_windows(
        self, 
        spans: List[Span], 
        window_size: int, 
        step_size: int
    ) -> Generator[Tuple[List[Span], Dict[str, str]], None, None]:
        """
        生成滑动窗口，每个窗口返回 (spans子集, ref_map)
        ref_map: span_id -> "S1", "S2", ...
        """
        n = len(spans)
        if n == 0:
            return
        
        start = 0
        while start < n:
            end = min(start + window_size, n)
            window_spans = spans[start:end]
            
            # 生成短引用
            ref_map = {}
            for i, span in enumerate(window_spans):
                ref_map[span.span_id] = f"S{i + 1}"
            
            yield window_spans, ref_map
            
            if end >= n:
                break
            start += step_size
    
    # ========================
    # 边解析与清洗
    # ========================
    
    def parse_window_edges(
        self,
        raw_links: List[Dict],
        ref_map: Dict[str, str],
        window_spans: List[Span]
    ) -> List[Edge]:
        """
        将LLM输出的边解析并映射回真实span_id
        执行基础清洗：去自环、去重
        """
        # 构建反向映射 ref -> span_id
        reverse_map = {ref: span_id for span_id, ref in ref_map.items()}
        
        # span_id -> order_index
        order_map = {s.span_id: s.order_index for s in window_spans}
        
        edge_map = {}  # (source, target, type) -> Edge
        
        for link in raw_links:
            source_ref = link.get("source", "")
            target_ref = link.get("target", "")
            rel_type = link.get("type", "")
            strength = link.get("strength", 0)
            note = link.get("note", "")
            
            # 映射到真实span_id
            source_id = reverse_map.get(source_ref)
            target_id = reverse_map.get(target_ref)
            
            if not source_id or not target_id:
                continue
            
            # 去自环
            if source_id == target_id:
                continue
            
            # 验证关系类型
            if rel_type not in RELATION_TYPES:
                continue
            
            # 验证strength范围
            strength = max(0.0, min(1.0, float(strength)))
            
            # 去重（保留strength最大的）
            key = (source_id, target_id, rel_type)
            candidate = Edge(
                source_span_id=source_id,
                target_span_id=target_id,
                relation_type=rel_type,
                strength=strength,
                note=note,
                source_order=order_map.get(source_id, 0),
                target_order=order_map.get(target_id, 0)
            )
            existing = edge_map.get(key)
            if existing is None or candidate.strength >= existing.strength:
                edge_map[key] = candidate
        
        return list(edge_map.values())
    
    # ========================
    # 物理约束剪枝
    # ========================
    
    def prune_edges(
        self,
        edges: List[Edge],
        tau: float,
        top_k: int,
        max_edges: int
    ) -> List[Edge]:
        """
        应用物理约束剪枝：
        1. 置信度过滤 (tau)
        2. Top-K per node
        3. 总数上限
        """
        # 1. 置信度过滤
        edges = [e for e in edges if e.strength >= tau]
        
        if not edges:
            return []
        
        # 2. Top-K per node (基于strength，同strength按距离近优先)
        # 对每个节点（作为source或target）保留最强的top_k条边
        node_edges = defaultdict(list)
        for e in edges:
            node_edges[e.source_span_id].append(e)
            node_edges[e.target_span_id].append(e)
        
        def top_k_score(e: Edge) -> Tuple:
            distance = abs(e.target_order - e.source_order)
            return (e.strength, -distance)
        
        kept_edges = set()
        for node, node_edge_list in node_edges.items():
            # 按强度排序，同强度时距离更近优先
            sorted_edges = sorted(node_edge_list, key=top_k_score, reverse=True)
            for e in sorted_edges[:top_k]:
                kept_edges.add((e.source_span_id, e.target_span_id, e.relation_type))
        
        edges = [e for e in edges if (e.source_span_id, e.target_span_id, e.relation_type) in kept_edges]
        
        # 3. 总数上限（需要时按关系类型优先级裁剪）
        if len(edges) > max_edges:
            def truncate_score(e: Edge) -> Tuple:
                priority = RELATION_PRIORITY.get(e.relation_type, 0)
                distance = abs(e.target_order - e.source_order)
                return (priority, e.strength, -distance)
            edges = sorted(edges, key=truncate_score, reverse=True)[:max_edges]
        
        return edges
    
    # ========================
    # 连通分量与Orphan吸附
    # ========================
    
    def compute_components(
        self,
        spans: List[Span],
        edges: List[Edge],
        noise_span_ids: Set[str]
    ) -> Tuple[Dict[str, List[str]], List[str]]:
        """
        计算连通分量，返回 (components, orphan_ids)
        components: {component_id: [span_ids]}
        orphan_ids: 孤儿节点列表
        """
        # 非NOISE的span_id集合
        valid_span_ids = {s.span_id for s in spans if s.span_id not in noise_span_ids}
        
        # 构建并查集
        uf = UnionFind()
        for span_id in valid_span_ids:
            uf.find(span_id)  # 初始化
        
        # 根据边连接节点（投影为无向图）
        for edge in edges:
            if edge.source_span_id in valid_span_ids and edge.target_span_id in valid_span_ids:
                uf.union(edge.source_span_id, edge.target_span_id)
        
        # 获取连通分量
        raw_components = uf.get_components()
        
        # 识别孤儿节点（只有自己的分量）
        orphan_ids = []
        components = {}
        for root, members in raw_components.items():
            if len(members) == 1:
                orphan_ids.append(members[0])
            else:
                components[root] = members
        
        return components, orphan_ids
    
    def absorb_orphans(
        self,
        spans: List[Span],
        components: Dict[str, List[str]],
        orphan_ids: List[str]
    ) -> Dict[str, List[str]]:
        """
        Orphan吸附：将孤儿节点吸附到邻居所在的component
        """
        if not orphan_ids:
            return components
        
        # span_id -> order_index
        order_map = {s.span_id: s.order_index for s in spans}
        # order_index -> span_id
        index_to_span = {s.order_index: s.span_id for s in spans}
        # span_id -> component_root
        span_to_component = {}
        for root, members in components.items():
            for span_id in members:
                span_to_component[span_id] = root
        
        # C_misc 兜底分量
        misc_component_id = "__MISC__"
        
        for orphan_id in orphan_ids:
            orphan_order = order_map.get(orphan_id, -1)
            absorbed = False
            
            # 尝试吸附到前一个或后一个邻居的component
            for delta in [-1, 1]:
                neighbor_order = orphan_order + delta
                neighbor_id = index_to_span.get(neighbor_order)
                if neighbor_id and neighbor_id in span_to_component:
                    target_root = span_to_component[neighbor_id]
                    components[target_root].append(orphan_id)
                    span_to_component[orphan_id] = target_root
                    absorbed = True
                    break
            
            # 无法吸附则归入misc
            if not absorbed:
                if misc_component_id not in components:
                    components[misc_component_id] = []
                components[misc_component_id].append(orphan_id)
                span_to_component[orphan_id] = misc_component_id
        
        return components
    
    # ========================
    # 动态打包
    # ========================
    
    def estimate_tokens(self, text: str) -> int:
        """简单估算token数（字符数/4）"""
        return len(text) // 4 + 1
    
    def pack_bundles(
        self,
        spans: List[Span],
        components: Dict[str, List[str]],
        token_limit: int,
        context_run_id: str,
        session_id: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        动态打包，返回 (bundles, bundle_items)
        
        bundles: [{bundle_id, context_run_id, session_id, order_index, meta, spans}]
        bundle_items: [{bundle_id, span_id, span_ref, order_index}]
        """
        # span_id -> Span
        span_map = {s.span_id: s for s in spans}
        
        # 按component最早时间排序
        def component_earliest_time(component_id: str) -> int:
            members = components[component_id]
            times = [span_map[sid].start_ms or 0 for sid in members if sid in span_map]
            return min(times) if times else 0
        
        sorted_component_ids = sorted(components.keys(), key=component_earliest_time)
        
        bundles = []
        bundle_items = []
        current_bundle_spans = []
        current_tokens = 0
        
        def finalize_bundle(bundle_spans: List[Span], meta: Dict = None):
            """封装当前bundle"""
            if not bundle_spans:
                return
            
            bundle_id = str(uuid4())
            order_index = len(bundles) + 1
            
            # 按时间排序
            sorted_spans = sorted(bundle_spans, key=lambda s: (s.start_ms or 0, s.order_index))
            
            bundles.append({
                "bundle_id": bundle_id,
                "context_run_id": context_run_id,
                "session_id": session_id,
                "order_index": order_index,
                "status": "READY",
                "meta": meta or {},
                "spans": sorted_spans
            })
            
            # 生成bundle内短引用
            for i, span in enumerate(sorted_spans):
                bundle_items.append({
                    "bundle_id": bundle_id,
                    "span_id": span.span_id,
                    "span_ref": f"S{i + 1}",
                    "order_index": i + 1
                })
        
        for comp_id in sorted_component_ids:
            member_ids = components[comp_id]
            comp_spans = [span_map[sid] for sid in member_ids if sid in span_map]
            
            # 按时间排序
            comp_spans = sorted(comp_spans, key=lambda s: (s.start_ms or 0, s.order_index))
            
            # 估算component总token
            comp_tokens = sum(self.estimate_tokens(s.text) for s in comp_spans)
            
            if comp_tokens > token_limit:
                # Component超大，需要切分
                if current_bundle_spans:
                    finalize_bundle(current_bundle_spans)
                    current_bundle_spans = []
                    current_tokens = 0
                
                # 按时间顺序切分
                sub_spans = []
                sub_tokens = 0
                for span in comp_spans:
                    span_tokens = self.estimate_tokens(span.text)
                    if sub_tokens + span_tokens > token_limit and sub_spans:
                        finalize_bundle(sub_spans, {"continuation_of": comp_id})
                        sub_spans = []
                        sub_tokens = 0
                    sub_spans.append(span)
                    sub_tokens += span_tokens
                
                if sub_spans:
                    finalize_bundle(sub_spans, {"continuation_of": comp_id})
            
            elif current_tokens + comp_tokens > token_limit:
                # 当前bundle放不下，先封包
                finalize_bundle(current_bundle_spans)
                current_bundle_spans = comp_spans[:]
                current_tokens = comp_tokens
            
            else:
                # 放入当前bundle
                current_bundle_spans.extend(comp_spans)
                current_tokens += comp_tokens
        
        # 封装最后一个bundle
        if current_bundle_spans:
            finalize_bundle(current_bundle_spans)
        
        return bundles, bundle_items
    
    # ========================
    # 数据库操作
    # ========================
    
    def create_context_run(
        self, 
        session_id: str, 
        options: Dict[str, Any]
    ) -> str:
        """创建context_run记录，返回context_run_id"""
        context_run_id = str(uuid4())
        
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO context_runs (context_run_id, session_id, options_snapshot, status)
                    VALUES (%s, %s, %s, 'RUNNING')
                    """,
                    (context_run_id, session_id, json.dumps(options, ensure_ascii=False))
                )
        
        return context_run_id
    
    def save_edges(self, context_run_id: str, edges: List[Edge]) -> int:
        """保存边到span_links，返回插入数量"""
        if not edges:
            return 0
        
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 使用 ON CONFLICT DO UPDATE 实现 upsert
                for edge in edges:
                    cur.execute(
                        """
                        INSERT INTO span_links 
                            (context_run_id, source_span_id, target_span_id, relation_type, strength, note)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (context_run_id, source_span_id, target_span_id, relation_type)
                        DO UPDATE SET strength = GREATEST(span_links.strength, EXCLUDED.strength),
                                      note = EXCLUDED.note
                        """,
                        (
                            context_run_id,
                            edge.source_span_id,
                            edge.target_span_id,
                            edge.relation_type,
                            edge.strength,
                            edge.note
                        )
                    )
        
        return len(edges)
    
    def save_bundles(
        self, 
        bundles: List[Dict], 
        bundle_items: List[Dict]
    ) -> int:
        """保存bundles和bundle_items，返回bundle数量"""
        if not bundles:
            return 0
        
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 保存bundles
                for bundle in bundles:
                    cur.execute(
                        """
                        INSERT INTO bundles 
                            (bundle_id, context_run_id, session_id, order_index, status, meta)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            bundle["bundle_id"],
                            bundle["context_run_id"],
                            bundle["session_id"],
                            bundle["order_index"],
                            bundle["status"],
                            json.dumps(bundle.get("meta", {}), ensure_ascii=False)
                        )
                    )
                
                # 保存bundle_items
                for item in bundle_items:
                    cur.execute(
                        """
                        INSERT INTO bundle_items (bundle_id, span_id, span_ref, order_index)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            item["bundle_id"],
                            item["span_id"],
                            item["span_ref"],
                            item["order_index"]
                        )
                    )
        
        return len(bundles)
    
    def update_context_run_status(
        self, 
        context_run_id: str, 
        status: str, 
        stats: Dict[str, Any] = None
    ):
        """更新context_run状态"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE context_runs 
                    SET status = %s, stats = %s
                    WHERE context_run_id = %s
                    """,
                    (status, json.dumps(stats or {}, ensure_ascii=False), context_run_id)
                )
    
    # ========================
    # 主流程
    # ========================
    
    def build_context(
        self,
        session_id: str,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        非流式构建上下文
        
        Returns:
            {
                "context_run_id": str,
                "span_total": int,
                "noise_count": int,
                "edge_count": int,
                "component_count": int,
                "bundle_total": int,
                "bundles_preview": [...]
            }
        """
        # 合并配置
        opts = {**DEFAULT_OPTIONS, **(options or {})}
        window_size = max(5, min(10, opts.get("window_size", 8)))
        step_size = max(1, min(window_size - 1, opts.get("step_size", window_size - 1)))
        tau = max(0.0, min(1.0, opts.get("tau", 0.6)))
        top_k = max(2, min(5, opts.get("top_k", 3)))
        max_edges_per_window = max(window_size, opts.get("max_edges_per_window", window_size * 3))
        token_limit = max(1000, opts.get("token_limit_per_bundle", 4000))
        mock_llm = opts.get("mock_llm", False)
        llm_model = _resolve_llm_model(opts)
        
        # 1. 加载spans
        spans = self.load_spans(session_id)
        if not spans:
            raise ValueError(f"No spans found for session_id: {session_id}")
        
        # 2. 创建context_run
        context_run_id = self.create_context_run(session_id, opts)
        
        try:
            # 3. 获取LLM客户端
            llm = self._get_llm_client(mock_llm)
            
            # 4. 滑动窗口产边
            all_edges: List[Edge] = []
            noise_span_ids: Set[str] = set()
            
            for window_spans, ref_map in self.generate_windows(spans, window_size, step_size):
                # LLM产边
                raw_links, noise_refs = llm.generate_links(window_spans, ref_map, llm_model)
                
                # 解析并清洗
                window_edges = self.parse_window_edges(raw_links, ref_map, window_spans)
                
                # 物理约束剪枝
                pruned_edges = self.prune_edges(window_edges, tau, top_k, max_edges_per_window)
                
                all_edges.extend(pruned_edges)
                
                # 记录noise
                reverse_map = {ref: span_id for span_id, ref in ref_map.items()}
                for ref in noise_refs:
                    if ref in reverse_map:
                        noise_span_ids.add(reverse_map[ref])
            
            # 5. 保存边
            self.save_edges(context_run_id, all_edges)
            
            # 6. 计算连通分量
            components, orphan_ids = self.compute_components(spans, all_edges, noise_span_ids)
            
            # 7. Orphan吸附
            components = self.absorb_orphans(spans, components, orphan_ids)
            
            # 8. 动态打包
            bundles, bundle_items = self.pack_bundles(
                spans, components, token_limit, context_run_id, session_id
            )
            
            # 9. CoverageGate检查
            bundled_span_ids = {item["span_id"] for item in bundle_items}
            non_noise_span_ids = {s.span_id for s in spans if s.span_id not in noise_span_ids}
            uncovered = non_noise_span_ids - bundled_span_ids
            
            if uncovered:
                # 兜底：将未覆盖的span放入misc bundle
                misc_spans = [s for s in spans if s.span_id in uncovered]
                if misc_spans:
                    misc_bundle_id = str(uuid4())
                    misc_bundle = {
                        "bundle_id": misc_bundle_id,
                        "context_run_id": context_run_id,
                        "session_id": session_id,
                        "order_index": len(bundles) + 1,
                        "status": "READY",
                        "meta": {"is_misc": True},
                        "spans": misc_spans
                    }
                    bundles.append(misc_bundle)
                    
                    sorted_misc = sorted(misc_spans, key=lambda s: (s.start_ms or 0, s.order_index))
                    for i, span in enumerate(sorted_misc):
                        bundle_items.append({
                            "bundle_id": misc_bundle_id,
                            "span_id": span.span_id,
                            "span_ref": f"S{i + 1}",
                            "order_index": i + 1
                        })
            
            # 10. 保存bundles
            self.save_bundles(bundles, bundle_items)
            
            # 11. 更新状态
            stats = {
                "span_total": len(spans),
                "noise_count": len(noise_span_ids),
                "edge_count": len(all_edges),
                "component_count": len(components),
                "bundle_total": len(bundles),
            }
            self.update_context_run_status(context_run_id, "READY", stats)
            
            # 12. 构建预览
            bundles_preview = []
            for bundle in bundles:
                bundle_text_lines = []
                for item in bundle_items:
                    if item["bundle_id"] == bundle["bundle_id"]:
                        span = next((s for s in bundle.get("spans", []) if s.span_id == item["span_id"]), None)
                        if span:
                            bundle_text_lines.append(f"[{item['span_ref']}] {span.text[:100]}...")
                
                bundles_preview.append({
                    "bundle_id": bundle["bundle_id"],
                    "order_index": bundle["order_index"],
                    "span_count": len([it for it in bundle_items if it["bundle_id"] == bundle["bundle_id"]]),
                    "meta": bundle.get("meta", {}),
                    "bundle_text_preview": "\n".join(bundle_text_lines[:3])
                })
            
            return {
                "context_run_id": context_run_id,
                **stats,
                "bundles_preview": bundles_preview
            }
        
        except Exception as e:
            self.update_context_run_status(context_run_id, "FAILED", {"error": str(e)})
            raise
    
    def build_context_stream(
        self,
        session_id: str,
        options: Dict[str, Any] = None
    ) -> Generator[SSEEvent, None, None]:
        """
        流式构建上下文，yield SSE事件
        """
        # 合并配置
        opts = {**DEFAULT_OPTIONS, **(options or {})}
        window_size = max(5, min(10, opts.get("window_size", 8)))
        step_size = max(1, min(window_size - 1, opts.get("step_size", window_size - 1)))
        tau = max(0.0, min(1.0, opts.get("tau", 0.6)))
        top_k = max(2, min(5, opts.get("top_k", 3)))
        max_edges_per_window = max(window_size, opts.get("max_edges_per_window", window_size * 3))
        token_limit = max(1000, opts.get("token_limit_per_bundle", 4000))
        mock_llm = opts.get("mock_llm", False)
        llm_model = _resolve_llm_model(opts)
        
        # 1. 加载spans
        spans = self.load_spans(session_id)
        if not spans:
            yield SSEEvent("error", {"message": f"No spans found for session_id: {session_id}"})
            return
        
        # 2. 创建context_run
        context_run_id = self.create_context_run(session_id, opts)
        
        yield SSEEvent("init", {
            "session_id": session_id,
            "context_run_id": context_run_id,
            "span_total": len(spans)
        })
        
        try:
            # 3. 获取LLM客户端
            llm = self._get_llm_client(mock_llm)
            
            # 4. 滑动窗口产边
            all_edges: List[Edge] = []
            noise_span_ids: Set[str] = set()
            window_index = 0
            
            for window_spans, ref_map in self.generate_windows(spans, window_size, step_size):
                window_index += 1
                span_refs = list(ref_map.values())
                
                yield SSEEvent("window_start", {
                    "window_index": window_index,
                    "span_refs": span_refs
                })
                
                # LLM产边
                raw_links, noise_refs = llm.generate_links(window_spans, ref_map, llm_model)
                
                yield SSEEvent("llm_edges", {
                    "window_index": window_index,
                    "raw_edge_count": len(raw_links)
                })
                
                # 解析并清洗
                window_edges = self.parse_window_edges(raw_links, ref_map, window_spans)
                
                # 物理约束剪枝
                pruned_edges = self.prune_edges(window_edges, tau, top_k, max_edges_per_window)
                
                yield SSEEvent("pruned_edges", {
                    "window_index": window_index,
                    "kept_edge_count": len(pruned_edges)
                })
                
                all_edges.extend(pruned_edges)
                
                yield SSEEvent("graph_progress", {
                    "total_edges_so_far": len(all_edges)
                })
                
                # 记录noise
                reverse_map = {ref: span_id for span_id, ref in ref_map.items()}
                for ref in noise_refs:
                    if ref in reverse_map:
                        noise_span_ids.add(reverse_map[ref])
            
            # 5. 保存边
            self.save_edges(context_run_id, all_edges)
            
            # 6. 计算连通分量
            components, orphan_ids = self.compute_components(spans, all_edges, noise_span_ids)
            
            # 7. Orphan吸附
            components = self.absorb_orphans(spans, components, orphan_ids)
            
            # 8. 动态打包
            bundles, bundle_items = self.pack_bundles(
                spans, components, token_limit, context_run_id, session_id
            )
            
            # 9. CoverageGate检查
            bundled_span_ids = {item["span_id"] for item in bundle_items}
            non_noise_span_ids = {s.span_id for s in spans if s.span_id not in noise_span_ids}
            uncovered = non_noise_span_ids - bundled_span_ids
            
            if uncovered:
                misc_spans = [s for s in spans if s.span_id in uncovered]
                if misc_spans:
                    misc_bundle_id = str(uuid4())
                    misc_bundle = {
                        "bundle_id": misc_bundle_id,
                        "context_run_id": context_run_id,
                        "session_id": session_id,
                        "order_index": len(bundles) + 1,
                        "status": "READY",
                        "meta": {"is_misc": True},
                        "spans": misc_spans
                    }
                    bundles.append(misc_bundle)
                    
                    sorted_misc = sorted(misc_spans, key=lambda s: (s.start_ms or 0, s.order_index))
                    for i, span in enumerate(sorted_misc):
                        bundle_items.append({
                            "bundle_id": misc_bundle_id,
                            "span_id": span.span_id,
                            "span_ref": f"S{i + 1}",
                            "order_index": i + 1
                        })
            
            # 10. 保存bundles
            self.save_bundles(bundles, bundle_items)
            
            yield SSEEvent("bundling_done", {
                "bundle_total": len(bundles)
            })
            
            # 11. 更新状态
            stats = {
                "span_total": len(spans),
                "noise_count": len(noise_span_ids),
                "edge_count": len(all_edges),
                "component_count": len(components),
                "bundle_total": len(bundles),
            }
            self.update_context_run_status(context_run_id, "READY", stats)
            
            # 12. 最终事件
            yield SSEEvent("final", {
                "context_run_id": context_run_id,
                "bundle_total": len(bundles),
                "edge_count": len(all_edges),
                "component_count": len(components)
            })
        
        except Exception as e:
            self.update_context_run_status(context_run_id, "FAILED", {"error": str(e)})
            yield SSEEvent("error", {"message": str(e)})


# 全局实例
context_builder = ContextBuilder()
