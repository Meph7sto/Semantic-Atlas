import logging
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import (
    _SEMANTIC_EMBEDDING_MODEL,
    _SEMANTIC_PAIR_MAX_REQUIREMENTS,
    _SEMANTIC_PAIR_THRESHOLD,
)
from .graph_core import _edge_label, _has_stronger_relation, _req_node_id
from .helpers import (
    _as_dict,
    _as_list,
    _build_semantic_text,
    _compact_list,
    _cosine_similarity,
    _extract_interface_terms,
    _extract_modules,
    _extract_terms,
    _extract_validation_terms,
    _flatten_values,
    _float_or_default,
    _get_semantic_embedder,
    _match_conflict_rule,
    _match_dependency_rule,
    _match_similarity_rule,
    _match_validation_rule,
    _max_term_document_frequency,
    _merge_evidence,
    _level_priority,
    _normalize_source_level,
    _get_semantic_embedding_error,
    _semantic_embedding_enabled,
    _short_text,
    _shared_values,
    _to_float_vector,
)

logger = logging.getLogger(__name__)


class RequirementGraphFeatureEngine:
    """Feature extraction and candidate recall for requirement graphs."""

    def __init__(self, clean):
        self._clean = clean

    def apply_project_edges(
        self,
        builder,
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

    def build_requirement_feature(
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
            "tags": {tag.lower() for tag in _compact_list(_as_list(req.get("tags")))},
            "modules": _extract_modules(req),
            "terms": _extract_terms(text),
            "interface_terms": _extract_interface_terms(text, custom_fields),
            "validation_terms": _extract_validation_terms(validation_text or text),
            "custom_fields": custom_fields,
        }

    def attach_semantic_embeddings(
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

    def get_local_embedding_status(
        self,
        requirement_features: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        has_embedding = any(feature.get("embedding") for feature in requirement_features.values())
        error = _get_semantic_embedding_error()
        return {
            "enabled": _semantic_embedding_enabled(),
            "available": has_embedding,
            "error": error,
            "model": _SEMANTIC_EMBEDDING_MODEL,
        }

    def apply_local_vector_edges(
        self,
        builder,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
        *,
        relation_limit: int,
        embedding_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        embedding_status = embedding_status or {}
        limit = max(6, min(120, int(relation_limit or 48)))
        selected_pairs = candidate_pairs[:limit]
        added_count = 0
        reviewed_count = 0
        edge_counter: Counter[str] = Counter()

        for pair in selected_pairs:
            source = pair.get("source")
            target = pair.get("target")
            source_feature = requirement_features.get(source)
            target_feature = requirement_features.get(target)
            if not source_feature or not target_feature:
                continue

            relation_candidates = self._build_local_relation_candidates(
                builder,
                pair,
                source_feature=source_feature,
                target_feature=target_feature,
            )
            if not relation_candidates:
                continue

            reviewed_count += 1
            for relation in relation_candidates:
                edge_type = relation["type"]
                edge_key = self._edge_key(relation["source"], relation["target"], edge_type)
                existed_before = edge_key in builder.edges
                builder.add_edge(
                    relation["source"],
                    relation["target"],
                    edge_type,
                    label=_edge_label(edge_type),
                    weight=relation["confidence"],
                    properties={
                        "source_kind": "local_vector",
                        "source_detail": relation["detail"],
                        "source": relation["detail"],
                        "confidence": relation["confidence"],
                        "reason": relation["reason"],
                        "evidence": relation["evidence"],
                        "model": _SEMANTIC_EMBEDDING_MODEL,
                    },
                )
                if not existed_before and edge_key in builder.edges:
                    added_count += 1
                    edge_counter[edge_type] += 1

        return {
            "enabled": True,
            "model": _SEMANTIC_EMBEDDING_MODEL,
            "available": bool(embedding_status.get("available", True)),
            "error": embedding_status.get("error"),
            "candidate_pair_count": len(selected_pairs),
            "reviewed_pair_count": reviewed_count,
            "added_count": added_count,
            "edge_counts": dict(edge_counter),
        }

    def collect_candidate_pairs(
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
        semantic_neighbors = self.collect_semantic_candidate_neighbors(
            requirement_features,
            per_requirement_limit=per_requirement_limit,
        )

        for node_id, feature in requirement_features.items():
            candidate_scores: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"score": 0, "evidence": []}
            )
            self.accumulate_candidates(
                node_id,
                feature["modules"],
                signal_indexes["modules"],
                candidate_scores,
                score=5,
                evidence_label="shared_module",
            )
            self.accumulate_candidates(
                node_id,
                feature["tags"],
                signal_indexes["tags"],
                candidate_scores,
                score=4,
                evidence_label="shared_tag",
            )
            self.accumulate_candidates(
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
            self.accumulate_candidates(
                node_id,
                feature["interface_terms"],
                signal_indexes["interfaces"],
                candidate_scores,
                score=4,
                evidence_label="shared_interface",
            )
            self.accumulate_candidates(
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
                    {"pair": pair_key, "score": 0, "signals": [], "requesters": set()},
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

    def collect_semantic_candidate_neighbors(
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

    def accumulate_candidates(
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

    @staticmethod
    def _extract_semantic_confidence(signals: Any) -> float:
        semantic_scores: List[float] = []
        for item in _as_list(signals):
            match = re.match(r"semantic_match:(\d+(?:\.\d+)?)", str(item or "").strip())
            if not match:
                continue
            semantic_scores.append(float(match.group(1)))
        if not semantic_scores:
            return 0.0
        return round(min(0.96, max(semantic_scores)), 3)

    def _build_local_relation_candidates(
        self,
        builder,
        pair: Dict[str, Any],
        *,
        source_feature: Dict[str, Any],
        target_feature: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        relation_candidates: List[Dict[str, Any]] = []
        semantic_confidence = self._extract_semantic_confidence(pair.get("signals"))

        dependency_lr = _match_dependency_rule(source_feature, target_feature)
        dependency_rl = _match_dependency_rule(target_feature, source_feature)
        conflict = _match_conflict_rule(source_feature, target_feature)
        validation = _match_validation_rule(source_feature, target_feature)
        similarity = _match_similarity_rule(source_feature, target_feature)

        for left_feature, right_feature, relation in (
            (source_feature, target_feature, dependency_lr),
            (target_feature, source_feature, dependency_rl),
        ):
            if relation:
                relation_candidates.append(
                    self._local_relation_candidate(
                        left_feature["id"],
                        right_feature["id"],
                        edge_type="DEPENDS_ON",
                        detail="local_vector.semantic_dependency",
                        relation=relation,
                        pair_signals=pair.get("signals"),
                        semantic_confidence=semantic_confidence,
                    )
                )

        if conflict:
            relation_candidates.append(
                self._local_relation_candidate(
                    source_feature["id"],
                    target_feature["id"],
                    edge_type="CONFLICTS_WITH",
                    detail="local_vector.semantic_conflict",
                    relation=conflict,
                    pair_signals=pair.get("signals"),
                    semantic_confidence=semantic_confidence,
                )
            )

        if validation:
            relation_candidates.append(
                self._local_relation_candidate(
                    source_feature["id"],
                    target_feature["id"],
                    edge_type="VALIDATES_WITH",
                    detail="local_vector.semantic_validation",
                    relation=validation,
                    pair_signals=pair.get("signals"),
                    semantic_confidence=semantic_confidence,
                )
            )

        for extra_relation in (
            self._match_local_includes_relation(source_feature, target_feature, pair, similarity=similarity),
            self._match_local_extends_relation(source_feature, target_feature, pair, similarity=similarity),
            self._match_local_impacts_relation(source_feature, target_feature, pair, similarity=similarity),
        ):
            if extra_relation:
                relation_candidates.append(extra_relation)

        if not relation_candidates and similarity and not _has_stronger_relation(
            builder, source_feature["id"], target_feature["id"]
        ):
            relation_candidates.append(
                self._local_relation_candidate(
                    source_feature["id"],
                    target_feature["id"],
                    edge_type="SIMILAR_TO",
                    detail="local_vector.semantic_candidate_recall",
                    relation=similarity,
                    pair_signals=pair.get("signals"),
                    semantic_confidence=semantic_confidence,
                    fallback_reason="本地向量模型召回的高相关需求对",
                )
            )

        deduped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for candidate in relation_candidates:
            key = self._edge_key(candidate["source"], candidate["target"], candidate["type"])
            current = deduped.get(key)
            if current is None or candidate["confidence"] > current["confidence"]:
                deduped[key] = candidate
        return list(deduped.values())

    def _local_relation_candidate(
        self,
        source: str,
        target: str,
        *,
        edge_type: str,
        detail: str,
        relation: Dict[str, Any],
        pair_signals: Any,
        semantic_confidence: float,
        fallback_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        confidence = _float_or_default(relation.get("confidence"), 0.68)
        if semantic_confidence > 0:
            confidence = max(confidence, min(0.93, semantic_confidence))
        return {
            "source": source,
            "target": target,
            "type": edge_type,
            "detail": detail,
            "confidence": round(confidence, 3),
            "reason": relation.get("reason") or fallback_reason or "本地语义候选边",
            "evidence": _merge_evidence(relation.get("evidence"), pair_signals, limit=10),
        }

    def _match_local_includes_relation(
        self,
        left_feature: Dict[str, Any],
        right_feature: Dict[str, Any],
        pair: Dict[str, Any],
        *,
        similarity: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        semantic_confidence = self._extract_semantic_confidence(pair.get("signals"))
        if semantic_confidence < 0.72 and not similarity:
            return None
        overlap = self._shared_overlap(left_feature, right_feature)
        if not (overlap["modules"] or overlap["interfaces"] or len(overlap["terms"]) >= 3):
            return None
        left_level = _level_priority(left_feature.get("source_level"))
        right_level = _level_priority(right_feature.get("source_level"))
        if left_level == right_level:
            return None
        source_feature, target_feature = (
            (left_feature, right_feature) if left_level > right_level else (right_feature, left_feature)
        )
        reason = "高层需求与低层需求主题高度重叠，可作为包含候选"
        evidence = [
            *(f"shared_module:{item}" for item in overlap["modules"][:2]),
            *(f"shared_interface:{item}" for item in overlap["interfaces"][:2]),
            *(f"shared_term:{item}" for item in overlap["terms"][:2]),
            f"semantic_match:{semantic_confidence:.3f}" if semantic_confidence > 0 else None,
        ]
        return {
            "source": source_feature["id"],
            "target": target_feature["id"],
            "type": "INCLUDES",
            "detail": "local_vector.semantic_include",
            "confidence": round(max(0.7, min(0.84, semantic_confidence or 0.74)), 3),
            "reason": reason,
            "evidence": _merge_evidence([], [item for item in evidence if item], limit=10),
        }

    def _match_local_extends_relation(
        self,
        left_feature: Dict[str, Any],
        right_feature: Dict[str, Any],
        pair: Dict[str, Any],
        *,
        similarity: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        semantic_confidence = self._extract_semantic_confidence(pair.get("signals"))
        if semantic_confidence < 0.7 and not similarity:
            return None
        markers = ("扩展", "增强", "附加", "追加", "可选", "兼容", "插件", "升级")
        left_hits = [marker for marker in markers if marker in left_feature.get("text_lower", "")]
        right_hits = [marker for marker in markers if marker in right_feature.get("text_lower", "")]
        if bool(left_hits) == bool(right_hits):
            return None
        overlap = self._shared_overlap(left_feature, right_feature)
        if not (overlap["modules"] or overlap["interfaces"] or len(overlap["terms"]) >= 2):
            return None
        source_feature, target_feature = (
            (left_feature, right_feature) if left_hits else (right_feature, left_feature)
        )
        evidence = [
            *(f"extension_marker:{item}" for item in (left_hits or right_hits)[:2]),
            *(f"shared_module:{item}" for item in overlap["modules"][:2]),
            *(f"shared_interface:{item}" for item in overlap["interfaces"][:2]),
            *(f"shared_term:{item}" for item in overlap["terms"][:2]),
            f"semantic_match:{semantic_confidence:.3f}" if semantic_confidence > 0 else None,
        ]
        return {
            "source": source_feature["id"],
            "target": target_feature["id"],
            "type": "EXTENDS",
            "detail": "local_vector.semantic_extend",
            "confidence": round(max(0.69, min(0.82, semantic_confidence or 0.72)), 3),
            "reason": "扩展/增强语义与主题重叠同时出现，可作为扩展候选",
            "evidence": _merge_evidence([], [item for item in evidence if item], limit=10),
        }

    def _match_local_impacts_relation(
        self,
        left_feature: Dict[str, Any],
        right_feature: Dict[str, Any],
        pair: Dict[str, Any],
        *,
        similarity: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        semantic_confidence = self._extract_semantic_confidence(pair.get("signals"))
        if semantic_confidence < 0.74 and not similarity:
            return None
        overlap = self._shared_overlap(left_feature, right_feature)
        if not (overlap["modules"] or overlap["interfaces"] or len(overlap["terms"]) >= 3):
            return None

        markers = ("影响", "联动", "变更", "同步", "触发", "通知", "回写", "传播")
        left_hits = [marker for marker in markers if marker in left_feature.get("text_lower", "")]
        right_hits = [marker for marker in markers if marker in right_feature.get("text_lower", "")]
        if bool(left_hits) != bool(right_hits):
            source_feature, target_feature = (
                (left_feature, right_feature) if left_hits else (right_feature, left_feature)
            )
        else:
            left_level = _level_priority(left_feature.get("source_level"))
            right_level = _level_priority(right_feature.get("source_level"))
            if left_level == right_level:
                return None
            source_feature, target_feature = (
                (left_feature, right_feature) if left_level > right_level else (right_feature, left_feature)
            )

        evidence = [
            *(f"impact_marker:{item}" for item in (left_hits or right_hits)[:2]),
            *(f"shared_module:{item}" for item in overlap["modules"][:2]),
            *(f"shared_interface:{item}" for item in overlap["interfaces"][:2]),
            *(f"shared_term:{item}" for item in overlap["terms"][:2]),
            f"semantic_match:{semantic_confidence:.3f}" if semantic_confidence > 0 else None,
        ]
        return {
            "source": source_feature["id"],
            "target": target_feature["id"],
            "type": "IMPACTS",
            "detail": "local_vector.semantic_impact",
            "confidence": round(max(0.7, min(0.84, semantic_confidence or 0.73)), 3),
            "reason": "变更/联动语义与主题重叠同时出现，可作为影响候选",
            "evidence": _merge_evidence([], [item for item in evidence if item], limit=10),
        }

    @staticmethod
    def _shared_overlap(
        left_feature: Dict[str, Any],
        right_feature: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        return {
            "modules": _shared_values(left_feature.get("modules") or [], right_feature.get("modules") or []),
            "interfaces": _shared_values(
                left_feature.get("interface_terms") or [],
                right_feature.get("interface_terms") or [],
            ),
            "terms": [
                term
                for term in _shared_values(left_feature.get("terms") or [], right_feature.get("terms") or [])
                if term
            ],
        }

    @staticmethod
    def _edge_key(source: str, target: str, edge_type: str) -> Tuple[str, str, str]:
        if edge_type in {"SIMILAR_TO", "CONFLICTS_WITH", "VALIDATES_WITH"} and source > target:
            source, target = target, source
        return source, target, edge_type
