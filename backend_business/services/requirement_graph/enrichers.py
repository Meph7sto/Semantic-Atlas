from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from psycopg2.extras import RealDictCursor

from .graph_core import (
    _edge_label,
    _req_node_id,
    _resolve_requirement_node,
    _resolve_requirement_node_fuzzy,
    _stakeholder_node_id,
)
from .helpers import (
    _as_dict,
    _as_list,
    _clean_label,
    _compact_list,
    _float_or_default,
    _normalize_label_distribution,
    _pick_index,
)


class RequirementGraphEnricher:
    """Applies auxiliary graph enrichments from analysis and membership data."""

    def __init__(self, service, data_access):
        self._service = service
        self._data_access = data_access

    def apply_l4_edges(
        self,
        builder,
        session_id: Optional[str],
    ) -> None:
        if not session_id:
            return
        with self._service.db.get_connection() as conn:
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

    def apply_trace_edges(
        self,
        builder,
        session_id: Optional[str],
        text_index: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        stats = {"record_id": None, "edge_count": 0}
        if not session_id or not hasattr(self._service.db, "get_latest_trace_batch"):
            return stats
        latest = self._service.db.get_latest_trace_batch(session_id)
        stats["record_id"] = (latest or {}).get("record_id")
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
                properties={
                    "source_kind": "trace_analysis",
                    "source_detail": "trace_analysis",
                    "source": "trace_analysis",
                    "record": rel,
                    "record_id": stats["record_id"],
                    "index": index,
                    "confidence": _float_or_default(rel.get("confidence"), 0.72),
                },
            )
            stats["edge_count"] += 1
        return stats

    def apply_conflict_edges(
        self,
        builder,
        session_id: Optional[str],
        text_index: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        stats = {"batch_id": None, "edge_count": 0}
        if not session_id or not hasattr(self._service.db, "get_latest_conflict_batch"):
            return stats
        latest = self._service.db.get_latest_conflict_batch(session_id) or {}
        stats["batch_id"] = latest.get("batch_id")
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
                    "source_kind": "conflict_analysis",
                    "source_detail": "conflict_analysis",
                    "source": "conflict_analysis",
                    "batch_id": stats["batch_id"],
                    "result": _as_dict(item.get("result_json")),
                    "index": index,
                    "confidence": 0.96,
                },
            )
            stats["edge_count"] += 1
        return stats

    def apply_classification(
        self,
        builder,
        session_id: Optional[str],
        text_index: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        empty_stats = {"record_id": None, "label_distribution": {}, "matched_count": 0, "total": 0, "edge_count": 0}
        if not session_id or not hasattr(self._service.db, "get_latest_classification"):
            return empty_stats
        latest = self._service.db.get_latest_classification(session_id) or {}
        empty_stats["record_id"] = latest.get("id")
        predictions = latest.get("predictions") or []
        grouped_nodes: Dict[str, List[str]] = defaultdict(list)
        raw_label_distribution: Dict[str, int] = defaultdict(int)
        matched_count = 0
        edge_count = 0

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
                    properties={
                        "source_kind": "classification_analysis",
                        "source_detail": "classification_analysis",
                        "source": "classification_analysis",
                        "category": label,
                        "record_id": latest.get("id"),
                        "confidence": 0.58,
                    },
                )
                edge_count += 1

        label_distribution = _normalize_label_distribution(latest.get("label_distribution"))
        if not label_distribution:
            label_distribution = dict(raw_label_distribution) or {
                label: len(list(dict.fromkeys(node_ids)))
                for label, node_ids in grouped_nodes.items()
            }
        return {
            "record_id": latest.get("id"),
            "label_distribution": label_distribution,
            "matched_count": matched_count,
            "total": int(latest.get("total") or sum(label_distribution.values()) or matched_count),
            "edge_count": edge_count,
        }

    def apply_stakeholders(
        self,
        builder,
        project_id: Optional[str],
        project_requirements: Iterable[Dict[str, Any]],
    ) -> None:
        member_profiles = self._data_access.load_project_members(project_id)
        user_ids = set(member_profiles)
        for req in project_requirements:
            for field in ("created_by", "updated_by", "assignee"):
                value = self._service._clean(req.get(field))
                if value:
                    user_ids.add(value)

        for user_id in sorted(user_ids):
            profile = member_profiles.get(user_id, {})
            label = profile.get("display_name") or profile.get("username") or user_id
            roles = profile.get("roles") or []
            role_label = "/".join(_compact_list([r.get("role_id") for r in roles])) or profile.get("role")
            source = "project_members/auth_users" if user_id in member_profiles else "requirement_people_evidence"
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
