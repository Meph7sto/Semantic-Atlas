import asyncio
import json
import logging
from pathlib import Path
import re
import threading
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp

from .constants import (
    _CONFLICT_MARKERS,
    _DEPENDENCY_MARKERS,
    _GENERIC_TERMS,
    _LEVEL_ORDER,
    _MODEL_DATA_DIR,
    _NON_INFORMATIVE_TERMS,
    _RELATION_PRIORITY,
    _REQUIREMENT_GRAPH_EMBEDDING_DIR,
    _RESOURCE_TERMS,
    _SEMANTIC_EMBEDDING_MODEL,
    _SEMANTIC_PAIR_THRESHOLD,
    _SEMANTIC_SIMILARITY_THRESHOLD,
    _SOURCE_KIND_PRIORITY,
    _SYMMETRIC_EDGE_TYPES,
    _TRANSIENT_TOOL_ERROR_STATUSES,
    _VALIDATION_MARKERS,
)

logger = logging.getLogger(__name__)

_semantic_embedder = None
_semantic_embedding_error: Optional[str] = None
_semantic_embedder_lock = threading.Lock()


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


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _short_text(text: Any, max_len: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return "未命名需求"
    return value if len(value) <= max_len else f"{value[:max_len]}..."


def _normalize_signal(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


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


def _is_informative_term(term: str) -> bool:
    normalized = str(term or "").strip().lower()
    if not normalized or normalized in _NON_INFORMATIVE_TERMS:
        return False
    if re.fullmatch(r"[a-z][a-z0-9_/-]*", normalized) and len(normalized) < 4:
        return False
    return True


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


def _max_term_document_frequency(requirement_count: int) -> int:
    if requirement_count <= 0:
        return 0
    return max(2, min(12, int(requirement_count * 0.3) or 2))


def _semantic_embedding_enabled() -> bool:
    import os

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

            model_source = _resolve_semantic_embedding_source()
            _semantic_embedder = SentenceTransformer(
                model_source,
                cache_folder=str(_MODEL_DATA_DIR),
            )
        except Exception as exc:
            _semantic_embedding_error = str(exc)
            logger.warning("Requirement graph semantic embedder unavailable: %s", exc)
            return None
    return _semantic_embedder


def _resolve_semantic_embedding_source() -> str:
    configured_model = str(_SEMANTIC_EMBEDDING_MODEL or "").strip()
    configured_path = Path(configured_model) if configured_model else None
    if configured_path and configured_path.exists():
        return str(configured_path.resolve())

    local_model_dir = Path(_REQUIREMENT_GRAPH_EMBEDDING_DIR).resolve()
    if _semantic_model_artifacts_present(local_model_dir):
        return str(local_model_dir)

    local_model_dir.parent.mkdir(parents=True, exist_ok=True)
    if not configured_model:
        return str(local_model_dir)

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=configured_model,
            local_dir=str(local_model_dir),
        )
        return str(local_model_dir)
    except Exception as exc:
        logger.warning(
            "Requirement graph semantic model download to %s failed; "
            "falling back to model id %s (%s)",
            local_model_dir,
            configured_model,
            exc,
        )
        return configured_model


def _semantic_model_artifacts_present(model_dir: Path) -> bool:
    if not model_dir.exists():
        return False
    marker_paths = (
        model_dir / "modules.json",
        model_dir / "config_sentence_transformers.json",
        model_dir / "config.json",
        model_dir / "sentence_bert_config.json",
        model_dir / "1_Pooling" / "config.json",
    )
    return any(path.exists() for path in marker_paths)


def _get_semantic_embedding_error() -> Optional[str]:
    return _semantic_embedding_error


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


def _normalize_edge_properties(properties: Dict[str, Any], weight: float) -> Dict[str, Any]:
    props = dict(properties or {})
    source_detail = props.get("source_detail") or props.get("source") or "unknown"
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
    if detail.startswith("trace_analysis"):
        return "trace_analysis"
    if detail.startswith("conflict_analysis"):
        return "conflict_analysis"
    if detail.startswith("classification_analysis"):
        return "classification_analysis"
    if detail.startswith("local_vector") or detail.startswith("semantic_candidate"):
        return "local_vector"
    if "llm" in detail:
        return "llm"
    if detail.startswith("rule_") or detail.startswith("semantic_"):
        return "rule_extra"
    return "rule_extra"


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
