import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import (
    _REQ_REQ_INFERRED_TYPES,
    _STAKEHOLDER_REQ_INFERRED_TYPES,
    _STAKEHOLDER_STAKEHOLDER_INFERRED_TYPES,
    _SYMMETRIC_EDGE_TYPES,
    _UNDIRECTED_EDGE_TYPES,
)
from .graph_core import (
    _edge_label,
    _llm_stakeholder_node_id,
    _resolve_node_reference,
    _stakeholder_node_id,
)
from .helpers import (
    _as_list,
    _clean_label,
    _compact_list,
    _drop_none,
    _extract_json_payload,
    _first_present,
    _float_or_default,
    _infer_target_modules,
    _level_priority,
    _normalize_text,
    _short_text,
    _stakeholder_profiles_compatible,
)


class RequirementGraphInferenceEngine:
    """LLM inference and scope selection for requirement graphs."""

    def __init__(self, service):
        self._service = service

    def apply_llm_inference(
        self,
        builder,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        enabled: bool,
        model: str,
        inference_limit: int,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
        allowed_relation_types: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        empty_stats = {
            "enabled": enabled,
            "model": model,
            "candidate_pair_count": 0,
            "inferred_edge_count": 0,
        }
        if not enabled or self._service.ai is None:
            return empty_stats

        pair_budget = max(6, min(80, int(inference_limit or 48)))
        selected_pairs = candidate_pairs[:pair_budget]
        if not selected_pairs:
            return empty_stats

        relation_types = allowed_relation_types or _REQ_REQ_INFERRED_TYPES
        prompt_payload = {
            "project_id": project_id,
            "session_id": session_id,
            "candidate_pairs": [
                {
                    "source": pair["source"],
                    "target": pair["target"],
                    "score": pair["score"],
                    "signals": pair["signals"],
                    "source_requirement": self.serialize_requirement_feature(requirement_features[pair["source"]]),
                    "target_requirement": self.serialize_requirement_feature(requirement_features[pair["target"]]),
                    "existing_relations": self._service._existing_pair_relations(
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
            f"只允许输出这些关系类型：{sorted(relation_types)}。"
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
        response = self._service.ai.chat_completion(
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
        alias_lookup = self.build_node_alias_lookup(builder, set(requirement_features.keys()))
        inferred_count = 0
        for raw_edge in edges if isinstance(edges, list) else []:
            edge = self.normalize_inferred_requirement_edge(
                raw_edge,
                valid_node_ids=set(requirement_features.keys()),
                valid_pairs=valid_pairs,
                alias_lookup=alias_lookup,
                allowed_relation_types=relation_types,
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

    @staticmethod
    def serialize_requirement_feature(feature: Dict[str, Any]) -> Dict[str, Any]:
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

    def normalize_inferred_requirement_edge(
        self,
        raw_edge: Any,
        *,
        valid_node_ids: set[str],
        valid_pairs: set[Tuple[str, str]],
        alias_lookup: Optional[Dict[str, str]] = None,
        allowed_relation_types: Optional[set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_edge, dict):
            return None
        source = _resolve_node_reference(raw_edge.get("source"), valid_node_ids, alias_lookup)
        target = _resolve_node_reference(raw_edge.get("target"), valid_node_ids, alias_lookup)
        edge_type = self._service._clean(raw_edge.get("type"))
        if not source or not target or not edge_type or source == target:
            return None
        relation_types = allowed_relation_types or _REQ_REQ_INFERRED_TYPES
        if edge_type not in relation_types:
            return None
        if tuple(sorted((source, target))) not in valid_pairs:
            return None
        if edge_type in _SYMMETRIC_EDGE_TYPES and source > target:
            source, target = target, source
        evidence = _compact_list(_as_list(raw_edge.get("evidence")))
        return {
            "source": source,
            "target": target,
            "type": edge_type,
            "confidence": max(0.0, min(1.0, _float_or_default(raw_edge.get("confidence"), 0.65))),
            "reason": self._service._clean(raw_edge.get("reason")) or "",
            "evidence": evidence[:8],
        }

    def build_inference_scope(self, builder, inference_limit: int) -> Dict[str, Any]:
        inference_limit = max(12, min(120, int(inference_limit or 48)))
        requirement_nodes = [node for node in builder.nodes.values() if node.get("kind") == "requirement"]
        stakeholder_nodes = [node for node in builder.nodes.values() if node.get("kind") == "stakeholder"]
        if not requirement_nodes:
            return {"requirements": [], "stakeholders": [], "existing_edges": [], "all_node_ids": set()}

        requirement_budget = min(
            len(requirement_nodes),
            max(8, min(inference_limit - 4, int(inference_limit * 0.75))),
        )
        requirement_ids = self.select_requirement_candidates(
            requirement_nodes,
            builder.edges.values(),
            requirement_budget,
        )
        stakeholder_budget = max(0, min(len(stakeholder_nodes), inference_limit - len(requirement_ids)))
        stakeholder_ids = self.select_stakeholder_candidates(
            requirement_ids,
            stakeholder_nodes,
            builder.edges.values(),
            builder.nodes,
            stakeholder_budget,
        )

        requirements = [
            self.serialize_requirement_node(builder.nodes[node_id])
            for node_id in requirement_ids
            if node_id in builder.nodes
        ]
        stakeholders = [
            self.serialize_stakeholder_node(builder.nodes[node_id])
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

    def select_requirement_candidates(
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
            if not (str(source).startswith("req:") and str(target).startswith("req:")) or source == target:
                continue
            degree_map[source] += 1
            degree_map[target] += 1
            neighbor_map[source].add(target)
            neighbor_map[target].add(source)

        def score(node: Dict[str, Any]) -> Tuple[int, int, int, str]:
            props = node.get("properties") or {}
            priority = int(_float_or_default(props.get("priority"), 0))
            validation = props.get("validation_rules") or {}
            validation_bonus = 10 if any(validation.values()) else 0
            people_bonus = 6 if any(props.get(field) for field in ("created_by", "updated_by", "assignee")) else 0
            category_bonus = 8 if props.get("category") else 0
            module_bonus = 6 if _infer_target_modules(props) else 0
            total = (
                degree_map.get(node["id"], 0) * 100
                + priority * 18
                + _level_priority(props.get("level")) * 8
                + validation_bonus
                + people_bonus
                + category_bonus
                + module_bonus
            )
            return (total, degree_map.get(node["id"], 0), priority, node["id"])

        sorted_nodes = sorted(
            requirement_nodes,
            key=lambda node: (-score(node)[0], -score(node)[1], -score(node)[2], node["id"]),
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
                [node_id for node_id in neighbor_map.get(anchor_id, set()) if node_id in by_id],
                key=lambda node_id: (-score(by_id[node_id])[0], by_id[node_id]["id"]),
            ):
                add_requirement(neighbor_id)
        for node in sorted_nodes:
            add_requirement(node["id"])
        return selected_ids

    def select_stakeholder_candidates(
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
                user_id = self._service._clean(props.get(field))
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

        def score(node: Dict[str, Any]) -> Tuple[int, int, int, str]:
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
            return (mentions * 100 + source_priority * 20 + metadata_bonus, mentions, source_priority, node["id"])

        sorted_nodes = sorted(
            stakeholder_nodes,
            key=lambda node: (-score(node)[0], -score(node)[1], -score(node)[2], node["id"]),
        )
        selected_ids: List[str] = []
        for node in sorted_nodes:
            if len(selected_ids) >= budget:
                break
            if score(node)[0] <= 0 and selected_ids:
                break
            selected_ids.append(node["id"])
        return selected_ids

    @staticmethod
    def serialize_requirement_node(node: Dict[str, Any]) -> Dict[str, Any]:
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

    @staticmethod
    def serialize_stakeholder_node(node: Dict[str, Any]) -> Dict[str, Any]:
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

    def merge_inferred_stakeholders(
        self,
        builder,
        raw_stakeholders: List[Any],
        *,
        model: str,
        valid_node_ids: set[str],
    ) -> Dict[str, Any]:
        existing_ids = set(builder.nodes)
        existing_alias_lookup = self.build_node_alias_lookup(builder, valid_node_ids)
        label_lookup: Dict[str, List[str]] = defaultdict(list)
        for node_id, node in builder.nodes.items():
            if node_id not in valid_node_ids or node.get("kind") != "stakeholder":
                continue
            label_lookup[_normalize_text(node.get("label"))].append(node_id)
        alias_lookup: Dict[str, str] = {}
        inferred_node_ids: List[str] = []

        for raw_stakeholder in raw_stakeholders:
            stakeholder = self.normalize_inferred_stakeholder(raw_stakeholder)
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
                        "source": "llm_inference"
                        if not matched_id
                        else builder.nodes[final_id]["properties"].get("source"),
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

    def normalize_inferred_stakeholder(self, raw_stakeholder: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_stakeholder, dict):
            return None
        label = self._service._clean(
            raw_stakeholder.get("label")
            or raw_stakeholder.get("name")
            or raw_stakeholder.get("stakeholder")
        )
        if not label:
            return None
        raw_id = self._service._clean(raw_stakeholder.get("id")) or _llm_stakeholder_node_id(label)
        node_id = raw_id if raw_id.startswith("stakeholder:") else _stakeholder_node_id(raw_id)
        roles = _compact_list(_as_list(raw_stakeholder.get("roles") or raw_stakeholder.get("role")))
        role = self._service._clean(raw_stakeholder.get("role")) or _first_present(*roles)
        return {
            "id": node_id,
            "label": label,
            "role": role,
            "roles": roles,
            "type": self._service._clean(raw_stakeholder.get("type")),
            "department": self._service._clean(raw_stakeholder.get("department")),
            "title": self._service._clean(raw_stakeholder.get("title")),
            "reason": self._service._clean(raw_stakeholder.get("reason")),
        }

    def build_node_alias_lookup(
        self,
        builder,
        valid_node_ids: set[str],
    ) -> Dict[str, str]:
        alias_lookup: Dict[str, str] = {}
        for node_id, node in builder.nodes.items():
            if node_id not in valid_node_ids:
                continue
            alias_lookup[node_id] = node_id
            label = self._service._clean(node.get("label"))
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
                clean_value = self._service._clean(value)
                if clean_value:
                    alias_lookup[clean_value] = node_id
                    alias_lookup[_normalize_text(clean_value)] = node_id
        return alias_lookup

    def normalize_inferred_edge(
        self,
        raw_edge: Any,
        valid_node_ids: set[str],
        alias_lookup: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_edge, dict):
            return None
        source = _resolve_node_reference(raw_edge.get("source"), valid_node_ids, alias_lookup)
        target = _resolve_node_reference(raw_edge.get("target"), valid_node_ids, alias_lookup)
        edge_type = self._service._clean(raw_edge.get("type"))
        if not source or not target or not edge_type or source == target:
            return None
        if source not in valid_node_ids or target not in valid_node_ids:
            return None
        source_kind = "stakeholder" if source.startswith("stakeholder:") else "requirement"
        target_kind = "stakeholder" if target.startswith("stakeholder:") else "requirement"
        if source_kind == "requirement" and target_kind == "requirement" and edge_type not in _REQ_REQ_INFERRED_TYPES:
            return None
        if source_kind == "stakeholder" and target_kind == "requirement" and edge_type not in _STAKEHOLDER_REQ_INFERRED_TYPES:
            return None
        if source_kind == "stakeholder" and target_kind == "stakeholder" and edge_type not in _STAKEHOLDER_STAKEHOLDER_INFERRED_TYPES:
            return None
        if edge_type in _UNDIRECTED_EDGE_TYPES and source > target:
            source, target = target, source
        return {
            "source": source,
            "target": target,
            "type": edge_type,
            "confidence": max(0.0, min(1.0, _float_or_default(raw_edge.get("confidence"), 0.65))),
            "reason": self._service._clean(raw_edge.get("reason")) or "",
        }
