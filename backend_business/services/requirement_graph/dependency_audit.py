import asyncio
import json
import logging
import threading
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .constants import (
    _DEPENDENCY_AUDIT_BATCH_SIZE,
    _DEPENDENCY_AUDIT_CONFIDENCE_THRESHOLD,
    _DEPENDENCY_AUDIT_MAX_CONCURRENCY,
    _DEPENDENCY_PER_SOURCE_LIMIT,
    _REQ_REQ_INFERRED_TYPES,
    _SYMMETRIC_EDGE_TYPES,
)
from .graph_core import _edge_label, _existing_pair_relations, _has_stronger_relation
from .helpers import (
    _as_list,
    _compact_list,
    _extract_json_payload,
    _float_or_default,
    _is_retryable_dependency_audit_error,
    _match_conflict_rule,
    _match_dependency_rule,
    _match_similarity_rule,
    _match_validation_rule,
    _merge_evidence,
)

logger = logging.getLogger(__name__)


class _DependencyAuditToolDef:
    @classmethod
    def get_tool_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_dependency_decisions",
                "description": (
                    "基于候选依赖对，返回每个候选是否成立、是否应反转方向，并给出简明证据。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "decisions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "candidate_id": {"type": "string"},
                                    "action": {
                                        "type": "string",
                                        "enum": ["confirm", "reverse", "reject", "unclear"],
                                    },
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                    "dependency_kind": {
                                        "type": "string",
                                        "enum": ["data", "control", "temporal", "resource", "validation", "other"],
                                    },
                                    "reason": {"type": "string"},
                                    "evidence": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["candidate_id", "action", "confidence", "reason"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["decisions"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_system_prompt(cls) -> str:
        return """你是需求依赖关系的严格裁决器。

你的任务不是“多找关系”，而是“删掉伪依赖”。

只在以下情况确认 DEPENDS_ON：
1. source 明确调用、读取、消费、依赖 target 的接口/数据/组件；
2. target 是 source 的前置条件、执行前提或必经校验；
3. 没有 target，source 无法正确实现、运行、验证或交付。

必须拒绝这些常见伪依赖：
- 只是同一模块、同一主题、同一父需求下的兄弟项；
- 只是都提到了相似关键词；
- 只是“相关”“配合”“一起工作”，但没有明确前置/输入输出/调用链；
- 只是同类能力或相邻功能。

方向判断规则：
- 如果实际是 target 依赖 source，返回 reverse；
- 如果证据不足，返回 reject 或 unclear，不要勉强确认。

输出要求：
- 必须调用 submit_dependency_decisions 工具；
- candidate_id 必须来自输入；
- 不要输出工具之外的普通文本。"""


class RequirementGraphDependencyAudit:
    """Rule edge application and dependency audit orchestration."""

    def __init__(self, service):
        self._service = service

    def apply_rule_edges(
        self,
        builder,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
        *,
        dependency_model: str = "deepseek-v4-pro",
        dependency_review_limit: int = 48,
        include_authoritative_relations: bool = True,
    ) -> Dict[str, Any]:
        edge_counter: Counter[str] = Counter()
        dependency_candidates: List[Dict[str, Any]] = []
        for pair in candidate_pairs:
            left = requirement_features.get(pair["source"])
            right = requirement_features.get(pair["target"])
            if not left or not right:
                continue

            dependency_lr = _match_dependency_rule(left, right)
            dependency_rl = _match_dependency_rule(right, left)
            conflict = _match_conflict_rule(left, right)
            validation = _match_validation_rule(left, right)
            similar = _match_similarity_rule(left, right)

            if include_authoritative_relations:
                for source_feature, target_feature, relation in (
                    (left, right, dependency_lr),
                    (right, left, dependency_rl),
                ):
                    if relation:
                        candidate = self.build_dependency_candidate(
                            source_feature=source_feature,
                            target_feature=target_feature,
                            relation=relation,
                            pair=pair,
                        )
                        if candidate:
                            dependency_candidates.append(candidate)

                if conflict:
                    builder.add_edge(
                        left["id"],
                        right["id"],
                        "CONFLICTS_WITH",
                        label=_edge_label("CONFLICTS_WITH"),
                        weight=conflict["confidence"],
                        properties={
                            "source_kind": "rule_extra",
                            "source_detail": conflict["detail"],
                            "source": conflict["detail"],
                            "confidence": conflict["confidence"],
                            "reason": conflict["reason"],
                            "evidence": conflict["evidence"],
                        },
                    )
                    edge_counter["CONFLICTS_WITH"] += 1

            if validation:
                builder.add_edge(
                    left["id"],
                    right["id"],
                    "VALIDATES_WITH",
                    label=_edge_label("VALIDATES_WITH"),
                    weight=validation["confidence"],
                    properties={
                        "source_kind": "rule_extra",
                        "source_detail": validation["detail"],
                        "source": validation["detail"],
                        "confidence": validation["confidence"],
                        "reason": validation["reason"],
                        "evidence": validation["evidence"],
                    },
                )
                edge_counter["VALIDATES_WITH"] += 1

            if include_authoritative_relations and similar and not _has_stronger_relation(builder, left["id"], right["id"]):
                builder.add_edge(
                    left["id"],
                    right["id"],
                    "SIMILAR_TO",
                    label=_edge_label("SIMILAR_TO"),
                    weight=similar["confidence"],
                    properties={
                        "source_kind": "rule_extra",
                        "source_detail": similar["detail"],
                        "source": similar["detail"],
                        "confidence": similar["confidence"],
                        "reason": similar["reason"],
                        "evidence": similar["evidence"],
                    },
                )
                edge_counter["SIMILAR_TO"] += 1

        if include_authoritative_relations:
            dependency_audit = self.apply_dependency_candidates(
                builder,
                dependency_candidates,
                model=dependency_model,
                review_limit=dependency_review_limit,
            )
            if dependency_audit["confirmed_count"]:
                edge_counter["DEPENDS_ON"] += dependency_audit["confirmed_count"]
        else:
            dependency_audit = {
                "model": dependency_model,
                "candidate_count": 0,
                "reviewed_count": 0,
                "confirmed_count": 0,
                "rejected_count": 0,
                "fallback_used": False,
                "pruned_transitive_count": 0,
            }

        return {
            "edge_counts": dict(edge_counter),
            "dependency_audit": dependency_audit,
        }

    def build_dependency_candidate(
        self,
        *,
        source_feature: Dict[str, Any],
        target_feature: Dict[str, Any],
        relation: Dict[str, Any],
        pair: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        evidence = _compact_list(_as_list(relation.get("evidence")))
        if not self.is_dependency_candidate_strong(evidence):
            return None
        source_req_id = self._service._clean(source_feature.get("req_id")) or source_feature["id"]
        target_req_id = self._service._clean(target_feature.get("req_id")) or target_feature["id"]
        return {
            "candidate_id": f"dep:{source_req_id}->{target_req_id}",
            "source": source_feature["id"],
            "target": target_feature["id"],
            "score": float(pair.get("score") or 0),
            "rule_confidence": float(relation.get("confidence") or 0),
            "detail": relation.get("detail"),
            "reason": relation.get("reason"),
            "evidence": evidence[:8],
            "signals": _compact_list(_as_list(pair.get("signals")))[:8],
            "source_requirement": self._service._serialize_requirement_feature(source_feature),
            "target_requirement": self._service._serialize_requirement_feature(target_feature),
        }

    @staticmethod
    def is_dependency_candidate_strong(evidence: List[str]) -> bool:
        strong_markers = ("mentioned_module:", "shared_interface:", "shared_validation:")
        if any(item.startswith(strong_markers) for item in evidence):
            return True
        shared_module_count = sum(1 for item in evidence if item.startswith("shared_module:"))
        return shared_module_count >= 1 and len(evidence) >= 3

    def apply_dependency_candidates(
        self,
        builder,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
        review_limit: int,
    ) -> Dict[str, Any]:
        selected_candidates = self.select_dependency_candidates(
            dependency_candidates,
            review_limit=review_limit,
        )
        if not selected_candidates:
            return {
                "model": model,
                "candidate_count": 0,
                "reviewed_count": 0,
                "confirmed_count": 0,
                "rejected_count": 0,
                "fallback_used": False,
                "pruned_transitive_count": 0,
            }

        fallback_used = False
        try:
            reviewed = self.review_dependency_candidates_with_llm(
                selected_candidates,
                model=model,
            )
            fallback_used = any(bool(item.get("used_fallback")) for item in reviewed)
        except Exception as exc:
            self.log_dependency_audit_failure(
                exc,
                candidate_count=len(selected_candidates),
                model=model,
                fallback_scope="full",
            )
            reviewed = self.fallback_dependency_decisions(selected_candidates)
            fallback_used = True

        confirmed_count = 0
        rejected_count = 0
        for decision in reviewed:
            action = str(decision.get("action") or "").strip().lower()
            candidate = decision.get("candidate")
            if not candidate or action in {"reject", "unclear"}:
                rejected_count += 1
                continue
            confidence = max(
                _float_or_default(candidate.get("rule_confidence"), 0),
                _float_or_default(decision.get("confidence"), 0),
            )
            if confidence < _DEPENDENCY_AUDIT_CONFIDENCE_THRESHOLD:
                rejected_count += 1
                continue

            source = candidate["source"]
            target = candidate["target"]
            if action == "reverse":
                source, target = target, source

            builder.add_edge(
                source,
                target,
                "DEPENDS_ON",
                label=_edge_label("DEPENDS_ON"),
                weight=confidence,
                properties={
                    "source_kind": "rule_extra",
                    "source_detail": candidate.get("detail"),
                    "source": candidate.get("detail"),
                    "confidence": confidence,
                    "reason": decision.get("reason") or candidate.get("reason"),
                    "evidence": _merge_evidence(candidate.get("evidence"), decision.get("evidence"), limit=10),
                    "audit_model": model,
                    "audit_confidence": _float_or_default(decision.get("confidence"), confidence),
                    "audit_action": action,
                    "dependency_kind": decision.get("dependency_kind"),
                },
            )
            confirmed_count += 1

        pruned_transitive_count = self.prune_transitive_dependency_edges(builder)
        confirmed_count = max(0, confirmed_count - pruned_transitive_count)
        return {
            "model": model,
            "candidate_count": len(dependency_candidates),
            "reviewed_count": len(selected_candidates),
            "confirmed_count": confirmed_count,
            "rejected_count": rejected_count,
            "fallback_used": fallback_used,
            "pruned_transitive_count": pruned_transitive_count,
        }

    def log_dependency_audit_failure(
        self,
        exc: Exception,
        *,
        candidate_count: int,
        model: str,
        fallback_scope: str,
    ) -> None:
        message = (
            "Dependency audit tool-call failed; falling back to strict rule filter "
            "(scope=%s, candidates=%s, model=%s)"
        )
        if _is_retryable_dependency_audit_error(exc):
            logger.warning(message + " reason=%s", fallback_scope, candidate_count, model, repr(exc))
            return
        logger.exception(message, fallback_scope, candidate_count, model)

    def select_dependency_candidates(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        review_limit: int,
    ) -> List[Dict[str, Any]]:
        limit = max(8, min(96, int(review_limit or 48)))
        per_source_counts: Dict[str, int] = defaultdict(int)
        selected: List[Dict[str, Any]] = []
        ordered = sorted(
            dependency_candidates,
            key=lambda item: (
                -_float_or_default(item.get("score"), 0),
                -_float_or_default(item.get("rule_confidence"), 0),
                -(len(item.get("evidence") or [])),
                str(item.get("candidate_id") or ""),
            ),
        )
        for candidate in ordered:
            source = candidate["source"]
            if per_source_counts[source] >= _DEPENDENCY_PER_SOURCE_LIMIT:
                continue
            selected.append(candidate)
            per_source_counts[source] += 1
            if len(selected) >= limit:
                break
        return selected

    def review_dependency_candidates_with_llm(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
    ) -> List[Dict[str, Any]]:
        if self._service.ai is None:
            return self.fallback_dependency_decisions(dependency_candidates)

        if not self._supports_tool_review(model):
            if hasattr(self._service.ai, "chat_completion"):
                return self.review_dependency_candidates_with_json(
                    dependency_candidates,
                    model=model,
                )
            return self.fallback_dependency_decisions(dependency_candidates)

        coroutine = self.review_dependency_candidates_with_llm_async(
            dependency_candidates,
            model=model,
        )
        try:
            return asyncio.run(coroutine)
        except RuntimeError as exc:
            if "asyncio.run() cannot be called from a running event loop" not in str(exc):
                raise

        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, Exception] = {}

        def _runner() -> None:
            try:
                result_holder["value"] = asyncio.run(
                    self.review_dependency_candidates_with_llm_async(
                        dependency_candidates,
                        model=model,
                    )
                )
            except Exception as thread_exc:  # pragma: no cover
                error_holder["error"] = thread_exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if error_holder.get("error"):
            raise error_holder["error"]
        return list(result_holder.get("value") or [])

    def review_dependency_candidates_with_json(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
    ) -> List[Dict[str, Any]]:
        reviewed: List[Dict[str, Any]] = []
        batches = [
            dependency_candidates[index : index + _DEPENDENCY_AUDIT_BATCH_SIZE]
            for index in range(0, len(dependency_candidates), _DEPENDENCY_AUDIT_BATCH_SIZE)
        ]
        for batch in batches:
            try:
                reviewed.extend(self.review_dependency_batch_with_json(batch, model=model))
            except Exception as exc:
                self.log_dependency_audit_failure(
                    exc,
                    candidate_count=len(batch),
                    model=model,
                    fallback_scope="json_batch",
                )
                reviewed.extend(self.fallback_dependency_decisions(batch))
        return reviewed

    async def review_dependency_candidates_with_llm_async(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
    ) -> List[Dict[str, Any]]:
        semaphore = asyncio.Semaphore(_DEPENDENCY_AUDIT_MAX_CONCURRENCY)
        batches = [
            dependency_candidates[index : index + _DEPENDENCY_AUDIT_BATCH_SIZE]
            for index in range(0, len(dependency_candidates), _DEPENDENCY_AUDIT_BATCH_SIZE)
        ]
        connector = aiohttp.TCPConnector(limit=max(8, _DEPENDENCY_AUDIT_MAX_CONCURRENCY * 2))
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self.review_dependency_batch(
                    batch,
                    model=model,
                    session=session,
                    semaphore=semaphore,
                )
                for batch in batches
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        reviewed: List[Dict[str, Any]] = []
        for batch, result in zip(batches, batch_results):
            if isinstance(result, Exception):
                self.log_dependency_audit_failure(
                    result,
                    candidate_count=len(batch),
                    model=model,
                    fallback_scope="batch",
                )
                reviewed.extend(self.fallback_dependency_decisions(batch))
                continue
            reviewed.extend(result)
        return reviewed

    async def review_dependency_batch(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
    ) -> List[Dict[str, Any]]:
        async with semaphore:
            payload = {
                "candidates": [
                    {
                        "candidate_id": item["candidate_id"],
                        "source": item["source"],
                        "target": item["target"],
                        "pair_score": item.get("score"),
                        "rule_confidence": item.get("rule_confidence"),
                        "rule_reason": item.get("reason"),
                        "rule_evidence": item.get("evidence"),
                        "signals": item.get("signals"),
                        "source_requirement": item.get("source_requirement"),
                        "target_requirement": item.get("target_requirement"),
                    }
                    for item in dependency_candidates
                ]
            }
            user_prompt = (
                "请严格审查这些依赖候选，删除只是“同主题/同模块/同父节点”导致的伪依赖。"
                "只有在 source 明确以前置、输入输出、调用、读取、消费、校验依赖 target 时才确认。"
                "输入如下：\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            response = await self._service.ai.chat_completion_with_tools_async(
                messages=[
                    {"role": "system", "content": _DependencyAuditToolDef.get_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[_DependencyAuditToolDef.get_tool_schema()],
                model=model,
                temperature=0.1,
                max_tokens=3200,
                tool_choice="required",
                session=session,
            )
        return self.parse_dependency_audit_response(response, dependency_candidates)

    def review_dependency_batch_with_json(
        self,
        dependency_candidates: List[Dict[str, Any]],
        *,
        model: str,
    ) -> List[Dict[str, Any]]:
        payload = {
            "candidates": [
                {
                    "candidate_id": item["candidate_id"],
                    "source": item["source"],
                    "target": item["target"],
                    "pair_score": item.get("score"),
                    "rule_confidence": item.get("rule_confidence"),
                    "rule_reason": item.get("reason"),
                    "rule_evidence": item.get("evidence"),
                    "signals": item.get("signals"),
                    "source_requirement": item.get("source_requirement"),
                    "target_requirement": item.get("target_requirement"),
                }
                for item in dependency_candidates
            ]
        }
        response = self._service.ai.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        _DependencyAuditToolDef.get_system_prompt()
                        + '\n只返回严格 JSON：{"decisions":[...]}，不要输出额外说明。'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请严格审查这些依赖候选，删除只是“同主题/同模块/同父节点”导致的伪依赖。"
                        "只有在 source 明确以前置、输入输出、调用、读取、消费、校验依赖 target 时才确认。"
                        "输入如下：\n"
                        + json.dumps(payload, ensure_ascii=False)
                    ),
                },
            ],
            model=model,
            temperature=0.1,
            max_tokens=3200,
        )
        return self.parse_dependency_audit_response(response, dependency_candidates)

    def parse_dependency_audit_response(
        self,
        response: Dict[str, Any],
        dependency_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidate_lookup = {
            str(item.get("candidate_id") or ""): item for item in dependency_candidates
        }

        decisions: List[Dict[str, Any]] = []
        raw_decisions: List[Any] = []
        tool_calls = response.get("tool_calls") if isinstance(response, dict) else []
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("type") != "function":
                    continue
                function_payload = call.get("function") or {}
                if function_payload.get("name") != "submit_dependency_decisions":
                    continue
                arguments = function_payload.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        continue
                if isinstance(arguments, dict):
                    raw_decisions.extend(_as_list(arguments.get("decisions")))

        if not raw_decisions and isinstance(response, dict):
            parsed = _extract_json_payload(response.get("content") or "")
            if isinstance(parsed, dict):
                raw_decisions = _as_list(parsed.get("decisions"))

        for item in raw_decisions:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidate_id") or "").strip()
            candidate = candidate_lookup.get(candidate_id)
            if candidate:
                decisions.append(
                    {
                        "candidate": candidate,
                        "action": str(item.get("action") or "unclear").strip().lower(),
                        "confidence": _float_or_default(item.get("confidence"), 0),
                        "reason": self._service._clean(item.get("reason")) or "",
                        "evidence": _compact_list(_as_list(item.get("evidence")))[:8],
                        "dependency_kind": self._service._clean(item.get("dependency_kind")) or "other",
                    }
                )
        return decisions or self.fallback_dependency_decisions(dependency_candidates)

    def _supports_tool_review(self, model: str) -> bool:
        supports_tool_calls = getattr(self._service.ai, "supports_tool_calls", None)
        if callable(supports_tool_calls):
            return bool(supports_tool_calls(model=model))
        return hasattr(self._service.ai, "chat_completion_with_tools_async")

    @staticmethod
    def fallback_dependency_decisions(
        dependency_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        decisions: List[Dict[str, Any]] = []
        for candidate in dependency_candidates:
            evidence = candidate.get("evidence") or []
            has_direct_reference = any(
                item.startswith(("mentioned_module:", "shared_interface:", "shared_validation:"))
                for item in evidence
            )
            decisions.append(
                {
                    "candidate": candidate,
                    "action": "confirm" if has_direct_reference else "reject",
                    "confidence": candidate.get("rule_confidence", 0.0),
                    "reason": candidate.get("reason") or "规则回退判定",
                    "evidence": evidence[:6],
                    "dependency_kind": "other",
                    "used_fallback": True,
                }
            )
        return decisions

    @staticmethod
    def prune_transitive_dependency_edges(builder) -> int:
        dependency_edges = [
            edge for edge in builder.edges.values() if edge.get("type") == "DEPENDS_ON"
        ]
        adjacency: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for edge in dependency_edges:
            adjacency[edge["source"]].append(edge)

        removable_keys: List[Tuple[str, str, str]] = []
        for edge in dependency_edges:
            source = edge["source"]
            target = edge["target"]
            direct_weight = _float_or_default(edge.get("weight"), 0)
            if direct_weight >= 0.9:
                continue
            for step in adjacency.get(source, []):
                via = step["target"]
                if via in {source, target}:
                    continue
                for step_two in adjacency.get(via, []):
                    if step_two["target"] != target:
                        continue
                    indirect_weight = min(
                        _float_or_default(step.get("weight"), 0),
                        _float_or_default(step_two.get("weight"), 0),
                    )
                    if indirect_weight >= direct_weight + 0.05:
                        removable_keys.append((edge["source"], edge["target"], edge["type"]))
                        break
                if (edge["source"], edge["target"], edge["type"]) in removable_keys:
                    break

        for key in removable_keys:
            builder.edges.pop(key, None)
        return len(removable_keys)

    @staticmethod
    def prune_weaker_similar_edges(builder) -> None:
        removable_keys = []
        for key, edge in builder.edges.items():
            if edge["type"] == "SIMILAR_TO" and _has_stronger_relation(builder, edge["source"], edge["target"]):
                removable_keys.append(key)
        for key in removable_keys:
            builder.edges.pop(key, None)
