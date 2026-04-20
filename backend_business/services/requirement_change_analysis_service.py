"""单需求变更影响分析服务。"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend_business.services.requirement_graph_service import _req_node_id
from backend_business.services.requirements_manage_service import (
    RequirementsManageService,
    normalize_priority,
    normalize_requirement_status,
)


_ALLOWED_CHANGE_FIELDS = ("title", "description", "tags", "priority", "status")
_SEMANTIC_CHANGE_FIELDS = {"title", "description", "tags"}
_MANAGEMENT_CHANGE_FIELDS = {"priority", "status"}
_MAIN_RELATION_TYPES = {"REFINES", "DEPENDS_ON", "CONFLICTS_WITH", "VALIDATES_WITH"}
_RISK_LEVEL_SCORE = {"high": 3, "medium": 2, "low": 1}
_RELATION_PRIORITY = {"DEPENDS_ON": 4, "CONFLICTS_WITH": 3, "REFINES": 2, "VALIDATES_WITH": 1}


class RequirementChangeAnalysisNotFoundError(ValueError):
    """分析对象不存在。"""


@dataclass
class _PropagationCandidate:
    requirement_id: str
    title: str
    source_level: str
    impact_level: str
    min_distance: int
    path: List[Dict[str, Any]]
    reason: str
    trigger_relations: List[str]


class RequirementChangeAnalysisService:
    """基于现有需求图谱执行单需求变更影响分析。"""

    def __init__(
        self,
        manage_service: RequirementsManageService,
        graph_service: Any,
    ) -> None:
        self.manage_service = manage_service
        self.graph_service = graph_service

    def analyze_requirement_change(
        self,
        *,
        project_id: str,
        requirement_id: str,
        changes: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized_project_id = str(project_id or "").strip()
        normalized_requirement_id = str(requirement_id or "").strip()
        if not normalized_project_id:
            raise ValueError("project_id 不能为空")
        if not normalized_requirement_id:
            raise ValueError("requirement_id 不能为空")

        requirement = self.manage_service.get_requirement(normalized_requirement_id)
        if not requirement or requirement.get("deleted"):
            raise RequirementChangeAnalysisNotFoundError("需求不存在")
        if requirement.get("project_id") != normalized_project_id:
            raise ValueError("需求不属于当前项目")

        before = self._build_snapshot(requirement)
        normalized_changes = self._normalize_changes(changes or {})
        after = {**before, **normalized_changes}
        changed_fields = [
            field
            for field in _ALLOWED_CHANGE_FIELDS
            if self._field_changed(before.get(field), after.get(field))
        ]
        if not changed_fields:
            return self._build_empty_result(
                requirement=requirement,
                before=before,
                after=before,
                analysis_status="no_effective_change",
                message="无有效变更",
            )

        graph = self.graph_service.build_graph(
            project_id=normalized_project_id,
            infer_relations=False,
            limit=2000,
        )
        nodes_by_node_id, nodes_by_requirement_id = self._index_nodes(graph.get("nodes") or [])
        source_node = nodes_by_requirement_id.get(normalized_requirement_id)
        if not source_node:
            raise RequirementChangeAnalysisNotFoundError("图谱中未找到对应需求")

        semantic_change = bool(_SEMANTIC_CHANGE_FIELDS.intersection(changed_fields))
        management_only = (
            bool(_MANAGEMENT_CHANGE_FIELDS.intersection(changed_fields))
            and not semantic_change
        )
        propagation_depth = 1 if management_only else 2

        impacted_map = self._collect_impacts(
            source_node_id=source_node["id"],
            source_requirement_id=normalized_requirement_id,
            nodes_by_node_id=nodes_by_node_id,
            propagation_depth=propagation_depth,
            semantic_change=semantic_change,
            edges=graph.get("edges") or [],
        )
        advisories = self._collect_advisories(
            source_node_id=source_node["id"],
            source_requirement_id=normalized_requirement_id,
            nodes_by_node_id=nodes_by_node_id,
            edges=graph.get("edges") or [],
            impacted_requirement_ids=set(impacted_map.keys()),
        )

        impacted_requirements = [
            {
                "requirement_id": item.requirement_id,
                "title": item.title,
                "source_level": item.source_level,
                "impact_level": item.impact_level,
                "min_distance": item.min_distance,
                "trigger_relations": item.trigger_relations,
                "short_reason": item.reason,
            }
            for item in self._sort_candidates(impacted_map.values())
        ]
        propagation_paths = [
            {
                "target_requirement_id": item.requirement_id,
                "path": item.path,
                "reason": item.reason,
            }
            for item in self._sort_candidates(impacted_map.values())
        ]

        summary = {
            "analysis_status": "completed" if impacted_requirements or advisories else "no_impact",
            "message": "已生成影响分析" if impacted_requirements or advisories else "未发现直接影响范围",
            "impacted_count": len(impacted_requirements),
            "direct_count": sum(1 for item in impacted_requirements if item["min_distance"] == 1),
            "high_risk_count": sum(1 for item in impacted_requirements if item["impact_level"] == "high"),
            "advisory_count": len(advisories),
        }

        return {
            "source_requirement": self._build_source_requirement(requirement),
            "before": before,
            "after": after,
            "changed_fields": changed_fields,
            "summary": summary,
            "impacted_requirements": impacted_requirements,
            "propagation_paths": propagation_paths,
            "advisories": {"similar_candidates": advisories},
        }

    def _build_snapshot(self, requirement: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": str(requirement.get("title") or ""),
            "description": str(requirement.get("description") or ""),
            "tags": self._normalize_tags(requirement.get("tags")),
            "priority": normalize_priority(requirement.get("priority"), allow_none=True),
            "status": normalize_requirement_status(requirement.get("status"), allow_none=True),
        }

    def _build_source_requirement(self, requirement: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "requirement_id": requirement.get("req_id"),
            "project_id": requirement.get("project_id"),
            "title": requirement.get("title") or "",
            "source_level": requirement.get("source_level") or "UNKNOWN_LEVEL",
            "status": requirement.get("status"),
            "priority": requirement.get("priority"),
            "tags": self._normalize_tags(requirement.get("tags")),
        }

    def _normalize_changes(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for field in _ALLOWED_CHANGE_FIELDS:
            if field not in changes:
                continue
            value = changes.get(field)
            if field == "title":
                normalized[field] = "" if value is None else str(value)
                continue
            if field == "description":
                normalized[field] = "" if value is None else str(value)
                continue
            if field == "tags":
                normalized[field] = self._normalize_tags(value)
                continue
            if field == "priority":
                normalized[field] = normalize_priority(value, allow_none=True)
                continue
            if field == "status":
                normalized[field] = normalize_requirement_status(value, allow_none=True)
        return normalized

    def _normalize_tags(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = value.split(",")
        elif isinstance(value, (list, tuple, set)):
            candidates = list(value)
        else:
            candidates = [value]
        normalized: List[str] = []
        seen = set()
        for item in candidates:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    def _field_changed(self, before: Any, after: Any) -> bool:
        if isinstance(before, list) or isinstance(after, list):
            return list(before or []) != list(after or [])
        return before != after

    def _build_empty_result(
        self,
        *,
        requirement: Dict[str, Any],
        before: Dict[str, Any],
        after: Dict[str, Any],
        analysis_status: str,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "source_requirement": self._build_source_requirement(requirement),
            "before": before,
            "after": after,
            "changed_fields": [],
            "summary": {
                "analysis_status": analysis_status,
                "message": message,
                "impacted_count": 0,
                "direct_count": 0,
                "high_risk_count": 0,
                "advisory_count": 0,
            },
            "impacted_requirements": [],
            "propagation_paths": [],
            "advisories": {"similar_candidates": []},
        }

    def _index_nodes(
        self,
        nodes: Iterable[Dict[str, Any]],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        nodes_by_node_id: Dict[str, Dict[str, Any]] = {}
        nodes_by_requirement_id: Dict[str, Dict[str, Any]] = {}
        for node in nodes:
            if node.get("kind") != "requirement":
                continue
            node_id = str(node.get("id") or "")
            requirement_id = str((node.get("properties") or {}).get("req_id") or "")
            if not node_id or not requirement_id:
                continue
            nodes_by_node_id[node_id] = node
            nodes_by_requirement_id[requirement_id] = node
        return nodes_by_node_id, nodes_by_requirement_id

    def _collect_impacts(
        self,
        *,
        source_node_id: str,
        source_requirement_id: str,
        nodes_by_node_id: Dict[str, Dict[str, Any]],
        propagation_depth: int,
        semantic_change: bool,
        edges: List[Dict[str, Any]],
    ) -> Dict[str, _PropagationCandidate]:
        outgoing_refines: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        incoming_refines: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        incoming_depends: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        conflict_edges: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        validate_edges: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for edge in edges:
            edge_type = edge.get("type")
            if edge_type not in _MAIN_RELATION_TYPES:
                continue
            source = edge.get("source")
            target = edge.get("target")
            if source not in nodes_by_node_id or target not in nodes_by_node_id:
                continue
            if edge_type == "REFINES":
                outgoing_refines[source].append(edge)
                incoming_refines[target].append(edge)
            elif edge_type == "DEPENDS_ON":
                incoming_depends[target].append(edge)
            elif edge_type == "CONFLICTS_WITH":
                conflict_edges[source].append(edge)
                conflict_edges[target].append(edge)
            elif edge_type == "VALIDATES_WITH":
                validate_edges[source].append(edge)
                validate_edges[target].append(edge)

        impacted_map: Dict[str, _PropagationCandidate] = {}
        queue = deque([(source_node_id, 0, [])])
        visited_depth: Dict[str, int] = {source_node_id: 0}

        while queue:
            current_node_id, current_depth, current_path = queue.popleft()

            if current_depth == 0:
                for edge in incoming_refines.get(current_node_id, []):
                    parent_node_id = edge["source"]
                    self._register_candidate(
                        impacted_map=impacted_map,
                        source_requirement_id=source_requirement_id,
                        target_node_id=parent_node_id,
                        nodes_by_node_id=nodes_by_node_id,
                        path=current_path + [self._edge_segment(edge, nodes_by_node_id)],
                        impact_level="medium",
                        reason="父需求需要重新核对本次变更对上层目标的影响。",
                    )
                for edge_group, impact_level, reason in (
                    (conflict_edges, "high", "与变更源存在直接冲突，相关约束需要重新评估。"),
                    (validate_edges, "medium", "与变更源存在直接验证联动，验收口径建议同步检查。"),
                ):
                    for edge in edge_group.get(current_node_id, []):
                        neighbor_node_id = self._other_node_id(edge, current_node_id)
                        self._register_candidate(
                            impacted_map=impacted_map,
                            source_requirement_id=source_requirement_id,
                            target_node_id=neighbor_node_id,
                            nodes_by_node_id=nodes_by_node_id,
                            path=current_path + [self._edge_segment(edge, nodes_by_node_id)],
                            impact_level=impact_level,
                            reason=reason,
                        )

            if current_depth >= propagation_depth:
                continue

            for edge in outgoing_refines.get(current_node_id, []):
                child_node_id = edge["target"]
                next_path = current_path + [self._edge_segment(edge, nodes_by_node_id)]
                next_depth = current_depth + 1
                self._register_candidate(
                    impacted_map=impacted_map,
                    source_requirement_id=source_requirement_id,
                    target_node_id=child_node_id,
                    nodes_by_node_id=nodes_by_node_id,
                    path=next_path,
                    impact_level="high" if next_depth == 1 else "medium",
                    reason=(
                        "下游细化需求直接承接变更源语义，建议同步评估。"
                        if next_depth == 1
                        else "通过细化链路传播的间接受影响需求，建议复核实现与拆解一致性。"
                    ),
                )
                if semantic_change and next_depth < propagation_depth and self._should_enqueue(visited_depth, child_node_id, next_depth):
                    visited_depth[child_node_id] = next_depth
                    queue.append((child_node_id, next_depth, next_path))

            for edge in incoming_depends.get(current_node_id, []):
                dependent_node_id = edge["source"]
                next_path = current_path + [self._edge_segment(edge, nodes_by_node_id)]
                next_depth = current_depth + 1
                self._register_candidate(
                    impacted_map=impacted_map,
                    source_requirement_id=source_requirement_id,
                    target_node_id=dependent_node_id,
                    nodes_by_node_id=nodes_by_node_id,
                    path=next_path,
                    impact_level="high" if next_depth == 1 else "medium",
                    reason=(
                        "该需求依赖变更源，前置能力变化可能直接影响其达成。"
                        if next_depth == 1
                        else "通过依赖链路传播的间接受影响需求，建议检查前置假设是否仍成立。"
                    ),
                )
                if semantic_change and next_depth < propagation_depth and self._should_enqueue(visited_depth, dependent_node_id, next_depth):
                    visited_depth[dependent_node_id] = next_depth
                    queue.append((dependent_node_id, next_depth, next_path))

        return impacted_map

    def _collect_advisories(
        self,
        *,
        source_node_id: str,
        source_requirement_id: str,
        nodes_by_node_id: Dict[str, Dict[str, Any]],
        edges: List[Dict[str, Any]],
        impacted_requirement_ids: set[str],
    ) -> List[Dict[str, Any]]:
        advisories: List[Dict[str, Any]] = []
        seen = set()
        for edge in edges:
            if edge.get("type") != "SIMILAR_TO":
                continue
            source = edge.get("source")
            target = edge.get("target")
            if source_node_id not in {source, target}:
                continue
            neighbor_node_id = target if source == source_node_id else source
            neighbor_node = nodes_by_node_id.get(neighbor_node_id)
            if not neighbor_node:
                continue
            requirement_id = str((neighbor_node.get("properties") or {}).get("req_id") or "")
            if not requirement_id or requirement_id == source_requirement_id:
                continue
            if requirement_id in impacted_requirement_ids or requirement_id in seen:
                continue
            seen.add(requirement_id)
            advisories.append(
                {
                    "requirement_id": requirement_id,
                    "title": neighbor_node.get("label") or requirement_id,
                    "source_level": (neighbor_node.get("properties") or {}).get("source_level") or "UNKNOWN_LEVEL",
                    "impact_level": "low",
                    "reason": "与变更源标签、模块或关键词相近，建议人工补充关注。",
                }
            )
        return sorted(
            advisories,
            key=lambda item: (self._level_sort_key(item.get("source_level")), item.get("title") or ""),
        )

    def _register_candidate(
        self,
        *,
        impacted_map: Dict[str, _PropagationCandidate],
        source_requirement_id: str,
        target_node_id: str,
        nodes_by_node_id: Dict[str, Dict[str, Any]],
        path: List[Dict[str, Any]],
        impact_level: str,
        reason: str,
    ) -> None:
        target_node = nodes_by_node_id.get(target_node_id)
        if not target_node:
            return
        requirement_id = str((target_node.get("properties") or {}).get("req_id") or "")
        if not requirement_id or requirement_id == source_requirement_id:
            return

        candidate = _PropagationCandidate(
            requirement_id=requirement_id,
            title=target_node.get("label") or requirement_id,
            source_level=(target_node.get("properties") or {}).get("source_level") or "UNKNOWN_LEVEL",
            impact_level=impact_level,
            min_distance=len(path),
            path=path,
            reason=reason,
            trigger_relations=self._collect_trigger_relations(path),
        )
        existing = impacted_map.get(requirement_id)
        if not existing:
            impacted_map[requirement_id] = candidate
            return

        merged_relations = self._merge_trigger_relations(
            existing.trigger_relations,
            candidate.trigger_relations,
        )
        should_replace = self._candidate_priority(candidate) > self._candidate_priority(existing)
        if should_replace:
            candidate.trigger_relations = merged_relations
            impacted_map[requirement_id] = candidate
            return

        existing.trigger_relations = merged_relations
        existing.min_distance = min(existing.min_distance, candidate.min_distance)

    def _should_enqueue(
        self,
        visited_depth: Dict[str, int],
        node_id: str,
        depth: int,
    ) -> bool:
        previous_depth = visited_depth.get(node_id)
        return previous_depth is None or depth < previous_depth

    def _edge_segment(
        self,
        edge: Dict[str, Any],
        nodes_by_node_id: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        edge_props = edge.get("properties") or {}
        source_node = nodes_by_node_id.get(edge.get("source")) or {}
        target_node = nodes_by_node_id.get(edge.get("target")) or {}
        return {
            "source": (source_node.get("properties") or {}).get("req_id") or edge.get("source"),
            "target": (target_node.get("properties") or {}).get("req_id") or edge.get("target"),
            "type": edge.get("type"),
            "source_kind": edge_props.get("source_kind") or "rule",
            "source_detail": edge_props.get("source_detail") or edge_props.get("source") or "unknown",
        }

    def _other_node_id(self, edge: Dict[str, Any], node_id: str) -> str:
        return edge.get("target") if edge.get("source") == node_id else edge.get("source")

    def _collect_trigger_relations(self, path: List[Dict[str, Any]]) -> List[str]:
        relations = {str(segment.get("type") or "") for segment in path if segment.get("type")}
        return sorted(relations, key=lambda item: (-_RELATION_PRIORITY.get(item, 0), item))

    def _merge_trigger_relations(self, left: List[str], right: List[str]) -> List[str]:
        return sorted(
            set(left or []) | set(right or []),
            key=lambda item: (-_RELATION_PRIORITY.get(item, 0), item),
        )

    def _candidate_priority(self, candidate: _PropagationCandidate) -> Tuple[int, int, int, str]:
        return (
            _RISK_LEVEL_SCORE.get(candidate.impact_level, 0),
            -candidate.min_distance,
            -len(candidate.path),
            candidate.requirement_id,
        )

    def _sort_candidates(self, candidates: Iterable[_PropagationCandidate]) -> List[_PropagationCandidate]:
        return sorted(
            candidates,
            key=lambda item: (
                -_RISK_LEVEL_SCORE.get(item.impact_level, 0),
                item.min_distance,
                self._level_sort_key(item.source_level),
                item.title,
                item.requirement_id,
            ),
        )

    def _level_sort_key(self, level: Optional[str]) -> int:
        normalized = str(level or "").upper()
        return {"L1": 1, "L2": 2, "L3": 3, "L4": 4}.get(normalized, 9)
