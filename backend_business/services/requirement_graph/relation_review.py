import asyncio
import json
import threading
from logging import Logger
from typing import Any, Callable, Dict, List, Optional

import aiohttp

from .helpers import _extract_json_payload


class _RelationReviewToolDef:
    @classmethod
    def get_tool_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_relation_mutations",
                "description": (
                    "基于候选需求对与现有关系，输出新增、修改、删除或排除关系的修订动作。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mutations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "candidate_id": {
                                        "type": "string",
                                        "description": "候选需求对 ID，必须来自输入包。",
                                    },
                                    "action": {
                                        "type": "string",
                                        "enum": ["add", "update", "delete", "reject"],
                                        "description": "新增、修改、删除或排除候选关系。",
                                    },
                                    "target_edge": {
                                        "type": "object",
                                        "properties": {
                                            "source": {"type": "string"},
                                            "target": {"type": "string"},
                                            "type": {"type": "string"},
                                        },
                                        "required": ["source", "target", "type"],
                                        "additionalProperties": False,
                                    },
                                    "replacement_edge": {
                                        "type": "object",
                                        "properties": {
                                            "source": {"type": "string"},
                                            "target": {"type": "string"},
                                            "type": {"type": "string"},
                                        },
                                        "required": ["source", "target", "type"],
                                        "additionalProperties": False,
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "reason": {
                                        "type": "string",
                                        "description": "修订原因，简短明确。",
                                    },
                                    "evidence": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "直接证据短语。",
                                    },
                                },
                                "required": [
                                    "candidate_id",
                                    "action",
                                    "target_edge",
                                    "confidence",
                                    "reason",
                                    "evidence",
                                ],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["mutations"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_system_prompt(cls, relation_types: List[str]) -> str:
        return (
            "你是需求关系复核器。"
            "只能在输入候选需求对范围内做关系修订。"
            "不能创造新节点，不能引用包外 candidate_id，不能跨 pair 改边。"
            "只允许新增或替换这些关系类型："
            f"{relation_types}。"
            "结构边（如 REFINES）不允许删除或修改。"
            "必须调用 submit_relation_mutations 工具输出。"
            "如果证据不足，对候选关系输出 reject。"
        )


class _RequirementGraphRelationReviewCoordinator:
    def __init__(
        self,
        *,
        ai: Any,
        logger: Logger,
        clean: Callable[[Any], Optional[str]],
        serialize_requirement_feature: Callable[[Dict[str, Any]], Dict[str, Any]],
        apply_llm_inference: Callable[..., Dict[str, Any]],
        pair_candidate_id: Callable[[Any, Any], str],
        existing_pair_relations: Callable[[Any, str, str], List[Dict[str, Any]]],
        resolve_node_reference: Callable[[Any, set[str]], Optional[str]],
        edge_label: Callable[[str], str],
        normalize_edge_key: Callable[[Any, Any, Any], tuple[str, str, str]],
        as_list: Callable[[Any], List[Any]],
        compact_list: Callable[[List[Any]], List[str]],
        float_or_default: Callable[[Any, float], float],
        inferred_relation_types: set[str],
        symmetric_edge_types: set[str],
    ) -> None:
        self.ai = ai
        self.logger = logger
        self.clean = clean
        self.serialize_requirement_feature = serialize_requirement_feature
        self.apply_llm_inference = apply_llm_inference
        self.pair_candidate_id = pair_candidate_id
        self.existing_pair_relations = existing_pair_relations
        self.resolve_node_reference = resolve_node_reference
        self.edge_label = edge_label
        self.normalize_edge_key = normalize_edge_key
        self.as_list = as_list
        self.compact_list = compact_list
        self.float_or_default = float_or_default
        self.inferred_relation_types = inferred_relation_types
        self.symmetric_edge_types = symmetric_edge_types

    def apply(
        self,
        builder: Any,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        enabled: bool,
        model: str,
        inference_limit: int,
        review_concurrency: int,
        package_size: int = 6,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized_concurrency = max(1, min(8, int(review_concurrency or 3)))
        empty_stats = {
            "package_count": 0,
            "reviewed_pair_count": 0,
            "added_count": 0,
            "updated_count": 0,
            "deleted_count": 0,
            "rejected_count": 0,
            "fallback_used": False,
            "model": model,
            "requested_concurrency": normalized_concurrency,
            "applied_concurrency": 0,
        }
        if not enabled or self.ai is None:
            return empty_stats

        pair_budget = max(6, min(80, int(inference_limit or 48)))
        selected_pairs = [
            pair
            for pair in candidate_pairs[:pair_budget]
            if pair.get("source") in requirement_features and pair.get("target") in requirement_features
        ]
        if not selected_pairs:
            return empty_stats

        packages = self._build_packages(
            builder,
            requirement_features=requirement_features,
            candidate_pairs=selected_pairs,
            review_concurrency=normalized_concurrency,
            package_size=package_size,
        )
        if not packages:
            return empty_stats

        if self._supports_tool_review(model):
            package_results = self._review_packages_with_llm(
                packages,
                model=model,
                review_concurrency=normalized_concurrency,
            )
        elif hasattr(self.ai, "chat_completion"):
            package_results = self._review_packages_with_json(packages, model=model)
        else:
            package_results = [RuntimeError("tool review unavailable")] * len(packages)

        stats = {
            "package_count": len(packages),
            "reviewed_pair_count": sum(len(package["candidate_pairs"]) for package in packages),
            "added_count": 0,
            "updated_count": 0,
            "deleted_count": 0,
            "rejected_count": 0,
            "fallback_used": False,
            "model": model,
            "requested_concurrency": normalized_concurrency,
            "applied_concurrency": min(normalized_concurrency, len(packages)),
        }

        for package, result in zip(packages, package_results):
            if isinstance(result, Exception):
                self.logger.warning(
                    "Requirement relation review package failed; falling back to legacy JSON review "
                    "(package=%s, pairs=%s, model=%s, error=%s)",
                    package["package_id"],
                    len(package["candidate_pairs"]),
                    model,
                    repr(result),
                )
                stats["fallback_used"] = True
                fallback_stats = self.apply_llm_inference(
                    builder,
                    project_id=project_id,
                    session_id=session_id,
                    enabled=True,
                    model=model,
                    inference_limit=max(6, len(package["candidate_pairs"])),
                    requirement_features=requirement_features,
                    candidate_pairs=package["candidate_pairs"],
                    allowed_relation_types=self.inferred_relation_types,
                )
                stats["added_count"] += fallback_stats.get("inferred_edge_count", 0)
                continue

            for mutation in result.get("mutations") or []:
                applied_action = self._apply_mutation_to_builder(
                    builder,
                    mutation=mutation,
                    package_id=package["package_id"],
                    model=model,
                )
                if applied_action == "add":
                    stats["added_count"] += 1
                elif applied_action == "update":
                    stats["updated_count"] += 1
                elif applied_action == "delete":
                    stats["deleted_count"] += 1
                elif applied_action == "reject":
                    stats["rejected_count"] += 1

        return stats

    def _build_packages(
        self,
        builder: Any,
        *,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
        review_concurrency: int,
        package_size: int = 6,
    ) -> List[Dict[str, Any]]:
        if not candidate_pairs:
            return []
        normalized_package_size = max(1, min(24, int(package_size or 6)))
        packages: List[Dict[str, Any]] = []
        for start in range(0, len(candidate_pairs), normalized_package_size):
            package_pairs = candidate_pairs[start : start + normalized_package_size]
            accepted_pairs = []
            candidates = []
            for pair in package_pairs:
                source = pair.get("source")
                target = pair.get("target")
                if source not in requirement_features or target not in requirement_features:
                    continue
                accepted_pairs.append(pair)
                candidates.append(
                    {
                        "candidate_id": self.pair_candidate_id(source, target),
                        "source": source,
                        "target": target,
                        "score": pair.get("score"),
                        "signals": pair.get("signals"),
                        "source_requirement": self.serialize_requirement_feature(
                            requirement_features[source]
                        ),
                        "target_requirement": self.serialize_requirement_feature(
                            requirement_features[target]
                        ),
                        "existing_relations": self.existing_pair_relations(
                            builder,
                            source,
                            target,
                        ),
                    }
                )
            if not candidates:
                continue
            packages.append(
                {
                    "package_id": f"pkg-{len(packages) + 1}",
                    "candidate_pairs": accepted_pairs,
                    "candidates": candidates,
                }
            )
        return packages

    def build_review_packages(
        self,
        builder: Any,
        *,
        requirement_features: Dict[str, Dict[str, Any]],
        candidate_pairs: List[Dict[str, Any]],
        inference_limit: int,
        package_size: int = 6,
    ) -> List[Dict[str, Any]]:
        pair_budget = max(6, min(80, int(inference_limit or 48)))
        selected_pairs = [
            pair
            for pair in candidate_pairs[:pair_budget]
            if pair.get("source") in requirement_features and pair.get("target") in requirement_features
        ]
        return self._build_packages(
            builder,
            requirement_features=requirement_features,
            candidate_pairs=selected_pairs,
            review_concurrency=1,
            package_size=package_size,
        )

    def _review_packages_with_llm(
        self,
        packages: List[Dict[str, Any]],
        *,
        model: str,
        review_concurrency: int,
    ) -> List[Any]:
        coroutine = self._review_packages_with_llm_async(
            packages,
            model=model,
            review_concurrency=review_concurrency,
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
                    self._review_packages_with_llm_async(
                        packages,
                        model=model,
                        review_concurrency=review_concurrency,
                    )
                )
            except Exception as thread_exc:  # pragma: no cover - defensive path
                error_holder["error"] = thread_exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if error_holder.get("error"):
            raise error_holder["error"]
        return list(result_holder.get("value") or [])

    def _review_packages_with_json(
        self,
        packages: List[Dict[str, Any]],
        *,
        model: str,
    ) -> List[Any]:
        results: List[Any] = []
        for package in packages:
            try:
                results.append(self._review_package_with_json(package, model=model))
            except Exception as exc:
                results.append(exc)
        return results

    async def _review_packages_with_llm_async(
        self,
        packages: List[Dict[str, Any]],
        *,
        model: str,
        review_concurrency: int,
    ) -> List[Any]:
        concurrency = max(1, min(int(review_concurrency or 1), len(packages)))
        semaphore = asyncio.Semaphore(concurrency)
        connector = aiohttp.TCPConnector(limit=max(6, len(packages) * 2))
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._review_package(
                    package,
                    model=model,
                    session=session,
                    semaphore=semaphore,
                )
                for package in packages
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

    async def review_packages_as_completed(
        self,
        packages: List[Dict[str, Any]],
        *,
        model: str,
        review_concurrency: int,
    ):
        if not packages:
            return
        if self._supports_tool_review(model):
            concurrency = max(1, min(int(review_concurrency or 1), len(packages)))
            semaphore = asyncio.Semaphore(concurrency)
            connector = aiohttp.TCPConnector(limit=max(6, len(packages) * 2))
            async with aiohttp.ClientSession(connector=connector) as session:
                async def _run(package):
                    try:
                        result = await self._review_package(
                            package,
                            model=model,
                            session=session,
                            semaphore=semaphore,
                        )
                        return package, result
                    except Exception as exc:
                        return package, exc

                tasks = [asyncio.create_task(_run(package)) for package in packages]
                for task in asyncio.as_completed(tasks):
                    yield await task
            return

        for package in packages:
            try:
                yield package, self._review_package_with_json(package, model=model)
            except Exception as exc:
                yield package, exc

    async def _review_package(
        self,
        package: Dict[str, Any],
        *,
        model: str,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        async with semaphore:
            payload = {
                "package_id": package["package_id"],
                "allowed_relation_types": sorted(self.inferred_relation_types),
                "candidates": package["candidates"],
            }
            user_prompt = (
                "请只对当前包里的候选需求对输出关系修订动作。"
                "新增、修改、删除都必须严格局限在 candidate_id 对应的 pair 内。"
                "输入如下：\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            response = await self.ai.chat_completion_with_tools_async(
                messages=[
                    {
                        "role": "system",
                        "content": _RelationReviewToolDef.get_system_prompt(
                            sorted(self.inferred_relation_types)
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                tools=[_RelationReviewToolDef.get_tool_schema()],
                model=model,
                temperature=0.1,
                max_tokens=3600,
                tool_choice="required",
                session=session,
            )
        return {
            "package_id": package["package_id"],
            "mutations": self._parse_response(response, package),
        }

    def _review_package_with_json(
        self,
        package: Dict[str, Any],
        *,
        model: str,
    ) -> Dict[str, Any]:
        payload = {
            "package_id": package["package_id"],
            "allowed_relation_types": sorted(self.inferred_relation_types),
            "candidates": package["candidates"],
        }
        response = self.ai.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        _RelationReviewToolDef.get_system_prompt(
                            sorted(self.inferred_relation_types)
                        )
                        + '\n只返回严格 JSON：{"mutations":[...]}，不要输出额外说明。'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请只对当前包里的候选需求对输出关系修订动作。"
                        "新增、修改、删除都必须严格局限在 candidate_id 对应的 pair 内。"
                        "输入如下：\n"
                        + json.dumps(payload, ensure_ascii=False)
                    ),
                },
            ],
            model=model,
            temperature=0.1,
            max_tokens=3600,
        )
        return {
            "package_id": package["package_id"],
            "mutations": self._parse_response(response, package),
        }

    def _parse_response(
        self,
        response: Dict[str, Any],
        package: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        candidate_lookup = {
            str(item.get("candidate_id") or ""): item for item in package.get("candidates") or []
        }

        mutations: List[Dict[str, Any]] = []
        raw_mutations: List[Any] = []
        tool_calls = response.get("tool_calls") if isinstance(response, dict) else []
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("type") != "function":
                    continue
                function_payload = call.get("function") or {}
                if function_payload.get("name") != "submit_relation_mutations":
                    continue
                arguments = function_payload.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        continue
                if isinstance(arguments, dict):
                    raw_mutations.extend(arguments.get("mutations") or [])

        if not raw_mutations and isinstance(response, dict):
            parsed = _extract_json_payload(response.get("content") or "")
            if isinstance(parsed, dict):
                raw_mutations = parsed.get("mutations") or []

        for item in raw_mutations if isinstance(raw_mutations, list) else []:
            normalized = self._normalize_mutation(item, candidate_lookup)
            if normalized:
                mutations.append(normalized)
        return mutations

    def _supports_tool_review(self, model: str) -> bool:
        supports_tool_calls = getattr(self.ai, "supports_tool_calls", None)
        if callable(supports_tool_calls):
            return bool(supports_tool_calls(model=model))
        return hasattr(self.ai, "chat_completion_with_tools_async")

    def _normalize_mutation(
        self,
        raw_mutation: Any,
        candidate_lookup: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_mutation, dict):
            return None
        candidate_id = str(raw_mutation.get("candidate_id") or "").strip()
        candidate = candidate_lookup.get(candidate_id)
        if not candidate:
            return None

        action = str(raw_mutation.get("action") or "").strip().lower()
        if action not in {"add", "update", "delete", "reject"}:
            return None

        target_edge = self._normalize_edge(
            raw_mutation.get("target_edge"),
            candidate=candidate,
            allow_extended_types=True,
        )
        if not target_edge:
            return None

        replacement_edge = None
        if action in {"add", "update"}:
            replacement_edge = self._normalize_edge(
                raw_mutation.get("replacement_edge"),
                candidate=candidate,
                allow_extended_types=False,
            )
            if not replacement_edge:
                return None

        return {
            "candidate_id": candidate_id,
            "candidate": candidate,
            "action": action,
            "target_edge": target_edge,
            "replacement_edge": replacement_edge,
            "confidence": max(
                0.0,
                min(1.0, self.float_or_default(raw_mutation.get("confidence"), 0.65)),
            ),
            "reason": self.clean(raw_mutation.get("reason")) or "",
            "evidence": self.compact_list(self.as_list(raw_mutation.get("evidence")))[:8],
        }

    def _normalize_edge(
        self,
        raw_edge: Any,
        *,
        candidate: Dict[str, Any],
        allow_extended_types: bool,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_edge, dict):
            return None
        valid_node_ids = {candidate.get("source"), candidate.get("target")}
        source = self.resolve_node_reference(raw_edge.get("source"), valid_node_ids)
        target = self.resolve_node_reference(raw_edge.get("target"), valid_node_ids)
        edge_type = self.clean(raw_edge.get("type"))
        if not source or not target or not edge_type or source == target:
            return None
        if allow_extended_types:
            if edge_type not in (self.inferred_relation_types | {"REFINES", "SIMILAR_TO"}):
                return None
        elif edge_type not in self.inferred_relation_types:
            return None
        if tuple(sorted((source, target))) != tuple(sorted((candidate["source"], candidate["target"]))):
            return None
        if edge_type in self.symmetric_edge_types and source > target:
            source, target = target, source
        return {"source": source, "target": target, "type": edge_type}

    def _apply_mutation_to_builder(
        self,
        builder: Any,
        *,
        mutation: Dict[str, Any],
        package_id: str,
        model: str,
    ) -> Optional[str]:
        action = mutation.get("action")
        target_edge = mutation.get("target_edge") or {}
        replacement_edge = mutation.get("replacement_edge") or {}

        if action == "add":
            if not replacement_edge:
                return None
            existing_edge = builder.edges.get(
                self.normalize_edge_key(
                    replacement_edge["source"],
                    replacement_edge["target"],
                    replacement_edge["type"],
                )
            )
            if existing_edge and not self._is_protected_edge(existing_edge):
                builder.remove_edge(
                    replacement_edge["source"],
                    replacement_edge["target"],
                    replacement_edge["type"],
                )
            builder.add_edge(
                replacement_edge["source"],
                replacement_edge["target"],
                replacement_edge["type"],
                label=self.edge_label(replacement_edge["type"]),
                weight=mutation["confidence"],
                properties=self._build_review_properties(
                    mutation,
                    package_id=package_id,
                    model=model,
                ),
            )
            return "add"

        if action == "reject":
            return "reject"

        existing_edge = builder.edges.get(
            self.normalize_edge_key(
                target_edge.get("source"),
                target_edge.get("target"),
                target_edge.get("type"),
            )
        )
        if not existing_edge or self._is_protected_edge(existing_edge):
            return None

        if action == "delete":
            builder.remove_edge(
                target_edge["source"],
                target_edge["target"],
                target_edge["type"],
            )
            return "delete"

        if action == "update" and replacement_edge:
            builder.remove_edge(
                target_edge["source"],
                target_edge["target"],
                target_edge["type"],
            )
            builder.add_edge(
                replacement_edge["source"],
                replacement_edge["target"],
                replacement_edge["type"],
                label=self.edge_label(replacement_edge["type"]),
                weight=mutation["confidence"],
                properties=self._build_review_properties(
                    mutation,
                    package_id=package_id,
                    model=model,
                ),
            )
            return "update"
        return None

    def _build_review_properties(
        self,
        mutation: Dict[str, Any],
        *,
        package_id: str,
        model: str,
    ) -> Dict[str, Any]:
        return {
            "source_kind": "llm",
            "source_detail": "llm_tool_review",
            "source": "llm_tool_review",
            "confidence": mutation.get("confidence"),
            "reason": mutation.get("reason"),
            "evidence": mutation.get("evidence"),
            "model": model,
            "review_action": mutation.get("action"),
            "review_package_id": package_id,
        }

    @staticmethod
    def _is_protected_edge(edge: Dict[str, Any]) -> bool:
        props = edge.get("properties") or {}
        if edge.get("type") == "REFINES":
            return True
        return props.get("source_kind") == "structural"
