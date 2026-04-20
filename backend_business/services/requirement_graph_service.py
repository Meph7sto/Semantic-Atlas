import asyncio
import hashlib
import json
import logging
import os
import re
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
from psycopg2.extras import RealDictCursor

from backend_business.services.ai_proxy import ai_proxy


_REQ_REQ_INFERRED_TYPES = {
    "DEPENDS_ON",
    "CONFLICTS_WITH",
    "INCLUDES",
    "EXTENDS",
    "IMPACTS",
    "VALIDATES_WITH",
}
_RULE_RELATION_TYPES = {
    "DEPENDS_ON",
    "CONFLICTS_WITH",
    "VALIDATES_WITH",
    "SIMILAR_TO",
}
_STAKEHOLDER_REQ_INFERRED_TYPES = {
    "RAISES",
    "OWNS",
    "AFFECTED_BY",
    "APPROVES",
    "BENEFITS_FROM",
    "OPPOSES",
}
_STAKEHOLDER_STAKEHOLDER_INFERRED_TYPES = {
    "INTEREST_CONFLICTS_WITH",
    "COLLABORATES_WITH",
}
_SYMMETRIC_EDGE_TYPES = {
    "COLLABORATES_WITH",
    "INTEREST_CONFLICTS_WITH",
    "CONFLICTS_WITH",
    "SIMILAR_TO",
    "VALIDATES_WITH",
}
_UNDIRECTED_EDGE_TYPES = _SYMMETRIC_EDGE_TYPES
_RELATION_PRIORITY = {
    "REFINES": 6,
    "DEPENDS_ON": 5,
    "CONFLICTS_WITH": 5,
    "INCLUDES": 4,
    "EXTENDS": 4,
    "IMPACTS": 4,
    "VALIDATES_WITH": 3,
    "SIMILAR_TO": 1,
}
_SOURCE_KIND_PRIORITY = {"structural": 3, "rule": 2, "llm": 1}
_LEVEL_ORDER = ["L1", "L2", "L3", "L4", "UNKNOWN_LEVEL"]
_DEPENDENCY_MARKERS = (
    "依赖",
    "前置",
    "调用",
    "使用",
    "基于",
    "接入",
    "读取",
    "写入",
    "消费",
    "订阅",
    "发布",
    "输入",
    "输出",
    "接口",
    "api",
    "module",
)
_VALIDATION_MARKERS = (
    "验收",
    "验证",
    "测试",
    "校验",
    "检查",
    "断言",
    "用例",
    "回归",
    "审计",
    "成功标准",
)
_CONFLICT_MARKERS = ("冲突", "互斥", "相反", "矛盾", "不能同时", "资源竞争")
_RESOURCE_TERMS = (
    "数据库",
    "缓存",
    "队列",
    "消息",
    "线程",
    "带宽",
    "显存",
    "gpu",
    "cpu",
    "内存",
    "锁",
    "连接池",
)
_GENERIC_TERMS = {
    "系统",
    "需求",
    "功能",
    "模块",
    "接口",
    "服务",
    "页面",
    "用户",
    "数据",
    "支持",
    "实现",
    "提供",
    "相关",
    "处理",
    "校验",
    "测试",
    "验证",
    "requirement",
    "service",
    "module",
    "system",
}
_NON_INFORMATIVE_TERMS = _GENERIC_TERMS | {
    "shall",
    "should",
    "must",
    "will",
    "would",
    "could",
    "may",
    "might",
    "need",
    "needs",
    "require",
    "required",
    "requires",
    "allow",
    "allows",
    "ensure",
    "ensures",
    "support",
    "supports",
    "provide",
    "provides",
    "能够",
    "可以",
    "需要",
    "应当",
    "应该",
    "必须",
    "用于",
}
_TRANSIENT_TOOL_ERROR_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 64) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


_DEPENDENCY_AUDIT_BATCH_SIZE = _env_int("REQUIREMENT_GRAPH_DEPENDENCY_AUDIT_BATCH_SIZE", 4, maximum=16)
_DEPENDENCY_AUDIT_MAX_CONCURRENCY = _env_int(
    "REQUIREMENT_GRAPH_DEPENDENCY_AUDIT_MAX_CONCURRENCY",
    2,
    maximum=8,
)
_DEPENDENCY_AUDIT_CONFIDENCE_THRESHOLD = 0.72
_DEPENDENCY_PER_SOURCE_LIMIT = 4
_SEMANTIC_EMBEDDING_MODEL = (
    os.environ.get("REQUIREMENT_GRAPH_EMBEDDING_MODEL")
    or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
_SEMANTIC_PAIR_MAX_REQUIREMENTS = 256
_SEMANTIC_PAIR_THRESHOLD = 0.62
_SEMANTIC_SIMILARITY_THRESHOLD = 0.74


_semantic_embedder = None
_semantic_embedding_error: Optional[str] = None
_semantic_embedder_lock = threading.Lock()


logger = logging.getLogger(__name__)


def _is_retryable_dependency_audit_error(exc: Exception) -> bool:
    if isinstance(exc, asyncio.TimeoutError):
        return True
    if isinstance(
        exc,
        (
            aiohttp.ClientConnectionError,
            aiohttp.ServerDisconnectedError,
            aiohttp.ClientOSError,
            aiohttp.ClientPayloadError,
        ),
    ):
        return True
    if isinstance(exc, aiohttp.ClientResponseError):
        return exc.status in _TRANSIENT_TOOL_ERROR_STATUSES
    return False


class _DependencyAuditToolDef:
    @classmethod
    def get_tool_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_dependency_decisions",
                "description": (
                    "基于候选依赖对，返回每个候选是否成立、是否应反转方向，"
                    "并给出简明证据。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "decisions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "candidate_id": {
                                        "type": "string",
                                        "description": "候选依赖的唯一 ID，必须来自输入。",
                                    },
                                    "action": {
                                        "type": "string",
                                        "enum": ["confirm", "reverse", "reject", "unclear"],
                                        "description": (
                                            "confirm=保持原方向；reverse=方向应反转；"
                                            "reject=不是依赖；unclear=证据不足。"
                                        ),
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                        "description": "对本次裁决的置信度。",
                                    },
                                    "dependency_kind": {
                                        "type": "string",
                                        "enum": ["data", "control", "temporal", "resource", "validation", "other"],
                                        "description": "依赖类型。",
                                    },
                                    "reason": {
                                        "type": "string",
                                        "description": "为什么确认、反转或拒绝该依赖。",
                                    },
                                    "evidence": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "直接证据短语，优先返回输入文本中的关键词或片段。",
                                    },
                                },
                                "required": ["candidate_id", "action", "confidence", "reason"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["decisions"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_system_prompt(cls) -> str:
        return """你是需求依赖关系的严格裁决器。

你的任务不是“多找关系”，而是“删掉伪依赖”。

只在以下情况确认 DEPENDS_ON：
1. source 明确调用、读取、消费、依赖 target 的接口/数据/组件；
2. target 是 source 的前置条件、执行前提或必经校验；
3. 没有 target，source 无法正确实现、运行、验证或交付。

必须拒绝这些常见伪依赖：
- 只是同一模块、同一主题、同一父需求下的兄弟项；
- 只是都提到了相似关键词；
- 只是“相关”“配合”“一起工作”，但没有明确前置/输入输出/调用链；
- 只是同类能力或相邻功能。

方向判断规则：
- 如果实际是 target 依赖 source，返回 reverse；
- 如果证据不足，返回 reject 或 unclear，不要勉强确认。

输出要求：
- 必须调用 submit_dependency_decisions 工具；
- candidate_id 必须来自输入；
- 不要输出工具之外的普通文本。"""


class RequirementGraphService:
    """Build a lightweight requirement knowledge graph from existing analysis data."""

    def __init__(self, db_service: Any, ai_client: Any = None):
        self.db = db_service
        self.ai = ai_client or ai_proxy

    def build_graph(
        self,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 600,
        infer_relations: bool = False,
        inference_model: str = "deepseek-reasoner",
        inference_limit: int = 48,
    ) -> Dict[str, Any]:
        project_id = self._clean(project_id) or self._resolve_project_id_by_session(
            self._clean(session_id)
        )
        session_id = self._clean(session_id) or self._resolve_project_session(project_id)
        limit = max(50, min(2000, int(limit or 600)))

        builder = _GraphBuilder(limit=limit)
        project_requirements = self._load_project_requirements(project_id, limit)
        requirement_features: Dict[str, Dict[str, Any]] = {}

        for req in project_requirements:
            node_id = _req_node_id(req.get("req_id"))
            normalized_level = _normalize_source_level(
                req.get("source_level"),
                req.get("requirement_type"),
            )
            builder.add_node(
                node_id,
                kind="requirement",
                label=req.get("title") or _short_text(req.get("description"), 36),
                group=normalized_level,
                properties={
                    "req_id": req.get("req_id"),
                    "project_id": req.get("project_id"),
                    "title": req.get("title"),
                    "description": req.get("description"),
                    "content": req.get("description"),
                    "type": req.get("requirement_type"),
                    "status": req.get("status"),
                    "priority": req.get("priority"),
                    "tags": _as_list(req.get("tags")),
                    "assignee": req.get("assignee"),
                    "parent_id": req.get("parent_id"),
                    "source_req_id": req.get("source_req_id"),
                    "source_level": normalized_level,
                    "level": normalized_level,
                    "custom_fields": _as_dict(req.get("custom_fields")),
                    "source": "manage_requirements",
                },
            )
            requirement_features[node_id] = self._build_requirement_feature(req, normalized_level)

        self._attach_semantic_embeddings(requirement_features)
        self._apply_project_edges(builder, project_requirements)
        candidate_pairs, candidate_stats = self._collect_candidate_pairs(requirement_features)
        rule_stats = self._apply_rule_edges(
            builder,
            requirement_features,
            candidate_pairs,
            dependency_model=inference_model,
            dependency_review_limit=inference_limit,
        )
        inference_stats = self._apply_llm_inference(
            builder,
            project_id=project_id,
            session_id=session_id,
            enabled=infer_relations,
            model=inference_model,
            inference_limit=inference_limit,
            requirement_features=requirement_features,
            candidate_pairs=candidate_pairs,
        )
        self._prune_weaker_similar_edges(builder)

        graph = builder.to_graph()
        graph["stats"]["strong_edge_count"] = graph["stats"]["structural_edge_count"] + graph["stats"]["rule_edge_count"]
        graph["stats"]["inferred_edge_count"] = inference_stats["inferred_edge_count"]
        graph["stats"]["candidate_pair_count"] = candidate_stats["pair_count"]
        graph["stats"]["candidate_pairs_per_requirement_limit"] = candidate_stats["per_requirement_limit"]
        graph["stats"]["candidate_requirement_count"] = candidate_stats["requirement_count"]
        graph["stats"]["source_requirement_count"] = len(project_requirements)
        graph["stats"]["rule_edge_counts"] = rule_stats["edge_counts"]
        graph["stats"]["dependency_audit"] = rule_stats["dependency_audit"]
        graph["meta"] = {
            "project_id": project_id,
            "session_id": session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": {
                "manage_requirements": len(project_requirements),
            },
            "candidate_recall": candidate_stats,
            "dependency_audit": rule_stats["dependency_audit"],
            "inference": inference_stats,
        }
        graph["legend"]["levels"] = _LEVEL_ORDER
        return graph

    def _resolve_project_session(self, project_id: Optional[str]) -> Optional[str]:
        if not project_id:
            return None
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_session_id
                    FROM manage_projects
                    WHERE project_id = %s
                    """,
                    (project_id,),
                )
                row = cur.fetchone()
        return row[0] if row and row[0] else None

    def _resolve_project_id_by_session(self, session_id: Optional[str]) -> Optional[str]:
        if not session_id:
            return None
        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT project_id
                    FROM manage_projects
                    WHERE current_session_id = %s
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        return row[0] if row and row[0] else None

    def _load_project_requirements(
        self,
        project_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not project_id:
            return []
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, project_id, requirement_type, status, title,
                           description, priority, assignee, tags, parent_id,
                           source_req_id, source_level, custom_fields, created_by,
                           updated_by, created_at::text AS created_at,
                           updated_at::text AS updated_at
                    FROM manage_requirements
                    WHERE project_id = %s AND COALESCE(deleted, FALSE) = FALSE
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (project_id, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def _load_l123_requirements(
        self,
        session_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint,
                           anchor_span_id, r, created_at::text AS created_at
                    FROM requirements_l123
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (session_id, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def _load_l4_requirements(
        self,
        session_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, source_top_id, source_top_text,
                           text, component, acceptance_criteria, test_method,
                           interfaces, data_contracts, error_handling, nfr,
                           open_questions, evidence_ids, confidence, source,
                           meta, created_at::text AS created_at
                    FROM low_level_requirements
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (session_id, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def _apply_project_edges(
        self,
        builder: "_GraphBuilder",
        project_requirements: Iterable[Dict[str, Any]],
    ) -> None:
        for req in project_requirements:
            target = _req_node_id(req.get("req_id"))
            parent_id = self._clean(req.get("parent_id"))
            source_req_id = self._clean(req.get("source_req_id"))
            if parent_id:
                builder.add_edge(
                    _req_node_id(parent_id),
                    target,
                    "REFINES",
                    label="父子细化",
                    weight=0.99,
                    properties={
                        "source_kind": "structural",
                        "source_detail": "manage_requirements.parent_id",
                        "source": "manage_requirements.parent_id",
                        "confidence": 0.99,
                        "reason": "来自需求父子字段",
                        "evidence": [f"parent_id={parent_id}"],
                    },
                )
            if source_req_id:
                builder.add_edge(
                    _req_node_id(source_req_id),
                    target,
                    "REFINES",
                    label="来源细化",
                    weight=0.97,
                    properties={
                        "source_kind": "structural",
                        "source_detail": "manage_requirements.source_req_id",
                        "source": "manage_requirements.source_req_id",
                        "confidence": 0.97,
                        "reason": "来自需求来源字段",
                        "evidence": [f"source_req_id={source_req_id}"],
                    },
                )

    def _build_requirement_feature(
        self,
        req: Dict[str, Any],
        normalized_level: str,
    ) -> Dict[str, Any]:
        title = self._clean(req.get("title")) or ""
        description = self._clean(req.get("description")) or ""
        custom_fields = _as_dict(req.get("custom_fields"))
        text = " ".join(
            part
            for part in [
                title,
                description,
                " ".join(_compact_list(_as_list(req.get("tags")))),
                " ".join(_compact_list(_flatten_values(custom_fields))),
            ]
            if part
        )
        text_lower = text.lower()
        validation_text = " ".join(
            _compact_list(
                _flatten_values(
                    {
                        "description": description,
                        "acceptance": custom_fields.get("acceptance_criteria"),
                        "validation": custom_fields.get("validation_rules"),
                        "test_method": custom_fields.get("test_method"),
                        "test_cases": custom_fields.get("test_cases"),
                    }
                )
            )
        )
        modules = _extract_modules(req)
        tags = {tag.lower() for tag in _compact_list(_as_list(req.get("tags")))}
        terms = _extract_terms(text)
        interface_terms = _extract_interface_terms(text, custom_fields)
        validation_terms = _extract_validation_terms(validation_text or text)
        return {
            "id": _req_node_id(req.get("req_id")),
            "req_id": self._clean(req.get("req_id")),
            "title": title,
            "description": description,
            "text": text,
            "text_lower": text_lower,
            "semantic_text": _build_semantic_text(req, title, description, custom_fields),
            "embedding": None,
            "source_level": normalized_level,
            "requirement_type": self._clean(req.get("requirement_type")),
            "status": self._clean(req.get("status")),
            "priority": _float_or_default(req.get("priority"), 0),
            "tags": tags,
            "modules": modules,
            "terms": terms,
            "interface_terms": interface_terms,
            "validation_terms": validation_terms,
            "custom_fields": custom_fields,
        }

    def _attach_semantic_embeddings(
        self,
        requirement_features: Dict[str, Dict[str, Any]],
    ) -> None:
        if not requirement_features or not _semantic_embedding_enabled():
            return
        embedder = _get_semantic_embedder()
        if embedder is None:
            return

        feature_items = list(requirement_features.items())
        texts = [item[1].get("semantic_text") or item[1].get("text") or "" for item in feature_items]
        try:
            vectors = embedder.encode(texts, normalize_embeddings=True)
        except Exception as exc:
            logger.warning("Requirement graph semantic embedding failed: %s", exc)
            return

        for (_, feature), vector in zip(feature_items, vectors):
            feature["embedding"] = _to_float_vector(vector)

    def _collect_candidate_pairs(
        self,
        requirement_features: Dict[str, Dict[str, Any]],
        per_requirement_limit: int = 10,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        per_requirement_limit = max(4, min(16, int(per_requirement_limit or 10)))
        term_document_frequency = Counter()
        for feature in requirement_features.values():
            for term in feature["terms"]:
                term_document_frequency[term] += 1
        max_term_document_frequency = _max_term_document_frequency(len(requirement_features))
        signal_indexes: Dict[str, Dict[str, set[str]]] = {
            "modules": defaultdict(set),
            "tags": defaultdict(set),
            "terms": defaultdict(set),
            "interfaces": defaultdict(set),
            "validation": defaultdict(set),
        }
        for node_id, feature in requirement_features.items():
            for module in feature["modules"]:
                signal_indexes["modules"][module].add(node_id)
            for tag in feature["tags"]:
                signal_indexes["tags"][tag].add(node_id)
            filtered_terms = [
                term
                for term in sorted(feature["terms"])
                if term_document_frequency.get(term, 0) <= max_term_document_frequency
            ]
            for term in filtered_terms[:18]:
                signal_indexes["terms"][term].add(node_id)
            for term in feature["interface_terms"]:
                signal_indexes["interfaces"][term].add(node_id)
            for term in feature["validation_terms"]:
                signal_indexes["validation"][term].add(node_id)

        pair_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        per_requirement_counts: Dict[str, int] = {}
        semantic_neighbors = self._collect_semantic_candidate_neighbors(
            requirement_features,
            per_requirement_limit=per_requirement_limit,
        )

        for node_id, feature in requirement_features.items():
            candidate_scores: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"score": 0, "evidence": []}
            )
            self._accumulate_candidates(
                node_id,
                feature["modules"],
                signal_indexes["modules"],
                candidate_scores,
                score=5,
                evidence_label="shared_module",
            )
            self._accumulate_candidates(
                node_id,
                feature["tags"],
                signal_indexes["tags"],
                candidate_scores,
                score=4,
                evidence_label="shared_tag",
            )
            self._accumulate_candidates(
                node_id,
                [
                    term
                    for term in sorted(feature["terms"])
                    if term_document_frequency.get(term, 0) <= max_term_document_frequency
                ][:12],
                signal_indexes["terms"],
                candidate_scores,
                score=2,
                evidence_label="shared_term",
            )
            self._accumulate_candidates(
                node_id,
                feature["interface_terms"],
                signal_indexes["interfaces"],
                candidate_scores,
                score=4,
                evidence_label="shared_interface",
            )
            self._accumulate_candidates(
                node_id,
                feature["validation_terms"],
                signal_indexes["validation"],
                candidate_scores,
                score=3,
                evidence_label="shared_validation",
            )
            for other_id, semantic_score in semantic_neighbors.get(node_id, []):
                candidate_scores[other_id]["score"] += max(3, int(round(semantic_score * 6)))
                candidate_scores[other_id]["evidence"] = _merge_evidence(
                    candidate_scores[other_id]["evidence"],
                    [f"semantic_match:{semantic_score:.3f}"],
                    limit=8,
                )

            ordered_candidates = sorted(
                candidate_scores.items(),
                key=lambda item: (-item[1]["score"], item[0]),
            )[:per_requirement_limit]
            per_requirement_counts[node_id] = len(ordered_candidates)
            for other_id, payload in ordered_candidates:
                pair_key = tuple(sorted((node_id, other_id)))
                pair_info = pair_map.setdefault(
                    pair_key,
                    {
                        "pair": pair_key,
                        "score": 0,
                        "signals": [],
                        "requesters": set(),
                    },
                )
                pair_info["score"] = max(pair_info["score"], payload["score"])
                pair_info["signals"] = _merge_evidence(
                    pair_info["signals"],
                    payload["evidence"],
                    limit=12,
                )
                pair_info["requesters"].add(node_id)

        pairs = [
            {
                "source": source,
                "target": target,
                "score": payload["score"],
                "signals": payload["signals"],
                "requester_count": len(payload["requesters"]),
            }
            for (source, target), payload in sorted(
                pair_map.items(),
                key=lambda item: (-item[1]["score"], item[0][0], item[0][1]),
            )
        ]
        return pairs, {
            "pair_count": len(pairs),
            "per_requirement_limit": per_requirement_limit,
            "per_requirement_counts": per_requirement_counts,
            "requirement_count": len(requirement_features),
            "max_term_document_frequency": max_term_document_frequency,
        }

    def _collect_semantic_candidate_neighbors(
        self,
        requirement_features: Dict[str, Dict[str, Any]],
        *,
        per_requirement_limit: int,
    ) -> Dict[str, List[Tuple[str, float]]]:
        if len(requirement_features) < 2 or len(requirement_features) > _SEMANTIC_PAIR_MAX_REQUIREMENTS:
            return {}

        feature_items = [
            (node_id, feature)
            for node_id, feature in requirement_features.items()
            if feature.get("embedding")
        ]
        if len(feature_items) < 2:
            return {}

        neighbor_limit = max(2, min(6, per_requirement_limit // 2 or 2))
        neighbors: Dict[str, List[Tuple[str, float]]] = {}
        for index, (node_id, feature) in enumerate(feature_items):
            ranked: List[Tuple[str, float]] = []
            for other_index, (other_id, other_feature) in enumerate(feature_items):
                if other_index == index:
                    continue
                similarity = _cosine_similarity(
                    feature.get("embedding"),
                    other_feature.get("embedding"),
                )
                if similarity < _SEMANTIC_PAIR_THRESHOLD:
                    continue
                ranked.append((other_id, similarity))
            ranked.sort(key=lambda item: (-item[1], item[0]))
            if ranked:
                neighbors[node_id] = ranked[:neighbor_limit]
        return neighbors

    def _accumulate_candidates(
        self,
        source_id: str,
        values: Iterable[str],
        index_map: Dict[str, set[str]],
        candidate_scores: Dict[str, Dict[str, Any]],
        *,
        score: int,
        evidence_label: str,
    ) -> None:
        for value in values:
            for target_id in index_map.get(value, set()):
                if target_id == source_id:
                    continue
                candidate_scores[target_id]["score"] += score
                candidate_scores[target_id]["evidence"] = _merge_evidence(
                    candidate_scores[target_id]["evidence"],
                    [f"{evidence_label}:{value}"],
                    limit=8,
                )

    def _apply_rule_edges(
        self,
        builder: "_GraphBuilder",
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
        *,
        dependency_model: str = "deepseek-reasoner",
        dependency_review_limit: int = 48,
    ) -> Dict[str, Any]:
        edge_counter: Counter[str] = Counter()
        dependency_candidates: List[Dict[str, Any]] = []
        for pair in candidate_pairs:
            left = requirement_features.get(pair["source"])
            right = requirement_features.get(pair["target"])
            if not left or not right:
                continue

            dependency_lr = _match_dependency_rule(left, right)
            dependency_rl = _match_dependency_rule(right, left)
            conflict = _match_conflict_rule(left, right)
            validation = _match_validation_rule(left, right)
            similar = _match_similarity_rule(left, right)

            for source_feature, target_feature, relation in (
                (left, right, dependency_lr),
                (right, left, dependency_rl),
            ):
                if not relation:
                    continue
                candidate = self._build_dependency_candidate(
                    source_feature=source_feature,
                    target_feature=target_feature,
                    relation=relation,
                    pair=pair,
                )
                if candidate:
                    dependency_candidates.append(candidate)

            if conflict:
                builder.add_edge(
                    left["id"],
                    right["id"],
                    "CONFLICTS_WITH",
                    label=_edge_label("CONFLICTS_WITH"),
                    weight=conflict["confidence"],
                    properties={
                        "source_kind": "rule",
                        "source_detail": conflict["detail"],
                        "source": conflict["detail"],
                        "confidence": conflict["confidence"],
                        "reason": conflict["reason"],
                        "evidence": conflict["evidence"],
                    },
                )
                edge_counter["CONFLICTS_WITH"] += 1

            if validation:
                builder.add_edge(
                    left["id"],
                    right["id"],
                    "VALIDATES_WITH",
                    label=_edge_label("VALIDATES_WITH"),
                    weight=validation["confidence"],
                    properties={
                        "source_kind": "rule",
                        "source_detail": validation["detail"],
                        "source": validation["detail"],
                        "confidence": validation["confidence"],
                        "reason": validation["reason"],
                        "evidence": validation["evidence"],
                    },
                )
                edge_counter["VALIDATES_WITH"] += 1

            if similar and not _has_stronger_relation(builder, left["id"], right["id"]):
                builder.add_edge(
                    left["id"],
                    right["id"],
                    "SIMILAR_TO",
                    label=_edge_label("SIMILAR_TO"),
                    weight=similar["confidence"],
                    properties={
                        "source_kind": "rule",
                        "source_detail": similar["detail"],
                        "source": similar["detail"],
                        "confidence": similar["confidence"],
                        "reason": similar["reason"],
                        "evidence": similar["evidence"],
                    },
                )
                edge_counter["SIMILAR_TO"] += 1

        dependency_audit = self._apply_dependency_candidates(
            builder,
            dependency_candidates,
            model=dependency_model,
            review_limit=dependency_review_limit,
        )
        if dependency_audit["confirmed_count"]:
            edge_counter["DEPENDS_ON"] += dependency_audit["confirmed_count"]

        return {
            "edge_counts": dict(edge_counter),
            "dependency_audit": dependency_audit,
        }

    def _build_dependency_candidate(
        self,
        *,
        source_feature: Dict[str, Any],
        target_feature: Dict[str, Any],
        relation: Dict[str, Any],
        pair: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        evidence = _compact_list(_as_list(relation.get("evidence")))
        if not self._is_dependency_candidate_strong(evidence):
            return None
        source_req_id = self._clean(source_feature.get("req_id")) or source_feature["id"]
        target_req_id = self._clean(target_feature.get("req_id")) or target_feature["id"]
        return {
            "candidate_id": f"dep:{source_req_id}->{target_req_id}",
            "source": source_feature["id"],
            "target": target_feature["id"],
            "score": float(pair.get("score") or 0),
            "rule_confidence": float(relation.get("confidence") or 0),
            "detail": relation.get("detail"),
            "reason": relation.get("reason"),
            "evidence": evidence[:8],
            "signals": _compact_list(_as_list(pair.get("signals")))[:8],
            "source_requirement": self._serialize_requirement_feature(source_feature),
            "target_requirement": self._serialize_requirement_feature(target_feature),
        }

    def _is_dependency_candidate_strong(self, evidence: List[str]) -> bool:
        strong_markers = (
            "mentioned_module:",
            "shared_interface:",
            "shared_validation:",
        )
        if any(item.startswith(strong_markers) for item in evidence):
            return True
        shared_module_count = sum(1 for item in evidence if item.startswith("shared_module:"))
        return shared_module_count >= 1 and len(evidence) >= 3

    def _apply_dependency_candidates(
        self,
        builder: "_GraphBuilder",
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
        review_limit: int,
    ) -> Dict[str, Any]:
        selected_candidates = self._select_dependency_candidates(
            dependency_candidates,
            review_limit=review_limit,
        )
        if not selected_candidates:
            return {
                "model": model,
                "candidate_count": 0,
                "reviewed_count": 0,
                "confirmed_count": 0,
                "rejected_count": 0,
                "fallback_used": False,
                "pruned_transitive_count": 0,
            }

        fallback_used = False
        try:
            reviewed = self._review_dependency_candidates_with_llm(
                selected_candidates,
                model=model,
            )
            fallback_used = any(bool(item.get("used_fallback")) for item in reviewed)
        except Exception as exc:
            self._log_dependency_audit_failure(
                exc,
                candidate_count=len(selected_candidates),
                model=model,
                fallback_scope="full",
            )
            reviewed = self._fallback_dependency_decisions(selected_candidates)
            fallback_used = True

        confirmed_count = 0
        rejected_count = 0
        for decision in reviewed:
            action = str(decision.get("action") or "").strip().lower()
            candidate = decision.get("candidate")
            if not candidate or action in {"reject", "unclear"}:
                rejected_count += 1
                continue
            confidence = max(
                _float_or_default(candidate.get("rule_confidence"), 0),
                _float_or_default(decision.get("confidence"), 0),
            )
            if confidence < _DEPENDENCY_AUDIT_CONFIDENCE_THRESHOLD:
                rejected_count += 1
                continue

            source = candidate["source"]
            target = candidate["target"]
            if action == "reverse":
                source, target = target, source

            builder.add_edge(
                source,
                target,
                "DEPENDS_ON",
                label=_edge_label("DEPENDS_ON"),
                weight=confidence,
                properties={
                    "source_kind": "rule",
                    "source_detail": candidate.get("detail"),
                    "source": candidate.get("detail"),
                    "confidence": confidence,
                    "reason": decision.get("reason") or candidate.get("reason"),
                    "evidence": _merge_evidence(
                        candidate.get("evidence"),
                        decision.get("evidence"),
                        limit=10,
                    ),
                    "audit_model": model,
                    "audit_confidence": _float_or_default(decision.get("confidence"), confidence),
                    "audit_action": action,
                    "dependency_kind": decision.get("dependency_kind"),
                },
            )
            confirmed_count += 1

        pruned_transitive_count = self._prune_transitive_dependency_edges(builder)
        confirmed_count = max(0, confirmed_count - pruned_transitive_count)
        return {
            "model": model,
            "candidate_count": len(dependency_candidates),
            "reviewed_count": len(selected_candidates),
            "confirmed_count": confirmed_count,
            "rejected_count": rejected_count,
            "fallback_used": fallback_used,
            "pruned_transitive_count": pruned_transitive_count,
        }

    def _log_dependency_audit_failure(
        self,
        exc: Exception,
        *,
        candidate_count: int,
        model: str,
        fallback_scope: str,
    ) -> None:
        message = (
            "Dependency audit tool-call failed; falling back to strict rule filter "
            "(scope=%s, candidates=%s, model=%s)"
        )
        if _is_retryable_dependency_audit_error(exc):
            logger.warning(message + " reason=%s", fallback_scope, candidate_count, model, repr(exc))
            return
        logger.exception(message, fallback_scope, candidate_count, model)

    def _select_dependency_candidates(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        review_limit: int,
    ) -> List[Dict[str, Any]]:
        limit = max(8, min(96, int(review_limit or 48)))
        per_source_counts: Dict[str, int] = defaultdict(int)
        selected: List[Dict[str, Any]] = []
        ordered = sorted(
            dependency_candidates,
            key=lambda item: (
                -_float_or_default(item.get("score"), 0),
                -_float_or_default(item.get("rule_confidence"), 0),
                -(len(item.get("evidence") or [])),
                str(item.get("candidate_id") or ""),
            ),
        )
        for candidate in ordered:
            source = candidate["source"]
            if per_source_counts[source] >= _DEPENDENCY_PER_SOURCE_LIMIT:
                continue
            selected.append(candidate)
            per_source_counts[source] += 1
            if len(selected) >= limit:
                break
        return selected

    def _review_dependency_candidates_with_llm(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
    ) -> List[Dict[str, Any]]:
        if self.ai is None or not hasattr(self.ai, "chat_completion_with_tools_async"):
            return self._fallback_dependency_decisions(dependency_candidates)

        coroutine = self._review_dependency_candidates_with_llm_async(
            dependency_candidates,
            model=model,
        )
        try:
            return asyncio.run(coroutine)
        except RuntimeError as exc:
            if "asyncio.run() cannot be called from a running event loop" not in str(exc):
                raise

        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, Exception] = {}

        def _runner() -> None:
            try:
                result_holder["value"] = asyncio.run(
                    self._review_dependency_candidates_with_llm_async(
                        dependency_candidates,
                        model=model,
                    )
                )
            except Exception as thread_exc:  # pragma: no cover - defensive path
                error_holder["error"] = thread_exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if error_holder.get("error"):
            raise error_holder["error"]
        return list(result_holder.get("value") or [])

    async def _review_dependency_candidates_with_llm_async(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
    ) -> List[Dict[str, Any]]:
        semaphore = asyncio.Semaphore(_DEPENDENCY_AUDIT_MAX_CONCURRENCY)
        batches = [
            dependency_candidates[index : index + _DEPENDENCY_AUDIT_BATCH_SIZE]
            for index in range(0, len(dependency_candidates), _DEPENDENCY_AUDIT_BATCH_SIZE)
        ]
        connector = aiohttp.TCPConnector(limit=max(8, _DEPENDENCY_AUDIT_MAX_CONCURRENCY * 2))
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._review_dependency_batch(
                    batch,
                    model=model,
                    session=session,
                    semaphore=semaphore,
                )
                for batch in batches
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        reviewed: List[Dict[str, Any]] = []
        for batch, result in zip(batches, batch_results):
            if isinstance(result, Exception):
                self._log_dependency_audit_failure(
                    result,
                    candidate_count=len(batch),
                    model=model,
                    fallback_scope="batch",
                )
                reviewed.extend(self._fallback_dependency_decisions(batch))
                continue
            reviewed.extend(result)
        return reviewed

    async def _review_dependency_batch(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
    ) -> List[Dict[str, Any]]:
        async with semaphore:
            system_prompt = _DependencyAuditToolDef.get_system_prompt()
            payload = {
                "candidates": [
                    {
                        "candidate_id": item["candidate_id"],
                        "source": item["source"],
                        "target": item["target"],
                        "pair_score": item.get("score"),
                        "rule_confidence": item.get("rule_confidence"),
                        "rule_reason": item.get("reason"),
                        "rule_evidence": item.get("evidence"),
                        "signals": item.get("signals"),
                        "source_requirement": item.get("source_requirement"),
                        "target_requirement": item.get("target_requirement"),
                    }
                    for item in dependency_candidates
                ]
            }
            user_prompt = (
                "请严格审查这些依赖候选，删除只是“同主题/同模块/同父节点”导致的伪依赖。"
                "只有在 source 明确以前置、输入输出、调用、读取、消费、校验依赖 target 时才确认。"
                "输入如下：\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            response = await self.ai.chat_completion_with_tools_async(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[_DependencyAuditToolDef.get_tool_schema()],
                model=model,
                temperature=0.1,
                max_tokens=3200,
                tool_choice="required",
                session=session,
            )
        return self._parse_dependency_audit_response(response, dependency_candidates)

    def _parse_dependency_audit_response(
        self,
        response: Dict[str, Any],
        dependency_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidate_lookup = {
            str(item.get("candidate_id") or ""): item for item in dependency_candidates
        }
        tool_calls = response.get("tool_calls") if isinstance(response, dict) else []
        if not isinstance(tool_calls, list):
            return self._fallback_dependency_decisions(dependency_candidates)

        decisions: List[Dict[str, Any]] = []
        for call in tool_calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                continue
            function_payload = call.get("function") or {}
            if function_payload.get("name") != "submit_dependency_decisions":
                continue
            arguments = function_payload.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            raw_decisions = arguments.get("decisions") if isinstance(arguments, dict) else []
            for item in raw_decisions if isinstance(raw_decisions, list) else []:
                if not isinstance(item, dict):
                    continue
                candidate_id = str(item.get("candidate_id") or "").strip()
                candidate = candidate_lookup.get(candidate_id)
                if not candidate:
                    continue
                decisions.append(
                    {
                        "candidate": candidate,
                        "action": str(item.get("action") or "unclear").strip().lower(),
                        "confidence": _float_or_default(item.get("confidence"), 0),
                        "reason": self._clean(item.get("reason")) or "",
                        "evidence": _compact_list(_as_list(item.get("evidence")))[:8],
                        "dependency_kind": self._clean(item.get("dependency_kind")) or "other",
                    }
                )
        return decisions or self._fallback_dependency_decisions(dependency_candidates)

    def _fallback_dependency_decisions(
        self,
        dependency_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        decisions: List[Dict[str, Any]] = []
        for candidate in dependency_candidates:
            evidence = candidate.get("evidence") or []
            has_direct_reference = any(
                item.startswith(("mentioned_module:", "shared_interface:", "shared_validation:"))
                for item in evidence
            )
            action = "confirm" if has_direct_reference else "reject"
            decisions.append(
                {
                    "candidate": candidate,
                    "action": action,
                    "confidence": candidate.get("rule_confidence", 0.0),
                    "reason": candidate.get("reason") or "规则回退判定",
                    "evidence": evidence[:6],
                    "dependency_kind": "other",
                    "used_fallback": True,
                }
            )
        return decisions

    def _prune_transitive_dependency_edges(self, builder: "_GraphBuilder") -> int:
        dependency_edges = [
            edge for edge in builder.edges.values() if edge.get("type") == "DEPENDS_ON"
        ]
        adjacency: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for edge in dependency_edges:
            adjacency[edge["source"]].append(edge)

        removable_keys: List[Tuple[str, str, str]] = []
        for edge in dependency_edges:
            source = edge["source"]
            target = edge["target"]
            direct_weight = _float_or_default(edge.get("weight"), 0)
            if direct_weight >= 0.9:
                continue
            for step in adjacency.get(source, []):
                via = step["target"]
                if via in {source, target}:
                    continue
                for step_two in adjacency.get(via, []):
                    if step_two["target"] != target:
                        continue
                    indirect_weight = min(
                        _float_or_default(step.get("weight"), 0),
                        _float_or_default(step_two.get("weight"), 0),
                    )
                    if indirect_weight >= direct_weight + 0.05:
                        removable_keys.append((edge["source"], edge["target"], edge["type"]))
                        break
                if (edge["source"], edge["target"], edge["type"]) in removable_keys:
                    break

        for key in removable_keys:
            builder.edges.pop(key, None)
        return len(removable_keys)

    def _prune_weaker_similar_edges(self, builder: "_GraphBuilder") -> None:
        removable_keys = []
        for key, edge in builder.edges.items():
            if edge["type"] != "SIMILAR_TO":
                continue
            if _has_stronger_relation(builder, edge["source"], edge["target"]):
                removable_keys.append(key)
        for key in removable_keys:
            builder.edges.pop(key, None)

    def _apply_l4_edges(
        self,
        builder: "_GraphBuilder",
        session_id: Optional[str],
    ) -> None:
        if not session_id:
            return
        with self.db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, top_req_id
                    FROM low_level_requirement_links
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()
        for row in rows:
            if row.get("top_req_id") and row.get("req_id"):
                builder.add_edge(
                    _req_node_id(row["top_req_id"]),
                    _req_node_id(row["req_id"]),
                    "REFINES",
                    label="生成 L4",
                    weight=0.88,
                    properties={"source": "low_level_requirement_links"},
                )

    def _apply_trace_edges(
        self,
        builder: "_GraphBuilder",
        session_id: Optional[str],
        text_index: Dict[str, List[str]],
    ) -> None:
        if not session_id or not hasattr(self.db, "get_latest_trace_batch"):
            return
        latest = self.db.get_latest_trace_batch(session_id)
        data = (latest or {}).get("data") or {}
        for index, rel in enumerate(data.get("relations") or []):
            if rel.get("has_relation") is False:
                continue
            source = _resolve_requirement_node(
                rel.get("high_req_id")
                or rel.get("source_id")
                or rel.get("from_id")
                or rel.get("high_requirement_id"),
                rel.get("high_req")
                or rel.get("high_requirement")
                or rel.get("source")
                or rel.get("source_text"),
                text_index,
            )
            target = _resolve_requirement_node(
                rel.get("low_req_id")
                or rel.get("target_id")
                or rel.get("to_id")
                or rel.get("low_requirement_id"),
                rel.get("low_req")
                or rel.get("low_requirement")
                or rel.get("target")
                or rel.get("target_text"),
                text_index,
            )
            if not source or not target or source == target:
                continue
            relation_type = str(rel.get("relation_type") or "trace").lower()
            edge_type = "DEPENDS_ON" if "depend" in relation_type else "REFINES"
            builder.add_edge(
                source,
                target,
                edge_type,
                label=_edge_label(edge_type),
                weight=_float_or_default(rel.get("confidence"), 0.72),
                properties={"source": "trace_analysis", "record": rel, "index": index},
            )

    def _apply_conflict_edges(
        self,
        builder: "_GraphBuilder",
        session_id: Optional[str],
        text_index: Dict[str, List[str]],
    ) -> None:
        if not session_id or not hasattr(self.db, "get_latest_conflict_batch"):
            return
        latest = self.db.get_latest_conflict_batch(session_id) or {}
        for index, item in enumerate(latest.get("items") or []):
            if not item.get("is_conflict"):
                continue
            source = _resolve_requirement_node(None, item.get("requirement_a"), text_index)
            target = _resolve_requirement_node(None, item.get("requirement_b"), text_index)
            if not source or not target or source == target:
                continue
            builder.add_edge(
                source,
                target,
                "CONFLICTS_WITH",
                label="冲突",
                weight=0.96,
                properties={
                    "source": "conflict_analysis",
                    "batch_id": latest.get("batch_id"),
                    "result": _as_dict(item.get("result_json")),
                    "index": index,
                },
            )

    def _apply_classification(
        self,
        builder: "_GraphBuilder",
        session_id: Optional[str],
        text_index: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        empty_stats = {
            "label_distribution": {},
            "matched_count": 0,
            "total": 0,
        }
        if not session_id or not hasattr(self.db, "get_latest_classification"):
            return empty_stats
        latest = self.db.get_latest_classification(session_id) or {}
        predictions = latest.get("predictions") or []
        grouped_nodes: Dict[str, List[str]] = defaultdict(list)
        raw_label_distribution: Dict[str, int] = defaultdict(int)
        matched_count = 0

        for index, prediction in enumerate(predictions):
            if isinstance(prediction, str):
                label = prediction
                req_text = _pick_index(latest.get("requirements") or [], index)
            else:
                label = (
                    prediction.get("label")
                    or prediction.get("predicted_label")
                    or prediction.get("category")
                    or prediction.get("class")
                )
                req_text = (
                    prediction.get("requirement")
                    or prediction.get("text")
                    or prediction.get("input")
                    or _pick_index(latest.get("requirements") or [], index)
                )
            label = _clean_label(label)
            if not label or not req_text:
                continue
            raw_label_distribution[str(label)] += 1
            node_id = _resolve_requirement_node(None, req_text, text_index)
            if not node_id:
                node_id = _resolve_requirement_node_fuzzy(req_text, text_index)
            if not node_id or node_id not in builder.nodes:
                continue
            node = builder.nodes[node_id]
            node["properties"]["category"] = label
            node["properties"]["classification"] = {
                "label": label,
                "source": "classification_analysis",
                "record_id": latest.get("id"),
            }
            node["group"] = node.get("group") or label
            grouped_nodes[str(label)].append(node_id)
            matched_count += 1

        for label, node_ids in grouped_nodes.items():
            unique_ids = list(dict.fromkeys(node_ids))[:12]
            for source, target in zip(unique_ids, unique_ids[1:]):
                builder.add_edge(
                    source,
                    target,
                    "SIMILAR_TO",
                    label=f"同类: {label}",
                    weight=0.58,
                    properties={"source": "classification_analysis", "category": label},
                )

        label_distribution = _normalize_label_distribution(
            latest.get("label_distribution")
        )
        if not label_distribution:
            label_distribution = dict(raw_label_distribution) or {
                label: len(list(dict.fromkeys(node_ids)))
                for label, node_ids in grouped_nodes.items()
            }
        return {
            "label_distribution": label_distribution,
            "matched_count": matched_count,
            "total": int(latest.get("total") or sum(label_distribution.values()) or matched_count),
        }

    def _apply_stakeholders(
        self,
        builder: "_GraphBuilder",
        project_id: Optional[str],
        project_requirements: Iterable[Dict[str, Any]],
    ) -> None:
        member_profiles = self._load_project_members(project_id)
        user_ids = set(member_profiles)
        for req in project_requirements:
            for field in ("created_by", "updated_by", "assignee"):
                value = self._clean(req.get(field))
                if value:
                    user_ids.add(value)

        for user_id in sorted(user_ids):
            profile = member_profiles.get(user_id, {})
            label = profile.get("display_name") or profile.get("username") or user_id
            roles = profile.get("roles") or []
            role_label = "/".join(_compact_list([r.get("role_id") for r in roles])) or profile.get("role")
            source = (
                "project_members/auth_users"
                if user_id in member_profiles
                else "requirement_people_evidence"
            )
            builder.add_node(
                _stakeholder_node_id(user_id),
                kind="stakeholder",
                label=label,
                group=profile.get("external_type") or role_label or "stakeholder",
                properties={
                    "user_id": user_id,
                    "name": label,
                    "username": profile.get("username"),
                    "role": role_label or profile.get("role"),
                    "roles": _compact_list([r.get("role_id") for r in roles]),
                    "type": profile.get("external_type") or "internal",
                    "department": profile.get("department"),
                    "title": profile.get("title"),
                    "source": source,
                },
            )

    def _load_project_members(self, project_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
        if not project_id:
            return {}
        if hasattr(self.db, "list_project_members"):
            data = self.db.list_project_members(project_id, include_roles=True)
            members = data.get("members") if isinstance(data, dict) else []
            return {m["user_id"]: m for m in members if m.get("user_id")}
        return {}

    def _apply_llm_inference(
        self,
        builder: "_GraphBuilder",
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        enabled: bool,
        model: str,
        inference_limit: int,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        empty_stats = {
            "enabled": enabled,
            "model": model,
            "candidate_pair_count": 0,
            "inferred_edge_count": 0,
        }
        if not enabled or self.ai is None:
            return empty_stats

        pair_budget = max(6, min(80, int(inference_limit or 48)))
        selected_pairs = candidate_pairs[:pair_budget]
        if not selected_pairs:
            return empty_stats

        prompt_payload = {
            "project_id": project_id,
            "session_id": session_id,
            "candidate_pairs": [
                {
                    "source": pair["source"],
                    "target": pair["target"],
                    "score": pair["score"],
                    "signals": pair["signals"],
                    "source_requirement": self._serialize_requirement_feature(
                        requirement_features[pair["source"]]
                    ),
                    "target_requirement": self._serialize_requirement_feature(
                        requirement_features[pair["target"]]
                    ),
                    "existing_relations": _existing_pair_relations(
                        builder,
                        pair["source"],
                        pair["target"],
                    ),
                }
                for pair in selected_pairs
                if pair["source"] in requirement_features and pair["target"] in requirement_features
            ],
        }
        if not prompt_payload["candidate_pairs"]:
            return empty_stats

        system_prompt = (
            "你是需求-需求关系裁决器。"
            "输入中每一项都是候选需求对，只能基于这些候选对做有限补充，不能自由生成全图关系。"
            "不要创造新节点，不要输出输入中不存在的 source/target。"
            "只允许输出这些关系类型："
            f"{sorted(_REQ_REQ_INFERRED_TYPES)}。"
            "每条边必须包含 confidence、reason、evidence。"
            "若依据不足，请不要输出该关系。"
            '只返回严格 JSON：{"edges":[{"source":"req:...","target":"req:...","type":"DEPENDS_ON","confidence":0.78,"reason":"...","evidence":["..."]}]}'
        )
        user_prompt = (
            "请仅对这些候选需求对做关系裁决。"
            "优先补充 DEPENDS_ON、CONFLICTS_WITH、VALIDATES_WITH；INCLUDES、EXTENDS、IMPACTS 只在有直接证据时输出。"
            "如果某对已经有结构或规则关系，只在你确认同类型关系也成立时输出，让系统做合并。"
            "输入数据如下：\n"
            + json.dumps(prompt_payload, ensure_ascii=False)
        )
        response = self.ai.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=0.1,
            max_tokens=3200,
        )
        parsed = _extract_json_payload(response.get("content") or "")
        edges = parsed.get("edges") if isinstance(parsed, dict) else []
        valid_pairs = {
            tuple(sorted((pair["source"], pair["target"])))
            for pair in selected_pairs
        }
        alias_lookup = self._build_node_alias_lookup(builder, set(requirement_features.keys()))
        inferred_count = 0
        for raw_edge in edges if isinstance(edges, list) else []:
            edge = self._normalize_inferred_requirement_edge(
                raw_edge,
                valid_node_ids=set(requirement_features.keys()),
                valid_pairs=valid_pairs,
                alias_lookup=alias_lookup,
            )
            if not edge:
                continue
            edge_key = (edge["source"], edge["target"], edge["type"])
            existed_before = edge_key in builder.edges
            builder.add_edge(
                edge["source"],
                edge["target"],
                edge["type"],
                label=_edge_label(edge["type"]),
                weight=edge["confidence"],
                properties={
                    "source_kind": "llm",
                    "source_detail": "llm_inference",
                    "source": "llm_inference",
                    "confidence": edge["confidence"],
                    "reason": edge["reason"],
                    "evidence": edge["evidence"],
                    "model": model,
                },
            )
            if not existed_before and builder.edges.get(edge_key):
                inferred_count += 1

        return {
            "enabled": enabled,
            "model": model,
            "candidate_pair_count": len(prompt_payload["candidate_pairs"]),
            "inferred_edge_count": inferred_count,
        }

    def _serialize_requirement_feature(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": feature["id"],
            "req_id": feature.get("req_id"),
            "title": feature.get("title"),
            "description": _short_text(feature.get("description"), 200),
            "source_level": feature.get("source_level"),
            "requirement_type": feature.get("requirement_type"),
            "status": feature.get("status"),
            "priority": feature.get("priority"),
            "tags": sorted(feature.get("tags") or []),
            "modules": sorted(feature.get("modules") or []),
            "interface_terms": sorted(feature.get("interface_terms") or []),
            "validation_terms": sorted(feature.get("validation_terms") or []),
        }

    def _normalize_inferred_requirement_edge(
        self,
        raw_edge: Any,
        *,
        valid_node_ids: set[str],
        valid_pairs: set[Tuple[str, str]],
        alias_lookup: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_edge, dict):
            return None
        source = _resolve_node_reference(raw_edge.get("source"), valid_node_ids, alias_lookup)
        target = _resolve_node_reference(raw_edge.get("target"), valid_node_ids, alias_lookup)
        edge_type = self._clean(raw_edge.get("type"))
        if not source or not target or not edge_type or source == target:
            return None
        if edge_type not in _REQ_REQ_INFERRED_TYPES:
            return None
        pair_key = tuple(sorted((source, target)))
        if pair_key not in valid_pairs:
            return None
        if edge_type in _SYMMETRIC_EDGE_TYPES and source > target:
            source, target = target, source
        evidence = _compact_list(_as_list(raw_edge.get("evidence")))
        return {
            "source": source,
            "target": target,
            "type": edge_type,
            "confidence": max(0.0, min(1.0, _float_or_default(raw_edge.get("confidence"), 0.65))),
            "reason": self._clean(raw_edge.get("reason")) or "",
            "evidence": evidence[:8],
        }

    def _build_inference_scope(
        self,
        builder: "_GraphBuilder",
        inference_limit: int,
    ) -> Dict[str, Any]:
        inference_limit = max(12, min(120, int(inference_limit or 48)))
        requirement_nodes = [
            node for node in builder.nodes.values() if node.get("kind") == "requirement"
        ]
        stakeholder_nodes = [
            node for node in builder.nodes.values() if node.get("kind") == "stakeholder"
        ]
        if not requirement_nodes:
            return {
                "requirements": [],
                "stakeholders": [],
                "existing_edges": [],
                "all_node_ids": set(),
            }

        requirement_budget = min(
            len(requirement_nodes),
            max(8, min(inference_limit - 4, int(inference_limit * 0.75))),
        )
        requirement_ids = self._select_requirement_candidates(
            requirement_nodes,
            builder.edges.values(),
            requirement_budget,
        )

        stakeholder_budget = max(0, min(len(stakeholder_nodes), inference_limit - len(requirement_ids)))
        stakeholder_ids = self._select_stakeholder_candidates(
            requirement_ids,
            stakeholder_nodes,
            builder.edges.values(),
            builder.nodes,
            stakeholder_budget,
        )

        requirements = [
            self._serialize_requirement_node(builder.nodes[node_id])
            for node_id in requirement_ids
            if node_id in builder.nodes
        ]
        stakeholders = [
            self._serialize_stakeholder_node(builder.nodes[node_id])
            for node_id in stakeholder_ids
            if node_id in builder.nodes
        ]
        scoped_ids = set(requirement_ids) | set(stakeholder_ids)
        existing_edges = [
            {
                "source": edge["source"],
                "target": edge["target"],
                "type": edge["type"],
                "confidence": edge["weight"],
                "source_detail": (edge.get("properties") or {}).get("source"),
                "reason": (edge.get("properties") or {}).get("reason"),
            }
            for edge in builder.edges.values()
            if edge["source"] in scoped_ids and edge["target"] in scoped_ids
        ]
        return {
            "requirements": requirements,
            "stakeholders": stakeholders,
            "existing_edges": existing_edges,
            "all_node_ids": scoped_ids,
        }

    def _select_requirement_candidates(
        self,
        requirement_nodes: List[Dict[str, Any]],
        edges: Iterable[Dict[str, Any]],
        budget: int,
    ) -> List[str]:
        budget = max(1, budget)
        degree_map: Dict[str, int] = defaultdict(int)
        neighbor_map: Dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if not (str(source).startswith("req:") and str(target).startswith("req:")):
                continue
            if source == target:
                continue
            degree_map[source] += 1
            degree_map[target] += 1
            neighbor_map[source].add(target)
            neighbor_map[target].add(source)

        def requirement_score(node: Dict[str, Any]) -> Tuple[int, int, int, str]:
            props = node.get("properties") or {}
            priority = int(_float_or_default(props.get("priority"), 0))
            validation = props.get("validation_rules") or {}
            validation_bonus = 10 if any(validation.values()) else 0
            people_bonus = 6 if any(props.get(field) for field in ("created_by", "updated_by", "assignee")) else 0
            category_bonus = 8 if props.get("category") else 0
            module_bonus = 6 if _infer_target_modules(props) else 0
            score = (
                degree_map.get(node["id"], 0) * 100
                + priority * 18
                + _level_priority(props.get("level")) * 8
                + validation_bonus
                + people_bonus
                + category_bonus
                + module_bonus
            )
            return (score, degree_map.get(node["id"], 0), priority, node["id"])

        sorted_nodes = sorted(
            requirement_nodes,
            key=lambda node: (
                -requirement_score(node)[0],
                -requirement_score(node)[1],
                -requirement_score(node)[2],
                node["id"],
            ),
        )
        by_id = {node["id"]: node for node in requirement_nodes}
        selected_ids: List[str] = []

        def add_requirement(node_id: Optional[str]) -> None:
            if node_id and node_id in by_id and node_id not in selected_ids and len(selected_ids) < budget:
                selected_ids.append(node_id)

        category_best: Dict[str, str] = {}
        level_best: Dict[str, str] = {}
        for node in sorted_nodes:
            props = node.get("properties") or {}
            category = _clean_label(props.get("category"))
            level = _clean_label(props.get("level")) or "managed"
            if category and category not in category_best:
                category_best[category] = node["id"]
            if level not in level_best:
                level_best[level] = node["id"]

        for node_id in category_best.values():
            add_requirement(node_id)
        for node_id in level_best.values():
            add_requirement(node_id)
        for node in sorted_nodes[: max(4, min(10, budget))]:
            add_requirement(node["id"])

        for anchor_id in list(selected_ids):
            for neighbor_id in sorted(
                [
                    node_id
                    for node_id in neighbor_map.get(anchor_id, set())
                    if node_id in by_id
                ],
                key=lambda node_id: (
                    -requirement_score(by_id[node_id])[0],
                    by_id[node_id]["id"],
                ),
            ):
                add_requirement(neighbor_id)

        for node in sorted_nodes:
            add_requirement(node["id"])
        return selected_ids

    def _select_stakeholder_candidates(
        self,
        requirement_ids: List[str],
        stakeholder_nodes: List[Dict[str, Any]],
        edges: Iterable[Dict[str, Any]],
        all_nodes: Dict[str, Dict[str, Any]],
        budget: int,
    ) -> List[str]:
        if budget <= 0 or not stakeholder_nodes:
            return []
        requirement_set = set(requirement_ids)
        mention_counts: Dict[str, int] = defaultdict(int)
        stakeholder_by_id = {node["id"]: node for node in stakeholder_nodes}

        for req_id in requirement_ids:
            props = (all_nodes.get(req_id) or {}).get("properties") or {}
            for field, weight in (("assignee", 4), ("created_by", 2), ("updated_by", 1)):
                user_id = self._clean(props.get(field))
                stakeholder_id = _stakeholder_node_id(user_id) if user_id else None
                if stakeholder_id and stakeholder_id in stakeholder_by_id:
                    mention_counts[stakeholder_id] += weight

        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source in requirement_set and target in stakeholder_by_id:
                mention_counts[target] += 3
            if target in requirement_set and source in stakeholder_by_id:
                mention_counts[source] += 3

        def stakeholder_score(node: Dict[str, Any]) -> Tuple[int, int, int, str]:
            props = node.get("properties") or {}
            source_priority = {
                "project_members/auth_users": 4,
                "llm_inference": 3,
                "requirement_people_evidence": 2,
            }.get(props.get("source"), 1)
            metadata_bonus = (
                (4 if props.get("role") else 0)
                + (3 if _as_list(props.get("roles")) else 0)
                + (2 if props.get("department") else 0)
                + (2 if props.get("title") else 0)
            )
            mentions = mention_counts.get(node["id"], 0)
            score = mentions * 100 + source_priority * 20 + metadata_bonus
            return (score, mentions, source_priority, node["id"])

        sorted_nodes = sorted(
            stakeholder_nodes,
            key=lambda node: (
                -stakeholder_score(node)[0],
                -stakeholder_score(node)[1],
                -stakeholder_score(node)[2],
                node["id"],
            ),
        )
        selected_ids: List[str] = []
        for node in sorted_nodes:
            if len(selected_ids) >= budget:
                break
            if stakeholder_score(node)[0] <= 0 and selected_ids:
                break
            selected_ids.append(node["id"])
        return selected_ids

    def _serialize_requirement_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        props = node.get("properties", {})
        return {
            "id": node["id"],
            "label": node.get("label"),
            "level": props.get("level"),
            "category": props.get("category"),
            "type": props.get("type"),
            "status": props.get("status"),
            "priority": props.get("priority"),
            "content": _short_text(props.get("content") or props.get("title"), 220),
            "target_modules": _infer_target_modules(props),
            "people_evidence": _drop_none(
                {
                    "created_by": props.get("created_by"),
                    "updated_by": props.get("updated_by"),
                    "assignee": props.get("assignee"),
                }
            ),
            "validation_evidence": _drop_none(
                {
                    "validation_rules": props.get("validation_rules"),
                    "interfaces": _as_list(props.get("interfaces")),
                    "data_contracts": _as_list(props.get("data_contracts")),
                    "error_handling": _as_list(props.get("error_handling")),
                }
            ),
        }

    def _serialize_stakeholder_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        props = node.get("properties", {})
        return {
            "id": node["id"],
            "label": node.get("label"),
            "role": props.get("role"),
            "roles": _as_list(props.get("roles")),
            "type": props.get("type"),
            "department": props.get("department"),
            "title": props.get("title"),
            "source": props.get("source"),
        }

    def _merge_inferred_stakeholders(
        self,
        builder: "_GraphBuilder",
        raw_stakeholders: List[Any],
        *,
        model: str,
        valid_node_ids: set[str],
    ) -> Dict[str, Any]:
        existing_ids = set(builder.nodes)
        existing_alias_lookup = self._build_node_alias_lookup(builder, valid_node_ids)
        label_lookup: Dict[str, List[str]] = defaultdict(list)
        for node_id, node in builder.nodes.items():
            if node_id not in valid_node_ids or node.get("kind") != "stakeholder":
                continue
            label_lookup[_normalize_text(node.get("label"))].append(node_id)
        alias_lookup: Dict[str, str] = {}
        inferred_node_ids: List[str] = []

        for raw_stakeholder in raw_stakeholders:
            stakeholder = self._normalize_inferred_stakeholder(raw_stakeholder)
            if not stakeholder:
                continue

            normalized_label = _normalize_text(stakeholder["label"])
            matched_id = _resolve_node_reference(
                stakeholder["id"],
                valid_node_ids,
                existing_alias_lookup,
            )
            if not matched_id:
                compatible_ids = [
                    node_id
                    for node_id in label_lookup.get(normalized_label, [])
                    if _stakeholder_profiles_compatible(builder.nodes.get(node_id), stakeholder)
                ]
                if len(compatible_ids) == 1:
                    matched_id = compatible_ids[0]
            final_id = matched_id or stakeholder["id"]
            existed_before = final_id in builder.nodes
            builder.add_node(
                final_id,
                kind="stakeholder",
                label=stakeholder["label"],
                group=stakeholder.get("type") or stakeholder.get("role") or "stakeholder",
                properties=_drop_none(
                    {
                        "name": stakeholder["label"],
                        "role": stakeholder.get("role"),
                        "roles": stakeholder.get("roles"),
                        "type": stakeholder.get("type"),
                        "department": stakeholder.get("department"),
                        "title": stakeholder.get("title"),
                        "source": "llm_inference" if not matched_id else builder.nodes[final_id]["properties"].get("source"),
                        "inference_reason": stakeholder.get("reason"),
                        "inference_model": model,
                    }
                ),
            )
            if final_id not in builder.nodes:
                continue
            alias_lookup[stakeholder["id"]] = final_id
            alias_lookup[stakeholder["label"]] = final_id
            alias_lookup[normalized_label] = final_id
            if final_id not in label_lookup[normalized_label]:
                label_lookup[normalized_label].append(final_id)
            if not existed_before and final_id not in existing_ids:
                inferred_node_ids.append(final_id)

        return {
            "alias_lookup": alias_lookup,
            "node_ids": inferred_node_ids,
            "inferred_count": len(inferred_node_ids),
        }

    def _normalize_inferred_stakeholder(self, raw_stakeholder: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_stakeholder, dict):
            return None
        label = self._clean(
            raw_stakeholder.get("label")
            or raw_stakeholder.get("name")
            or raw_stakeholder.get("stakeholder")
        )
        if not label:
            return None
        raw_id = self._clean(raw_stakeholder.get("id")) or _llm_stakeholder_node_id(label)
        node_id = raw_id if raw_id.startswith("stakeholder:") else _stakeholder_node_id(raw_id)
        roles = _compact_list(
            _as_list(raw_stakeholder.get("roles") or raw_stakeholder.get("role"))
        )
        role = self._clean(raw_stakeholder.get("role")) or _first_present(*roles)
        return {
            "id": node_id,
            "label": label,
            "role": role,
            "roles": roles,
            "type": self._clean(raw_stakeholder.get("type")),
            "department": self._clean(raw_stakeholder.get("department")),
            "title": self._clean(raw_stakeholder.get("title")),
            "reason": self._clean(raw_stakeholder.get("reason")),
        }

    def _build_node_alias_lookup(
        self,
        builder: "_GraphBuilder",
        valid_node_ids: set[str],
    ) -> Dict[str, str]:
        alias_lookup: Dict[str, str] = {}
        for node_id, node in builder.nodes.items():
            if node_id not in valid_node_ids:
                continue
            alias_lookup[node_id] = node_id
            label = self._clean(node.get("label"))
            if label:
                alias_lookup[label] = node_id
                alias_lookup[_normalize_text(label)] = node_id
            props = node.get("properties") or {}
            for value in (
                props.get("req_id"),
                props.get("user_id"),
                props.get("username"),
                props.get("name"),
            ):
                clean_value = self._clean(value)
                if clean_value:
                    alias_lookup[clean_value] = node_id
                    alias_lookup[_normalize_text(clean_value)] = node_id
        return alias_lookup

    def _normalize_inferred_edge(
        self,
        raw_edge: Any,
        valid_node_ids: set[str],
        alias_lookup: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_edge, dict):
            return None
        source = _resolve_node_reference(raw_edge.get("source"), valid_node_ids, alias_lookup)
        target = _resolve_node_reference(raw_edge.get("target"), valid_node_ids, alias_lookup)
        edge_type = self._clean(raw_edge.get("type"))
        if not source or not target or not edge_type or source == target:
            return None
        if source not in valid_node_ids or target not in valid_node_ids:
            return None
        source_kind = "stakeholder" if source.startswith("stakeholder:") else "requirement"
        target_kind = "stakeholder" if target.startswith("stakeholder:") else "requirement"
        if (
            source_kind == "requirement"
            and target_kind == "requirement"
            and edge_type not in _REQ_REQ_INFERRED_TYPES
        ):
            return None
        if (
            source_kind == "stakeholder"
            and target_kind == "requirement"
            and edge_type not in _STAKEHOLDER_REQ_INFERRED_TYPES
        ):
            return None
        if (
            source_kind == "stakeholder"
            and target_kind == "stakeholder"
            and edge_type not in _STAKEHOLDER_STAKEHOLDER_INFERRED_TYPES
        ):
            return None
        if edge_type in _UNDIRECTED_EDGE_TYPES and source > target:
            source, target = target, source
        return {
            "source": source,
            "target": target,
            "type": edge_type,
            "confidence": max(0.0, min(1.0, _float_or_default(raw_edge.get("confidence"), 0.65))),
            "reason": self._clean(raw_edge.get("reason")) or "",
        }

    @staticmethod
    def _clean(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class _GraphBuilder:
    def __init__(self, limit: int):
        self.limit = limit
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    def add_node(
        self,
        node_id: str,
        kind: str,
        label: Optional[str],
        group: Optional[str],
        properties: Dict[str, Any],
    ) -> None:
        if not node_id:
            return
        if node_id in self.nodes:
            self.nodes[node_id]["properties"].update(_drop_none(properties))
            if label and not self.nodes[node_id].get("label"):
                self.nodes[node_id]["label"] = label
            return
        if len(self.nodes) >= self.limit:
            return
        self.nodes[node_id] = {
            "id": node_id,
            "kind": kind,
            "label": label or node_id,
            "group": group or kind,
            "size": 18 if kind == "stakeholder" else 22,
            "properties": _drop_none(properties),
        }

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        label: str,
        weight: float,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not source or not target or source == target:
            return
        if edge_type in _SYMMETRIC_EDGE_TYPES and source > target:
            source, target = target, source
        key = (source, target, edge_type)
        normalized_properties = _normalize_edge_properties(properties or {}, weight)
        if key in self.edges:
            self.edges[key]["weight"] = round(max(self.edges[key]["weight"], float(weight)), 3)
            self.edges[key]["properties"] = _merge_edge_properties(
                self.edges[key]["properties"],
                normalized_properties,
                edge_type=edge_type,
            )
            return
        self.edges[key] = {
            "id": f"{edge_type}:{source}->{target}",
            "source": source,
            "target": target,
            "type": edge_type,
            "label": label,
            "weight": round(float(weight), 3),
            "properties": normalized_properties,
        }

    def to_graph(self) -> Dict[str, Any]:
        valid_edges = [
            edge
            for edge in self.edges.values()
            if edge["source"] in self.nodes and edge["target"] in self.nodes
        ]
        edge_counts = Counter(edge["type"] for edge in valid_edges)
        node_counts = Counter(node["kind"] for node in self.nodes.values())
        level_counts = Counter(
            str(node.get("properties", {}).get("source_level") or node.get("group") or "UNKNOWN_LEVEL")
            for node in self.nodes.values()
            if node.get("kind") == "requirement"
        )
        edge_source_counts = Counter(
            (edge.get("properties") or {}).get("source_kind") or "rule"
            for edge in valid_edges
        )
        return {
            "nodes": list(self.nodes.values()),
            "edges": valid_edges,
            "stats": {
                "node_count": len(self.nodes),
                "edge_count": len(valid_edges),
                "node_counts": dict(node_counts),
                "edge_counts": dict(edge_counts),
                "level_counts": {level: level_counts.get(level, 0) for level in _LEVEL_ORDER},
                "edge_source_counts": dict(edge_source_counts),
                "structural_edge_count": edge_source_counts.get("structural", 0),
                "rule_edge_count": edge_source_counts.get("rule", 0),
            },
            "legend": {
                "node_kinds": ["requirement"],
                "edge_types": sorted(edge_counts.keys()),
            },
        }


def _req_node_id(req_id: Any) -> str:
    if str(req_id).startswith("req:"):
        return str(req_id)
    return f"req:{req_id}"


def _stakeholder_node_id(user_id: Any) -> str:
    return f"stakeholder:{user_id}"


def _llm_stakeholder_node_id(label: Any) -> str:
    normalized = _normalize_text(label)
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:10] if normalized else "unknown"
    return f"stakeholder:llm:{digest}"


def _short_text(text: Any, max_len: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return "未命名需求"
    return value if len(value) <= max_len else f"{value[:max_len]}..."


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _index_text(text_index: Dict[str, List[str]], node_id: str, *texts: Any) -> None:
    for text in texts:
        normalized = _normalize_text(text)
        if normalized:
            text_index[normalized].append(node_id)


def _resolve_requirement_node(
    explicit_id: Any,
    text: Any,
    text_index: Dict[str, List[str]],
) -> Optional[str]:
    if explicit_id:
        return _req_node_id(explicit_id)
    normalized = _normalize_text(text)
    matches = text_index.get(normalized) or []
    return matches[0] if matches else None


def _resolve_requirement_node_fuzzy(
    text: Any,
    text_index: Dict[str, List[str]],
) -> Optional[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return None

    short_key = normalized[:48]
    for indexed_text, node_ids in text_index.items():
        if not indexed_text or not node_ids:
            continue
        if normalized in indexed_text or indexed_text in normalized:
            return node_ids[0]
        if short_key and (indexed_text.startswith(short_key) or short_key.startswith(indexed_text[:48])):
            return node_ids[0]
    return None


def _resolve_node_reference(
    value: Any,
    valid_node_ids: set[str],
    alias_lookup: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    if value is None:
        return None
    clean_value = str(value).strip()
    if not clean_value:
        return None
    if clean_value in valid_node_ids:
        return clean_value
    if alias_lookup:
        if clean_value in alias_lookup:
            return alias_lookup[clean_value]
        normalized = _normalize_text(clean_value)
        if normalized in alias_lookup:
            return alias_lookup[normalized]
    return None


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            return {"raw": value}
    return {"value": value}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except Exception:
            return [text]
    return [value]


def _compact_list(values: Iterable[Any]) -> List[str]:
    return [str(v).strip() for v in values if str(v or "").strip()]


def _drop_none(value: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in value.items() if v is not None}


def _normalize_source_level(source_level: Any, requirement_type: Any) -> str:
    normalized = str(source_level or "").strip().upper()
    if normalized in {"L1", "L2", "L3", "L4"}:
        return normalized
    if str(requirement_type or "").strip().lower() == "low_level":
        return "L4"
    return "UNKNOWN_LEVEL"


def _flatten_values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        flattened: List[str] = []
        for nested in value.values():
            flattened.extend(_flatten_values(nested))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for nested in value:
            flattened.extend(_flatten_values(nested))
        return flattened
    text = str(value).strip()
    return [text] if text else []


def _extract_modules(req: Dict[str, Any]) -> set[str]:
    custom_fields = _as_dict(req.get("custom_fields"))
    candidates = _compact_list(
        _flatten_values(
            [
                custom_fields.get("module"),
                custom_fields.get("modules"),
                custom_fields.get("target_module"),
                custom_fields.get("target_modules"),
                custom_fields.get("component"),
                custom_fields.get("components"),
            ]
        )
    )
    modules = {
        _normalize_signal(value)
        for value in candidates
        if _normalize_signal(value)
    }
    for tag in _compact_list(_as_list(req.get("tags"))):
        normalized_tag = _normalize_signal(tag)
        if normalized_tag and normalized_tag not in _GENERIC_TERMS:
            if ":" in normalized_tag:
                modules.add(normalized_tag.split(":", 1)[1])
            elif normalized_tag.endswith("模块") or normalized_tag.endswith("service"):
                modules.add(normalized_tag)
    return modules


def _extract_terms(text: Any) -> set[str]:
    value = str(text or "")
    terms = {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{2,}", value.lower())
        if _is_informative_term(token)
    }
    for token in re.findall(r"[\u4e00-\u9fff]{2,8}", value):
        normalized = token.strip().lower()
        if normalized and _is_informative_term(normalized):
            terms.add(normalized)
    return terms


def _build_semantic_text(
    req: Dict[str, Any],
    title: str,
    description: str,
    custom_fields: Optional[Dict[str, Any]] = None,
) -> str:
    custom_fields = custom_fields or {}
    return " ".join(
        part
        for part in [
            title,
            description,
            " ".join(_compact_list(_as_list(req.get("tags")))),
            " ".join(_compact_list(_flatten_values(custom_fields))),
        ]
        if part
    )


def _is_informative_term(term: str) -> bool:
    normalized = str(term or "").strip().lower()
    if not normalized or normalized in _NON_INFORMATIVE_TERMS:
        return False
    if re.fullmatch(r"[a-z][a-z0-9_/-]*", normalized) and len(normalized) < 4:
        return False
    return True


def _max_term_document_frequency(requirement_count: int) -> int:
    if requirement_count <= 0:
        return 0
    return max(2, min(12, int(requirement_count * 0.3) or 2))


def _semantic_embedding_enabled() -> bool:
    enabled = os.environ.get("REQUIREMENT_GRAPH_ENABLE_EMBEDDING", "1").strip().lower()
    if enabled in {"0", "false", "off", "no"}:
        return False
    return "PYTEST_CURRENT_TEST" not in os.environ


def _get_semantic_embedder():
    global _semantic_embedder, _semantic_embedding_error
    if _semantic_embedding_error:
        return None
    if _semantic_embedder is not None:
        return _semantic_embedder

    with _semantic_embedder_lock:
        if _semantic_embedding_error:
            return None
        if _semantic_embedder is not None:
            return _semantic_embedder
        try:
            from sentence_transformers import SentenceTransformer

            _semantic_embedder = SentenceTransformer(_SEMANTIC_EMBEDDING_MODEL)
        except Exception as exc:
            _semantic_embedding_error = str(exc)
            logger.warning("Requirement graph semantic embedder unavailable: %s", exc)
            return None
    return _semantic_embedder


def _to_float_vector(vector: Any) -> List[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()
    return [float(item) for item in vector]


def _extract_interface_terms(text: Any, custom_fields: Optional[Dict[str, Any]] = None) -> set[str]:
    value = " ".join(
        _compact_list(
            [
                str(text or ""),
                " ".join(_compact_list(_flatten_values(custom_fields or {}))),
            ]
        )
    )
    interface_terms = {
        _normalize_signal(token)
        for token in re.findall(r"(?:GET|POST|PUT|PATCH|DELETE)\s+[^\s,;]+|/[A-Za-z0-9_/-]+", value, re.I)
    }
    resource_terms = {
        _normalize_signal(term)
        for term in _RESOURCE_TERMS
        if term.lower() in value.lower()
    }
    return {term for term in interface_terms | resource_terms if term}


def _extract_validation_terms(text: Any) -> set[str]:
    value = str(text or "")
    markers = {
        _normalize_signal(term)
        for term in _VALIDATION_MARKERS
        if term.lower() in value.lower()
    }
    for token in re.findall(r"[\u4e00-\u9fff]{2,8}", value):
        if any(marker in token for marker in _VALIDATION_MARKERS):
            normalized = _normalize_signal(token)
            if normalized:
                markers.add(normalized)
    return markers


def _normalize_signal(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _shared_values(left: Iterable[str], right: Iterable[str]) -> List[str]:
    return sorted(set(left) & set(right))


def _cosine_similarity(left: Any, right: Any) -> float:
    if not left or not right:
        return 0.0
    left_values = left if isinstance(left, list) else _to_float_vector(left)
    right_values = right if isinstance(right, list) else _to_float_vector(right)
    if len(left_values) != len(right_values) or not left_values:
        return 0.0
    return sum(lv * rv for lv, rv in zip(left_values, right_values))


def _match_dependency_rule(
    source_feature: Dict[str, Any],
    target_feature: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    evidence: List[str] = []
    text = source_feature["text_lower"]
    if not any(marker in text for marker in _DEPENDENCY_MARKERS):
        return None
    shared_modules = _shared_values(source_feature["modules"], target_feature["modules"])
    if shared_modules:
        evidence.extend(f"shared_module:{item}" for item in shared_modules[:3])
    mentioned_modules = [
        module
        for module in target_feature["modules"]
        if module and module in text
    ]
    if mentioned_modules:
        evidence.extend(f"mentioned_module:{item}" for item in mentioned_modules[:3])
    shared_interfaces = _shared_values(
        source_feature["interface_terms"],
        target_feature["interface_terms"],
    )
    if shared_interfaces:
        evidence.extend(f"shared_interface:{item}" for item in shared_interfaces[:3])
    shared_terms = [
        term
        for term in _shared_values(source_feature["terms"], target_feature["terms"])
        if term not in _NON_INFORMATIVE_TERMS
    ]
    if not (shared_modules or mentioned_modules or shared_interfaces):
        return None
    if shared_terms:
        evidence.extend(f"shared_term:{item}" for item in shared_terms[:2])
    return {
        "detail": "rule_dependency_signal_match",
        "confidence": 0.82 if mentioned_modules or shared_interfaces else 0.74,
        "reason": "依赖/调用表达与模块或接口信号重合",
        "evidence": evidence[:6],
    }


def _match_conflict_rule(
    left_feature: Dict[str, Any],
    right_feature: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    left_text = left_feature["text_lower"]
    right_text = right_feature["text_lower"]
    evidence: List[str] = []
    if any(marker in left_text or marker in right_text for marker in _CONFLICT_MARKERS):
        evidence.append("explicit_conflict_marker")

    opposite_groups = [
        ({"加密", "脱敏", "鉴权", "权限"}, {"明文", "匿名", "开放访问"}),
        ({"低延迟", "实时", "高性能"}, {"强一致", "审计", "复杂校验"}),
        ({"独占", "专用", "单租户"}, {"共享", "多租户"}),
        ({"异步", "缓存"}, {"同步", "强一致"}),
    ]
    for left_terms, right_terms in opposite_groups:
        left_hit = any(term.lower() in left_text for term in left_terms)
        right_hit = any(term.lower() in right_text for term in right_terms)
        reverse_left_hit = any(term.lower() in left_text for term in right_terms)
        reverse_right_hit = any(term.lower() in right_text for term in left_terms)
        if (left_hit and right_hit) or (reverse_left_hit and reverse_right_hit):
            evidence.append("opposite_constraints")
            break

    shared_resources = _shared_values(left_feature["interface_terms"], right_feature["interface_terms"])
    if shared_resources:
        evidence.extend(f"shared_resource:{item}" for item in shared_resources[:3])
    if not evidence:
        return None
    return {
        "detail": "rule_conflict_signal_match",
        "confidence": 0.85 if "opposite_constraints" in evidence else 0.76,
        "reason": "约束方向相反或争抢同一资源",
        "evidence": evidence[:6],
    }


def _match_validation_rule(
    left_feature: Dict[str, Any],
    right_feature: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    shared_validation = _shared_values(
        left_feature["validation_terms"],
        right_feature["validation_terms"],
    )
    shared_modules = _shared_values(left_feature["modules"], right_feature["modules"])
    if not shared_validation:
        return None
    evidence = [f"shared_validation:{item}" for item in shared_validation[:4]]
    evidence.extend(f"shared_module:{item}" for item in shared_modules[:2])
    return {
        "detail": "rule_validation_overlap",
        "confidence": 0.78 if shared_modules else 0.72,
        "reason": "验收或验证方式高度重合",
        "evidence": evidence[:6],
    }


def _match_similarity_rule(
    left_feature: Dict[str, Any],
    right_feature: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    shared_tags = _shared_values(left_feature["tags"], right_feature["tags"])
    shared_modules = _shared_values(left_feature["modules"], right_feature["modules"])
    shared_interfaces = _shared_values(
        left_feature["interface_terms"],
        right_feature["interface_terms"],
    )
    shared_terms = [
        term
        for term in _shared_values(left_feature["terms"], right_feature["terms"])
        if term not in _NON_INFORMATIVE_TERMS
    ]
    semantic_similarity = _cosine_similarity(
        left_feature.get("embedding"),
        right_feature.get("embedding"),
    )
    lexical_anchor = bool(shared_modules or shared_interfaces)
    corroborated_overlap = (bool(shared_tags) and len(shared_terms) >= 3) or len(shared_terms) >= 4

    if semantic_similarity > 0:
        if semantic_similarity < _SEMANTIC_SIMILARITY_THRESHOLD:
            return None
        if not (lexical_anchor or corroborated_overlap):
            return None
    elif not (
        (shared_modules and (shared_tags or shared_interfaces or shared_terms))
        or (shared_interfaces and len(shared_terms) >= 2)
        or corroborated_overlap
    ):
        return None

    evidence = [f"shared_tag:{item}" for item in shared_tags[:3]]
    evidence.extend(f"shared_module:{item}" for item in shared_modules[:3])
    evidence.extend(f"shared_interface:{item}" for item in shared_interfaces[:2])
    evidence.extend(f"shared_term:{item}" for item in shared_terms[:3])
    if semantic_similarity > 0:
        evidence.append(f"semantic_similarity:{semantic_similarity:.3f}")
    return {
        "detail": "semantic_similarity_match" if semantic_similarity > 0 else "rule_similarity_recall",
        "confidence": round(min(0.92, semantic_similarity), 3) if semantic_similarity > 0 else 0.66,
        "reason": "句向量与模块/接口/关键词信号同时接近" if semantic_similarity > 0 else "模块、接口或关键词高度重合",
        "evidence": evidence[:6],
    }


def _has_stronger_relation(builder: "_GraphBuilder", left_id: str, right_id: str) -> bool:
    pair = {left_id, right_id}
    for edge in builder.edges.values():
        if {edge["source"], edge["target"]} != pair:
            continue
        if edge["type"] != "SIMILAR_TO":
            return True
    return False


def _existing_pair_relations(
    builder: "_GraphBuilder",
    left_id: str,
    right_id: str,
) -> List[Dict[str, Any]]:
    relations = []
    for edge in builder.edges.values():
        if {edge["source"], edge["target"]} != {left_id, right_id}:
            continue
        props = edge.get("properties") or {}
        relations.append(
            {
                "source": edge["source"],
                "target": edge["target"],
                "type": edge["type"],
                "source_kind": props.get("source_kind"),
                "source_detail": props.get("source_detail"),
            }
        )
    return relations


def _normalize_edge_properties(properties: Dict[str, Any], weight: float) -> Dict[str, Any]:
    props = dict(properties or {})
    source_detail = (
        props.get("source_detail")
        or props.get("source")
        or "unknown"
    )
    source_kind = props.get("source_kind") or _infer_source_kind(source_detail)
    evidence = _merge_evidence([], _as_list(props.get("evidence")), limit=12)
    reason = str(props.get("reason") or "").strip()
    confidence = _float_or_default(props.get("confidence"), weight)
    merged_sources = props.get("sources")
    if not isinstance(merged_sources, list) or not merged_sources:
        merged_sources = [{"kind": source_kind, "detail": source_detail}]
    source_kinds = []
    source_details = []
    for item in merged_sources:
        kind = str((item or {}).get("kind") or source_kind)
        detail = str((item or {}).get("detail") or source_detail)
        if kind not in source_kinds:
            source_kinds.append(kind)
        if detail not in source_details:
            source_details.append(detail)
    return _drop_none(
        {
            **{k: v for k, v in props.items() if k not in {"evidence", "sources"}},
            "source": source_detail,
            "source_kind": source_kind,
            "source_detail": source_detail,
            "source_kinds": source_kinds,
            "source_details": source_details,
            "sources": merged_sources,
            "confidence": round(confidence, 3),
            "reason": reason or None,
            "evidence": evidence,
        }
    )


def _merge_edge_properties(
    current: Dict[str, Any],
    incoming: Dict[str, Any],
    *,
    edge_type: str,
) -> Dict[str, Any]:
    current_quality = _edge_quality(current, edge_type)
    incoming_quality = _edge_quality(incoming, edge_type)
    primary = incoming if incoming_quality > current_quality else current
    secondary = current if primary is incoming else incoming
    merged_sources = _merge_source_entries(current.get("sources"), incoming.get("sources"))
    merged_evidence = _merge_evidence(current.get("evidence"), incoming.get("evidence"), limit=12)
    return _drop_none(
        {
            **secondary,
            **primary,
            "source_kinds": _ordered_unique(
                list(current.get("source_kinds") or []) + list(incoming.get("source_kinds") or []),
                key=lambda item: (-_SOURCE_KIND_PRIORITY.get(item, 0), item),
            ),
            "source_details": _ordered_unique(
                list(current.get("source_details") or []) + list(incoming.get("source_details") or []),
            ),
            "sources": merged_sources,
            "evidence": merged_evidence,
            "confidence": round(
                max(
                    _float_or_default(current.get("confidence"), 0),
                    _float_or_default(incoming.get("confidence"), 0),
                ),
                3,
            ),
            "reason": primary.get("reason") or secondary.get("reason"),
        }
    )


def _edge_quality(properties: Dict[str, Any], edge_type: str) -> Tuple[int, int, float]:
    return (
        _SOURCE_KIND_PRIORITY.get(properties.get("source_kind"), 0),
        _RELATION_PRIORITY.get(edge_type, 0),
        _float_or_default(properties.get("confidence"), 0),
    )


def _infer_source_kind(source_detail: Any) -> str:
    detail = str(source_detail or "").lower()
    if detail.startswith("manage_requirements."):
        return "structural"
    if "llm" in detail:
        return "llm"
    return "rule"


def _merge_source_entries(current: Any, incoming: Any) -> List[Dict[str, str]]:
    merged = []
    seen = set()
    for item in list(current or []) + list(incoming or []):
        kind = str((item or {}).get("kind") or "").strip() or "rule"
        detail = str((item or {}).get("detail") or "").strip() or "unknown"
        key = (kind, detail)
        if key in seen:
            continue
        seen.add(key)
        merged.append({"kind": kind, "detail": detail})
    return sorted(
        merged,
        key=lambda item: (-_SOURCE_KIND_PRIORITY.get(item["kind"], 0), item["detail"]),
    )


def _merge_evidence(current: Any, incoming: Any, *, limit: int = 8) -> List[str]:
    merged = []
    seen = set()
    for value in list(_as_list(current)) + list(_as_list(incoming)):
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
        if len(merged) >= limit:
            break
    return merged


def _ordered_unique(values: List[str], key=None) -> List[str]:
    unique = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return sorted(unique, key=key) if key else unique


def _infer_target_modules(props: Dict[str, Any]) -> List[str]:
    direct_values = _compact_list(_as_list(props.get("target_modules") or props.get("component")))
    if direct_values:
        return direct_values
    custom_fields = _as_dict(props.get("custom_fields"))
    return _compact_list(
        [
            custom_fields.get("target_module"),
            custom_fields.get("target_modules"),
            custom_fields.get("module"),
            custom_fields.get("modules"),
        ]
    )


def _level_priority(level: Any) -> int:
    normalized = str(level or "").strip().upper()
    if "L1" in normalized:
        return 5
    if "L2" in normalized:
        return 4
    if "L3" in normalized:
        return 3
    if "L4" in normalized:
        return 2
    return 1


def _stakeholder_profiles_compatible(
    existing_node: Optional[Dict[str, Any]],
    inferred_stakeholder: Dict[str, Any],
) -> bool:
    if not existing_node:
        return False
    props = existing_node.get("properties") or {}
    existing_roles = {
        _normalize_text(item)
        for item in _compact_list(_as_list(props.get("roles") or props.get("role")))
    }
    inferred_roles = {
        _normalize_text(item)
        for item in _compact_list(
            _as_list(inferred_stakeholder.get("roles") or inferred_stakeholder.get("role"))
        )
    }
    if existing_roles and inferred_roles and existing_roles.isdisjoint(inferred_roles):
        return False

    for field in ("type", "department", "title"):
        existing_value = _normalize_text(props.get(field))
        inferred_value = _normalize_text(inferred_stakeholder.get(field))
        if existing_value and inferred_value and existing_value != inferred_value:
            return False
    return True


def _extract_json_payload(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fenced_match:
        raw = fenced_match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _clean_label(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_label_distribution(value: Any) -> Dict[str, int]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return {}
    if not isinstance(value, dict):
        return {}

    distribution: Dict[str, int] = {}
    for label, count in value.items():
        clean_label = _clean_label(label)
        if not clean_label:
            continue
        try:
            distribution[clean_label] = int(count or 0)
        except (TypeError, ValueError):
            distribution[clean_label] = 0
    return distribution


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_present(*values: Optional[str]) -> Optional[str]:
    return next((value for value in values if value), None)


def _pick_index(values: List[Any], index: int) -> Any:
    return values[index] if 0 <= index < len(values) else None


def _edge_label(edge_type: str) -> str:
    return {
        "REFINES": "细化",
        "DEPENDS_ON": "依赖",
        "CONFLICTS_WITH": "冲突",
        "SIMILAR_TO": "相似",
        "INCLUDES": "包含",
        "EXTENDS": "扩展",
        "IMPACTS": "影响",
        "VALIDATES_WITH": "验证关联",
        "RAISES": "提出",
        "OWNS": "负责",
        "AFFECTED_BY": "受影响",
        "APPROVES": "审批",
        "BENEFITS_FROM": "受益",
        "OPPOSES": "反对",
        "INTEREST_CONFLICTS_WITH": "利益冲突",
        "COLLABORATES_WITH": "协作",
    }.get(edge_type, edge_type)
