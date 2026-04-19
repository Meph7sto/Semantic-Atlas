import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from psycopg2.extras import RealDictCursor


class RequirementGraphService:
    """Build a lightweight requirement knowledge graph from existing analysis data."""

    def __init__(self, db_service: Any):
        self.db = db_service

    def build_graph(
        self,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 600,
    ) -> Dict[str, Any]:
        project_id = self._clean(project_id)
        session_id = self._clean(session_id) or self._resolve_project_session(project_id)
        limit = max(50, min(2000, int(limit or 600)))

        builder = _GraphBuilder(limit=limit)
        project_requirements = self._load_project_requirements(project_id, limit)
        l123_requirements = self._load_l123_requirements(session_id, limit)
        l4_requirements = self._load_l4_requirements(session_id, limit)

        text_index: Dict[str, List[str]] = defaultdict(list)
        owners_by_requirement: Dict[str, Dict[str, Optional[str]]] = {}

        for req in project_requirements:
            node_id = _req_node_id(req.get("req_id"))
            owners_by_requirement[node_id] = {
                "created_by": self._clean(req.get("created_by")),
                "updated_by": self._clean(req.get("updated_by")),
                "assignee": self._clean(req.get("assignee")),
            }
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
        self._apply_conflict_edges(builder, session_id, text_index, owners_by_requirement)
        classification_stats = self._apply_classification(builder, session_id, text_index)
        self._apply_stakeholders(builder, project_id, owners_by_requirement)

        graph = builder.to_graph()
        graph["stats"]["classification_counts"] = classification_stats["label_distribution"]
        graph["stats"]["classified_requirement_count"] = classification_stats["matched_count"]
        graph["stats"]["classification_total"] = classification_stats["total"]
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
        owners_by_requirement: Dict[str, Dict[str, Optional[str]]],
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
            self._add_stakeholder_conflict_edge(builder, source, target, owners_by_requirement)

    def _add_stakeholder_conflict_edge(
        self,
        builder: "_GraphBuilder",
        source_req: str,
        target_req: str,
        owners_by_requirement: Dict[str, Dict[str, Optional[str]]],
    ) -> None:
        source_owner = _first_present(
            owners_by_requirement.get(source_req, {}).get("assignee"),
            owners_by_requirement.get(source_req, {}).get("created_by"),
        )
        target_owner = _first_present(
            owners_by_requirement.get(target_req, {}).get("assignee"),
            owners_by_requirement.get(target_req, {}).get("created_by"),
        )
        if source_owner and target_owner and source_owner != target_owner:
            builder.add_edge(
                _stakeholder_node_id(source_owner),
                _stakeholder_node_id(target_owner),
                "INTEREST_CONFLICTS_WITH",
                label="利益冲突",
                weight=0.66,
                properties={"source": "requirement_conflict_projection"},
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
            node_id = _resolve_requirement_node(None, req_text, text_index)
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
            label_distribution = {
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
        owners_by_requirement: Dict[str, Dict[str, Optional[str]]],
    ) -> None:
        member_profiles = self._load_project_members(project_id)
        user_ids = set(member_profiles)
        for owners in owners_by_requirement.values():
            user_ids.update(v for v in owners.values() if v)

        for user_id in sorted(user_ids):
            profile = member_profiles.get(user_id, {})
            label = profile.get("display_name") or profile.get("username") or user_id
            roles = profile.get("roles") or []
            role_label = "/".join(_compact_list([r.get("role_id") for r in roles])) or profile.get("role")
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
                    "type": profile.get("external_type") or "internal",
                    "authority": _authority_from_roles(roles, profile.get("role")),
                    "source": "project_members/auth_users",
                },
            )

        for req_node, owners in owners_by_requirement.items():
            created_by = owners.get("created_by")
            updated_by = owners.get("updated_by")
            assignee = owners.get("assignee")
            if created_by:
                builder.add_edge(
                    _stakeholder_node_id(created_by),
                    req_node,
                    "RAISES",
                    label="提出",
                    weight=0.8,
                    properties={"source": "manage_requirements.created_by"},
                )
            if assignee:
                builder.add_edge(
                    _stakeholder_node_id(assignee),
                    req_node,
                    "OWNS",
                    label="负责",
                    weight=0.86,
                    properties={"source": "manage_requirements.assignee"},
                )
            if updated_by and updated_by != created_by:
                builder.add_edge(
                    _stakeholder_node_id(updated_by),
                    req_node,
                    "AFFECTED_BY",
                    label="参与变更",
                    weight=0.62,
                    properties={"source": "manage_requirements.updated_by"},
                )

    def _load_project_members(self, project_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
        if not project_id:
            return {}
        if hasattr(self.db, "list_project_members"):
            data = self.db.list_project_members(project_id, include_roles=True)
            members = data.get("members") if isinstance(data, dict) else []
            return {m["user_id"]: m for m in members if m.get("user_id")}
        return {}

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
    }.get(edge_type, edge_type)


def _authority_from_roles(roles: List[Dict[str, Any]], fallback_role: Optional[str]) -> str:
    role_ids = {role.get("role_id") for role in roles if isinstance(role, dict)}
    if {"PO", "CLIENT"} & role_ids:
        return "decision"
    if {"REVIEWER", "QA"} & role_ids:
        return "validation"
    if {"BA"} & role_ids:
        return "analysis"
    if {"DEV", "CONTRACTOR"} & role_ids:
        return "implementation"
    if fallback_role in {"super_admin", "admin"}:
        return "decision"
    return "participant"
