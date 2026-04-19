import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from psycopg2.extras import RealDictCursor

from backend_business.services.ai_proxy import ai_proxy


_REQ_REQ_INFERRED_TYPES = {
    "INCLUDES",
    "EXTENDS",
    "IMPACTS",
    "VALIDATES_WITH",
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
_UNDIRECTED_EDGE_TYPES = {"COLLABORATES_WITH", "INTEREST_CONFLICTS_WITH"}


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
        infer_relations: bool = True,
        inference_model: str = "deepseek-reasoner",
        inference_limit: int = 48,
    ) -> Dict[str, Any]:
        project_id = self._clean(project_id)
        session_id = self._clean(session_id) or self._resolve_project_session(project_id)
        limit = max(50, min(2000, int(limit or 600)))

        builder = _GraphBuilder(limit=limit)
        project_requirements = self._load_project_requirements(project_id, limit)
        l123_requirements = self._load_l123_requirements(session_id, limit)
        l4_requirements = self._load_l4_requirements(session_id, limit)

        text_index: Dict[str, List[str]] = defaultdict(list)

        for req in project_requirements:
            node_id = _req_node_id(req.get("req_id"))
            builder.add_node(
                node_id,
                kind="requirement",
                label=req.get("title") or _short_text(req.get("description"), 36),
                group=req.get("source_level") or req.get("requirement_type") or "managed",
                properties={
                    "req_id": req.get("req_id"),
                    "title": req.get("title"),
                    "content": req.get("description"),
                    "level": req.get("source_level") or "managed",
                    "type": req.get("requirement_type"),
                    "status": req.get("status"),
                    "priority": req.get("priority"),
                    "tags": _as_list(req.get("tags")),
                    "source": "manage_requirements",
                    "project_id": req.get("project_id"),
                    "created_by": req.get("created_by"),
                    "updated_by": req.get("updated_by"),
                    "assignee": req.get("assignee"),
                    "custom_fields": _as_dict(req.get("custom_fields")),
                },
            )
            _index_text(text_index, node_id, req.get("title"), req.get("description"))

        for req in l123_requirements:
            node_id = _req_node_id(req.get("req_id"))
            builder.add_node(
                node_id,
                kind="requirement",
                label=_short_text(req.get("text"), 36),
                group=req.get("level") or "L1-L3",
                properties={
                    "req_id": req.get("req_id"),
                    "content": req.get("text"),
                    "level": req.get("level"),
                    "source": "requirements_l123",
                    "session_id": req.get("session_id"),
                    "fingerprint": req.get("fingerprint"),
                    "anchor_span_id": req.get("anchor_span_id"),
                    "evidence": req.get("r"),
                },
            )
            _index_text(text_index, node_id, req.get("text"))

        for req in l4_requirements:
            node_id = _req_node_id(req.get("req_id"))
            validation_rules = {
                "acceptance_criteria": _as_list(req.get("acceptance_criteria")),
                "test_method": req.get("test_method"),
                "nfr": _as_list(req.get("nfr")),
                "open_questions": _as_list(req.get("open_questions")),
            }
            builder.add_node(
                node_id,
                kind="requirement",
                label=_short_text(req.get("text"), 36),
                group="L4",
                properties={
                    "req_id": req.get("req_id"),
                    "content": req.get("text"),
                    "level": "L4",
                    "component": req.get("component"),
                    "target_modules": _compact_list([req.get("component")]),
                    "validation_rules": validation_rules,
                    "interfaces": _as_list(req.get("interfaces")),
                    "data_contracts": _as_list(req.get("data_contracts")),
                    "error_handling": _as_list(req.get("error_handling")),
                    "confidence": req.get("confidence"),
                    "source": "low_level_requirements",
                    "session_id": req.get("session_id"),
                    "source_top_id": req.get("source_top_id"),
                },
            )
            _index_text(text_index, node_id, req.get("text"))

        self._apply_project_edges(builder, project_requirements)
        self._apply_l4_edges(builder, session_id)
        self._apply_trace_edges(builder, session_id, text_index)
        self._apply_conflict_edges(builder, session_id, text_index)
        classification_stats = self._apply_classification(builder, session_id, text_index)
        self._apply_stakeholders(builder, project_id, project_requirements)
        strong_edge_count = len(builder.edges)
        inference_stats = self._apply_llm_inference(
            builder,
            project_id=project_id,
            session_id=session_id,
            enabled=infer_relations,
            model=inference_model,
            inference_limit=inference_limit,
        )

        graph = builder.to_graph()
        graph["stats"]["classification_counts"] = classification_stats["label_distribution"]
        graph["stats"]["classified_requirement_count"] = classification_stats["matched_count"]
        graph["stats"]["classification_total"] = classification_stats["total"]
        graph["stats"]["strong_edge_count"] = strong_edge_count
        graph["stats"]["inferred_edge_count"] = inference_stats["inferred_edge_count"]
        graph["stats"]["inferred_stakeholder_count"] = inference_stats["inferred_stakeholder_count"]
        graph["legend"]["classification_labels"] = list(
            classification_stats["label_distribution"].keys()
        )
        graph["meta"] = {
            "project_id": project_id,
            "session_id": session_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": {
                "project_requirements": len(project_requirements),
                "requirements_l123": len(l123_requirements),
                "low_level_requirements": len(l4_requirements),
            },
            "inference": inference_stats,
        }
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
                    weight=0.86,
                    properties={"source": "manage_requirements.parent_id"},
                )
            if source_req_id:
                builder.add_edge(
                    _req_node_id(source_req_id),
                    target,
                    "REFINES",
                    label="来源细化",
                    weight=0.78,
                    properties={"source": "manage_requirements.source_req_id"},
                )

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
    ) -> Dict[str, Any]:
        empty_stats = {
            "enabled": enabled,
            "model": model,
            "scope_requirement_count": 0,
            "scope_stakeholder_count": 0,
            "inferred_edge_count": 0,
            "inferred_stakeholder_count": 0,
        }
        if not enabled or self.ai is None:
            return empty_stats

        scope = self._build_inference_scope(builder, inference_limit)
        if not scope["requirements"] or len(scope["all_node_ids"]) < 2:
            return empty_stats

        prompt_payload = {
            "project_id": project_id,
            "session_id": session_id,
            "requirements": scope["requirements"],
            "stakeholders": scope["stakeholders"],
            "existing_edges": scope["existing_edges"],
        }
        system_prompt = (
            "你是需求图谱关系推理器。"
            "请基于节点内容、角色职责、分类标签、层级信息和已有关系，"
            "补充缺失的高置信关系，并在必要时补充新的利益相关方节点。"
            "字段信息只是推理证据，不直接映射为关系。"
            "不要重复已有边。不要创造新的需求节点，但可以补充新的利益相关方节点。"
            "如果缺乏明确依据，请不要输出该关系。"
            "只返回严格 JSON："
            '{"stakeholders":[{"id":"stakeholder:llm:...","label":"...","role":"...","type":"...","department":"...","title":"...","reason":"..."}],'
            '"edges":[{"source":"...","target":"...","type":"...","confidence":0.0,"reason":"..."}]}'
        )
        user_prompt = (
            "请推理以下需求图谱中的新增关系，并在候选节点不足时补充新的利益相关方节点。"
            "新增利益相关方节点必须使用 stakeholder:llm: 前缀的 id。"
            "只允许输出这些关系类型："
            f"需求-需求 {sorted(_REQ_REQ_INFERRED_TYPES)}；"
            f"利益相关方-需求 {sorted(_STAKEHOLDER_REQ_INFERRED_TYPES)}；"
            f"利益相关方-利益相关方 {sorted(_STAKEHOLDER_STAKEHOLDER_INFERRED_TYPES)}。"
            "优先复用已有 stakeholder id；只有上下文中不存在合适候选人时才新增节点。"
            "reason 请简短说明依据。输入数据如下：\n"
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
        raw_stakeholders = []
        if isinstance(parsed, dict):
            raw_stakeholders = parsed.get("stakeholders") or parsed.get("nodes") or []
        merge_stats = self._merge_inferred_stakeholders(
            builder,
            raw_stakeholders if isinstance(raw_stakeholders, list) else [],
            model=model,
            valid_node_ids=scope["all_node_ids"],
        )
        valid_node_ids = set(scope["all_node_ids"]) | set(merge_stats["node_ids"])
        alias_lookup = self._build_node_alias_lookup(builder, valid_node_ids)
        alias_lookup.update(merge_stats["alias_lookup"])
        edges = parsed.get("edges") if isinstance(parsed, dict) else []
        inferred_count = 0
        for raw_edge in edges if isinstance(edges, list) else []:
            edge = self._normalize_inferred_edge(
                raw_edge,
                valid_node_ids,
                alias_lookup=alias_lookup,
            )
            if not edge:
                continue
            edge_key = (edge["source"], edge["target"], edge["type"])
            if edge_key in builder.edges:
                continue
            builder.add_edge(
                edge["source"],
                edge["target"],
                edge["type"],
                label=_edge_label(edge["type"]),
                weight=edge["confidence"],
                properties={
                    "source": "llm_inference",
                    "reason": edge["reason"],
                    "model": model,
                },
            )
            inferred_count += 1

        return {
            "enabled": enabled,
            "model": model,
            "scope_requirement_count": len(scope["requirements"]),
            "scope_stakeholder_count": len(scope["stakeholders"]),
            "inferred_edge_count": inferred_count,
            "inferred_stakeholder_count": merge_stats["inferred_count"],
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
        key = (source, target, edge_type)
        if key in self.edges:
            self.edges[key]["weight"] = max(self.edges[key]["weight"], weight)
            return
        self.edges[key] = {
            "id": f"{edge_type}:{source}->{target}",
            "source": source,
            "target": target,
            "type": edge_type,
            "label": label,
            "weight": round(float(weight), 3),
            "properties": _drop_none(properties or {}),
        }

    def to_graph(self) -> Dict[str, Any]:
        valid_edges = [
            edge
            for edge in self.edges.values()
            if edge["source"] in self.nodes and edge["target"] in self.nodes
        ]
        edge_counts = Counter(edge["type"] for edge in valid_edges)
        node_counts = Counter(node["kind"] for node in self.nodes.values())
        return {
            "nodes": list(self.nodes.values()),
            "edges": valid_edges,
            "stats": {
                "node_count": len(self.nodes),
                "edge_count": len(valid_edges),
                "node_counts": dict(node_counts),
                "edge_counts": dict(edge_counts),
            },
            "legend": {
                "node_kinds": ["requirement", "stakeholder"],
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
