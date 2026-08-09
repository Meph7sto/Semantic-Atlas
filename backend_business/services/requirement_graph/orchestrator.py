import asyncio
from collections import Counter, defaultdict
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
import uuid

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
from .relation_discovery import _RequirementGraphRelationDiscoveryCoordinator
from .relation_review import _RequirementGraphRelationReviewCoordinator

logger = logging.getLogger(__name__)

PCA_DEMO_PROJECT_ID = "demo-pca-infusion-pump-project"
PCA_DEMO_SESSION_ID = "demo-pca-infusion-pump-session"

PCA_DEMO_GRAPH_RELATIONS = [
    {
        "source": "PCA-L-04",
        "target": "PCA-L-05",
        "type": "DEPENDS_ON",
        "confidence": 0.94,
        "reason": "低液量预警和空仓停泵共享储液仓余量测量链路，阈值策略需要按同一测量误差模型验证。",
        "evidence": ["1 ml 预警阈值", "0.5 ml 空仓报警并停泵", "储液仓测量误差不超过 1 ml"],
    },
    {
        "source": "PCA-L-05",
        "target": "PCA-L-23",
        "type": "CONFLICTS_WITH",
        "confidence": 0.91,
        "reason": "空仓报警要求停泵，KVO 需求要求维持最低流量；两者在报警与泵速 Table 4 未确认前存在条件边界冲突。",
        "evidence": ["空仓报警并停泵", "输注期间维持 KVO 流量", "Table 4 缺失"],
    },
    {
        "source": "PCA-L-10",
        "target": "PCA-L-11",
        "type": "SIMILAR_TO",
        "confidence": 0.86,
        "reason": "基础输注流量范围与基础流量精度都约束正常基础输注输出，属于同一泵送性能验证簇。",
        "evidence": ["Fbasal min/max", "基础流量允许偏差"],
    },
    {
        "source": "PCA-L-12",
        "target": "PCA-L-13",
        "type": "SIMILAR_TO",
        "confidence": 0.84,
        "reason": "患者追加剂量的过量与不足预警使用相同 1 分钟判断窗口，应合并设计测试边界。",
        "evidence": ["患者追加剂量过量 1 分钟", "患者追加剂量不足 1 分钟"],
    },
    {
        "source": "PCA-L-46",
        "target": "PCA-L-47",
        "type": "SIMILAR_TO",
        "confidence": 0.82,
        "reason": "患者追加和医护追加的流量容差均需补充参数来源，适合在同一评审项中关闭。",
        "evidence": ["追加剂量流量容差待确认", "医护追加剂量流量容差待确认"],
    },
    {
        "source": "PCA-L-08",
        "target": "PCA-L-36",
        "type": "DEPENDS_ON",
        "confidence": 0.9,
        "reason": "电子防拆检测要求同时写入事件日志，日志保留策略直接影响防拆审计可追溯性。",
        "evidence": ["检测到防拆写入 Event Log", "事件日志至少保留 1000 小时"],
    },
    {
        "source": "PCA-L-08",
        "target": "PCA-L-53",
        "type": "DEPENDS_ON",
        "confidence": 0.88,
        "reason": "防拆属于故障/安全事件，故障日志容量和覆盖策略会影响防拆证据保存。",
        "evidence": ["tamper attempts in Fault Log", "故障日志至少 1000 小时"],
    },
    {
        "source": "PCA-L-20",
        "target": "PCA-L-50",
        "type": "DEPENDS_ON",
        "confidence": 0.87,
        "reason": "报警静音状态必须可见，控制面板展示逻辑依赖报警线程的静音策略和优先级判断。",
        "evidence": ["静音状态和到期时间需要显示", "高优先级报警静音范围待确认"],
    },
    {
        "source": "PCA-L-14",
        "target": "PCA-L-52",
        "type": "VALIDATES_WITH",
        "confidence": 0.83,
        "reason": "过热/过载报警名称与测温位置不一致，必须通过温升或负载异常测试确认触发条件。",
        "evidence": ["55 摄氏度测点待确认", "泵过载/过热命名不一致"],
    },
    {
        "source": "PCA-L-18",
        "target": "PCA-L-19",
        "type": "DEPENDS_ON",
        "confidence": 0.89,
        "reason": "医护追加剂量流量由剂量和持续时间计算得出，随后必须受药物库软/硬限制约束。",
        "evidence": ["square bolus 按持续时间均匀输注", "药物库软限制/硬限制"],
    },
    {
        "source": "PCA-L-19",
        "target": "PCA-L-22",
        "type": "IMPACTS",
        "confidence": 0.88,
        "reason": "硬限制拒绝处方会直接影响启动输注、医护追加和患者追加是否允许执行。",
        "evidence": ["超过硬限制必须拒绝", "累计剂量达到硬限制应停止追加并降至 KVO"],
    },
    {
        "source": "PCA-L-21",
        "target": "PCA-L-22",
        "type": "INCLUDES",
        "confidence": 0.81,
        "reason": "累计剂量限制是药物库边界检查在时间窗口上的扩展，属于剂量安全约束的一部分。",
        "evidence": ["时间窗口最大剂量", "最大剂量限制提示"],
    },
    {
        "source": "PCA-L-38",
        "target": "PCA-L-39",
        "type": "DEPENDS_ON",
        "confidence": 0.85,
        "reason": "市电与电池切换策略决定掉电时是否继续输注，电源故障检测会触发停泵或报警策略。",
        "evidence": ["battery backup", "mains power failure", "电源异常检测"],
    },
    {
        "source": "PCA-L-31",
        "target": "PCA-L-32",
        "type": "CONFLICTS_WITH",
        "confidence": 0.8,
        "reason": "基础过量报警和基础不足预警使用同一允许偏差但方向相反，测试设计需防止同一采样窗口误判。",
        "evidence": ["高于处方超过允许偏差", "低于处方超过允许偏差"],
    },
    {
        "source": "PCA-L-54",
        "target": "PCA-L-55",
        "type": "IMPACTS",
        "confidence": 0.84,
        "reason": "故障屏蔽成功与否决定报警线程是否继续显示故障以及是否写入独立故障灯相关状态。",
        "evidence": ["成功屏蔽故障是否仍报警待确认", "独立故障灯响应硬件故障"],
    },
    {
        "source": "PCA-L-36",
        "target": "PCA-L-53",
        "type": "SIMILAR_TO",
        "confidence": 0.86,
        "reason": "事件日志和故障日志都要求至少 1000 小时保留，覆盖策略应统一评审。",
        "evidence": ["事件日志 1000 小时", "故障日志 1000 小时"],
    },
]


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
        inference_model: str = "deepseek-v4-pro",
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

    async def stream_graph_events(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 900,
        inference_limit: int = 48,
        package_size: int = 6,
        review_concurrency: int = 3,
        model: str = "deepseek-v4-pro",
    ):
        run_id = uuid.uuid4().hex
        project_id = self._clean(project_id) or self._resolve_project_id_by_session(
            self._clean(session_id)
        )
        session_id = self._clean(session_id) or self._resolve_project_session(project_id)
        if self._is_pca_demo_scope(project_id=project_id, session_id=session_id):
            async for event in self._stream_pca_demo_graph_events(
                project_id=project_id,
                session_id=session_id,
                limit=limit,
                review_concurrency=review_concurrency,
                model=model,
                run_id=run_id,
            ):
                yield event
            return
        limit = max(50, min(2000, int(limit or 900)))
        inference_limit = max(6, min(80, int(inference_limit or 48)))
        package_size = max(1, min(24, int(package_size or 6)))
        review_concurrency = max(1, min(8, int(review_concurrency or 3)))
        model = self._clean(model) or "deepseek-v4-pro"

        builder = _GraphBuilder(limit=limit)
        relation_review_stats = {
            "package_count": 0,
            "reviewed_pair_count": 0,
            "completed_package_count": 0,
            "added_count": 0,
            "updated_count": 0,
            "deleted_count": 0,
            "rejected_count": 0,
            "fallback_used": False,
            "model": model,
            "requested_concurrency": review_concurrency,
            "applied_concurrency": 0,
            "package_size": package_size,
        }
        progress = {
            "completed_pairs": 0,
            "total_pairs": 0,
            "completed_packages": 0,
            "total_packages": 0,
        }
        candidate_edges_by_pair: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        try:
            (
                project_requirements,
                requirement_features,
                candidate_pairs,
                candidate_stats,
                local_embedding_status,
                trace_stats,
                conflict_stats,
                classification_stats,
            ) = self._prepare_stream_base(
                builder,
                project_id=project_id,
                session_id=session_id,
                limit=limit,
            )

            base_graph = self._build_stream_graph_payload(
                builder,
                project_id=project_id,
                session_id=session_id,
                project_requirements=project_requirements,
                trace_stats=trace_stats,
                conflict_stats=conflict_stats,
                classification_stats=classification_stats,
                candidate_stats=candidate_stats,
                local_vector_stats={
                    "enabled": False,
                    "model": local_embedding_status.get("model"),
                    "available": local_embedding_status.get("available", False),
                    "error": local_embedding_status.get("error"),
                    "candidate_pair_count": 0,
                    "reviewed_pair_count": 0,
                    "added_count": 0,
                    "edge_counts": {},
                },
                relation_review_stats=relation_review_stats,
                run_id=run_id,
            )
            yield "base_graph", {"run_id": run_id, "graph": base_graph}

            before_local_keys = set(builder.edges.keys())
            local_vector_stats = self._apply_local_vector_edges(
                builder,
                requirement_features,
                candidate_pairs,
                relation_limit=inference_limit,
                embedding_status=local_embedding_status,
            )
            candidate_edges = [
                dict(edge)
                for key, edge in builder.edges.items()
                if key not in before_local_keys
                and (edge.get("properties") or {}).get("source_kind") == "local_vector"
            ]
            for edge in candidate_edges:
                candidate_edges_by_pair[self._edge_pair_key(edge["source"], edge["target"])].append(edge)
            yield "candidate_edges", {
                "run_id": run_id,
                "edges": candidate_edges,
                "stats": local_vector_stats,
            }

            running_graph = self._build_stream_graph_payload(
                builder,
                project_id=project_id,
                session_id=session_id,
                project_requirements=project_requirements,
                trace_stats=trace_stats,
                conflict_stats=conflict_stats,
                classification_stats=classification_stats,
                candidate_stats=candidate_stats,
                local_vector_stats=local_vector_stats,
                relation_review_stats=relation_review_stats,
                run_id=run_id,
            )
            self._persist_relation_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode="llm",
                graph=running_graph,
                run_id=run_id,
                snapshot_status="running",
                progress_json=progress,
            )

            relation_review = self._make_relation_review_coordinator()
            packages = relation_review.build_review_packages(
                builder,
                requirement_features=requirement_features,
                candidate_pairs=candidate_pairs,
                inference_limit=inference_limit,
                package_size=package_size,
            )
            progress["total_packages"] = len(packages)
            progress["total_pairs"] = sum(len(package["candidate_pairs"]) for package in packages)
            relation_review_stats["package_count"] = len(packages)
            relation_review_stats["reviewed_pair_count"] = progress["total_pairs"]
            relation_review_stats["applied_concurrency"] = min(review_concurrency, len(packages)) if packages else 0
            yield "review_progress", dict(progress)

            async for package, result in relation_review.review_packages_as_completed(
                packages,
                model=model,
                review_concurrency=review_concurrency,
            ):
                if isinstance(result, Exception):
                    relation_review_stats["fallback_used"] = True
                    result = {"mutations": []}

                decided_pair_keys = set()
                for mutation in result.get("mutations") or []:
                    pair_key = self._edge_pair_key(
                        mutation["candidate"]["source"],
                        mutation["candidate"]["target"],
                    )
                    decided_pair_keys.add(pair_key)
                    self._remove_local_candidate_edges(builder, pair_key)
                    applied_action = relation_review._apply_mutation_to_builder(
                        builder,
                        mutation=mutation,
                        package_id=package["package_id"],
                        model=model,
                    )
                    if applied_action not in {"add", "update", "delete", "reject"}:
                        applied_action = "reject"
                    if applied_action == "add":
                        relation_review_stats["added_count"] += 1
                    elif applied_action == "update":
                        relation_review_stats["updated_count"] += 1
                    elif applied_action == "delete":
                        relation_review_stats["deleted_count"] += 1
                    elif applied_action == "reject":
                        relation_review_stats["rejected_count"] += 1
                    yield "relation_decision", self._build_relation_decision_event(
                        mutation=mutation,
                        action=applied_action,
                        package_id=package["package_id"],
                        model=model,
                        builder=builder,
                        run_id=run_id,
                    )

                for pair in package.get("candidate_pairs") or []:
                    pair_key = self._edge_pair_key(pair.get("source"), pair.get("target"))
                    if pair_key in decided_pair_keys:
                        continue
                    rejected_edges = self._remove_local_candidate_edges(builder, pair_key)
                    if not rejected_edges:
                        rejected_edges = [{
                            "source": pair.get("source"),
                            "target": pair.get("target"),
                            "type": "SIMILAR_TO",
                            "weight": 0,
                            "properties": {},
                        }]
                    for edge in rejected_edges:
                        relation_review_stats["rejected_count"] += 1
                        yield "relation_decision", {
                            "run_id": run_id,
                            "action": "reject",
                            "edge": edge,
                            "reason": "DeepSeek 未确认该候选关系",
                            "confidence": None,
                            "package_id": package["package_id"],
                        }

                progress["completed_pairs"] = min(
                    progress["total_pairs"],
                    progress["completed_pairs"] + len(package.get("candidate_pairs") or []),
                )
                progress["completed_packages"] += 1
                relation_review_stats["completed_package_count"] = progress["completed_packages"]
                yield "review_progress", dict(progress)

                running_graph = self._build_stream_graph_payload(
                    builder,
                    project_id=project_id,
                    session_id=session_id,
                    project_requirements=project_requirements,
                    trace_stats=trace_stats,
                    conflict_stats=conflict_stats,
                    classification_stats=classification_stats,
                    candidate_stats=candidate_stats,
                    local_vector_stats=local_vector_stats,
                    relation_review_stats=relation_review_stats,
                    run_id=run_id,
                )
                running_snapshot = self._persist_relation_snapshot(
                    project_id=project_id,
                    session_id=session_id,
                    relation_mode="llm",
                    graph=running_graph,
                    run_id=run_id,
                    snapshot_status="running",
                    progress_json=progress,
                )
                if running_snapshot:
                    yield "snapshot_saved", {
                        "run_id": run_id,
                        "snapshot_status": "running",
                        "snapshot": running_snapshot,
                    }
                await asyncio.sleep(0)

            self._prune_weaker_similar_edges(builder)
            final_graph = self._build_stream_graph_payload(
                builder,
                project_id=project_id,
                session_id=session_id,
                project_requirements=project_requirements,
                trace_stats=trace_stats,
                conflict_stats=conflict_stats,
                classification_stats=classification_stats,
                candidate_stats=candidate_stats,
                local_vector_stats=local_vector_stats,
                relation_review_stats=relation_review_stats,
                run_id=run_id,
            )
            final_graph["edges"] = [
                edge for edge in final_graph.get("edges") or []
                if (edge.get("properties") or {}).get("review_action") != "reject"
            ]
            final_snapshot = self._persist_relation_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode="llm",
                graph=final_graph,
                run_id=run_id,
                snapshot_status="final",
                progress_json=progress,
            )
            if final_snapshot:
                final_graph.setdefault("meta", {})["relation_snapshot"] = final_snapshot
                yield "snapshot_saved", {
                    "run_id": run_id,
                    "snapshot_status": "final",
                    "snapshot": final_snapshot,
                }
            yield "done", {
                "run_id": run_id,
                "stats": final_graph.get("stats") or {},
                "snapshot": final_snapshot,
            }
        except asyncio.CancelledError:
            interrupted_graph = self._safe_stream_graph_from_builder(builder)
            self._persist_relation_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode="llm",
                graph=interrupted_graph,
                run_id=run_id,
                snapshot_status="interrupted",
                progress_json=progress,
            )
            raise
        except Exception as exc:
            failed_graph = self._safe_stream_graph_from_builder(builder)
            failed_snapshot = self._persist_relation_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode="llm",
                graph=failed_graph,
                run_id=run_id,
                snapshot_status="failed",
                progress_json={**progress, "error": str(exc)},
            )
            yield "error", {
                "run_id": run_id,
                "message": str(exc),
                "snapshot": failed_snapshot,
            }

    async def stream_discover_relation_events(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 900,
        review_concurrency: int = 3,
        model: str = "deepseek-v4-pro",
    ):
        run_id = uuid.uuid4().hex
        project_id = self._clean(project_id) or self._resolve_project_id_by_session(
            self._clean(session_id)
        )
        session_id = self._clean(session_id) or self._resolve_project_session(project_id)
        if self._is_pca_demo_scope(project_id=project_id, session_id=session_id):
            async for event in self._stream_pca_demo_graph_events(
                project_id=project_id,
                session_id=session_id,
                limit=limit,
                review_concurrency=review_concurrency,
                model=model,
                run_id=run_id,
            ):
                yield event
            return
        limit = max(50, min(2000, int(limit or 900)))
        review_concurrency = max(1, min(8, int(review_concurrency or 3)))
        model = self._clean(model) or "deepseek-v4-pro"

        builder = _GraphBuilder(limit=limit)
        progress = {
            "completed_packages": 0,
            "total_packages": 0,
            "added_edges": 0,
            "skipped_packages": 0,
            "review_concurrency": review_concurrency,
        }
        relation_review_stats = {
            "package_count": 0,
            "completed_package_count": 0,
            "added_count": 0,
            "updated_count": 0,
            "deleted_count": 0,
            "rejected_count": 0,
            "skipped_package_count": 0,
            "fallback_used": False,
            "model": model,
            "requested_concurrency": review_concurrency,
            "applied_concurrency": 0,
            "discovery_mode": "top_l4_tool",
        }

        try:
            project_requirements = self._load_project_requirements(project_id, limit)
            top_requirements = self._load_l123_requirements(session_id, limit)
            l4_requirements = self._load_l4_requirements(session_id, limit)
            l4_links = self._load_l4_requirement_links(session_id)
            (
                trace_stats,
                conflict_stats,
                classification_stats,
                canonical_node_by_source_req_id,
            ) = self._build_discover_base_graph(
                builder,
                project_id=project_id,
                session_id=session_id,
                project_requirements=project_requirements,
                top_requirements=top_requirements,
                l4_requirements=l4_requirements,
                l4_links=l4_links,
            )
            base_graph = self._build_discover_graph_payload(
                builder,
                project_id=project_id,
                session_id=session_id,
                source_requirement_count=len(project_requirements),
                trace_stats=trace_stats,
                conflict_stats=conflict_stats,
                classification_stats=classification_stats,
                relation_review_stats=relation_review_stats,
                run_id=run_id,
            )
            yield "base_graph", {"run_id": run_id, "graph": base_graph}

            coordinator = self._make_relation_discovery_coordinator()
            links_by_top: Dict[str, List[str]] = defaultdict(list)
            for link in l4_links:
                top_req_id = self._clean(link.get("top_req_id"))
                low_req_id = self._clean(link.get("req_id"))
                if top_req_id and low_req_id:
                    links_by_top[top_req_id].append(low_req_id)
            l4_by_req_id = {
                self._clean(item.get("req_id")): item
                for item in l4_requirements
                if self._clean(item.get("req_id"))
            }

            packages = []
            progress["total_packages"] = len(top_requirements)
            yield "discover_progress", dict(progress)

            for index, top in enumerate(top_requirements, start=1):
                top_req_id = self._clean(top.get("req_id"))
                top_node_id = canonical_node_by_source_req_id.get(top_req_id or "")
                linked_low_ids = list(dict.fromkeys(links_by_top.get(top_req_id, [])))
                lows = [
                    l4_by_req_id[req_id]
                    for req_id in linked_low_ids
                    if req_id in l4_by_req_id
                    and canonical_node_by_source_req_id.get(req_id) in builder.nodes
                ]
                package_id = f"top-{index}:{top_req_id}"
                if not top_node_id or top_node_id not in builder.nodes:
                    progress["completed_packages"] += 1
                    progress["skipped_packages"] += 1
                    relation_review_stats["skipped_package_count"] = progress["skipped_packages"]
                    yield "package_skipped", {
                        "run_id": run_id,
                        "package_id": package_id,
                        "top_req_id": top_req_id,
                        "reason": "no_manage_requirement",
                        "l4_count": len(linked_low_ids),
                    }
                    yield "discover_progress", dict(progress)
                    continue
                if not lows:
                    progress["completed_packages"] += 1
                    progress["skipped_packages"] += 1
                    relation_review_stats["skipped_package_count"] = progress["skipped_packages"]
                    yield "package_skipped", {
                        "run_id": run_id,
                        "package_id": package_id,
                        "top_req_id": top_req_id,
                        "reason": "no_l4",
                        "l4_count": 0,
                    }
                    yield "discover_progress", dict(progress)
                    continue
                known_refines = [
                    {
                        "source": top_node_id,
                        "target": canonical_node_by_source_req_id.get(self._clean(low.get("req_id")) or ""),
                        "type": "REFINES",
                    }
                    for low in lows
                    if canonical_node_by_source_req_id.get(self._clean(low.get("req_id")) or "")
                ]
                top_node = builder.nodes[top_node_id]
                canonical_l4_requirements = []
                for low in lows:
                    low_req_id = self._clean(low.get("req_id")) or ""
                    low_node_id = canonical_node_by_source_req_id.get(low_req_id)
                    if not low_node_id or low_node_id not in builder.nodes:
                        continue
                    low_node = builder.nodes[low_node_id]
                    low_properties = low_node.get("properties") or {}
                    canonical_l4_requirements.append(
                        {
                            **low,
                            "req_id": low_properties.get("req_id") or low_req_id,
                            "text": low_node.get("label") or low_properties.get("description") or low.get("text"),
                            "node_id": low_node_id,
                        }
                    )
                package = coordinator.build_package(
                    package_id=package_id,
                    top_requirement={
                        **top,
                        "req_id": top_node["properties"].get("req_id") or top_req_id,
                        "level": top_node["properties"].get("source_level") or top.get("level"),
                        "text": top_node.get("label") or top.get("text"),
                        "node_id": top_node_id,
                    },
                    l4_requirements=canonical_l4_requirements,
                    known_refines=known_refines,
                )
                if len(lows) > 80:
                    reason = "too_many_l4"
                elif coordinator.estimate_prompt_chars(package) > 50000:
                    reason = "prompt_too_long"
                else:
                    reason = None
                if reason:
                    progress["completed_packages"] += 1
                    progress["skipped_packages"] += 1
                    relation_review_stats["skipped_package_count"] = progress["skipped_packages"]
                    yield "package_skipped", {
                        "run_id": run_id,
                        "package_id": package_id,
                        "top_req_id": top_req_id,
                        "reason": reason,
                        "l4_count": len(lows),
                        "prompt_chars": coordinator.estimate_prompt_chars(package),
                    }
                    yield "discover_progress", dict(progress)
                    continue
                packages.append(package)

            relation_review_stats["package_count"] = len(packages)
            relation_review_stats["applied_concurrency"] = min(review_concurrency, len(packages)) if packages else 0

            async for package, result in coordinator.review_packages_as_completed(
                packages,
                model=model,
                review_concurrency=review_concurrency,
            ):
                if isinstance(result, Exception):
                    relation_review_stats["fallback_used"] = True
                    result = {"relations": []}

                for relation in result.get("relations") or []:
                    edge = self._apply_discovered_relation(
                        builder,
                        relation=relation,
                        package_id=package["package_id"],
                        model=model,
                    )
                    if not edge:
                        continue
                    progress["added_edges"] += 1
                    relation_review_stats["added_count"] += 1
                    yield "relation_decision", {
                        "run_id": run_id,
                        "action": "add",
                        "edge": edge,
                        "reason": relation.get("reason"),
                        "confidence": relation.get("confidence"),
                        "package_id": package["package_id"],
                    }

                progress["completed_packages"] += 1
                relation_review_stats["completed_package_count"] = progress["completed_packages"]
                yield "discover_progress", dict(progress)
                await asyncio.sleep(0)

            self._prune_weaker_similar_edges(builder)
            final_graph = self._build_discover_graph_payload(
                builder,
                project_id=project_id,
                session_id=session_id,
                source_requirement_count=len(project_requirements),
                trace_stats=trace_stats,
                conflict_stats=conflict_stats,
                classification_stats=classification_stats,
                relation_review_stats=relation_review_stats,
                run_id=run_id,
            )
            final_snapshot = self._persist_relation_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode="llm",
                graph=final_graph,
                run_id=run_id,
                snapshot_status="final",
                progress_json=progress,
            )
            if final_snapshot:
                final_graph.setdefault("meta", {})["relation_snapshot"] = final_snapshot
                yield "snapshot_saved", {
                    "run_id": run_id,
                    "snapshot_status": "final",
                    "snapshot": final_snapshot,
                }
            yield "done", {
                "run_id": run_id,
                "stats": final_graph.get("stats") or {},
                "snapshot": final_snapshot,
            }
        except asyncio.CancelledError:
            interrupted_graph = self._safe_stream_graph_from_builder(builder)
            self._persist_relation_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode="llm",
                graph=interrupted_graph,
                run_id=run_id,
                snapshot_status="interrupted",
                progress_json=progress,
            )
            raise
        except Exception as exc:
            failed_graph = self._safe_stream_graph_from_builder(builder)
            failed_snapshot = self._persist_relation_snapshot(
                project_id=project_id,
                session_id=session_id,
                relation_mode="llm",
                graph=failed_graph,
                run_id=run_id,
                snapshot_status="failed",
                progress_json={**progress, "error": str(exc)},
            )
            yield "error", {
                "run_id": run_id,
                "message": str(exc),
                "snapshot": failed_snapshot,
            }

    def _is_pca_demo_scope(
        self,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
    ) -> bool:
        return project_id == PCA_DEMO_PROJECT_ID or session_id == PCA_DEMO_SESSION_ID

    async def _stream_pca_demo_graph_events(
        self,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        limit: int,
        review_concurrency: int,
        model: str,
        run_id: str,
    ):
        limit = max(50, min(2000, int(limit or 900)))
        review_concurrency = max(1, min(8, int(review_concurrency or 3)))
        model = self._clean(model) or "deepseek-v4-pro"

        builder = _GraphBuilder(limit=limit)
        (
            project_requirements,
            _requirement_features,
            _candidate_pairs,
            candidate_stats,
            local_embedding_status,
            trace_stats,
            conflict_stats,
            classification_stats,
        ) = self._prepare_stream_base(
            builder,
            project_id=project_id,
            session_id=session_id,
            limit=limit,
            include_candidate_recall=False,
        )
        self._apply_low_level_link_edges(builder, session_id)

        relation_review_stats = self._pca_demo_relation_review_stats(
            model=model,
            review_concurrency=review_concurrency,
            added_count=0,
        )
        base_graph = self._build_stream_graph_payload(
            builder,
            project_id=project_id,
            session_id=session_id,
            project_requirements=project_requirements,
            trace_stats=trace_stats,
            conflict_stats=conflict_stats,
            classification_stats=classification_stats,
            candidate_stats=candidate_stats,
            local_vector_stats={
                "enabled": False,
                "model": local_embedding_status.get("model"),
                "available": local_embedding_status.get("available", False),
                "error": local_embedding_status.get("error"),
                "candidate_pair_count": 0,
                "reviewed_pair_count": 0,
                "added_count": 0,
            },
            relation_review_stats=relation_review_stats,
            run_id=run_id,
        )
        yield "base_graph", {"run_id": run_id, "graph": base_graph}
        await asyncio.sleep(0)

        total_edges = len(PCA_DEMO_GRAPH_RELATIONS)
        for index, relation in enumerate(PCA_DEMO_GRAPH_RELATIONS, start=1):
            edge = self._add_pca_demo_relation_edge(
                builder,
                relation,
                model=model,
                package_id=f"pca-demo-package-{((index - 1) // 4) + 1:02d}",
            )
            if not edge:
                continue
            yield "review_progress", {
                "run_id": run_id,
                "completed_pairs": index,
                "total_pairs": total_edges,
                "completed_packages": ((index - 1) // 4) + 1,
                "total_packages": (total_edges + 3) // 4,
                "review_concurrency": review_concurrency,
            }
            yield "relation_decision", {
                "run_id": run_id,
                "action": "add",
                "edge": edge,
                "reason": relation["reason"],
                "confidence": relation["confidence"],
                "package_id": (edge.get("properties") or {}).get("review_package_id"),
            }
            await asyncio.sleep(0)

        relation_review_stats = self._pca_demo_relation_review_stats(
            model=model,
            review_concurrency=review_concurrency,
            added_count=total_edges,
        )
        final_graph = self._build_stream_graph_payload(
            builder,
            project_id=project_id,
            session_id=session_id,
            project_requirements=project_requirements,
            trace_stats=trace_stats,
            conflict_stats=conflict_stats,
            classification_stats=classification_stats,
            candidate_stats=candidate_stats,
            local_vector_stats={
                "enabled": False,
                "model": local_embedding_status.get("model"),
                "available": local_embedding_status.get("available", False),
                "error": local_embedding_status.get("error"),
                "candidate_pair_count": 0,
                "reviewed_pair_count": 0,
                "added_count": 0,
            },
            relation_review_stats=relation_review_stats,
            run_id=run_id,
        )
        final_snapshot = self._persist_relation_snapshot(
            project_id=project_id,
            session_id=session_id,
            relation_mode="llm",
            graph=final_graph,
            run_id=run_id,
            snapshot_status="final",
            progress_json={
                "completed_pairs": total_edges,
                "total_pairs": total_edges,
                "completed_packages": (total_edges + 3) // 4,
                "total_packages": (total_edges + 3) // 4,
                "demo": "pca_requirement_graph",
            },
        )
        if final_snapshot:
            final_graph.setdefault("meta", {})["relation_snapshot"] = final_snapshot
            yield "snapshot_saved", {
                "run_id": run_id,
                "snapshot_status": "final",
                "snapshot": final_snapshot,
            }
        yield "done", {
            "run_id": run_id,
            "stats": final_graph.get("stats") or {},
            "snapshot": final_snapshot,
        }

    def _add_pca_demo_relation_edge(
        self,
        builder: _GraphBuilder,
        relation: Dict[str, Any],
        *,
        model: str,
        package_id: str,
    ) -> Optional[Dict[str, Any]]:
        source = _req_node_id(relation.get("source"))
        target = _req_node_id(relation.get("target"))
        if source not in builder.nodes or target not in builder.nodes:
            return None
        edge_type = str(relation.get("type") or "").strip()
        confidence = _float_or_default(relation.get("confidence"), 0.82)
        builder.add_edge(
            source,
            target,
            edge_type,
            label=_edge_label(edge_type),
            weight=confidence,
            properties={
                "source_kind": "llm",
                "source_detail": "pca_demo_graph_design",
                "source": "pca_demo_graph_design",
                "confidence": confidence,
                "reason": relation.get("reason"),
                "evidence": _compact_list(_as_list(relation.get("evidence")))[:8],
                "model": model,
                "review_action": "add",
                "review_package_id": package_id,
            },
        )
        return builder.edges.get(_normalize_edge_key(source, target, edge_type))

    def _apply_low_level_link_edges(
        self,
        builder: _GraphBuilder,
        session_id: Optional[str],
    ) -> None:
        if not session_id:
            return
        load_pairs = getattr(self.db, "get_requirement_pairs_for_trace", None)
        if not callable(load_pairs):
            return
        try:
            pairs = load_pairs(session_id)
        except Exception as exc:
            logger.warning(
                "Requirement graph low-level link loading failed (session=%s): %s",
                session_id,
                exc,
            )
            return
        for pair in pairs or []:
            source_req_id = pair.get("high_req_id") or pair.get("top_req_id")
            target_req_id = pair.get("low_req_id") or pair.get("req_id")
            source = _req_node_id(source_req_id)
            target = _req_node_id(target_req_id)
            if source not in builder.nodes or target not in builder.nodes:
                continue
            builder.add_edge(
                source,
                target,
                "REFINES",
                label=_edge_label("REFINES"),
                weight=0.99,
                properties={
                    "source_kind": "structural",
                    "source_detail": "low_level_requirement_links",
                    "source": "low_level_requirement_links",
                    "confidence": 0.99,
                    "reason": "来自顶层需求与底层需求追溯链接表",
                    "evidence": [f"{source_req_id} -> {target_req_id}"],
                },
            )

    @staticmethod
    def _pca_demo_relation_review_stats(
        *,
        model: str,
        review_concurrency: int,
        added_count: int,
    ) -> Dict[str, Any]:
        total_edges = len(PCA_DEMO_GRAPH_RELATIONS)
        return {
            "package_count": (total_edges + 3) // 4,
            "reviewed_pair_count": added_count,
            "completed_package_count": (added_count + 3) // 4 if added_count else 0,
            "completed_packages": (added_count + 3) // 4 if added_count else 0,
            "total_packages": (total_edges + 3) // 4,
            "added_count": added_count,
            "updated_count": 0,
            "deleted_count": 0,
            "rejected_count": 0,
            "fallback_used": False,
            "model": model,
            "requested_concurrency": review_concurrency,
            "applied_concurrency": review_concurrency,
            "package_size": 4,
            "demo": "pca_requirement_graph",
        }

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

    def get_latest_snapshot_graph_any_mode(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 600,
    ) -> Optional[Dict[str, Any]]:
        preferred_modes = ("llm", "local")
        latest_snapshot_graph = None
        latest_snapshot_created_at = ""
        latest_snapshot_id = ""
        for mode in preferred_modes:
            graph = self.get_latest_snapshot_graph(
                project_id=project_id,
                session_id=session_id,
                relation_mode=mode,
                limit=limit,
            )
            if not graph:
                continue
            snapshot_meta = ((graph.get("meta") or {}).get("relation_snapshot") or {})
            created_at = str(snapshot_meta.get("created_at") or "")
            snapshot_id = str(snapshot_meta.get("snapshot_id") or "")
            if (created_at, snapshot_id) >= (latest_snapshot_created_at, latest_snapshot_id):
                latest_snapshot_graph = graph
                latest_snapshot_created_at = created_at
                latest_snapshot_id = snapshot_id
        return latest_snapshot_graph

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

    def delete_relation_snapshots(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        relation_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        delete_relations = getattr(self.db, "delete_requirement_graph_relations", None)
        if not callable(delete_relations):
            raise ValueError("当前数据库服务不支持需求图谱关系删除")
        return delete_relations(
            project_id=self._clean(project_id),
            session_id=self._clean(session_id),
            relation_mode=self._clean(relation_mode),
        )

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
        canonical_node_by_requirement_ref: Dict[str, str] = {}

        for req in project_requirements:
            req_id = self._clean(req.get("req_id"))
            if not req_id:
                continue
            normalized_level = _normalize_source_level(
                req.get("source_level"),
                req.get("requirement_type"),
            )
            node_id = _req_node_id(req_id)
            builder.add_node(
                node_id,
                kind="requirement",
                label=req.get("title"),
                group=normalized_level,
                properties={
                    "req_id": req_id,
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
            canonical_node_by_requirement_ref[req_id] = node_id
            canonical_node_by_requirement_ref[node_id] = node_id
            source_req_id = self._clean(req.get("source_req_id"))
            if source_req_id:
                canonical_node_by_requirement_ref[source_req_id] = node_id
                canonical_node_by_requirement_ref[_req_node_id(source_req_id)] = node_id

        snapshot_edges = snapshot.get("edges") or []

        def resolve_snapshot_node(node_id: Any, req_id: Any) -> Optional[str]:
            raw_node_id = self._clean(node_id)
            raw_req_id = self._clean(req_id)
            candidates = [
                raw_node_id,
                raw_req_id,
                raw_node_id.removeprefix("req:") if raw_node_id else "",
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                canonical = canonical_node_by_requirement_ref.get(candidate)
                if canonical in builder.nodes:
                    return canonical
            return None

        for edge in snapshot_edges:
            edge_type = str(edge.get("relation_type") or "").strip()
            source = resolve_snapshot_node(edge.get("source_node_id"), edge.get("source_req_id"))
            target = resolve_snapshot_node(edge.get("target_node_id"), edge.get("target_req_id"))
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
                "run_id": snapshot.get("run_id"),
                "snapshot_status": snapshot.get("snapshot_status") or "final",
                "relation_mode": snapshot.get("relation_mode"),
                "edge_count": snapshot.get("edge_count", len(graph["edges"])),
                "created_at": snapshot.get("created_at"),
                "invalidated_at": snapshot.get("invalidated_at"),
                "is_active": snapshot.get("is_active"),
                "progress_json": snapshot.get("progress_json"),
            },
        }
        graph["legend"]["levels"] = _LEVEL_ORDER
        return graph

    def _load_l123_requirements(self, session_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._data_access.load_l123_requirements(session_id, limit)

    def _load_l4_requirements(self, session_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._data_access.load_l4_requirements(session_id, limit)

    def _load_l4_requirement_links(self, session_id: Optional[str]) -> List[Dict[str, Any]]:
        return self._data_access.load_l4_requirement_links(session_id)

    def _build_discover_base_graph(
        self,
        builder: _GraphBuilder,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        project_requirements: List[Dict[str, Any]],
        top_requirements: List[Dict[str, Any]],
        l4_requirements: List[Dict[str, Any]],
        l4_links: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, str]]:
        text_index: Dict[str, List[str]] = defaultdict(list)
        canonical_node_by_source_req_id: Dict[str, str] = {}

        for req in project_requirements:
            req_id = self._clean(req.get("req_id"))
            if not req_id:
                continue
            node_id = _req_node_id(req_id)
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
                    "req_id": req_id,
                    "project_id": req.get("project_id") or project_id,
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
            if req_id:
                canonical_node_by_source_req_id[req_id] = node_id
            source_req_id = self._clean(req.get("source_req_id"))
            if source_req_id:
                canonical_node_by_source_req_id[source_req_id] = node_id
            _index_text(
                text_index,
                node_id,
                req_id,
                source_req_id,
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

        self._apply_project_edges(builder, project_requirements)

        source_top_ids_by_l4: Dict[str, List[str]] = defaultdict(list)
        for link in l4_links:
            req_id = self._clean(link.get("req_id"))
            top_req_id = self._clean(link.get("top_req_id"))
            if req_id and top_req_id:
                source_top_ids_by_l4[req_id].append(top_req_id)

        for req in top_requirements:
            req_id = self._clean(req.get("req_id"))
            node_id = canonical_node_by_source_req_id.get(req_id or "")
            if not node_id:
                continue
            _index_text(text_index, node_id, req_id, req.get("text"))

        for req in l4_requirements:
            req_id = self._clean(req.get("req_id"))
            node_id = canonical_node_by_source_req_id.get(req_id or "")
            if not node_id:
                continue
            _index_text(text_index, node_id, req_id, req.get("text"), req.get("source_top_text"))

        for link in l4_links:
            top_req_id = self._clean(link.get("top_req_id"))
            low_req_id = self._clean(link.get("req_id"))
            source = canonical_node_by_source_req_id.get(top_req_id or "")
            target = canonical_node_by_source_req_id.get(low_req_id or "")
            if source not in builder.nodes or target not in builder.nodes:
                continue
            builder.add_edge(
                source,
                target,
                "REFINES",
                label=_edge_label("REFINES"),
                weight=0.88,
                properties={
                    "source_kind": "structural",
                    "source_detail": "low_level_requirement_links",
                    "source": "low_level_requirement_links",
                    "confidence": 0.88,
                },
            )
        trace_stats = self._apply_trace_edges(builder, session_id, text_index)
        conflict_stats = self._apply_conflict_edges(builder, session_id, text_index)
        classification_stats = self._apply_classification(builder, session_id, text_index)
        return trace_stats, conflict_stats, classification_stats, canonical_node_by_source_req_id

    def _build_discover_graph_payload(
        self,
        builder: _GraphBuilder,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        source_requirement_count: int,
        trace_stats: Dict[str, Any],
        conflict_stats: Dict[str, Any],
        classification_stats: Dict[str, Any],
        relation_review_stats: Dict[str, Any],
        run_id: str,
    ) -> Dict[str, Any]:
        graph = builder.to_graph()
        analysis_edge_counts = self._count_edges_by_source_kinds(
            graph["edges"],
            {"trace_analysis", "conflict_analysis", "classification_analysis"},
        )
        supplemental_edge_counts = self._count_edges_by_source_kinds(
            graph["edges"],
            {"llm", "rule_extra", "local_vector"},
        )
        graph["stats"]["strong_edge_count"] = graph["stats"]["structural_edge_count"] + analysis_edge_counts["total"]
        graph["stats"]["analysis_edge_count"] = analysis_edge_counts["total"]
        graph["stats"]["supplemental_edge_count"] = supplemental_edge_counts["total"]
        graph["stats"]["inferred_edge_count"] = relation_review_stats.get("added_count", 0)
        graph["stats"]["edge_source_counts"] = {
            **graph["stats"].get("edge_source_counts", {}),
            **analysis_edge_counts["by_kind"],
            **supplemental_edge_counts["by_kind"],
        }
        graph["stats"]["source_requirement_count"] = source_requirement_count
        graph["stats"]["local_vector"] = {
            "enabled": False,
            "candidate_pair_count": 0,
            "reviewed_pair_count": 0,
            "added_count": 0,
        }
        graph["stats"]["relation_review"] = relation_review_stats
        graph["stats"]["review_concurrency"] = relation_review_stats.get("requested_concurrency", 0)
        graph["stats"]["classification_label_distribution"] = classification_stats.get("label_distribution", {})
        graph["stats"]["classification_matched_count"] = classification_stats.get("matched_count", 0)
        graph["stats"]["trace_edge_count"] = trace_stats.get("edge_count", 0)
        graph["stats"]["conflict_edge_count"] = conflict_stats.get("edge_count", 0)
        graph["stats"]["classification_edge_count"] = classification_stats.get("edge_count", 0)
        graph["meta"] = {
            "project_id": project_id,
            "session_id": session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "relation_mode": "llm",
            "discovery_mode": "top_l4_tool",
            "review_concurrency": relation_review_stats.get("requested_concurrency", 0),
            "local_vector": graph["stats"]["local_vector"],
            "relation_review": relation_review_stats,
            "analysis_records": {
                "trace_record_id": trace_stats.get("record_id"),
                "conflict_batch_id": conflict_stats.get("batch_id"),
                "classification_record_id": classification_stats.get("record_id"),
            },
        }
        graph["legend"]["levels"] = _LEVEL_ORDER
        return graph

    def _make_relation_discovery_coordinator(self) -> _RequirementGraphRelationDiscoveryCoordinator:
        return _RequirementGraphRelationDiscoveryCoordinator(
            ai=self.ai,
            logger=logger,
            clean=self._clean,
            edge_label=_edge_label,
            normalize_edge_key=_normalize_edge_key,
            resolve_node_reference=self._resolve_node_reference,
            as_list=_as_list,
            compact_list=_compact_list,
            float_or_default=_float_or_default,
            allowed_relation_types=set(_REQ_REQ_INFERRED_TYPES) | {"SIMILAR_TO"},
            symmetric_edge_types=_SYMMETRIC_EDGE_TYPES,
        )

    def _apply_discovered_relation(
        self,
        builder: _GraphBuilder,
        *,
        relation: Dict[str, Any],
        package_id: str,
        model: str,
    ) -> Optional[Dict[str, Any]]:
        source = relation.get("source")
        target = relation.get("target")
        edge_type = relation.get("type")
        if not source or not target or source == target or edge_type == "REFINES":
            return None
        edge_key = _normalize_edge_key(source, target, edge_type)
        existing = builder.edges.get(edge_key)
        incoming_confidence = _float_or_default(relation.get("confidence"), 0.65)
        incoming_evidence = _compact_list(_as_list(relation.get("evidence")))[:8]
        if existing:
            props = existing.get("properties") or {}
            if props.get("source_kind") == "structural" or existing.get("type") == "REFINES":
                return None
            current_quality = (
                _float_or_default(props.get("confidence"), existing.get("weight") or 0),
                len(props.get("evidence") or []),
            )
            incoming_quality = (incoming_confidence, len(incoming_evidence))
            if incoming_quality <= current_quality:
                return None
            builder.remove_edge(source, target, edge_type)
        builder.add_edge(
            source,
            target,
            edge_type,
            label=_edge_label(edge_type),
            weight=incoming_confidence,
            properties={
                "source_kind": "llm",
                "source_detail": "llm_discovery_tool",
                "source": "llm_discovery_tool",
                "confidence": incoming_confidence,
                "reason": self._clean(relation.get("reason")),
                "evidence": incoming_evidence,
                "model": model,
                "review_action": "add",
                "review_package_id": package_id,
            },
        )
        return builder.edges.get(edge_key)

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
        relation_review = self._make_relation_review_coordinator(
            inferred_relation_types=inferred_relation_types,
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

    def _make_relation_review_coordinator(
        self,
        *,
        inferred_relation_types: Optional[set[str]] = None,
    ) -> _RequirementGraphRelationReviewCoordinator:
        return _RequirementGraphRelationReviewCoordinator(
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

    def _prepare_stream_base(
        self,
        builder: _GraphBuilder,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        limit: int,
        include_candidate_recall: bool = True,
    ):
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

        if include_candidate_recall:
            self._attach_semantic_embeddings(requirement_features)
            local_embedding_status = self._feature_engine.get_local_embedding_status(
                requirement_features
            )
            candidate_pairs, candidate_stats = self._collect_candidate_pairs(requirement_features)
        else:
            local_embedding_status = {
                "available": False,
                "model": None,
                "error": None,
                "disabled": True,
                "reason": "pca_demo_static_graph",
            }
            candidate_pairs = []
            candidate_stats = {
                "pair_count": 0,
                "per_requirement_limit": 0,
                "per_requirement_counts": {},
                "requirement_count": len(requirement_features),
                "max_term_document_frequency": 0,
                "source": "pca_demo_static_graph",
            }
        self._apply_project_edges(builder, project_requirements)
        trace_stats = self._apply_trace_edges(builder, session_id, text_index)
        conflict_stats = self._apply_conflict_edges(builder, session_id, text_index)
        classification_stats = self._apply_classification(builder, session_id, text_index)
        return (
            project_requirements,
            requirement_features,
            candidate_pairs,
            candidate_stats,
            local_embedding_status,
            trace_stats,
            conflict_stats,
            classification_stats,
        )

    def _build_stream_graph_payload(
        self,
        builder: _GraphBuilder,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        project_requirements: List[Dict[str, Any]],
        trace_stats: Dict[str, Any],
        conflict_stats: Dict[str, Any],
        classification_stats: Dict[str, Any],
        candidate_stats: Dict[str, Any],
        local_vector_stats: Dict[str, Any],
        relation_review_stats: Dict[str, Any],
        run_id: str,
    ) -> Dict[str, Any]:
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
            relation_review_stats.get("added_count", 0) + relation_review_stats.get("updated_count", 0)
        )
        graph["stats"]["analysis_edge_count"] = analysis_edge_counts["total"]
        graph["stats"]["supplemental_edge_count"] = supplemental_edge_counts["total"]
        graph["stats"]["edge_source_counts"] = {
            **graph["stats"].get("edge_source_counts", {}),
            **analysis_edge_counts["by_kind"],
            **supplemental_edge_counts["by_kind"],
        }
        graph["stats"]["candidate_pair_count"] = candidate_stats.get("pair_count", 0)
        graph["stats"]["candidate_pairs_per_requirement_limit"] = candidate_stats.get("per_requirement_limit", 0)
        graph["stats"]["candidate_requirement_count"] = candidate_stats.get("requirement_count", 0)
        graph["stats"]["source_requirement_count"] = len(project_requirements)
        graph["stats"]["local_vector"] = local_vector_stats
        graph["stats"]["relation_review"] = relation_review_stats
        graph["stats"]["review_concurrency"] = relation_review_stats.get("requested_concurrency", 0)
        graph["stats"]["classification_label_distribution"] = classification_stats.get("label_distribution", {})
        graph["stats"]["classification_matched_count"] = classification_stats.get("matched_count", 0)
        graph["stats"]["trace_edge_count"] = trace_stats.get("edge_count", 0)
        graph["stats"]["conflict_edge_count"] = conflict_stats.get("edge_count", 0)
        graph["stats"]["classification_edge_count"] = classification_stats.get("edge_count", 0)
        graph["meta"] = {
            "project_id": project_id,
            "session_id": session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "relation_mode": "llm",
            "review_concurrency": relation_review_stats.get("requested_concurrency", 0),
            "candidate_recall": candidate_stats,
            "local_vector": local_vector_stats,
            "relation_review": relation_review_stats,
        }
        graph["legend"]["levels"] = _LEVEL_ORDER
        return graph

    def _safe_stream_graph_from_builder(self, builder: _GraphBuilder) -> Dict[str, Any]:
        try:
            return builder.to_graph()
        except Exception:
            return {"nodes": [], "edges": [], "stats": {}, "legend": {}}

    @staticmethod
    def _edge_pair_key(source: Any, target: Any) -> str:
        left, right = sorted((str(source or "").strip(), str(target or "").strip()))
        return f"{left}|{right}"

    def _remove_local_candidate_edges(self, builder: _GraphBuilder, pair_key: str) -> List[Dict[str, Any]]:
        removed = []
        for key, edge in list(builder.edges.items()):
            if self._edge_pair_key(edge.get("source"), edge.get("target")) != pair_key:
                continue
            if (edge.get("properties") or {}).get("source_kind") != "local_vector":
                continue
            removed.append(dict(edge))
            builder.edges.pop(key, None)
        return removed

    def _build_relation_decision_event(
        self,
        *,
        mutation: Dict[str, Any],
        action: str,
        package_id: str,
        model: str,
        builder: _GraphBuilder,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        edge_ref = mutation.get("replacement_edge") if action in {"add", "update"} else mutation.get("target_edge")
        edge = None
        if edge_ref:
            edge = builder.edges.get(
                _normalize_edge_key(edge_ref.get("source"), edge_ref.get("target"), edge_ref.get("type"))
            )
        if not edge:
            edge = {
                "source": edge_ref.get("source") if edge_ref else None,
                "target": edge_ref.get("target") if edge_ref else None,
                "type": edge_ref.get("type") if edge_ref else None,
                "weight": mutation.get("confidence"),
                "properties": {
                    "source_kind": "llm",
                    "source_detail": "llm_tool_review",
                    "confidence": mutation.get("confidence"),
                    "reason": mutation.get("reason"),
                    "evidence": mutation.get("evidence"),
                    "model": model,
                    "review_action": action,
                    "review_package_id": package_id,
                },
            }
        return {
            "run_id": run_id,
            "action": action,
            "edge": edge,
            "reason": mutation.get("reason"),
            "confidence": mutation.get("confidence"),
            "package_id": package_id,
        }

    def _persist_relation_snapshot(
        self,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        relation_mode: Optional[str],
        graph: Dict[str, Any],
        run_id: Optional[str] = None,
        snapshot_status: str = "final",
        progress_json: Optional[Dict[str, Any]] = None,
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
                run_id=run_id,
                snapshot_status=snapshot_status,
                progress_json=progress_json,
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
