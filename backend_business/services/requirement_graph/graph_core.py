import hashlib
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import _LEVEL_ORDER, _SYMMETRIC_EDGE_TYPES
from .helpers import (
    _as_dict,
    _as_list,
    _compact_list,
    _drop_none,
    _float_or_default,
    _merge_edge_properties,
    _normalize_edge_properties,
    _normalize_signal,
    _normalize_text,
)


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

    def remove_edge(self, source: str, target: str, edge_type: str) -> bool:
        key = _normalize_edge_key(source, target, edge_type)
        if key not in self.edges:
            return False
        del self.edges[key]
        return True

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


def _pair_candidate_id(source: Any, target: Any) -> str:
    left, right = sorted((str(source or "").strip(), str(target or "").strip()))
    return f"pair:{left}|{right}"


def _normalize_edge_key(source: Any, target: Any, edge_type: Any) -> Tuple[str, str, str]:
    normalized_source = str(source or "").strip()
    normalized_target = str(target or "").strip()
    normalized_type = str(edge_type or "").strip()
    if normalized_type in _SYMMETRIC_EDGE_TYPES and normalized_source > normalized_target:
        normalized_source, normalized_target = normalized_target, normalized_source
    return normalized_source, normalized_target, normalized_type


def _stakeholder_node_id(user_id: Any) -> str:
    return f"stakeholder:{user_id}"


def _llm_stakeholder_node_id(label: Any) -> str:
    normalized = _normalize_text(label)
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:10] if normalized else "unknown"
    return f"stakeholder:llm:{digest}"


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
        explicit_matches = text_index.get(_normalize_text(explicit_id)) or []
        if explicit_matches:
            return explicit_matches[0]
    normalized = _normalize_text(text)
    matches = text_index.get(normalized) or []
    if matches:
        return matches[0]
    if explicit_id:
        return _req_node_id(explicit_id)
    return None


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


def _has_stronger_relation(builder: _GraphBuilder, left_id: str, right_id: str) -> bool:
    pair = {left_id, right_id}
    for edge in builder.edges.values():
        if {edge["source"], edge["target"]} != pair:
            continue
        if edge["type"] != "SIMILAR_TO":
            return True
    return False


def _existing_pair_relations(
    builder: _GraphBuilder,
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
