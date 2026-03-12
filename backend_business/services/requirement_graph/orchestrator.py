from collections import Counter, defaultdict
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend_business.services.ai_proxy import ai_proxy

from .constants import (
    _LEVEL_ORDER,
    _REQ_REQ_INFERRED_TYPES,
    _SYMMETRIC_EDGE_TYPES,
)
from .data_access import RequirementGraphDataAccess
from .dependency_audit import RequirementGraphDependencyAudit
from .enrichers import RequirementGraphEnricher
from .feature_engine import RequirementGraphFeatureEngine
from .graph_core import (
    _GraphBuilder,
    _edge_label,
    _existing_pair_relations,
    _index_text,
    _normalize_edge_key,
    _req_node_id,
    _resolve_node_reference,
)
from .helpers import _as_list, _compact_list, _float_or_default, _normalize_source_level
from .inference_engine import RequirementGraphInferenceEngine
from .relation_review import _RequirementGraphRelationReviewCoordinator

logger = logging.getLogger(__name__)


class RequirementGraphService:
    """Orchestrates requirement graph assembly while delegating to focused modules."""

    def __init__(self, db_service: Any, ai_client: Any = None):
        self.db = db_service
        self.ai = ai_client or ai_proxy
        self._data_access = RequirementGraphDataAccess(self.db)
        self._feature_engine = RequirementGraphFeatureEngine(self._clean)
        self._dependency_audit = RequirementGraphDependencyAudit(self)
        self._inference_engine = RequirementGraphInferenceEngine(self)
        self._enricher = RequirementGraphEnricher(self, self._data_access)

    def build_graph(
        self,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 600,
        infer_relations: bool = False,
        relation_mode: Optional[str] = None,
        inference_model: str = "deepseek-reasoner",
        inference_limit: int = 48,
        review_edges: Optional[List[Dict[str, Any]]] = None,
        review_concurrency: int = 3,
    ) -> Dict[str, Any]:
        project_id = self._clean(project_id) or self._resolve_project_id_by_session(
            self._clean(session_id)
        )
        session_id = self._clean(session_id) or self._resolve_project_session(project_id)
        limit = max(50, min(2000, int(limit or 600)))
        review_concurrency = max(1, min(8, int(review_concurrency or 3)))

        builder = _GraphBuilder(limit=limit)
        project_requirements = self._load_project_requirements(project_id, limit)
        requirement_features: Dict[str, Dict[str, Any]] = {}
        text_index: Dict[str, List[str]] = defaultdict(list)

        for req in project_requirements:
            node_id = _req_node_id(req.get("req_id"))
            normalized_level = _normalize_source_level(
                req.get("source_level"),
                req.get("requirement_type"),
            )
            builder.add_node(
                node_id,
                kind="requirement",
                label=req.get("title"),
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
                    "custom_fields": req.get("custom_fields") if isinstance(req.get("custom_fields"), dict) else None,
                    "source": "manage_requirements",
                    "created_by": req.get("created_by"),
                    "updated_by": req.get("updated_by"),
                },
            )
            requirement_features[node_id] = self._build_requirement_feature(req, normalized_level)
            _index_text(
                text_index,
                node_id,
                req.get("req_id"),
                req.get("source_req_id"),
                req.get("title"),
                req.get("description"),
                " ".join(
                    part
                    for part in [
                        str(req.get("title") or "").strip(),
                        str(req.get("description") or "").strip(),
                    ]
                    if part
                ),
            )

        self._attach_semantic_embeddings(requirement_features)
        local_embedding_status = self._feature_engine.get_local_embedding_status(
            requirement_features
        )
        self._apply_project_edges(builder, project_requirements)
        trace_stats = self._apply_trace_edges(builder, session_id, text_index)
        conflict_stats = self._apply_conflict_edges(builder, session_id, text_index)
        classification_stats = self._apply_classification(builder, session_id, text_index)
        normalized_relation_mode = self._normalize_relation_mode(
            relation_mode,
            infer_relations=infer_relations,
        )
        supplied_review_edges = self._normalize_review_edges(
            review_edges,
            requirement_features=requirement_features,
            relation_limit=inference_limit,
        )

        if normalized_relation_mode in {"local", "llm"}:
            if normalized_relation_mode == "llm" and supplied_review_edges:
                candidate_pairs, candidate_stats = self._build_candidate_pairs_from_review_edges(
                    supplied_review_edges,
                    requirement_features=requirement_features,
                    relation_limit=inference_limit,
                )
            else:
                candidate_pairs, candidate_stats = self._collect_candidate_pairs(requirement_features)
        else:
            candidate_pairs = []
            candidate_stats = {
                "pair_count": 0,
                "per_requirement_limit": 0,
                "per_requirement_counts": {},
                "requirement_count": len(requirement_features),
                "max_term_document_frequency": 0,
            }

        if normalized_relation_mode == "local":
            local_vector_stats = self._apply_local_vector_edges(
                builder,
                requirement_features,
                candidate_pairs,
                relation_limit=inference_limit,
                embedding_status=local_embedding_status,
            )
            rule_stats = {
                "edge_counts": {},
                "dependency_audit": {
                    "model": inference_model,
                    "candidate_count": 0,
                    "reviewed_count": 0,
                    "confirmed_count": 0,
                    "rejected_count": 0,
                    "fallback_used": False,
                    "pruned_transitive_count": 0,
                },
            }
            relation_review_stats = {
                "package_count": 0,
                "reviewed_pair_count": 0,
                "added_count": 0,
                "updated_count": 0,
                "deleted_count": 0,
                "fallback_used": False,
                "model": inference_model,
                "requested_concurrency": review_concurrency,
                "applied_concurrency": 0,
            }
        elif normalized_relation_mode == "llm":
            if supplied_review_edges:
                local_vector_stats = self._apply_review_seed_edges(
                    builder,
                    supplied_review_edges,
                )
                rule_stats = {
                    "edge_counts": {},
                    "dependency_audit": {
                        "model": inference_model,
                        "candidate_count": 0,
                        "reviewed_count": 0,
                        "confirmed_count": 0,
                        "rejected_count": 0,
                        "fallback_used": False,
                        "pruned_transitive_count": 0,
                    },
                }
            else:
                local_vector_stats = self._apply_local_vector_edges(
                    builder,
                    requirement_features,
                    candidate_pairs,
                    relation_limit=inference_limit,
                    embedding_status=local_embedding_status,
                )
                rule_stats = self._apply_rule_edges(
                    builder,
                    requirement_features,
                    candidate_pairs,
                    dependency_model=inference_model,
                    dependency_review_limit=inference_limit,
                    include_authoritative_relations=False,
                )
            relation_review_stats = self._apply_llm_relation_review(
                builder,
                project_id=project_id,
                session_id=session_id,
                enabled=True,
                model=inference_model,
                inference_limit=inference_limit,
                review_concurrency=review_concurrency,
                requirement_features=requirement_features,
                candidate_pairs=candidate_pairs,
                inferred_relation_types=_REQ_REQ_INFERRED_TYPES,
            )
        else:
            local_vector_stats = {
                "enabled": False,
                "model": local_embedding_status.get("model"),
                "available": local_embedding_status.get("available", False),
                "error": local_embedding_status.get("error"),
                "candidate_pair_count": 0,
                "reviewed_pair_count": 0,
                "added_count": 0,
            }
            rule_stats = {
                "edge_counts": {},
                "dependency_audit": {
                    "model": inference_model,
                    "candidate_count": 0,
                    "reviewed_count": 0,
                    "confirmed_count": 0,
                    "rejected_count": 0,
                    "fallback_used": False,
                    "pruned_transitive_count": 0,
                },
            }
            relation_review_stats = {
                "package_count": 0,
                "reviewed_pair_count": 0,
                "added_count": 0,
                "updated_count": 0,
                "deleted_count": 0,
                "fallback_used": False,
                "model": inference_model,
                "requested_concurrency": review_concurrency,
                "applied_concurrency": 0,
            }
        self._prune_weaker_similar_edges(builder)

        graph = builder.to_graph()
        analysis_edge_counts = self._count_edges_by_source_kinds(
            graph["edges"],
            {"trace_analysis", "conflict_analysis", "classification_analysis"},
        )
        supplemental_edge_counts = self._count_edges_by_source_kinds(
            graph["edges"],
            {"local_vector", "rule_extra", "llm"},
        )
        graph["stats"]["strong_edge_count"] = graph["stats"]["structural_edge_count"] + analysis_edge_counts["total"]
        graph["stats"]["inferred_edge_count"] = (
            relation_review_stats["added_count"] + relation_review_stats["updated_count"]
        )
        graph["stats"]["analysis_edge_count"] = analysis_edge_counts["total"]
        graph["stats"]["supplemental_edge_count"] = supplemental_edge_counts["total"]
        graph["stats"]["edge_source_counts"] = {
            **graph["stats"].get("edge_source_counts", {}),
            **analysis_edge_counts["by_kind"],
            **supplemental_edge_counts["by_kind"],
        }
        graph["stats"]["candidate_pair_count"] = candidate_stats["pair_count"]
        graph["stats"]["candidate_pairs_per_requirement_limit"] = candidate_stats["per_requirement_limit"]
        graph["stats"]["candidate_requirement_count"] = candidate_stats["requirement_count"]
        graph["stats"]["source_requirement_count"] = len(project_requirements)
        graph["stats"]["review_seed_edge_count"] = len(supplied_review_edges)
        graph["stats"]["rule_edge_counts"] = rule_stats["edge_counts"]
        graph["stats"]["dependency_audit"] = rule_stats["dependency_audit"]
        graph["stats"]["local_vector"] = local_vector_stats
        graph["stats"]["relation_review"] = relation_review_stats
        graph["stats"]["review_concurrency"] = review_concurrency
        graph["stats"]["classification_label_distribution"] = classification_stats["label_distribution"]
        graph["stats"]["classification_matched_count"] = classification_stats["matched_count"]
        graph["stats"]["trace_edge_count"] = trace_stats["edge_count"]
        graph["stats"]["conflict_edge_count"] = conflict_stats["edge_count"]
        graph["stats"]["classification_edge_count"] = classification_stats["edge_count"]
        graph["meta"] = {
            "project_id": project_id,
            "session_id": session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": {
                "manage_requirements": len(project_requirements),
                "trace_analysis": trace_stats["edge_count"],
                "conflict_analysis": conflict_stats["edge_count"],
                "classification_analysis": classification_stats["edge_count"],
                "local_vector": supplemental_edge_counts["by_kind"].get("local_vector", 0),
                "rule_extra": supplemental_edge_counts["by_kind"].get("rule_extra", 0),
                "llm": supplemental_edge_counts["by_kind"].get("llm", 0),
            },
            "analysis_records": {
                "trace_record_id": trace_stats.get("record_id"),
                "conflict_batch_id": conflict_stats.get("batch_id"),
                "classification_record_id": classification_stats.get("record_id"),
            },
            "candidate_recall": candidate_stats,
            "relation_mode": normalized_relation_mode,
            "review_seed_edge_count": len(supplied_review_edges),
            "review_concurrency": review_concurrency,
            "local_vector": local_vector_stats,
            "dependency_audit": rule_stats["dependency_audit"],
            "inference": relation_review_stats,
            "relation_review": relation_review_stats,
        }
        persistence_stats = self._persist_relation_snapshot(
            project_id=project_id,
            session_id=session_id,
            relation_mode=normalized_relation_mode,
            graph=graph,
        )
        if persistence_stats:
            graph["meta"]["relation_snapshot"] = persistence_stats
        graph["legend"]["levels"] = _LEVEL_ORDER
        return graph

    def get_latest_snapshot_graph(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        relation_mode: Optional[str] = None,
        limit: int = 600,
    ) -> Optional[Dict[str, Any]]:
        get_latest_snapshot = getattr(self.db, "get_latest_requirement_graph_snapshot", None)
        if not callable(get_latest_snapshot):
            return None
        snapshot = get_latest_snapshot(
            project_id=self._clean(project_id),
            session_id=self._clean(session_id),
            relation_mode=self._clean(relation_mode),
        )
        if not snapshot:
            return None
        return self._build_graph_from_snapshot(snapshot, limit=limit)

    def list_snapshot_history(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        relation_mode: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        list_snapshots = getattr(self.db, "list_requirement_graph_snapshots", None)
        if not callable(list_snapshots):
            return []
        return list_snapshots(
            project_id=self._clean(project_id),
            session_id=self._clean(session_id),
            relation_mode=self._clean(relation_mode),
            limit=max(1, min(100, int(limit or 20))),
        )

    def get_snapshot_graph(self, snapshot_id: str, *, limit: int = 600) -> Dict[str, Any]:
        get_snapshot = getattr(self.db, "get_requirement_graph_snapshot_by_id", None)
        if not callable(get_snapshot):
            raise ValueError("当前数据库服务不支持需求图谱快照读取")
        snapshot = get_snapshot(snapshot_id)
        if not snapshot:
            raise ValueError("未找到指定的需求图谱快照")
        return self._build_graph_from_snapshot(snapshot, limit=limit)

    def _resolve_project_session(self, project_id: Optional[str]) -> Optional[str]:
        return self._data_access.resolve_project_session(project_id)

    def _resolve_project_id_by_session(self, session_id: Optional[str]) -> Optional[str]:
        return self._data_access.resolve_project_id_by_session(session_id)

    def _load_project_requirements(self, project_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._data_access.load_project_requirements(project_id, limit)

    def _build_graph_from_snapshot(self, snapshot: Dict[str, Any], *, limit: int) -> Dict[str, Any]:
        project_id = self._clean(snapshot.get("project_id")) or self._resolve_project_id_by_session(
            self._clean(snapshot.get("session_id"))
        )
        session_id = self._clean(snapshot.get("session_id")) or self._resolve_project_session(project_id)
        builder = _GraphBuilder(limit=max(50, min(2000, int(limit or 600))))
        project_requirements = self._load_project_requirements(project_id, builder.limit)

        for req in project_requirements:
            normalized_level = _normalize_source_level(
                req.get("source_level"),
                req.get("requirement_type"),
            )
            builder.add_node(
                _req_node_id(req.get("req_id")),
                kind="requirement",
                label=req.get("title"),
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
                    "custom_fields": req.get("custom_fields") if isinstance(req.get("custom_fields"), dict) else None,
                    "source": "manage_requirements",
                    "created_by": req.get("created_by"),
                    "updated_by": req.get("updated_by"),
                },
            )

        for edge in snapshot.get("edges") or []:
            edge_type = str(edge.get("relation_type") or "").strip()
            source = self._clean(edge.get("source_node_id"))
            target = self._clean(edge.get("target_node_id"))
            if not source or not target or not edge_type:
                continue
            properties = dict(edge.get("properties") or {})
            if edge.get("source_kind") and not properties.get("source_kind"):
                properties["source_kind"] = edge.get("source_kind")
            if edge.get("source_detail") and not properties.get("source_detail"):
                properties["source_detail"] = edge.get("source_detail")
            if edge.get("confidence") is not None and properties.get("confidence") is None:
                properties["confidence"] = edge.get("confidence")
            if edge.get("reason") and not properties.get("reason"):
                properties["reason"] = edge.get("reason")
            if isinstance(edge.get("evidence"), list) and not properties.get("evidence"):
                properties["evidence"] = edge.get("evidence")
            if edge.get("model") and not properties.get("model"):
                properties["model"] = edge.get("model")
            if edge.get("review_action") and not properties.get("review_action"):
                properties["review_action"] = edge.get("review_action")
            if edge.get("review_package_id") and not properties.get("review_package_id"):
                properties["review_package_id"] = edge.get("review_package_id")
            builder.add_edge(
                source,
                target,
                edge_type,
                _edge_label(edge_type),
                _float_or_default(edge.get("weight"), 0.0),
                properties=properties,
            )

        graph = builder.to_graph()
        analysis_edge_counts = self._count_edges_by_source_kinds(
            graph["edges"],
            {"trace_analysis", "conflict_analysis", "classification_analysis"},
        )
        supplemental_edge_counts = self._count_edges_by_source_kinds(
            graph["edges"],
            {"local_vector", "rule_extra", "llm"},
        )
        graph["stats"]["strong_edge_count"] = graph["stats"]["structural_edge_count"] + analysis_edge_counts["total"]
        graph["stats"]["inferred_edge_count"] = supplemental_edge_counts["by_kind"].get("llm", 0)
        graph["stats"]["analysis_edge_count"] = analysis_edge_counts["total"]
        graph["stats"]["supplemental_edge_count"] = supplemental_edge_counts["total"]
        graph["stats"]["edge_source_counts"] = {
            **graph["stats"].get("edge_source_counts", {}),
            **analysis_edge_counts["by_kind"],
            **supplemental_edge_counts["by_kind"],
        }
        graph["meta"] = {
            "project_id": project_id,
            "session_id": session_id,
            "generated_at": snapshot.get("created_at"),
            "loaded_from_snapshot": True,
            "relation_mode": snapshot.get("relation_mode"),
            "relation_snapshot": {
                "snapshot_id": snapshot.get("snapshot_id"),
                "relation_mode": snapshot.get("relation_mode"),
                "edge_count": snapshot.get("edge_count", len(graph["edges"])),
                "created_at": snapshot.get("created_at"),
                "invalidated_at": snapshot.get("invalidated_at"),
                "is_active": snapshot.get("is_active"),
            },
        }
        graph["legend"]["levels"] = _LEVEL_ORDER
        return graph

    def _load_l123_requirements(self, session_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._data_access.load_l123_requirements(session_id, limit)

    def _load_l4_requirements(self, session_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._data_access.load_l4_requirements(session_id, limit)

    def _apply_project_edges(self, builder: _GraphBuilder, project_requirements: Iterable[Dict[str, Any]]) -> None:
        self._feature_engine.apply_project_edges(builder, project_requirements)

    def _build_requirement_feature(self, req: Dict[str, Any], normalized_level: str) -> Dict[str, Any]:
        return self._feature_engine.build_requirement_feature(req, normalized_level)

    def _attach_semantic_embeddings(self, requirement_features: Dict[str, Dict[str, Any]]) -> None:
        self._feature_engine.attach_semantic_embeddings(requirement_features)

    def _collect_candidate_pairs(
        self,
        requirement_features: Dict[str, Dict[str, Any]],
        per_requirement_limit: int = 10,
    ):
        return self._feature_engine.collect_candidate_pairs(
            requirement_features,
            per_requirement_limit=per_requirement_limit,
        )

    def _collect_semantic_candidate_neighbors(
        self,
        requirement_features: Dict[str, Dict[str, Any]],
        *,
        per_requirement_limit: int,
    ):
        return self._feature_engine.collect_semantic_candidate_neighbors(
            requirement_features,
            per_requirement_limit=per_requirement_limit,
        )

    def _apply_local_vector_edges(
        self,
        builder: _GraphBuilder,
        requirement_features,
        candidate_pairs,
        *,
        relation_limit: int,
        embedding_status: Optional[Dict[str, Any]] = None,
    ):
        return self._feature_engine.apply_local_vector_edges(
            builder,
            requirement_features,
            candidate_pairs,
            relation_limit=relation_limit,
            embedding_status=embedding_status,
        )

    def _apply_review_seed_edges(
        self,
        builder: _GraphBuilder,
        review_edges: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        edge_counter: Counter[str] = Counter()
        pair_keys = set()
        added_count = 0
        model = None

        for edge in review_edges:
            source = edge["source"]
            target = edge["target"]
            edge_type = edge["type"]
            props = edge["properties"]
            edge_key = _normalize_edge_key(source, target, edge_type)
            existed_before = edge_key in builder.edges
            builder.add_edge(
                source,
                target,
                edge_type,
                label=_edge_label(edge_type),
                weight=edge["weight"],
                properties={
                    "source_kind": "local_vector",
                    "source_detail": props.get("source_detail") or "local_vector.frontend_snapshot",
                    "source": props.get("source_detail") or "local_vector.frontend_snapshot",
                    "confidence": props.get("confidence"),
                    "reason": props.get("reason"),
                    "evidence": props.get("evidence"),
                    "model": props.get("model"),
                },
            )
            pair_keys.add(tuple(sorted((source, target))))
            if not existed_before and edge_key in builder.edges:
                added_count += 1
                edge_counter[edge_type] += 1
            if not model and props.get("model"):
                model = props.get("model")

        return {
            "enabled": True,
            "model": model,
            "available": bool(review_edges),
            "error": None,
            "candidate_pair_count": len(pair_keys),
            "reviewed_pair_count": len(pair_keys),
            "added_count": added_count,
            "edge_counts": dict(edge_counter),
            "seeded_from_frontend": True,
        }

    def _accumulate_candidates(self, *args, **kwargs) -> None:
        self._feature_engine.accumulate_candidates(*args, **kwargs)

    def _apply_rule_edges(self, builder: _GraphBuilder, requirement_features, candidate_pairs, **kwargs):
        return self._dependency_audit.apply_rule_edges(
            builder,
            requirement_features,
            candidate_pairs,
            **kwargs,
        )

    def _build_dependency_candidate(self, **kwargs):
        return self._dependency_audit.build_dependency_candidate(**kwargs)

    def _is_dependency_candidate_strong(self, evidence: List[str]) -> bool:
        return self._dependency_audit.is_dependency_candidate_strong(evidence)

    def _apply_dependency_candidates(self, builder: _GraphBuilder, dependency_candidates, **kwargs):
        return self._dependency_audit.apply_dependency_candidates(
            builder,
            dependency_candidates,
            **kwargs,
        )

    def _log_dependency_audit_failure(self, exc: Exception, **kwargs) -> None:
        self._dependency_audit.log_dependency_audit_failure(exc, **kwargs)

    def _select_dependency_candidates(self, dependency_candidates, **kwargs):
        return self._dependency_audit.select_dependency_candidates(
            dependency_candidates,
            **kwargs,
        )

    def _review_dependency_candidates_with_llm(self, dependency_candidates, **kwargs):
        return self._dependency_audit.review_dependency_candidates_with_llm(
            dependency_candidates,
            **kwargs,
        )

    def _parse_dependency_audit_response(self, response: Dict[str, Any], dependency_candidates):
        return self._dependency_audit.parse_dependency_audit_response(
            response,
            dependency_candidates,
        )

    def _fallback_dependency_decisions(self, dependency_candidates):
        return self._dependency_audit.fallback_dependency_decisions(dependency_candidates)

    def _apply_llm_relation_review(
        self,
        builder: _GraphBuilder,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        enabled: bool,
        model: str,
        inference_limit: int,
        review_concurrency: int = 3,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
        inferred_relation_types: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        relation_review = _RequirementGraphRelationReviewCoordinator(
            ai=self.ai,
            logger=logger,
            clean=self._clean,
            serialize_requirement_feature=self._serialize_requirement_feature,
            apply_llm_inference=self._apply_llm_inference,
            pair_candidate_id=self._pair_candidate_id,
            existing_pair_relations=self._existing_pair_relations,
            resolve_node_reference=self._resolve_node_reference,
            edge_label=_edge_label,
            normalize_edge_key=_normalize_edge_key,
            as_list=_as_list,
            compact_list=_compact_list,
            float_or_default=_float_or_default,
            inferred_relation_types=inferred_relation_types or _REQ_REQ_INFERRED_TYPES,
            symmetric_edge_types=_SYMMETRIC_EDGE_TYPES,
        )
        return relation_review.apply(
            builder,
            project_id=project_id,
            session_id=session_id,
            enabled=enabled,
            model=model,
            inference_limit=inference_limit,
            review_concurrency=review_concurrency,
            requirement_features=requirement_features,
            candidate_pairs=candidate_pairs,
        )

    @staticmethod
    def _normalize_relation_mode(
        relation_mode: Optional[str],
        *,
        infer_relations: bool,
    ) -> str:
        normalized = str(relation_mode or "").strip().lower()
        if normalized in {"none", "local", "llm"}:
            return normalized
        return "llm" if infer_relations else "none"

    def _prune_transitive_dependency_edges(self, builder: _GraphBuilder) -> int:
        return self._dependency_audit.prune_transitive_dependency_edges(builder)

    def _prune_weaker_similar_edges(self, builder: _GraphBuilder) -> None:
        self._dependency_audit.prune_weaker_similar_edges(builder)

    def _apply_l4_edges(self, builder: _GraphBuilder, session_id: Optional[str]) -> None:
        self._enricher.apply_l4_edges(builder, session_id)

    def _apply_trace_edges(self, builder: _GraphBuilder, session_id: Optional[str], text_index) -> None:
        return self._enricher.apply_trace_edges(builder, session_id, text_index)

    def _apply_conflict_edges(self, builder: _GraphBuilder, session_id: Optional[str], text_index) -> None:
        return self._enricher.apply_conflict_edges(builder, session_id, text_index)

    def _apply_classification(self, builder: _GraphBuilder, session_id: Optional[str], text_index):
        return self._enricher.apply_classification(builder, session_id, text_index)

    def _apply_stakeholders(
        self,
        builder: _GraphBuilder,
        project_id: Optional[str],
        project_requirements: Iterable[Dict[str, Any]],
    ) -> None:
        self._enricher.apply_stakeholders(builder, project_id, project_requirements)

    def _load_project_members(self, project_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
        return self._data_access.load_project_members(project_id)

    def _apply_llm_inference(self, builder: _GraphBuilder, **kwargs):
        return self._inference_engine.apply_llm_inference(builder, **kwargs)

    def _persist_relation_snapshot(
        self,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        relation_mode: Optional[str],
        graph: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        normalized_mode = self._clean(relation_mode)
        if normalized_mode not in {"local", "llm"}:
            return None
        save_snapshot = getattr(self.db, "save_requirement_graph_snapshot", None)
        if not callable(save_snapshot):
            return None
        try:
            return save_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode=normalized_mode,
                edges=graph.get("edges") or [],
            )
        except Exception as exc:
            logger.warning(
                "Requirement graph relation snapshot persistence failed "
                "(project=%s, session=%s, mode=%s): %s",
                project_id,
                session_id,
                normalized_mode,
                exc,
            )
            return {
                "saved": False,
                "error": str(exc),
            }

    def _serialize_requirement_feature(self, feature: Dict[str, Any]) -> Dict[str, Any]:
        return self._inference_engine.serialize_requirement_feature(feature)

    def _normalize_inferred_requirement_edge(self, raw_edge: Any, **kwargs):
        return self._inference_engine.normalize_inferred_requirement_edge(raw_edge, **kwargs)

    def _build_inference_scope(self, builder: _GraphBuilder, inference_limit: int):
        return self._inference_engine.build_inference_scope(builder, inference_limit)

    def _select_requirement_candidates(self, requirement_nodes, edges, budget: int):
        return self._inference_engine.select_requirement_candidates(
            requirement_nodes,
            edges,
            budget,
        )

    def _select_stakeholder_candidates(self, requirement_ids, stakeholder_nodes, edges, all_nodes, budget: int):
        return self._inference_engine.select_stakeholder_candidates(
            requirement_ids,
            stakeholder_nodes,
            edges,
            all_nodes,
            budget,
        )

    def _serialize_requirement_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        return self._inference_engine.serialize_requirement_node(node)

    def _serialize_stakeholder_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        return self._inference_engine.serialize_stakeholder_node(node)

    def _merge_inferred_stakeholders(self, builder: _GraphBuilder, raw_stakeholders, **kwargs):
        return self._inference_engine.merge_inferred_stakeholders(
            builder,
            raw_stakeholders,
            **kwargs,
        )

    def _normalize_inferred_stakeholder(self, raw_stakeholder: Any):
        return self._inference_engine.normalize_inferred_stakeholder(raw_stakeholder)

    def _build_node_alias_lookup(self, builder: _GraphBuilder, valid_node_ids: set[str]) -> Dict[str, str]:
        return self._inference_engine.build_node_alias_lookup(builder, valid_node_ids)

    def _normalize_inferred_edge(self, raw_edge: Any, valid_node_ids: set[str], alias_lookup=None):
        return self._inference_engine.normalize_inferred_edge(
            raw_edge,
            valid_node_ids,
            alias_lookup,
        )

    @staticmethod
    def _count_edges_by_source_kinds(edges: List[Dict[str, Any]], kinds: set[str]) -> Dict[str, Any]:
        counts = {kind: 0 for kind in kinds}
        total = 0
        for edge in edges:
            edge_kinds = set((edge.get("properties") or {}).get("source_kinds") or [])
            matched = edge_kinds & kinds
            if not matched:
                continue
            total += 1
            for kind in matched:
                counts[kind] += 1
        return {"total": total, "by_kind": counts}

    def _normalize_review_edges(
        self,
        review_edges: Optional[List[Dict[str, Any]]],
        *,
        requirement_features: Dict[str, Dict[str, Any]],
        relation_limit: int,
    ) -> List[Dict[str, Any]]:
        if not isinstance(review_edges, list):
            return []

        allowed_types = set(_REQ_REQ_INFERRED_TYPES) | {"SIMILAR_TO"}
        max_edges = max(12, min(240, int(relation_limit or 48) * 4))
        normalized_edges: List[Dict[str, Any]] = []
        seen_keys = set()

        for raw_edge in review_edges:
            if not isinstance(raw_edge, dict):
                continue

            source = self._clean(raw_edge.get("source"))
            target = self._clean(raw_edge.get("target"))
            edge_type = self._clean(raw_edge.get("type"))
            if (
                not source
                or not target
                or source == target
                or source not in requirement_features
                or target not in requirement_features
                or edge_type not in allowed_types
            ):
                continue

            props = raw_edge.get("properties") if isinstance(raw_edge.get("properties"), dict) else {}
            if self._clean(props.get("source_kind")) not in {None, "local_vector"}:
                continue

            edge_key = _normalize_edge_key(source, target, edge_type)
            if edge_key in seen_keys:
                continue
            seen_keys.add(edge_key)

            normalized_edges.append(
                {
                    "source": source,
                    "target": target,
                    "type": edge_type,
                    "weight": _float_or_default(
                        raw_edge.get("weight"),
                        _float_or_default(props.get("confidence"), 0.72),
                    ),
                    "properties": {
                        "source_kind": "local_vector",
                        "source_detail": self._clean(props.get("source_detail")) or "local_vector.frontend_snapshot",
                        "confidence": _float_or_default(props.get("confidence"), raw_edge.get("weight") or 0.72),
                        "reason": self._clean(props.get("reason")),
                        "evidence": _compact_list(_as_list(props.get("evidence"))),
                        "model": self._clean(props.get("model")),
                    },
                }
            )
            if len(normalized_edges) >= max_edges:
                break

        return normalized_edges

    def _build_candidate_pairs_from_review_edges(
        self,
        review_edges: List[Dict[str, Any]],
        *,
        requirement_features: Dict[str, Dict[str, Any]],
        relation_limit: int,
    ):
        pair_map: Dict[tuple[str, str], Dict[str, Any]] = {}
        per_requirement_counts: Counter[str] = Counter()

        for edge in review_edges:
            pair_key = tuple(sorted((edge["source"], edge["target"])))
            payload = pair_map.setdefault(
                pair_key,
                {
                    "score": 0,
                    "signals": [],
                },
            )
            payload["score"] = max(payload["score"], max(1, int(round(edge["weight"] * 10))))
            payload["signals"] = _compact_list(
                [
                    *payload["signals"],
                    f"seed_edge:{edge['type']}",
                    edge["properties"].get("source_detail"),
                    *edge["properties"].get("evidence", []),
                ]
            )

        candidate_pairs = [
            {
                "source": source,
                "target": target,
                "score": payload["score"],
                "signals": payload["signals"],
                "requester_count": 2,
            }
            for (source, target), payload in sorted(
                pair_map.items(),
                key=lambda item: (-item[1]["score"], item[0][0], item[0][1]),
            )
        ]

        for pair in candidate_pairs:
            per_requirement_counts[pair["source"]] += 1
            per_requirement_counts[pair["target"]] += 1

        return candidate_pairs, {
            "pair_count": len(candidate_pairs),
            "per_requirement_limit": max(6, min(120, int(relation_limit or 48))),
            "per_requirement_counts": dict(per_requirement_counts),
            "requirement_count": len(requirement_features),
            "max_term_document_frequency": 0,
            "edge_count": len(review_edges),
            "source": "frontend_local_review_edges",
        }

    @staticmethod
    def _existing_pair_relations(builder: _GraphBuilder, left_id: str, right_id: str):
        return _existing_pair_relations(builder, left_id, right_id)

    @staticmethod
    def _pair_candidate_id(source: Any, target: Any) -> str:
        from .graph_core import _pair_candidate_id

        return _pair_candidate_id(source, target)

    @staticmethod
    def _resolve_node_reference(value: Any, valid_node_ids: set[str], alias_lookup=None):
        return _resolve_node_reference(value, valid_node_ids, alias_lookup)

    @staticmethod
    def _clean(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
